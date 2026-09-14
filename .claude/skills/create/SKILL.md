---
name: create
description: Register a Workline Work whose meaning has already been decided. Use ONLY inside an established Workline Project (one that already has .workline/project.yaml), when Roadmap or START has fixed what Work must exist, or when a human/AI directly requests creation of a standalone Workline Work. CREATE assigns stable identity, writes the Work body, registers already-decided relations and Related data, and for direct standalone invocation wraps registration in its own Direct Work Operation context through Git finalization. Not for creating files, directories, components, branches, or any generic project artifact.
---

# CREATE

「何のWorkを作るか」が決定された後、そのWorkをWorklineへ正式登録する。

## Invocation

- Roadmapから呼ばれる
- STARTから呼ばれる
- human / AIからStandalone Work作成として直接起動される

Roadmap / STARTから呼ばれる場合、CREATE registration coreはcallerのoperationへ参加しGit finalizerにならない。

parent operationなしの直接起動の場合だけ、CREATE entrypointがDirect Work Operation contextを生成し、その外側contextがGit finalizationまで所有する。Direct Work Operationは別SkillではなくCREATE direct invocationのoperation contextである。

## Responsibility

registration coreの担当:

- input validation
- stable Work ID / display発行
- Work body登録
- origin登録
- `phase_id` 登録
- callerが決定済みのRoadmap relation登録
- Related登録
- 必要なderivation detail登録
- callerが決定済みのspecial Work kind登録
- postcheck

registration coreが担当しない:

- Workが必要かの判断
- Roadmap / Phase作成
- START
- target
- implementation
- lifecycle event
- completion
- phase_integration_checkの自動生成
- human_confirmationの自動生成

直接Standalone invocationでは、CREATE entrypointのDirect Work Operation contextが人間/AIから与えられたWork意味を確定入力として受け、registration core呼出後にpostcheck / commit / remoteありならpushまで行う。新しいSkill routingは作らない。

pushする場合の宛先は `rules/git` のpush destinationに従う。mutationを開くより前・networkより前に承認先一致を検査し、承認先なし / 不一致はWork登録の前にSTOPする。CREATEで承認先を変更しない。

## Input

通常Work必須:

- name
- `このWorkで成立させる状態`
- origin
- Phase Workなら `phase_id`

必要に応じてcallerが決定して渡す:

- roadmap relations
- Related
- derivation detail
- `work_kind`
- `confirmation_target`
- parent mutation context

Direct standalone invocationでは `origin.type = standalone`。Phase Workのdirect creationをこの経路で推測して作らない。

## Identity / format

stable ID:

```text
w_<ULID-like>
```

表示用:

```text
W-xx
```

Roadmap Work概念:

```yaml
---
id: w_...
display: W-...
type: work
phase_id: p_...
origin:
  type: roadmap
  roadmap_id: r_...
  phase_id: p_...
---
```

Standalone:

```yaml
---
id: w_...
display: W-...
type: work
origin:
  type: standalone
---
```

`phase_id` はcurrent affiliation、originはbirth fact。derivedとは別事実。

## Special Work

special Workも `type: work`。

```text
work_kind: phase_integration_check
work_kind: human_confirmation
```

通常Workには `work_kind` を付けない。

`confirmation_target` は確認対象の意味情報でありdependencyの代用ではない。

Direct standalone invocationではspecial Phase Workを独自作成しない。integration / human_confirmationはRoadmap / STARTが意味owner。

## Integration boundary

CREATEはintegrationを自動生成しない。

```text
初回Phase展開のintegration意味owner
→ Roadmap

実行中の追加Work / 再integration意味owner
→ START

正式登録
→ CREATE registration core
```

`unfinished integration` は `rules/ai-decision` の定義で数え、安定状態で1 Phaseにつき同時最大1件。

callerが通常Workを追加するとき:

- unfinished integrationが1件 → callerが `new work -> requires_completion -> integration` を決定してCREATEへ渡す
- unfinished integrationが0件で再統合必要 → callerが新integrationとdependencyを設計してCREATEへ渡す
- unfinished integrationが2件以上 → 構造異常としてSTOP

CREATEは「通常Workを追加したからintegrationが必要だろう」と推測しない。

## Relations

`.workline/relations/roadmap.yaml`:

```text
planned_next
derived
return_to
requires_completion
```

Work間relationの意味ownerはWork構造を決めたoperation owner。

```text
Phase初回展開 → Roadmap
START内派生 / fix / return → START
Standalone direct creation → CREATE entrypointのDirect Work Operation context
```

registration coreは決定済みrelationを登録するだけ。

`derived` はhistorical fact。その他はfuture plan。

## Related

`.workline/relations/related.yaml`:

```text
must_read
conditional_must_read
obey
realizes
must_update
conditional_must_update
```

conditional relationは機械的・具体的に評価可能なconditionを必要とする。`if relevant` のような曖昧条件を登録しない。

## Derivation detail

`derived` relationだけで理由が不足する場合、`.workline/derivations/der_<ULID>.md` 等へ理由を置ける。

from / to identityはrelation正本に置き、detailへ重複正本化しない。

## Lifecycle

CREATE成功時に `work_started` 等を記録しない。state fieldを保存しない。targetを付けない。新Workはgenerated state上unstarted。

## Mutation / Git

`rules/git` に従う。

```text
Roadmap caller
→ CREATE registration coreはRoadmap mutationへ参加
→ Roadmap owns Git

START caller
→ CREATE registration coreはSTART mutationへ参加
→ START owns Git

Direct standalone invocation
→ CREATE entrypointがProject contextを照合し（foreignならforeign_project_mutationでSTOP）、Workline implementationを照合し（configured rootのimplementationでなければSTOP）、Project execution lockを取得
→ CREATE entrypointがDirect Work Operation mutationを開始
→ registration coreを同mutationで実行
→ entrypoint contextがpostcheck / commit / remoteありなら承認先へpush
```

Direct standalone invocationは `create-work` CLIで起動する。`rules/git` のWorkline implementationに従い、対象Projectの中から `py -3 -I -B "<R>\run-workline.py" create-work . --name <name> --desired-state <state>`（POSIXは `python3 -I -B "<R>/run-workline.py" create-work ...`、R = configured Workline root）を使う。

Roadmap / STARTから呼ばれるregistration coreは、呼び出し元operationがactivateしたprocessの中で、そのoperationが保持するProject execution lockの内側で実行し、lockを取り直さない。

途中失敗後は同じmutation ID / Work ID / relation IDをresumeする。新IDで重複CREATEしない。direct standalone invocationがcommitを記録した後・作る前に中断・失敗し、その間に独立なoperationや人のcommitでHEADが進んだ場合は、`rules/git` のCommit / pushの条件（記録したbaseがHEADの祖先、base以降のどのcommitも記録したpathsを変更していない、記録したbranchの上にいる）を示せる時だけGit段階からresumeし、示せなければreconcile required。HEADが記録時のbaseのままでも、記録したbranchの上にいなければ（別branch、detached HEAD等）commitを作らずreconcile requiredとする（`rules/git` のCommit / push）。記録と同じcommit messageのcommitがあっても、それだけではcommit済みとしない（同じ規定）。direct standalone invocationがWorkの登録を記録した後・commitを記録する前に中断した場合も、再実行は登録を決定したbranchの上でだけ進み、別branch等では何もreplay・記録・commitせずreconcile requiredとする（同じ規定）。

direct standalone invocationは、最初のID予約より前に、決定内容の正規identity（この記録形式のversion、Work name、成立状態、Related（type / to / condition）、derivation detail）をmutationのinvocationへ記録する。nameとlabelだけのinvocationは、別内容の再実行を同じrequestと見なして記録済みstageを飛ばし、Projectには最初のrequestが決めた内容が残ったまま成功を返し得る。postcheckはWorkが解決でき成立状態sectionを持つことを見るが、今回のrequestが決めた本文内容と正本を突き合わせないため、これを検出しない。nameはrenderingがそのまま書くのでverbatim、成立状態とderivation detailはrenderingがstripするのでstrip後で比較し、derivation detailは無しと空を区別する。

記録済みrequestが今回のrequestと一致する時だけresumeする。一致しない再実行は、mutationを開くより前に `reconcile_required` とし、pending record・effects・reserved IDs・statusをそのまま保持する。rollback・abandon・削除・新しいmutationの開始は行わない。requestを記録していない旧実装のpending recordも自動resumeせず、同じく `reconcile_required` とする。

direct standalone invocationの予定write scopeは、`relations/related.yaml` と登録するWork自身とする。relation payloadを渡さずlifecycle eventも記録しないため、`relations/roadmap.yaml` と `events/events.jsonl` はこの経路では書き得ない。registration coreがRoadmap / STARTのmutationへ参加する場合のscopeは、その呼び出し元operationが宣言する。

中央正本の物理writeはMutation Controller経由。

## 登録前の構造検査

registration coreは、Postcheckの構造validationを、登録するeffectを記録する前に、同じ規則で登録後のProjectの投影へ適用する。独自の構造規則は持たない。

投影は、記録しようとするWork file・derivation detail・relation・Relatedを、storeが読み戻すのと同じ規則で現在stateへ重ねたものとする。resumeしたmutationが記録済みで未適用のeffectを持つ場合は、それも適用順に重ねる。Project execution lockにより他のwriterは入らないので、投影はpostcheckが見るstateと一致する。

構造が不正になる登録（cancelled / plan_excludedのWorkを `requires_completion` のpredecessorにする、cycle、同一edgeの重複等）は、effectを記録・適用する前に、postcheckと同じ `postcheck_failed`・同じmessageでSTOPする。canonical file・relation・commit・pushは変更せず、今回開いたmutationはeffectを持たないままabandonされる。構造precheckを持たないdirect standalone invocationでも、構造が既に不正なProjectでは同じ理由で登録前に拒否し、Work fileもpending recordも残さない（既存の不正は修復しない）。記録済み・未適用のeffectをresumeする場合も適用する前に同じ検査を行い、中断の間に不正になっていれば、effectを適用せずpending recordをそのまま残してSTOPする。構造が不正にならない登録は従来どおり記録・適用する。

複数のstageで登録するcaller（RoadmapのPhase entry）は、最初のstageを記録する前に、未記録の全stageのWork payload（name・成立状態・Related）をregistration coreと同じpayload規則で検査する（`skills/roadmap` 参照）。

cancel / plan exclusionのreplanに伴うWork登録は、ownerがreplan全体（terminal event・relation削除・relation追加・新Work）を記録前に投影検査したうえでの適用手順の一部なので、この登録前の構造検査を行わず、登録の適用後にpostcheckで検査する。中断したplan exclusionを同じrequestでresumeする場合、記録済みの登録stageはregistration coreで登録し直さず、そのstageと予約IDから読み戻す。まだ記録していない登録は、ownerが記録済みeffectをreplayする前に、登録が会う状態に対して、registration coreが記録前に行うのと同じ検査（payload・endpoint・integration invariant・human_confirmation・`requires_completion` cycle）を同じ報告で行う（`skills/roadmap` のMutation / Git）。

replanはterminal event → 新Work（追加relationを含む）→ relation削除 → commit / pushの順に適用し、この順序は変えない。登録はrelation削除より前に行われるので、この登録が行う構造検査（記録前の `requires_completion` cycle検査と、適用後のpostcheckの構造validation）は、同じreplanが登録の直後に削除すると決定済みのRoadmap relationを除いた構造で判定する。除外したWork / Phaseを前提とする削除予定のrelationがまだ残っている一時的な状態で、owner projectionが妥当と判定したreplanを拒否しない。除くのは名指しされたrelationだけで、それ以外の構造問題とpayload・endpoint・integration invariant・human_confirmationの規則は従来どおり判定し、削除そのものは登録の後に適用する。登録前の構造検査を行う登録に同じ削除が渡される場合も、同じ構造で判定する。

## Postcheck

- stable ID unique / resolvable
- body desired stateあり
- origin / phase_id整合
- caller payloadとrelations / Related一致
- integration invariant違反なし
- special Work recursionなし
- lifecycle event / targetを勝手に作っていない
- central refs valid

完了済みPhaseへ新Workを追加しない。
