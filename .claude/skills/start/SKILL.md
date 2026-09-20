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

## outer continuation

1 Work完了ごとに同一Phaseのeffective current-plan Work / generated state / dependenciesを再計算する。START再実行（resume）では、そのmutationが記録した直前のWorkのterminal finalization（Terminal finalization参照）を終えるまで次のWorkを再計算しない。記録済みのcancelを続けた再実行は、そのcancelを終えたところでSTARTを終える。記録済みのholdを続けた再実行も同じで、そのholdを終えたところでSTARTを終える（Question wait / temporary move / true hold参照）。

startable Workが1件に決まれば同一Phase内で継続。

どれを次にするかは `planned_next` で決める。既に完了したWorkが次に推奨しているWorkを優先し、そのうちまだ終わっていないWorkから前に置かれていないものを採る。cancelled / plan_excludedのpredecessorは候補を後ろへ押さえない。

正式条件を適用しても2件以上残る場合は、どれも自動で選ばずstopとしてRoadmapへreturnする。候補listの先頭・ID順 / ULID順・relation fileの記録順・宣言順・表示番号・dict / listの挿入順でtieを破らない。stop理由に候補のIDを含め、人間が次に実行するWorkを明示できるようにする。

このstopで新たなcanonical stateを作らない。直前に完了したWorkのfinalizationは通常どおり閉じ、次のWorkのlifecycle event・derived Work・commitは行わない。

Phase completeまたはstopならRoadmapへreturn。

次PhaseをSTART自身で選ばない。
