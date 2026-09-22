---
name: review
description: Judge whether an already-decided Workline artifact is authorized to be persisted, as a subordinate gate inside an existing operation. Use ONLY inside an established Workline Project (one that already has .workline/project.yaml), and only when Roadmap, Phase CREATE or START is already running and asks whether its Candidate may proceed. REVIEW owns Candidate identity, Evidence, reviewer tasks, adjudication and the Authorization Receipt; it never progresses a Roadmap, Phase or Work, never finalizes Git, and never opens a Project mutation of its own. Not for code review requests, PR review, document review, or any generic "review this" task.
---

# REVIEW

決定済みの成果物が「そのまま永続化してよいか」を判定する、operationの内側のsubordinate gate。

Reviewは許可を出すだけで、何も進めない。

## Authority boundary

Reviewが所有する:

- Candidate identity（何をreviewしたか）
- Review Context / Effective Policy identity
- Evidence と dependency completeness
- reviewer taskのaccept / settle
- adjudication と obligation
- Authorization Receipt の発行
- supersession

Reviewが所有しない:

- Roadmap progression
- Phase progression
- Work lifecycle completion
- Git finalization（commit / push）
- top-level Project mutation

```text
Review
=
subordinate authorization / quality gate

Review
!=
second lifecycle / progression controller
```

lifecycleの正本は従来どおり canonical entities / relations / lifecycle events から導出される。Review recordはWork / Phase / Roadmapのstate導出に一切入らない（`rules/ai-decision`、`ProjectView`）。

## Invocation

Reviewは単独のtop-level operationとして起動しない。既に走っているoperation ownerが、自分のmutationの中からgateとして呼ぶ。

```text
Roadmap planning Review  -> Roadmap mutation owner
Phase entry Review       -> Roadmap mutation owner
Work Formal Review       -> START mutation owner
Policy Review            -> 対応するPolicy operation owner
```

Reviewは自分でProject lockを取らず、自分でmutationを開かず、自分でcommitしない。canonical Review recordを書くのは、そのgateを使っているoperation ownerのmutationである。

## 適用範囲

P1で成立しているのは、Review Coreの永続化・回復・識別の土台と、この責務境界である。

P2で、Roadmap作成（Roadmap planning Review）とPhase entry（Phase entry Review）が、呼び出しごとの明示opt-in（`review=PlanningReview(...)`、`skills/roadmap` のReview-v1 planning）でだけこのgateを通る。opt-inしない呼び出しは従来どおりで、Reviewは何も読まず書かない。planning operationの流れ・entry順・recoveryの指揮・write scopeは `skills/roadmap` が所有し、このSkillはrecordとpolicyと証明の意味を所有する。

ReviewはWork completionに自動適用されない。STARTの通常のWork completion semanticsはreview-v1へ切り替わっておらず、`work_completed` はこれまでどおり判定される。activation recordは作らず、Work terminalのConsumptionも作らない。

```text
Work terminal Review gating: NOT ACTIVATED
```

Work terminal gatingとresult commitのproof / push分割はP3が扱う。

## 正本の置き場所

canonical Review recordは `.workline/review/` に置く。最初のReview writeで遅延生成し、一度もReviewを使っていないProjectは現在と同じ形のままでよい。

```text
.workline/review/
├─ gates/<review_run_id>/<generation:06d>.yaml
├─ receipts/<receipt_id>.yaml
├─ consumptions/<consumption_id>.yaml
├─ supersessions/<superseded_receipt_id>.yaml
├─ candidate-snapshots/<candidate_hash>.yaml
├─ task-inputs/<review_task_id>.yaml
└─ activation/work-terminal-v1.yaml
```

`.workline/runtime/review/` はephemeralな実行material専用で、canonical Review truthではなく、evidenceでもなく、acceptedタスクを再構成できる唯一のmaterialでもない。cloneやruntime cleanupで消えてよい。消えて困るものはcanonical側に置く。

canonical Review recordはすべてimmutable create-onlyで書く。既存recordを書き換えず、後の状態は新しいgenerationやsupersessionで表す。

```text
target無し         -> そのbytesで作成
同一bytes          -> 適用済み（replay安全）
異なる内容 / 種別  -> reconcile required
```

## Gate generation

1つのReview Runは、1から始まり1ずつ増える連続したgenerationを持つ。各generationは直前のgenerationとそのcanonical digestを名指す。latestは連鎖全体を検証してから決まるもので、いちばん大きい番号のfileではない。

欠番、重複、predecessor不一致、digest不一致、未知のversion、読めないfileはfail closed。

同じReview Runのgenerationを計算する前に、そのRunのpending generation mutationを必ず先に確認する。

```text
ちょうど1件 -> 先にresume / reconcileする
複数 / 矛盾 -> reconcile required
0件         -> 連鎖を検証してN+1を計算する
```

Project execution lockはlive processしか直列化せず、crashで解放される。physical generation fileが作られた後・appliedを保存する前に落ちた場合、次の起動が連鎖を読むとN+1が見えてしまい、放っておけばN+2へ進んでRunが分岐する。そのためgeneration mutationは初期WriteScopeに必ず次の2つを入れる。

```text
.workline/review/gates/<review_run_id>/<generation:06d>.yaml
.workline/review/gates/<review_run_id>/.generation-serialization
```

2つ目はscope専用のconflict tokenで、file自体を作らず、commitせず、Review truthにもしない。未完のN+1と後続の試行が機械的に重なるためだけに存在する。

## Candidate / task provenance

外部reviewerへ投げる前に、clone-safeな再構成materialをcanonicalへ残す。digestだけを保存して再構成materialの代わりにしない。

accepted task descriptorは、成果物と要求のidentityに加えて、それらを「どう再構成するか」も縛る。

```text
candidate_hash
candidate_material_digest
request_digest
task_input_digest
```

同じ `candidate_hash` に到達する別のsnapshot bytesは、別のprovenanceである。結果が同じでも再構成が違えばReview validityは変わる。

runtimeのprovider job handleはauthorityにしない。clone後やruntime喪失後は、canonical materialから同じ要求とCandidateを厳密に再構成できたときだけ同じ `task_id` を再実行・再取得してよい。再構成できない、digestが合わない、adapter versionが無い場合はfail closedで、代わりのtask IDを黙って発番しない。

## accepted と settled

acceptedは「canonical task identityと要求とprovenanceがgate generationに記録された」。settledは「terminal result / status / digestがgate generationへ反映された」。この2つは別の事実で、1つのfieldにまとめない。

外部callbackがProject stateを直接書かない。結果はProject lockを持つoperationへ戻り、canonical task inputと照合してから、次のgenerationとしてsettlementを書く。

未知のcallback、矛盾する重複、canonical task materialの欠落、digest不一致はfail closed。

## seal と Authorization Receipt

`sealed_authorized` のgenerationだけがconsumable Receiptを発行できる。acceptedなtaskにunsettledが残っている間はsealしない。

sealが最初にReceiptを発行する場合、generationのimmutable createとReceiptのimmutable createを同じmutation stageに記録する。途中で落ちたら残りのeffectだけをresumeする。ReviewStoreで読み直して両方validと示せるまで、consumerはそのReceiptを使わない。

Receiptは「このCandidateを許可した」としか言わない。

```text
Receipt existence != operation completion
Authorization     != Consumption
```

Receiptは自分を格納するcommitのSHAを持たない。

## Consumption

1つのReceiptはたかだか1回しか消費されない。Work kindではterminal eventも同じで、1つの `terminal_event_id` にたかだか1つのConsumptionが対応する。

完全に同じtupleのreplayはidempotent。矛盾するtupleはreconcile。

P1では、`work_completed` に対してConsumptionが必ず1つ存在するというtotalityを現行STARTへ適用しない。それはP3 activationの責務である。

## 三つのprojection

```text
ReviewedArtifactProjection      Reviewが正しさを許可する対象
AuthorizedTransitionProjection  その許可のもとでownerが適用するcanonical transition
OperationMetadataProjection     Receipt / Consumption / supersession等のReview bookkeeping
```

```text
OperationMetadataProjection を
state.py / progression / correctness の
normative sourceにしてはならない。
```

あるfileが実際にruntime behaviorを決めるなら、それはmetadataではない。Context / Policy / canonical transition stateとして適切なauthorityの下で表す。

## 永続結果の証明

「同じbytesだった」では足りない。defaultや省略やloaderの解釈で、見た目が同じまま意味が変わり得る。reviewされた意味が、canonical loaderで読み直した意味と一致することまで示す。

```text
reviewed semantics
-> 期待されるcanonical projection
-> 永続化
-> canonical loaderで読み直す
-> 正規化した永続semantics
== reviewed semantics
```

書いた後にdisplayや名前の類似でidentityを引き当てない。identityはowning mutationが予約したものを使う。

## Evidence completeness

Evidence adapterは、自分のcheckが実際に依存するclassと、その各classをどう説明するかを宣言する。

```text
required classes ⊆ observed ∪ pinned ∪ denied ∪ not_required
```

これを満たさないものは `unknown`。

```text
unknown != proof
```

unknownはその場限りの使用に留まり、別Candidateへ再利用しない。「変化が見つからなかった」ことは不変の証明にならない。

## HEAD advancement

Git-write compatibilityとReview-validity compatibilityは別物である。記録したpathsが触られていないことは、Context / Evidence / Policy / toolchain / provenanceが変わっていないことを何も示さない。

```text
Git-write compatibility != Review-validity compatibility
```

どれか1つでもcompletenessを示せなければreuseせず、新しいCandidateを立てる。

## 停止規則

次はいずれもfail closedで、推測で先へ進まない。

```text
未知 / 読めないschema version
連鎖の欠番・矛盾
duplicate logical ID
immutable factの衝突
malformedなprovenance
canonical materialの欠落
digest不一致
未知のcallback
未settledのままのseal要求
ignore対象のReview path
containmentを示せないwrite先
```

`.gitignore` 等を書き換えてReview pathをcommit可能にしない。

## 回復

automatic reset / rebase / amend / force push / clean recoveryは行わない。別主体が作ったcommitを、このoperationが作ったcommitとして推測で採用しない。

Reviewが関わる回復も従来どおりreconcile requiredで止まり、人が判断する。

## Planning kinds and identities（P2）

```text
review kind               RoadmapPlan: roadmap-plan-v1            PhaseEntryDesign: phase-entry-design-v1
task slot / task kind     roadmap-plan-reviewer / planning-review-v1   phase-entry-design-reviewer / planning-review-v1
adapter                   roadmap-plan-adapter-v1                  phase-entry-design-adapter-v1
target identity           予約したRoadmap ID                        phase_id
operation identity        <operation>:<request_digest>（requestの正規identityのdigest）
```

契約の識別子: planning `review-v1-planning-v1`、publication `review-v1-planning-publication-v1`、commit primitive `review-v1-planning-local-v1`、proof `review-v1-planning-proof-v1`、committed planning proof `review-v1-planning-committed-proof-v1`、checkout capability `review-v1-planning-checkout-v1`、persisted result `review-v1-planning-persisted-result-v1`、policy `review-v1-planning-policy-v1`。

Candidateは `review-planning-candidate` recordで、review kind、Candidateの内容（予約したIDを含む）、declared base（名指した既存Phase / Workのlifecycleと状態、Phase・Roadmapのlifecycleと状態、Phase依存の状態）からなる。callerが渡したmapping（Relatedのcondition等）は、P1 serializerのkey順（各階層でcode point昇順）で、すべてのentryを保ったままCandidateに入る。sequenceはcallerの順を保つ。Candidateが正確に保てない値（float、tuple、textでないkey、空key、sequence内のsequence、lone surrogate、readerが失う値）は `review_candidate_unrepresentable` で拒否し、何かを補って受け入れない。

## Planning Review Policy

planningのEffective Policyは次の静的recordそのものである（Workline実装の定数と一致しなければならない）。

```yaml
adjudication_rule: review-v1-planning-adjudication-v1
blocking_severities:
  - HIGH
  - MID
declined_disposition: "the task settles failed; the planning attempt is not authorized"
error_disposition: "no settlement; the same task is launched again by the next run"
instruction: review-v1-planning-instruction-v1
low_disposition: "recorded in the report digest, returned to the caller, non-blocking"
obligation_rule: "every HIGH or MID finding and every failed task is an unresolved obligation; P2 resolves none"
policy_id: review-v1-planning-policy-v1
repair: "none; a not-authorized planning attempt is terminal"
report_statuses:
  - completed
  - declined
reviewer_identity_rule: "caller-declared identity and version, bound at acceptance; a settlement is accepted only from them"
schema: review-planning-policy
seal_rule: every required task settled completed and zero unresolved obligations
severities:
  - HIGH
  - MID
  - LOW
slots:
  - required: true
    review_kind: roadmap-plan-v1
    task_kind: planning-review-v1
    task_slot: roadmap-plan-reviewer
  - required: true
    review_kind: phase-entry-design-v1
    task_kind: planning-review-v1
    task_slot: phase-entry-design-reviewer
timeout_disposition: "none imposed by Workline; a reviewer that gives up returns declined"
version: 1
```

## Reviewer interface（P2）

callerは `PlanningReview(reviewer, reviewer_identity, reviewer_version)` を渡す。reviewerは同期callbackで、`PlanningReviewTask`（task ID、slot、kind、review kind、request envelope、digest群）を受け取り、`PlanningReviewReport`（task ID、reviewer identity / version、status `completed` / `declined`、finding（severity `HIGH` / `MID` / `LOW`、code、message））を返す。taskは常にcanonicalなTaskInputから組み立て、memoryの値から作らない。runtime喪失後も同じ `task_id` を、accepted時のreviewer identity / versionにだけ再launchする（違えば `review_reviewer_mismatch`）。

reviewerが例外を投げる・不正なreportを返す・別identityのreportを返す場合は何もsettleせず（`review_reviewer_failed` / `review_report_invalid` / `review_reviewer_mismatch`）、planning mutationはpendingのまま、次の実行が同じtaskを再launchする。runtimeに書くreportの写しはsettlement materialではない。

## Adjudication（P2）

sealするのは、必須taskがすべて `completed` でsettleし、未解決obligationが0の時だけである。HIGHとMIDのfinding、`failed` でsettleしたtask（`declined` を含む）は未解決obligationであり、P2はどれも解決しない。そのRunは `not_authorized` でterminalになり、何も登録しない。LOWのfindingはreportのdigestに記録してcallerへ返し、sealを止めない。

## Planning transition state machine（P2）

planningのgate chainは次の4つのtransitionだけを持ち、各transitionは1つのgeneration mutation（owner: review-v1 planning operation、`planning_mutation_id` でplanning mutationに結び付く）で書き、commitし、永続を証明してから完了する。

```text
1 accept      Candidate snapshot + task input + gate 1（open、acceptedなtask）
2 settle      gate 2（open、settleしたtask、adjudication）
3 seal        gate 3（sealed_authorized）+ Authorization Receipt
4 invalidate  gate 4（open）+ Supersession（sealの後・登録開始前のstale）
```

各generation mutationの初期write scopeは、そのtransitionが作るfileと、Runの `.generation-serialization` tokenちょうどであり、後から広げない。generation 5は無く、登録stageを記録した後にgeneration 4は開始しない。

## Planning Consumption v2（P2）

planningのConsumptionはversion 2の `PlanningConsumption` で、Receipt、Run、generation 3、review kind、`authorized_candidate_hash`、`operation_identity`、planning mutationのID、target identityと、`persisted_result` を持つ。`persisted_result` はcontract、request digest、登録commit（Kp）とその親、branch（完全なref）、登録deltaのdigest、semantic projectionのdigest、adapter / loader identity、kindごとの予約ID（RoadmapPlan: roadmap / Phase / relation、PhaseEntryDesign: Phase / Roadmap / 通常Work / integration / confirmation / roadmap relation / Related / canonical first Work）を持つ。version 1のConsumptionがplanning kindを名指せば不正である。1つのReceiptのConsumption、1つの登録commitのPlanning Consumption、1つの（review kind, target）のPlanning Consumptionは、それぞれたかだか1つ（`review_consumption_conflict`）。

登録deltaのdigestは `review-planning-delta` recordのdigestで、recordの各scalarは型が固定されている: modeはtext（`"000000"` / `"100644"`）、object IDは全長の小文字16進text（SHA-256 repositoryでは64文字、zero IDは64個の `0`）。整数のmodeを持つrecordは別のdigestになる。

## 何を証明し、何を証明として扱わないか（P2）

- **expected physical projection**: Candidateの登録を、canonical Candidate snapshotから計算したW、Runのadapter、登録commitの親Pの正本だけから、writerのbuilderとplanned-write計算で作ったbytes（ledger全体を含む）。
- **C-2(Kp)**（`review-v1-planning-proof-v1`）: Kpがこのplanning mutation自身のcommitであり、branch・親・系譜が記録どおりで、`git diff-tree` のdeltaがexpected physical projectionそのもの（path・transition・mode・byte）で、記録した登録effectもそれと一致し、committed-result loaderで読み直した意味がreviewしたCandidateと一致し、Pの上でcurrency（declared baseを先に）が保たれていること。
- **C-2(Km)**: Kmがこのmutation自身のcommitで、Consumptionだけを加え、その親がKpまたはplanning-owned pathに触れないKpの子孫であり、committed planning proofが通ること。
- **committed planning proof**（`review-v1-planning-committed-proof-v1`）: 公開しようとするcommitの履歴に登録されたRunごとに、committed objectだけから（runtime record、note、remote、working treeを読まず、attributeを評価しない）、登録commit・Runのrecord・expected physical projection（CP5）・意味（CP6、declared baseのCP7を先に）・Consumption・metadata commitを証明する。attributeを評価しないのでcheckout capabilityを要しない。
- 証明として扱わないもの: Consumptionやmetadata commitやnoteの存在、commit message、branchの位置、承認先（remote）の状態、Supersession、planning mutationの完了。同じ意味を別のbytesで持つ登録commitは、誰が作ったものでも証明されない。
- `P2_PUBLICATION_GIT_MIN` より古いGitで拒否された公開は、登録が存在することを主張しない。push stageの形、publication barrierが評価される場所、2つのGit最小versionは `rules/git`（Commit / push、Push destination、Git versions）が所有し、このSkillはそれに従う。

## Recovery classification（P2）

canonical recovery discoveryは、同じreview kindと `operation_identity` を持つRunを、HEADの履歴とworking treeから集め、各Runをclean persistence（HEADの履歴が加えたrecordがHEADの木に同じblobであること、working treeのrecordがcommit済みであること、各stageが揃っていること、chainがP1の形であること、Runのserialization tokenを持つpending mutationが無いこと）で確かめてから、次の順に分類する: generation 4 → terminal `invalidated`、登録commitかConsumptionがある → committed planning proofが通れば terminal `consumed`・通らなければ `review_recovery_incomplete`、generation 2が許可しない → terminal `not_authorized`、他のRunの `set_aside_runs` に名指されている → `set_aside`、再構成できない → `review_recovery_incomplete`、generation 1か許可するgeneration 2 → currencyがcurrentなら回復可能・staleなら廃止（理由はstale reason）、generation 3 → 回復可能。回復可能なRunが複数なら `review_recovery_ambiguous`。新しいRunのrequest envelopeの `set_aside_runs` は、set asideした各Runとその理由（`invalidated`、`consumed`、`not_authorized`、`set_aside`、stale reason）を記録し、以後それらは回復しない。

## Checkout capability（P2）

Review recordはcanonical bytesでしか読まないので、P2はGitのcheckoutがReview pathのLF bytesをこのrepositoryとそのcommitのすべてのfresh cloneで再現することを、書く前に積極的に示した時だけReview recordを書く。P2 v1が支える構成は1つだけである: HEADのroot `.gitattributes` の最後のattribute ruleが次の行そのもので、HEADが `.workline/` の下に `.gitattributes` を持たないこと。

```text
.workline/review/** !text eol=lf -filter -ident -working-tree-encoding
```

証明の4層（すべて必要）: 1. HEADのcommitted objectから読むroot `.gitattributes` の生bytes（NULを含まず、最後のattribute ruleがこの行）、2. `.workline/` の下に名前がfoldして `.gitattributes` になるentryが無いこと、3. HEADのcommitted `.gitattributes` だけの評価がform Lを印字すること、4. このrepositoryの実効評価（`info/attributes`、attribute sourceの付け替え、global / systemを含む）がform Lを印字し、`unset` という名前のfilter driverが構成されていないこと。

```text
form L   text: unspecified   eol: lf   filter: unset   ident: unset   working-tree-encoding: unset
```

form Lの印字だけでは何も証明しない（literalの `filter=unset` も同じ語を印字する）。どれかの層が成り立たなければ `review_checkout_unsafe`、判定できなければ `review_checkout_unknown`。支えない構成は安全でないと示されたものではなく、P2 v1が証明しないものである。Worklineは `.gitattributes` も `info/attributes` も書かない。

Review recordを書く前提として、既存のReview namespaceのすべてのrecordがP1の厳格なreaderで読めること（`review_namespace_unreadable`）も要る。CRLFのrecordを正規化して読み直すことはしない。
