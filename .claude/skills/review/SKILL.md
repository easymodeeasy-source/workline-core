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

P3で、Workのterminalization（Work Formal Review）が、Projectのactivation（下記のWork-terminal activation）とSTARTの呼び出しごとの明示opt-in（`review=WorkReview(...)`、`skills/start` のReview-v1 Work）の両方がある時だけこのgateを通る。ReviewはWork completionに自動適用されない。activationはreview-v1を選ばず、opt-inしないSTARTは、activateされたProjectでも従来どおりで、Reviewは何も読まず書かない。

```text
Work terminal Review gating: ACTIVATED per Project (one-time, human-confirmed) x per START invocation (explicit opt-in)
```

Workのterminalizationの流れ・executor・lock・mutation・Git finalizationは `skills/start` が所有し、このSkillはCandidate・Context・Evidence・Review recordとproofの意味を所有する。Gitの安全性は `rules/git` が所有する。

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

P1のこの土台に、P3のactivationがtotalityを加える。activateされたProjectで、activationの後のreview-v1 `work_completed` には、そのterminal eventを名指すWork-kind Consumptionがちょうど1つある（下記Work-terminal activation）。legacyの `work_completed` はConsumptionを要しない。

Work-kind Consumption（`terminal_event_id` を持つ）は、どちらの形を消費したかを `artifact_kind` で必ず言う（F1 §11.3）。`result_commit` は `authorized_result_commit_sha` に完全なcommit id（K1）を持ち、`empty` は結果commitを持たない（null）。Work-kindでないConsumptionは4つ（`terminal_event_id`、`terminal_event_type`、`authorized_result_commit_sha`、`artifact_kind`）をすべてnullで持つ。fieldは省略せず、nullとして必ず書く。`artifact_kind` と結果commitのどちらも、もう一方から導かない。

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

Reviewが関わる回復も従来どおりreconcile requiredで止まり、人が判断する。例外は、このoperation自身が作ったexact K1を新しい許可のもとで採用する、下記のWork post-commit recovery（F4）のClass Aだけで、それもhistoryを書き換えず、厳格な適格性を示せない時はreconcile requiredで止まる。

## Human recovery disposition（RB10 N4）

置き換えRunを作らず、自動では再開できないReview Runを、人が明示に自動回復の選択から外す処分は、Reviewではなく `rules/git` のWorkline recovery authority（専用のmaintenance operation `recovery-disposition`、CLI `dispose-recovery`、明示の `--confirm` と対象のstable ID・理由が必須）が所有し、その正本はReview historyではなく `.workline/recovery/dispositions/<rr_...>.yaml` である。新しいSkillもrouting IDも作らない。

意味はRB3-C1のset-asideと同じ1つだけである: 古いRunとそのrecordはevidenceとして残り、自動の回復選択がそれを再び選ばない。dispositionはRunの削除・完了・修理・再解釈ではなく、generation 4もSupersessionも書かず、Review recordを書き換えない。canonical recovery discovery（planningもWorkも）は、他のRunのrequestの `set_aside_runs` に加えて、validなdisposition（canonical、HEADがcommitし、そのRunのexactなrecovery witness `review-run-recovery-v1` に一致する）を同じset-aside関係のもう1つの源として読み、そのRunを安定code `disposed_by_human` でset asideする。新しいRunのrequestはこのcodeだけで名指し、人の自由記述の理由を写さない。witnessと合わない・読めないdisposition、pendingのSTART mutationが持つRunのdispositionは、discoveryを `review_recovery_incomplete` で止める（fail closed）。

処分できるのは、recordが揃って読め、consumedでも既にset asideでもなく、current（未supersede）なsealed Receiptを持たず、Work policyの分類が「どのpending STARTも持たない」ことだけを理由に回復不能とするRun（上記の回復の選択でincompleteになる孤立Run）である。この規則（pendingのSTART mutationが持つRunだけが回復可能）は変わらず、owner不明・形の壊れたRunを処分可能にしない。current Receiptの無効化は従来どおりSupersessionが所有し、dispositionはそれを迂回しない（`recovery_disposition_receipt_current`）。既にsupersede・consumed・set asideのRunには重複した意味を書かない（`recovery_disposition_unnecessary`）。planning Runの分類はそれを再開するplanning requestに対して行うものなので、dispositionの対象にならない。

statusは、validなdispositionのRunを既存の `set_aside` とし、追加の `set_aside_source: human_disposition` で区別する（他のRunのrequestによるものは `successor_request`）。Receipt / Consumptionの状態はそのまま別に見える。

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

各generation mutationの初期write scopeは、そのtransitionが作るfileと、Runの `.generation-serialization` tokenちょうどであり、後から広げない。v1 planning Runにgeneration 5は無く（P4 Runの形は `## P4 Repair Loop` が定める）、登録stageを記録した後にgeneration 4は開始しない。

## Planning Consumption v2（P2）

planningのConsumptionはversion 2の `PlanningConsumption` で、Receipt、Run、generation 3、review kind、`authorized_candidate_hash`、`operation_identity`、planning mutationのID、target identityと、`persisted_result` を持つ。`persisted_result` はcontract、request digest、登録commit（Kp）とその親、branch（完全なref）、登録deltaのdigest、semantic projectionのdigest、adapter / loader identity、kindごとの予約ID（RoadmapPlan: roadmap / Phase / relation、PhaseEntryDesign: Phase / Roadmap / 通常Work / integration / confirmation / roadmap relation / Related / canonical first Work）を持つ。version 1のConsumptionがplanning kindを名指せば不正である。1つのReceiptのConsumption、1つの登録commitのPlanning Consumption、1つの（review kind, target）のPlanning Consumptionは、それぞれたかだか1つ（`review_consumption_conflict`）。

登録deltaのdigestは `review-planning-delta` recordのdigestで、recordの各scalarは型が固定されている: modeはtext（`"000000"` / `"100644"`）、object IDは全長の小文字16進text（SHA-256 repositoryでは64文字、zero IDは64個の `0`）。整数のmodeを持つrecordは別のdigestになる。

## 何を証明し、何を証明として扱わないか（P2）

- **expected physical projection**: Candidateの登録を、canonical Candidate snapshotから計算したW、Runのadapter、登録commitの親Pの正本だけから、writerのbuilderとplanned-write計算で作ったbytes（ledger全体を含む）。
- **C-2(Kp)**（`review-v1-planning-proof-v1`）: Kpがこのplanning mutation自身のcommitであり、branch・親・系譜が記録どおりで、`git diff-tree` のdeltaがexpected physical projectionそのもの（path・transition・mode・byte）で、記録した登録effectもそれと一致し、committed-result loaderで読み直した意味がreviewしたCandidateと一致し、Pの上でcurrency（declared baseを先に）が保たれていること。
- **C-2(Km)**: Kmがこのmutation自身のcommitで、Consumptionだけを加え（v1 / P4-onlyのRun。P5 Runは保存したpolicyにより、consumed Run summaryとConsumptionの2つだけを加える）、その親がKpまたはplanning-owned pathに触れないKpの子孫であり、committed planning proofが通ること。
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

## Work-terminal activation（P3）

activationはProject単位のcapabilityであり、分類の境界である。「`activation_base_head` から、最初の `legacy_event_count` 件のcanonical Eventを `legacy_event_prefix_sha256` で固定したうえで、このProjectはreview-v1のoperation contractでWorkをterminalizeしてよい」と言う。どのWorkがreviewされなければならないとも、Reviewがlifecycleを所有・導出・gateするとも、既存のWork・event・recordの意味が変わるとも言わない。lifecycleの正本ではなく、`ProjectView` / `state.py`、構造validation、startability、progressionはactivation recordを読まない。

```text
Project capability（activation record）  x  呼び出しごとの選択（STARTのdurable marker）
```

**record**:

```text
path      .workline/review/activation/work-terminal-v1.yaml
schema    review-work-terminal-activation   version 1
fields    operation_contract          "review-v1"（唯一の値）
          legacy_event_count          N（0以上の整数）
          legacy_event_prefix_sha256  小文字16進64桁（work-terminal-activation-digest-v1）
          activation_base_head        40桁の完全なcommit id（activationを決めたHEAD）
```

Projectに1つで、論理的な一意性と物理的な一意性は同じである。activation directoryはそのplain fileだけを持ち、他のentry・nested directory・link / junction / reparse pointを持たない。immutable create-onlyで、置き換えず、Worklineは削除しない。同じbytesのreplayは適用済み、違うbytesは `reconcile required`。fieldもversionも増やさず、後のcontractは別pathの別recordである。recordが無いことは「activateされていない」という正当な状態であり、Review fileが無いことはlegacyの証明にならない。

recordを作るのは専用のmaintenance operation `work-terminal-activation` だけで（`rules/git` のOperation Owner）、START・Review・Roadmapは作らない。Nとdigestは、そのHEADがcommitしたevent logから計算し、working treeからは計算しない。recordは、そのpathについてcheckout capability（上記のCheckout capabilityの4層）を示せる時だけ書き、作ったcommitがそのpathに決めたbytesそのものを持つことと、そのcommitでprefixが再現することを確かめる。一度activateしたProjectにもう一度実行しても、recordがcommitされていて、working treeが同じbytesを持ち、prefixがHEADで再現する時に `already_activated` と答えるだけで、何も作り直さず、境界を動かさない。それ以外の状態は採用・作り直し・置換をせず、fail closedする（malformed・未知のrecordはreaderの拒否、それ以外は `reconcile required`）。

**digest**: `work-terminal-activation-digest-v1` は、event logをcanonical Event readerと同じように読み（空の物理行を無視し、CRLFとCRをLFとして読む）、各Eventのrecord形（schemaが許すすべてのfield。運ばれるmetadataを含む）を、keyをcode point順に並べ、separatorを `,` と `:` にし、ASCII escapeせずUTF-8にし、NaN / Infinityを持たず、各recordの後にLFを1つ置いたJSONとし、最初のN件を順に連結したbytesのSHA-256（小文字16進）である。生のbytesではなくparseしたEventを縛るので、CRLF→LFや空行の整理では変わらず、activationより前のEventの変更・並べ替え・削除・挿入・metadataの変更では変わる。Review recordのrendererでもserializerのdigestでもない。identityは（このalgorithm, 有効なEvent schema）の組である。producer、STARTのentry、C-2のproof、validationは同じ1つの実装で計算する。activation record自身のcanonical digest（CandidateとContextが縛るもの）とは、別のmaterialについての別のdigestである。

**分類**（F1 §10。P1 R4 §4.2のactivation後の分類はF1が前方修正している）:

```text
recordなし                         activateされていない（正当）。位置でcompletionを分類しない。
                                   review-v1 markerを持つ work_completed は矛盾（invalid）
record、prefixが再現する           Event 0 .. N-1 はactivation前のlegacyで、何も要らない。
                                   index >= N の work_completed は
                                     markerなし                        legacy。Consumptionを要しない
                                     marker review-v1                  そのterminal_event_idを名指す
                                                                       Work-kind Consumptionがちょうど1つ
                                     それ以外のmarker                   invalid
                                     marker が activation・Run・Receipt と矛盾   invalid
record malformed、operation_contract   fail closed。どのeventもそのせいでlegacyにならない
未知、version未知、prefixが再現しない   （prefixが再現しなければN以降を何も分類しない）
```

markerはeventの `operation_contract` である。markerが本当に無いことだけがlegacyであり、Review metadata（`review_receipt_id` / `review_run_id` / `review_generation`）をmarker無しで持つもの、未知のmarker、review-v1 markerでmetadataがちょうどその4つの正しい値でないものはinvalidで、legacyへ落とさない。totalityの対象はterminal event `work_completed` だけで、`work_started` / `work_target_added` / `work_resumed` / `work_target_removed` はどのindexでも対象外である。eventのmetadataはnon-normativeで、state導出に入らない。

P5 Runのterminal stageは、Runが保存したhistory contractにより、consumed Run summaryのcreateを先頭に同じ3つのeffectを続ける1つのdurableな単位であり、片側の判定はeventとConsumptionについて同じである。片側だけの状態（eventだけ、Consumptionだけ）は、pendingのreview-v1 Work STARTのmutationが、その2つを1つのdurableなterminal stageとして記録しており、欠けている方をそのmutationのreplayがまだ終えられる間だけ正当である。eventだけなら、記録したeventがそのものとして適用済みで、event logがそのmutationの書いたとおりのままであり、Consumptionのcreateが未適用であること。Consumptionだけなら、そのmutationが自分で書いたbytesのConsumptionがあり、event logがそのmutationの記録した、stageの最初のeventを書く直前の内容のままであること。fileの内容から意図を推測しない。それ以外のeventだけ・Consumptionだけ・重複は不正で、`reconcile required` として人が直す。Projectのvalidationはこれらを `review_activation_prefix_mismatch` / `review_completion_marker_invalid` / `review_completion_marker_contradiction` / `review_completion_unconsumed` / `review_consumption_unbound` として報告する。

移行はしない。既存のEventを書き換えず、markerを足さず、完了したWorkを開き直さず、既存のConsumptionを書き換えず、Work単位のactivationを作らず、pendingのlegacy STARTを変換せず、過去のWorkにReview recordを作らない。activationより前のEventの意味は何も変わらない。activationはreview-v1を選ばない。

## Work Review（P3）

**identities**:

```text
review kind                  work-result-v1
task kind / task slot        work-result-review-v1 / work-result-reviewer
projection semantics         work-result-projection-v1
adapter                      work-result-adapter-v1
authorized operation stage   start:work-terminal
target identity              Work ID
operation identity           start:<request identity recordのcanonical bytesのSHA-256>
                             （request identity = work_id と review_contract。STARTのmodeは入らない）
policy                       review-v1-work-policy-v1
```

`review-v1-work-v1` はSTARTの選択子とdurableな `review_contract` markerであり、`work-result-v1` はReview Runの種類である。別のnamespaceにあり、Contextは両方を縛る。どちらも他方から導かず、stateから推測しない。identityに表示番号・時刻・mutation id・host・path・branch名・序数は入らない。

**Candidate**: `review-work-candidate` version 1、ちょうど6 key（schema、version、`review_kind`、`projection`（`reviewed_artifact`、`work-result-projection-v1`、content）、`declared_base`、`activation`）。`candidate_hash` はそのcanonical bytesのSHA-256だけである。`declared_base` は、S-c0の後・Candidateを凍結する直前のcommitted HEAD（`base_commit`）、branchの完全なref名、そのcommitのcommitted stateからcanonical loaderで読んだWork（display、name、desired state（本文の「このWorkで成立させる状態」sectionのtext。frontmatterのkeyではない）、phase、state）とそのdependency・read obligationであり、working treeを読まない。K1の親が `base_commit` である必要はない（F3 A-1。このRun自身のgeneration commitだけを挟んでよい）。

```text
result_commit   entries（宣言したowned pathごと、pathのUTF-8順）と message（結果commitのmessage）
                entry: path、status A/M/D、old_kind / old_mode / old_oid（baseの木）、
                       new_kind / new_mode / new_oid、content_sha256（file / symlinkのbytes。他はnull）
                Gitのtree entryがkind・mode・oidの権威
empty           entries と emptiness_proof（base_commit、宣言したpaths、baseと違うowned path = []）。messageなし
```

Reviewする面は、宣言したowned set（結果pathと削除path）だけである。対応するobject kindはすべて: `100644` / `100755` のfile、`120000` のsymlink（link targetのbytes。追わない）、`160000` のgitlink（参照するcommit id）、そのどれかの削除（`absent`）。executorが返した後に、対応する形を拒否しない（no-trap）。宣言したowned setのspelling・containment・directory・読めないことで正確にprojectできない時だけ `review_candidate_unavailable`。予約namespace（`.workline/review` とその配下、`.workline/events/events.jsonl`）の宣言は、projectabilityではなくownershipの問題で、`reconcile required`（reason `review_reserved_namespace`）である（F3 A-5 / A-6。判定と順序は `skills/start`）。

**no-K1の判別**（F3 A-3）: `artifact_kind` は、Candidateのentryのどれかが変化している（old_* と new_* が違う）かで決まり、entriesやresult pathsが空かどうかでは決まらない。宣言したpathがどれも変化していない（all-inert）Candidateは `empty` でK1を持たず、そのentryもpayloadを持つ。偽の・placeholderの・全0のcommit id、合成した空のcommitは作らない。CandidateとConsumptionの `artifact_kind` は独立の記述であり、両方読んで比べ、どちらも他方から導かない。

**projections**: ReviewedArtifactProjection = Candidateのcontent。AuthorizedTransitionProjection = 許可のもとでSTARTが `base_commit` に対して適用する `work_target_removed` → `work_completed`。OperationMetadataProjection = Receipt・Consumption・terminal eventのoperation-contract metadata等のReview bookkeeping。OperationMetadataProjectionは、lifecycleの正本にも正しさの権威にもならない。

**reconstruction**: snapshot modeだけである。clone-safeなsnapshot material（`review-v1-work-snapshot-material-v1`: Candidateそのもの + entryごとのpayload。file / symlinkはbytes（`base64-rfc4648-v1`）、gitlinkとabsentはpayloadなし。変化していないentryもpayloadを持つ）をcanonicalに置き、そこからCandidateを正確に再構成できなければfail closed。

**Context**（version 2。F3 A-4 / A-7）: `review-work-context` version 2。version 1のfieldを名前・順序・意味を変えずにすべて持つ: review kind、review contract、projection semantics、adapter、loader identity（実行中のimplementation）、authority（configured Workline rootの `registry.md`（`rules/*` の本文はその中にあるのでregistry.mdで縛る）と `skills/start`・`skills/review`・`skills/create` のbytes（CRLFはLFとして）のdigest）、`git_persistence`（値は `review-v1-work-local-v2`。Work persistenceのidentityで、規定は `rules/git`）、activation binding。Effective Policy（`review-v1-work-policy-v1`）はContextではなくgateが縛る。加えるfieldは1つだけで、`review_checkout_capability` はちょうど5 keyで、verdictのfieldを持たない:

```text
capability_contract  review-v1-work-checkout-capability-v1
form                 form-L
namespace            .workline/review/**
base_tree            完全なobject id
resulting_tree       完全なobject id
```

Contextはgeneration 1がtaskをacceptする前に不変になり、TaskInputとすべてのgenerationが `review_context_hash` で縛る。resulting treeがunsafe / unknownでもContextは正当で、Runは作られReviewされる。判定はsealで `Context.resulting_tree` についてだけ導き、`capable` の時だけReceiptを出す（unsafe / unknownは許可しない）。sealはContextのbyteを1つも変えず、新しい `review_context_hash` を計算しない。version 1のContext、`review-v1-work-local-v1` を持つContextは、このcontract versionのものではない。

**activation binding**: CandidateとContextは、activation recordのcanonical digest、`operation_contract`、`activation_base_head` を縛る。これはrecordのbytesについてのdigestで、Eventについての `work-terminal-activation-digest-v1` とは別のmaterialの別のdigestである。

**reviewer**: `WorkReview(reviewer, reviewer_identity, reviewer_version)`。identityとversionはgeneration 1のacceptで縛り、同じtaskはacceptした時のreviewerにだけ再launchする（違えば `review_reviewer_mismatch`）。reviewerは `WorkReviewTask` を受け取り `WorkReviewReport`（status `completed` / `declined`、finding（severity `HIGH` / `MID` / `LOW`））を返す。HIGHとMIDのfinding、`completed` 以外のsettleは許可しない。request envelope（`review-work-request`）はCandidate全体とContextそのものであり、その `work` は `declared_base.work` のwork_id・display・name・desired stateの写しである。

**Work Review Policy**: Work kindのEffective Policy（`review-v1-work-policy-v1`）は次の静的recordそのものである（Workline実装の定数と一致しなければならない）。`effective_policy_hash` はそのcanonical bytesのdigestで、Contextではなくgateが縛る。

```yaml
adjudication_rule: review-v1-work-adjudication-v1
blocking_severities:
  - HIGH
  - MID
declined_disposition: "the task settles failed; the Work completion is not authorized"
error_disposition: "no settlement; the same task is launched again by the next run"
instruction: review-v1-work-instruction-v1
low_disposition: "non-blocking; represented only by digest, in the settled report and the adjudication (its LOW count); P3 keeps no LOW text in a canonical record and returns none to the caller; durable finding history is deferred to the later Repair/History work"
obligation_rule: "every HIGH or MID finding and every failed task is an unresolved obligation; P3 resolves none"
policy_id: review-v1-work-policy-v1
repair: "none; a not-authorized Work completion is not terminalized"
report_statuses:
  - completed
  - declined
reviewer_identity_rule: "caller-declared identity and version, bound at acceptance; a settlement is accepted only from them"
schema: review-work-policy
seal_rule: every required task settled completed and zero unresolved obligations
severities:
  - HIGH
  - MID
  - LOW
slots:
  - required: true
    review_kind: work-result-v1
    task_kind: work-result-review-v1
    task_slot: work-result-reviewer
timeout_disposition: "none imposed by Workline; a reviewer that gives up returns declined"
version: 1
```

LOWのfindingはblockせず、obligationにならない。LOWは、settleしたreportのdigest（taskの `result_digest` とreport setのdigest）とadjudication（LOWの件数）を通して、digestでだけ縛られる。reportの本文（findingのseverity・code・message）はruntimeのcopyにしか置かれず（authorityでもsettlementのmaterialでもない）、canonical recordには残らない。だからP3は、LOWのfindingの本文を永続化せず、callerにも返さない（`StartResult` はfindingを持たない）。runtimeを失うと再構成できない結果を、runtimeがある間だけ返す経路は作らない。findingとそのdispositionの永続的な履歴、LOWの扱いは、後のRepair / Historyの作業である。

**Evidence**: Evidenceは、STARTが実行する凍結した検査（own-bytes: owned pathがwitnessのままであること。review-namespace: 既存のReview recordがすべてcanonicalに読めること）、凍結したCandidateをclone-safeなmaterialだけから再構成してprimary working treeを読まずに行うisolated verification、validity closureのdigestである。reviewerのreportはEvidenceではない。このcontract versionではEvidence completenessはunknownで、reuseは拒否する。

**closureとHEAD advance**（F3 A-2）: ReviewValidityClosureの特化である。CandidateとK1 / K2の間に許すHEAD advanceは、このRun自身のcanonical Review-generation commit（このRunのrecordだけ、Runの検証したchainから導いたpathだけ、すべて追加、mode 100644、parent 1つ、完全なdelta、他のcommitなし）だけである。それ以外のHEAD advance（人・他のtool・他のoperation・他のRun）は、新しいCandidateを要する。一般的なHEAD reuseは、completenessがunknownの間は到達しない。

**Receiptと無効化**: Work Receiptは、このCandidateをこのContext・Policy・Evidenceのもとで `start:work-terminal` に使うことを許すだけで、K1もK2も名指さない。Candidate・Context・Policy・Evidence・activationの変化と、上記の例外以外のHEAD advanceはReviewを無効にし、その許可は使わない。

**seal**: resulting treeがReview namespaceについてcanonicalなcheckout capability（form L、上記のCheckout capabilityの4層）を保つことを、その木について機械的に示せない限りsealしない。reviewerの判断に委ねない。

**proof**: `review-v1-work-proof-v1` のC-2は、immutableな入力に対する再実行可能な証明であり、保存されたverdictではない。C-2(K1)はW1〜W12を、C-2(K2)はT1〜T12を、committed objectだけから証明する（K1 / K2がこのmutation自身のcommitであること、親とRAW lineage、K1のdeltaがCandidateの変化するentryちょうどであること、K2のdeltaがevent logとConsumptionちょうどであること、event logがちょうど2件（`work_target_removed`、`work_completed`）を加えること、Consumptionの内容と束縛、ReceiptとConsumptionの一意性とtotality、許可がまだcurrentであること、結果の束縛（`result_commit` はK1、`empty` は結果deltaなし）など）。3つのprojectionの物理的な置き場所は、ReviewedArtifactProjectionの変化がK1だけ、AuthorizedTransitionProjectionとConsumptionがK2だけである。通常のK2はmetadataだけを加えるcommitで、それ自身をReviewしない（再帰の打ち切り。Class Aの形は下記のWork post-commit recovery（F4））。proof noteはrecoveryのためのpointerで、証明の結果ではない。完了したC-2はdurableなcheckpointであって永久の正しさではなく、各境界で現在の正しさを導き直し、後のcanonicalな事実は通った証明をstaleにする。

**F2を前方修正するF3のstatement**（F2だけを読む人のために）。F3はF2の7つの文を名指しで置き換え、F2のfileは編集しない:

```text
A-1  F2 §5.3          base_commit は S-c0 の後・Candidate凍結直前のcommitted HEAD。K1の親である必要はない
A-2  F2 §14.4 §16.1   「すべてのHEAD advanceは新しいCandidate」から、このRun自身のgeneration commitを除く
A-3  F2 §7.1-7.3      result-bearing / no-K1 の判別は「変化するentryがあるか」。all-inertは empty
A-4  F2 §10.1 §10.3   Context version 2 と、Review namespaceについてのcheckout capabilityの束縛
A-5  F2 §6.2 §6.5     予約されたReview namespace（宣言はownershipの拒否 review_reserved_namespace）
A-6  F2 §6.2 §6.5     予約されたlifecycle event log（同じreason。PRE_S_C0_BASE と declared_base が交換可能になる）
A-7  F2 §10.3         git_persistence の値は review-v1-work-local-v2
```

F2を修正しないF3だけの訂正が2つある。C3-1: Work Review Runのgeneration commitは、durableな `review_kind` が `work-result-v1` の時だけWorkのpersistence identityで作り、planningのRunは何も変わらない。C3-2: Workの完了より前のcommitは、attribute sourceを自分の記録した親にpinする（`declared_base` はまだ無い）。どちらも `rules/git` の規定である。

## Work post-commit recovery（F4）

STARTが作った結果commit K1が存在し、そのC-2(K1)が通らなくなった時の回復の意味を、ここが所有する（流れ・順序・再開は `skills/start`、Gitの安全性は `rules/git`）。K1がまだ無い時に分かった不一致（pre-commit drift）は、その不一致をcommitしない（新しいCandidateが要る）。Class A / B / Cはcommitの後の回復であり、通常の流れの戦略ではない。unknownは証明ではない。

**分類**（明示的でfail-closed。まず安全の事実をそれぞれ示し、その後にだけ分類する）:

```text
Class A   このmutationのS-c1が作った（C-1）exact K1。raw parentがちょうど1つ、完全なdeltaが分かり、そのpathが
          旧Candidateの宣言したowned setの中だけにあり、宣言したbranchがちょうどK1を持ち、旧RunがG1 / G2 / G3で
          sealされ、R1がcurrentで未supersede・未消費、Review namespaceがcanonical、C2をcommitted objectだけから
          凍結でき、K1のpublication effectもterminal effectもdurableでなく、承認先がK1を持たない
  A1      K1のdelta・containment・messageが旧Candidateと違う（operation-ownedな永続化の変換）が、すべてoperation-owned
  A2      K1は旧Candidateそのもので、Context / Effective Policy / Evidenceが今は再導出できない（公開・terminalより前）
Class B   完全なdeltaに宣言したowned setの外のpathがある     reconcile。修復・revert・所有の主張・push・terminalizeをしない
Class C   ownership・ref・lineage・完全なdelta・remote stateを示せない   reconcile。採用・push・terminalizeをしない
```

malformedなnamespace、欠けたimmutable record、矛盾するactivation、既存のConsumption、不明な承認先、foreign lineageは、どれもAに格下げしない。置き換えの許可より前に承認先が既にK1を持つことは、unauthorized / historical publication escapeであり、history rewrite・遡及の許可・通常のClass Aの公開をせず、reconcileする。承認先は固定したpinと、承認先そのものを読むことで判断し、古いremote-tracking refは公開の証拠にしない。

**same-Run invalidation**: 置き換えるRunの封印済みReceipt R1は、同じRunのgeneration 4とSupersession(R1)を1つのgeneration mutationで作って、消費できなくする。generation 4はopenで、Receiptもauthorized stageも持たず、generation 3のacceptedとsettledをそのまま運び、`previous_digest` はgeneration 3のdigest、`evidence_digest` はWorkのinvalidation evidence（`review-work-invalidation-evidence`。`superseded_receipt_id` とreason）のdigestである。reasonは安定したidentity `work_class_a_replacement` で、Supersessionも同じreasonと `superseding_generation` 4を持つ。Supersessionのschemaとvalidatorは変えない（同じRunの後のopen generationによる無効化だけを意味する）。generation 4はWork Runの最後のgenerationで、generation 5は無い。generation 4の後、R1は消費されず、旧Runはcurrentな許可として再開しない。

**successor Run**: 旧Runのgeneration 4がcommitされた後にだけ、置き換えのReview Runを1つ始める。予約keyは `review-successor-run:<predecessor_review_run_id>` で、最初のRunの予約key（`review-run:<review_kind>:<target_identity>`）は変えない。同じ置き換えのreplayは同じsuccessorを予約する。1つのpredecessorにsuccessorはたかだか1つで、successorのsuccessor（再帰的なClass A）は無く、矛盾する予約は `reconcile required` である。successorのreview kind（`work-result-v1`）・target identity（同じWork ID）・operation identityは最初のRunと同じで、予約keyは回復の仕組みであって意味のidentityを変えない。

**request v1 / v2**: versionを持つのはWorkのrequest envelope（`review-work-request`）だけで、Candidate・TaskInput・Receiptのversionは変えない。version 1は `set_aside_runs` を持たず、commit済みのversion 1のTaskInputは書き換えずにそのまま読み、暗黙のset-asideを持たない（version 1が `set_aside_runs` を持てば不正）。F4の後に作る新しいRunはversion 2で、`set_aside_runs`（`review_run_id` と `reason` だけからなる項目を `review_run_id` の順に並べた正確なlist。重複・自分自身・不正な項目・canonicalでない順はfail closed）を持ち、request digestはenvelope全体を覆う。最初のRunは、回復の選択がset asideした、同じreview kindとoperation identityを持つ他のRun（他のSTARTが始めたRunを含む）をそれぞれその分類の理由（`consumed`、`invalidated`、`not_authorized`、`set_aside`、stale reason）で名指し、より古い一致するRunが無い時だけ空のlistを持つ。successorは置き換えた旧Runを `work_class_a_replacement` で名指し、それ以外にset asideした一致するRunもそれぞれの理由で名指す。set-asideは古いRunを削除も編集もせず、そのRunを自動回復の選択から外すだけであり、年齢やIDの順から推測しない。置き換えRunを作らない人の明示の処分は、F4ではなく後の専用operationが所有する。

**C2**: 置き換えCandidateは、commitされたK1とその親だけから作り、working treeを一切読まない。旧Candidateが宣言したpathの集合が閉じた宣言集合で、各entryのold identityはparent(K1)から、new identity（file / symlinkはbytesも。gitlinkと削除はpayloadなし）はK1から読み、変化しないentryも残す。parent(K1)からK1への完全なdeltaはその集合の外のpathを持たない。messageはK1に永続されたmessageそのもの、`declared_base` はparent(K1)、resulting treeはK1の木そのものである。Context・Effective Policy・Evidence・activationは今のものを新しく計算し、C2は新しいReviewを受ける。古い許可は再利用しない。

**K_adoptとadopted-result**: K_adoptは、successorのgeneration 3とR2を永続するcommitそのものであり、Reviewのsealの後に別のmetadata commitを作らない（再帰の打ち切り。K_adopt自身も、旧generation 4とsuccessorのgeneration commitも、Reviewを受けない）。K1からK_adoptまでの範囲は、旧Runのgeneration 4のcommitとsuccessorのgeneration 1・2・3のcommitだけで、domain・成果・lifecycleの変化を含まない。それ以外のpath・domain・lifecycleのdeltaはClass B / reconcileであり、もう一度のClass Aにはならない。adopted-result proof（`review-v1-work-adopted-result-proof-v1`）は、committed objectだけから、exact K1の所有、範囲の各commitがちょうど一つ前のcommitの上にありそのgenerationのrecordだけを加えること、旧Runのgeneration 4とSupersession、successorがsealされR2を出していること、C2がexact K1を縛ること、R2・Context・Policy・Evidence・activation・declared baseがcurrentであること、ConsumptionもterminalもまだRunに無いこと、承認先のidentityを示す。その公開の役割（adopted-result）は通常のresultの役割と別であり、1つの完了がその両方を持つことはない。

**terminal**: Consumptionは従来どおり、R2を消費し `authorized_result_commit_sha = K1` を縛る（R2が許可したC2の永続した成果がK1だから）。K_terminalの親はK_adoptである。terminal proofは、R2 / C2 / ConsumptionがexactなK1を縛ることと、K1 → 旧generation 4 → successor generation 1 → 2 → 3 = K_adopt → K_terminal の系譜とを別々に証明し、K1の後に成果のdeltaが無いことを示す。通常のF3は従来どおり parent(K2) = K1 であり、どちらの親の規則を使うかはdurableなClass-A checkpointだけが決め、親の形からは決めない。

**回復の選択**: 1つのWork Review invocationについて、同じreview kindとoperation identityを持つすべてのRunを、canonical recovery discoveryで consumed / invalidated（supersede済み）/ set_aside / not_authorized / 回復可能 / stale / incomplete のどれかと示す。回復可能がちょうど1つならそれを続け、0なら通常の前提が許す時に新しいRunを始めてよく、複数またはincomplete・矛盾したRunがあれば `reconcile required`。consumed・invalidated・set asideのRunは再開しない。新しさで選ばない。operation identityはmutation id・時刻・modeを含まないので、同じWorkの別のSTART（失われたSTARTを含む）が始めたRunも一致するRunであり、これはreview-v1 Work STARTのすべての呼び出し（新しいSTART、最初のRunだけを続ける再開、Class Aの再開）に適用する。Work Review Runは、それを予約したSTART mutationのrecordとcanonicalなReview recordからだけ続けられる（`skills/start` のresume）。残りのstageが使うもの（予約したRun・task・Receipt・ConsumptionのID、generation mutationの所有者、Candidateを凍結した時のownership witnessとpre-existing dirtyのsnapshot、S-c0 / S-c1のcommit（C-1）、terminal stage）はそのrecordだけにあってReview recordには無く、別のmutationはそれを持てない（新しいIDを予約し、回復した予約を結び付けるのはrecovery planning mutationだけで、失われたSTARTのexecutorが書いたbytesは開始前からの変更としてsnapshotし、自分が作っていないcommitを自分のものとして採用しない）。そのため回復可能な形のRun（currencyがcurrentなgeneration 1か許可するgeneration 2、またはseal済み）が回復可能なのは、このWorkのpendingのSTART mutationがそれを予約している時だけであり、どのpendingのSTART mutationも持たないものはincomplete（`review_recovery_incomplete`）である。このWorkのpendingのSTART mutationが予約したRunはそのmutationの回復selectorのものであり、ここでは分類しない（そのRunのrequestがset asideしたRunはset asideのまま）。呼び出しと同じinvocationのmutationは開かれて再開し、そのselectorが自分のRunを続ける（ちょうど1つの回復可能なRunの再開）。別のmode等、別のSTART mutationが持つRunがある時は、mutationを開く時に従来のwrite scopeの衝突として `reconcile required` で止まり、何も予約せず、その横に新しいRunを始めない。それ以外の一致するRunは、どれも再開しないもの（consumed・invalidated・not_authorized・set_aside・stale）でなければならず、incompleteなRunがあれば、mutationを開く前に `reconcile required`（`review_recovery_incomplete`）で止まり、何も予約・記録・書き込みせず、executorを実行しない。

Class-A checkpointとadopted-result proof noteはSTART mutationのruntime materialであり、canonical Review recordでもlifecycleの正本でもない。generation 4・Supersession・successorのRunを含め、Review recordはlifecycleの権威にならない。

## P4 Repair Loop（current-cycle Repair / BL-004）

P4はreview-v1 planning kindとreview-v1 Work kindに共通の、明示opt-inの新しいReview contractである。v1（P2 / P3 / F4）のRun、Receipt、TaskInput、Policyの意味は一切変えない。共通の意味は `workline.review.p4`（inert: lock・mutation・file書き込み・Git finalization・lifecycle遷移を持たない）、kind固有のCandidateは `review/planning.py` と `review/work_review.py`、operationの所有はRoadmap（`skills/roadmap`）とSTART（`skills/start`）が持つ。Reviewはlifecycle・top-level Project mutation・Git finalizationを所有しない。

識別子: planning P4 contract `review-v1-planning-p4-v1`、Work P4 contract `review-v1-work-p4-v1`、P4 Effective Policy `review-v1-p4-policy-v1`、discovery instruction `review-v1-p4-discovery-instruction-v1`、adjudication instruction `review-v1-p4-adjudication-instruction-v1`（adjudication contract `review-v1-p4-adjudication-v1`）、repair instruction `review-v1-p4-repair-instruction-v1`。task kind: `p4-discovery-v1`（slot `p4-discovery.<viewpoint>`）、`p4-adjudication-v1`（slot `p4-adjudicator`）、`p4-repair-v1`（slot `p4-repair`）。ID kind: Finding `rfd`、Repair Batch `rrb`。予約key: `review-finding:<run>:<正規順の序数>`、`review-repair-batch:<source run>`、後継Runは既存の `review-successor-run:<predecessor>`。

### discovery != adjudication

discoveryはfreshである。discovery actorは固定されたCandidate、現在のrequirement / desired state、Context / Policyと必要なEvidenceを受け、過去のFinding / Repair historyを受けない。discoveryはclaimを報告するだけで、Problem / Improvement / HUMANを決めず、Candidateを修理しない。adjudicationはhistory-awareで、凍結されたraw report、Candidate、requirement、Context / Policy、同じcycleの過去Finding / Repair関係を受ける。adjudicatorもCandidateを変更しない。

### canonicalなraw report

P4のdiscovery reportはcurrent-cycleの正本recordである: `.workline/review/reports/<result_digest>.yaml`（ファイル名 == canonical report recordのdigest == settleした `result_digest`）。rawは「未adjudication」の意味であり、未sanitizeではない。永続化の前にH-3を満たす（chain-of-thought・transcript・secret・不要な絶対/local path・不要なprivate識別子を持たない）。H-3を満たせない戻り値は永続化もsettleもせず、同じtaskを同じactorへ再launchする。raw reportは不変で、後のadjudicationを反映して書き換えない。reviewerのseverityはadjudicationの入力であり、権威ではない。

### Problem / Improvement / HUMAN（§12.4の順）

各claimを次の順で一つの結果へ: 1 支持されない → `unsupported`（Findingなし）、2 requirementの意味を決める必要がある → `HUMAN`（推測で定義しない）、3 決定済みrequirementを満たさない → `Problem`、4 実行可能なより良い代替がある → `Improvement`、5 それ以外 → `dismissed_non_actionable`。内容categoryは `Problem` と `Improvement` だけで、Findingを作るのもこの2つだけである。重複は修理identityでだけ統合し（同じ問題・同じ意味責任・一つの修理で全source claimが閉じる時だけ）、不確かなら別のまま、統合したseverityは支持される最も強いもので全source参照を保つ。順序の飛ばし、支持されないclaimのFinding化、HUMANの不確かさのProblem化、目標が成り立たない時のLOW非blocking、因果linkなしのB/C、claimの欠落、G3が束ねていないreport、矛盾する重複Finding identityは `review_p4_adjudication_invalid` で何もsettleしない。

### blocking（H-4）

Problem HIGH / MIDはblockingなcurrent-cycle義務である。Problem LOWは現在の完了目標が成り立つ間だけ非blocking。ImprovementはHIGH / MID / LOWのどれでも非blocking。`C_REPAIR_INDUCED` のProblemは未解決のまま収束させない。LOW・Improvementは自動でWorkを作らない（disposition: `repaired_current_cycle`、`retained_history_only`、`future_work_candidate`、`no_action_after_adjudication`）。

### P4 Runの形（G1-G6、G7は無い）

```text
1 accept      discovery task(s) + CandidateSnapshot + 開いたgate
2 settle      全discovery taskのsettle + canonical raw report
3 accept      canonical materialだけから作ったadjudication TaskInput
4 settle      canonical adjudication record + obligation digest
5 seal        AUTHORIZATION_READY: gate 5（sealed_authorized）+ Receipt（review_generation 5）
5 accept      REPAIR_REQUIRED: Repair Batch + repair TaskInput（Receiptなし）
6 settle      Repair Result + CandidateSnapshot N+1（Receiptなし）
6 invalidate  stale化した G5 Receipt: 開いたgate 6 + Supersession（G-3）
```

generation 5と6がどちらの形かは、正本record（accepted descriptorのtask kind、seal、settlement、Supersession）から読み、generation番号だけでは決めない。P4のG4をv1のinvalidationと、P4のG5 sealをrepairと読まない。外部actor（discovery・adjudicator・repair）は、そのTaskInputとaccepted descriptorがcommit済みgenerationに永続し読み戻せるまでlaunchしない。runtime喪失後も同じtaskを同じactor identity / versionにだけ再launchする。HUMANが残るRunはG4でHUMAN_WAITのまま止まり、修理を推測しない。

A stale P4 authorization Receipt is invalidated by a P4 G6 invalidate transition that atomically Supersedes the G5 Receipt. Repair G6 and invalidation G6 are distinct transition shapes. No G7 exists. P4 Work does not reuse F4 Class A for a G5-sealed P4 Run.

A HUMAN_WAIT Run remains non-authorizing at G4. A later Human decision is supplied through the owning operation boundary as an explicit decision identity and disposition. The decision does not create a separate requirement store. A requirement change must already be reflected in its normal authority; a confirmation may leave requirement bytes unchanged. The owner binds the decision, sets the prior HUMAN_WAIT Run aside as `human_decision`, freezes a new Candidate/Context as needed, and starts a new P4 Run.

### one Repair Batch per Candidate generation

REPAIR_REQUIRED のadjudicationは、そのCandidate世代につき一つだけの不変Repair Batch（`.workline/review/repair-batches/<repair_batch_id>.yaml`）を作る。batchは決定可能なblocking Problem HIGH / MIDを全部持ち、Improvement・HUMAN・unsupported・dismissedを持たず、LOW Problemは意図して修理すると決めた時だけ持つ。ReviewRepairRequestは正本recordだけから組み立てる。repair actorは完全なrepaired Candidate proposalを返すだけで、Review権威として作業treeを書き換えない。例外・不正な戻り値はsettleせず（`review_p4_repair_invalid`）、明示のfailed / declinedは旧Candidateを決して認可せず成功修理にもしない（`review_p4_repair_failed`）。Repair Coverage Checkは構造化dataで、unknown（未解決gap、列挙不能、未coverage）はPASSしない（`review_p4_repair_coverage_unknown`）。共有責任に対する局所patchは、次のFormal Reviewを使う前に広げる（`review_p4_repair_widen_required`）。各修理は一つのimpact class（LOCAL / SHARED / CONTRACT / FOUNDATION）を記録し、最低再検証はファイル数でなく意味的影響で決まる。必要な再検証が残る修理は後継Runへ進めない（`review_p4_reverification_incomplete`）。

### new Candidate / new Run after repair

成功した修理はG6で不変のRepair Result（`.workline/review/repair-results/<repair_batch_id>.yaml`）と完全なCandidateSnapshot N+1を持つ。Candidate N+1はpatchでなく完全な新Candidateで、結果候補世代 = source + 1。どのReview Runもcandidate_hashをその場で変えない。後継Runは同じoperation identity・同じtarget / review kindで、RB3-C1の決定的な後継予約（`review-successor-run:<predecessor>`、一つの前任につき後継はたかだか一つ、衝突はreconcile）を使い、request（succession）が前任Run・Repair Batch・Repair Result digest・candidate_generationを明示し、前任を `p4_repaired` としてset asideする。世代は file順・時刻・最新IDから導かない。

P4 planning Candidate N+1 currency is proven from its immutable Repair Result, complete stored CandidateSnapshot, successor linkage, current declared base, Context, Policy and decided requirement/desired-state authority. A repaired Candidate is never reconstructed from the original Candidate-N caller request merely to test equality.

The Work repair actor returns a complete repaired Candidate proposal/material and never directly mutates the canonical working tree as Review authority. After G6, the owning START alone adopts the exact proposal onto the allowed result surface using the existing ownership, overlap, witness, resulting-tree and verification machinery. The adopted Candidate must equal the persisted Candidate N+1 exactly before successor Review or Git persistence.

### Evidence-only positive-proof reuse

Candidate NのreportもadjudicationもReceiptも、N+1の認可として再利用しない。N+1のformal discoveryは新しいCandidateに対して行う。Evidenceだけが、`closure` の依存class語彙の下で正に証明された時（両方の宣言がcomplete、必須classがcover、非必須classが説明済み、具体identity・adapter identity / version・proof mechanismが不変、修理impactが証明した前提を壊さない）だけ再利用できる。それ以外は `unknown` / `invalidated` で取り直す。全体Reviewの再利用に `closure.may_reuse` を使わない。planning EvidenceはP4ではfresh-use-onlyである。

### A/B/C と STRATEGY_CHANGE

修理後のFindingの関係は `A_NEW`・`B_RECURRENCE`（前のFinding / Repairを名指し、同じ問題・意味責任、前の修理が閉じなかった正の根拠）・`C_REPAIR_INDUCED`（原因のRepair Batchと因果Evidence digest）。時刻だけで因果を決めず、不明はA_NEW。同じsemantic surfaceで連続する二つの支持されたB/C（BB・CC・BC・CB）の後の修理は `STRATEGY_CHANGE` でなければならず、変えない通常戦略は受け付けない（`review_p4_strategy_change_required`）。timeout・rate limit・crash・不正な戻り値などの運用失敗は再発に数えない。semantic round上限は無い。

### convergence

認可できるのは、未解決のblocking Review義務が0で、必要なcoverage・Evidenceが現在の時だけである（全discoveryのsettle、coverageの充足または明示解決、raw reportの永続、adjudication完了、未adjudication claim 0、Problem HIGH / MID 0、LOWとImprovementの追跡可能なdisposition、未解決HUMAN 0、修理後再検証の完了、最新Repair Coverage Checkの完了、未解決の修理起因Problem 0、未実施STRATEGY_CHANGE 0、認可に使うEvidenceが現在）。「新しいfinding = 0」は必要条件でも十分条件でもない。verification-onlyのIntegration Evidenceは、宣言されないProject / 外部 / nested状態の永続変更があればPASSしない（gitlink identityはnested作業treeの変更を認可しない）。Integrationが要求する修理は通常のfix Workとして既存のprogressionで扱う。

### namespace と version dispatch

P4は閉じたReview namespaceへ `reports/`、`adjudications/`、`repair-batches/`、`repair-results/` を加える。4種のrecordはすべてimmutable create-only・strict schema・canonical bytes・clone-safeで、参照されていても孤立していても検証し、checkout capability / path安全性の証明に含まれ、lifecycle truthではない。どのcontractかは永続したTaskInput / requestが明示するP4 contractだけで決め、generation数やrecordの形から推測しない。pendingのv1 Runはv1のままでだけ再開し、v1 RunをP4へ黙って昇格しない。v1 Receiptは束ねたpolicyのままで解釈する。

P4のSTOP code: `review_p4_human_wait`、`review_p4_adjudication_invalid`、`review_p4_adjudicator_failed`、`review_p4_repair_failed`、`review_p4_repair_invalid`、`review_p4_repair_coverage_unknown`、`review_p4_repair_widen_required`、`review_p4_reverification_incomplete`、`review_p4_strategy_change_required`、`review_p4_human_decision_invalid`、`review_p4_receipt_invalidated`。P4のreconcile reason: `review_p4_contract_mismatch`、`review_p4_linkage_invalid`、`review_p4_successor_conflict`、`review_p4_adoption_mismatch`、`review_p4_chain_invalid`。

## P4 Review Policy

P4のEffective Policyは次の静的recordそのものである（Workline実装の定数 `workline.review.p4.POLICY_RECORD` と一致しなければならない）。

```yaml
adjudication:
  contract: review-v1-p4-adjudication-v1
  instruction: review-v1-p4-adjudication-instruction-v1
  merge_rule: "same substantive issue, same semantic responsibility, one repair closes all; uncertain stays separate"
  order:
    - unsupported
    - HUMAN
    - Problem
    - Improvement
    - dismissed_non_actionable
  severity_rule: "the strongest severity the adjudication supports; the reviewer's severity is input only"
  slot: p4-adjudicator
  task_kind: p4-adjudication-v1
blocking_rule: "Problem HIGH or MID, and every C_REPAIR_INDUCED Problem, is a blocking current-cycle obligation"
categories:
  - Problem
  - Improvement
convergence_rule: "unresolved blocking review obligations = 0 and required coverage and Evidence are current"
discovery:
  history: "fresh: no prior Finding or Repair history"
  instruction: review-v1-p4-discovery-instruction-v1
  report_rule: H-3 public-safe structured claims plus an explicit coverage declaration
  slot_rule: "one required task per viewpoint the P4 selector binds; at least one"
  task_kind: p4-discovery-v1
dispositions:
  - repair_required
  - repaired_current_cycle
  - retained_history_only
  - future_work_candidate
  - no_action_after_adjudication
evidence_reuse_rule: "positive proof under the dependency vocabulary only; a report, adjudication or Receipt is never reused"
human_rule: "a required requirement decision is HUMAN_WAIT at generation 4; no repair guesses it"
impact_classes:
  - LOCAL
  - SHARED
  - CONTRACT
  - FOUNDATION
improvement_rule: Improvement of any severity is non-blocking
last_generation: 6
low_rule: Problem LOW is non-blocking only while the current completion objective still holds
outcomes:
  - unsupported
  - HUMAN
  - Problem
  - Improvement
  - dismissed_non_actionable
policy_id: review-v1-p4-policy-v1
relations:
  - A_NEW
  - B_RECURRENCE
  - C_REPAIR_INDUCED
repair:
  batch_rule: one Repair Batch per Candidate generation holding every decidable blocking Problem
  instruction: review-v1-p4-repair-instruction-v1
  proposal_rule: "a complete repaired Candidate proposal; the owner alone adopts it"
  slot: p4-repair
  task_kind: p4-repair-v1
reverification_minimums:
  CONTRACT:
    - adjacent_eligibility
    - contract_roundtrip
    - failure_interruption_resume
    - writers_readers
  FOUNDATION:
    - broad_integration
    - full_suite
  LOCAL:
    - direct_consumers
    - focused_tests
  SHARED:
    - focused_tests
    - integration_checks
    - representative_callers
review_contracts:
  - review-v1-planning-p4-v1
  - review-v1-work-p4-v1
schema: review-p4-policy
seal_generation: 5
severities:
  - HIGH
  - MID
  - LOW
strategy_rule: two consecutive supported B/C failures on one semantic surface require STRATEGY_CHANGE
version: 1
work_creation_rule: LOW and Improvement never create Work automatically
```

## P5 Review History（durable Review history / BL-005）

P5は、P4-capableなRunにだけ、Reviewの事実をclone安全な不変historyとして残す。historyは不変のP1-P4 record（CandidateSnapshot、TaskInput、gate、Receipt、Consumption、Supersession、raw report、adjudication、Repair Batch、Repair Result）への検証済みprojection / referenceであり、lifecycleの正本ではない。scheduler・queue・第二のRoadmap・自動Work生成器・AI memoryでもない。共通の意味は `workline.review.history`（inert）と `workline.review.p4` のP5 owner material（inert）が持ち、書き込みは各sourceの事実を永続させる同じtransitionで、そのoperation owner（Roadmap / START）だけが行う。

P5 capability is an explicit per-Run stored Review policy/history-contract property within the P4-capable owner family. New first Runs use the P5-capable policy after P5 activation; a cycle keeps the policy/history family of its first Run. Existing P4-only Runs are never upgraded by file presence, current code, or shape inference.

識別子: history contract `review-v1-history-v1`、P5 Effective Policy `review-v1-p5-policy-v1`（P4と同じowner contract `review-v1-planning-p4-v1` / `review-v1-work-p4-v1` の中の、Runごとに保存されるpolicy。新しいowner markerもselectorも無い）、P5 adjudication instruction `review-v1-p5-adjudication-instruction-v1`。P5 requestは `policy_id` と `history_contract` を明示し、discovery requestはそのgeneration 1が書くset-aside summaryとHuman Decision Evidenceをidentityとdigestで束ねる。P4-onlyのrequest / TaskInput / Context / Receiptのbytesは変えない。currencyは常にそのRunが保存したpolicyで判定し、現在のdefaultと比べない。pendingのowner mutationでまだRunが無いものだけが、最初のRunを現在のP5 defaultで作る。

### 不変のhistory layout

```text
.workline/review/history/
  runs/<review_run_id>.yaml          Run summary（Runごとにただ一つ、最終dispositionの時に一度だけ）
  findings/<finding_id>.yaml         Finding summary（正規化Findingごとに一つ）
  repairs/<repair_batch_id>.yaml     Repair summary（成功した修理ごとに一つ）
  relations/<relation_id>.yaml       後の / cross-runのrelation（ID kind `rhr`）
  human-decisions/<decision_id>.yaml Human Decision Evidence（影響Runごとに一つ、ID kind `rhd`）
```

すべてimmutable create-only・strict schema・canonical bytes・filename == record identityで、可変の「現在のhistory」fileもindexも持たない。予約keyは `review-relation:<run>:<決定的な序数>` と `review-decision:<影響Run>`（`review-run:` では始まらない）。

History namespace structure is validated by the shared Review readers. Cross-source history semantics are validated separately. A P5 history defect blocks the P5 transition whose stored contract requires that history; it does not become a new lifecycle gate for unrelated pre-P5 or P4-only operations.

### 書く境界（ownerの責任）

```text
G1 accept       set-asideする前任のうち、P5で最終summaryの無いRunの set_aside summary
                + 影響HUMAN_WAIT RunごとのHuman Decision Evidence（外部launchの前にcommit）
G2 settle       discovery taskがfailedでsettleする時: not_authorized Run summary（同じG2）
G4 settle       Finding summary全部 + 受理したrelation + HUMAN_WAITならRun summary（同じG4）
G6 settle       Repair summary + repaired_to_next_candidate Run summary（同じG6）
G6 invalidate   invalidated Run summary（同じG6、Supersessionと一緒）
Consumption     consumed Run summaryを先に、同じstageでConsumption（同じowner commit）
```

A P5 Run whose canonical G2 settlement makes discovery non-authorizing receives its immutable not_authorized Run summary in that same G2 transition.

Run summaryは一度だけ書き、authorizedからconsumed / invalidatedへ書き換えない。Receipt発行の時点では書かない。planningのKmはP5 RunではRun summaryとConsumptionの2つを加え、WorkのterminalはP5 RunではRun summaryのcreateを先頭に、同じ3つのeffect（2つのevent、Consumption）を続ける1つのdurableなstageである。どちらもsourceのConsumptionに対してcommit後に証明する。v1 / P4-onlyの形は変えない。

`authorized` and `historical_escape` remain reserved Run-disposition vocabulary values, but P5 writes neither until a canonical source transition exists that can prove that final disposition. Downstream escape is represented by an immutable relation, never by rewriting a prior Run verdict.

### 必要なhistoryのgate（P5 Runだけ）

保存されたcontractがhistoryを要求するP5 Runだけが、次を越える前に `require_history_ready` を通す: G4はFinding summaryが全部canonicalであること、HUMAN_WAITはそのRun summary、repairしたG6はRepair summaryとrepaired summary、Human decisionの下での後継launchはHuman Decision Evidence、通常のConsumptionは同じtransitionのconsumed Run summary。欠けていれば `review_p5_history_missing`、sourceと合わなければ `review_p5_history_invalid` で何も進めない。pre-P5（v1 / P3 / P4-only）のRunは `not_required_by_contract` で、このgateを持たない。backfillはしない: 古いcommit・chat・memoryからhistoryを合成せず、無いevidenceは無いままにする。

### Finding / Repair / causality / relation

Finding summaryはcanonical P4 adjudicationのFindingから正確に写し（category・severity・semantic surface・disposition・A/B/C）、unsupported / HUMAN / dismissedのclaimからは作らない。本文はP4がpublic-safeとしてcanonical化した文だけである。Repair summaryはRepair BatchとRepair Resultから写し、時間的な隣接を因果としない。因果 / 関係のstatusは `supported`・`unresolved`・`insufficient_evidence` で、`supported` だけがsupporting evidence digestを持って確定した再発 / 因果として数えられる。不明は不明のまま残す。

A P5-capable adjudication receives a deterministic validated prior-history reference set for the same target/review kind and may return structured cross-run relation claims. Accepted relations are immutable new G4 facts; they never rewrite prior Findings or Runs.

relation recordは端点のrecordを書き換えない。Finding summaryの `relation_ids` は同じG4で受理したrelationだけを束ね、後のrelationで追記しない。LOW Problem・Improvementはどのseverityでも自動でWorkを作らない。将来Workとのprovenance link（`future_work_link`）は明示のCREATE入力からだけ作る（`skills/create` のfuture Work provenance）。Future Work provenance is optional explicit CREATE input. P5 never schedules or creates Work automatically. When source_finding_id is supplied and valid, CREATE persists one future_work_link relation in the same canonical owner commit as the Work without changing Work progression or originating completion dependencies.

### Human Decision Evidence

Human Decision Evidence explicitly identifies the prior HUMAN_WAIT Run and candidate affected by the decision. The owner validates that exact canonical G4 HUMAN state, sets that Run aside as `human_decision`, persists one immutable evidence record before the resumed external Review launch, and separately proves the current canonical requirement/authority. Evidence never substitutes for requirement authority.

P5のcycleをHuman decisionの下で再開するには、`p4.HumanDecision` に加えて、P4 request bytesに入らない別の明示入力 `p4.DecisionEvidence`（影響Run・Candidate・decision identity / disposition・HUMAN entry / coverage gap・public-safeな問いと決定の要約・requirement authority identity・action class・source / effect digest）が要る。無ければ `review_p5_history_missing`、名指すRunが正当なHUMAN_WAITでない・再開されない・P4-onlyなら `review_p5_decision_evidence_invalid`、`requirement_changed` なのにcanonical authorityが変わっていなければ `review_p5_authority_mismatch` で、どれも何も予約・記録・launchする前に止まる。P4-onlyのcycleは従来どおり `p4.HumanDecision` だけで再開する。

### H-3

P5 recordはstructuredでpublic-safeである。chain-of-thought・hidden reasoning・raw model / chat transcript・secret / credential・自由な追加map・不要な個人情報 / local path / machine識別子を持つfieldは無い。写すのはP4がcanonical化したpublic-safeな文と、明示の構造化P5入力だけで、危険な文は別の主張へ書き換えず拒否する。Work Candidateのpayloadはhistoryへcopyせずdigestでだけ参照する。P1-P4のreconstruction materialは削らず弱めない。

P5のSTOP code: `review_p5_history_missing`、`review_p5_history_invalid`、`review_p5_disposition_unsupported`、`review_p5_authority_mismatch`、`review_p5_decision_evidence_invalid`。P5のreconcile reason: `review_p5_history_conflict`。

## P5 Review Policy

P5のEffective Policyは次の静的recordそのものである（Workline実装の定数 `workline.review.p4.P5_POLICY_RECORD` と一致しなければならない）。

```yaml
adjudication:
  contract: review-v1-p4-adjudication-v1
  instruction: review-v1-p5-adjudication-instruction-v1
  merge_rule: "same substantive issue, same semantic responsibility, one repair closes all; uncertain stays separate"
  order:
    - unsupported
    - HUMAN
    - Problem
    - Improvement
    - dismissed_non_actionable
  prior_history_rule: "a deterministic complete set of validated P5 Run / Finding / Repair history references of the same review kind and target, by digest; no chat memory, transcript or Candidate copy"
  relation_rule: "structured cross-run relation claims (type, source Finding, prior target, surface, status, evidence digests, public-safe rationale); only supported is confirmed"
  severity_rule: "the strongest severity the adjudication supports; the reviewer's severity is input only"
  slot: p4-adjudicator
  task_kind: p4-adjudication-v1
blocking_rule: "Problem HIGH or MID, and every C_REPAIR_INDUCED Problem, is a blocking current-cycle obligation"
categories:
  - Problem
  - Improvement
convergence_rule: "unresolved blocking review obligations = 0 and required coverage and Evidence are current"
discovery:
  history: "fresh: no prior Finding or Repair history"
  instruction: review-v1-p4-discovery-instruction-v1
  report_rule: H-3 public-safe structured claims plus an explicit coverage declaration
  slot_rule: "one required task per viewpoint the P4 selector binds; at least one"
  task_kind: p4-discovery-v1
dispositions:
  - repair_required
  - repaired_current_cycle
  - retained_history_only
  - future_work_candidate
  - no_action_after_adjudication
evidence_reuse_rule: "positive proof under the dependency vocabulary only; a report, adjudication or Receipt is never reused"
history:
  authority_rule: "history is a validated projection and reference layer, never lifecycle truth, a scheduler or a Work generator"
  contract: review-v1-history-v1
  family_rule: "a cycle keeps the policy and history contract of its first Run; an existing Run is read only from its own stored identity and is never upgraded"
  finding_rule: "one Finding summary per normalized Finding, in the G4 that persists the adjudication"
  human_decision_rule: "one Human Decision Evidence record per affected HUMAN_WAIT Run, in the successor G1 before any external launch; never requirement authority"
  relation_rule: accepted relations are immutable new G4 facts and never rewrite an endpoint
  repair_rule: "the Repair summary and the repaired Run summary, in the G6 that persists the Repair Result"
  sanitation_rule: "structured public-safe fields only: no chain-of-thought, transcript, secret, free map or Candidate payload"
  summary_rule: "one immutable Run summary, written in the transition that makes the Run's durable disposition final; the two reserved dispositions no transition proves are never written"
human_rule: "a required requirement decision is HUMAN_WAIT at generation 4; no repair guesses it"
impact_classes:
  - LOCAL
  - SHARED
  - CONTRACT
  - FOUNDATION
improvement_rule: Improvement of any severity is non-blocking
last_generation: 6
low_rule: Problem LOW is non-blocking only while the current completion objective still holds
outcomes:
  - unsupported
  - HUMAN
  - Problem
  - Improvement
  - dismissed_non_actionable
policy_id: review-v1-p5-policy-v1
relations:
  - A_NEW
  - B_RECURRENCE
  - C_REPAIR_INDUCED
repair:
  batch_rule: one Repair Batch per Candidate generation holding every decidable blocking Problem
  instruction: review-v1-p4-repair-instruction-v1
  proposal_rule: "a complete repaired Candidate proposal; the owner alone adopts it"
  slot: p4-repair
  task_kind: p4-repair-v1
reverification_minimums:
  CONTRACT:
    - adjacent_eligibility
    - contract_roundtrip
    - failure_interruption_resume
    - writers_readers
  FOUNDATION:
    - broad_integration
    - full_suite
  LOCAL:
    - direct_consumers
    - focused_tests
  SHARED:
    - focused_tests
    - integration_checks
    - representative_callers
review_contracts:
  - review-v1-planning-p4-v1
  - review-v1-work-p4-v1
schema: review-p5-policy
seal_generation: 5
severities:
  - HIGH
  - MID
  - LOW
strategy_rule: two consecutive supported B/C failures on one semantic surface require STRATEGY_CHANGE
version: 1
work_creation_rule: LOW and Improvement never create Work automatically
```

## P6 Project-local Adaptive Policy（§15 / §30）

P6は、Global Review policyを下限として、Project固有の検証の強さを2つの固定surfaceの範囲内でだけ学習・調整する。Projectが学べるのは「どう検証するか」であり、「何が正しいか」ではない。Global policyはこのProjectから書き換えない（その変更はRB7）。

### GlobalPolicyBaseline

正本のloaderは読み取り専用の `workline.review.policy.load_global_baseline` である。RB7がGlobal policyを実体化するまでは `source_mode: derived-baseline` で、Workline rootの `registry.md` と review / roadmap / start Skillのdigest、固定meta-rules、2つのsurface定義、既存のplanning / Work / P4 / P5 / P6 policy identityから正確・再現可能に導く。canonical digestがbaseline identityで、Review ContextとProfileがそれを束ねる。Workline rootへは何も書かない。読めないauthorityは `review_p6_baseline_unavailable` で止まる。

### 固定の2 surface

```text
review.discovery.required_slots      default   Global 1  範囲 1..4  N個の必須discovery slotを、N組の異なるreviewer identity/versionで
review.reverification.extra_scope_steps  adaptive  Global 0  範囲 0..3  修理の再検証をimpact levelからN段広げる（FOUNDATIONで頭打ち、P4の下限より下げない）
```

強さは「大きい整数ほど強い」。登録されていないsurfaceは調整できず、学習で増えることもない。正しさ・権限の意味（severity / blocking、Problem / Improvement / HUMANの意味、要件の権威、Receipt / Consumptionの正しさ、Mutation / Gitの安全不変条件、self-hosting、破壊的操作の規則、Project固有capabilityの承認境界、lifecycleの完了・順序）は絶対に調整できない（`review_p6_surface_non_adaptive`）。

### canonical Project Profile

Project固有のpolicyの正本は `.workline/review/policy/project-profile.yaml` の1件だけである。無いことは正当で、Global baselineそのものを意味する。Project開始はこれを作らず、backfillもしない。中身は厳格なschema（version、親のdigest、束ねたbaselineのdigest / version、loader semantics identity、surfaceごとのoverride、active experiment refs）だけで、自由記述・script・credential・絶対pathの欄は無い。bytesはcanonicalそのものでなければならない（`review_p6_profile_invalid`）。

Profileを変えるのは内部operation `project-policy-change`（owner `project-policy-change`、`workline.project_policy`）だけで、専用のMutation effect `replace_review_profile`（そのpath・そのownerだけ、直前のbytesの正確な期待値とのcompare-and-replace）で書く。generic write_fileはこのnamespaceへどの大小文字でも届かない。他のReview recordは今までどおりimmutableである。Project-facingのSkillもregistry routingも増やさない。

lineageはimmutableな変更記録から証明する: version 1は不在から、以後は正確な親digestで+1、各versionを1件の保存された変更が作る。各overrideは、それを支える変更が決めたsurfaceとsetting（その変更の `affected_policy_surface` と `after_setting`）そのものである。保存された各変更記録は、それが名指すReceipt（Policy Reviewのkindで、stage `project-policy-change:persist-profile` を認可し、その変更記録のRunとCandidateを名指すもの）に裏付けられる（ownerはsealしたgeneration 5とReceiptを変更記録より前にcommitする）。どの変更も作っていないProfile（`project-policy-change` の外での直接編集）も、Receiptに裏付けられない変更記録（他のProjectからの写しや手書き）に支えられたProfileも、新しいRunのEffective Policyにならず `review_p6_lineage_invalid` で止まり（policy maintenance / reconcile）、validationのProblemになる。

### compatibility（R6-2）

Profileは、それが書かれた時のbaseline（そのProfileを作った変更記録が束ねる完全なbaseline record）とcurrent baselineの、policy意味の射影（surfaceのid・class・範囲・Global setting、meta-rules、loader semantics、Global policy version）が正確に等しい時だけ適用する。Workline rootの文言だけの変更はcompatibleのままで、意味の変更はRB7のversioned total adapterが証明するまでincompatibleである。推測・merge・overrideの黙った削除はしない。incompatibleなProfileは新しいRunを始めず（`review_p6_profile_incompatible`）、validation Problemになる。open Runは自分が凍結したpolicyで続く。

### Effective Policy

P4-capableなFormal Review（planning、START、Policy Review）の新しい最初のRunは、すべてP6-capableで（Orchestrator ruling R6-1）、policy `review-v1-p6-policy-v1` を束ね、GlobalPolicyBaseline + Profile（または明示の不在）を解決して正規化したEffective Policyを自分のrequestに凍結する。effective_policy_hashはそのrecordのdigestである。open Runは途中でpolicyを変えず、後継とHuman decisionの新しいRunはcycleの最初のRunのpolicyを保つ。既存のP4-only / P5のRunは自分の保存したidentityでだけ読み、upgradeしない。P6 policyはP5の規則とhistory contractをそのまま持つ。

凍結したEffective Policyがこのbuildで読めないP6 requestは、P6のまま `review_p6_effective_policy_unreadable` でfail closedし、別のfamilyのrequestやv1としては決して読まない。Policy Reviewのcontract `review-v1-policy-change-p6-v1` はP6 policyの下でだけ束ねられる。

### holdout（lightening）

設定を下げる（lightening）変更は、変更前の強い挙動を独立のall_relevant holdoutとして凍結する。holdoutはmeasurementであってauthorityではない。

- `required_slots` 3 -> 2: 外した3つ目のdiscovery slotをholdout slotとしてG1で受理し、G2でsettleし、G4でadjudicateする（selectorの `holdout_discovery`）。必要なholdout actorが無ければlaunch前に `review_p6_holdout_unbound` で拒否する。holdoutを選ぶ実験が無いRunへのholdoutは `review_p6_holdout_not_applicable`。
- `extra_scope_steps` 2 -> 1: 外した広い再検証levelのcheckを、Repair Resultより前に修理のverificationに含める。無ければ `review_p6_holdout_unsettled`、失敗すれば `review_p6_holdout_failed` でblockする。結果は既存の `reverification.completed` に残る。

terminalより前に分かったholdoutの結果: Problem HIGH / MIDは現在のblocking obligation、Problem LOWはH-1 / H-4、Improvementは非blocking、要件の曖昧さはHUMAN、Findingなしはmeasurement evidenceだけ。terminal完了の後に分かった結果はP5の下流 / 履歴evidenceになり、古いlifecycleを書き換えない。

### Policy Review（`project-policy-change-v1`）

Policy Changeは正規化したPolicyChangeCandidate（命令的なpatchではない）として、kind `project-policy-change-v1`、target `project-policy`、stage `project-policy-change:persist-profile`、contract `review-v1-policy-change-p6-v1` でreviewする。P4のG1-G5を使い、Repair Batchの分岐は無い: blocking Problemは G4でterminal（`not_authorized`、Receipt無し）、HUMANはG4で `human_wait`、修正した提案は新しいCandidateである。

変更前規則: Policy Reviewは変更前のEffective Policyと固定meta-rulesでreviewし、提案された後の状態は、自分を認可するreviewのreviewerやcheckを減らせない。discovery actorは変更前のEffective Policyに対して、freezeの時だけでなく、G1とdiscoveryのlaunchの各stepで（再開のたびに）検査する。

固定の機械的meta-verifierは、reviewerが見落としても次を検査する: evidenceの出所（P5 recordのdigest）、Relevant Opportunityの基礎（異なるReview Runで、そのsurfaceを実際に使ったもの。同じRunの2つのrefやrelationとその対象は1つ）、surface / class / 範囲、正しさ・権限の変更が無いこと、lighteningのholdout、overlap、environmentの帰属、正確なrollback単位、before / afterの正規化された意味、requestの再導出とそのdigest。恒久的なstrengthen / lighten / adjustは2つ以上のRelevant Opportunityを要する（`review_p6_single_event`）。temporary_guardは強める向きだけで、1つの深刻な支持された逃し（supportedな downstream_escape / repair_induced relation、またはsupportedな HIGH / MID Problem）から作れ、再評価 / 期限の基準を持つ。

### 永続化

G5のReceiptの後、immutableな変更記録（`.workline/review/policy/changes/<rpc_...>.yaml`、Candidateがreviewされたbaseline recordを完全に束ねる）とProfileのCASを1つのstageに記録し、Kp（その2 pathだけの `base_exact` policy commit）、C-2(Kp)（正確な親 / branch / delta、reviewした後のProfile bytes、canonical loaderでの意味の往復、Receiptがcurrent）、push先があればKpの公開、Policy Consumption version 3とP5のconsumed Run summary、Km、C-2(Km)、Kmの公開、の順で進む。証明の前にpushせず、forceも履歴の書き換えもしない。remoteの無いProjectは同じlocalの証明とcommit境界を保つ。rollbackは新しい高いProfile versionであり、Gitのreset / revertではない。

runtimeを失った後（ORCH-RB6-1）: frozenなCandidateを持つpending mutationが無い呼び出しは、何かを予約する前に、canonical recovery discovery（`review_recovery_incomplete` / `review_recovery_ambiguous` を含む同じ仕組み）で、Policy Review kindと同じoperation identity（`project-policy-change:<request digest>`）のRunをHEADの履歴とworking treeから集め、次の順に分類する: Policy Reviewのcontractでない → reconcile。変更記録がHEADの履歴で追加されたかHEADの木 / working treeにある（登録の行b）→ そのRun自身のReceiptでその変更を名指すcommit済みのPolicy Consumption（HEADの木にあるか、HEADの履歴が追加したもの。working treeにしか無いConsumptionは数えない）があれば `consumed`、無ければ `review_p6_run_unrecovered`（同じ変更記録を二度と追加しない。revertはそれをreconcileしない）。G2のdeclined / AUTHORIZATION_READYでもHUMAN_WAITでもないG4（blocking）→ terminalの `not_authorized`（同じrequestは新しいRun）。G4のHUMAN_WAITはset asideしない（CP R8）: それは同じcanonicalなHUMAN_WAIT Runのままで、同じrequestは、ownerがそこで完了した後でもruntimeを失った後でも、canonical discoveryでそのRunを見つけ、同じpolicy change ID・Review IDのまま `human_wait` を返す。そのRunのために何も書かず、Receipt・Consumptionを予約せず、新しいRunもset asideも作らず、Humanの答えを推測しない（policy kindにはHuman決定での再開入力が無く、Policy Review Runをset asideする既存の経路も無い。Human recovery dispositionはWork Review Runだけを対象とする。P6のHuman APIは作らない）。今のstateや呼び出しのactorに対して判断し直さないので（P4のplanning / WorkがG4 HUMAN_WAITのRunをcurrencyから外すのと同じ。何もlaunchしない）、before-stateが動いていても、discovery actorの数が凍結したpolicyに足りなくても、同じ `human_wait` を返す。別のrequest（変えた提案）は自分のCandidateとRunであり、HUMAN_WAITのRunを名指さず、set asideもしない。再構成できない（Policy Reviewのkind / target、discovery → adjudication → sealの形でrepair branchもgeneration 6も無いこと、受理したtaskのprovenance、sealしたgeneration 5とReceiptの束縛）→ `review_recovery_incomplete`。それ以外は回復可能で、何かを束ねる前に、Candidateがこのrequestのものであること、凍結したEffective PolicyがG1とCandidateの束ねたものであること、正確なbefore-state（Profile・Effective Policy・Global baseline）が今も成り立つこと、固定meta-verifierが今もCandidateを受け入れることを証明し直す。before-stateが動いていれば `review_p6_before_state_conflict` で何も予約もpendingも残さずに止まり（Runがcanonical（generation 1以降）なら同じrequestは古い提案として同じように止まる。generation 1より前に放棄されたmutationには正本のRunが無いので、同じrequestの次の呼び出しは動いたstateの上の新しいCandidateになる。変えた提案は新しいCandidate）、どのstepでもbefore-stateの衝突は、effectの無いowner mutationを放棄して、Profileのscopeを持つpending mutationを残さない。回復可能なRunが1つなら、その正本のpolicy change ID・Run・task・sealしたReceiptを束ねて（新しく発番せず。同じ束縛を既に保存したcrash後の再試行はそのまま続く）そこから再開し、無ければ新しいRunを始める。自分のReceiptのcommit済みConsumptionの無い変更記録をHEADの木かworking treeが持てば（Kp / Kmのidentityが保存されなかった。ConsumptionとRun summaryを書いた後Kmの前に失われた場合も同じ）、Git履歴から推測せず、どのrequestでも新しいPolicy Changeを始めず、`review_p6_run_unrecovered` でreconcile requiredとして止まる（手動reconcileの境界）。publication barrierのfast-path readは1回の読み取りで `.workline/review/candidate-snapshots/`・`.workline/review/policy/changes/`・`.workline/review/policy/project-profile.yaml` を見るので、Candidate snapshotに一度も触れていない履歴でも変更記録かProfileを持てば証明に進む。履歴が一度でも変更記録かProfileを追加したなら、pushするcommitが持つProfile（または不在）と変更記録は、正本のProfile lineageとReceiptの裏付け（上の規則そのもの、commit済みobjectだけから）を満たさなければならない。Kpを伴わないProfileの書き換え・削除や、Profileの無い変更記録は公開しない。stranded Kpのrevertは両方を戻すので公開できる。barrierは、policy commit（Kp）を履歴に持つcommitのpushを、どのoperationのものでも、そのKpが正本のobjectだけから証明できる時（PK1-PK7: 1つの追加commitと1つの親、変更記録とProfileだけのdelta、変更記録が名指すCandidateの変更記録そのもの、reviewした後のProfile bytes、親のbefore Profile、親でPolicy Reviewのkind / target / contract・provenance・generation 5とReceiptの束縛を持つsealしたRun、履歴に無効化もSupersessionも無くKpに自分のConsumptionが無いこと）だけ通し、そのReceiptのConsumptionをpushするcommitが持つか、その履歴のどれかのcommitが追加したなら（後のcommitが消したりrevertしたりしたものも含む）、それとKmも正本のobjectだけから証明する（PK8-PK9: それは自分のpathにある1つのv3 Policy Consumptionで、ReceiptとRunを束ね、変更・Kp・親・before / afterのProfileのversionとdigest・baseline digest・正規化projection hash・policy delta digestの主張をKpと親から計算し直して一致し、他のPolicy Consumptionが同じ変更やKpを名指さない。Kmはその1つの追加commitで、Kpのcleanな子孫の上にRun summaryとConsumptionだけを加え、pushするcommitはそのpathにKmのConsumptionを持つか何も持たない）。Consumptionがどこにも無い証明済みのKpは、そのownerが§30.20の順で公開するのと同じく、Kpだけとして公開される。

### evaluation

観察の評価はevidenceであり、Profileを書き換えない（`.workline/review/policy/evaluations/<rpe_...>.yaml`、同じownerのimmutable createと通常のGit finalization）。

- `retain`: 観察を終える（Profileの `active_experiment_refs` から、そのrefを有効なactive集合から外す）。その変更の凍結した `minimum_opportunities` 個以上の異なるRelevant Opportunity（そのsurfaceを使い、凍結したEffective Policyがその変更をactiveとして挙げるRun。lighteningならholdoutが効いていたRun）がevidenceで証明される時だけ受理する。temporary_guardは評価で恒久化しない: それを置き換えるreviewされたstrengthen Candidate（単一イベントの下限を満たす）が恒久化し、rollbackが終わらせる。根拠の無い保存されたretainは何も終わらせず、validation Problemになる。
- `adjust` / `rollback`: 評価だけで、Profileを変えるには新しいreviewされたCandidateが要る。rollbackは、そのsurfaceを今governしているactiveな変更を正確に戻す。
- `inconclusive`: 成功ではない。凍結した契約が安全に許す時だけ観察を続ける。

overlap: 同じsurfaceの2つの実験は `known_overlap`、v1の2つのsurfaceは `proven_disjoint`。並行に観察できるのは `proven_disjoint` だけで、他は直列化するか、自分のsurfaceの実験を明示にsupersedeする（別のsurfaceの実験はsupersedeしない。lighteningの実験を、そのholdoutが測る挙動より下のままで終わらせない）。environment: 観察窓の中で重要なidentity（baseline、reviewer、adapter、toolchain、measurement contract、dependency）が変わったら、窓を分けるか、保存されたevidenceである正の無関係の証明を示すか、`inconclusive` にする。時系列は因果ではない。

### BL-055 shadow authority（advisory）

Project-localのartifactがWorkline authorityを複製・置換していないかの診断（none / suspected / confirmed）は、read-onlyの `status` のpolicy sectionと `validate-project` の表示がadvisoryとして示す。validate_projectのProblemにならず、PASS / FAILを変えず、何も編集・削除・移行しない。

### 停止規則（P6）

P6のSTOP code: `review_p6_surface_unknown`、`review_p6_surface_non_adaptive`、`review_p6_setting_invalid`、`review_p6_surface_reclassified`、`review_p6_profile_invalid`、`review_p6_profile_incompatible`、`review_p6_lineage_invalid`、`review_p6_baseline_unavailable`、`review_p6_candidate_invalid`、`review_p6_single_event`、`review_p6_duplicate_evidence`、`review_p6_evidence_invalid`、`review_p6_direction_invalid`、`review_p6_lightening_unmeasured`、`review_p6_guard_invalid`、`review_p6_overlap_unresolved`、`review_p6_forbidden_change`、`review_p6_before_state_conflict`、`review_p6_discovery_slots_unmet`、`review_p6_holdout_unbound`、`review_p6_holdout_not_applicable`、`review_p6_holdout_unsettled`、`review_p6_holdout_failed`、`review_p6_evaluation_invalid`、`review_p6_environment_unattributed`、`review_p6_human_wait`、`review_p6_not_authorized`、`review_p6_policy_review_invalid`。validation / 拒否のcode: `review_p6_effective_policy_unreadable`。P6のreconcile reason: `review_p6_profile_before_mismatch`、`review_p6_persisted_mismatch`、`review_p6_chain_invalid`、`review_p6_publication_invalid`、`review_p6_record_conflict`、`review_p6_run_unrecovered`。

## P6 Review Policy

P6-capableなfamily policyのidentity recordは次の静的recordそのものである（Workline実装の定数 `workline.review.p4.P6_POLICY_RECORD` と一致しなければならない）。P6 RunのEffective Policyはこのrecordのdigestを束ねる、Runが凍結した正規化record（GlobalPolicyBaseline + Profileまたは明示の不在）である。

```yaml
adaptive:
  extra_scope_steps_rule: "post-repair reverification at the repair's impact level widened by N levels, capped at FOUNDATION, never below the P4 minimum"
  holdout_rule: "an active lightening experiment freezes the pre-change stronger behaviour as an all_relevant holdout: discovery holdout slots accepted at G1, settled at G2 and adjudicated at G4; reverification holdout checks present in the repair verification before the Repair Result; a failed holdout check blocks; without its holdout channel the Run is refused"
  policy_review_rule: "project-policy-change-v1 is reviewed under the pre-change Effective Policy and the fixed meta-rules, G1-G5, no Repair Batch branch; blocking or HUMAN issues no Receipt"
  registry:
    - review.discovery.required_slots
    - review.reverification.extra_scope_steps
  registry_rule: "exactly the two fixed v1 surfaces; an unknown surface is rejected; the absolute non-adaptive surface is rejected mechanically; a Profile never reclassifies or invents a surface"
  required_slots_rule: "N required discovery slots bound to N distinct reviewer identity/version pairs, all settled at G2 before adjudication"
  resolution_rule: "a NEW first Run of a P4-capable Formal Review resolves GlobalPolicyBaseline + the canonical Project Profile or its explicit absence and freezes the normalized Effective Policy in its requests; an open Run never changes policy; an incompatible Profile starts no new Run"
adjudication:
  contract: review-v1-p4-adjudication-v1
  instruction: review-v1-p5-adjudication-instruction-v1
  merge_rule: "same substantive issue, same semantic responsibility, one repair closes all; uncertain stays separate"
  order:
    - unsupported
    - HUMAN
    - Problem
    - Improvement
    - dismissed_non_actionable
  prior_history_rule: "a deterministic complete set of validated P5 Run / Finding / Repair history references of the same review kind and target, by digest; no chat memory, transcript or Candidate copy"
  relation_rule: "structured cross-run relation claims (type, source Finding, prior target, surface, status, evidence digests, public-safe rationale); only supported is confirmed"
  severity_rule: "the strongest severity the adjudication supports; the reviewer's severity is input only"
  slot: p4-adjudicator
  task_kind: p4-adjudication-v1
blocking_rule: "Problem HIGH or MID, and every C_REPAIR_INDUCED Problem, is a blocking current-cycle obligation"
categories:
  - Problem
  - Improvement
convergence_rule: "unresolved blocking review obligations = 0 and required coverage and Evidence are current"
discovery:
  history: "fresh: no prior Finding or Repair history"
  instruction: review-v1-p4-discovery-instruction-v1
  report_rule: H-3 public-safe structured claims plus an explicit coverage declaration
  slot_rule: "one required task per viewpoint the P4 selector binds; at least one"
  task_kind: p4-discovery-v1
dispositions:
  - repair_required
  - repaired_current_cycle
  - retained_history_only
  - future_work_candidate
  - no_action_after_adjudication
evidence_reuse_rule: "positive proof under the dependency vocabulary only; a report, adjudication or Receipt is never reused"
history:
  authority_rule: "history is a validated projection and reference layer, never lifecycle truth, a scheduler or a Work generator"
  contract: review-v1-history-v1
  family_rule: "a cycle keeps the policy and history contract of its first Run; an existing Run is read only from its own stored identity and is never upgraded"
  finding_rule: "one Finding summary per normalized Finding, in the G4 that persists the adjudication"
  human_decision_rule: "one Human Decision Evidence record per affected HUMAN_WAIT Run, in the successor G1 before any external launch; never requirement authority"
  relation_rule: accepted relations are immutable new G4 facts and never rewrite an endpoint
  repair_rule: "the Repair summary and the repaired Run summary, in the G6 that persists the Repair Result"
  sanitation_rule: "structured public-safe fields only: no chain-of-thought, transcript, secret, free map or Candidate payload"
  summary_rule: "one immutable Run summary, written in the transition that makes the Run's durable disposition final; the two reserved dispositions no transition proves are never written"
human_rule: "a required requirement decision is HUMAN_WAIT at generation 4; no repair guesses it"
impact_classes:
  - LOCAL
  - SHARED
  - CONTRACT
  - FOUNDATION
improvement_rule: Improvement of any severity is non-blocking
last_generation: 6
low_rule: Problem LOW is non-blocking only while the current completion objective still holds
outcomes:
  - unsupported
  - HUMAN
  - Problem
  - Improvement
  - dismissed_non_actionable
policy_id: review-v1-p6-policy-v1
relations:
  - A_NEW
  - B_RECURRENCE
  - C_REPAIR_INDUCED
repair:
  batch_rule: one Repair Batch per Candidate generation holding every decidable blocking Problem
  instruction: review-v1-p4-repair-instruction-v1
  proposal_rule: "a complete repaired Candidate proposal; the owner alone adopts it"
  slot: p4-repair
  task_kind: p4-repair-v1
reverification_minimums:
  CONTRACT:
    - adjacent_eligibility
    - contract_roundtrip
    - failure_interruption_resume
    - writers_readers
  FOUNDATION:
    - broad_integration
    - full_suite
  LOCAL:
    - direct_consumers
    - focused_tests
  SHARED:
    - focused_tests
    - integration_checks
    - representative_callers
review_contracts:
  - review-v1-planning-p4-v1
  - review-v1-work-p4-v1
  - review-v1-policy-change-p6-v1
schema: review-p6-policy
seal_generation: 5
severities:
  - HIGH
  - MID
  - LOW
strategy_rule: two consecutive supported B/C failures on one semantic surface require STRATEGY_CHANGE
version: 1
work_creation_rule: LOW and Improvement never create Work automatically
```
