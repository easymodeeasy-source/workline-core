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

## P1時点の適用範囲

現時点でReviewはWork completionに自動適用されない。STARTの通常のWork completion semanticsはreview-v1へ切り替わっておらず、`work_completed` はこれまでどおり判定される。

```text
Work terminal Review gating: NOT ACTIVATED
```

P1で成立しているのは、Review Coreの永続化・回復・識別の土台と、この責務境界である。Roadmap / Phase entryへの結線はP2、Work terminal gatingとresult commitのproof / push分割はP3が扱う。

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
