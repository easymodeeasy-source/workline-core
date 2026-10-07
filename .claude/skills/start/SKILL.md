---
name: start
description: Execute an already-registered Workline Work and drive it to the requested execution boundary. Use ONLY inside an established Workline Project (one that already has .workline/project.yaml) when a registered Workline Work must actually be performed, including dependency checks, target/lifecycle handling, derived fix Work creation through CREATE, integration or human-confirmation execution, Git persistence, and same-Phase continuation in explicit outer mode. Not for starting a server, script, build, task, or any generic "start" request.
---

# START

指定された既存Workを実行し、その成立条件を実現し、必要な派生・確認・Git保存を含めて、指定された実行モードの終端まで進める。

## Input

必須:

- stable Work ID
- mode

mode:

```text
single-work
outer
```

自然言語の雰囲気からmodeを推測しない。

## Mode

### single-work

指定Workと、そのWork成立に必要なderived fix / dependency / structural human_confirmationまでを扱う。Phase全体・Project全体を自動実行しない。

### outer

Phase Workなら同一Phaseがcompleteになるかstop条件に到達するまで進める。次Phaseへ越境しない。

Standalone Workのouterはstandalone scope内だけ。

## Start flow

```text
Project context照合（foreignならSTOP）
↓
Workline implementation照合（configured rootのimplementationでなければSTOP）
↓
Project execution lock取得
↓
stable Work resolve
↓
generated state確認
↓
dependency確認
↓
Related / common rules読取
↓
Git / pending mutation precheck
↓
target / lifecycle処理
↓
Work実行
↓
必要ならCREATE派生 / fix Work
↓
integration / confirmation処理
↓
completion precheck
↓
Git保存
↓
terminal finalization
↓
mode=outerなら同一Phase内の次startable Workを再計算
↓
return時にlock解放
```

`rules/git` のProject contextに従い、START（resumeを含む）は対象Projectのcontextから実行する。invocation Project contextが対象Projectと一致しなければ、lockを取得する前に `foreign_project_mutation` でSTOPし、何も書かない。

STARTにはCLIが無い。`rules/git` のWorkline implementationに従い、対象Projectの中でisolated Python processを開始し、同じprocessで `<R>/run-workline.py` の `activate()` を実行してからSTARTのPython APIをimportする（R = configured Workline root）。executorもそのprocessの中で動く。Project contextの照合の後、実行中のimplementationがconfigured rootのものでなければ、lockを取得する前に `workline_implementation_mismatch` / `workline_implementation_unverified` でSTOPし、何も書かない。PYTHONPATHの手組みや別のimplementationへfallbackしない。

`rules/git` のProject execution lockに従う。Work state・dependency・pending mutation・push destination・dirty stateはlock取得後に読み、lock取得前に読んだstateをmutation判断へ使わない。executorもlockの内側で実行される。他processが同じProjectで実行中なら待たずに `project_operation_busy` でSTOPし、何も書かない。executorの中から同じProjectの別top-level Workline operationを開始しない（`project_operation_nested`）。

`rules/information-tracing` に従い、Related / common rules読取のtargetは実行前に一意解決できなければならない。must_read、条件が現在成立しているconditional_must_read、obey chainのtargetが解決できない場合は、target / lifecycle処理・executor実行・Git書込みより前に `related_target_missing` でSTOPする。「たぶん不要」「古いfileだろう」と推測して無視せず、filename / directory / mtime / 意味類似で代替も探さない。自動修復もしない。

terminal Work（completed / cancelled / plan_excluded）のRelatedは当時のhistorical evidenceであり、現在のread obligationではない。targetが後から正式に削除されても、その事実だけでProject structureをinvalidとしない。

他のstarted（in_progress / held）non-terminal Workが現在読む必要のあるtargetのうち、今回の実行で壊された場合に元へ戻せないもの（directory / link / 読めないfile等）があるときは、lifecycle eventやexecutorより前に `related_target_unprotectable` でSTOPする。壊してから報告する順序にしない。

## Generated Work lifecycle

Unstarted開始:

```text
work_started
work_target_added
```

既にin_progressだがtargetなし:

```text
work_target_added
```

held resume:

```text
work_resumed
work_target_added
```

通常完了terminal:

```text
work_target_removed
work_completed
```

terminal:

```text
work_completed
work_cancelled
plan_excluded
```

は相互排他的。同一Workへ複数種類terminal eventをappendしない。terminal後に通常lifecycle eventを追加しない。

`plan_excluded` は未開始のfuture-plan Workにだけ使う。開始済みWorkをcurrent planから外す場合はcancelとして扱う。

state fieldをWork本体へ保存しない。

## Question wait / temporary move / true hold

質問・判断待ち:

- Workはin_progress
- target原則維持
- lifecycle eventなし
- ad hoc質問のためhuman_confirmation Workを作らない
- START invocationはProject execution lockを解放して戻り、START mutationはpendingのまま残る
- 再開は新しいSTART invocationがlockを取得してからpending mutationをresumeする

一時的に別Workへ移る:

- 元Workはin_progress
- 必要ならtargetだけremove
- CREATE / START branch Work
- relationを正式登録
- return前にdependency再確認

本当に中断:

```text
work_target_removed
work_held
```

holdのlifecycle eventは、それを決定したbranchと、executorが返した理由を同じdurable writeでrecordへ記録する（`rules/git` のCommit / push）。理由はSTARTの呼び出し元への言葉でありProject正本の内容にはならないので、recordが同じ種類の同じ値として保てない理由（小数、object等）は記録しないだけで、holdを拒否しない。

hold eventを記録した後、それを含むcommitを記録する前、またはそのcommit / pushの前に中断・STOPした場合、同じWork・同じmodeのSTART再実行は、現在stateからlifecycleを決め直す前にrecordを読む。holdのeventは `work_completed` / `work_cancelled` と違ってterminalではなく、適用済みのstateは「後のSTARTが正当にresumeできるheld Work」に見えるので、recordを読まない再実行は自分が今記録したholdをresumeし直し、`work_resumed` / `work_target_added` を追加してexecutorを呼び直し、返ってきたものを新しい決定として記録してしまう。stage名は毎回新しく採番されるため重複防止も働かない。

recordがそのholdをこのSTART自身のものと示せる場合だけ続ける: 対象Workのlifecycle stageとして次の番号で記録され、holdの記録する2 event（`work_target_removed` / `work_held`）をちょうど予約済みIDで持ち、`work_held` のeffectに理由以外を載せておらず、single-workでは指定Workであり、holdより前に記録した決定はそれぞれ自分のcommitで確定済みであり、holdの後に記録されたstageがそのholdのcommitだけであり、そのcommitが未記録ならHEADのevent logがまだそのeventを持たないこと。続ける場合は、executorを再実行せず、eventを追加せず、新しいstageを作らず、他のWorkを選ばず、同じmutationで残っているcommit / pushだけを行い、記録した理由とともに `held` を返す。outerでもholdの後に次のWorkを選ばない（中断が無い場合と同じ）。

示せない場合（複数の `work_held`、STARTが記録しない形のstage・event・予約ID・理由、holdの後の別stage、このmutationが記録していないcommitによってHEADのevent logが既にそのeventを持つ場合）は、何もreplayせずrecordを変更しないまま `reconcile_required` でSTOPする。理由を記録していない旧implementationのrecordは、holdが決定したものはevent自体なので同じように続け、`held` を理由なしで返す。この継続もholdを決定したbranchの上でだけ行う（`rules/git` のCommit / push）。開始前からの未commit変更でGit段階が止まるrecordは、従来どおり同じ `dirty_overlap` で止まり、再実行はeffect・event・executor呼び出しのどれも増やさない。

holdを決定する前の中断（executorがまだholdを返しておらず、Work開始のlifecycleだけをrecordが持つ場合）は何も決定していないので、従来どおりexecutorから決め直す。question waitのresumeもこれに当たる。

## Work cancel

開始済みWorkを正式に不要と判断してcurrent planから外す場合はSTARTがcancel operation ownerになる。

```text
必要なら work_target_removed
↓
work_cancelled
↓
影響するWork間future relation / integration prerequisiteをreplan
↓
structural validation
↓
START-owned finalization commit / remoteありならpush
```

cancelはcompletedへの代替ではない。Workのdesired state、origin、`phase_id`、historical `derived` を書き換えない。

cancelled Workを前提としていた `requires_completion` は満たされた扱いにしない。dependencyを正式変更するか代替Workを作る。replan不能ならcancel operationを成功扱いにせずSTOPする。

未開始Phase Workをfuture planから外す `plan_excluded` はRoadmapのfuture-plan operationが担当する。未開始Standalone WorkはSTARTがstandalone scope operationとして `plan_excluded` を所有する。

Standalone Workのplan exclusionの途中失敗も、Roadmapのplan exclusionと同じ規則で同じmutationをresumeする（`skills/roadmap` のMutation / Git）: replanを含む決定内容を最初のID予約より前にrequestとしてinvocationへ記録し、記録済みrequestが一致して、recordがそのrequest自身のものと示せる時だけ、そのmutationが適用したeffectを除いたstateで判定し、残りをreplayの前に検査して最後まで進める。requestを記録していない旧実装のrecord、別request、書き換えたrecordは `reconcile_required` でSTOPし、recordを変更しない。branchとcommitの扱いは `rules/git` のCommit / pushに従う。このmutationのinvocationはoperation `start-plan-exclude` と対象Workで、START実行（Work・mode）のinvocationを共有しないので、Terminal finalizationのresumeがplan exclusionのrecordを読むことも、plan exclusionがSTARTのrecordを自分のrecordとして読むこともない。

## Derived / fix Work

実行中に新Workが必要と判断した場合、STARTがWork意味とrelationを決め、CREATEへ登録依頼する。

```text
START = 意味owner
CREATE = 登録
Mutation Controller = physical writer
START = Git operation owner
```

executorが派生を返した時、STARTはその派生の決定（executorが返した内容）を、それを登録するstageより前にrecordへ記録する。中断やquestion waitの後の同じWork・同じmodeのSTART再実行は、そのcycleをexecutorから決め直す前にrecordを読み、記録済みの派生をこのSTART自身のものと示せる場合だけ、その決定で続ける: executorを呼ばず、記録済みのregistration stageをそのまま使い、Work・派生detail・relationを二度登録しない。示せない場合はrecordを変更しないまま `reconcile_required` で停止する。決定を記録する前の中断と、recordが保てない決定（記録しないだけで派生自体は拒否しない）は、従来どおりexecutorから決め直す。

示せる条件: 各Workの派生が `<Work>:derive:<n>` として決定順に記録され、未記録はその末尾1件までであること（決定を記録した直後の中断）。記録済みのstageが決定したbranchを持ち、派生と次の派生の間に記録されたstageがその派生のcommitだけであること。single-workでは指定Workの派生だけであること。targetを外した派生がそのWorkの派生の最後であること。記録済みstageの内容がその決定の作る登録と完全一致すること（`rules/git` の記録済みstageの判定。displayはstage自身が記録した値）。

1回のattemptが決める派生は1件で、targetを外さない派生の後は同じWorkの次のattemptが続く（1つのcycleが複数の派生を決めることがある）。targetを外す派生（Question wait / temporary move / human_confirmation NG参照）はそのWorkのcycleを終わらせる決定なので、target削除まで記録済みなら残りのGit段階（commit / push）だけを行って `moved` を返す: executorを呼ばず、Workを開き直さず、lifecycle eventもstageも追加しない。commitのmessageはその決定のもの（派生なら `chore(workline): branch from <display>`、NGなら `chore(workline): <display> NG; fix planned`）。`<display>` はその派生を決定した時のWorkのdisplayで、決定と一緒にrecordへ記録し、記録済みcommitのmessageの確認にも、まだ作っていないcommitのmessageにもその値を使う。displayはidentityではなく人が変更できる表示用の値なので、現在のWork fileのdisplayから作り直さない。displayを記録していない旧recordは、そのkindのmessageの形（`<display>` の前後の固定文字列が一致し、その間が空でないこと）で示す。outerではその後に次のWorkを選ぶ（中断が無い場合と同じ）。同じWorkが後で新しいcycleとして開かれた場合（NG後の再確認等）、そのcycleは自分の派生を決める。

派生は、そのWork自身への `requires_completion` を登録することがある（NGは再integrationから元のconfirmationへ必ず登録し、それ以外の派生は、targetを外すかどうかにかかわらず、executorが決めた場合に登録する）。これはそのWorkを新しいcycleとして開く時（targetを外した後に戻る際等）と完了する時に確認するdependencyで、中断の無いcycleは、派生を登録してから次のattemptまで（targetを外す派生ならtarget削除まで）の間にdependencyを確認しない。そのため、question waitや中断の後に同じcycleを続ける再実行は、Workを実行する前のdependency確認で、そのcycle自身の派生が登録したそのWorkへの `requires_completion` だけを未充足として数えず、記録済みの派生を登録し直して次のattempt（targetを外す派生ならtarget削除）から続ける。数えないのは、このmutationの再実行で記録済みの派生を示せ（上の条件）、Workがそのcycleのtargetを持ったままで、そのcycleを開いたlifecycle stageの直後からrecordが持つstageが、Git stage（commit / push）を除けばそのcycleの派生の登録stageを決定順に並べたものだけであり（target削除・hold・cancel・完了のlifecycle、成果、他の登録を含まない。Git stageは、各登録を確定するcommit、再実行が記録したcommit等で、何も決定しない）、各登録stageがその決定の作る登録と完全一致し（予約したrelation IDとpayloadを含む）、Projectがその関係を登録どおりに持つ場合の、その関係だけである。関係そのものは削除も変更もせず、満たされた扱いにもしない: そのWorkの完了は従来どおりそのdependencyが満たされるまで拒否され（Work completion precheck）、target削除でcycleが終わった後にそのWorkを開く実行（outerの続き、新しいSTART）は従来どおり確認して停止する。元からあるdependency、別の決定や他者が加えたもの、決定やcycleを示せないrecordのもの、ここで開くcycleのものは従来どおり確認して停止し、登録と一致しないstageはcycleの何も実行せず `reconcile_required` で停止する。

CREATEが登録前の構造検査で拒否した派生Work / fix Work（`skills/create` 参照）は、Work file・relation・Relatedのいずれも書かれない。拒否までにSTARTがそのWorkへ記録したlifecycle event（`work_started` / `work_target_added` 等）は、executor実行中の他のSTOPと同じくSTART mutationに残り、同じWork・同じmodeのSTARTでresumeする。

## Integration ownership

実行中の追加Work / 再integrationの意味ownerはSTART。

CREATEはintegrationを自動生成しない。

以下の `unfinished integration` は `rules/ai-decision` の定義で数える。

### unfinished integrationが1件

新Workがそのintegration前に完了すべきなら:

```text
new Work
--requires_completion-->
existing integration
```

をSTARTが決めCREATEへ渡す。

### unfinished integrationが0件で再統合が必要

STARTが新integrationと確認対象Work集合を決め、CREATEへ渡す。

完了済みintegrationをreopenしない。

### unfinished integrationが2件以上

構造異常。新integrationを作らずSTOP。

## human_confirmation NG

例:

```text
I1 completed
↓
H1 in_progress
↓ NG
F1 fix
↓
I2 integration
↓
H1へ戻る
```

STARTが:

- F1の必要性・成立状態を決めCREATE
- I2の必要性・確認対象を決めCREATE
- `F1 / 必要なactive Work -> I2` dependencyを決める
- 必要なら `I2 -> H1` requires_completionを決める

CREATEは登録だけ。

H1はNG時点でcompletedにしない。targetを外してfixへ移り、戻る際に同じH1を再開する。新しいconfirmationを意味なく増殖させない。

## Phase effective Work set

Phase completionやouter continuationで使うcurrent-plan Work集合は新しい台帳へ保存せず、既存正本から生成する。

```text
effective current-plan Work
=
phase_id = 対象Phase
AND generated terminal state != cancelled
AND generated terminal state != plan_excluded
```

`cancelled` / `plan_excluded` Workはcompletedへ変換されるのではなく、effective current-plan setの外になる。

ただしWorkをcancel / plan_excludeしただけでPhase構造が自動成立するわけではない。cancel / plan exclusionを決めたoperation ownerは、その変更で影響する:

```text
requires_completion
integration prerequisite
planned_next
return_to
```

を同じ正式operationでreplanし、構造validationを通す。

cancelled / plan_excluded predecessorを持つ `requires_completion` を「満たされた」と読み替えて残してはならない。必要ならdependencyを正式変更するか代替Workを作る。

## Phase completion

Phase completeはeventではなく生成する。

少なくとも:

- Phaseがcancelled / plan_excludedでない
- effective current-plan Workが全てcomplete
- integrationが少なくとも1件存在
- effective current-plan上のunfinished integrationなし
- structural human_confirmationがeffective current-planに存在するならcomplete
- cancel / plan exclusion後のrelation / integration replanが完了
- structural validation PASS

`cancelled` / `plan_excluded` Workはcompletedではない。

## Work completion precheck

- Workの成立状態を満たす
- realizesを満たす
- must_updateを満たす
- applicable conditional_must_updateを満たす
- 必要tests / verification PASS
- unresolved required dependencyなし
- 他のstarted（in_progress / held）non-terminal Workが現在読む必要のあるtargetを、deletion resultとして消していない
- canonical refs valid
- 新たなstructural human_confirmation要否を評価済み
- Workline structure valid

成立しないWorkを完了扱いにするためdesired stateを書き換えない。

### Work result

Work resultには、作成・更新したresultと、意図的に削除したtracked fileの両方があり得る。両者は別々に宣言する。

```text
通常result   → 完了時にfilesystem上に存在すること
deletion result → 明示宣言し、tracked fileであり、完了時に不存在であること
```

存在しないはずのresultを「たぶん削除された」と推測しない。宣言のないmissing resultは未達成として扱う。

Workのchanged result集合は「通常result ∪ deletion result」とする。したがってmust_update / applicable conditional_must_updateのtargetは、更新でも意図的削除でも満たせる。realizesはtarget実在を要求する意味のままで、deletionでは満たされない。

deletion resultも通常resultと同じくcurrent START operation-owned changeとして扱う。pre-existing dirty保護（START開始前から削除されていたtracked fileを今回の成果として横取りしない）と、exact pathでのGit finalizationを同じく受ける。

directory名をdeletion resultとして宣言しない。実際にtrackedされているfile pathを列挙する。

deletion resultは、他のstarted（in_progress / held）non-terminal Workが現在読む必要のあるtargetを消さない。executorが正常に終わっても例外で終わっても、その直後に喪失を検出し、消えたtargetをexecutor開始前の状態（未commitのローカル内容を含む）へ戻す。正常終了なら `related_target_removed` でSTOPし、executorが例外で終わった場合は戻したうえでその失敗をそのまま伝える。戻せなかった場合だけ、元の失敗を隠さずに別途報告する。STOPするだけで消えたまま残さない。戻すのは消えた保護対象pathだけであり、他の変更やworking tree全体を戻さない。未開始Workの計画修正はRoadmapのRelated maintenanceで行い、terminal Workのhistorical Relatedは書き換えない。

## Future relation maintenance

START内でbranch / fix / return計画を変えた場合、STARTがWork間future relation正規化の意味owner。

- planned_nextのterminal/inactive targetをactive planから除外可
- return_to先cancelled / plan_excludedならreplan
- requires_completion predecessor cancelled / plan_excludedはsatisfied扱いしない

`derived` はhistorical factとして保護。

## Phase Integration Review（marked integration、RB5）

`work_kind: phase_integration_check` で `phase_review_contract: phase-integration-review-v1` を持つintegration（marked integration）は、STARTが **Phase Integration Review** を必ず通して完了させる。markerはRoadmap（review-v1のPhase entry）またはSTART（reviewed semanticsの再integration）がCREATEへ渡して付けるcanonical metadataであり、STARTの実行時に推測・追加・除去しない。markerの無いintegrationは従来どおりの通常executor経路で、何も変わらない。

- **selector**: `start(..., phase_review=PhaseIntegrationReview(discovery=..., adjudicator=...))`。Work Formal Reviewの `review=` とは別のselectorで、`review=` はmarked integrationの代わりにならない（`phase_review` が無ければ `phase_review_required` で、何も書かずに止まる）。P3のWork-terminal activationはPhase Integration Reviewの前提ではない。
- **両方のselector（Control Plane裁定 Q-C1 = OPTION_A_FAIL_CLOSED）**: 2つのselectorは、1つのinvocationにmutation contractを跨がせない。single-workでmarked integrationを指せば、`phase_review` がそのPhase Integration Reviewに適用され、`review=` はselectorとして検証するだけで、Work Reviewのactivation・marker・recoveryには使わない（integrationは通常のterminal semanticsのまま）。outer modeで両方を渡し、review-v1 Workのmutationがmarked integrationへ続くことになる時は、Phase Integrationの永続effectより前に `phase_review_outer_with_work_review` で何も書かずに止まる（F3のpublicationは変えず、push-onlyのterminal stageも作らない）。integrationはsingle-workの `phase_review=` STARTで実行する。
- **review-v1 Work Reviewとreviewed Phaseの完了**: reviewed Phaseの最後の未完了effective Work（例: downstream confirmation）の完了はそのPhaseの現在のbasisを閉じ、同じtransitionでphase_completion evidenceを要る。review-v1 Work Reviewのterminal stageはF3で固定された形でevidenceを持てないので、そのWorkを `review=` で実行するSTARTは、何かを記録する前に `phase_review_work_review_closes_reviewed_phase` で止まる（再開されたSTART・outerの継続・始まっていたWork Review Runの継続でも同じ）。そのWorkは通常のSTARTで完了させ、evidenceはその完了と同じstageに記録される。reviewed Phaseの他のWorkとlegacy Phaseは変わらない。
- **semantics note**: `phase_review` を持つ新しいSTARTは、mutationの最初の永続保存（open）でreviewed Phase integration semanticsのnoteを記録する。noteの無い（RB5より前の）pendingのSTARTはlegacyのまま再開し、marked integrationをreviewしない（upgradeしない）。
- **reviewed semanticsの派生**: そのSTARTが作る再integrationはmarked integrationで、Phaseのeffective Workの完全なdirect predecessor closureを持つ（Human NGのconfirmationはdownstream）。`before_integration = false` の通常Workは拒否、unfinished integrationの既存closureの欠けは `phase_integration_coverage_gap`、reviewed Phaseでunmarkedのunfinished integrationへの追加は `phase_integration_unmarked_unfinished` で、どれもeffectの前に止まる。
- **Run**: integrationの通常のopening lifecycle（`work_started` / `work_target_added`）を記録し、HEADのcommitted状態からPhase Integration Candidateを凍結してから、P4のdiscovery → adjudication → seal（G1〜G5、contract `review-v1-phase-integration-p4-v1`）を回す。executorはintegrationのCompletedを作らない。discovery / adjudicatorの起動の前後でProjectの永続状態をSTART自身が測り、変わっていれば `phase_integration_verification_side_effect` で何もsettleしない（verification-only）。Candidateが最新でなくなれば `review_candidate_mismatch` のreconcile。他のSTARTが持つopenのIntegration Runを置き換えない（`review_recovery_incomplete`）。
- **G4のdisposition**: `HUMAN_WAIT` はそのRunのまま待つ（STARTはpending）。`human_decision` とHuman Decision Evidenceを持つ再実行で、待っているRunを `human_decision` としてset asideするsuccessor Runになる。`DOMAIN_REPAIR_REQUIRED` はRunをfinal `not_authorized` で終え、executorへ専用のrepair planning context（`ExecutionContext.integration_repair`: blocking Finding・semantic surface・unmet objective obligation・prior repair link・STRATEGY_CHANGE要否）を渡し、`IntegrationRepairPlan(strategy_id, Derive(move=True))`・question・holdだけを受ける（それ以外は `phase_integration_repair_plan_invalid`）。planはregistrationより前に保存し、fix Workを通常のderivationでCREATEへ渡し（各fix Workにversion 2の `future_work_link` provenance）、targetを外して `moved` で返る。fix完了後に同じintegrationへ入り直すと新しいCandidate / Runになる。`CONFIRMATION_STRUCTURE_REQUIRED` はRunをfinal `not_authorized` で終え、決定的な `human_confirmation` を1件だけCREATEへ渡してcommitし（既に有効なdownstream confirmationがあれば作らない）、同じintegrationのsuccessor Runへ続く。step 4の拒否（`phase_integration_uncovered` / `phase_integration_not_authorizable`）もG4でfinal `not_authorized` で、そのcodeで止まる。finalのRunはset asideで名指さず、authorizableとして回復しない。
- **STRATEGY_CHANGE（Control Plane裁定 Q-C2 / Q-C3）**: G4は、adjudicationの `repair_induced` claimが名指せるWorkを、このintegrationの以前の修理が登録したfix Work（検証済みのversion 2 `future_work_link` がちょうど1件）に限る。STRATEGY_CHANGE要否は同じsemantic surfaceのsupportedなB/C relation chainで決め（現在のFindingのsupportedなB/Cの前任Finding自身も同じsurfaceのsupportedなB/Cの前任を持つ）、Runの順番・時刻・newest・IDの辞書順では決めない。要る時、そのsurfaceで既にlinkされたstrategy identityを再利用するplanは何も登録する前に `phase_integration_repair_plan_invalid` で拒否する。
- **terminal**: `AUTHORIZATION_READY` だけがG5のReceiptを出す。terminal gateの全条件を確かめてから、1つのlifecycle stageに consumed Run summary・通常の `work_target_removed`・markerの無い通常の `work_completed`・その `work_completed` のevent IDに束ねたversion 5のIntegration Consumption・（このtransitionでreviewed Phaseが生成完了するなら）phase_completion evidenceを記録し、STARTの通常の `<Work>:finalize` のcommitとpushで閉じる。再開はこのstageを記録から読み、同じ組で終える。commit後にHEADがReview recordを正確なbytesで持つことと、evidenceがHEADのcommitted Phase basisであることを証明する（違えば `review_achievement_basis_mismatch` のreconcile、置き換えない）。
- **Phase evidence obligation**: reviewed Phaseを生成完了にするSTARTの完了（downstream confirmationの完了を含む）は、そのPhaseのphase_completion evidenceを同じlifecycle stage・同じcommitに記録する。STARTのcancelで閉じるbasisは `<prefix>:achievement` stageに記録する。covering integrationのReview recordに操作前からの変更があれば `dirty_overlap`、引けるcovering Reviewが無ければ `phase_evidence_unavailable` で、どちらも何も記録しない。legacy Phaseは何も記録しない。

## Mutation / Git

STARTがSTART operation owner。

START開始前にworking tree / branch / remote / ownershipを確認する。pre-existing dirtyはSTART-ownedではない。

CREATEによる派生Work / relation変更も同じSTART operationへ属する。

commit直前にdiffを再確認し、START-owned changeだけをstageする。START開始前からの変更と同じfileを、hunk分離で自分の分だけcommitすることはしない。その変更がevent log（STARTは何を返してもcommitする）にある場合は、lifecycle eventの追記とexecutorの実行より前にSTOPし、executorが返した成果path・削除pathや、executorが返した派生の登録が書くrelation fileと重なる場合は、その成果commitや派生の記録より前にSTOPする（`rules/git` のCommit / push）。後者では、STOPする前に、重なったpathをexecutor実行前の内容へそのまま戻す。executorが返した成果と、そこにexecutorが残していた内容はrecordへ保存し、人がその変更をcommitまたは破棄した後の再実行は保存した成果で続け、executorを再実行しない（recordが保ちきれない成果は保存せず、従来どおり問い直す）。派生はWork file・派生detail・relationを1件も記録・適用する前に判定する。開始時snapshotは広げないが、runが何かを書くより前に、現在は変更されていないpathを落とす。

START開始時にcleanだったpathへ、START開始後に他者・別AIが書いた変更は、開始時snapshotの外にあるので上の判定では止まらない。STARTは、event log・relation file・Work file等へ書くたびにその内容をrecordへ記録し、executorが返した成果path・削除pathはexecutorが返した時点の内容をrecordへ記録する。記録済みeffectを書き直す直前と、成果commit・finalization commitを作る直前に、その内容が現在もそのままであることを確認し、示せなければevent・成果・relationのどれも書かず、stage・commit・pushもせず、その変更を書き戻しも削除もせず、recordを変えずに `reconcile required` で停止する（`rules/git` のCommit / push）。特にexecutorが返してから成果commitまでの間に成果pathが書き換えられた場合、STARTはその成果を `completed` として返さず、自分が持っていた古い成果をその上へ書き戻さない。人がその変更をcommitまたは破棄するか、pathをSTART自身が書いた内容へ戻せば、同じSTARTの再実行がそこから進む。

STARTが記録したcommit（成果commit、finalization commit等）を作る前に中断・失敗した場合、その間に人のcommit等でHEADが進んでも、`rules/git` のCommit / pushに従い、記録したbaseがHEADの祖先であり、base以降のどのcommitも記録したpathsを変更しておらず、記録したbranchの上にいることを示せる時だけ、そのHEADの上に記録どおりのcommitを作ってGit段階から継続する。pathsの一部だけ・別の内容でのcommit、変更して戻した履歴、履歴の書換え、branchの変更、branchを記録していない旧implementationのrecordは、従来どおりreconcile required。HEADが記録時のbaseのままでも、記録したbranchの上にいることを示せなければ（同じcommitを指す別branchのcheckout、branch名の変更等）、成果commitやterminal eventを含むfinalization commitを別branchへ作らず、reconcile requiredで停止する。記録したbranchへ戻れば、同じSTARTの再実行がGit段階から継続する（`rules/git` のCommit / push）。人などが記録と同じmessageで別の変更をcommitしていても、それだけでは成果commitやfinalization commitを作ったことにならない。まだ適用済みと記録していないcommitは同じ条件で判断し、成果やterminal eventを未commitのままcompletedとしない（同じ規定）。STARTは、executorが返した後にそのcycleの結果（完了・hold・cancel・派生等）を記録する時に、それを決定したbranchとHEADのcommitを同じrecordへ記録し、executorより前に記録するWork開始のlifecycleではbranchを固定しない。決定を記録した後・それを確定するcommitを記録する前に中断した再実行は、決定したbranchの上（そのbranchが独立なcommitで進んだだけの場合を含む）でだけ進み、別branch・書き換えた履歴・detached HEAD・Gitが判定できない場合は、何もreplay・commit・pushせずreconcile requiredで停止する。決定したbranchへ戻れば、同じSTARTの再実行が続きから進む。決定したbranchを記録していない旧implementationのrecordは、同じbranchの上でも推測せず停止する（`rules/git` のCommit / push）。成果commitやfinalization commitを作った後（pushの前・完了の前）に、そのcommitを履歴に含まないbranch等へ移って再実行し、そのcommitで確定する適用済みのlifecycle event等をもう一度書くことになる場合は、そのcommitが記録したbranchの上でだけ書き、別branch・detached HEAD・Gitが判定できない場合は、何もreplay・push・記録せずreconcile requiredで停止する。記録したbranchへ戻れば同じSTARTの再実行が進み、branchを記録していないcommitは従来どおり扱う（同じ規定）。

remoteあり通常Projectでは最終Work結果をremoteへ反映する。remoteなしはlocal commitでよい。

記録したpushが公開するのは、そのGit段階のcommitとその土台の履歴だけで、question waitや中断の間に人などが同じbranchへ積んだcommitは、そのpushでは公開しない。後のWorkやstageがその上に自分のcommitを作った場合だけ、そのcommitの履歴として公開される（`rules/git` のPush destination）。

STARTがGit段階を記録した後・そのcommitを作る前に中断し、その間に人などが同じ変更を自分のcommitへ取り込んだ場合、STARTはそのcommitを自分のcommitとして採用せず、記録したpushも実行せずに `reconcile_required` で停止する。これはerrorではなく公開の安全境界である。回復は人が行い、その別主体のcommitが未公開で安全に取り消せる場合だけ、取り込まれた変更をworking treeへ戻してから同じpending mutationを再実行し、記録どおりのcommitはSTART自身に作らせる（recordやProject正本を手で直さない）。公開済み・後続commitあり・安全に戻せることを示せない場合は自動修復せず、人のGit調整が必要である（`rules/git` のCommit / push）。

pushする場合の宛先は `rules/git` のpush destinationに従う。START開始前、mutationを開くより前、networkへ触れるより前に承認先一致を検査し、承認先なし / 不一致 / 解決不能はdomain writeの前にSTOPする。承認先をSTART側で変更しない。

### 成果commit message

executorが成果completionで中身のあるmessageを渡した場合は、その文字列をそのまま使う。STARTはprefixを足さず、typeを変換せず、前後の空白も含めて内容を書き換えず、形式も検査しない。

messageが無い場合、およびmessageが空・空白だけの場合のdefaultは、neutralな固定messageとする。

```text
chore(workline): <display> <name>
```

空白だけのmessageは「messageを渡さなかった」と同じに扱う。どちらも読み手に何も伝えないため区別しない。これを拒否してWorkを止めない。空かどうかの判定にだけ空白を無視し、実際にcommitするmessageはexecutorが渡した文字列そのものとする（判定のためのstrip結果をcommitしない）。

成果がfeat / fix / docs / refactorのどれに当たるかはproduct判断であり、STARTはWork名・成立状態・work_kind・成果fileの内容から推測しない。判断できるのは成果の意味を決めたexecutorだけなので、typeを持たせたい場合はexecutorが明示messageで渡す。

create / modify / deleteの成果は同一のowned setとして1 commitにまとめるため、deletionだけの成果も同じdefaultを使う。owned result fileが無いWorkは成果commit自体を作らない。

### Terminal finalization

Work成果の必要commit / push後、terminal lifecycleを同じfinalization mutationで処理する。

```text
completion precheck PASS
↓
必要な成果commit / push
↓
work_target_removed
↓
work_completed
↓
eventsを含む最終commit
↓
remoteありなら承認先へ最終push
↓
外部的にもWork complete
```

completed event記録後にcommit / push失敗したら、通常STARTを再実行しない。同じpending finalization mutationをresumeし、domain実作業やeventを重複させずGit段階だけ継続する。

completed eventを記録した後、そのeventを含む最終commitを記録する前に中断・STOPした場合も同じ。同じWork・同じmodeのSTART再実行は、現在stateからWorkを選び直す前に、そのpending mutationが記録したterminal lifecycle eventのfinalizationが終わっているかをrecordで確かめる。completionのeventを記録（または適用）したのに最終commitが未記録なら、executorを再実行せず、eventを追加せず、他のWorkを選ばず、同じmutationで最終commit / pushを行ってからcompletedとして扱う。outerではその後に同一Phase内の次startable Workを再計算する。前のWorkのterminal eventを次のWorkのcommitへ混ぜない。

このGit段階からの継続は、recordがそれをこのSTART自身のcompletionと示す場合だけ行う: そのlifecycle stageがcompletionの記録するevent（`work_target_removed` / `work_completed`）を予約済みIDでちょうど持ち、最後に記録されたstageであり、single-workでは指定Workのものであり、HEADのevent logがまだそのeventを持たないこと。示せない場合（複数Workのfinalizationが未完了、STARTが記録しない形のrecord、このmutationが記録していないcommitによってHEADのevent logが既にそのeventを持つ）は、何もreplayせずrecordを変更しないまま `reconcile_required` でSTOPする。この継続もcompletionを決定したbranchの上でだけ行い、別branchへcheckoutした後の再実行は、finalization commitを別branchへ作らず、次のWork・integration・Phase完了へも進まず、何もreplayせずrecordを変更しないまま `reconcile_required` でSTOPする（`rules/git` のCommit / push）。

cancelでは、STARTはexecutorが返したcancelの決定（対象Work、replanのstageを記録するprefix、理由、replanの新Workと追加relationをexecutorが渡したとおりの値と順序で、削除relationを決定した時にProjectが持っていた内容で）を `work_cancelled` のeffectに載せ、cancelのlifecycle eventを記録するのと同じdurable writeでrecordに記録する。このwriteはcancelを決定したbranchも記録する（`rules/git` のCommit / push）。replanに予約したIDは決定に重ねて書かない。決定のどれかの値を、recordが書いて読み戻した時に同じ種類の同じ値として保てない場合（小数、tuple、object、listの中のlist、空でない文字列以外をkeyに持つmapping、UTF-8で書けないsurrogateを含む文字列など）、およびreplanがその記録の形にならない場合（新Workのnameが文字列でない、Relatedが `RelatedSpec` の形でない等）は、cancel eventを記録する前に `validation_failed` でSTOPし、cancelのeventも決定も記録しない。決定を持たないcancel eventは記録しない。

cancel eventを記録した後に中断・STOPした場合、同じWork・同じmodeのSTART再実行は、現在stateを判定する前・mutationを開く前・何もreplayする前にrecordを読み、記録済みの決定からcancelを続けられることを示せる場合だけ続ける: 決定がSTARTの記録する形であり、対象Workがsingle-workでは指定Work、outerでは同じPhase範囲のWorkであり、prefixと予約IDがそのcancelのものであり、決定の後に記録されたstage（新Workの登録または追加relation、削除relation、cancelのcommit）がその決定の作るものと順序どおり一致し、適用済みのeffectが記録順の先頭部分であること（同じSTARTが先に追加し、このcancelが削除したrelationの追加は、`rules/git` のMulti-write mutationのとおり適用済みとして数え、書き戻さない）。そのうえでcancel自身が適用したeffectを除いたstateでSTART precheckとcancelのreplanの投影を行い、残りのeffectを記録・適用すれば出る拒否は何もreplayする前に、その拒否の本来のcode（投影の `spec_violation`、検証の `validation_failed` / `structure_invalid`、`dirty_overlap` 等）で出し、recordを変更しない。続ける場合は、executorを再実行せず、prefix・予約ID・削除relation・記録済みの新Work登録をrecordから取り、残りのreplan・structural validation・commit / pushだけを行って、記録した理由とともに `cancelled` を返す。outerでもcancelの後に次のWorkを選ばず、Phase完了やintegrationへも進まない（中断が無い場合と同じ）。

決定を記録していない旧implementationのrecordは、cancelのcommitを記録済みでも、event・commit・現在stateから決定を推測せず、何もreplayせずrecordを変更しないまま `reconcile_required` でSTOPする。決定の形・対象・prefix・予約・stageの順序・記録済みeffectが決定と一致しないrecord、削除するrelationをProjectが決定した時の内容で持たない場合、同じSTARTの複数のrecord、このmutationが記録していないcommitによってHEADのevent logが既にcancel eventを持つ場合も同じ。cancelを決定したbranch以外での再実行は、何もreplay・commit・pushせず `reconcile_required` で停止し、決定したbranchへ戻れば同じ再実行が続きから進む（`rules/git` のCommit / push）。cancel eventを記録する前の中断では、従来どおりexecutorから決め直す。

どの場合も、未commit / 未pushのterminal eventを残したままcompleted / cancelled / stopped / phase_completeを返してSTART mutationを閉じない。

期待値不一致・divergence・ownership競合はreconcile required。

## Review-v1 Work（明示opt-in）

STARTは、呼び出しごとの明示opt-inでだけWorkのterminalizationをReview gate（`skills/review`）に通す。`start(..., review=WorkReview(reviewer, reviewer_identity, reviewer_version))` がreview-v1 Workであり、選択子は版付きのcontract `review-v1-work-v1` を運ぶ（booleanではない）。`review=None`（既定）はlegacy pathで、従来と1 byteも変わらない。contract modeはAPI境界で固定し、Project state・Review file・Work kind・Workの内容・executorの結果から推測しない。

Projectのactivation（`skills/review` のWork-terminal activation）はreview-v1を選べる条件であり、選ぶことではない。activationを作るのは専用のmaintenance operation（`rules/git` のOperation Owner）で、STARTはactivationを作らず、推測もしない。activateされたProjectでもlegacy STARTはそのまま使え、その `work_completed` はmarkerを持たず、Consumptionを要しない。

**durable marker**: review-v1 STARTのmutationは、最初のdurable writeで、liveのinvocation（operation、work_id、mode）に加えて `review_contract: review-v1-work-v1` と `publication_contract: review-v1-split-v1` をちょうど持つ。どのGit stageよりも前に書く。markerはslot identityではない。

**resume**: pendingのSTART recordのcontractは再実行で変わらない（昇格も降格もしない）。markerの無いrecordをreview-v1で、markerのあるrecordをlegacyで、部分的・未知・余分なmarkerのrecordをどちらで呼んでも、`reconcile required`（reason `review_marker_mismatch`）で停止し、recordを変えず、executorを実行せず、Reviewを読まない。legacyで使えるのは、そのrecordが終わった後の別のinvocationだけである。

**entry順**:

```text
1  lockより前（何も書かない）: 選択子（review_contract_invalid）、immutable Review createを保てないplatform
   （review_create_unsupported）、remoteがありP2_PUBLICATION_GIT_MIN未満・version不明のGit（review_git_unsupported）、
   pinしたattribute source（HEADの木）がReview namespaceの外へmaterialな変換を割り当てる（review_git_transform）、
   Gitがattribute sourceのpinを守ることを示せない（review_git_unsupported）。規定は rules/git
2  Project context → self-hosting → Workline implementation → Project execution lock
   （lock holderの情報はstaticなmarker review_contract だけで、callerの値を書かない）
3  marker互換（上記のresume）
4  liveのSTART precheck、Git、push destination（従来どおり）
5  activation: recordが無ければ review_not_activated で停止する。mutation・executor・Review record・Git write・
   networkのどれも無い。recordがmalformed、operation_contractが未知ならreaderの ValidationError、prefix digestが
   HEADのcommitted event logから再現しなければ reconcile required。どれもlegacyへ落とさない
6  mutationを2つのmarkerとともにopen
```

`review_not_activated` は、Projectがこの任意のcapabilityを有効にしていないための通常のSTOPであり、`reconcile required` ではない。

**完了の流れ**（executorが `Completed` を返した後。順序固定）:

```text
5a-6   宣言の正規化（\ を / にするだけ）、正規のspelling、予約namespace、containmentと結合したownership witness、
       そのwitnessでのownershipの宣言。ここまでdurableなものは何も無い
7-9    completion precheck、開始時からの変更の分離、pinしたGit persistence preflight
9a     S-c0: このWorkのentry lifecycle eventがcommitされていなければ、event logだけをcommitする（<W>:entry）
10-12  Work Candidate（executorが返した時点のwitnessから。K1より前）、snapshot material、resulting tree、
       Context v2、凍結したCandidateそのもののisolated verification
13-16  generation 1（accept）、reviewer、generation 2（settle）、checkout capabilityの判定、capableの時だけ
       generation 3（sealとReceipt）
17-24  RAW lineage、Consumption IDの予約、S-c1（<W>:results）とK1、C-2(K1)、result-proof note、
       remoteがあればK1だけのpush（<W>:results-publication）
25-35  terminal stage（<W>:lifecycle:<n>）、S-c2（<W>:finalize）とK2、C-2(K2)、terminal-proof note、
       remoteがあればK2だけのpush（<W>:finalize-publication）
36-37  recorded-completion proofが通った後に completed を返す
```

- STARTは、宣言したowned set（結果pathと削除path）から、executorが返した時点でWork Candidateを凍結する。それはどの結果commitよりも前である。Candidateはその時のwitness（bytesとGitのidentity）から作り、pathを読み直さない。
- 対応する結果のobject kind（file、実行可能file、symlink、gitlink、削除）を、entryでもexecutorが返した後でも拒否しない。宣言したowned setを正確にprojectできない時（正規でないspelling、containmentを示せない、directory、読めない）だけ `review_candidate_unavailable` で停止する。
- 結果を持たないWork（宣言したpathが無い、またはどれも変化しない）はreview-v1の正当な場合で、empty-artifact Candidateになる。K1を作らず、空のcommitを合成せず、Consumptionの `artifact_kind` は `empty` である。
- STARTは `skills/review` のEvidenceの検査を実行し、凍結したCandidateそのものをisolated verificationで検証し、その結果のdigestをgateへ渡す。
- 許可された遷移を適用するのはReviewではなくSTARTであり、AuthorizedTransitionProjectionが名指す遷移（`work_target_removed`、`work_completed`）だけを適用する。

**stage**: review-v1 Workのcommitとpushは同じstageにしない。1つのreview-v1 Work mutationが持つpushはたかだか2つで、どちらもpublication stage（K1、K2。Class Aでは下記のK_adopt、K_terminal）である。それ以外のWork cycleのGit stageはすべてcommitだけで、2つのpushのどちらかが公開する証明済みの履歴としてだけ承認先へ届く。commitの作り方、pushの規定、attribute sourceのpinは `rules/git` に従う。1つのreview-v1 Work mutationは1つの完了だけを持つので、outerでもreview-v1の完了の後は次のWorkを選ばずに返る。

**terminal stage**: 1つのlifecycle stageに、予約したIDでの `work_target_removed`、operation-contract metadata（`operation_contract: review-v1`、`review_receipt_id`、`review_run_id`、`review_generation`）を持つ `work_completed`、そのRunのConsumptionのimmutable createの3つを、この順にdurableに記録してから適用する。eventのIDは `<stage>:event:0` / `<stage>:event:1`、Consumption IDは `review-consumption:<receipt_id>` のkeyで予約する。この形でないstageはreview-v1の完了ではなく、legacyの完了としても読まない。

**recorded-completion proof**: `completed` を返すのは、recorded-completion proof（K2がこのmutationのcommitであり、proof noteがそれぞれのcommitを名指し、公開すべきものが公開され、何も未commitで残っていないこと等）が通った後だけである。Receiptがあること、K2があること、承認先へ公開されたことは、それぞれ単独では完了の証明にならない。

**remoteなし**: pushは無く、すべての証明はそのまま行う。legacyのcommitとpushを1つにした形には戻らない。

**resume**: 中断の後の再実行は、そのmutationのrecordとcanonicalなReview recordから導き直し、決め直さない。既に始めたWork Review Runはrecordから続け、Candidateを凍結し直さない。Contextはgeneration 1のacceptより前に不変になる。pendingのreview-v1 mutationはlegacyへ降格しない。何を続けるかは1つのrecovery selectorが、mutation自身の予約・Class-A checkpoint・canonicalなchainから決める（最初のRun、checkpoint済みで旧generation 4がまだ、旧Runが無効化済み、successorを予約済み、successorのreview中、successorがseal済み）。新しさ・HEAD・commit messageでは決めない。Work Review Runを始めた（generation 1があるか、そのgeneration mutationがpendingの）STARTは、reviewerのerrorやsettleが許可しない等でSTOPしても、effectを記録していないことを理由にmutationをabandonせずpendingのまま残し、次の同じSTARTがそのRunを続ける（reviewerのerrorはsettleせず、次のrunが同じtaskを同じreviewerへ再launchする: Work Review Policyの `error_disposition`。新しいCandidateもRunも作らない）。Runを始める前のSTOPは従来どおり、effectを記録していなければmutationをabandonする。

**回復の選択（すべての呼び出し）**: review-v1 Work STARTのすべての呼び出し（新しいSTART、最初のRunだけを続ける再開、Class Aの再開）は、activationの後・mutationを開く前に、このWorkの同じreview kindとoperation identityを持つRun（別のSTART、失われたSTARTが始めたRunを含む）を `skills/review` の回復の選択で分類する。Work Review Runはそれを予約したSTART mutationのrecordからだけ続けられるので、このWorkのpendingのSTART mutationが予約したRunはそのmutationの回復selectorのものとして除き（同じinvocationならそのmutationを開いて続け、別のmodeのmutationならmutationを開く時に従来のwrite scopeの衝突で止まる）、それ以外のRunはどれも再開しないもの（consumed・invalidated・not_authorized・set_aside・stale）でなければならない。どのpendingのSTART mutationも持たない回復可能な形のRun（失われたSTARTのRun等）は、その再開に要る予約・generation mutationの所有者・ownership witness・pre-existing dirtyのsnapshot・S-c0 / S-c1のcommit・terminal stageがどのpendingのrecordにも無いのでincompleteであり、incompleteなRunがあれば `reconcile required`（`review_recovery_incomplete`）で止まり、mutation・予約・記録・Git writeを作らず、executorを実行しない。新しい最初のRunのrequestは、set asideした他のRunをそれぞれ理由とともに名指す（無ければ空のlist）。

**post-commit recovery（F4 Class A）**: K1を作った後に、そのC-2(K1)が通らなくなった時だけ、STARTはClass Aを試みる（例: K1を作った後の中断から再実行までの間にimplementationが変わり、縛ったContextが再計算できない）。Class A / B / C・same-Run invalidation・successor Run・request v1 / v2・C2・adopted-resultの意味は `skills/review` のWork post-commit recoveryが所有する。K1より前に分かった不一致は、K1としてcommitしない。

- 試みる場所: step 20のC-2(K1)が `reconcile required` で通らなかった時だけである。C-2(K1)の失敗をそのままClass Aとして扱わず、明示的な分類（`skills/review`）がA1かA2を示した時だけ続ける。
- 厳格な適格性: exact K1がこのmutationのS-c1が作ったcommit（C-1）で、宣言したbranchがちょうどK1を持ち、K1のpublication effect（push stage）も、terminal lifecycle・Consumption・terminal commitのstageもまだdurableでなく、旧RunのR1がcurrentで消費できる状態で、承認先がK1を持たないこと。承認先がK1を既に持てば `reconcile required`（reason `review_result_already_published`）、別の履歴なら `review_destination_divergent`、読めない・示せない時はSTOP（`review_destination_unknown`）で、どれも採用しない。publication effectやterminal effectが既にdurableな時は、それを書き換えず・削除せず・その後ろに置き換えの公開を足さず `reconcile required`（`review_class_a_ineligible`）。Class Bは `review_class_b_unowned_content`、Class Cは `review_class_c_unprovable`（またはC-2(K1)自身のreason）で止まる。
- exact K1とC2: K1は、S-c1のdurableな `prepared_commit_id` とC-1の `commit_id` / applied（`rules/git`）から読み、HEAD・commit message・最新commit・pathの類似からは決めない。C2は、commitされたK1とその親だけから作る（`skills/review`）。
- checkpoint: 旧Runのgeneration 4を記録する前に、START mutationへdurableなClass-A checkpoint（`review_work_class_a_checkpoint`。exact K1とその親、branch、旧Run・旧Receipt・旧Candidate hash、分類と理由、S-c1のstageとseq、predecessor Run、契約version、publication / terminal effectがまだ無いこと）を書く。Class B / Cではcheckpointを作らない。再開の時は何かをする前にcheckpointをimmutableなcommitted stateに対して検証し、矛盾すれば `reconcile required` で止まる。commit message・最新commit・branch tip・pathの類似・K1の存在からcheckpointを再構成しない。
- topology:

```text
checkpoint -> 旧Run generation 4 + Supersession(R1)（1つのgeneration mutation）
-> successorの予約 -> 回復の選択（旧Runはinvalidated、回復可能はsuccessorだけ）
-> successor generation 1（C2、version 2 request）-> reviewer -> generation 2 -> checkout capability（K1の木）
-> generation 3 + R2 = K_adopt -> adopted-result proof note（review_work_adopted_result_proof）
-> remoteがあれば exact K_adopt のpush（<W>:adopted-publication）
-> terminal stage（R2を消費し、Consumptionの結果commitはK1）-> K_terminal（親はK_adopt）-> terminal proof
-> remoteがあれば exact K_terminal のpush（<W>:finalize-publication）-> recorded-completion proof -> completed
```

- 公開点: remoteのある成果ありのClass Aも、pushはちょうど2つ（K_adopt、K_terminal）である。最初のpushはK1・旧generation 4・successorのgeneration 1〜3・R2を1つのfast-forwardの系譜で運び、K1単独もbranch tipも公開しない。adopted-result proofは記録の前と適用の直前に評価し直す。remoteなしではpushは無く、同じproofとcurrentnessを行い、K_adoptがlocalの系譜の錨になる。
- 許可は、結果publicationの記録の前、その直前、terminal stageの記録の前、terminal commitの前、terminal publicationの記録の前とその直前、`completed` を返す前のそれぞれで導き直す。以前の証明を時を超えた正しさとして扱わない。
- successorのReviewが許可しない場合は、最初のRunと同じくterminalizeせず `reconcile required` で止まる（修復のloopは持たない）。
- 再開: どの中断の後も、同じWork・同じmodeのreview-v1 STARTの再実行が、recordとcanonical recordから同じ予約ID・同じsuccessor・同じK1 / K_adoptを導き直して続ける。Candidate・Run・Receipt・Supersession・Consumption・terminal event・publicationを重複させず、force・reset・rebase・amend・branch tipの置き換えをせず、legacy STARTへ落ちない。

**予約namespace**: review-v1を選ぶことは、executorが走る前に、invocation contractとして次の2つの予約namespaceを縛る。

```text
.workline/review と .workline/review/**    canonical Review namespace（F3 A-5）
.workline/events/events.jsonl             lifecycle event log（F3 A-6）
```

executorはこれらを結果pathとしても削除pathとしてもownできない。規則は静的で選択した時から有効であり、具体的な結果pathのlistを知る必要はない。判定はownershipの宣言（`declare_own_content`）より前に3層で行い、文字列のprefixでは決めない: 正規のspelling（書き直さずに拒否する）、予約namespaceの分類（ASCIIだけのcase foldは前段のfilterで、権威はno-followで開いた祖先、またはpathの最後の要素自身のfilesystem object identity）、Project containment。containmentの検査は結合したownership witnessを作り、宣言はpathを解決し直さずにそのwitnessを永続化する。祖先が無くなっている削除は正当な結果（無いことの証明）であり、拒否しない。予約namespaceの宣言は所有できない状態であり、`reconcile required`（reason `review_reserved_namespace`）で停止する。対応しない結果の形ではなく、`review_candidate_unavailable`（projectability）でもなく、legacyへ落とすこともない。identityを確定できない時はfail closedである。

**STOP codeとreason**: review-v1 WorkのSTOPはcode（`StopError` / `ValidationError`）であり、`reconcile required` は `code == "reconcile_required"` のまま意味を `reason` に持つ。lockより前: `review_contract_invalid`、`review_create_unsupported`、`review_git_unsupported`、`review_git_transform`、hermeticなGit環境に入れない（`review_identity_unavailable`、`review_repository_grafted`、`review_repository_shallow` 等）。lockの後・mutationより前: `review_not_activated`。完了の流れ: `review_base_uncommitted`、`review_candidate_unavailable`、`review_context_unavailable`、`review_namespace_unreadable`、`review_resulting_tree_unavailable`、reviewer（`review_reviewer_failed`、`review_report_invalid`、`review_reviewer_mismatch`。意味は `skills/review`）、sealしないcheckout capability（`review_checkout_unsafe` / `review_checkout_unknown`）、commit（`review_commit_plan_invalid`、`review_index_lock_reconciliation`、`review_local_cleanup_checkpoint`）。reasonは `review_marker_mismatch`、`review_reserved_namespace`、`review_registration_base_moved`、`review_commit_unowned`、`review_publication_invalid`。post-commit recovery（F4）: STOP code `review_destination_unknown`、reason `review_class_a_ineligible`、`review_class_b_unowned_content`、`review_class_c_unprovable`、`review_result_already_published`、`review_destination_divergent`、`review_recovery_ambiguous`、`review_recovery_incomplete`、`review_chain_invalid`。回復の選択（すべての呼び出し）: reason `review_recovery_incomplete`（別のmodeのpendingのSTARTは従来のwrite scopeの衝突）。liveのcode（`detached_head`、`dirty_overlap`、`related_target_missing` 等）は意味を変えない。

**P4（current-cycle Repair Loop、明示opt-in）**: `start(..., review=WorkReviewP4(discovery, adjudicator, repair, human_decision=None))` は、v1の `WorkReview` とは別の選択型で、Work P4 contract `review-v1-work-p4-v1` を選ぶ。v1の選択型にP4の任意動作を足さない。discovery actor（viewpointごと）・adjudicator・repair actorは、どのlaunchより前にTaskInputへ束ねたidentity / versionにだけ再launchする（違えば `review_reviewer_mismatch`）。

- **marker と dispatch**: P4のSTART mutationは、最初のdurable writeから区別されたmarker（`review_contract: review-v1-work-p4-v1`、`publication_contract: review-v1-split-v1`）を持ち、lockのholder記述もP4 contractだけを名指す。publication markerはv1と同じ（Workのpublication validatorはReview contractの世代を読み分けない）。同じslotのpendingのrecordは自分と同じcontractのmarkerでなければ継続せず、mutationを開く前に `review_marker_mismatch` で止まる（v1をP4へ昇格もP4をv1へ降格もしない）。Workのoperation identityは変えない（v1と同じ `start:<digest>`）。P4のmarkerはそれに入らず、後継Runも同じoperation identityを保つ。Contextは、変えないWork Context v2をP4 contractとPolicyと共に束ねるP4 Work Contextである。
- **流れ**: v1と同じfreeze（5a〜12: ownership、precheck、S-c0、Candidate、resulting tree、isolated verification）→ G1 discovery accept → G2 settle + canonical raw report → G3 adjudication accept → G4 adjudication。AUTHORIZATION_READYならcheckout capability（15a）の後にG5 seal + Receipt（`review_generation` 5）、その後はv1と同じterminal path（lineage、S-c1 / K1、C-2(K1)、K1のpush、terminal stage、Consumption（`review_generation` 5）、S-c2 / K2、C-2(K2)、K2のpush、recorded-completion proof）。lineageのown-Review集合は、このSTARTのP4 cycleの全record（各Run、raw report、adjudication、Repair Batch / Result、Candidate N+1）である。
- **Candidate N+1の採用（START所有）**: The Work repair actor returns a complete repaired Candidate proposal/material and never directly mutates the canonical working tree as Review authority. After G6, the owning START alone adopts the exact proposal onto the allowed result surface using the existing ownership, overlap, witness, resulting-tree and verification machinery. The adopted Candidate must equal the persisted Candidate N+1 exactly before successor Review or Git persistence. 提案は宣言済みの結果pathの完全なbytesだけで、宣言の外を変えれば何もsettleしない（`review_p4_repair_invalid`）。採用は、記録済みwitnessが今も成り立つことを確かめてから書き、ownershipを結び直し、step 10と同じ方法でCandidateを組み直してN+1のhashと照合し、isolated verificationを行う。違えば `review_p4_adoption_mismatch` で止まる。再開時に既に採用済みなら照合だけをやり直す。
- **後継Run**: 採用の後、`review-successor-run:<predecessor>` で後継Runを予約し、Candidate N+1でdiscoveryからやり直す。requestは前任Run・Repair Batch・Repair Result digest・candidate_generation + 1を明示し、前任を `p4_repaired` としてset asideする。
- **HUMAN_WAIT**: G4でHUMANが残れば `review_p4_human_wait` で止まり、STARTはpendingのまま残る（修理を推測しない）。A HUMAN_WAIT Run remains non-authorizing at G4. A later Human decision is supplied through the owning operation boundary as an explicit decision identity and disposition. The decision does not create a separate requirement store. A requirement change must already be reflected in its normal authority; a confirmation may leave requirement bytes unchanged. The owner binds the decision, sets the prior HUMAN_WAIT Run aside as `human_decision`, freezes a new Candidate/Context as needed, and starts a new P4 Run. Workでは、決定（`human_decision=HumanDecision(...)`）を持つ同じWork・同じmodeのSTART再実行が、pendingのmutationに決定を永続的に束ね、待っているRunを `human_decision` としてset asideし、作業treeからCandidateを凍結し直して新しいP4 Runを始める。決定はSTARTのslot identityに入らない。決定の束ねはmutationに1つではなく、待っているRunごとに1つ（待っているRun → 決定）で、successorの予約より前に永続化する。同じRunへ同じ決定での再実行は冪等で、別のsuccessorを作らない。束ね済みのRunへ別の決定を渡すと `review_p4_human_decision_invalid` で止まり、束ねは変わらない。同じpendingのSTARTの中で後の別のRunがHUMAN_WAITになれば、そのRunには後の別の決定を束ねる。既に別のRunの待ちを解いた決定や、待っているRunのrequestが既に持っていた決定（待ちより前に渡されたもの）は、その待ちを解かず `review_p4_human_wait` のまま残る。successorのdiscovery requestは、先行Runの待ちを解いた決定そのものを束ねる。
- **最終Receiptの消費とClass A**: terminal stageが消費するのはcycleの現在のRunのG5 Receiptだけである。P4 RunはF4 Class Aに入らない。K1の後にC-2(K1)が通らず、束ねたContext / Policyがもはや導き直せない（stale）なら、G5 ReceiptをP4のG6 invalidation（Supersession付き）で直ちに無効にして `review_p4_receipt_invalidated` で止まる。それ以外は `reconcile required` のまま止まる。A stale P4 authorization Receipt is invalidated by a P4 G6 invalidate transition that atomically Supersedes the G5 Receipt. Repair G6 and invalidation G6 are distinct transition shapes. No G7 exists. P4 Work does not reuse F4 Class A for a G5-sealed P4 Run.
- **v1を読み替えない**: pendingのv1 Runはv1のままでだけ再開する。P4のG4をF4のinvalidationと、P4のG5 sealをrepairと読まない。
- **P4のSTOP codeとreason**（意味は `skills/review`）: `review_p4_human_wait`、`review_p4_adjudication_invalid`、`review_p4_adjudicator_failed`、`review_p4_repair_failed`、`review_p4_repair_invalid`、`review_p4_repair_coverage_unknown`、`review_p4_repair_widen_required`、`review_p4_reverification_incomplete`、`review_p4_strategy_change_required`、`review_p4_human_decision_invalid`、`review_p4_receipt_invalidated`。Runを開始した後のSTOPではSTARTはpendingのまま残る。reason: `review_p4_contract_mismatch`、`review_p4_linkage_invalid`、`review_p4_successor_conflict`、`review_p4_adoption_mismatch`、`review_p4_chain_invalid`。

**P5（durable Review history、P4-capableなRun）**: P5 capability is an explicit per-Run stored Review policy/history-contract property within the P4-capable owner family. New first Runs use the P5-capable policy after P5 activation; a cycle keeps the policy/history family of its first Run. Existing P4-only Runs are never upgraded by file presence, current code, or shape inference. STARTのP4 selector・marker・lock・operation identityは変えない。Runがまだ無いpendingのSTARTが作る最初のRunは現在のP5 policy `review-v1-p5-policy-v1` と history contract `review-v1-history-v1` を束ね、repairやHuman decisionのsuccessorはcycleの最初のRunのpolicyを保つ。currency・Context・Policyの判定は、そのRunが保存したpolicyで行う。P4-onlyのRun（P5 activationより前に始まったcycle）は、request・terminal stage・K2を含めて従来と同じである。

- **START ownerが書くhistory**（`skills/review` の P5 Review History、同じgeneration mutationかterminal stageの中で、別のhistory commitを作らない）: G1にset-asideする前任のset_aside summaryとHuman Decision Evidence（外部launchより前にcommit）、G2でdiscoveryがfailedでsettleする時のnot_authorized summary、G4にFinding summary・受理したcross-run relation・HUMAN_WAITのRun summary、修理のG6にRepair summaryとrepaired summary、G6 invalidationにinvalidated summary。A P5 Run whose canonical G2 settlement makes discovery non-authorizing receives its immutable not_authorized Run summary in that same G2 transition.
- **P5のterminal stage**: consumed Run summaryのcreateを先頭に、従来の3つのeffect（`work_target_removed`、`work_completed`、Consumptionのcreate）を続ける4つのeffectを、1つのdurableなlifecycle stageとして記録してから適用する（P5の形はRunが保存したhistory contractで読み分け、stageの形から推測しない）。K2の差分はevent log・Consumption・Run summaryの3つで、C-2(K2)はT4でこの差分を、T8でsummaryのbytesと正確なConsumptionに対するsummaryの検証を、P-6でsummaryのcommitを証明する。K1とK2の間にhistoryだけのcommitを挟まない。lineage（L-2）のown-Review集合には、cycleの各Runのgenerationが書いたhistoryを正本recordから導いて含め、fileの存在からは導かない。
- **Human decisionでのP5 cycleの再開**: P5のHUMAN_WAITは、`human_decision=HumanDecision(...)` に加えて `decision_evidence=(DecisionEvidence(...),)` を持つSTART再実行でだけ再開する。evidenceの `affected_review_run_id` はP4-R7の待っているRunそのものでなければならない。決定の束ね・successorの予約・どのeffectよりも前に、Runが実際にG4 HUMAN_WAITに達したこと・Candidate・kind / target・決定identity / disposition・requirement authorityの反映を証明し、successorのG1でHuman Decision Evidenceを1つ永続してからdiscoveryをlaunchする。Human Decision Evidence explicitly identifies the prior HUMAN_WAIT Run and candidate affected by the decision. The owner validates that exact canonical G4 HUMAN state, sets that Run aside as `human_decision`, persists one immutable evidence record before the resumed external Review launch, and separately proves the current canonical requirement/authority. Evidence never substitutes for requirement authority. P4-onlyのcycleは従来どおり決定だけで再開する。
- **P5のSTOP code**（意味は `skills/review`）: `review_p5_history_missing`（必要なhistory、またはP5の待ちを再開するevidenceが無い）、`review_p5_history_invalid`、`review_p5_disposition_unsupported`、`review_p5_authority_mismatch`（`requirement_changed` なのにWork本文が変わっていない）、`review_p5_decision_evidence_invalid`（待っているRun以外を名指す、またはP4-onlyのRunを名指すevidence）。どれもRunを進めず、STARTはpendingのまま残る。reason: `review_p5_history_conflict`。

**P6（Project-local Adaptive Policy、P4-capableなRun）**: Orchestrator ruling R6-1により、P4-capableなFormal Reviewの新しい最初のRunはすべてP6-capableで、family policy `review-v1-p6-policy-v1` を束ねる（P5の規則とhistory contract `review-v1-history-v1` をそのまま持つ）。新しい最初のRunは、どの予約・記録・launchより前に、GlobalPolicyBaseline + canonical Project Profile（`.workline/review/policy/project-profile.yaml`、または明示の不在）を解決して正規化したEffective Policyを凍結し、自分のrequestに束ねる（`skills/review` のP6 Project-local Adaptive Policy）。修理の後継とHuman decisionでの新しいRunはcycleの最初のRunのpolicy（family）を保ち、自分のEffective Policyを開始時に新しく解決して凍結する（cycleの最初のRunのEffective Policyは引き継がない）。open Runは途中でpolicyを変えない。既存のP4-only / P5のRunは自分の保存したidentityで読む。

- **discovery**: selectorのdiscovery actorは、Effective Policyの `review.discovery.required_slots` 個以上で、異なるreviewer identity / versionに束ねる（足りなければ `review_p6_discovery_slots_unmet`）。activeなlightening実験がdiscovery holdoutを凍結していれば、selectorの `holdout_discovery`（required slotとは別のviewpointと、別のidentity / version）が正確にその数だけ要り、G1で受理・G2でsettle・G4でadjudicateする（無ければ `review_p6_holdout_unbound`、選ぶ実験が無いのに渡せば `review_p6_holdout_not_applicable`。どれも何も予約・launchしない）。
- **修理の再検証**: 必要な再検証は、修理のimpact levelを `review.reverification.extra_scope_steps` 段広げたlevelごとのP4下限（FOUNDATIONで頭打ち、P4の下限より下げない）。activeなlightening実験が外した広いlevelのcheckはholdoutで、Repair Resultより前に修理のverificationに含まれていなければ `review_p6_holdout_unsettled`、失敗すれば `review_p6_holdout_failed` で何もsettleしない。
- **Profileが使えない時**: Profileが読めない（`review_p6_profile_invalid`）、lineageを証明できない（`review_p6_lineage_invalid`）、current baselineとcompatibleでない（`review_p6_profile_incompatible`）なら、新しいRunは始まらない（policy maintenance / reconcile）。open Runは自分が凍結したpolicyで続く。凍結したEffective Policyが読めないP6 requestは `review_p6_effective_policy_unreadable` でfail closedする。

## outer continuation

1 Work完了ごとに同一Phaseのeffective current-plan Work / generated state / dependenciesを再計算する。START再実行（resume）では、そのmutationが記録した直前のWorkのterminal finalization（Terminal finalization参照）を終えるまで次のWorkを再計算しない。記録済みのcancelを続けた再実行は、そのcancelを終えたところでSTARTを終える。記録済みのholdを続けた再実行も同じで、そのholdを終えたところでSTARTを終える（Question wait / temporary move / true hold参照）。

startable Workが1件に決まれば同一Phase内で継続。

どれを次にするかは `planned_next` で決める。既に完了したWorkが次に推奨しているWorkを優先し、そのうちまだ終わっていないWorkから前に置かれていないものを採る。cancelled / plan_excludedのpredecessorは候補を後ろへ押さえない。

正式条件を適用しても2件以上残る場合は、どれも自動で選ばずstopとしてRoadmapへreturnする。候補listの先頭・ID順 / ULID順・relation fileの記録順・宣言順・表示番号・dict / listの挿入順でtieを破らない。stop理由に候補のIDを含め、人間が次に実行するWorkを明示できるようにする。

このstopで新たなcanonical stateを作らない。直前に完了したWorkのfinalizationは通常どおり閉じ、次のWorkのlifecycle event・derived Work・commitは行わない。

Phase completeまたはstopならRoadmapへreturn。

次PhaseをSTART自身で選ばない。
