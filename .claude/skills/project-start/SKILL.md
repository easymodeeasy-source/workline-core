---
name: project-start
description: Initialize a local folder as a new Workline Project. This is the only Workline Skill usable before a Workline Project exists — use it when a folder that has no .workline/project.yaml yet — named explicitly, or indicated as the current directory ("このルート", "ここ", "this folder") — must be connected to the common Workline registry, receive the canonical .workline structure, resolve its Git boundary, and get the required initial local commit without starting a Roadmap.
---

# Project開始

対象local folderをWorkline利用可能な新規Projectとして初期化する。

これはpre-project操作である。Workline root側から使用する。established Project（`.workline/project.yaml` を持つroot）を再初期化する経路ではない。

`rules/git` のProject contextに従い、別の成立済みWorkline Projectのcontextから対象folderをProject開始しない。成立済みWorkline Projectの配下に新しいWorkline Projectを作らない（nested Workline Projectは作らない）。canonical implementationはどちらも書き込む前にSTOPする（`foreign_project_mutation` / `nested_workline_project`）。Project開始のmutationは、その実行が対象rootに与えた許可の内側でだけ書き込まれ、owner名だけでは許可されない。

## Canonical implementation first

Workline rootにこのoperationのcanonical implementationが存在する場合は、必ずそれを使用する。

```text
実装の存在を先に確認する
→ 存在する: それを実行する
→ 使用不能: STOPして報告する
```

このSKILL本文を根拠に `.workline` 構造・project.yaml・bootstrap・mutation metadataを手作業で再実装しない。実装の存在確認より先にfilesystemを書き始めない。

手組みした構造は未検証の再実装であり、canonical implementationからはbroken / partialとして扱われる。implementationが使えないときにmanual fallbackへ進まない。

起動は `rules/git` のWorkline implementationに従い、Workline root自身のcanonical launcherから行う。

```text
Windows: py -3 -I -B "<R>\run-workline.py" project-start <project-root> --workline-root <R>
POSIX:   python3 -I -B "<R>/run-workline.py" project-start <project-root> --workline-root <R>
R = 下記の入力解決で決まったWorkline root
```

実行中launcherのRと `--workline-root` が一致しなければ `workline_implementation_mismatch` でSTOPし、何も書かない。launcherが使えない場合（Python 3.11未満、`-I` なし、implementationの不在・不一致）はSTOPして報告し、`python -m workline.cli`・PYTHONPATHの手組み・editable installへfallbackしない。targetへinterpreter / launcher等のruntime情報を書かない。

## Input resolution

Project rootとWorkline rootは入力解決規則で決める。どちらも規則から一意解決できた場合、`rules/human-confirmation` に従い、確認のためだけに人間へ返さない。質問は一意解決できなかったときの手段であり、既定の手順ではない。

### Project root

```text
A. 呼び出し元 / ユーザーがabsolute Project rootを明示している
   → その値を使う

B. ユーザーが「このルート」「ここ」「このfolder」「current directory」等、
   現在の作業directoryを対象として明示している
   → cwdをProject rootとして使う

C. それ以外で一意に解決不能
   → 初めて人間へ質問する
```

A / Bで解決した場合、確認のためだけのAskUserQuestionを出さない。

明示pathとcwdが競合する場合は勝手に選ばず、STOP / clarificationとする。

### Workline root

明示値がある場合、そのrootだけをvalidationする。別rootを探索しない。別registryを探さない。確認質問を出さない。無効なら代替候補を探さずSTOPする。

明示値がない場合、今回実行しているconcrete ProjectSTART SKILL.md自身の所属Workline rootから解決する。

```text
concrete ProjectSTART SKILL.md
↓
そのSkillを所有するWorkline root
↓
<root>/registry.md
↓
workline://skills/project-start のtargetが
そのconcrete SKILL.md自身へ戻ることを確認
↓
Workline root確定
```

しない:

- cwd周辺のregistry.md検索
- 親directory全体 / sibling directoryの探索
- filename / mtime / Git上の新しさ / 内容類似による候補比較
- checkpoint / audit / fix / old specを代替正本として探索すること
- 「どちらのWorkline rootですか？」という候補UI

concrete Skillからowning Workline rootを一意解決できなければ、configuration / routing errorとしてSTOPする。その場合もfilesystemから別Worklineを探して救済しない。

## Preflight

1. Project rootが存在するdirectoryであることを確認する。
2. Workline rootが存在するdirectoryであることを確認する。
3. 実行中のWorkline implementationがそのWorkline rootのものであることを確認する（`rules/git` のWorkline implementation。不一致なら何も書かずSTOP）。
4. `<workline-root>/registry.md` を読み、必須4 rule IDと5 Skill IDを一意解決する。
5. 各required Skill targetがroot内のreadable non-empty fileへ解決することを確認する。
6. Git boundaryを確認する。

Git boundary:

```text
Project root = Git root
→ 既存repoを使用

Project root配下にrepoなし かつ 親Git repoなし
→ git init -b main

Project rootが親Git repoのsubdirectory
→ 追加判定する
```

親repoをProject repoとして流用しない。

親Git repoが存在する場合、次の両方をGit自身から機械的に証明できたときだけ `git init -b main` を自動実行してよい。

```text
1. Project root directory全体が
   nearest parent Git repoからignoreされている

AND

2. nearest parent Git repoが
   Project root配下のpathを1件もtrackしていない
```

このときAskUserQuestionを出さない。これは無条件nested repo化ではなく、親repoとProject repoのownershipが衝突しないことをGitから確認できた安全経路である。

次のどれかならSTOPする。

```text
Project rootが親repoからignoreされていない
親repoがProject root配下を1件以上trackしている
ignore状態を確実に判定できない
Git boundaryにその他の曖昧さがある
```

STOP時に「たぶんVaultだから大丈夫」と推測しない。特定のpathを特別扱い・hardcodeしない。判定はGit観測結果だけから行う。

remoteは任意。GitHub repoを自動作成しない。URLを推測しない。既存remoteを変更しない。

### Push destination

remoteがある場合、`rules/git` のpush destinationを人間確認で決める。

```text
remoteなし
→ 承認先を作らない。従来どおり成立

remoteあり + expected push locatorを人間が明示
→ credential混入検査
→ Gitが解決するactive push locatorが正確に1件か検査
→ 明示locatorと文字列一致するときだけ project.yaml へ承認先を書く
→ 初期commitへ含める（pushはしない）

remoteあり + 明示なし
→ Project成立は許可する
→ 承認先を作らない
→ 結果へ unpinned を明示する
→ 最初のpush系operationがSTOPする
```

current remoteを見て承認先を自動生成しない。誤ったremoteが最初から設定されている場合を検出できなくなる。

既存Projectへ承認先を後から入れるのはProject開始の再実行ではなく、pin maintenanceで行う。

既に正常なWorkline Projectなら二重初期化しない。pending Project開始 mutationが無いbroken / partial `.workline` は推測修復せずSTOPする。

## Mutation

`rules/git` のmulti-write mutationを使う。

Project開始がoperation owner。Project開始の下位writeは同じoperation mutationへ属する。

Project開始（初期化）は `rules/git` のProject execution lockの対象外である。同じProjectへProject開始を同時に複数実行することはサポートしない。

途中失敗後にpending Project開始 mutationが入力Projectと一意一致する場合はresumeする。新規初期化として上書きしない。

## Create Project structure

```text
.workline/
├─ project.yaml
├─ roadmaps/
├─ phases/
├─ works/
├─ relations/
│  ├─ roadmap.yaml
│  └─ related.yaml
├─ events/
│  └─ events.jsonl
└─ derivations/
```

空directoryはlocal runtime convenienceでありGit正本ではない。`.gitkeep` を作らない。clone後に空directoryが無くてもbrokenではない。

初期値:

```yaml
# relations/roadmap.yaml
relations: []
```

```yaml
# relations/related.yaml
relations: []
```

`events.jsonl` は空。

## Project bootstrap Skill

ProjectSTART成功後、対象ProjectはClaude Codeアプリから直接開いて日常運用する。そのため canonical structureに加えてProject側entryを1個だけ設置する。

```text
.claude/skills/workline/SKILL.md
```

これはcanonical Skillのコピーではない。非常に薄いbootstrapであり、次だけを持つ。

```text
.workline/project.yaml の存在確認
→ configured Workline root解決
→ registry validation
→ stable ID skills/project-router の一意解決
→ canonical SKILL.md読込
→ 以降はcanonical routerに従う
```

しない:

- canonical Skill（Roadmap / Phase CREATE / CREATE / START等）の本文コピー
- 現在のSkill一覧・Skill対応表の保存
- Workline rootのabsolute pathの埋め込み
- Workline operation semanticsの複製
- junction / symlinkによるcanonical Skill群の展開

bootstrapが知るstable IDは `skills/project-router` だけである。Skillがregistryへ追加されても、Project側を変更せずに利用可能でなければならない。

### conflict

```text
同pathが無い
→ 作成する

同pathがexpected bootstrapと完全一致
→ 再作成しない

同pathの内容が異なる
→ ownership不明としてSTOP
→ 自動上書きしない
```

`.claude/skills/` 配下の既存の他Skillは読まない・変更しない。

対象ProjectのGit設定が `.claude/skills/workline/SKILL.md` をignoreしている場合、bootstrapはcommitできずclone先へ届かない。推測で `-f` せずSTOPして報告する。

## project.yaml

`project.yaml` は、このProjectが使うWorkline rootとrule refsだけを持つ。

概念:

```yaml
workline:
  root: <absolute Workline root>

rules:
  git:
    ref: workline://rules/git
  ai-decision:
    ref: workline://rules/ai-decision
  human-confirmation:
    ref: workline://rules/human-confirmation
  information-tracing:
    ref: workline://rules/information-tracing
```

Project名、概要、目的、現在Roadmap、現在地、進捗、next Work、Skill一覧、versionを重複保存しない。

## Initial commit

Project開始は初期commitまで責任を持つ。

固定message:

```text
chore(workline): initialize project
```

commit対象は、Project開始が今回作成した次だけとする。

```text
.workline/** のtracked成果物
.claude/skills/workline/SKILL.md
```

`git add .` を使わない。既存dirty、既存 `.claude/skills/**` の他Skillをcommitしない。安全に分離不能ならSTOP。

commit前にregistry / routingを再確認する。

初期commit後はpushしない。承認先を書いた場合もpushしない。

commit失敗時は同じmutationをresumeし、既に一致するdomain filesを作り直さない。

## Postcheck

成功条件:

- Git top-level = Project root
- project.yamlが指定Workline rootを保持
- 4 rulesが一意解決
- 5 common Skillsが一意解決
- required central storesが有効
- Project bootstrap Skillがexpected内容で存在しtrackedである
- initial commitが成立
- unrelated user changesをcommit / delete / overwriteしていない
- `.claude/skills/` の他Skillを変更していない

Project開始成功後にRoadmapを自動作成・開始しない。

## 既存Projectへのbootstrap backfill

bootstrap導入前に初期化されたProjectは、ProjectSTARTの再実行では対応しない。established Projectをこのpre-project経路へ入れない。

backfillはbootstrap / infrastructure責務であり、専用のmaintenance経路で行う。新しいdomain Skillを増やさない。

```text
対象: valid established Workline Projectのみ
追加: bootstrap 1ファイルだけ
不変: .workline再初期化なし / project.yaml書き換えなし
      Roadmap / Phase / Work / relations / events変更なし
      .claude/skills の他Skill変更なし
同path異内容: STOP
再実行: idempotent
lock: 成立済みProjectのexecution lockを取得して行う（他processが実行中なら project_operation_busy）
起動: 対象Projectの中から <R>/run-workline.py backfill-bootstrap .（rules/git のWorkline implementation）
```

backfillは通常のmaintenanceなので、Project開始の「初期commit必須・push不要」例外を適用しない。remoteがあればcommit後pushまで行う（clone先で利用可能である必要があるため）。

## 既存Projectへのpush destination pin

push destination承認先を持たない既存Projectも、ProjectSTARTの再実行では対応しない。bootstrap backfillと同じくinfrastructure maintenance経路で行う。新しいdomain Skillを増やさず、Project routerのSkill inventoryへも追加しない。

```text
対象: valid established Workline Projectのみ
入力: 承認するpush locatorを人間が明示（configから導出しない）
検査: credential混入なし / active push locatorが正確に1件 / 明示locatorと文字列一致
変更: .workline/project.yaml の git.push だけ
不変: .workline再初期化なし
      Roadmap / Phase / Work / relations / events変更なし
他のpending mutationがある: STOP（旧承認先向けの進行中operationを壊さない）
lock: 成立済みProjectのexecution lockを取得して行う（他processが実行中なら project_operation_busy）
再実行: idempotent
起動: 対象Projectの中から <R>/run-workline.py pin-push-destination . --url <承認するlocator>（rules/git のWorkline implementation）
```

承認先はGitが返したlocatorそのもの。`.git` の有無・trailing slash・case差・HTTPS/SSHを同一視しない。両方許可するなら人間が両方を明示する。

remote変更の正しい順序:

```text
人間がGit remoteを変更
↓
通常operationは承認先不一致でSTOP（fail-closed）
↓
人間が新destinationを明示してpin maintenance
↓
承認先更新 / commit / 新承認先へpush
↓
通常operation再開
```

AIがcurrent remoteを見て承認先を追従させない。承認先変更は人間確認の対象。
