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

## Derived / fix Work

実行中に新Workが必要と判断した場合、STARTがWork意味とrelationを決め、CREATEへ登録依頼する。

```text
START = 意味owner
CREATE = 登録
Mutation Controller = physical writer
START = Git operation owner
```

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

commit直前にdiffを再確認し、START-owned changeだけをstageする。同一fileにunrelated changeがある場合、安全にhunk分離できる時だけ分離する。不能ならSTOP。

remoteあり通常Projectでは最終Work結果をremoteへ反映する。remoteなしはlocal commitでよい。

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

期待値不一致・divergence・ownership競合はreconcile required。

## outer continuation

1 Work完了ごとに同一Phaseのeffective current-plan Work / generated state / dependenciesを再計算する。

startable Workが1件に決まれば同一Phase内で継続。

どれを次にするかは `planned_next` で決める。既に完了したWorkが次に推奨しているWorkを優先し、そのうちまだ終わっていないWorkから前に置かれていないものを採る。cancelled / plan_excludedのpredecessorは候補を後ろへ押さえない。

正式条件を適用しても2件以上残る場合は、どれも自動で選ばずstopとしてRoadmapへreturnする。候補listの先頭・ID順 / ULID順・relation fileの記録順・宣言順・表示番号・dict / listの挿入順でtieを破らない。stop理由に候補のIDを含め、人間が次に実行するWorkを明示できるようにする。

このstopで新たなcanonical stateを作らない。直前に完了したWorkのfinalizationは通常どおり閉じ、次のWorkのlifecycle event・derived Work・commitは行わない。

Phase completeまたはstopならRoadmapへreturn。

次PhaseをSTART自身で選ばない。
