# Workline Registry

現在仕様のauthorityは、この `registry.md` の4共通ルール本文と、registry-routed canonical Skillsの `SKILL.md` のみ。
checkpoint / audit / fix / old spec はhistory / rationaleであり、実行時正本ではない。

正式marker:

```text
<!-- workline-id: <id> -->
<!-- workline-target: <relative-path> -->
<!-- workline-context: <pre-project | project | router> -->
```

`workline-context` はSkillの適用条件を宣言する。`skills/*` は必須。

```text
pre-project → Workline Project成立前にだけ使う（初期化）
project     → established Workline Project内で使う
router      → Project内entryからのSkill選択自身を担う
```

参照:

```text
workline://<id>
```

必須IDは各ちょうど1件。0件・複数件・broken routing時に名前・path・mtime・意味類似で代替しない。

registryに登録された `skills/*` は必須集合に限らずすべてvalidationの対象とする。必須ID集合は「必要なauthorityの欠落検出」であり、存在するSkillの一覧ではない。Skillの追加はこのregistryとcanonical `SKILL.md` の更新だけで完了し、既存Projectを更新しない。

---

## Git / Mutation Safety
<!-- workline-id: rules/git -->

### 基本原則

Git履歴は積み上げる。既存未保存作業、未commit変更、未追跡ファイル、他者・別AIの変更をWorkline都合で失わせない。現在operationが責任を持つ変更だけをstage / commitする。`git add .` を無条件に使わない。

remoteなしは正常。localがremoteに対して単純behindなら安全確認後 `pull --ff-only` 可。diverged、force push、rebase、reset、clean、既存remote変更・削除、ownership不明変更の破棄は自動実行しない。

既存untrackedファイルの編集・上書き・削除は人間確認へ返す。

`.workline/runtime/` はWorkline-owned non-domain runtime補助領域とする。Worklineが作成・管理するrecovery metadataを同一mutationの期待値に従って作成・更新する場合は前項の既存untracked保護の対象外だが、Workline ownershipを確認できないrecordや期待値不一致のrecordは自動上書きせず `reconcile required` として停止する。`.workline/runtime/locks/` に置くProject execution lock（lock fileと診断用holder情報）も同じruntime補助領域であり、commitせず、domain正本やevidenceとして扱わない。

### Operation Owner

Project側へ書き込むstate-changing操作には operation owner を1つ置く。

```text
Project開始 → Project開始
Roadmap操作 → Roadmap
START実行 → START
Standalone Workの直接作成 → CREATE direct invocationが作るDirect Work Operation context
```

Phase CREATE / CREATEのregistration coreはGit finalizerではない。呼び出し元operation ownerのmutationへ参加する。

CREATEがRoadmap / STARTのparent operationなしで直接起動された場合だけ、CREATE entrypoint自身がDirect Work Operation contextを生成し、その外側contextがpostcheck / commit / remoteありならpushまでを所有する。新しいSkillやroutingは増やさない。

各state-changing operationのentryで、operation ownerは（成立済みProjectでは次節のProject context照合、Workline implementation照合、Project execution lock取得の後に）current invocationの対象と予定write scopeに関係するpending mutationを検査する。一意対応する1件があれば新規mutationを開始せずそのmutationをresumeし、0件なら新規mutationを開始してよい。複数件、競合、または他ownerのpending mutationから安全に独立していると証明できない場合は `reconcile required` として停止する。

### Project context

成立済みWorkline Projectへ書き込むstate-changing operationは、invocation Project contextがtarget Projectと一致する場合だけ実行する。一致しなければ `foreign_project_mutation` としてSTOPする。

invocation Project contextは、top-level operation開始時のprocess作業directoryから1回だけ解決する。session identity・引数・環境変数・promptの記述からは決めない。

```text
作業directoryを実体pathへ解決し、上方向へ探索する（各directoryで次の順に判定）
1. .workline/project.yaml がある → そのestablished Workline Project
2. .git（file / directory）がある → Projectではない Git repository境界。ここで探索を止める
3. どちらもない → 親directoryへ
rootまで見つからない → Project contextなし
```

同じdirectoryに `.workline/project.yaml` と `.git` の両方がある場合はWorkline Projectとする。最も近いGit境界を越えて親のWorkline Projectを探さない。contextとtarget Projectは、文字列ではなく実体のdirectoryとして照合する。

contextはtop-level operation開始時に確定する。実行中にexecutorや子processが作業directoryを変えても、進行中operationの許可は変わらない。新しいtop-level operationは、その時点の作業directoryから改めて解決する。QuestionWait後のresumeも新しいinvocationとして照合する。同じsessionである必要はなく、同じProject contextから実行されればよい。

```text
targetがestablished Projectか確認
→ invocation Project contextを解決
→ target Projectと照合（foreignならSTOP）
→ Workline implementation照合（configured rootのimplementationでなければSTOP）
→ Project execution lock取得
→ pending mutation / Project stateを読む
→ mutation open / resume → effects → validation → commit / push
```

foreign STOPは、execution lock・holder情報・mutation intent・event・relation・entityを作らず、Git add / commit / pushも行わない。

別Projectのread-only参照（validation、state / entityの読取、候補確認、診断、pending mutationの読取、記録を伴わない判定、Git情報の読取）は許可し、この照合を行わない。

foreign mutationを許可するoverride（flag・引数・環境変数・owner名・promptの記述）は設けない。成立済みProjectへの操作は、そのProjectのcontextから行う。

Mutation Controllerは、成立済みProjectのmutationを、この照合を通ったtop-level operationのexecution lockの内側でだけopen / resume / 書込みする。

Project開始（初期化）はforeign mutationとは別のpre-project operationとして、次をすべて満たす場合だけ実行する。

```text
- 明示されたtarget folderに対する、Project開始のcanonical implementationの実行である
- invocation Project contextが、target以外の成立済みWorkline Projectではない
  （Workline root、Projectではないdirectory / Git repository、target自身やその配下からは実行できる）
- targetが成立済みWorkline Projectの配下にない（nested Workline Projectは作らない）
- 実行中のWorkline implementationが、project.yamlへ書くWorkline rootのものである（Workline implementation）
```

Project開始のmutationは、その実行が対象rootに与えた許可の内側でだけopen / resume / 書込みできる。owner名だけでは許可されない。

このcontextは、あるProject contextで作業中に別Projectのpathを誤ってmutation targetへ渡す事故を防ぐmechanical guardであり、security sandboxではない。意図的な作業directoryの変更（`cd` / `chdir`）や、Worklineを経由しないfilesystemへの直接書込みは保証の対象外である。

### Workline implementation

Workline operationは、supported interpreter上で、configured Workline rootに由来するimplementationだけが実行する。configured Workline root（以下 `R`）は、成立済みProjectでは `.workline/project.yaml` の `workline.root`、Project開始では明示されたWorkline rootである。

interpreter identityとimplementation identityは別の要件である。

```text
interpreter     : Python 3.11以上（exact versionは要求しない）
implementation  : <R>/src/workline（Rのworking tree）
canonical entry : <R>/run-workline.py
```

implementationはinstallせず、runtime copyも持たない。ambient install・editable install・site-packagesのworklineはcanonical runtimeではない。Rのworking treeが更新されると、次に起動したcanonical processからその内容が実行される。

CLI subcommandがあるoperationは、必ずlauncherから起動する。成立済みProjectのoperationはそのProjectの中から、Project開始はWorkline root等から起動する（Project context）。

```text
Windows: py -3 -I -B "<R>\run-workline.py" <command> ...
POSIX:   python3 -I -B "<R>/run-workline.py" <command> ...
```

CLI subcommandが無いoperation（Roadmap、START、related maintenance、achievement等）はPython APIを使い、次のinvariantに従う。

```text
isolated Python processを開始
→ 同じprocessで <R>/run-workline.py の activate() を実行
→ activate PASS
→ その後にだけ workline APIをimport
→ operation
```

Windows PowerShell（5.1 / 7共通）:

```powershell
& {
    $OutputEncoding = [System.Text.UTF8Encoding]::new($false)

    @'
import runpy

activate = runpy.run_path(r"<R>\run-workline.py")["activate"]
activate()

# only after activation:
from workline import roadmap as rm, start as st

# operation...
'@ | py -3 -I -B -
}
```

Windows PowerShell 5.1は、`$OutputEncoding` を明示しないとdriver本文の非ASCII文字を `?` に変えてPythonへ渡す。scriptblockの中で設定するので、呼び出し側の設定は変わらない。cmdにはAPI driverの正式な例を置かない（CLIはcmdでも使える）。

POSIX:

```sh
python3 -I -B - <<'PY'
import runpy

activate = runpy.run_path(r"<R>/run-workline.py")["activate"]
activate()

# only after activation:
from workline import roadmap as rm, start as st

# operation...
PY
```

`activate()` より前に `workline` をimportしない。activateはprocess-localであり、token・authorization・import path・環境変数・fileを別processへ引き継がない。子processでWorkline APIを使う場合は、その子processが自分でactivateする。activateはProject context・Workline implementation照合・Project execution lockの代わりではなく、各top-level operationはそれらを従来どおり評価する。

`python -m workline.cli`、console script、`PYTHONPATH` の手作業設定、editable installを前提にしたimport、site-packagesのworklineの直接起動は、動いてもcanonicalではない。launcherやactivateが使えない場合はSTOPして報告し、これらへfallbackしない。

`-I` は、`PYTHONPATH` を含む `PYTHON*` 環境変数、user site-packages（user側の `.pth` / usercustomize）、作業directory / script directory由来のimport pathの混入を抑える。system site-packagesとその `.pth`、sitecustomize、startup codeが追加するfinder、venvのsite-packagesは残り得る。`-I` はidentityの保証ではない。

`-B` と、launcherがWorkline codeのimport前に設定する `sys.dont_write_bytecode` により、canonical runtimeはWorkline rootへPython bytecode cacheを書かない。

identityを保証するのはorigin verificationである。launcherとactivateは次の順で検査する。

```text
Python version（3.11未満 → workline_python_unsupported）
→ isolated mode（-Iなし → workline_invocation_not_isolated）
→ bytecode書込みを無効化
→ 既にloadされている workline / workline.* のoriginを全件検査
→ <R>/src をimport sourceとして設定し、worklineをload
→ load済みの workline / workline.* のoriginを全件再検査
→ 作業directoryが成立済みProjectなら、その workline.root が R であることを照合
→ CLIへdispatch / activateはreturn
```

PASS条件は、`workline.__path__` が `<R>/src/workline` だけの1要素であり、load済みの `workline` / `workline.*` のoriginがすべてその配下の `.py` であること。directoryの同一性は実体（real path / file identity）で判定し、文字列だけで比較しない。`<R>/src` をimport pathの先頭へ置くこと自体はidentityの証明ではない。

```text
workline_implementation_unverified  : originを一意に証明できない
                                      （namespace / frozen / built-in / sourceless pyc / extension、出所の混在）
workline_implementation_mismatch    : 単一のpackage directoryだが <R>/src/workline ではない
workline_implementation_unavailable : <R>/src/workline が無い、またはloadできない
```

別rootのmoduleが既にloadされていても、sys.modulesから消して読み直さない。実行済みコードの副作用は取り消せないためSTOPする。同じRのmoduleが既にloadされている場合は受け入れる。

launcherを経由しない経路でimplementationがimportされた場合も、implementation自身が、実際にloadされているimplementationとconfigured rootを次の時点で照合する。

```text
成立済みProjectへのstate-changing operation : Project context照合の後、Project execution lock取得の前
Project開始                                  : pre-project contextの確認の後、registry validationとmutationの前
                                               （実行中implementationのroot == 明示されたWorkline root）
成立済みProjectのcanonical validation        : configured rootのimplementationでなければPASSさせない
```

照合に失敗したoperationは、execution lock・holder情報・mutation intent・event・relation・entityを作らず、Git add / commit / pushも行わない。Project contextの不一致とimplementationの不一致が両方ある場合は、Project context（`foreign_project_mutation`）を先に報告する。

照合を回避するoverride（flag・引数・環境変数）は設けない。

Project contextは「どのProjectへ書くか」、Workline implementationは「どのimplementationが書くか」、Project execution lockは「同時に動くwriterがいくつか」を決める。三者を混ぜない。

これはsupported interpreterとconfigured rootのimplementationを取り違えないためのmechanical guardであり、security sandboxではない。選んだinterpreterのstartup code（`.pth` / sitecustomize）の実行そのもの、sys.modules・finder・照合処理の意図的な書き換え、driverやexecutorが実行する任意のコードは保証の対象外である。

保証するのは、configured rootのworking treeのimplementationであることまでである。committed revision・main branch・clean tree・released version・process間のrevision一致・実行中にsourceが変更されないことは保証しない。

### Project execution lock

成立済みWorkline Projectへ書き込むstate-changing operationは、Project単位のactive execution lockを保持している間だけ実行する。同一Projectで同時に実行中のwriterは1つだけとする。

```text
top-level operation開始
→ Project context照合（foreignならSTOP。lockを作らない）
→ Workline implementation照合（STOPならlockを作らない）
→ lock取得（待たない）
→ pending mutation / Project state / push destination / dirty stateを読む
→ mutation open / resume / begin
→ effects → validation → commit → push
→ mutation complete / QuestionWait / STOP処理
→ lock解放
```

operationは、write判断に使うWorkline structural state（pending mutation・lifecycle・dependency・push destination等）をlock取得後に読み、lock取得前に読んだものを使い回さない。書込みを伴わない参照・診断はlockを必要としない。

`roadmap_achieved` を記録する場合、Roadmapの「達成したい状態」を満たしたというsemantic judgementはcallerによるexplicit evaluationであり、execution lockはこの判断をlock内で再実行しない。execution lockが保証するのは、記録直前にWorkline canonical stateのstructural precondition（Roadmapが通常操作可能・全active Phase complete）をlock内で再確認し、成立しなければ記録しないことまでである。Workline canonical state外のdomain evidence（判断に用いた成果物・verification結果等）までatomic snapshotにする保証はない。

pending mutationとexecution lockは別物である。pending mutationはdurableなrecovery状態、execution lockは「いまこのProjectでwriterが実行中である」ことだけを表す。QuestionWait等でoperationが戻る時はlockを解放し、pending mutationは維持する。resumeは新しいinvocationがlockを取得してから行う。

他processがlockを保持している場合は待たずに `project_operation_busy` としてSTOPする。これは `reconcile required` ではない。busy側はmutation intent・event・relation・entityを書かず、Git add / commit / pushも行わない。

lockはOSが管理する排他file lock（`.workline/runtime/locks/project.lock`）とし、所有の正本はlockの保持そのものである。並置するholder情報は診断用であり、所有判定に使わない。process終了時にlockは解放される。persistent lease・TTL・強制解除・stale lock cleanupは設けない。crash後は次のoperationがlockを取得し、既存のpending mutation recoveryに従う。

lockを取得するのはtop-level operation ownerだけである。Phase CREATE / CREATEのregistration coreは呼び出し元operationのlockとmutationへ参加し、lockを取り直さない。同一processで、同じProjectのlockを保持したまま別のtop-level operationを開始した場合は `project_operation_nested` としてSTOPする。

Mutation Controllerは、Project開始以外のoperation ownerについて、execution lockを保持していないmutationのopen / resume / 書込みを拒否する。

Project開始（初期化）はexecution lockの対象外であり、同じProjectへProject開始を同時に複数実行することはサポートしない。成立済みProjectに対するmaintenance（bootstrap backfill、push destination pin等）はexecution lockの対象である。

### Mutation Controller

中央正本の物理writeは共通のMutation Controller経路を通す。
対象例:

```text
relations/roadmap.yaml
relations/related.yaml
events/events.jsonl
Roadmap / Phase / Work本体
```

Domain Skillは意味を決め、Mutation Controllerは決定済みpayloadをvalidationして適用する。Mutation Controllerは意味判断しない。

### Multi-write mutation

複数正本を変更するoperationは stable `mutation_id` を持つ。概念:

```text
mut_<ULID>
```

recovery metadataは `.workline/runtime/mutations/<mutation_id>.yaml` 等、`.workline/runtime/` 配下のruntime補助領域に置く。runtime metadataはdomain正本ではなく通常commit対象にしない。

mutation開始時に必要なentity / relation IDを先行発行し保持する。途中失敗後は新しいIDでやり直さず、同じmutationをresumeする。

operation ownerは、最初のdomain effectより前に、`mutation_id`、operation owner、current invocationと予定write scope、先行発行ID、決定済みの予定effectと期待値を同じmutationとして識別・resumeするために十分なrecovery intentへ記録し、durable local writeの成立を確認する。operation中に新たなeffectを決定した場合も、そのdomain effectより前に同じrecovery intentへdurableに追記する。recovery intentのdurable writeに失敗した場合は対応するdomain effectを開始せずSTOPする。

各effectはresume時に:

```text
未適用
適用済み・期待値一致
適用済み・期待値不一致
```

へ分類する。

- 未適用 → 同じmutationの予定effectを適用
- 一致 → skip
- 不一致 → `reconcile required` として停止。自動上書きしない

可能な限り参照される側を先に書き、参照する側を後に書く。

### Cleanup

rollbackを通常回復方式にしない。

同一mutationで今回新規作成し、未commit、他正本から未参照、期待値と完全一致する孤立生成物だけは定義済みcleanupとして削除可。

既存domain fact、既存event、commit済み変更、ownership不明変更、他主体変更はrollbackしない。

### Commit / push

1 Work / 1 operation = 1 commit / 1 push とはしない。複数commit / push可。

通常WorkとRoadmap操作は、remoteがある通常Projectでは必要成果がremoteへ反映されるまで成功扱いにしない。remoteなしでは必要なlocal commit成立でよい。

Project開始は例外で、初期commit必須・push不要。

commit失敗 / push失敗時はdomain writeを再実行せず、同じpending mutationのGit段階からresumeする。

START terminal処理は `work_target_removed` / `work_completed` を含む最終commitと、remoteありならその最終pushまでをfinalization mutationとする。local completed / remote未反映時は通常STARTを再実行せず finalization resumeする。

### Push destination

remoteがある通常Projectのpushは、Project正本が承認したpush destinationと一致するときだけ行う。承認先の正本は `.workline/project.yaml`。

```text
git:
  push:
    remote: <remote name>
    allowed_urls:
      - <人間が明示承認した exact secret-free push locator>
```

これはcacheではなくsafety authorityである。Git remote configはclone毎・未追跡・任意のツールが書き換え可能で、それ自身を正とすると「最初から誤ったremote」を検出できない。承認先はcommitされ、fresh cloneへ届き、変更がreviewに現れる。

承認先はrepository identityの推論結果ではなく、**Gitが返したlocatorそのもの**である。比較は文字列一致で行い、次を同一視しない。

```text
/repo と /repo.git
/repo と /repo/
pathのcase差
HTTPSとSSH
その他provider依存のrepository path表現
```

サーバによっては別repositoryになり得るため、Worklineは同一性を推測しない。両方を許可するなら人間が両方を `allowed_urls` へ明示する。同じrepositoryが表記差で拒否されること（false negative）は許容し、別repositoryが同一と判定されること（false positive）は許容しない。

安全検査に使うlocatorと、実際に接続・pushするlocatorは同一でなければならない。`.git` や trailing slash を落とす等、repository pathを書き換えた値をidentity判定・drift判定・network接続のいずれにも使わない。

push系operation ownerは、mutationを開くより前に、networkへ触れるより前に検査する。

```text
remoteなし                   → local commit成立でよい（従来どおり）
remoteあり・承認先なし       → STOP
承認先のremote名が存在しない → STOP
active push URLが0件 / 複数件 → STOP
resolved URLがallowed_urls外 → STOP
```

active push destinationはGit自身の解決結果（`pushurl` / `pushInsteadOf` 適用後）を使い、正確に1件でなければならない。複数destinationへのfan-outは扱わない。

`git_push` effectは承認済みlocatorをそのままdurableに保持する。resume時もnetworkより前に、記録済みlocatorとcurrent解決結果の文字列一致を確認する。remote名だけを見て現在の指し先へfetch / pushしない。不一致は `reconcile required`。

push反映の確認は、実pushと同じremote名・同じrefspecの `git push --dry-run` で行い、Git自身に同じrewrite解決を1回だけ通させる。

resolved locatorを別のGit commandへ引数として再投入しない。`url.<base>.insteadOf` が `pushInsteadOf` の生成したlocatorをさらに書き換え、実push先とは別のrepositoryを読み得るためである。fetch URL側のstateやremote-tracking refも反映済みの根拠にしない。

dry-run結果の解釈:

```text
=   up to date          → 反映済み
*   new branch          → 未反映
    fast-forward update → 未反映
!   rejected            → reconcile required
その他 / 解釈不能        → STOP（推測しない）
transport / auth失敗    → STOP
```

credentialを含むURLは承認先・回復記録・エラーメッセージのいずれにも残さない。検出時はredactしてSTOPする。

承認先を書き込めるのはProject開始と専用のpin maintenanceだけで、Mutation Controllerがownerを機械的に検査する。AIやdomain operationがcurrent remoteへ承認先を自動追従させない。承認先の追加・変更はProject固有ルール変更として人間確認の対象。

Worklineが保証するのは「どのrepositoryへpushするか」までである。HTTPS credential account、SSH authentication identity、credential managerが選ぶaccount、provider CLIのlogin accountは保証しない。remote destination確認済みをaccount確認済みとして報告しない。

---

## AI Decision
<!-- workline-id: rules/ai-decision -->

AIは確定済みの上位成立状態を変えない範囲で、実現方法・技術手段・検証方法・未来計画の具体化を自律判断してよい。

AIが判断可能であることと、Workline正式構造を直接書き換えてよいことは別。Roadmap / Phase / Work / relationの変更は担当Skill / operation ownerとMutation Controllerの正式経路を通す。

```text
Roadmapの達成したい状態
→ AI単独で意味変更しない

未開始Phase / Work
→ 未来計画
→ 上位目的を維持し、成果の意味を大きく変えない範囲で正式経路から調整可

開始済みPhase / Work
→ 成立状態を完了しやすく意味変更しない
→ 新しい意味は追加Work / 新Phase等で表現

origin / derived / events等の起きた事実
→ 現在計画に合わせて書き換えない
```

Future-plan relation:

```text
planned_next
requires_completion
return_to
```

は正式経路から変更可能。`derived` はhistorical factとして保護する。

`cancelled` / `plan_excluded` は `completed` ではない。前提entityがcancelled / plan_excludedでも `requires_completion` は満たされない。operation ownerがreplanする。

Phaseのeffective current-plan Work集合は、当該Phaseに所属するWorkのうち `cancelled` / `plan_excluded` を除いたものから生成する。これは新しいmembership正本ではない。cancel / plan exclusionを決めたoperation ownerは、影響する `requires_completion` / integration / `planned_next` / `return_to` をreplanし、構造validationを通す責任を持つ。`plan_excluded` は未開始未来計画にだけ使い、開始済みWorkはcancelで扱う。

`unfinished integration` は、このeffective current-plan Work集合に属する `work_kind: phase_integration_check` のうちgenerated stateが `completed` でないWorkだけを指す。`cancelled` / `plan_excluded` integrationは数えない。

---

## Human Confirmation
<!-- workline-id: rules/human-confirmation -->

安全に調査・検索・比較・テスト・検証で解消できる不確実性は、不要に人間へ返さない。

人間確認が必要:

- Roadmapの達成したい状態そのものの意味変更
- 開始済みPhase / Workの成立状態の意味変更
- 複数の妥当案で成果の意味・重要特性が大きく変わる
- 見た目・音・実物・文言採用・ビジネス判断など人間にしか成立判定できないもの
- rules/gitが要求する危険操作
- 必須正本が一意解決不能
- Workline共通ルール / Project固有ルール変更
- Projectの実行能力・自動実行・外部接続・外部へのデータ開示・書込可能範囲を新たに拡張または変更するtooling / configuration変更

未開始Phase / Workの、上位目的を維持した通常の未来計画調整は一律人間確認にしない。

構成変更の対象例:

```text
hookの新規有効化
MCP server / connectorの追加・変更
project-local Skill / agent automationの追加
plugin / bridge / routine等、Projectから利用可能な実行能力を増やす構成変更
external agentの新しい実行modeの導入で、開示範囲または書込境界が変わるもの
```

対象外:

```text
承認済みtool / configを、承認済み境界内で通常利用すること
capability / external exposure / automatic execution boundaryを変えない
domain configの通常値変更
```

ProjectSTARTを人間が明示実行した結果としてcanonical Workline bootstrap Skillを配置することは、その明示intentに含まれるため別途の人間確認にしない。成立済みProjectへ後から新しいproject-local Skill / automationを追加し、実行能力を変える場合は対象。

Project固有CONTRACTがより厳しいProject-specific safety boundaryを追加することは妨げない。

`rules/human-confirmation` は「今、人間判断が必要か」を決める。`human_confirmation` Workは「人間確認そのものが成果成立の構造的一部」の場合だけ作る。通常質問・回答待ちではWorkを作らず、元Workは原則in_progress / target維持。

---

## Information Tracing
<!-- workline-id: rules/information-tracing -->

正式な正本参照とimplementation searchを分離する。

正本探索:

```text
stable ID
正式routing
明示relation / affiliation
```

から一意解決する。0件・複数件・broken reference時にfilename、directory、mtime、Git上の新しさ、タイトル、意味類似から代替しない。

Roadmap配下Workの基本読取順:

```text
Work
→ Phase
→ Roadmap
→ must_read
→ applicable conditional_must_read
→ obey chain
→ implementation search
```

単独Workでは存在しないPhase / Roadmapを補わない。

implementation searchではdefinition、reference、usage、tests、dependency、impact、error path等を必要範囲で自由に検索してよい。ただし検索結果を正式なRoadmap / Phase / Work / rule / relation正本へ勝手に昇格しない。

checkpoint / audit / fix / old specは現在仕様の正本として横断合成しない。現在仕様はこのregistryとrouting先Skillだけから読む。

---

# Skills

Skill本文はこのregistryに置かない。identityは `workline-id`、現在の物理解決先は `workline-target`。

## Project開始
<!-- workline-id: skills/project-start -->
<!-- workline-target: .claude/skills/project-start/SKILL.md -->
<!-- workline-context: pre-project -->

## Project router
<!-- workline-id: skills/project-router -->
<!-- workline-target: .claude/skills/project-router/SKILL.md -->
<!-- workline-context: router -->

## Roadmap
<!-- workline-id: skills/roadmap -->
<!-- workline-target: .claude/skills/roadmap/SKILL.md -->
<!-- workline-context: project -->

## Phase CREATE
<!-- workline-id: skills/phase-create -->
<!-- workline-target: .claude/skills/phase-create/SKILL.md -->
<!-- workline-context: project -->

## CREATE
<!-- workline-id: skills/create -->
<!-- workline-target: .claude/skills/create/SKILL.md -->
<!-- workline-context: project -->

## START
<!-- workline-id: skills/start -->
<!-- workline-target: .claude/skills/start/SKILL.md -->
<!-- workline-context: project -->
