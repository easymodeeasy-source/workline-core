---
name: phase-create
description: Register a Workline Phase whose meaning has already been decided by the Roadmap Skill. Use ONLY inside an established Workline Project (one that already has .workline/project.yaml), and only as the internal Phase-registration path when Roadmap has fixed the Phase name, desired state, Roadmap membership, and any Phase relations to register. Not for generic project phases, milestones, or planning stages.
---

# Phase CREATE

決定済みPhaseをWorklineへ正式登録する内部Skill。

初期callerはRoadmap Skillのみ。人間から通常直接起動しない。

## Responsibility

担当:

- input validation
- stable Phase ID発行
- display発行
- Phase body登録
- `roadmap_id` 登録
- Roadmapが決定済みのPhase relation payload登録
- postcheck

担当しない:

- Phaseの意味判断
- Phase分割・統合
- Phase間relationの意味判断
- Work設計
- phase_integration_check設計
- human_confirmation判断
- START
- completion判断
- Git finalization

## Input

必須:

- Roadmap ID
- Phase name
- `成立させたい状態`

任意:

- Roadmapが既に意味を決定したPhase relation payload
- parent mutation context

Roadmapが意味を決めていない入力を補完しない。

## Phase format

stable ID:

```text
p_<ULID-like>
```

表示用:

```text
P-xx
```

`display` はidentityでもexecution orderでもない。

概念:

```yaml
---
id: p_...
display: P-...
type: phase
roadmap_id: r_...
---
```

```md
# <Phase名>

## 成立させたい状態
...
```

state field、origin field、Work一覧、進捗を保存しない。

`roadmap_id` がcurrent Roadmap membershipの正本。Roadmap側へPhase一覧を重複保存しない。

## Precheck

- Project / project.yaml / common refsが有効
- Roadmap IDが一意解決
- Roadmapがcancelled / achievedではない
- held Roadmapの場合はRoadmapが正式なfuture-plan変更としてPhase追加を決定している
- Phase name / desired stateが決定済み
- relation payloadのtargetが有効
- mixed Phase↔Work relationを含まない

## Relation boundary

Phase間relationの意味ownerはRoadmapのみ。

```text
Roadmap
→ relation意味を決定
→ Phase CREATEへpayload

Phase CREATE
→ validation
→ Mutation Controller経由で登録
```

Phase CREATE自身が `planned_next` / `requires_completion` / `derived` / `return_to` を発見・追加・変更しない。

## Mutation / Git

`rules/git` に従う。

Phase CREATEは独立Git operation ownerではない。Roadmapのparent mutationへ参加し、Mutation Controller経由で書く。RoadmapがProject contextとWorkline implementationの照合を通って保持するProject execution lockの内側で、Roadmapがactivateしたprocessの中で実行し、照合もlockの取得もやり直さない。

途中失敗後は同じmutation context / Phase IDをresumeする。新Phase IDを発行して重複作成しない。

## Directory

write直前に必要なら `.workline/phases/` / `.workline/relations/` を作る。空directoryの存在を前提にしない。`.gitkeep` は不要。

## 登録前の構造検査

Postcheckの構造validationは、登録するeffectを記録する前に、同じ規則で登録後のProjectの投影へ適用する。独自の構造規則は持たない。

投影は、記録しようとするPhase file・relationを、storeが読み戻すのと同じ規則で現在stateへ重ねたものとする。resumeしたmutationが記録済みで未適用のeffectを持つ場合は、それも適用順に重ねる。Project execution lockにより他のwriterは入らないので、投影はpostcheckが見るstateと一致する。

構造が不正になる登録（cancelled / plan_excludedのPhaseを `requires_completion` のpredecessorにする、cancelled / plan_excludedのPhaseを `return_to` 先にする、`requires_completion` のcycle、同一edgeの重複等）は、Phase file・relationを記録・適用する前に、postcheckと同じ `postcheck_failed`・同じmessageでSTOPする。canonical file・relation・commit・pushは変更せず、そのoperationが今回開いたmutationはeffectを持たないままabandonされる。構造が不正にならない登録は従来どおり記録・適用する。

Roadmap作成ではRoadmap fileがPhaseより先に登録されるため、RoadmapはRoadmap fileを記録する前に、そのRoadmap fileを加えた投影に対して、このSkillのprecheck・relation payload検査・登録前の構造検査を行う（`skills/roadmap` 参照）。

## Postcheck

- Phase ID unique / resolvable
- `type: phase`
- valid `roadmap_id`
- display valid
- bodyにdesired stateあり
- state / originなし
- relation payloadが決定内容と一致
- Phase CREATE自身の意味推測によるrelationなし
- Work / lifecycle eventを作っていない

失敗時は`rules/git`のresume / reconcile contractへ従い、推測rollbackしない。
