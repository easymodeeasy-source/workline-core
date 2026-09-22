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

runtime補助領域をGitのignore対象にするための設定（Project rootの `.gitignore`、`.git/info/exclude`、runtime配下のignore file等）は、Workline側で作成・変更しない。Projectの既存ignore設定はProject側の所有物として扱う。

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

各state-changing operationのentryで、operation ownerは（成立済みProjectでは次節のProject context照合、self-hosting照合、Workline implementation照合、Project execution lock取得の後に）current invocationの対象と予定write scopeに関係するpending mutationを検査する。一意対応する1件があれば新規mutationを開始せずそのmutationをresumeし、0件なら新規mutationを開始してよい。複数件、競合、または他ownerのpending mutationから安全に独立していると証明できない場合は `reconcile required` として停止する。

review-v1 planning operation（`skills/roadmap` の明示opt-inによるRoadmap作成・Phase entry）は、1つのplanning mutationと、それが開始するgeneration mutationをownする。entryで一意対応するmutationはそのplanning mutationである。`planning_mutation_id` とRunのserialization tokenでそれに結び付くpending generation mutationはその従属mutationであり、`skills/review` の順序で先にresume・解決する。それ以外は従来どおり複数件 / 競合として `reconcile required` で停止する。runtime（`.workline/runtime/**`）を失った後は、recovery discoveryが見つけた1つのcanonical Review Runを継続するrecovery planning mutation（invocationに `recovery_of_review_run_id` を持つ、新しいIDのmutation）を開始してよい。失われたmutationのIDやrecord、他のmutationのrecordを自分のものとして扱わない（`skills/roadmap`）。

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
→ self-hosting照合（Project rootとWorkline rootが別の実体directoryだと証明できなければSTOP）
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
- targetが、project.yamlへ書くWorkline rootとは別の実体directoryだと証明できる（Unsupported self-hosting）
- 実行中のWorkline implementationが、project.yamlへ書くWorkline rootのものである（Workline implementation）
```

Project開始のmutationは、その実行が対象rootに与えた許可の内側でだけopen / resume / 書込みできる。owner名だけでは許可されない。

このcontextは、あるProject contextで作業中に別Projectのpathを誤ってmutation targetへ渡す事故を防ぐmechanical guardであり、security sandboxではない。意図的な作業directoryの変更（`cd` / `chdir`）や、Worklineを経由しないfilesystemへの直接書込みは保証の対象外である。

### Unsupported self-hosting

Workline rootを、それ自身をWorkline rootとするWorkline Projectとして管理するself-hostingは、現在のWorkline rulesではサポートしない。

state-changing operationは、Project rootとWorkline rootが別の実体directoryだと機械的に証明できる場合だけ実行する。Workline rootは、成立済みProjectでは `.workline/project.yaml` の `workline.root`、Project開始では明示されたWorkline rootである。

```text
同じ実体directory                          → STOP
別の実体directory                          → この照合は通過
両方存在するがfile identityを判定できない  → 別directoryだと証明できないためSTOP
Workline rootが存在しない                  → self-hostingとは扱わない（root不在の既存の扱いに従う）
```

同一性はfile identity（`os.path.samefile` 相当）で判定し、pathの文字列だけで比較しない。case差、区切り文字、末尾の区切り、`..`、相対path、symlink / junction、短縮名によって照合を抜けない。

STOPは `workline_self_hosting_unsupported` とし、何も書かない。

- Project開始: pre-project contextの確認の後、Workline implementation照合・registry validation・Git boundaryの確認・mutationの前に照合する。Git repositoryでないtargetに `git init` せず、既存repositoryのHEAD・index・config・working treeも変えない。targetが既にこの配置の成立済みProjectでも `already_initialized` とせずSTOPする。
- 成立済みProjectへのstate-changing operation: Project context照合の後、Workline implementation照合とProject execution lock取得の前に照合する。execution lock・holder情報・mutation intent・event・relation・entityを作らず、Git add / commit / pushも行わない。

```text
Project context            （foreign_project_mutation）
→ Unsupported self-hosting （workline_self_hosting_unsupported）
→ Workline implementation  （workline_implementation_* / workline_python_unsupported）
→ Project execution lock   （project_operation_busy / project_operation_nested）
```

foreignなcontextからはtargetの配置を評価しない。配置がsupportedでなければ、正しいimplementationへ切り替えてもoperationを実行できないため、implementation照合より先に報告する。canonical launcher / activateが作業directoryのProjectで別のWorkline rootのlauncherを起動時に拒否するのはWorkline implementationのprocess起動時の照合であり、この順序より先に起きうる。

読み取り（file・state・entity・pending mutationの参照、startable / select / diagnose、記録を伴わない達成判定、registry validation、canonical launcherのactivate）は禁止しない。成立済みProjectのcanonical validationは、この配置を `workline_self_hosting_unsupported` のproblemとして報告してPASSにせず、他のproblemも併記する。project.yamlの形式検査やProject成立判定そのものには含めない。

この配置を許可するoverride（flag・引数・環境変数・owner名・人間確認による例外・専用mode）は設けない。既存のこの配置を自動修復・解除しない（project.yamlを書き換えず、`.workline` やpending mutationを削除しない）。

これはself-hostingを正式にサポートするまでの暫定guardであり、サポートを判断する際に再評価する。Workline rootとProject rootが親子関係にある配置や、別のWorkline rootがWorkline rootを統治する配置はこの照合の対象外である（nested Workline Projectの扱いはProject contextに従う）。

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
成立済みProjectへのstate-changing operation : Project context照合とself-hosting照合の後、Project execution lock取得の前
Project開始                                  : pre-project contextの確認とself-hosting照合の後、registry validationとmutationの前
                                               （実行中implementationのroot == 明示されたWorkline root）
成立済みProjectのcanonical validation        : configured rootのimplementationでなければPASSさせない
```

照合に失敗したoperationは、execution lock・holder情報・mutation intent・event・relation・entityを作らず、Git add / commit / pushも行わない。Project contextの不一致やUnsupported self-hostingにも当たる場合は、それらをimplementationの不一致より先に報告する（Unsupported self-hostingの節の順序）。

照合を回避するoverride（flag・引数・環境変数）は設けない。

Project contextは「どのProjectへ書くか」、Unsupported self-hostingは「そのProjectとWorkline rootの配置がsupportedか」、Workline implementationは「どのimplementationが書くか」、Project execution lockは「同時に動くwriterがいくつか」を決める。これらを混ぜない。

これはsupported interpreterとconfigured rootのimplementationを取り違えないためのmechanical guardであり、security sandboxではない。選んだinterpreterのstartup code（`.pth` / sitecustomize）の実行そのもの、sys.modules・finder・照合処理の意図的な書き換え、driverやexecutorが実行する任意のコードは保証の対象外である。

保証するのは、configured rootのworking treeのimplementationであることまでである。committed revision・main branch・clean tree・released version・process間のrevision一致・実行中にsourceが変更されないことは保証しない。

### Project execution lock

成立済みWorkline Projectへ書き込むstate-changing operationは、Project単位のactive execution lockを保持している間だけ実行する。同一Projectで同時に実行中のwriterは1つだけとする。

```text
top-level operation開始
→ Project context照合（foreignならSTOP。lockを作らない）
→ self-hosting照合（STOPならlockを作らない）
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

正本とrecovery recordのstructured text（YAML subsetのfile、`events/events.jsonl`）では、文字列fieldの中のUnicode line separatorを物理的な行・recordの区切りとして扱わない（`events/events.jsonl` の1件はLFで終わる）。U+0085 / U+2028 / U+2029は合法なtextであり、入力として拒否しない。writerはこれらを文字列の中でJSONのUnicode escapeとして書き、1つの値・1件のrecordを1物理行に収める。readerは、それ以前に文字列の中へraw文字のまま書かれた既存のrecordとfileも読む。そのようなfileは通常のoperationで次に保存されるときにescape表現になり、修復のためだけに書き換えない。

### Multi-write mutation

複数正本を変更するoperationは stable `mutation_id` を持つ。概念:

```text
mut_<ULID>
```

recovery metadataは `.workline/runtime/mutations/<mutation_id>.yaml` 等、`.workline/runtime/` 配下のruntime補助領域に置く。runtime metadataはdomain正本ではなく通常commit対象にしない。

closeしたrecovery recordはresumeの対象ではない。completedとしてcloseしたmutationは、自分が今回作成したそのrecord自身を削除する。削除してよいのは次をすべて示せる場合に限る:

```text
そのrecordを今回の実行が作成し、既存recordをresumeしていない
top-level fieldが、closeしたrecordのfield setと完全一致し、versionがint型そのものである
通常のregular fileであり、link等の間接参照ではない
Gitのindexにも HEADにも存在しない（判定できないgit呼び出しは「存在する」として扱う）
内容が、そのmutationが最後に書いたものと完全一致する
```

1つでも示せない場合はrecordを残す。削除はそのoperation自身の後始末でありresultではないため、削除の失敗をoperationの失敗として扱わず、そのためにdomain effectを再実行しない。pending recordとabandoned recordは削除しない。他のmutationが残したrecordも削除しない。保持期間・件数上限・古いrecordの一括cleanupは設けない。

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

同じmutationのrecordが、適用済みと記録したrelationの追加と、それより後のstageで記録した同じrelation（同じrelation file、IDとrecordのすべてのfield）の削除を持つ場合、そのrelationが正本に無いことはその自分の削除で説明できるので、追加を未適用として書き戻さず一致とする。削除自体の適用済みは問わない（削除を書いた後、適用済みを保存する前に中断した場合を含む）。削除を記録した後・適用する前に人がそのrelationを記録どおりに消した場合も、これと区別できないので同じ扱いになる。未適用とすると、削除の後のresumeのたびにrelationを書き戻して削除し直し、その間で止まればrelationが戻ったまま `reconcile required` から抜けられないためである。IDやrecordが一致しないrelation（同じtype / from / toのものを含む）、適用済みと記録していない追加、追加より前や同じstageにある削除、recordの削除で説明できない変更は、このmutationのものと推測せず従来どおり分類する。

記録済みのstageが、そのrequestや決定が記録するものであることを示すために組み立て直す場合、現在の正本から採番し直される表示用の値をその比較に含めない。Workを登録するstageでは、effectのkindとpath、stable Work ID、frontmatterの残りとbody全体、derivation detail、先行発行したrelation / derivation ID、relation payload、記録した順序をすべて完全一致で比べ、Workのdisplay番号だけはそのstage自身が記録した値を使う。displayはProjectがWorkをどう見せるかであり、Workが何であるかではない（uniqueness ruleが無く、何もdisplayでは引かず、重複や欠番でも構造は妥当で、projectionは `W-??` で成立する）。mutationがpendingの間に別のoperationや人が登録したWorkは現在のWork数を変えるので、採番し直すとstageが何も変わっていなくても不一致になり、同じ他人のWorkがstageの記録より前に届いた場合とで同じ中断・同じ計画の結果が変わってしまうためである。resumeが書くdisplayは、そのstageが記録した値のままとし、現在の件数で採番し直さない（欠番や重複が残ることは妥当である）。そのWorkのwriteをstageが持たない、読めない、displayが非空のstringでない場合は、他の差分と同じくstageを示せていないものとして扱う。

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

operation開始前からの未commit変更が、そのoperationが最初のdomain effectより前に分かるcommit対象（STARTとlifecycle決定ではevent log、plan exclusionではevent logとreplanが書くrelation file）と重なる場合、そのGit段階は変更を分離できず必ず停止する。そのためoperation ownerは、event・executor・正本write・commit・pushのどれも行う前に、Git段階が読むのと同じ開始時snapshotで `dirty_overlap` として停止し、effectを記録していないmutationをabandonする。人がその変更をcommitまたは破棄すれば、同じoperationは新しいmutationとして進む。同じfileの中の人の変更と自分の変更をhunk等で分けて自分の分だけcommitすることはしない（operationは人の変更を含むstateで判断している）。effectを記録済みのmutation（この判定より前のimplementationが残したrecordを含む）には後から適用せず、開始時の内容を推測で補わず、従来どおりGit段階で停止する。

operationが最初のdomain effectより前には分からないcommit対象（STARTでexecutorが返す成果path・削除path、executorが返した派生をCREATEへ登録する際に書くrelation file）が開始時snapshotと重なる場合は、その成果・派生を適用する前に同じ `dirty_overlap` で停止する。停止する前に、開始時snapshotのpathがexecutorの実行前に持っていた内容をそのまま戻す（存在しなかったpathは存在しない状態へ戻す）。戻すのは重なったpathだけであり、working tree全体や他の変更は戻さない。directory・link・読めなかったpathは戻さず、戻せなかったことを停止時に示す。派生の登録は、Work file・派生detail・relationを1件も記録・適用する前に判定する。

この停止で、executorが正常終了して返した成果と、重なったpathにexecutorが残していた内容は、そのmutationのrecordへdurableに保存してよい。人がその変更をcommitまたは破棄した後の再実行は、保存した成果を使い、executorを再実行しない。保存するのはこの停止で重なった1つのWorkの成果だけであり、executorの結果一般をcacheしない。recordがそのまま保ちきれない成果（大きすぎる、読み戻せない）は保存せず、従来どおり再実行でexecutorへ問い直す。

開始時snapshotは一度だけ取り、後から広げない（operationが自分のexecutorの出力を開始前からの変更と取り違えないため）。ただしそのrunが何かを書くより前に、snapshotが名指すpathのうち現在は変更されていないものを落とす。人がその変更をcommitまたは破棄すれば、同じmutationがそこから進む。mutation自身が書いたpathであることを理由に落とさない（snapshotはpathだけを持ち、その中の人の変更と自分の変更を区別できないため）。開始前の変更と自分の変更が同じpathにある記録済みmutationは、推測で直さず従来どおり停止する。

operationがpathをownしていることは、そのpathにある現在のbytesをownしていることではない。`git add` と `git commit --only` は渡されたpathにworking treeが持つものをそのままcommitし、operationが持つ根拠は「そのfileのどこかへ自分が書いた」だけなので、operation開始後に他者・別AIがそのpathへ書いた変更も「HEADと違う」点では自分の書込みと同じであり、自分の成果としてcommit・pushされ成功として報告される。そこでoperationは、Project正本fileへ書くたびに、そのpathが書く前に持っていた内容と、自分がそこへ書いた内容を、その書込みと同じrecordへ記録する。effectが書かないのにcommitするpath（STARTのexecutorが返す成果path・削除path、既にoperationが書くはずの内容そのものを持つfile等）は、その内容をoperation ownerがrecordへ記録する。

そのうえで、記録済みeffectを書く直前に、そのfileが現在も自分が最後にそこへ書いた内容（最初の書込みの前はそのstageが記録した書く前の内容）を持つことを確認し、commitを作る直前に、そのcommitが運ぶpathのそれぞれが現在も自分が置いた内容を持つことを確認する。書込みの前にも確認するのは、event logへの追記もrelationの追加・削除によるledgerの再renderも、fileに既にある他者の変更を取り込んでしまい（parseできる記録は自分のstateとして取り込み、再現できない行は消す）、その後はcommit直前の確認では区別できないためである。HEADと同じpathはそのcommitへ何も加えないので確認しない。示せない場合（現在の内容が記録と違う、自分の書込みでないのにHEADと違う、内容を読めない）は、stage・commit・pushのどれも行わず、その変更を書き戻しも削除もせず、recordを変えずに `reconcile required` で停止する。人がその変更をcommitまたは破棄するか、pathをoperation自身が書いた内容へ戻せば、同じoperationは再実行でそこから進む。他者の変更と自分の変更をhunk等で分けて自分の分だけcommitすることはしない（開始前の変更と同じ規定）。他者が自分と同一のbytesを書いた場合は内容として区別できないので、同一の内容はそのoperation自身のものとして扱う。内容についての記録を持たないrecord（この記録より前のimplementationのもの）と、そのpathを書いたeffectが内容を記録していないpathは、推測せず従来どおり扱う。

commitは、commit message・commitするpaths・記録時のHEAD（base）と、記録時にHEADが指していたbranchの完全なref名（`refs/heads/<name>`）をeffectとして記録してから作る。detached HEADで記録したcommitはbranchを持たない。

Project正本へのeffect（event・relation・Roadmap / Phase / Work・Project開始やbackfillが書くfile等）を決定したstageは、そのeffectと同じdurable writeで、決定した所在として、その時HEADが指していたbranchの完全なref名（detached HEADではbranchなし）とHEADのcommit（まだcommitの無いbranchではなし）をeffectに記録する。所在はoperationやmutationの開始時ではなく、effectを決定した時に固定する。STARTがexecutorより前にWorkの実行を開くために記録するlifecycle（`work_started` / `work_resumed` / `work_target_added` だけのstage）は何も決定せず、所在を持たない。STARTの所在は、executorが返した後にそのcycleの完了・hold・cancel・派生等を記録した時に固定されるので、executorの実行中やquestion waitの間にbranchを変えた場合は、変えた後のbranchが所在になる。決定を確定するcommitを記録するまでに同じmutationが記録する別の決定も、同じ所在を持つ。

決定したeffectを確定するcommitを記録するまで、そのmutationは、HEADが決定の所在と同じbranch（detached HEADで決定した場合はdetached HEAD）の上にあり、その履歴が決定した時のcommitを含む（そのbranchが独立なcommit等で進んだだけである）ことを示せる時だけ、記録済みeffectのreplayと、stage・新しいIDの予約・note・write scopeの記録を行う。示せなければ、何もreplay・記録・commit・pushせず、recordを変えずに `reconcile required` で停止する。同じcommitを指す別branchへのcheckout、決定した時のcommitを含まない履歴（amend / reset / rebase等）、branch上で決定したmutationのdetached HEADでの再実行（branchを必要とするoperationは従来どおり入口の `detached_head` で先に停止する）、detached HEADで決定したmutationのbranch上での再実行、Gitが判定できない場合がこれに当たる。別branchで確定したcommitは決定したbranchにもそのremoteにも届かないのに、operationが成功扱いになるためである。決定した所在へ戻れば、同じ再実行がそこから進む。outer STARTは、前のWorkの決定を確定するcommitをこの条件で記録できない限り、次のWork・integration・Phase完了へ進まない。

決定を確定するcommitは決定の所在の上でだけ記録し、そのcommitが記録するbranchは決定の所在のbranchと一致しなければならない。一致しなければcommitを記録せずに停止する。commitを記録した後は、決定の所在ではなく、以下の記録したcommitの条件（message・branch・base・履歴）がそのmutationを扱う。

commitを記録した後の再実行が、そのcommitで確定する適用済みのeffect（event・relation・Roadmap / Phase / Work・Project開始やbackfillが書くfile等）を、現在のworking treeに無いためもう一度書くことになる場合は、そのeffectの直後に記録したcommitが記録したbranchの上でだけ書く。HEADがそのbranchの上に無い（別branch、detached HEAD、GitがHEADのbranchを判定できない）なら、そのeffectを含め何もreplay・記録・commit・pushせず、recordを変えずに `reconcile required` で停止する。commitを作った後・pushの前や、pushの後・operationの完了前に、そのcommitを履歴に含まないbranchへ移って再実行すると、適用済みの正本をそのbranchのworking treeへ書き直し、前のstageの記録済みpushを再実行してから、書き直しで変更が残ったcommitの分類で停止し（記録と同じmessageのcommitがそのbranchにあれば成功扱いになる）、記録したbranchへ戻るcheckoutもGitが書き直しを理由に拒否するためである。記録したbranchへ戻れば、同じ再実行がそこから進む。書き直しが起きない再実行（記録したbranchの上、そのcommitを履歴に含むbranch、Gitがbranchを判定できなくても正本がworking treeにある場合）は変えない。branchを持たないcommit（branchを記録する前のimplementationのrecord等）が確定するeffectはこの条件で推測や停止をせず、以下の条件で従来どおり扱う。

所在を持たない決定（所在を記録する前のimplementationのrecord）は、どこで決定したかを示さない。現在HEADが指すbranchが記録時と同じでも推測せず、確定するcommitを記録するまでは `reconcile required` で停止する。決定を記録する時にGitがHEADのbranchを判定できない場合は、その決定を記録せずに停止する。

記録したcommitが作られたこと（適用済み・期待値一致）は、commit messageの一致だけでは示さない。同じmessageは誰でも、どの内容・どのbranchのcommitにも付けられ、commitの同一性を示さないためである。base以降に記録と同じmessageのcommitがあることを一致の根拠にするのは、そのmutationがそのcommitを既に適用済みとしてrecordに記録している場合（resumeや後続stageでの再分類）だけとする（そのcommitのcommit IDも記録している場合は、記録したbranchの上では次の段落のcommit IDだけで判断する）。適用済みと記録していないcommit（記録した後・作る前の中断、commit自体の失敗、commitを作った直後・適用済みを記録する前の中断）は、同じmessageのcommitが履歴にあっても作られたとはみなさず、記録したpathsにcommitする変更が残っていない場合だけ一致とする。変更が残っていれば、以下のbranch・base・履歴の条件で未適用を示せる時だけ記録どおりのcommitを作り、示せなければ期待値不一致として `reconcile required` で停止する。同じmessageのcommitでも、pathsの一部だけ・別の内容でのcommit、別branchへの切替は、それぞれの条件どおり停止する。commitを作った直後・適用済みを記録する前に中断し、再実行までに記録したpathsが他の変更（内容を書き換えるhookを含む）でdirtyになった場合も、そのcommitがこのmutationのものと示せないので停止する。

mutationが自分でcommitを作った時は、commitが成功した直後のHEADのcommit IDを、そのcommitを適用済みとする記録と同じdurable writeでeffectに記録する。記録するのは、commit前のHEADを唯一のparentとする（まだcommitの無いbranchではparentを持たない）新しいcommitであることをGitが示したcommitだけで、そう示せない場合（hookが続けて別のcommitを作った、HEADを動かした、Gitが判定できない等）はIDを記録しない。後から履歴を探索して別のcommitのIDを推測しない。

commit IDを記録した適用済みのcommitは、HEADが記録したbranchの上にある時（branchを持たないrecordではdetached HEADの時）、そのIDだけで判断する。IDのcommitがHEADから到達可能であることをGitが示せば、保存されたcommit messageが記録と違っても一致とする。Gitはmessageの行末空白・改行・連続空行を整理して保存し、`commit-msg` / `prepare-commit-msg` hookは内容を追加・変更できるため、自分が作ったcommitでも記録と同じmessageを持つとは限らないからである。IDのcommitに到達できない（amend / reset / rebase等で履歴がそのcommitを含まない）、IDを示せない、Gitが判定できない場合は、messageの一致へ戻らず、期待値不一致として `reconcile required` で停止する。HEADが記録したbranchの上にない場合、IDはmutationの残りがどこで続くかを示さないので一致の根拠にせず、IDを持たないcommitと同じくこの節の他の条件で扱う。

commit IDを持たないcommit（commitを作った直後・適用済みとIDを記録する前の中断、IDを記録する前のimplementationのrecord）は従来どおり扱い、保存されたmessageと記録の違い（空白・改行・hookによる追記等）を正規化して一致とはしない。

記録したcommitをmutationが作る前に、そのcommitが運ぶ変更を別主体のcommitが取り込んだ場合（人が散らかったworking treeをまとめてcommitした場合等）、記録したpathsにcommitする変更は残らないので上の「適用済みと記録していないcommit」の規定で一致となるが、mutationはそのcommitを作っていないのでcommit IDを持たない。このとき、mutationはそのcommitを自分のcommitとして採用しない。branchの先端へfallbackせず、messageの一致へfallbackせず、内容の一致だけからcommitの同一性を推測せず、記録したpushを実行せず、`reconcile required` で停止する（Push destination）。これはerrorではなく公開の安全境界である。公開は取り消せないので、自分が作ったと示せないcommitは公開しない。

この停止からの回復は人が行う。別主体のcommitがまだ公開されておらず、かつそれを安全に取り消せる場合は、そのcommitが取り込んだ変更をworking treeへ戻した状態にしてから、同じoperationを再実行する。記録どおりのcommitはWorkline自身に作らせ、pending mutation recordを手で書き換えず、Project正本fileを手で作り直さない。安全なGit操作は履歴の形によって異なるので、特定のcommandを唯一の手順としない（直前の未公開commitだけを戻す単純な場合は `git reset --mixed HEAD~1` がその一例である）。

次のいずれかに当たる場合、Worklineは自動修復しない。人がGitで調整する必要があることを示して停止する。force pushは回復手順にしない。

```text
別主体のcommitが既にremoteへ公開されている
そのcommitの後に別のcommitが積まれている
共有履歴の書き換えが必要になる
どのcommitを戻せばよいかを積極的に示せない
戻すことで他者の変更を失わせる可能性がある
```

記録したcommitを未適用として扱うには、HEADとbaseの関係だけでなく、recordのbranchと現在HEADが指すbranchの整合も示す必要がある。commitを記録した後・作る前に中断したmutation（commit自体の失敗を含む）のresumeで、HEADがまだbaseであることだけでは未適用としない。次を示せる時だけ未適用として、記録どおりのcommitを作る。

```text
recordがbranchを持つ:     現在HEADが指すbranchの完全なref名が、recordのbranchと一致する
recordがbranchを持たない: HEADがdetachedであることをGitが示す
```

HEADがbaseのままでも、同じcommitを指す別branchへのcheckout、branch名の変更、branchを持つrecordでのdetached HEAD（branchを必要とするoperationは従来どおり入口の `detached_head` で先に停止する）、branchを持たないrecordでのbranchの上での再実行、recordのbranchが完全なbranch名でない場合、Gitが判定できない場合は、期待値不一致として `reconcile required` で停止し、commitを作らない。別branchに作ったcommitは記録したbranchにもremoteにも届かないためである。記録したbranchへ戻れば、同じ再実行がGit段階から進む。branchを持たないrecordにはbranchを記録する前のimplementationのrecordも含まれるが、どのbranchで記録したかを推測しない。

commitを記録した後・作る前に中断したmutation（commit自体の失敗を含む）のresumeでは、その間に独立なoperationや人のcommitでHEADがbaseから進んだことだけを期待値不一致としない。記録したcommitが作られておらず（上記の一致に当たらず、pathsにcommitする変更が残っている）、次をすべて示せる場合だけ未適用として扱い、現在のHEADの上に記録どおりのcommitを作る。

```text
recordのbaseが完全なcommit IDで、現在のHEADの祖先である
base..HEADのどのcommitも記録したpathsを変更していない
  （mergeは全parentを辿る。rename検出はしない。途中で変更して元の内容へ戻した履歴も変更とみなす）
現在HEADが指すbranchが、recordのbranchと一致する
```

1つでも示せない場合は従来どおり期待値不一致として `reconcile required` で停止し、commitを作らない。pathsの一部だけ、または別の内容でのcommit、変更して戻した・revertした履歴、amend / reset / rebase等でbaseがHEADの祖先でない履歴、branchの変更、baseやbranchをrecordから示せない場合、Gitが判定できない場合がこれに当たる。branchを記録していない旧implementationのrecordは、同じstageのpush先branch等から推測せず、HEADが進んでいれば停止する。remoteだけが先に進んだ場合（push previewの `!` で `reconcile required`）の扱いは変えない。

START terminal処理は `work_target_removed` / `work_completed` を含む最終commitと、remoteありならその最終pushまでをfinalization mutationとする。local completed / remote未反映時は通常STARTを再実行せず finalization resumeする。

review-v1 planning operationのcommit（generation commit、登録commit Kp、metadata commit Km）は、contained planning commit primitive（`review-v1-planning-local-v1`）で作る。記録したpathsだけを `git commit --only` し、hooksにはWorkline-ownedの空のdirectory（`.workline/runtime/review/no-hooks`）を `core.hooksPath` として渡し、hook・commit署名・background maintenanceのどれも実行しない。review-v1 planningは、最初のReview recordを書く前に、自分のplanning-owned path（登録path、Runのrecord path、Consumption path）と重なる開始時からの変更を `dirty_overlap` で拒否する。

review-v1の登録commit（Kp）は、記録した親（`base_head`）の上でだけ作る（`base_exact`）。`base_exact` は上記のcommit分類から、独立なoperationや人のcommitでHEADがbaseから進んだ場合を未適用として扱う段だけを除き、それ以外の分類は変えない。HEADが記録した親から動いていれば、Kpを作らず `reconcile required`（reason `review_registration_base_moved`）で停止する。

review-v1の登録commitは、その親の上でのexpected physical projection、すなわちcanonical writerが書くbytes（ledger全体を含む）そのものを運ぶ。同じ意味を別のbytesで持つ登録commitは、誰が作ったものでもWorklineは公開しない（Push destination）。

review-v1 planning operationは、その登録が公開された時にだけ成功する（remoteなしではC-2(Km)が通った時）。`not_authorized` または `stale` で終わったoperationは何も登録せず、何も公開しない。そのgeneration commit（sealの後の `stale` ではgeneration 4とSupersessionも）はlocal履歴として残り、そのbranchからの次のpushが運ぶ。

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

承認先はどのrepositoryへpushしてよいかの承認であり、何を公開してよいかの承認ではない。記録したpushが公開するのは、同じGit段階でそのpushの直前に記録したcommitと、そのcommitが作られた土台の履歴だけであり、pushを実行・再実行する時点のlocal branchの先端ではない。pushは、mutationがそのcommitを作った時に記録したcommit IDを `<commit ID>:refs/heads/<branch>` としてpushし、forceしない。そのcommitの後に同じbranchへ積まれたcommitは、人・別tool・別operationのどれのものでも、どのpathを変更していても、中断やquestion waitの間のものでも、そのpushでは公開しない。同じmutationの後のstageがその上に自分のcommitを作れば、そのstageのpushが自分のcommitの履歴として公開する（記録したcommitを独立なcommitの上に作る場合と同じ）。

pushとcommitの対応はGit段階の記録だけで示す。pushはGit段階の唯一のcommitの直後（recordの並びでも `seq` でも隣）に記録された、そのGit段階の最後のeffectである。そのcommitは、mutationが作ったcommitのIDとともに適用済みとして記録され、branchを完全な名前で持ち、pushのbranchはそれと同じである。そのIDのcommitは、parentをちょうど1つ持ち、parentが記録したbaseの子孫であり、記録したpaths以外を変更していないことをGitが示し、記録したbranchがそれを含む。1つでも示せないpush（commit IDを記録する前のimplementationのrecord、commitを作った直後・IDを保存する前に中断したrecord、hookが続けてcommitを作った等でIDを記録できなかったcommit、他者が同じ内容をcommitしたため作らなかったcommit、書き換えたrecord）は、何もpushせずに `reconcile required` で停止する。branchの先端をpushせず、commitを推測で特定しない。公開は取り消せないためである。

resumeは記録したpushを、そのcommitが承認先のbranchでどうなっているかで分類する。確認は、実pushと同じremote名・同じrefspecの `git push --dry-run` で行い、Git自身に同じrewrite解決を1回だけ通させる。

```text
=   up to date          → 公開済み（pushしない）
*   new branch          → 未公開（そのcommitでbranchを作る）
    fast-forward update → 未公開（そのcommitまでだけ進める）
!   rejected            → 承認先を読んで判定する（次の段落）
その他 / 解釈不能        → STOP（推測しない）
transport / auth失敗    → STOP
```

`!` は、承認先のbranchがそのcommitの先へ進んでいる（後のstageのpush、人のpush等で既に公開済み）か、別の履歴を持つかのどちらかである。その区別のためだけに承認先を読み取り専用で読む。Gitが記録済みlocatorを書き換えずにそのまま読むことを `git ls-remote --get-url` で確かめてから、そのlocatorでbranchが指すcommitを読み、このrepositoryに無ければそのbranchの履歴を取得する（refもFETCH_HEADも作らず、working tree・index・HEAD・branchを変えない。どこからも参照されないobjectがobject databaseに増えるだけ）。そのcommitを含めば公開済みとしてbranchをそのまま残し、含まなければ何もpush・forceせずに `reconcile required`。Gitがlocatorを別のURLへ書き換える場合は別のrepositoryを読むことになるので読まずに `reconcile required`。読めない、読んでいる間にbranchが変わった場合はSTOPし、公開済みと推測しない。分類がremoteを書き換えることはなく、remoteを書き換えるのは未公開と分類したcommitの最終的なpushだけである。

resolved locatorを別のGit commandへ引数として渡すのは、この読み取りでGitがそのlocatorを書き換えずにそのまま読むと示した時だけである。`url.<base>.insteadOf` が `pushInsteadOf` の生成したlocatorをさらに書き換え、実push先とは別のrepositoryを読み得るためである。fetch URL側のstateやremote-tracking refも公開済みの根拠にしない。

credentialを含むURLは承認先・回復記録・エラーメッセージのいずれにも残さない。検出時はredactしてSTOPする。

承認先を書き込めるのはProject開始と専用のpin maintenanceだけで、Mutation Controllerがownerを機械的に検査する。AIやdomain operationがcurrent remoteへ承認先を自動追従させない。承認先の追加・変更はProject固有ルール変更として人間確認の対象。

Worklineが保証するのは「どのrepositoryへpushするか」までである。HTTPS credential account、SSH authentication identity、credential managerが選ぶaccount、provider CLIのlogin accountは保証しない。remote destination確認済みをaccount確認済みとして報告しない。

durable invocationが `review-v1-planning-publication-v1` を名指すmutation（review-v1 planning mutation）のpushは、それ自身のstage（`review-publication`）であり、payloadが名指すcommit（metadata commit Km）だけを `<commit ID>:refs/heads/<branch>` として公開する。このstageは、C-2(Km)（committed planning proofを含む）が通った後にだけ記録する。上記のcurrent-combinedの規定は、それ以外のすべてのmutationについて変わらない。どちらの規定に従うかはdurable invocationだけが決め、stageの形や内容からは決めない。planning mutationのcommitとpushを同じstageにしたもの、generation mutationのpush、markerが不完全・未知のmutationのpushは、何もpushせずに `reconcile required` で停止する。

どのoperationのpushも、review-v1 planningの登録commitを履歴に含むcommitを、committed planning proof（`skills/review`）がそのcommitについてその登録のRunを証明しない限り公開しない（publication barrier）。

- pushを含むstageを記録する前（HEADについて）、記録済みpushのdry runが書き込み（`*` / 空白）を示す時、pushの直前に評価する。stageを記録する前に拒否されたoperationは、domain effectを適用したままpending mutationとして待ち、barrierが解けた後に続ける。
- 承認先が既に持つpush（`=`、または `!` で承認先がそのcommitを含む）は何も公開しないので拒否しない。承認先について読んだものを証明として扱わない。
- 履歴のどのcommitも `.workline/review/candidate-snapshots/` に触れていない履歴は、fast-path read（`git rev-list --full-history -n 1 <C> -- .workline/review/candidate-snapshots/`）で通す。どのGitもこれに答え、P2の最小versionを要しない。この読み取りに答えられなければ通さない。
- それ以外の履歴は、`P2_PUBLICATION_GIT_MIN` 以上のGitでだけ分類する。そこでは登録commitを持たないCandidate snapshotはbarrierを始めない。それ未満、またはversion不明のGitでは、登録が見つかったからではなく証明を実行できないために、その公開を `review_publication_barrier` で拒否する。

### Git versions（review-v1 planning）

`rules/git` は2つの閾値をownする。

```text
P2_REVIEW_GIT_MIN      = 2.40.0   review-v1 planningのGit semanticsを実行する最小version
P2_PUBLICATION_GIT_MIN = 2.31.0   publication proof（barrierのregistered-Run discoveryとcommitted planning proof）を評価する最小version
```

- `P2_REVIEW_GIT_MIN` より古いGit、またはversion不明のGitでの明示的なreview-v1 planning invocationは、lockより前に `review_git_unsupported` で停止し、何も開始せず、pending mutationも変えない。
- `P2_PUBLICATION_GIT_MIN` より古いGit、またはversion不明のGitでは、fast pathが通さない履歴のpushを `review_publication_barrier`（証明不能。Runも登録commitも名指さない）で拒否する。
- legacy operationは、planning Candidate snapshotを一度も持たない履歴について、今日より新しいGitを要しない。

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

terminal Work（completed / cancelled / plan_excluded）のRelatedも、そのWorkが当時読む / 満たす必要があったもののhistorical factとして保護する。後続Workがtargetを正式に削除しても、edgeを削除・書換えしない。現在のread obligationはterminalでないWorkのRelatedだけである。

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

Relatedのread obligationは、from Workが実行し得る間だけ現在の義務である。

```text
from Workがterminal（completed / cancelled / plan_excluded）
→ そのRelatedは当時何を読む必要があったかのhistorical evidence
→ 記録のまま保持し、現在のfilesystemへ合わせて書き換えない
→ targetが現存しないことだけを理由にbroken referenceとしない

from Workがterminalでない
→ 現在のread obligation
→ must_read / 条件が現在成立しているconditional_must_read / obey chainのtargetは
   そのWorkを実行する前に一意解決できなければならない
→ 解決できなければSTOPし、推測で無視せず代替も探さない
```

Workline自身のoperationは、実行し得るWorkの現在のread obligationを壊す状態を自分で作らない。

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

## REVIEW
<!-- workline-id: skills/review -->
<!-- workline-target: .claude/skills/review/SKILL.md -->
<!-- workline-context: project -->
