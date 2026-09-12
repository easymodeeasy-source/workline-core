---
name: roadmap
description: Convert a human goal into a Workline Roadmap and meaningful Phases, maintain future planning, select startable Phases, expand a Phase into Works when it is actually entered, and explicitly judge Roadmap achievement. Use ONLY inside an established Workline Project (one that already has .workline/project.yaml) for Roadmap creation, planning changes, Phase selection/entry, Roadmap or Phase hold/resume/cancel, and achievement checks. Not for generic product roadmaps, planning documents, or any repository that is not a Workline Project.
---

# Roadmap

人間のまとまった目的をRoadmapとPhaseへ変換し、未来計画を維持し、現在着手すべきPhaseを選び、Phase着手時にWork構造を設計し、Roadmap達成までのPhase間進行を管理する。

## Responsibility

- Roadmap name / background / desired state
- optional scope / out-of-scope
- Phase分割
- Phase間relationの意味決定
- Phase CREATE呼び出し
- startable Phase算出・選択
- Phase着手時のWork構造設計
- CREATE呼び出し
- 初回phase_integration_check設計
- structural human_confirmation要否の初期判断
- STARTへのhandoff
- future-plan maintenance
- hold / resume / cancel / plan exclusion
- Roadmap achievementの明示判定

直接Phase / Work fileを書かず、登録はPhase CREATE / CREATE + Mutation Controllerを使う。

STARTの代わりにWorkを実行しない。STARTを次Phaseへ越境させない。

## Roadmap format

stable ID:

```text
r_<ULID-like>
```

表示用 `R-xx` はidentity/orderではない。

概念:

```yaml
---
id: r_...
display: R-...
type: roadmap
---
```

```md
# <Roadmap名>

## 背景
...

## 達成したい状態
...

## 対象範囲
必要な場合のみ

## 対象外
必要な場合のみ
```

state、Phase一覧、progress、current target、next Work、詳細実装、generic issueをRoadmap bodyへ保存しない。

## New Roadmap

新Roadmap作成時にRoadmap全体を意味のある中間到達点でPhase分割し、全Phaseを登録する。ただしWorkは展開しない。

Phase:

> Roadmapの目標を意味のある中間到達点へ分割した単位。

implementation / test / docs等の機械的カテゴリだけでPhaseを分けない。

正式流れ:

```text
Roadmap意味決定
↓
全Phase意味決定
↓
Phase間relation意味決定
↓
Phase CREATE群
↓
Roadmap構造検査
↓
Roadmap operation commit / push
```

Phase CREATEへ決定済みPhase relation payloadを渡してよい。Phase CREATE自身にrelation意味を考えさせない。

## Phase relations

意味ownerはRoadmapのみ。

```text
planned_next
→ 推奨順

requires_completion
→ execution constraint

derived
→ historical causal fact

return_to
→ future return plan
```

表示番号を実行順として使わない。

`derived` はhistory。その他はfuture planで正式経路から変更可能。

cancelled / plan_excluded前提はrequires_completionを満たさない。dependencyを外す・代替Phaseを作る等のreplanをRoadmapが行う。

## Startable Phase

候補条件:

- Roadmapがcancelled / achievedでない
- Roadmap heldなら先にresume
- Phaseがcomplete / held / cancelled / plan_excludedでない
- incoming `requires_completion` predecessorが全てcompleted
- refs / membership / structure valid

候補0件:

- active Phaseが全てcompleteならRoadmap achievement check
- それ以外はdependency / hold / cancel / plan exclusion / broken structureを診断
- 推測で次Phaseを選ばない

複数候補:

- 人間の明示意図
- planned_next
- dependency
- 既存priority / external constraint / target
- parallel safety

から選ぶ。成果意味が大きく変わる選択なら `rules/human-confirmation`。

## Phase entry

WorkはPhaseへ実際に入る時だけ展開する。

既にWorkが展開されたPhaseへ、新しいentry designを渡してPhase entryを再実行しない。展開済みPhaseにはdesignが登録する対象がなく、渡されたdesignを黙って無視すれば、呼び出し側が別の計画が登録されたと誤認し得る。Phase entryはこれを `phase_already_expanded` でSTOPし、design無視・既存entryへの差し替え・通常成功としての返却・ID発行・mutation開始・canonical state変更・commitのいずれも行わない。展開済みPhaseの現在構造はread-onlyで読み、計画の正式変更はRoadmapのRelated maintenance等から行う（`rules/ai-decision`）。なお、Roadmapがactiveでない場合、Phaseがcomplete / held / cancelled / plan_excludedの場合、Phaseのdependencyが未充足の場合は、従来どおりそれぞれの理由でSTOPし、`phase_already_expanded` より優先する。どの経路でもcanonical stateは変更しない。

ただしこのPhase自身のPhase entryが中断してpending mutationが残っている状態は、呼び出し側の再実行ではなくrecovery stateであり、`phase_already_expanded` として扱わない。中断した展開は同じmutationで前へ進めて完了させる。

Phase entryは、最初のID予約より前に、展開対象のdesignをmutationのinvocationへ記録する。記録する内容は、通常Workの宣言順・key・name・成立状態・Related（type / to / condition）、integration、human_confirmationの有無と内容、`planned_next`、`requires_completion`、明示entry、およびこの記録形式のversionとする。通常Workの順序はdisplay番号を決めるため意味を持ち、並べ替えを同一designとして扱わない。

再実行のdesignが記録済みdesignと一致する場合だけ、そのpending mutationをresumeする。既に記録済みのstageはcaller specから決め直さず、記録済みeffectをclassify / applyし、そのstageのIDと結果は記録済みreserved ID / effectから再構成する。未記録のstageだけを、同一性が確認されたcaller designから決める。記録済みのdesignと一致しない再実行は `reconcile_required` とし、既存のpending mutationを別のdesignで継続しない。前半は記録済みdesign、後半は再実行designという混在を作らない。

designを記録していない旧実装のpending phase-entry recordは自動resumeしない。どの中断位置でも `reconcile_required` とし、pending record・effects・reserved IDs・statusをそのまま保持する。rollback・abandon・削除・新しいmutationへの差し替えは行わない。診断にはmutation id、Phase id、legacy phase-entry pendingであること、自動resumeにはdesign記録が不足していることを含める。

中断した展開のmutationは、resume中のSTOPでabandonしない。今回の実行が新しく開いたPhase entryがeffect記録前にSTOPした場合にabandonする既存の動作は変えない。

明示entryの妥当性は、domain write・mutation effect・Git commit / pushより前に検査する。designのWork keyに存在しないentry、およびこの展開が作るWorkの完了を待つことになるentryは、展開前にSTOPする。既存Workの完了を待つentryは、その既存Workが既にcompletedなら妥当である。

Work:

> その部分だけで何が成立したかを言え、別々に着手・中断・派生・完了を管理する意味がある単位。

正式流れ:

```text
Phase成立状態を読む
↓
既に展開済みならread-onlyで現在構造を検査し、Phase entryを再実行しない
↓
未展開の場合だけ通常Work群を設計
↓
CREATE 通常Work群
↓
通常Work ID群を取得
↓
初回 phase_integration_check を設計
↓
CREATE integration + 通常Work群→integration requires_completion
↓
human_confirmationの構造的必要性を初期判定
↓
必要ならCREATE human_confirmation + integration→confirmation requires_completion
↓
Phase構造検査
↓
Roadmap operation commit / remoteありなら承認先へpush
↓
実行要求がある場合STARTへhandoff
```

CREATEにintegrationを自動生成させない。

初回integrationの意味ownerはRoadmap。

## human_confirmation

人間判断そのものがPhase成立条件の構造的一部ならspecial Workとして作る。

単なる質問・確認待ちでは作らない。

integration実行時に実結果を見て必要性を再評価する。初期判定で不要でも、実結果から人間確認が構造的に必要になればSTARTが追加判断する。

## START handoff

Phase実行要求がある場合、entry Workを選び `START mode=outer` を呼ぶ。

STARTは同一Phase完了またはstopでRoadmapへ戻る。次Phaseへ自動越境しない。

人間がRoadmap全体を連続実行する意図を明示している場合のみ、START return後にRoadmapがstartable Phaseを再計算して次Phaseを選べる。

## Future plan maintenance

未開始Phase / Workはfuture plan。上位目的を維持し成果意味を大きく変えない範囲で正式経路から変更可。

未開始Workをcurrent future planから外す場合は `plan_excluded` を記録する。物理deleteや `phase_id` 書換えはしない。そのoperationで影響する `requires_completion` / integration prerequisite / `planned_next` / `return_to` もreplanし、構造validationを通す。

開始済みPhase / Workの成立状態を完了しやすく変更しない。開始済みWorkに `plan_excluded` は使わない。実行不要になった開始済みWorkはSTARTのcancel経路で扱う。

started Workを別Phaseへ移さない。

historical `derived` / origin / eventsを書き換えない。

### 既存未開始WorkのRelated maintenance

登録済みWorkのRelated relationもfuture planであり、正式経路で追加・削除できる。

```text
must_read
conditional_must_read
obey
realizes
must_update
conditional_must_update
```

意味ownerはRoadmap。Phase entry時に `WorkDesign.related` の意味を決めたのがRoadmapである以上、その後の計画修正もRoadmapが所有する。CREATEはregistration coreのままであり、既存Workの意味変更ownerにしない。

対象は「既存の、まだ未開始の、Roadmap配下Work」だけ。

```text
Work generated state = unstarted
origin.type = roadmap
phase_idが解決可能
Roadmapが通常操作可能
```

started / held / completed / cancelled / plan_excluded Workのrelated変更はこの経路で行わない。standalone Workも対象外。

terminal Work（completed / cancelled / plan_excluded）のRelatedは、そのWorkが当時読む / 満たす必要があったもののhistorical evidenceである。後続Workがtargetを正式に削除しても、そのedgeを削除・書換えせず、targetの不在だけでbroken扱いにもしない。

started（in_progress / held）Workのrelated変更経路は設けない。代わりに、Workline自身のoperationがその不整合を作らない（`skills/start` のWork result / completion precheck）。外部操作でtargetが失われた場合は、次のSTARTが `related_target_missing` でSTOPする。

削除は既存relation IDの指定で行う。対象Workがfromである実在relationだけが削除可能で、別Work所有のrelation IDや解決不能なIDはSTOPする。名前・target・意味類似で補完しない。

`roadmap.yaml` のrelationはこの操作では触らない。Work本文・`origin`・`phase_id`・eventsも書き換えない。

これはlifecycle eventではない。`work_started` / `plan_excluded` / `work_target_added` 等を記録せず、`events.jsonl` は不変。

同一edge（type / from / to / condition が同一）が既に存在する場合は重複追加しない。有効変更が0件ならno-opとして正常終了し、commitもpushもrelation IDの発行も行わない。

request identityはrequest内容だけから決まり、current related stateに依存しない。identityはadd / removeの構造そのもので持ち、区切り文字で連結したlabel文字列では持たない（別内容のrequestが同じlabel文字列になり得る）。request自身の中の重複（同一edgeの重複指定・同一relation IDの重複削除）は、operationがもともと1件として扱うので、identityを作るより前・request解決より前に畳む。畳んだ後の位置からrelation IDを予約するので、同じ意味の綴り違いが同じIDをresumeする。畳むとdefault labelも変わるため、畳む前のlabelの下にあるpending recordも探す（そこに残り得るのはrequestを記録していない旧implementationのrecordだけで、見落とすとno-opとして取り残される）。matching pending mutationが既にeffectsをdurable記録している場合は、current stateから対象を再解決せず記録済みeffectsを正としてresumeする。

```text
remove effect適用後にcommit前失敗
→ 現在のrelated.yamlに対象relationは無い
→ これを「unresolvable」と判定しない
→ 記録済みmutationのeffectsから継続する
```

適用済みeffectの判定はMutation Controllerの `未適用 / 適用済み・期待値一致 / 適用済み・期待値不一致` に委ねる。resume時に新しいrelation IDやmutationを作らない。

まだeffectsを記録していないpending mutationは、何も適用されていないので通常のcurrent-state validationから続行してよい。新規operationでは解決不能relation IDを引き続き拒否する。

**`relations/related.yaml` の手編集は禁止。** Work再作成やplan exclusionでrelated不足を回避しない。Mutation Controller経由の正式経路を使う。

## Lifecycle

Phase hold:

```text
phase_held
```

child Workを暗黙holdしない。

Phase resume:

```text
phase_resumed
```

startable Workを再計算し、全childを暗黙resumeしない。

Phase cancel:

```text
phase_cancelled
```

child Workを暗黙cancelしない。

未開始Phaseをfuture planから外す:

```text
plan_excluded
```

物理deleteしない。

未開始Workをfuture planから外す場合も同じ `plan_excluded` terminalをそのWorkへ記録し、relation / integrationを同じRoadmap operationでreplanする。

Roadmap:

```text
roadmap_held
roadmap_resumed
roadmap_cancelled
roadmap_achieved
```

holdはchildへ自動伝播しない。cancelもchildを暗黙cancelしない。

cancelled / achieved Roadmapへ通常新Phaseを追加・開始しない。

## Future relation normalization

未来計画変更を決めたRoadmap operationがPhase / 未開始Workのfuture relation正規化も決める。

- planned_nextの候補がterminal/inactive → active future planから除外可
- return_to先がcancelled / plan_excluded → replan
- requires_completion predecessor cancelled / plan_excluded → satisfied扱いせずblockedのままreplan
- Work plan exclusionでintegration prerequisiteが変わる → integration dependencyを再設計

物理writeはMutation Controller。

## Roadmap achievement

全active Phase completeだけでRoadmap達成としない。

```text
全active Phase complete
↓
Roadmapの「達成したい状態」を明示評価
```

客観的に満たす → `roadmap_achieved`

人間判断が成果成立の一部 → 人間確認

未達 → desired stateを変えず追加Phase / replan

desired state自体の変更が必要 → human confirmation

上記の明示評価はcallerが行うsemantic judgementであり、Project execution lockはこの判断をlock内で再実行しない。`roadmap_achieved` を記録する場合は、記録直前にlock内でWorkline canonical stateのstructural precondition（Roadmapが通常操作可能・全active Phase complete）を再確認し、成立する時だけ記録する。lock取得前に読んだWorkline structural stateをwrite判断へ使い回さない。lockは判断に用いたdomain evidence（成果物・verification結果等）のatomic snapshotを保証しない。記録を伴わない判定・診断はlockを取らない。

Roadmap start event / Phase completion eventは作らない。stateは生成する。

## Mutation / Git

RoadmapがRoadmap operation owner。

Roadmap body / Phase / relation / Work構造の変更は同じ上位mutationへ束ねられる。Phase CREATE / CREATEは子登録処理で独立commit / pushしない。

Phase展開後、STARTへ渡す前にRoadmap-owned structural changesをcommitし、remoteありならpushする。

pushする場合の宛先は `rules/git` のpush destinationに従う。各Roadmap operationはmutationを開くより前・networkより前に承認先一致を検査し、承認先なし / 不一致はSTOPする。Roadmap操作で承認先を変更しない。

途中失敗は同じmutationをresume。期待値不一致ならreconcile required。

callerが内容を決めるRoadmap operation（Roadmap作成 / Phase追加 / Related maintenance）は、最初のID予約より前に、決定内容の正規identityをそのmutationのinvocationへ記録する。operationと対象・labelだけのinvocationは、別内容の再実行を同じrequestと見なして記録済みstageを飛ばし、Projectには最初のrequestが決めた内容が残ったまま成功を返し得る。postcheckはentityが解決でき成立状態section等を持つことを見るが、今回のrequestが決めた本文内容と正本を突き合わせないため、これを検出しない。Phase relationのように決定payloadとの一致を検査する部分はあるが、それは `postcheck_failed` として遅れて止まるだけで、requestの取り違え自体を防がない。

記録内容（いずれもこの記録形式のversionを含む）:

- Roadmap作成: Roadmap name / 背景 / 達成したい状態 / 対象範囲 / 対象外、全Phaseのkey・name・成立状態を宣言順で、Phase間relationを宣言順で
- Phase追加: 追加Phaseのkey・name・成立状態を宣言順で、Phase間relationを宣言順で
- Related maintenance: 追加edge（type / to / condition）と削除relation IDを指定順で

nameはrenderingがそのまま書くのでverbatim、section本文はrenderingがstripするのでstrip後で比較する。任意sectionは有無と内容を別に記録する。宣言順はdisplay番号やID予約の対応を決めるため意味を持ち、並べ替えを同一requestとして扱わない。

同じslot（operation・対象・label）に未完了mutationがある場合、記録済みrequestが今回のrequestと一致する時だけresumeする。一致しない再実行は、mutationを開くより前・記録済みeffectをreplayするより前・no-op判定より前に `reconcile_required` とし、pending record・effects・reserved IDs・statusをそのまま保持する。rollback・abandon・削除・新しいmutationの開始は行わない。

requestを記録していない旧実装のpending recordは自動resumeしない。どの中断位置でも `reconcile_required` とし、同じく何も変更しない。診断にはmutation id、対象operation、requestを記録する前に書かれたrecordであることを含める。

`invocation_key` はcallerのlabelであって識別子ではない。label文字列の一致だけでresumeを決めない。

held Roadmapへの正式なfuture-plan変更が決定済みかどうかは、request一致検査の後・mutationを開くより前に検査する。この判定はeffectに到達せず登録内容を変えないためrequest identityへ含めない。request一致検査より後に置くのは、継続できないpending recordの存在をlifecycle factで隠さないため。mutationを開くより前に置くのは、拒否された再実行が既存のpending mutationをabandonしないため。

Roadmap operationは `rules/git` のProject contextに従い、対象Projectのcontextから実行する。invocation Project contextが対象Projectと一致しなければ、lockを取得する前に `foreign_project_mutation` でSTOPし、何も書かない。

Roadmap operationにはCLIが無い。`rules/git` のWorkline implementationに従い、対象Projectの中でisolated Python processを開始し、同じprocessで `<R>/run-workline.py` の `activate()` を実行してから、RoadmapのPython APIをimportする（R = configured Workline root）。Project contextの照合の後、実行中のimplementationがconfigured rootのものでなければ、lockを取得する前にSTOPし、何も書かない。PYTHONPATHの手組みや別のimplementationへfallbackしない。

Roadmap operationは `rules/git` のProject execution lockを取得してから、Roadmap / Phase / Work state・dependency・pending mutation・push destinationを読む。lock取得前に読んだWorkline structural stateをwrite判断へ使い回さない。Phase CREATE / CREATEは同じlockとmutationへ参加し、lockを取り直さない。STARTへのhandoffはRoadmap operationが戻ってlockを解放した後に行う。他processが同じProjectで実行中なら待たずに `project_operation_busy` でSTOPし、何も書かない。
