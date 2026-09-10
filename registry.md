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

`.workline/runtime/` はWorkline-owned non-domain runtime補助領域とする。Worklineが作成・管理するrecovery metadataを同一mutationの期待値に従って作成・更新する場合は前項の既存untracked保護の対象外だが、Workline ownershipを確認できないrecordや期待値不一致のrecordは自動上書きせず `reconcile required` として停止する。

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

各state-changing operationのentryで、operation ownerはcurrent invocationの対象と予定write scopeに関係するpending mutationを検査する。一意対応する1件があれば新規mutationを開始せずそのmutationをresumeし、0件なら新規mutationを開始してよい。複数件、競合、または他ownerのpending mutationから安全に独立していると証明できない場合は `reconcile required` として停止する。

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
