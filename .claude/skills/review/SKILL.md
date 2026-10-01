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

片側だけの状態（eventだけ、Consumptionだけ）は、pendingのreview-v1 Work STARTのmutationが、その2つを1つのdurableなterminal stageとして記録しており、欠けている方をそのmutationのreplayがまだ終えられる間だけ正当である。eventだけなら、記録したeventがそのものとして適用済みで、event logがそのmutationの書いたとおりのままであり、Consumptionのcreateが未適用であること。Consumptionだけなら、そのmutationが自分で書いたbytesのConsumptionがあり、event logがそのmutationの記録した、stageの最初のeventを書く直前の内容のままであること。fileの内容から意図を推測しない。それ以外のeventだけ・Consumptionだけ・重複は不正で、`reconcile required` として人が直す。Projectのvalidationはこれらを `review_activation_prefix_mismatch` / `review_completion_marker_invalid` / `review_completion_marker_contradiction` / `review_completion_unconsumed` / `review_consumption_unbound` として報告する。

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

**proof**: `review-v1-work-proof-v1` のC-2は、immutableな入力に対する再実行可能な証明であり、保存されたverdictではない。C-2(K1)はW1〜W12を、C-2(K2)はT1〜T12を、committed objectだけから証明する（K1 / K2がこのmutation自身のcommitであること、親とRAW lineage、K1のdeltaがCandidateの変化するentryちょうどであること、K2のdeltaがevent logとConsumptionちょうどであること、event logがちょうど2件（`work_target_removed`、`work_completed`）を加えること、Consumptionの内容と束縛、ReceiptとConsumptionの一意性とtotality、許可がまだcurrentであること、結果の束縛（`result_commit` はK1、`empty` は結果deltaなし）など）。3つのprojectionの物理的な置き場所は、ReviewedArtifactProjectionの変化がK1だけ、AuthorizedTransitionProjectionとConsumptionがK2だけである。通常のK2はmetadataだけを加えるcommitで、それ自身をReviewしない（再帰の打ち切り。Class AのK2とは区別し、Class Aはここで扱わない）。proof noteはrecoveryのためのpointerで、証明の結果ではない。完了したC-2はdurableなcheckpointであって永久の正しさではなく、各境界で現在の正しさを導き直し、後のcanonicalな事実は通った証明をstaleにする。

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
