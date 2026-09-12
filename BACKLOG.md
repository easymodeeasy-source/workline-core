# Workline Improvement Backlog

## Authority

- このファイルはWorkline仕様の正本ではない。
- normative authorityは `registry.md` と、registryがroutingするcanonical Skills（`.claude/skills/<name>/SKILL.md`）だけである。
- backlog itemは未採用の候補であり、ここに記載されているだけでは仕様・rule・behaviorにならない。
- ある項目が実装済みになっても、canonical authority（`registry.md` / canonical Skills）へ反映されるまではnormative ruleとして扱わない。
- このbacklogはWorklineのRoadmap / Phase / Workではなく、Workline lifecycleでは管理しない。

## Conventions

- 各項目は `BL-001` 形式のstable IDを持つ。表示順を変えてもIDを振り直さず、再利用もしない。
- `Status` は現在分かっていることの区分であり、ticket lifecycleではない。
  - `OPEN`: 追加・改善したい能力。欠陥の再現を前提としない。
  - `VERIFIED`: 問題（欠落・欠陥）の実在を、現行実装または実運用で確認済み。解決済みという意味ではない。
  - `INVESTIGATE`: 問題の実在・原因・規模・方針のいずれかを、先に調査する必要がある。
  - `DEFERRED`: 実例や前提条件が揃うまで、意図的に保留している。
  - `RESOLVED`: 対応がcanonical authority（`registry.md` / canonical Skills）と実装へ反映済み。以後の正本はcanonical authorityであり、この項目は経緯の記録として残す。
- `Evidence class`:
  - `real-project migration`: 既存の実ProjectをWorklineへ移行した際に観測した。
  - `smoke test`: Workline検証用Projectでのsmoke testで観測した。
  - `code inspection`: 現行のworkline-core（実装・canonical仕様・repository状態）の確認で特定した。
  - `design deferral`: 設計段階で意図的に後回しにした論点。
  - `self-hosting assessment`: workline-coreのself-hosting診断で特定した。
- このrepositoryはpublicである。private Projectの名称・識別子・固有仕様・ファイル名・commit、ローカルの絶対パス、AI sessionログからの引用、個人情報・認証情報は書かない。private Projectでの発見は `real-project migration` 程度に一般化する。

## Notes

- remoteを持つProjectで、承認済みpush destinationへのpushを伴うoperationは、real-project migrationで実走済み（real-project path verified）。open itemにはしていない。

## Index

| ID | Title | Status |
|---|---|---|
| BL-001 | Foreign Project mutation boundary | RESOLVED |
| BL-002 | Work completion automatic review | OPEN |
| BL-003 | Phase completion automatic review | OPEN |
| BL-004 | Review finding classification / convergence | OPEN |
| BL-005 | Review / achievement evidence durability | VERIFIED |
| BL-006 | Read-only status/context command | OPEN |
| BL-007 | Cold-start recovery performance | INVESTIGATE |
| BL-008 | Python interpreter resolution | RESOLVED |
| BL-009 | Historical deleted Related / must_read semantics | RESOLVED |
| BL-010 | Generated artifact hygiene | RESOLVED |
| BL-011 | Reusable migration procedure | OPEN |
| BL-012 | Unsupported self-hosting guard | RESOLVED |
| BL-013 | Self-hosting readiness | DEFERRED |
| BL-014 | Deterministic tie-break among startable candidates | VERIFIED |
| BL-015 | Silent no-op on Phase re-entry | RESOLVED |
| BL-016 | Default result commit message type | RESOLVED |
| BL-017 | Declared write scope broader than actual writes | RESOLVED |
| BL-018 | Unused assignment in Phase expansion | RESOLVED |
| BL-019 | Runtime recovery record retention and ignore policy | RESOLVED |
| BL-020 | Correction of mis-recorded historical facts | DEFERRED |
| BL-021 | Concurrent operation exclusion | RESOLVED |
| BL-022 | ProjectSTART abandoned pre-effect recovery | RESOLVED |
| BL-023 | Phase expansion cannot resume after an interruption | RESOLVED |
| BL-024 | Resume invocation does not bind decided content | RESOLVED |

## Items

### BL-001 Foreign Project mutation boundary

- ID: BL-001
- Title: Foreign Project mutation boundary
- Status: RESOLVED
- Kind: design, spec, implementation
- Problem: あるrepository（Workline rootや別のProject）を開いたsessionから、別のWorkline Projectへのmutation（Project開始、Roadmap操作、bootstrap backfill等）をそのまま実行できる。現行の仕様・実装にはsessionとProjectの対応（session/Project affinity）という概念がなく、各operationは渡された任意のProject rootへ書き込む。別Projectをreadすることは許容し得るが、readとwriteの境界、別Projectへのwriteに明示的なoverrideを要求するかどうかが定義されていない。
- Why it matters: 意図しないProjectへの書込み、operation ownerや実行文脈の取り違え、canonical implementationを使わない手作業の構造再現につながる。real-project migrationでは、別のrepositoryを開いたsessionから移行対象Projectへのmutationが行われ、手作業での構造再現（後に巻き戻し）も発生した。
- Likely scope: readとwriteの境界、session/Project affinity、明示的overrideの要否の設計。`rules/git`（operation ownerと書込範囲）、Project側bootstrapと `skills/project-router` の入口規則、Workline root側から他folderへ行うpre-project操作（`skills/project-start`）との整理、CLI / Python APIのentry check。設計段階で保留したmulti-repo Project / 1 repositoryに複数Project（現行原則は 1 Project ≒ 1 repository）の論点もここで扱う。
- Cross-project impact: あり（全Projectのoperation entry）
- Backfill likely: 可能性あり（Project側bootstrapや入口規則を変える場合）
- Human confirmation likely: yes（共通ルールの変更、書込可能範囲の変更）
- Self-hosting prerequisite: yes（BL-013 の session / Project context rule）
- Evidence class: real-project migration, code inspection, design deferral, self-hosting assessment
- Resolution: 成立済みProjectへのstate-changing operationを、top-level operation開始時の作業directoryから1回だけ解決するinvocation Project contextがtarget Projectと一致する場合だけ許可した（session identityは使わない）。一致しなければProject execution lockより前に `foreign_project_mutation` でSTOPし、lock・mutation intent・event・relation・entity・Gitのいずれにも書き込まない。照合の後にexecution lockを取り、その後でmutationを行う。別Projectのread-only参照は許可する。Project開始は、別の成立済みProjectのcontextからでなく、成立済みProjectの配下でもないtargetに限るpre-project例外とし、そのmutationはProject開始の実行が対象rootに与えた許可の内側でだけ受け付ける（owner名だけによる免除は廃止）。overrideは設けない。作業directory由来のcontextは誤操作を防ぐmechanical guardであり、security sandboxではない。multi-repo Projectの設計は扱っていない。`rules/git` とcanonical Skillsへ反映済み。

### BL-002 Work completion automatic review

- ID: BL-002
- Title: Work completion automatic review
- Status: OPEN
- Kind: spec, implementation
- Problem: Work完了時の確認は、機械的に検査できるcompletion precheck（must_update / realizes / result path / dependency / 構造validation）に限られる。成果・diff・verification結果・「このWorkで成立させる状態」との整合を自動でレビューする仕組みがなく、レビューはWorklineの外で都度行われている。
- Why it matters: 構造上PASSでも成立状態を満たさないWorkがcompletedになり得る。completedはterminalで戻せないため、見逃した欠陥は後からfix Workとして扱うしかない。real-project migrationでは、completedになったWorkの欠陥が、後続の第三者レビューで初めて見つかった。
- Likely scope: `skills/start` のcompletion precheckとSTART実装の完了経路、レビュー対象（成果 / diff / verification / desired state）と判定の扱い、BL-004（分類と収束）・BL-005（証跡の保存）との接続
- Cross-project impact: あり（全ProjectのSTART完了挙動）
- Backfill likely: no（既存のcompleted Workは再判定しない想定）
- Human confirmation likely: yes（START completion semanticsと自動実行境界の変更）
- Self-hosting prerequisite: no
- Evidence class: real-project migration, code inspection

### BL-003 Phase completion automatic review

- ID: BL-003
- Title: Phase completion automatic review
- Status: OPEN
- Kind: spec, implementation
- Problem: Phase completeはeventではなく生成状態であり、条件はeffective current-plan Workの完了、integrationの存在、構造validation等の機械的条件に限られる。単体Workの再レビューではなく、Phase全体としてintegration・authorityの整合・lifecycleの妥当性・欠落した責務（どのWorkも担っていない成立条件）を確認する仕組みがない。
- Why it matters: 個々のWorkがPASSでも、Phaseの「成立させたい状態」を満たさないままRoadmapへ戻り得る。real-project migrationでは、Phase単位のレビューで、個々のWork完了時には検出されなかった欠陥が見つかり、追加Workで対応した。
- Likely scope: Phase completionの生成条件、`phase_integration_check` Workの意味と確認範囲、`skills/start`（outer continuation）と `skills/roadmap`（Phase完了後の復帰）
- Cross-project impact: あり（全ProjectのPhase完了判定）
- Backfill likely: no
- Human confirmation likely: yes（Phase completion semanticsの変更）
- Self-hosting prerequisite: no
- Evidence class: real-project migration, code inspection

### BL-004 Review finding classification / convergence

- ID: BL-004
- Title: Review finding classification / convergence
- Status: OPEN
- Kind: procedure, spec
- Problem: review結果の分類と収束条件が定義されていない。findingを少なくとも `VALID DEFECT` / `IMPROVEMENT` / `FALSE POSITIVE` / `REQUIREMENT CHANGE` 等に分類しないため、改善提案や誤検出まで成果物の修正要求として扱われ、review → 修正 → 再reviewのloopが収束しにくい（Review Loopの非収束）。
- Why it matters: 不要なartifact revisionが増え、完了判定が遅れる。分類が場当たりになると、同じ種類のfindingの扱いがreviewごとに変わる。real-project migrationでは分類をその都度定義しており、reviewが報告した該当箇所数と実際の該当数が食い違う場面もあった。移行に伴うWorkline側の修正でも、同じ論点で複数回のreview往復が発生した。
- Likely scope: 分類の定義と各分類の扱い（例: `VALID DEFECT` だけを修正必須とする、`IMPROVEMENT` は候補として記録する、`FALSE POSITIVE` は根拠付きで棄却する、`REQUIREMENT CHANGE` は `rules/human-confirmation` へ接続する）、収束条件、BL-002 / BL-003 での利用、分類結果の記録（BL-005）
- Cross-project impact: あり（review手順を共通化する場合）
- Backfill likely: no
- Human confirmation likely: yes（review手順を共通ルールやcanonical Skillへ入れる場合）
- Self-hosting prerequisite: no
- Evidence class: real-project migration

### BL-005 Review / achievement evidence durability

- ID: BL-005
- Title: Review / achievement evidence durability
- Status: VERIFIED
- Kind: spec, implementation
- Problem: `work_completed` / `roadmap_achieved` 等のeventは id / type / entity / at だけを持ち、なぜPASS / achievedと判定したのか、どのverification / evidenceを使ったのかを保存しない。Roadmap achievement判定の判断内容も永続化されない。mutation recovery recordはruntime領域にありcommit対象外のため、証跡の保存先にはならない。
- Why it matters: 判定の根拠がWorklineの記録の外にしか残らず、fresh sessionや第三者が完了・達成の妥当性を後から検証できない。eventの時刻は記録時刻であり、検証を実施した時点と一致しない場合もある。real-project migrationでは、完了判定に使ったverification結果や第三者レビューの結果がWorklineの記録に残らなかった。
- Likely scope: 何を・どこまでdurableに残すか（判定理由、使用したverification、review結果と分類）、event / record schema、`skills/start` と `skills/roadmap`（achievement）の証跡規則、derivation detailに類する証跡文書の置き場、public repositoryに残さない情報の扱い
- Cross-project impact: あり
- Backfill likely: no（過去の判定根拠は再構成しない想定。schema互換の検討は必要）
- Human confirmation likely: yes（canonical schema / 共通ルールの変更）
- Self-hosting prerequisite: no（self-hosting時の記録価値には直結する）
- Evidence class: code inspection, real-project migration

### BL-006 Read-only status/context command

- ID: BL-006
- Title: Read-only status/context command
- Status: OPEN
- Kind: interface
- Problem: 現在の状態を取得するcanonicalなread-only interfaceがない。CLIはregistry / Project validation、Project開始、push destination pin、bootstrap backfill、standalone Work作成だけを提供し、Roadmap / Phase / Workの状態取得にはPython APIを直接呼ぶ必要がある。Claude等のAIは、その都度sourceを読みながら状態取得方法を再構築している。
- Why it matters: 状態確認のたびに実装の読解が必要になり、recoveryが遅くなる（BL-007）。読み方の誤りが起きやすく、read目的の手組みコードがmutationを伴うAPIに触れる余地もある。smoke testとreal-project migrationの双方で、状態確認のためのコードをその場で書いていた。
- Likely scope: 例えば次をread-onlyで返すcanonical interface（CLI subcommand等）: Project、Roadmap / Phase、current target、next startable、pending mutation、validation結果、execution authority（どのregistry / canonical Skill / 実装で動作しているか）、Git branchとapproved push destination。mutationを開かないこと、networkへ接続しないことを保証する。
- Cross-project impact: あり（全Projectが使う入口になる）
- Backfill likely: no（Project側bootstrapから案内する場合は可能性あり）
- Human confirmation likely: no（read-onlyで、実行能力・外部接続・書込範囲を広げない場合）
- Self-hosting prerequisite: no
- Evidence class: smoke test, real-project migration, code inspection

### BL-007 Cold-start recovery performance

- ID: BL-007
- Title: Cold-start recovery performance
- Status: INVESTIGATE
- Kind: implementation, interface
- Problem: fresh sessionでProjectの現在地を回復するまでに長い時間がかかる。bootstrap → registry validation → router → Skill読込 → 状態取得の各段と、実装内で繰り返される全entity読込・構造validation・Git status呼出しのどこに時間を要しているかは計測されていない。
- Why it matters: 「fresh sessionが正本だけから現在地を回復できる」というWorklineの前提の実用性を下げ、長い回復時間は手順の省略や推測を誘発する。real-project migrationでは、fresh sessionからのrecoveryに要した時間の長さが（欠陥ではないが）改善候補として挙がった。
- Likely scope: performance measurement（段階別の所要時間、Project規模・record数との関係）、bootstrap / routing手順、状態読込とvalidationの重複、Git呼出し回数、BL-006との統合
- Cross-project impact: あり（全Projectのrecovery）
- Backfill likely: no（Project側bootstrapの手順を変える場合は可能性あり）
- Human confirmation likely: no（routingの意味やauthorityを変えない高速化の場合）
- Self-hosting prerequisite: no
- Evidence class: real-project migration, code inspection

### BL-008 Python interpreter resolution

- ID: BL-008
- Title: Python interpreter resolution
- Status: RESOLVED
- Kind: interface, procedure
- Problem: 実装は `requires-python >=3.11` を要求するが、環境の既定 `python` がそれ未満の場合がある。READMEの起動手順は `python -m workline.cli` だけで、install方式や使うinterpreterを定めていないため、実行のたびに対応するinterpreterの探索とimport path（`PYTHONPATH` 等）の指定が必要になる。Roadmap / START等の操作にはCLI entryがなく、Python APIを直接呼ぶ必要もある。
- Why it matters: Claude等のAIが毎回interpreter探索とimport path設定をやり直すことになり、誤ったinterpreterでの失敗や、どの実装コードが実行されたかの曖昧さが生じる。canonical implementation firstの原則上、実装を起動できなければSTOPになるため、起動手順の不安定さがそのまま作業停止につながる。smoke testとreal-project migrationの双方で都度の起動設定が必要になり、既定interpreterでは実装をimportできない失敗も発生した。
- Likely scope: canonical runtime / launcher / interpreter policy（install方式、entry point、interpreter選択規則、version検査）、READMEやcanonical Skillに書く起動手順、CLI entryの範囲（BL-006と連携）。smoke testで挙がった「PYTHONPATHとCLIの使い勝手」の指摘はこの項目へ統合した。
- Cross-project impact: あり（全Projectからの実装起動方法）
- Backfill likely: 可能性あり（Project側bootstrapから起動手順を案内する場合）
- Human confirmation likely: yes（実行環境・launcher等のtooling構成の変更）
- Self-hosting prerequisite: partial（BL-013 の runtime / development separation と関係する）
- Evidence class: smoke test, real-project migration, code inspection
- Resolution: Workline root直下のcanonical source launcher（`run-workline.py`）から起動する形を正式にした。installせずWorkline rootの `src/workline` を実行し、Python 3.11以上（exact versionは固定しない）とisolated invocation（`-I`、bytecodeを書かない）を要求する。launcherと実装内の照合は、実際にloadされたimplementationのoriginとconfigured Workline rootを比べ、不一致・証明不能は成立済みProjectのexecution lockより前に何も書かずSTOPする（Project開始・validate-projectも同様）。CLIの無いoperationは、同じprocessでactivateした後にだけAPIをimportする。ambient install・editable install・PYTHONPATHには依存せず、project.yaml schema・bootstrap・intent / event形式は変えず、既存Projectのbackfillは不要。committed / released versionやruntime / development separationは扱っていない（BL-013）。security sandboxではない。`rules/git` とcanonical Skills、READMEへ反映済み。

### BL-009 Historical deleted Related / must_read semantics

- ID: BL-009
- Title: Historical deleted Related / must_read semantics
- Status: RESOLVED
- Kind: spec, implementation
- Problem: completed Workの `must_read` 等のRelated targetが、後続のWorkで意図的に削除された場合の意味が定義されていない。historical evidence（そのWorkが当時何を読んだか）と、現在の参照が有効か（current validity）を区別する規則がなく、構造validationはRelated targetの存在を検査しない。意図的なtracked file削除はWork resultとして扱えるようになり、must_update / realizesでの扱いは定義済みだが、must_readを含む履歴側Relatedの扱いは未定義のまま。started / completed等のWorkに対するRelated maintenanceも、現行仕様では定義していない。
- Why it matters: 削除済みtargetを指す履歴参照を「壊れた参照」と誤判定するか、逆に死んだ参照を現在の読取計画に残すかの判断が場当たりになる。旧authorityを退役させる移行では、履歴Relatedのtarget削除が必ず起きる。real-project migrationでは、completed Workのmust_read targetが後続Workで意図的に削除され、その扱いを都度判断した。
- Likely scope: historical evidenceとcurrent validity validationの分離、`rules/information-tracing`（読取順とhistorical参照）、`skills/start` / `skills/roadmap` のRelatedの意味、構造validation、reading planの生成
- Cross-project impact: あり
- Backfill likely: no（意味を定義するだけの場合）
- Human confirmation likely: yes（canonical semanticsの変更）
- Self-hosting prerequisite: no
- Evidence class: real-project migration, code inspection
- Resolution: Related edgeを、from Workが実行し得る間の現在のread obligationと、terminal Work（completed / cancelled / plan_excluded）のhistorical evidenceに分けた。historical側は記録のまま保持し、後続Workがtargetを正式に削除してもedgeを削除・書換えせず、targetの不在だけでstructure validationをfailさせない。現在側は、STARTがWorkを実行する前にmust_read / 条件が現在成立しているconditional_must_read / obey chainのtargetを解決し、解決できなければlifecycle event・executor実行・Git書込みより前に `related_target_missing` でSTOPする（推測で無視せず、filename / mtime / 意味類似での代替も自動修復もしない）。Workline自身がこの状態を作らないよう、deletion resultが他のstarted（in_progress / held）non-terminal Workの現在のread targetを消す場合はcompletion precheckで失敗させる。削除するWork自身はtargetが存在する状態で開始しているため対象外。未開始Workは従来どおりRoadmapのRelated maintenanceで計画修正し、started Work用のRelated編集経路は新設していない。既存Projectへも即時適用し、grace periodやlegacy modeは設けない。historical record自体の訂正はBL-020へ要件として追記した。relation type・record schema・project.yaml・event・backfillの変更なし。`rules/information-tracing` / `rules/ai-decision` と `skills/start` / `skills/roadmap` へ反映済み。

### BL-010 Generated artifact hygiene

- ID: BL-010
- Title: Generated artifact hygiene
- Status: RESOLVED
- Kind: hygiene
- Problem: workline-coreに `.gitignore` がなく、test実行やpackage metadata生成で作られる `__pycache__/`、`*.egg-info/` 等がuntrackedとして作業ツリーに残る。
- Why it matters: `git status` のdirty noiseになり、意図した変更の確認を読みにくくし、誤ってcommitされる余地を残す。
- Likely scope: workline-coreの生成物policyと `.gitignore`（Python bytecode、packaging metadata、test cache等）
- Cross-project impact: no（workline-core repositoryのみ。Project側のruntime recordはBL-019）
- Backfill likely: no
- Human confirmation likely: no
- Self-hosting prerequisite: no
- Evidence class: code inspection, self-hosting assessment
- Resolution: repository rootへ `.gitignore` を追加し、実測で生成を確認した `__pycache__/`、`.pytest_cache/`、`*.egg-info/` の3 patternだけをignore対象にした。genericなPython templateは使わず、このrepositoryが生成しない `build/`、`dist/`、`.coverage`、`.mypy_cache/` 等は入れていない。READMEのdevelopment test例も `py -3 -B -m pytest tests -q` にし、`-B` はworking treeへbytecode cacheを残さないためのdevelopment hygieneであって、Runtimeの起動条件ではないことを明記した。ただし主たる修正は `.gitignore` である。test suiteはcanonicalでない起動形を検証する子processを起動するため、`-B` を付けたfull runでも `src/workline/__pycache__` に23件が残ることを実測した。tracked file全件がignoreされないことを機械的に確認しており、正本である `registry.md` とcanonical Skillsが隠れることはない。既にworking treeにある生成物は削除していない。このrepositoryの履歴で一度もtrackedになっていないためindexから外す必要がなく、手元のcopyは各開発者の持ち物だからである。`pyproject.toml`、`registry.md`、canonical Skillsは変更しておらず、canonical runtimeのsemanticsは変わらない。canonical runtimeが `-B` の有無にかかわらずbytecode cacheを書かないのは、launcherがWorkline importの前に `sys.dont_write_bytecode` を設定するためであり、既存のcanonical記述が正しいことを実測で確認した。workline-core repository自身のdevelopment hygieneであり、Projectへ及ぶ影響はない（Workline operationがProjectのignore設定を書かない規則はBL-019）。

### BL-011 Reusable migration procedure

- ID: BL-011
- Title: Reusable migration procedure
- Status: OPEN
- Kind: procedure
- Problem: 既存Projectを旧authority（Workline以前の手順・文書・自動化）からWorklineへ移す手順が、再利用可能な形で存在しない。最初の移行は、その場の指示とRoadmap設計で進められた。
- Why it matters: 移行のたびに手順を設計し直すと、ownership inventoryの漏れ、local safety ruleの喪失、旧authorityとの二重正本、standalone recoveryの未確認が起きやすい。
- Likely scope: 再利用可能なprocedure / checklist: ownership inventory（どの文書・Skill・自動化が何のauthorityか。project-local Skillの棚卸しと扱いを含む）、local safety preservation、current state migration、legacy authority retirement、standalone recovery（fresh sessionが正本だけから回復できるか）、final achievement。置き場（非正本のguideか、canonical Skill / ruleか）も決める。設計段階で保留したProject-specific Skillの標準配置の論点はここで扱う。
- Cross-project impact: あり（今後の移行すべて）
- Backfill likely: no
- Human confirmation likely: yes（canonical Skill / 共通ルールにする場合。非正本guideなら不要）
- Self-hosting prerequisite: no
- Evidence class: real-project migration, design deferral

### BL-012 Unsupported self-hosting guard

- ID: BL-012
- Title: Unsupported self-hosting guard
- Status: RESOLVED
- Kind: implementation, spec
- Problem: Project開始は、Project rootとWorkline rootが同一（Project root == Workline root）であることを拒否しない。self-hostingは正式にサポートされていないが、現状では機械的に初期化できてしまう。
- Why it matters: 意図せずWorkline root自身がProjectになると、変更対象と、それを統治・回復するrule / 実装が同じ作業ツリーに入る（循環）。さらに、Workline root側から行うpre-project操作と「成立済みProjectの内側」という文脈が衝突する（BL-013）。
- Likely scope: self-hostingを正式サポートするまでの扱いとして、STOP / explicit human confirmation / unsupported-mode validation のどれを採るべきかを調査する。Project開始と既存Project向けmaintenance経路での検出、BL-013の再評価条件との結び付け。
- Cross-project impact: no（通常Projectの開始挙動は変えない想定）
- Backfill likely: no
- Human confirmation likely: yes（Project開始の拒否条件の追加はcanonical Skillの変更）
- Self-hosting prerequisite: yes（正式サポートまでのguard）
- Evidence class: code inspection, self-hosting assessment
- Resolution: Project rootとそのWorkline rootが別の実体directoryだと証明できない配置を、現在のWorkline rulesではサポートしないself-hostingとして扱うguardを入れた。判定はfile identity（`os.path.samefile` 相当）で行い、同じdirectory、または両方存在するのに判定できない場合はfail-closedで `workline_self_hosting_unsupported` としてSTOPする。Project開始はpre-project contextの確認の後、git init・`.workline`・bootstrapより前に止まる。既にこの配置の成立済みProjectでも、state-changing operationはProject contextの後、Workline implementation照合とexecution lockの前に止まり、何も書かない。読み取りは引き続き可能で、validate-projectはこの配置をproblemとして報告しPASSにしない。overrideや自動修復は設けず、project.yaml・bootstrap・intent / event形式は変えず、既存Projectのbackfillは不要。self-hostingの正式サポートはBL-013で扱う。`rules/git` とproject-start Skill、READMEへ反映済み。

### BL-013 Self-hosting readiness

- ID: BL-013
- Title: Self-hosting readiness
- Status: DEFERRED
- Kind: design
- Problem: workline-coreをWorkline自身で管理する（self-hosting）前提が揃っていない。現時点ではself-hostしない判断をしており、次の条件が揃った時点で再評価する。
  - runtime / development separation（他Projectを統治する実装と、開発中の作業ツリーの分離）
  - release boundary（どの版がProjectを統治するか。設計段階で保留したbranch strategyを含む）
  - intent format compatibility policy（mutation recovery recordの形式互換）
  - break-glass / repair / reconcile path（実装が壊れた時の修理手順と、記録との突き合わせ）
  - session / Project context rule（Workline root側の操作とProject内の操作の区別。BL-001）
  - public/private disclosure policy（public repositoryへ計画記録を置く範囲）
  - portable root handling（Project設定に保存されるWorkline rootの絶対pathの可搬性）
- Why it matters: 前提なしにself-hostすると、Workが自身の完了条件を統治するruleや実装を変更でき、recovery recordの形式変更で自身のpending mutationを再開不能にし得る。実装が壊れた時は、manual fallbackを禁じる原則によりWorkline経由での修理ができない。また、全Projectが共有するWorkline rootの作業途中状態が各Projectへ露出する。real-project migration中にも、Workline root側の破壊的変更により、移行途中のProjectでmaintenance操作が必要になった。
- Likely scope: 上記条件ごとの設計、BL-012のguard、BL-001 / BL-008 / BL-019 との整合
- Cross-project impact: あり（Workline rootを共有する全Project）
- Backfill likely: 可能性あり（root handlingや実行環境を変える場合）
- Human confirmation likely: yes
- Self-hosting prerequisite: n/a（この項目自体が再評価条件）
- Evidence class: self-hosting assessment, real-project migration, design deferral

### BL-014 Deterministic tie-break among startable candidates

- ID: BL-014
- Title: Deterministic tie-break among startable candidates
- Status: VERIFIED
- Kind: spec, implementation
- Problem: startable Work（またはPhase）が複数ある場合、仕様は人間の明示意図・planned_next・dependency・priority・parallel safety等から選ぶと定めるが、最後のtie-breakが実装上の候補listの先頭になっている。START outer continuationの次Work選択、Roadmapのhandoff / Phase entryでのentry Work選択、startable Phaseの選択が該当する。
- Why it matters: 選択結果が実装の内部順序に依存し、仕様から予測・再現できない。候補の並び順を変える実装変更で、挙動が黙って変わる。
- Likely scope: `skills/roadmap` / `skills/start` の複数候補時の最終規則（現行順序の明文化か、新しい決定規則か）、START next Work選択、Roadmap handoff / Phase entry / Phase選択の実装とtest
- Cross-project impact: あり（選択結果が変わり得る）
- Backfill likely: no
- Human confirmation likely: yes（選択規則の意味を変える場合。現行順序の明文化だけなら不要）
- Self-hosting prerequisite: no
- Evidence class: smoke test, code inspection

### BL-015 Silent no-op on Phase re-entry

- ID: BL-015
- Title: Silent no-op on Phase re-entry
- Status: RESOLVED
- Kind: interface, implementation
- Problem: 既にWorkが展開されたPhaseへPhase entryを再実行すると、重複展開はしない（仕様どおり）が、渡したWork設計が既存構造と食い違っていても検証も警告もされずに無視される。結果には「展開しなかった」ことを示すflagがあるだけで、呼び出し側が見落とすと、意図したWorkが登録されたと誤認し得る。
- Why it matters: 別Phaseの設計を取り違えて渡す等の誤りを検出できず、計画と正本がずれたまま実行へ進む可能性がある。
- Likely scope: 再entry時の結果（食い違いの検出・警告・STOPの要否）、`skills/roadmap` のPhase entry記述、test
- Cross-project impact: あり（Roadmap APIの挙動。影響は小さい）
- Backfill likely: no
- Human confirmation likely: no（診断を追加するだけの場合。STOPへ変える場合はyes）
- Self-hosting prerequisite: no
- Evidence class: smoke test, code inspection
- Resolution: 既にWorkが展開されたPhaseへ新しいentry designを渡すPhase entryの再実行を、state変更より前に `phase_already_expanded` でSTOPすることにした。designを黙って無視せず、既存entryへ差し替えず、通常成功として返さず、ID発行・mutation開始・canonical state変更・commitも行わない。診断にはPhase IDと「既に展開済みなので新しいentry designを受け付けない」ことを含める。Roadmapがactiveでない場合、Phaseがcomplete / held / cancelled / plan_excludedの場合、dependencyが未充足の場合は、従来からあるそれぞれの診断が優先する（そちらの方が具体的な理由を示すため、順序は変更していない）。いずれの経路でもcanonical stateは変更しない。「既存構造と同じdesignか」の機械照合は実装していない（graph同型判定・対応付け探索・design key復元を含む）。設計調査の結果、designの比較はlabel付きgraph同型判定に相当し、endpoint解決順序・特殊Work比較・曖昧性・探索の完全性という独立した正しさの要件を伴うため、欠陥の規模に対して複雑すぎると判断した。展開済みPhaseの現在構造はread-onlyで読み、計画の正式変更はRoadmap側の経路で行う。併せて、明示entryの妥当性をdomain write・mutation effect・Git commit / pushより前へ移した。従来は初回展開をfinalizeした後に「entry Workがstartableでない」と判明して例外を返しており、成功してcommit済みのoperationにAPIが失敗を返していた（再現済み: HEAD進行・Work commit済み・mutation completed・validate_project PASSと同時にSpecViolation）。新しい検査はdesignと既存Workの状態だけから判定する: entryがdesignのWork keyにない場合、この展開が作るWorkの完了を待つ場合はSTOPし、既存Workの完了を待つ場合はそれがcompletedなら妥当とする。rollbackでは直していない。空design・reserved keyの検査も展開済み判定の後へ揃え、初回とre-entryで意味が逆転しないようにした。BL-014の一般tie-break（entry=None時の複数startable候補選択）は変更していない。このPhase自身のPhase entryが中断してpending mutationが残っている状態は呼び出し側の再実行と区別し、`phase_already_expanded` として扱わず、pending recordをabandon・削除しない。その中断状態のresume自体はBL-023が扱う。schema・event・relation type・project.yamlは変更しておらず、backfillは不要。`skills/roadmap` へ反映済み。

### BL-016 Default result commit message type

- ID: BL-016
- Title: Default result commit message type
- Status: RESOLVED
- Kind: implementation
- Problem: STARTがWork成果をcommitする際、messageの指定がなければ既定で `feat(workline): ...` になり、Workの性質（docs / fix / chore等）に関わらず `feat` typeが付く。
- Why it matters: Conventional Commits等を運用するrepositoryでは履歴の分類が不正確になり、message指定が実質必須になる。
- Likely scope: 成果commitの既定messageの決め方、executorからtypeを渡す手段、`skills/start` の記述
- Cross-project impact: あり（全Projectの成果commit履歴）
- Backfill likely: no
- Human confirmation likely: no
- Self-hosting prerequisite: no
- Evidence class: smoke test, code inspection
- Resolution: 成果commitの既定messageから固定の `feat` を廃止し、neutralな `chore(workline): <display> <name>` にした。成果がfeat / fix / docs / refactorのどれに当たるかはproduct判断であり、Work名・成立状態・work_kind・成果fileの内容から推測しない。推測経路は追加していない（名前の語からのtype判定、work_kindからのtype導出、成果diffの解釈を含む）。再現のとおり、変更前はfeature・bugfix・document-only・deletion-onlyのいずれのWorkでも `feat(workline): ...` が付き、同じWorkのfinalize commitが `chore(workline): complete ...` であるため、1 Workが矛盾するtypeの2 commitを残していた。既定messageは他のWorkline生成commit（create / expand phase / complete / hold / cancel等、およびProject開始の固定message `chore(workline): initialize project`）と同じ側へ揃えた。executorが `Completed(message=...)` で明示したmessageの扱いは変更していない。そのままverbatimで使い、prefixを足さず、typeを変換せず、形式も検査しない（Conventional Commits validatorは追加していない）。messageは必須化していない。create / modify / deleteの成果は従来どおり同一owned setとして1 commitにまとめるため、deletionだけの成果も同じ既定messageになる。owned result fileが無いWorkが成果commitを作らない挙動も変えていない。commit typeを読むconsumerはrepository内に無く（CI・changelog・release自動化・commit message parser・hookのいずれも存在しない）、過去commitは書き換えていない。schema・event・relation type・project.yamlは変更しておらず、backfillは不要。canonical authorityはConventional Commitsを要求しておらず、allowed type一覧も持たないため、この既定はneutral defaultであってtype体系の採用ではない。`skills/start` へ反映済み。BL-014のstartable候補のtie-breakは変更していない。

### BL-017 Declared write scope broader than actual writes

- ID: BL-017
- Title: Declared write scope broader than actual writes
- Status: RESOLVED
- Kind: implementation
- Problem: Roadmap operationは種類に関わらず、予定write scopeのfilesとして共通ledger（roadmap relations / related / events）の3ファイルを固定で宣言する（例: Phase entryはeventを書かず、Phase hold / resumeはrelationを書かない）。STARTも同じ3ファイルを固定で宣言する。
- Why it matters: pending mutationとのoverlap判定は宣言されたwrite scopeで行われるため、実際には独立なoperation同士も重なりありとして `reconcile required` になる。現時点で実害は確認されていないが、中断や並行作業の際に不要な停止の原因になり得る。
- Likely scope: operationごとの予定write scopeの精密化（意図的に直列化しているなら、その明文化で足りるかの判断を含む）、Mutation Controllerのoverlap判定との整合、既存pending recordとの互換、BL-021との関係
- Cross-project impact: あり（operation同士の衝突判定）
- Backfill likely: no
- Human confirmation likely: no
- Self-hosting prerequisite: no
- Evidence class: smoke test, code inspection
- Resolution: 各Roadmap operationが共通ledger 3ファイルを一律に宣言するのをやめ、そのoperationが最後まで進んだ場合に書き得るcanonical fileだけを予定write scopeとして宣言するようにした。実測での再現: pendingの `phase-hold`（実際にはevent logしか書かない）が `work-related-maintenance`（related.yamlだけ）と `add_phases`（roadmap.yamlだけ）をいずれも `reconcile_required` で停止させ、pendingの `work-related-maintenance` と pendingの `roadmap-create` も同様に、1ファイルも共有しない `phase-hold` を停止させた。計4組を再現し、recordのdeclared filesと実effectのfilesを並べて、原因がdeclared scopeの重なりだけであることを確認した。宣言内容はoperation種別から静的に決まる: Roadmap作成 / Phase追加 = `relations/roadmap.yaml`、Phase entry = `relations/roadmap.yaml` + `relations/related.yaml`（lifecycle eventではないのでevent logを書かない）、Roadmap / Phaseの hold / resume / cancel と achievement記録 = `events/events.jsonl`、plan exclusion（Phase / Work）= replanがWork登録とrelation変更を行い得るため3つとも、既存未開始WorkのRelated maintenance = `relations/related.yaml`。direct standalone CREATEも `relations/related.yaml` だけに狭めた（relation payloadを渡さずlifecycle eventも記録しないため、他の2つはこの経路では書き得ない）。STARTは変更していない: question wait / completion / hold / derive の各経路を実測し、宣言している3ファイルがそのまま書き得る集合であることを確認した（start-plan-excludeもreplan経由で3つとも書き得る）。`project-start` / `push-destination-pin` / `bootstrap-backfill` は元から自分のpath listを宣言しており実測でも一致していたため変更していない。「実際に書いたfile」ではなく「書き得るfile」を宣言する: scopeはどの経路を通るか決まる前に宣言するので、条件付きでしか書かないfile（Phase relationを伴うRoadmap作成、Relatedを伴うPhase entry、Workを登録するreplan）も含める。共有ledgerはfile単位で書き直すため、同じledgerを書き得る2 operationは独立ではなく、両方が宣言する。検証: 13のRoadmap operation・START・direct CREATEを一通り実行し、記録された全effectのledger集合が宣言集合の部分集合であること（under-declarationが無いこと）を確認した。scopeを決めていないoperation名は全ledgerを宣言するfail-closedとし、過大宣言の側へ倒す。既存pending recordのwrite scopeは書き換えない: 旧実装が記録した広いscopeはそのまま尊重され、resume時の比較は新旧scopeの和集合で行われる。backfillもrewriteもしない。entity scopeは元から精密だったため変更していない（`add_phases` がRoadmap entityを宣言する点だけは実書き込みより広いが、同一Roadmapの計画変更同士を競合させる意図として妥当なので残した）。BL-021のProject execution lockとは責務が別で、lockは同時実行の直列化、write scopeは中断して残ったpending mutationからの独立性判定であり、lock側は変更していない。write scopeはeffectに対する許可ではなく衝突宣言であり（`MutationController.open` 以外に読む場所がない）、狭めてもoperationが書けるものは変わらない。挙動上の帰結として、Phaseの展開が中断して残っているRoadmapでも hold / resume ができるようになった（展開recordは無変更のまま残り、Roadmapをresumeすれば同じmutationで完了することを実測）。`skills/roadmap` と `skills/create` へ反映済み。

### BL-018 Unused assignment in Phase expansion

- ID: BL-018
- Title: Unused assignment in Phase expansion
- Status: RESOLVED
- Kind: hygiene
- Problem: Phase展開の実装で、構造検査の戻り値を代入した変数が使われないまま、直後に状態の再読込結果で上書きされている。動作には影響しない。
- Why it matters: 構造検査の結果を後続で使っているように読め、保守時の誤読を招く。
- Likely scope: 該当実装の整理（構造検査は失敗時のSTOPのためだけに呼ぶ意図の明確化）
- Cross-project impact: no（挙動は変わらない）
- Backfill likely: no
- Human confirmation likely: no
- Self-hosting prerequisite: no
- Evidence class: smoke test, code inspection
- Resolution: Phase展開の構造検査について、未使用の代入 `after = ` だけを削除し、`_stop_on_structure(store, "phase structure check")` の呼出しは保持した。この呼出しはcommit / pushより前に置かれた唯一の構造ゲートであり、`_finalize` は `gitops.finalize`（git_commit / git_push effect）を適用してから自身の postcheck を走らせるため、呼出しごと消すと構造不正な展開がcommit・pushされた後にしかSTOPできなくなる。canonical Skill `skills/roadmap` の順序（Phase構造検査 → commit / push）もこの呼出しを要求している。意図が読み取れるよう、値のためではなく失敗時のSTOPのために呼んでいることをcommentで明記した。挙動・schema・canonical semanticsは不変で、canonical wordingの変更もbackfillも不要。代入された値が読まれないことはAST上で確認済み（`after` の出現はStore / Store / Loadの3つのみ、唯一のLoadは上書き後、間の文は `after` を読まず、分岐・try・closureなし）。この代入は初出commit `2ba599f` から存在し、linter未設定のため検出されていなかった。既存testは呼出しの有無を一切固定していなかった（呼出しごと削除したmutantでもfocused 67件が全passする実測）ため、`ExpansionStructureCheckTests` を1件追加した: 展開自身の構造検査を失敗させ、`structure_invalid` / `phase structure check` でSTOPし、かつHEADが動いていない（commit・pushに到達していない）ことを固定する。このtestは修正前・修正後いずれもPASSし、呼出しを削除したmutantではHEADが進んで失敗する。実測: focused 68 passed / 36 subtests、full suite 532 passed / 2 skipped / 397 subtests、validate-registry PASS。

### BL-019 Runtime recovery record retention and ignore policy

- ID: BL-019
- Title: Runtime recovery record retention and ignore policy
- Status: RESOLVED
- Kind: design, implementation, hygiene
- Problem: `.workline/runtime/` のmutation recovery recordは完了後も残り続け、各operationの開始時には完了済みを含む全recordが読み込まれ、形式versionが検査される。放置されたpending record（stale mutation）の扱いは設計段階で保留したままで、完了済みrecordの保持期間やcleanup経路もない。また、Project開始はruntime領域をGitのignore対象にしないため、Projectによってはruntime recordがuntrackedとして表示され続ける。
- Why it matters: recordの蓄積は起動時のコスト（BL-007）を増やし、形式を変更した時に過去record全体が互換性の問題になる（BL-013 の intent format compatibility policy）。untrackedのruntime recordはdirty noiseになり、Workline以外のtoolから誤ってcommitされる余地がある。一方で、cleanupを誤るとrecoveryに必要な情報を失う。
- Likely scope: 完了済み / abandoned / stale pendingの各recordの保持とcleanup規則（`rules/git` のcleanup定義との整合）、runtime領域のignore方針（Workline-owned範囲に置くignoreの是非を含む）、形式versionの互換方針
- Cross-project impact: あり
- Backfill likely: yes（既存Projectのruntime ignoreと既存record）
- Human confirmation likely: yes（cleanup規則は共通ルールの変更。Projectのignore設定を変える場合も）
- Self-hosting prerequisite: partial（BL-013 の intent format compatibility policy と関係する）
- Evidence class: design deferral, smoke test, real-project migration, code inspection
- Resolution: closeしたrecovery recordはresumeの対象ではないため、completedとしてcloseしたmutationが、自分が今回作成したrecord自身を削除することにした。削除は次をすべて機械的に示せる場合に限る: 今回の実行が作成し既存recordをresumeしていない / top-level fieldがcloseしたrecordのfield setと完全一致しversionがint型そのものである / 通常のregular fileであり間接参照でない / Gitのindexにも HEADにも存在しない（判定できないgit呼び出しは「存在する」として扱う）/ 内容がそのmutationが最後に書いたものと完全一致する。1つでも示せなければrecordを残す。resumeしたmutationのrecordを削除しないのは、operationが待っている間に第三者が加えた変更がloadで許容されsaveで書き戻されるため、最終的な内容が作成者の証明にならないからである。indexとHEADを別に問うのは、`git rm --cached` でindexから外れてもHEADが保持しているrecordを削除するとcommit済みの変更を消すことになるからである。削除はoperation自身の後始末でありresultではないため、全effect・Git stage・構造postcheckの後に行い、失敗してもoperationは成功のままとし、そのためにdomain effectを再実行しない。cleanupが中断して残ったcompleted recordは次回も通常どおり読める。pending record、abandoned record、resumeしたmutationのrecord、他のmutationが残したrecordは削除しない。abandoned recordを残すのは、Project開始がそのfolderをやり直してよいと判断できる唯一の証拠だからである（BL-022）。既存Projectに既に蓄積したrecordは今回の対象とせず、保持期間・件数上限・一括cleanup・maintenance commandは設けない。Git ignore設定（Project rootの `.gitignore`、`.git/info/exclude`、runtime配下のignore file等）はWorkline側で作成・変更せず、Projectの既存ignore設定はProject側の所有物として扱う。schema、intent version、project.yaml、event、relation typeは変更しておらず、backfillは不要。残る論点の分離: 狭いwrite scopeを持つ `bootstrap-backfill` / `push-destination-pin` のpending recordは通常作業を止めないため気付かれずに残り得る（その可視化はBL-006のpending mutation報告の範囲）、残存recordのintent format互換方針はBL-013、cold-start性能全体はBL-007、workline-core自身の生成物hygieneはBL-010。`rules/git` とproject-start Skillへ反映済み。

### BL-023 Phase expansion cannot resume after an interruption

- ID: BL-023
- Title: Phase expansion cannot resume after an interruption
- Status: RESOLVED
- Kind: implementation, design
- Problem: Phase entryの展開が、通常Work適用後・integration適用前などで中断すると、pending mutationが残ったままProjectが進めなくなる。再実行したPhase entryは、そのPhase自身のpending phase-entry mutationをrecovery stateとして識別するものの、既にWorkがある場合はresumeせずそのまま返すため、integrationは作られない。一方で他のoperationはそのpending mutationとwrite scopeが重なるため `reconcile_required` で停止する。実測では `add_phases` とWork STARTの両方が停止し、`validate_project` は問題を報告しなかった。
- Why it matters: Project全体が進行不能になり、Workline経由で回復する経路がない。中断したoperationは同じmutationをresumeするという `rules/git` の前提（`registry.md` Multi-write mutation）と `skills/roadmap` の記述が、この経路では成立していない。
- Likely scope: 中断したPhase expansionのrecovery semantics。実測した障害は少なくとも3点: `register_works()` のprojection check（integration invariant等）が `has_stage` guardより前に走るため、適用済みintegrationを持つPhaseで記録済みintegration stageを再投影すると `integration invariant: would have 2 unfinished integrations` で衝突する。`roadmap._open()` が戻る前に `mutation.apply()` を呼ぶため、resume時に記録済みeffectが照合より前に適用される。`abandon_on_stop()` が `mutation.resumed` を見ないため、resumeしたmutationをabandonし得る経路がある。registration coreは共有であり、Phase entry / add_phases / standalone CREATE / STARTのderiveへの横断影響を調べる必要がある。pending recordにdesignを束縛する（または記録済み決定を正本とする）方法、designを伴わない legacy pending recordの扱いも決める。rollbackでは直さない。
- Cross-project impact: あり（全Projectの回復可能性）
- Backfill likely: 可能性あり（既に詰まっているProjectの回復手順）
- Human confirmation likely: yes（recovery semanticsとMutation Controller契約に触れる）
- Self-hosting prerequisite: no
- Evidence class: code inspection, smoke test
- Resolution: Phase entryが、最初のID予約より前に、展開対象のPhaseEntryDesignをmutationのinvocationへcanonicalな形で記録するようにした（通常Workの宣言順・key・name・成立状態・Related、integration、human_confirmationの有無と内容、planned_next、requires_completion、明示entry、記録形式version）。digestではなく内容そのものを保持するため、人がrecordを読んで何を展開していたか分かる。通常Workの順序はdisplay番号を決めるため意味として扱い、並べ替えは別designとする。これにより、中断した展開が「どのdesignに束縛されているか」が最初のdurable recordの時点で確定する。再実行のdesignが一致する場合だけpending mutationをresumeし、既に記録済みのstageはcaller specから決め直さず記録済みeffectをclassify / applyし、IDと結果は記録済みreserved ID / effectから再構成する。未記録stageだけを同一性確認済みのcaller designから決めるため、前半が旧design・後半が新designという混在が構造的に作れない。一致しない再実行は `reconcile_required` とし、pending recordを一切変更しない。実測: 中断点 P0（intent作成直後）/ P1（ID予約後）/ P2（works記録・未適用）/ P4（works適用済み）/ P5（integration記録・未適用）/ P7（integration適用済み）/ P8（confirmation記録・適用）/ P9（finalize前）/ P10（commit後・complete前）のすべてで、同じmutation IDのまま前進して完了し、Work・integration・confirmation・relationの重複なし、validate_projectもclean。以前はP4以降が回復不能で、pending中は `add_phases`・Work START・`hold_phase` がいずれも `reconcile_required` で停止していた。併せて次の2点を直した: 展開済みPhaseの早期returnが `_open` より前にあり pending mutationへ到達できなかった点（このPhase自身のpending phase-entryがある場合はresume pathへ入れる。BL-015の `phase_already_expanded` は、pendingが無い展開済みPhaseに対して従来どおり）。`register_works()` が記録済みstageでもspec由来のreserve / projectionを先に行い、適用済みintegrationを二重計上して `integration invariant: would have 2 unfinished integrations` で衝突していた点（記録済みstageはregistration coreを呼ばずに再構成する。registration core自体は変更していない）。`abandon_on_stop()` はglobalには変更していない: BL-022がresumeしたeffect 0件のmutationをabandonする動作に依存しているため（`test_a_stop_while_resuming_is_retried_as_a_new_mutation`）、Phase entryの内側でのみ、resumeしたmutationをabandonしないようにした。designを記録していない旧実装のpending recordはどの位置でも自動resumeせず `reconcile_required` とし、record・effects・reserved IDs・statusをそのまま保持する（P8 / P10も例外にしない。effect completenessは証明できても、過去に別designが混ざっていないことを証明できないため）。`INTENT_VERSION` とgeneric mutation schemaは変更していない: 記録はphase-entry invocationのoperation-localな意味追加であり、既存のrecord形式でそのまま往復する。明示entryもdesign記録に含むため、resume後の `entry_work_id` は元のdesign.entryから決まる。BL-014の一般tie-breakは変更していない。standalone CREATE / add_phases の共有binding欠陥はBL-024。`skills/roadmap` へ反映済み。

### BL-024 Resume invocation does not bind decided content

- ID: BL-024
- Title: Resume invocation does not bind decided content
- Status: RESOLVED
- Kind: implementation, design
- Problem: 中断したoperationをresumeするかどうかは、mutationのinvocationが一致するかで決まる。しかしinvocationは「何を決めたか」を含んでいないため、同じinvocation identityで内容の違うrequestを再実行すると、記録済みの旧決定を保持したまま新requestへsuccessを返す。実測: standalone CREATEで同じname / keyのまま異なる成立状態を渡して再実行すると、successが返るがstoreされているWorkは旧内容のまま（`create.py` のinvocationは operation / name / key だけで、postcheckも存在確認しか行わない）。`add_phases` も同様に、同じPhase名で異なる成立状態を渡すとD1のPhase本文を保持したままsuccessを返す。
- Why it matters: 呼び出し側は自分が渡した内容が登録されたと解釈するが、正本は別の内容のままになる。中断・resumeが絡む経路でのみ起きるため気付きにくい。
- Likely scope: resume identityが「決定内容」を束縛するための共通契約。Phase entryではBL-023でoperation-localに解決済み（designをinvocationへ記録し、不一致は `reconcile_required`）。同じ考え方をcaller横断の共通contractにするか、各ownerでoperation-localに解くかを決める必要がある。対象は少なくとも standalone CREATE（`create.py` の direct owner invocation）と `add_phases`（`roadmap.py` の invocation key）。postcheckが存在確認しか行わず内容一致を見ていない点も併せて扱う。rollbackでは直さない。
- Cross-project impact: あり（resumeを伴う全operation）
- Backfill likely: 可能性あり（既存pending recordの扱い）
- Human confirmation likely: yes（共通resume contractに触れる）
- Self-hosting prerequisite: no
- Evidence class: code inspection, smoke test
- Resolution: callerが内容を決める4つのowner（direct standalone CREATE / Roadmap作成 / Phase追加 / 既存未開始WorkのRelated maintenance）が、最初のID予約より前に、決定内容の正規identityを自分のinvocationへ `request` として記録するようにした。`MutationController.begin` がそれをdurableに書いてからID予約が始まるため、中断したoperationがどのrequestに束縛されているかは最初のdurable recordの時点で確定する。共有helperは `mutation.py` の `same_request`（canonical JSON比較。Pythonが `True` と `1` を同一視する一方recordは区別するため、objectではなくencodingで比較する）、`pending_for_slot`（invocationのうち「どれを対象にしているか」を言うslot部分だけで未完了recordを探す。内容が違うrequestでも、本来resumeしていたはずのrecordを必ず見つけて拒否できるようにするため）、`require_same_request`（legacy record / 複数件 / 内容不一致のいずれも `reconcile_required`）。identityはdigestではなく内容そのもので、人がrecordを読んで何を決めていたか分かる。正規化はrenderingに合わせた: section本文になる値はstrip（`store.render_body` がstripする）、nameはverbatim（renderingがそのまま書く）、Roadmapの任意sectionは有無と内容を別に記録（renderingがtruthinessで含める）、`derivation_detail` は無しと空を区別。宣言順はdisplay番号とID予約の対応を決めるため保持し、並べ替えは別requestとする。検査位置は、mutationを開くより前・記録済みeffectをreplayするより前（`roadmap._open` は戻る前にapplyする）で、Related maintenanceではno-op fast pathより前（D1の適用済みedgeの部分集合をD2が要求すると、D1をpendingのまま「やることなし」と返してしまうため）。実測（baseline `5e6580b`）: standalone CREATEは同じname / keyで別の成立状態を渡すとsuccessを返し正本はD1のまま、roadmap-createはD1の本文 + D2のPhaseという混ざったRoadmapをsuccessで返し、add_phasesはD1の成立状態を保持したままsuccess、Related maintenanceは明示keyで別のaddを渡すとD1のedgeを保持したままsuccess。いずれも修正後は `reconcile_required` となり、正本もpending recordも変わらない。同一requestの再実行は、intentだけ / 記録済み未適用 / 適用済みのどの中断点でも同じmutation・同じreserved IDで前進し、重複entity・重複relation・取り残しreservationはない。`_related_request_key` はrequest文字列を区切り文字で連結しescapeしないため別内容が同じ文字列になり得ることを実測で確認し（`(must_read, "a: | +obey:b")` と `(must_read,"a") + (obey,"b")` が同一label）、identityはlabelではなく構造で持つようにした。requestが自分自身の中に持つ重複（同一edge・同一removal id）は `_resolve_related_changes` がもともと1件として扱うので、identityを作るより前・request解決より前に畳み、畳んだ位置からrelation IDを予約する（`related:add:<index>` はrequest内の位置がkeyのため、畳まないと `(E, E, F)` と `(E, F)` でFのreservationが取り残される）。畳むとdefault labelが変わるので、畳む前のlabelの下も探す（そうしないと、以前の実装が `(E, E)` で作ったlegacy pending recordを唯一見つけられるはずの再実行がno-opを返して取り残す）。`future_plan_change` はidentityへ含めない（held Roadmapを通すかどうかだけを決めeffectに到達しないため、含めるとactive Roadmapで同一内容の再実行を拒否してしまう）。代わりにrequest一致検査の後・mutationを開くより前に検査し、継続できないrecordの存在をlifecycle factで隠さず、拒否された再実行が既存のpending mutationをabandonしないようにした。requestを記録していない旧実装のpending recordはどの中断位置でも自動resumeせず `reconcile_required` とし、record・effects・reserved IDs・statusをそのまま保持する（rollback・abandon・削除・差し替え・新規mutationのいずれも行わない）。これにより、従来default keyで自動resumeできていたRelated maintenanceのpending recordは、以後は人の照合対象になる。変更しなかったowner: `start`（決定はattemptごとで、attemptごとに新しいstageを開く。2回目のattemptが別の結果を決めて同じmutationを完了できることを確認）、`start-plan-exclude` / `phase-plan-exclude` / `work-plan-exclude`（eventのpayloadは対象entityに対する `plan_excluded` で固定。replan effectを記録する `apply_replan` はterminal eventをapplyした後にしか走らないため、replan effectが記録されている＝eventが適用済み＝次の呼び出しはunstarted prechekで止まる。唯一通る窓〈eventが記録済み・未適用〉でも、正本には再実行自身の内容だけが残り最初のrequestの内容は残らないことを3 operation × 2窓で実測）、`roadmap-achievement`（eventは `roadmap_achieved` 固定、`detail` は返すだけ）、Roadmap / Phase lifecycle（event種別固定）、`project-start`（内容不一致はpostcheckが拒否）、`bootstrap-backfill`（payloadは定数）、`push-destination-pin`（決定内容は既にinvocationにある）。どのidentityもそのownerのinvocation内のoperation-local keyなので、`INTENT_VERSION` とgeneric record schemaは変更していない（共通contractへ昇格させていないため人間判断を要する一般規則の変更も発生しなかった）。BL-023がPhase entryにoperation-localで入れた比較器 `_same_design` は、同じ内容の共有 `same_request` へ置き換えた（Phase entryの挙動は変えない）。Phase relationのendpointをspec keyで書くかそのkeyが予約されたPhase IDで書くかは別requestとして扱う: identityは最初のID予約より前にdurableでなければならず、その時点でPhase IDは存在しないため一方を他方へ解決できない（理由は `_phase_relation_records` のdocstringへ記録）。`skills/create` と `skills/roadmap` へ反映済み。

### BL-020 Correction of mis-recorded historical facts

- ID: BL-020
- Title: Correction of mis-recorded historical facts
- Status: DEFERRED
- Kind: spec, design
- Problem: 正しい手順で記録されたevent、derived relation、origin等の「起きた事実」が、後から内容として誤りだったと分かった場合の正式な訂正方式がない。これらは書換え・物理削除をしない原則で保護されている。
- Why it matters: 誤記録が見つかった時に、書換え禁止を守ったまま現在の解釈を正す手段がなく、手編集の誘惑や、誤った履歴を前提にした判断が残る。
- Likely scope: 訂正eventや注記の方式、generated stateへの反映、`rules/ai-decision`（起きた事実は現在計画に合わせて書き換えない）との整合。設計段階で「実例が出るまで保留」とした論点であり、実例が出た時点で設計する。
- Tracked requirements (BL-009由来): BL-009でterminal Workのhistorical Relatedを「当時の証拠」として保持すると確定した。その記録自体が誤りだった場合（例: そもそもそのWorkはそのfileを読む必要がなかった）の訂正はここで扱い、最低限次を満たすこと。
  - 元の記録を物理削除・書換えしない
  - 訂正自体を正式な記録として残す
  - downstream readerが訂正の存在を機械的に判定できる（人間向けのREADMEメモだけでは不足）
  - superseded / invalidatedなhistorical factを現在の真実として扱わない（後続WorkやAIが元記録だけを事実として再利用しない）
- Cross-project impact: あり
- Backfill likely: no
- Human confirmation likely: yes（共通ルール / event schemaの変更）
- Self-hosting prerequisite: no
- Evidence class: design deferral

### BL-021 Concurrent operation exclusion

- ID: BL-021
- Title: Concurrent operation exclusion
- Status: RESOLVED
- Kind: implementation, design
- Problem: Mutation Controllerは、pending mutationの検出とwrite scopeのoverlap判定で競合を防ぐが、複数のprocessが同じProjectで同時にoperationを開始した場合の排他（lock / mutex / queue等）は実装されていない。pending mutationの検出からrecovery recordの作成までの間や、ledgerファイルの読み込みから書き戻しまでの間に、別processが割り込む余地がある。
- Why it matters: 複数のsessionやagentが同じProjectを並行して操作すると、互いのpending mutationを検出できないまま同じ正本を更新し、更新の取りこぼしが起き得る。現時点で発生は確認していない。
- Likely scope: 排他の要否と方式（single-writer前提の明文化で足りるか、lock等を入れるか）、設計段階で実装時に決めるとした排他技術の論点、BL-017との関係
- Cross-project impact: あり
- Backfill likely: no
- Human confirmation likely: no（前提の明文化や実装内の排他だけの場合。共通ルールを変える場合はyes）
- Self-hosting prerequisite: no
- Evidence class: design deferral, code inspection
- Resolution: 成立済みProjectにProject単位のactive execution lock（OS管理の排他file lock、one active writer per Project）を導入した。operationはlock取得後にpending mutation・Project state・push destinationを読み、他processが実行中なら待たずに `project_operation_busy` でSTOPして何も書かない。QuestionWaitではlockを解放しpending mutationを維持する。crash時はOSがlockを解放し、既存のpending mutation recoveryで再開する。Mutation ControllerはProject開始以外のownerについてlockなしのmutationを拒否する。initial Project開始の同時実行は対象外（非サポート）。`rules/git` とcanonical Skillsへ反映済み。

### BL-022 ProjectSTART abandoned pre-effect recovery

- ID: BL-022
- Title: ProjectSTART abandoned pre-effect recovery
- Status: RESOLVED
- Kind: implementation, spec
- Problem: Project開始がrecovery intentを作成した後、domain effectを適用する前にSTOPすると（例: bootstrap pathがGitにignoreされている、既存の未commit変更と重なる）、intentはabandonedとして残り、`.workline/` にはruntime recordだけが存在する状態になる。原因を解消して再実行しても、pending mutationがなく成立済みProjectでもないため `partial_workline` としてSTOPし、正式な経路では再開も再初期化もできない。
- Why it matters: 一時的な前提条件の不備だけで、そのfolderをWorkline Projectとして開始できなくなる。回復には手作業での削除が必要になり、推測修復を禁じる規則とも衝突する。使い捨てのrepositoryで再現を確認している。
- Likely scope: Project開始の「partial .workline」判定（canonical fileを含まずruntime領域だけがある状態の扱い）、abandonedになったProject開始intentの扱い、STOP時の孤立生成物cleanup（`rules/git` のcleanup定義との整合）、`skills/project-start` の記述とtest
- Cross-project impact: あり（Project開始の経路）
- Backfill likely: no
- Human confirmation likely: yes（Project開始の判定規則とcanonical Skillの変更）
- Self-hosting prerequisite: no
- Evidence class: code inspection
- Resolution: 新しいProject開始は、git initを含むpre-effect検査（Git boundary、bootstrapのcommit可否、pre-existing dirtyの分離可能性）をrecovery intentの作成より前に終え、そこでのSTOPでは `.workline` を作らないようにした（`.git` だけが残り得るが削除せず、次回は既存repositoryとして扱う）。dirty snapshotは検査時にcaptureし、intent作成直後・最初のeffectより前に同じsnapshotを記録する。`.workline` が、そのfolderに対するProject開始がeffectを1件も記録する前にabandonedになったrecovery recordだけから成ると既存のfieldから機械的に証明できる場合は、それらのrecordを変更・削除・resumeせずに残したまま、新しいmutationとしてやり直す。それ以外のpartial `.workline` は `partial_workline`、ownershipを確認できないrecordは `reconcile_required` のままSTOPする。pending Project開始のresumeは変更していない。intent version・record schema・project.yaml・bootstrap・eventは変更せず、recordのcleanup・保持期間・runtime ignore（BL-019）とProject開始の同時実行（BL-021）は扱っていない。`skills/project-start` へ反映済み。
