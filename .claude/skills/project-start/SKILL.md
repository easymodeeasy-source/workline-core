---
name: project-start
description: Initialize a local folder as a new Workline Project. This is the only Workline Skill usable before a Workline Project exists — use it when a folder that has no .workline/project.yaml yet — named explicitly, or indicated as the current directory ("このルート", "ここ", "this folder") — must be connected to the common Workline registry, receive the canonical .workline structure, resolve its Git boundary, and get the required initial local commit without starting a Roadmap.
---

# Project開始

対象local folderをWorkline利用可能な新規Projectとして初期化する。

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
3. `<workline-root>/registry.md` を読み、必須4 rule IDと5 Skill IDを一意解決する。
4. 各required Skill targetがroot内のreadable non-empty fileへ解決することを確認する。
5. Git boundaryを確認する。

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

既に正常なWorkline Projectなら二重初期化しない。pending Project開始 mutationが無いbroken / partial `.workline` は推測修復せずSTOPする。

## Mutation

`rules/git` のmulti-write mutationを使う。

Project開始がoperation owner。Project開始の下位writeは同じoperation mutationへ属する。

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

Project開始が今回作成した内容だけをstageする。`git add .` を使わない。既存dirtyをcommitしない。安全に分離不能ならSTOP。

commit前にregistry / routingを再確認する。

初期commit後はpushしない。

commit失敗時は同じmutationをresumeし、既に一致するdomain filesを作り直さない。

## Postcheck

成功条件:

- Git top-level = Project root
- project.yamlが指定Workline rootを保持
- 4 rulesが一意解決
- 5 common Skillsが一意解決
- required central storesが有効
- initial commitが成立
- unrelated user changesをcommit / delete / overwriteしていない

Project開始成功後にRoadmapを自動作成・開始しない。
