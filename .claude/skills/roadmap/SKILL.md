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

現在適用する正式条件は、この順に次の3つだけである。

1. 人間の明示意図（明示されたPhaseが候補にあればそれを選ぶ）
2. `planned_next`（下記「候補選択の決着」）
3. dependency（候補条件で既に適用済み。未充足のPhaseは候補に入らない）

成果意味が大きく変わる選択なら `rules/human-confirmation`。

将来の設計候補（**現在は未実装**。schemaにもrelationにも存在せず、選択条件として適用されない）:

```text
既存priority
external constraint / target
parallel safety
```

これらを「現在適用される条件」として扱わない。実装が無いものを適用したつもりで候補を絞らない。

## 候補選択の決着

startable Phaseの選択と、Phase entry / handoffのentry Work選択と、STARTの同一Phase内継続は、同じ規則で決着させる。

`planned_next` は推奨順である。候補が2件以上あるとき、次の順に絞る。各段階は結果が残る場合だけ適用する。

1. 既にcompleted / completeなentityが `planned_next` で次に推奨している候補
2. そのうち、まだ終わっていないentityから `planned_next` で前に置かれていない候補

cancelled / plan_excludedのpredecessorは二度と終わらないので、候補を後ろへ押さえない。

絞った結果が1件ならそれを選ぶ。

**2件以上残る場合は選ばずSTOPする。** 候補listの先頭・ID順 / ULID順・relation fileの記録順・宣言順・表示番号・dict / listの挿入順など、内部順序に由来するものでtieを破らない。これらはいずれも実行順ではない。診断には候補のIDを含め、人間が明示選択できるようにする。

STOPの位置は経路によって違う。共通なのは「選べなかった候補のためにcanonical stateを進めない」ことであり、「STOPすれば何も起きていない」ではない。

startable Phase選択・新規Phase entry・handoff:

> ambiguityは新しいcanonical writeより前に判定する。ID予約・mutation開始・entity書込み・commit / pushのいずれも行わず、Projectは操作前のままである。handoffはSTARTもexecutorも起動しない。

STARTの同一Phase内継続:

> 直前のWorkは既に正当に完了しており、そのlifecycle eventとcommitはcanonical stateに残る。これは曖昧さとは無関係に成立した事実なので巻き戻さない。ambiguityが分かった後は、次の候補のためのlifecycle event・derived Work・mutation・commit / pushを作らずstopとして返す。直前Workのfinalizationは通常どおり閉じ、pending mutationを残さない。

中断した展開のresumeはこの判定の対象にしない。`skills/roadmap` のPhase entryが定めるとおり最後まで進め、entry Workが一意に決まらない場合はentryなしとして返す。実行時のentry指定はhandoffが求める。

## Phase entry

WorkはPhaseへ実際に入る時だけ展開する。

既にWorkが展開されたPhaseへ、新しいentry designを渡してPhase entryを再実行しない。展開済みPhaseにはdesignが登録する対象がなく、渡されたdesignを黙って無視すれば、呼び出し側が別の計画が登録されたと誤認し得る。Phase entryはこれを `phase_already_expanded` でSTOPし、design無視・既存entryへの差し替え・通常成功としての返却・ID発行・mutation開始・canonical state変更・commitのいずれも行わない。展開済みPhaseの現在構造はread-onlyで読み、計画の正式変更はRoadmapのRelated maintenance等から行う（`rules/ai-decision`）。なお、Roadmapがactiveでない場合、Phaseがcomplete / held / cancelled / plan_excludedの場合、Phaseのdependencyが未充足の場合は、従来どおりそれぞれの理由でSTOPし、`phase_already_expanded` より優先する。どの経路でもcanonical stateは変更しない。

ただしこのPhase自身のPhase entryが中断してpending mutationが残っている状態は、呼び出し側の再実行ではなくrecovery stateであり、`phase_already_expanded` として扱わない。中断した展開は同じmutationで前へ進めて完了させる。

Phase entryは、最初のID予約より前に、展開対象のdesignをmutationのinvocationへ記録する。記録する内容は、通常Workの宣言順・key・name・成立状態・Related（type / to / condition）、integration、human_confirmationの有無と内容、`planned_next`、`requires_completion`、明示entry、およびこの記録形式のversionとする。通常Workの順序はdisplay番号を決めるため意味を持ち、並べ替えを同一designとして扱わない。

再実行のdesignが記録済みdesignと一致する場合だけ、そのpending mutationをresumeする。既に記録済みのstageはcaller specから決め直さず、記録済みeffectをclassify / applyし、そのstageのIDと結果は記録済みreserved ID / effectから再構成する。未記録のstageだけを、同一性が確認されたcaller designから決める。記録済みのdesignと一致しない再実行は `reconcile_required` とし、既存のpending mutationを別のdesignで継続しない。前半は記録済みdesign、後半は再実行designという混在を作らない。

designを記録していない旧実装のpending phase-entry recordは自動resumeしない。どの中断位置でも `reconcile_required` とし、pending record・effects・reserved IDs・statusをそのまま保持する。rollback・abandon・削除・新しいmutationへの差し替えは行わない。診断にはmutation id、Phase id、legacy phase-entry pendingであること、自動resumeにはdesign記録が不足していることを含める。

中断した展開のmutationは、resume中のSTOPでabandonしない。今回の実行が新しく開いたPhase entryがeffect記録前にSTOPした場合にabandonする既存の動作は変えない。この規則はlegacy Phase entryのものである。review-v1 Phase entryのplanning mutationは、最初のgeneration mutationを開始するまでは、開始したものでもresumeしたものでも、どのSTOPでもabandonする（Review-v1 planning）。

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

明示のentry Workが無い場合は「候補選択の決着」で選ぶ。2件以上残るならSTARTを呼ばずSTOPし、entry Workの明示を求める。

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

cancelしたPhaseは二度と完了しない。そのPhaseを `requires_completion` のpredecessorとして待つPhase、または `return_to` 先として戻る予定のPhaseが、cancelled / plan_excludedでないまま残ると、構造は `dependency_unreplanned` / `return_to_unreplanned` になる。Phase cancelは、現在stateへ `phase_cancelled` を1件加えた投影を通常の構造validationで検査し、不正になる場合はmutationを開かず、event・recovery record・commit・pushのいずれも作らずに `spec_violation` でSTOPする。plan exclusionやWork cancelのreplan検査と同じ投影検査であり、独自の依存規則を持たない。待っているPhaseのreplan（dependencyを外す、そのPhaseをcancel / plan exclusionする等）を正式経路で先に行う。構造が不正にならないcancel（誰にも待たれていない、待つ側が既にcancelled / plan_excluded、別Roadmapの無関係なrelationだけがある等）は従来どおり記録・commit・pushする。

この検査は前提条件の一部として判定する。自分の未完了mutationが既に `phase_cancelled` を適用した後の再実行では、そのeventを除いたstateで判定し直すので（Mutation / Git参照）、投影はeventを1回だけ加え、自分自身のresumeを拒否しない。記録済み・未適用のeventをresumeする場合も適用より前に検査し、中断の間に構造が変わって不正になっていれば、eventを適用せずpending recordを変更しないままSTOPする。構造検査をcommit / pushの後に行っていた旧実装が既に公開した不正なcancelは自動repairせず、従来どおり構造検査でSTOPする。

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

## Review-v1 planning（明示opt-in）

Roadmap作成とPhase entryは、呼び出しごとの明示opt-inでだけReview gate（`skills/review`）を通る。`create_roadmap(..., review=PlanningReview(...))` / `enter_phase(..., review=PlanningReview(...))` がreview-v1 planningであり、`review=None`（既定）はlegacy pathで従来と1 byteも変わらない。opt-inはdurable invocationのmarker（`review_contract: review-v1-planning-v1`、`publication_contract: review-v1-planning-publication-v1`、recoveryでは `recovery_of_review_run_id`）として記録し、markerの無いrecordとある呼び出し、またはその逆は `reconcile required`（`review_marker_mismatch`）で停止してrecordを変えない。opt-inしたinvocationがlegacyへfallbackすることはない。

入口（lockより前）: 不正な `review` 引数は `review_contract_invalid`、immutable Review createを保てないplatformは `review_create_unsupported`、`rules/git` のreview-v1最小version `P2_REVIEW_GIT_MIN` より古いGit・version不明のGitは `review_git_unsupported` で停止し、何も読まず書かない。

entry順（両kindで固定）:

```text
1  引数・platform・Git versionの検査（lockより前）
2  requestのidentityより前のlive検査（Roadmap作成: payload検査と構造precheck。Phase entry: 構造precheck、
   Phase・Roadmap・lifecycleの状態、依存）。continuation modeではこのうち可変の受理factは拒否しない（下記）
3  request identity（live の roadmap_request_identity / design_identity）
4  canonical-input preflight: conditional Relatedのconditionをliveの validate_condition で検査し（拒否はliveと
   同じ validation_failed）、request identityをP1のserializerだけで表せることを示す。表せない値（float、tuple、
   textでないkey、空key、sequence内のsequence、lone surrogate）は review_candidate_unrepresentable。
   _open より前なので何も開始しない
5  liveのsame-request検査とmarker検査
6  残りのliveの受理検査（Phase entry: phase_already_expanded、通常Workが1つ以上、予約key、明示entryの
   開始可能性、unique entry）。このPhase自身の中断したreview-v1 Phase entryには、liveの中断展開の規則どおり
   phase_already_expanded と unique entry を適用しない。continuation modeでは明示entryの開始可能性も拒否しない
7  slotにpendingなreview-v1 planning mutationが無い時だけ、canonical recovery discovery（skills/review）
8  _open: pendingなplanning mutationを記録済みinvocationでresume、または新しいRun / recoveryのmutationを開始
9  setup（新しいRunのfreeze、recoveryのbinding、中断したsetupの完成）の後にReviewの流れ
```

liveのRoadmap semanticsがoperationとして受理できるかを先に決め（2・5・6）、その後でReview recoveryがどのRunを続けるかを決める（7）。

新しいRunのfreeze（順序固定）:

```text
1  予約: Roadmap作成は roadmap と decide_phases のPhase / relation ID、Phase entryは register_works のkeyの
   全stageのID。entity scopeを広げる
2  HEADのcommitted basis（committed-result loaderによるHEADのcommitted view + Wの期待effect）でCandidateを
   作る: declared base、R9選択、working-tree互換検査、表現可能性検査
3  Review Context、Effective Policy、evidence、request envelope
4  Run / task / Receipt / ConsumptionのID予約。Consumption pathをfile scopeへ加える
5  gate.require_committable、Git persistence preflight（transform属性とcheckout capability）、Review namespaceの
   読取り可能性、dirty overlap（登録path + Run record path + Consumption path）、push先があれば
   HEADについてのpublication barrier
6  noteの review_binding（branchとHEAD）
7  generation mutation 1を開始する
```

**R9のcanonical self-selection**（このSkillが所有する）: 最初のWorkは、HEADのcommitted basis上の `startable_works` + `planned_next_preference` だけで決まり、working treeでは決めない。明示entryをどう拒否するかもこのcanonical selectionが決め、callerが名指したWorkでは決めない。

- 優先候補が一意（A）: canonical_first_workはA。明示entryがAなら有効で、A以外のWorkを名指せば `review_entry_not_canonical`。このcodeは、canonicalな最初のWorkがあるのにcallerが別のWorkを名指した場合だけに使う。
- 優先候補が同順位で複数（曖昧）: 明示entryはどれも `review_entry_ambiguous` で拒否する。同順位のWorkの1つを名指しても、同順位の外の開始可能なWorkを名指しても同じである（committed basisがどのWorkを最初にするか決めていないので、どの明示entryもcanonicalにならない）。entry無しの同順位はliveの `ambiguous_startable_candidates`。
- 開始可能なWorkが無い: canonical_first_workはnull。明示entryは、liveの開始可能性検査が `_open` より前に従来どおり拒否する。

特定のWorkから始めるdesignは、`planned_next` でそう計画して選択を一意にする。明示entryがcommitted basisを上書きすることはない。working treeとHEADがdeclared base・PhaseのWork集合・R9選択のどれかで違えば、freezeで `review_base_uncommitted` として停止する（commitまたは破棄してから再実行する）。

**currency**: currencyは1つのbase commitについて、Context、Policy、そのcommitのcommitted viewで計算したdeclared base、そしてdeclared baseが等しい時だけCandidateの再構築（R9選択を含む）、の順で判定する。declared baseの差は常にdeclared baseの差として1回だけ分類し、R9やCandidateの不一致として報告しない。sealの前のstaleは何も書かずterminal `stale`、sealの後・登録開始前のstale（use check）はgeneration 4とSupersessionを書いてから `stale`。use checkが通るとHEADを `use_check_head` として記録する。最初の登録stageを記録した後は `stale` で終わらず、差は `reconcile required` になる: Kpを記録する直前のpre-Kp currency proof（P = HEAD。Pは `use_check_head` 自身、またはその子孫でplanning-owned pathに触れていない履歴であること、Runのrecordがcommit済みであること、currency、記録した登録effectがexpected physical projectionそのものであること）が `review_registration_base_moved` / `review_receipt_invalid` / `review_registration_currency_changed` / `review_candidate_mismatch` / `review_registration_projection_mismatch` で止める。working-tree round tripはR9選択をHEADのcommitted basisから読むが、HEADのdeclared baseがCandidateのものと違う場合はその差をpre-Kp currency proofに分類させ、R9不一致として止めない。declared baseが等しいのに、登録したworking treeの意味がReviewの許可したものと違えば、round trip自身が `review_roundtrip_mismatch` で止め、Kpを作らず、planning mutationはpendingのまま残る。

**terminal**: `registered`（登録が公開された、remoteなしではC-2(Km)が通った）、`not_authorized`（reviewが許可しなかった。何も登録しない）、`stale`（sealの前、またはsealの後にgeneration 4とSupersessionを書いた）。

**Phase entry continuation mode**: Phase entryのlive検査は「いまここで新しいPhase entryを始めてよいか」を答える。
review-v1 Phase entryは2回目以降の呼び出しで別の問いも立てる。「このProjectが既に始めたPhase entryを最後まで
運んでよいか」である。後者を前者のfactで決めると、canonicalになったRunが止まる。

境界はcanonical stateだけから読む。slot（このPhase）にreview-v1 Phase entryのpending planning mutationがあり、
そのmutationが持つRun（Run keyの予約、recovery planning mutationなら `recovery_binding` が指すRun）に
**canonical generation 1**（HEADにcommitされ、P1 readerで読み戻せるgeneration 1と、そのCandidate snapshot・
task input）があるとき、その呼び出しはcontinuation modeに入る。Runを持たないmutation、commitされていない
generation 1、開始しただけのgeneration mutationは境界の外で、通常の新規entryとして扱う。この判定は予約も
書き込みもせず、caller値を評価せず、Runを作らず・直さず、recovery discoveryも走らせない。検査の順序は変えない。

continuation modeでは、新しいentryの可否を決める可変factが、そのpending mutation自身のrequestを拒否しない。
Roadmapのlifecycle（held / cancelled / achieved）、Phaseのlifecycleとstate（complete / held / cancelled /
plan_excluded）、Phase・Roadmapのsettled-lifecycle検査、Phaseの依存、明示entryの現在の開始可能性、そして
liveの中断展開の規則が既に飛ばす phase_already_expanded と unique entry である。Phaseが属するRoadmapが解決
すること自体は静的factなので拒否は残る。

これらのfactが無視されるわけではない。committedな変化は、流れが到達している境界で分類される。Receiptの前は
currency（stale）、seal後・登録前はuse check（generation 4）、登録開始後Kpの前は pre-Kp currency proof、Kp生成後は
C-2(Kp) のP12（Kpの親P）、pushは committed planning proof のCP7である。publication barrierに止められた他の
operationがworking treeへ適用しただけで未commitの変化は、どのcurrencyもproofも読まない。

continuation modeは検査の免除ではない。引数・platform・Git version、構造precheck、Phaseとそのroadmapの解決、
request identity、canonical-input preflight、same-request検査、marker互換、designの静的な形（通常Workが1つ以上、
予約key、その他の不正design）、そしてresumeしたmutation自身のreplay・binding・proofは、すべてそのまま走る。
境界はpending recordから読むので、このrequestでない呼び出しも可変factは通過するが、直後のsame-request検査が
従来どおり拒否する（別のdesignは `reconcile required`、legacyは `review_marker_mismatch`）。

fresh / generation 1前の呼び出しは従来どおりすべてのlive受理検査を受ける。legacy Phase entryはcontinuation mode
に入らず、liveの中断展開・abandonの規則もそのままである。Roadmap作成にはこの種の可変受理検査が無いので関係しない。
continuation modeはlifecycleの権限を作らない。Reviewは従属gateのままで、`state.py` もlifecycle導出も変わらない。

**writer hand-off**: freeze後の登録は、canonical Candidateから計算したW（CanonicalPlanningWriterInput）だけから書き、callerのplan / designを二度とbytesを作るhelperへ渡さない。mappingのkey順はCandidateの正規順、sequenceの順はCandidateの順である。各登録stageの前に、display番号を割り当てるentity directory（Roadmap作成: `roadmaps/`・`phases/`、Phase entry: `works/`）のentryがHEADのものとこのmutationが書いたものだけであることを確かめ（display base check）、違えば `dirty_overlap` で止める。

**operation binding**: freezeで記録した `review_binding`（branchとHEAD）を、以後のgeneration mutationと登録のすべてのstageの前に確かめ、branchが変わっていれば `reconcile required`（`review_binding_moved`）で止める。

**Git段階**: 登録はKp（`base_exact` の登録commit）、C-2(Kp)、Planning Consumption、Km（Consumptionだけのmetadata commit）、C-2(Km)、push先があれば `review-publication` stageでのKmのpush、の順で進む。commit primitive、`base_exact`、pushのstageとpublication barrierは `rules/git` に従う。

**Git persistence preflight**: freeze（手順5）で、また以後Review recordを書くstageを記録する前と、P2が記録するすべてのGit stageの直前に（attributeとconfigurationは途中で変わり得る）、次の2つをこの順で評価する。

1. transform attribute: そのstageのplanning-owned pathのすべてについて、`git check-attr -z filter ident working-tree-encoding` が3つとも `unspecified`（または `unset`）を報告し、実効configurationが `unset` または `unspecified` という名前のfilter driverを定義していない（`filter.unset.*`・`filter.unspecified.*` のkeyが無い）こと。それ以外は `review_git_transform` で止める。書いたbytesとcommitされるblobを違えさせる変換や、`git add` 中に外部processを走らせる変換（clean / process filter、Git LFS、`$Id$` の展開、再encoding）を拒否するためである。印字された語だけでは状態を示さない（literalの値も同じ語を印字する）ので、driverの名前も見る。
2. checkout capability: そのstageのReview record path（freezeではRunが書き得るすべてのReview pathと、HEADにcommit済みのすべてのReview record）について、`skills/review` のcheckout capability。

`unset` という名前のfilter driverは第1部にもcheckout capabilityの第4層にも当たるが、review-v1の流れでは第1部を先に評価するので、そのrepositoryでのreview-v1 planningは `review_git_transform` で止まる。`review_checkout_unsafe` は、checkout capabilityをそれだけで評価した時に同じrepositoryが受ける拒否であり、流れの中では第1部が通ってcapabilityの条件だけが成り立たない時の拒否である（`unspecified` という名前のdriverは第1部だけに当たり、それ以外の層の失敗はcapabilityだけのものである）。どちらもfail-closedで何も書かず、freezeではplanning mutationをabandonし、それ以後はpendingのまま残す。どちらのcodeを受けるかに依存するものは無い。

**runtime喪失からの回復**: slotにpendingなreview-v1 planning mutationが無い呼び出しは、まずcanonical recovery discovery（`skills/review` の分類）を行う。回復可能なRunがちょうど1つならそのRunを続けるrecovery planning mutationを開始し、Runのcanonical recordからreserved ID（domain ID、Run ID、task ID、generation 3があればReceipt ID）を1回のdurable saveで束縛する（`recovery_binding`）。canonicalにならなかったID（generation 3より前のReceipt ID、Consumption ID）だけを同じkeyで新しく予約する。どのIDも推測で作らず、束縛するIDが別IDで予約済み・種類違い・HEADのcommitted viewかworking treeで使用中なら `review_recovery_reservation_conflict`。回復可能なRunが無く、不完全なRunも無い時だけ新しいRunを開始し、set asideしたRunを `recovery_discovery` noteとrequest envelopeの `set_aside_runs` に記録する。不完全・曖昧なら `review_recovery_incomplete` / `review_recovery_ambiguous` で何も開始しない。runtime喪失だけを理由に新しいRunを開始しない。

**中断したsetup（pre-freeze resume setup）**: effectを記録せずgeneration mutationも開始していないplanning mutationは、再実行でそのmutationのsetupを完成させる。`recovery_discovery` noteの無い新しいRunのmutationはdiscoveryをやり直し（その間にRunが回復可能になっていれば `review_discovery_changed`）、記録済みの予約はそのまま使い、足りない予約を固定順で予約し（順序に無い記録済みkeyは `review_setup_invalid`）、freezeの他の手順をすべてやり直す。bindingの無いrecovery planning mutationはdiscoveryで同じRunを示してから束縛する（予約だけ持つrecordは `review_recovery_reservation_conflict`、Runがもう唯一の回復可能なRunでなければ `review_discovery_changed`）。

**abandon**: 最初のgeneration mutationを開始するまで、review-v1 planning mutationはeffectを持たずcanonicalなものを何も持たないので、開始したものでもresumeしたものでも、Phase entryでも、どのSTOPでもabandonする。generation mutationを開始した後はterminalまでpendingのまま残り、同じrequestの再実行がresumeする。

**STOP codeとreason**: review-v1 planningのSTOPはcode（`StopError` / `ValidationError`）で、`reconcile required` は `code == "reconcile_required"` のまま意味を `reason` に持つ。STOPが残す状態は、lockまたは `_open` より前なら何も開始しないこと、`_open` の後は上のabandonの規則（最初のgeneration mutationより前はabandon、それ以後はpending）である。review-v1 planningのSTOP code:

- lockより前: `review_contract_invalid`、`review_create_unsupported`、`review_git_unsupported`（入口）
- `_open` より前: `review_candidate_unrepresentable`（canonical-input preflight。`_open` の後の表現可能性検査も同じcodeで、detailがどちらの拒否かを示す）
- freeze: `review_base_uncommitted`、`review_entry_not_canonical`、`review_entry_ambiguous`（R9）
- `review_context_unavailable`: configured Workline rootのregistryまたはSkillを解決・読取りできず、Review Contextを計算できない。recovery discovery、freeze、そしてContextを計算し直すすべての点（reviewer launchの前、2つ目以降のgeneration mutationの前、use check、pre-Kp currency proof、C-2(Kp)）で止まる。discoveryでは何も開始せず、freezeではabandonし、それ以後はpendingのまま残す。staleの差ではないので、一時的な読取り失敗がReceiptを無効にすることはない
- `review_git_transform`: Git persistence preflightの第1部（上記）。freezeではabandon、それ以後はpending
- `review_checkout_unsafe`、`review_checkout_unknown`: checkout capability（意味は `skills/review`）。freezeとrecovery setupではabandon、それ以後はpending
- `review_namespace_unreadable`: 既存のReview namespaceの読取り（意味は `skills/review`）。recovery discoveryでは何も開始せず、freezeとrecovery setupではabandon
- `review_reviewer_failed`、`review_report_invalid`、`review_reviewer_mismatch`: reviewer（意味は `skills/review`）。何もsettleせず、pendingのまま
- `review_hooks_path_invalid`: contained planning commit primitive（`rules/git`）が `core.hooksPath` に渡す `.workline/runtime/review/no-hooks` に、空のplain directoryでないentryがある。Git stageの前に止まり、planning mutationはpendingのまま
- `review_publication_barrier`: publication barrier（`rules/git`）。freezeとrecovery setupではabandon、Kmのpushの前なら何もpushしない
- `review_roundtrip_mismatch`（P1のcode）: declared baseが等しい時のworking-tree round trip（上のcurrency）。pendingのまま

liveのcode（`validation_failed`、`postcheck_failed`、`structure_invalid`、`dirty_overlap`、`phase_already_expanded`、`ambiguous_startable_candidates`、`phase_blocked`、`roadmap_held`、`spec_violation`）は意味を変えない。continuation modeでは、そのうち可変の受理factによるものがそのrequestを拒否しない。P1のcode（Review recordの読取り・検証、settlement、persistence、committability、containment）もP1の意味のままで、上の状態の規則で止まる。

liveのcodeが従来どおり投げる `reconcile required`（same-request不一致、scope重なり、`reserve_id` の種類違い、liveのsettled-lifecycle検査（continuation modeでは走らない）、liveのbranch binding、liveのreplay / push分類の不一致）は `reason` を持たない。reasonの一覧は `review_marker_mismatch`、`review_recovery_incomplete`、`review_recovery_ambiguous`、`review_discovery_changed`、`review_recovery_reservation_conflict`、`review_setup_invalid`、`review_binding_moved`、`review_chain_invalid`、`review_task_invalid`、`review_generation_owner_conflict`、`review_candidate_mismatch`、`review_receipt_invalid`、`review_registration_base_moved`、`review_registration_currency_changed`、`review_registration_projection_mismatch`、`review_commit_unowned`、`review_persisted_proof_failed`、`review_metadata_commit_mismatch`、`review_publication_invalid`、`review_publication_contract_invalid`。

## Mutation / Git

RoadmapがRoadmap operation owner。

Roadmap body / Phase / relation / Work構造の変更は同じ上位mutationへ束ねられる。Phase CREATE / CREATEは子登録処理で独立commit / pushしない。

Phase展開後、STARTへ渡す前にRoadmap-owned structural changesをcommitし、remoteありならpushする。

pushする場合の宛先は `rules/git` のpush destinationに従う。各Roadmap operationはmutationを開くより前・networkより前に承認先一致を検査し、承認先なし / 不一致はSTOPする。Roadmap操作で承認先を変更しない。

途中失敗は同じmutationをresume。期待値不一致ならreconcile required。

lifecycle決定とplan exclusionは、開始前からの未commit変更がevent log（plan exclusionではreplanが書くRoadmap relation / Relatedも）と重なる場合、eventを記録する前に `dirty_overlap` でSTOPし、何も書かずmutationをabandonする（`rules/git` のCommit / push）。

Roadmap operation開始時にcleanだったpathへ、開始後に他者・別AIが書いた変更も、そのcommitへは入らない。operationは、event log・relation file・entity file等へ書くたびにその内容をrecordへ記録し、記録済みeffectを書き直す直前とcommitを作る直前に、それが現在もそのままであることを確認する。示せなければ何も書かず、stage・commit・pushもせず、その変更を書き戻しも削除もせず、recordを変えずに `reconcile required` で停止する（`rules/git` のCommit / push）。

commitを記録した後・作る前に中断したoperation（commit自体の失敗を含む）の再実行は、その間に独立なoperationや人のcommitでHEADが進んだことだけでは止まらない。`rules/git` のCommit / pushに従い、記録したbaseがHEADの祖先であり、base以降のどのcommitも記録したpathsを変更しておらず、記録したbranchの上にいることを示せる時だけ、そのHEADの上に記録どおりのcommitを作ってpushする。pathsの一部だけ・別の内容でのcommit、変更して戻した履歴、履歴の書換え、branchの変更、branchを記録していない旧implementationのrecordは、従来どおりreconcile required。HEADが記録時のbaseのままでも、記録したbranchの上にいることを示せなければ（同じcommitを指す別branchのcheckout、branch名の変更、detached HEAD等）、commitを作らずreconcile requiredで停止し、記録したbranchへ戻れば同じ再実行が進む。branchを記録していないrecordは、HEADがbranchの上にいれば再開しない（`rules/git` のCommit / push）。記録と同じcommit messageのcommitが履歴にあっても、それだけではcommitを作ったことにならない。まだ適用済みと記録していないcommitは、記録したpathsにcommitする変更が残っていなければ一致、残っていれば上の条件で判断し、operationの変更を未commitのまま成功扱いにしない（同じ規定）。lifecycle event・Roadmap / Phase / Workの登録・Related maintenanceを記録した後・それを確定するcommitを記録する前に中断した再実行は、それを決定したbranchの上（独立なcommitで進んだだけの場合を含む）でだけ進み、別branch・書き換えた履歴・detached HEAD・Gitが判定できない場合は、何もreplay・commit・pushせずreconcile requiredで停止する。決定したbranchを記録していない旧implementationのrecordは推測せず停止する（`rules/git` のCommit / push）。commitを作った後（pushの前・完了の前）に、そのcommitを履歴に含まないbranch等へ移って再実行し、そのcommitで確定する適用済みのlifecycle event・登録・Relatedをもう一度書くことになる場合は、そのcommitが記録したbranchの上でだけ書き、別branch・detached HEAD・Gitが判定できない場合は、何もreplay・push・記録せずreconcile requiredで停止する。branchを記録していないcommitは従来どおり扱う（同じ規定）。

Roadmap作成・Phase追加・Phase entryの登録は、Phase CREATE / CREATEの登録前の構造検査に従い、構造が不正になる登録をeffectの記録・適用より前に、postcheckと同じ `postcheck_failed` で拒否する（`skills/phase-create`、`skills/create` 参照）。拒否されたrequestはcanonical file・relation・commit・pushを変更せず、今回開いたmutationをabandonするので、同じrequestの再実行も、修正したrequestも、他のoperationも、pending recordやdirty fileに止められない。

- Roadmap作成: Roadmap fileを記録する前に、そのRoadmap fileを加えた投影に対して全Phaseを決定し、Phase CREATEのprecheck・relation payload検査・登録前の構造検査を行う。Phase CREATEが拒否する作成はRoadmap fileも書かない。Phase ID / relation IDはこの時点で予約するので、Roadmap fileを記録する前後に中断したrecordもそれらを持ち、resumeは同じIDを使う。
- Phase entry: 通常Work・integration・human_confirmationを別々のstageで登録するので、最初のstageを記録する前に、未記録の全stageのWork payload（name・成立状態・Related）をCREATEのpayload規則で宣言順に検査する。各stageの構造はCREATE registration coreがそのstageを記録する前に検査する。後続stageのrelationとconfirmation対象はPhase entry自身が登録済みWorkから組み立て、未開始Workの追加はpayload規則が読むPhase stateを変えないので、payloadを通った後続stageが先行stageの適用後に拒否されることはない。
- resume: Roadmap作成・Phase追加・Phase entryは、resumeしたmutationの記録済みeffectをreplayする前に、未適用のeffectを現在stateへ重ねた投影を同じ検査にかける。中断の間に独立なoperation（例: 記録済み・未適用のrelationが前提とするPhaseのcancel）がstateを変えて不正になっていれば、何も適用せず、pending recordを変更しないまま `postcheck_failed` でSTOPする。そのrecordはwrite scopeが重なるoperationを従来どおり止めるので、人による照合が要る。Roadmap fileを記録した後・Phaseを記録する前に中断した作成は、Roadmap fileをreplayし、Phaseを記録する前にこの検査で止まる。

callerが内容を決めるRoadmap operation（Roadmap作成 / Phase追加 / Related maintenance / Phase・Workのplan exclusion）は、最初のID予約より前に、決定内容の正規identityをそのmutationのinvocationへ記録する。operationと対象・labelだけのinvocationは、別内容の再実行を同じrequestと見なして記録済みstageを飛ばし、Projectには最初のrequestが決めた内容が残ったまま成功を返し得る。postcheckはentityが解決でき成立状態section等を持つことを見るが、今回のrequestが決めた本文内容と正本を突き合わせないため、これを検出しない。Phase relationのように決定payloadとの一致を検査する部分はあるが、それは `postcheck_failed` として遅れて止まるだけで、requestの取り違え自体を防がない。

記録内容（いずれもこの記録形式のversionを含む）:

- Roadmap作成: Roadmap name / 背景 / 達成したい状態 / 対象範囲 / 対象外、全Phaseのkey・name・成立状態を宣言順で、Phase間relationを宣言順で
- Phase追加: 追加Phaseのkey・name・成立状態を宣言順で、Phase間relationを宣言順で
- Related maintenance: 追加edge（type / to / condition）と削除relation IDを指定順で
- plan exclusion（Phase / Work）: 対象、replanの新Work（key・name・成立状態・phase_id・roadmap_id・work_kind・confirmation_target・Related（type / to / condition）・derivation detail）を宣言順で、追加relation（type / from / to）を宣言順で、削除relation IDを指定順で

nameはrenderingがそのまま書くのでverbatim、section本文（成立状態・derivation detail等）はrenderingがstripするのでstrip後で比較する。任意sectionとderivation detailは有無と内容を別に記録する。relationのendpointは書かれたとおりに記録し、request内のkeyと、そのkeyに予約されたIDは別requestとする（identityはID予約より前に固定するため）。宣言順はdisplay番号やID予約の対応を決めるため意味を持ち、並べ替えを同一requestとして扱わない。どのbranchで決定・確定したかはrequestに含めない（`rules/git` のCommit / pushに従い、決定したeffectと一緒に記録される）。

同じslot（operation・対象・label）に未完了mutationがある場合、記録済みrequestが今回のrequestと一致する時だけresumeする。一致しない再実行は、mutationを開くより前・記録済みeffectをreplayするより前・no-op判定より前に `reconcile_required` とし、pending record・effects・reserved IDs・statusをそのまま保持する。rollback・abandon・削除・新しいmutationの開始は行わない。

requestを記録していない旧実装のpending recordは自動resumeしない。どの中断位置でも `reconcile_required` とし、同じく何も変更しない。診断にはmutation id、対象operation、requestを記録する前に書かれたrecordであることを含める。

`invocation_key` はcallerのlabelであって識別子ではない。label文字列の一致だけでresumeを決めない。

Roadmap / Phaseのhold / resume / cancelとachievement記録も、途中失敗は同じoperation・同じ対象の再実行で同じmutationをresumeする。これらが決める内容は対象とevent種別だけで、どちらもinvocation（operationと対象）で決まるため、requestを別に記録しない。

自分の未完了mutationが既に適用したlifecycle eventは、そのrequestが出会う現在stateではなくrecovery stateである。前提条件（holdなら対象がactive、resumeならheld 等）をそのeventを含むstateだけで判定すると、eventを適用した後に中断したholdの再実行が「既にheld」として自分自身を拒否し、commit / push / mutation完了へ進む経路が無くなる。前提条件はまず従来どおり現在stateで判定し、拒否された時だけ、次をすべて示せるeventを除いたstateで判定し直す。

- 未完了mutationが同じoperation・同じ対象のものである（Mutation Controllerがresumeするinvocationと一致する）
- そのmutationが記録したeventが、このoperationが記録するevent（種別と対象）そのものである
- event logがそのeventを記録どおりに保持している（適用済み・期待値一致）

これを示せなければ、次の例外を除き判定も結果も従来と同じである。eventをまだ記録していない、記録したeventがevent logに無い、または記録したeventがこのoperationのeventでない未完了mutationは、自分のeventを証明しない。読めないrecovery recordも何も証明せず、従来どおりmutationを開く時に報告される。stateだけを見て完了済みと扱わない: 未完了mutationの無いheld Phaseや、別のmutationが書いたeventによるstateは、従来どおり前提条件で拒否する。別operation・別対象のrequestはこのmutationを継続せず、従来どおりwrite scopeで独立性を判定する。例外として、前提条件が拒否された時に、同じoperation・対象の未完了mutationが複数ある場合と、event logが同じIDで記録と異なる内容を保持している場合は `reconcile_required` とし、pending recordを変更しない。

plan exclusion（Phase / Work）は `plan_excluded` eventを記録・適用してから、replan（新Workの登録と追加relation、relationの削除）を記録・適用し、commit / pushする。自分の未完了mutationが既に適用したevent・新Work・追加relation・削除も、同じrequestが出会う現在stateではなくrecovery stateである。それを含む現在stateで構造precheck・前提条件（unstarted）・replanを判定すると、eventを適用した後に中断した再実行が自分自身を拒否し（削除前の構造、既にplan_excluded、削除済みrelationの解決不能、記録済みintegrationの二重計上）、mutationを完了する経路が無くなる。そこでplan exclusionは、同じslot（operationと対象）の未完了mutationについて、mutationを開く前・何もreplayする前に、記録済みrequestが今回のrequestと一致することを確かめ（上記。requestを記録していない旧実装のrecord、別request、複数recordは `reconcile_required`）、stageを記録済みなら次をすべて示せる時だけ同じmutationを最後まで進める。

- 予約IDが、このrequestが予約するkeyだけに、そのkeyの種類の互いに異なるIDとして記録されている
- 記録済みstageが、このrequestが記録する順（`event` → 新Workの登録 または 新Workの無い追加relation → 削除 → `finalize`）の先頭部分であり、各stageがこのrequestと予約IDから決まる内容そのものである: 予約IDの対象の `plan_excluded` 1件、登録coreが作るWork file・derivation detail・追加relation・Related、追加relation、指定順の削除、記録済みeffectのpathsとこのoperationのmessageによるcommit
- 適用済みのeffectが記録順の先頭部分で、未適用のeffectは最後に記録したstageにだけあり、commitを記録した後には無い

示せた場合、構造precheck・前提条件・commit messageの照合・replanの投影は、そのmutationが適用したeffectを除いたstate（適用済みのeventと追加relationを除き、書いたentity fileを除き、削除したrelationは記録したsnapshotから戻す）で判定する。記録済みの削除はそのstageから、記録済みの新Work登録はそのstageと予約IDから読み戻し、現在stateから解決し直したり登録し直したりしない。記録済み・未適用のeffectと未記録のstageは、replayする前に、登録coreが記録前に行う検査、effectの記録時の検査、残りをすべて適用した後の構造、commitが未記録なら開始前からの変更との分離で検査し、拒否される場合は、記録・適用した場合と同じ拒否（`spec_violation` / `validation_failed` / `dirty_overlap` 等）で、何もreplay・記録・commit・pushせずpending recordを変更しないままSTOPする。示せないrecord（書き換えたstage・予約ID・進行）はどの中断位置でも `reconcile_required` とし、何も変更しない。stageを記録していないrecordは何も適用していないので、予約IDがこのrequestのものだと示せれば、従来どおり現在stateで判定する。どのbranchの上でreplay・記録・commitしてよいか、記録済みのcommitが作られたかどうかはこの判定に含めず、`rules/git` のCommit / pushに従う（決定を記録したbranchの上でだけ進み、commitはそのbranchを引き継ぎ、独立なcommitで伸びただけのbranchでは記録どおりのcommitを作り、同じmessageのcommitだけでは作成済みとしない）。requestを記録していても、決定のbranchやcommitのbranchを持たないrecordは推測で進めない。完了したplan exclusionの同じrequestは従来どおり前提条件で拒否する。

各Roadmap operationが宣言する予定write scopeは、そのoperationが最後まで進んだ場合に書き得るcanonical fileの集合とする。今回の呼び出しで実際に書いたfileではない: どの経路を通るか決まる前に宣言するので、条件付きでしか書かないfileも含める。共有ledger（`relations/roadmap.yaml` / `relations/related.yaml` / `events/events.jsonl`）はfile単位で書き直すため、同じledgerを書き得る2 operationは独立ではなく、両方がそれを宣言する。

- Roadmap作成 / Phase追加: `relations/roadmap.yaml`
- Phase entry: `relations/roadmap.yaml` と `relations/related.yaml`（lifecycle eventではないのでevent logは書かない）
- Roadmap / Phaseのhold / resume / cancel、achievement記録: `events/events.jsonl`
- plan exclusion（Phase / Work）: replanがWork登録とrelation変更を行い得るため3つとも
- 既存未開始WorkのRelated maintenance: `relations/related.yaml`

この静的集合には1つだけ例外がある。review-v1 planning mutation（Roadmap作成 / Phase entry）は、上記に加えて、自分のConsumption path `.workline/review/consumptions/<consumption_id>.yaml` を宣言する。このpathは予約したConsumption IDで決まるため、そのIDを予約した時にfile scopeへ加える（Review-v1 planning）。planning mutationが開始するgeneration mutationは、`skills/review` が各transitionに与える初期scopeを宣言する。

宣言が実際より広いと、同じfileを一切書かないoperation同士が「安全に独立していると証明できない」として `reconcile_required` になる。狭すぎると競合を見逃す。どちらも避けるため、scopeはoperation種別から予測できる静的な集合とし、caller inputやcurrent stateで動的に変えない。scopeを決めていないoperationは全ledgerを宣言する（過大宣言の側へ倒す）。entity scopeは従来どおり、そのoperationが変更する対象と、operation中に発行したIDを含める。

既に書かれたpending recordのwrite scopeは後から書き換えない。広いscopeを記録した旧実装のrecordは、そのscopeのまま従来どおり停止させる。

write scopeは同じfileを書くかどうかを表すもので、他のmutationが決めたlifecycle factを実行可否の判断に読むかどうかは表さない。lifecycle factはevent logから導かれるため、他のmutationがeventを記録してから適用するまでの間、current stateにはその決定が現れない。Phase entryは対象Roadmapと対象Phaseのlifecycleを、既存未開始WorkのRelated maintenanceは対象Roadmapと対象Workのlifecycleを実行可否の判断に読むが、どちらもevent logを書かないので、この依存はwrite scopeの重なりでは検出されない。そこでこの2 operationは、読むentityのいずれかについて、未完了mutationが記録済みで未適用のlifecycle eventを持つ場合に `reconcile_required` で停止し、mutationを開かず何も書かない。停止理由には、そのmutation、owner、entity、event種別を含める。未適用かどうかは、そのeventがevent logに存在するかで判定する。

この確認は読む側だけで行う。write scopeへRoadmap entityやevent logを加えると重なりが対称になり、途中まで展開したPhaseがRoadmapのhold / resumeを止めるなど、独立なoperationを不要に停止させるため、そうしない。適用済みのlifecycle eventはcurrent stateに現れるので、通常のprecondition（cancelled / held等）がそのまま報告し、この確認は停止理由を上書きしない。別Roadmapの未完了lifecycle決定や、そのoperationが読まないentity（同じRoadmapの別Phase等）の未完了lifecycle決定では停止しない。Phase entryが依存関係として読む先行Phaseの未完了lifecycle決定も対象にしない: relationを再計画せずに先行Phaseをcancelしようとすると、cancel自身がeventを適用する前の構造投影で停止するので（Lifecycle参照）、Phase entryを止めなくても不整合は作られない。

held Roadmapへの正式なfuture-plan変更が決定済みかどうかは、request一致検査の後・mutationを開くより前に検査する。この判定はeffectに到達せず登録内容を変えないためrequest identityへ含めない。request一致検査より後に置くのは、継続できないpending recordの存在をlifecycle factで隠さないため。mutationを開くより前に置くのは、拒否された再実行が既存のpending mutationをabandonしないため。

Roadmap operationは `rules/git` のProject contextに従い、対象Projectのcontextから実行する。invocation Project contextが対象Projectと一致しなければ、lockを取得する前に `foreign_project_mutation` でSTOPし、何も書かない。

Roadmap operationにはCLIが無い。`rules/git` のWorkline implementationに従い、対象Projectの中でisolated Python processを開始し、同じprocessで `<R>/run-workline.py` の `activate()` を実行してから、RoadmapのPython APIをimportする（R = configured Workline root）。Project contextの照合の後、実行中のimplementationがconfigured rootのものでなければ、lockを取得する前にSTOPし、何も書かない。PYTHONPATHの手組みや別のimplementationへfallbackしない。

Roadmap operationは `rules/git` のProject execution lockを取得してから、Roadmap / Phase / Work state・dependency・pending mutation・push destinationを読む。lock取得前に読んだWorkline structural stateをwrite判断へ使い回さない。Phase CREATE / CREATEは同じlockとmutationへ参加し、lockを取り直さない。STARTへのhandoffはRoadmap operationが戻ってlockを解放した後に行う。他processが同じProjectで実行中なら待たずに `project_operation_busy` でSTOPし、何も書かない。
