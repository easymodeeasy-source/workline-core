---
name: project-start
description: Initialize a human-provided local folder as a new Workline Project. Use when a folder must be connected to the common Workline registry, receive the canonical .workline structure, validate the Git-root boundary, and create the required initial local commit without starting a Roadmap.
---

# Project開始

人間が指定したlocal folderをWorkline利用可能な新規Projectとして初期化する。

## Input

必須:

- Project rootのabsolute path
- Workline rootのabsolute path

Workline rootを推測・探索しない。

## Preflight

1. Project rootが存在するdirectoryであることを確認する。
2. Workline rootが存在するdirectoryであることを確認する。
3. `<workline-root>/registry.md` を読み、必須4 rule IDと5 Skill IDを一意解決する。
4. 各required Skill targetがroot内のreadable non-empty fileへ解決することを確認する。
5. Git top-levelを確認する。

Git boundary:

```text
Project root = Git root
→ 既存repoを使用

Project root配下にGit repoなし、親repoにも含まれない
→ git init -b main

Project rootが親Git repoのsubdirectory
→ STOP
```

親repoをProject repoとして流用しない。自動でnested repo化しない。

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
