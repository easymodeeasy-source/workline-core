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
| BL-009 | Historical deleted Related / must_read semantics | VERIFIED |
| BL-010 | Generated artifact hygiene | VERIFIED |
| BL-011 | Reusable migration procedure | OPEN |
| BL-012 | Unsupported self-hosting guard | RESOLVED |
| BL-013 | Self-hosting readiness | DEFERRED |
| BL-014 | Deterministic tie-break among startable candidates | VERIFIED |
| BL-015 | Silent no-op on Phase re-entry | VERIFIED |
| BL-016 | Default result commit message type | VERIFIED |
| BL-017 | Declared write scope broader than actual writes | VERIFIED |
| BL-018 | Unused assignment in Phase expansion | VERIFIED |
| BL-019 | Runtime recovery record retention and ignore policy | INVESTIGATE |
| BL-020 | Correction of mis-recorded historical facts | DEFERRED |
| BL-021 | Concurrent operation exclusion | RESOLVED |
| BL-022 | ProjectSTART abandoned pre-effect recovery | RESOLVED |

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
- Status: VERIFIED
- Kind: spec, implementation
- Problem: completed Workの `must_read` 等のRelated targetが、後続のWorkで意図的に削除された場合の意味が定義されていない。historical evidence（そのWorkが当時何を読んだか）と、現在の参照が有効か（current validity）を区別する規則がなく、構造validationはRelated targetの存在を検査しない。意図的なtracked file削除はWork resultとして扱えるようになり、must_update / realizesでの扱いは定義済みだが、must_readを含む履歴側Relatedの扱いは未定義のまま。started / completed等のWorkに対するRelated maintenanceも、現行仕様では定義していない。
- Why it matters: 削除済みtargetを指す履歴参照を「壊れた参照」と誤判定するか、逆に死んだ参照を現在の読取計画に残すかの判断が場当たりになる。旧authorityを退役させる移行では、履歴Relatedのtarget削除が必ず起きる。real-project migrationでは、completed Workのmust_read targetが後続Workで意図的に削除され、その扱いを都度判断した。
- Likely scope: historical evidenceとcurrent validity validationの分離、`rules/information-tracing`（読取順とhistorical参照）、`skills/start` / `skills/roadmap` のRelatedの意味、構造validation、reading planの生成
- Cross-project impact: あり
- Backfill likely: no（意味を定義するだけの場合）
- Human confirmation likely: yes（canonical semanticsの変更）
- Self-hosting prerequisite: no
- Evidence class: real-project migration, code inspection

### BL-010 Generated artifact hygiene

- ID: BL-010
- Title: Generated artifact hygiene
- Status: VERIFIED
- Kind: hygiene
- Problem: workline-coreに `.gitignore` がなく、test実行やpackage metadata生成で作られる `__pycache__/`、`*.egg-info/` 等がuntrackedとして作業ツリーに残る。
- Why it matters: `git status` のdirty noiseになり、意図した変更の確認を読みにくくし、誤ってcommitされる余地を残す。
- Likely scope: workline-coreの生成物policyと `.gitignore`（Python bytecode、packaging metadata、test cache等）
- Cross-project impact: no（workline-core repositoryのみ。Project側のruntime recordはBL-019）
- Backfill likely: no
- Human confirmation likely: no
- Self-hosting prerequisite: no
- Evidence class: code inspection, self-hosting assessment

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
- Status: VERIFIED
- Kind: interface, implementation
- Problem: 既にWorkが展開されたPhaseへPhase entryを再実行すると、重複展開はしない（仕様どおり）が、渡したWork設計が既存構造と食い違っていても検証も警告もされずに無視される。結果には「展開しなかった」ことを示すflagがあるだけで、呼び出し側が見落とすと、意図したWorkが登録されたと誤認し得る。
- Why it matters: 別Phaseの設計を取り違えて渡す等の誤りを検出できず、計画と正本がずれたまま実行へ進む可能性がある。
- Likely scope: 再entry時の結果（食い違いの検出・警告・STOPの要否）、`skills/roadmap` のPhase entry記述、test
- Cross-project impact: あり（Roadmap APIの挙動。影響は小さい）
- Backfill likely: no
- Human confirmation likely: no（診断を追加するだけの場合。STOPへ変える場合はyes）
- Self-hosting prerequisite: no
- Evidence class: smoke test, code inspection

### BL-016 Default result commit message type

- ID: BL-016
- Title: Default result commit message type
- Status: VERIFIED
- Kind: implementation
- Problem: STARTがWork成果をcommitする際、messageの指定がなければ既定で `feat(workline): ...` になり、Workの性質（docs / fix / chore等）に関わらず `feat` typeが付く。
- Why it matters: Conventional Commits等を運用するrepositoryでは履歴の分類が不正確になり、message指定が実質必須になる。
- Likely scope: 成果commitの既定messageの決め方、executorからtypeを渡す手段、`skills/start` の記述
- Cross-project impact: あり（全Projectの成果commit履歴）
- Backfill likely: no
- Human confirmation likely: no
- Self-hosting prerequisite: no
- Evidence class: smoke test, code inspection

### BL-017 Declared write scope broader than actual writes

- ID: BL-017
- Title: Declared write scope broader than actual writes
- Status: VERIFIED
- Kind: implementation
- Problem: Roadmap operationは種類に関わらず、予定write scopeのfilesとして共通ledger（roadmap relations / related / events）の3ファイルを固定で宣言する（例: Phase entryはeventを書かず、Phase hold / resumeはrelationを書かない）。STARTも同じ3ファイルを固定で宣言する。
- Why it matters: pending mutationとのoverlap判定は宣言されたwrite scopeで行われるため、実際には独立なoperation同士も重なりありとして `reconcile required` になる。現時点で実害は確認されていないが、中断や並行作業の際に不要な停止の原因になり得る。
- Likely scope: operationごとの予定write scopeの精密化（意図的に直列化しているなら、その明文化で足りるかの判断を含む）、Mutation Controllerのoverlap判定との整合、既存pending recordとの互換、BL-021との関係
- Cross-project impact: あり（operation同士の衝突判定）
- Backfill likely: no
- Human confirmation likely: no
- Self-hosting prerequisite: no
- Evidence class: smoke test, code inspection

### BL-018 Unused assignment in Phase expansion

- ID: BL-018
- Title: Unused assignment in Phase expansion
- Status: VERIFIED
- Kind: hygiene
- Problem: Phase展開の実装で、構造検査の戻り値を代入した変数が使われないまま、直後に状態の再読込結果で上書きされている。動作には影響しない。
- Why it matters: 構造検査の結果を後続で使っているように読め、保守時の誤読を招く。
- Likely scope: 該当実装の整理（構造検査は失敗時のSTOPのためだけに呼ぶ意図の明確化）
- Cross-project impact: no（挙動は変わらない）
- Backfill likely: no
- Human confirmation likely: no
- Self-hosting prerequisite: no
- Evidence class: smoke test, code inspection

### BL-019 Runtime recovery record retention and ignore policy

- ID: BL-019
- Title: Runtime recovery record retention and ignore policy
- Status: INVESTIGATE
- Kind: design, implementation, hygiene
- Problem: `.workline/runtime/` のmutation recovery recordは完了後も残り続け、各operationの開始時には完了済みを含む全recordが読み込まれ、形式versionが検査される。放置されたpending record（stale mutation）の扱いは設計段階で保留したままで、完了済みrecordの保持期間やcleanup経路もない。また、Project開始はruntime領域をGitのignore対象にしないため、Projectによってはruntime recordがuntrackedとして表示され続ける。
- Why it matters: recordの蓄積は起動時のコスト（BL-007）を増やし、形式を変更した時に過去record全体が互換性の問題になる（BL-013 の intent format compatibility policy）。untrackedのruntime recordはdirty noiseになり、Workline以外のtoolから誤ってcommitされる余地がある。一方で、cleanupを誤るとrecoveryに必要な情報を失う。
- Likely scope: 完了済み / abandoned / stale pendingの各recordの保持とcleanup規則（`rules/git` のcleanup定義との整合）、runtime領域のignore方針（Workline-owned範囲に置くignoreの是非を含む）、形式versionの互換方針
- Cross-project impact: あり
- Backfill likely: yes（既存Projectのruntime ignoreと既存record）
- Human confirmation likely: yes（cleanup規則は共通ルールの変更。Projectのignore設定を変える場合も）
- Self-hosting prerequisite: partial（BL-013 の intent format compatibility policy と関係する）
- Evidence class: design deferral, smoke test, real-project migration, code inspection

### BL-020 Correction of mis-recorded historical facts

- ID: BL-020
- Title: Correction of mis-recorded historical facts
- Status: DEFERRED
- Kind: spec, design
- Problem: 正しい手順で記録されたevent、derived relation、origin等の「起きた事実」が、後から内容として誤りだったと分かった場合の正式な訂正方式がない。これらは書換え・物理削除をしない原則で保護されている。
- Why it matters: 誤記録が見つかった時に、書換え禁止を守ったまま現在の解釈を正す手段がなく、手編集の誘惑や、誤った履歴を前提にした判断が残る。
- Likely scope: 訂正eventや注記の方式、generated stateへの反映、`rules/ai-decision`（起きた事実は現在計画に合わせて書き換えない）との整合。設計段階で「実例が出るまで保留」とした論点であり、実例が出た時点で設計する。
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
