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

途中失敗後は同じmutation ID / Work ID / relation IDをresumeする。新IDで重複CREATEしない。

中央正本の物理writeはMutation Controller経由。

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
