# workline-core

Workline の実装・正式仕様リポジトリ。

## Authority

この repository への初期移行完了後、現在仕様の正本は次だけとする。

```text
registry.md
registry-routed canonical Skills（.claude/skills/<name>/SKILL.md）
```

canonical Skillの現在の集合は `registry.md` の `workline-id: skills/*` から読む。README側にSkill一覧を二重管理しない。

旧 `aiproject-vault/new-dev-os-redesign/` の checkpoint / audit / fix / live-spec は設計履歴・rationaleとして保持するが、実装時のnormative sourceとして横断合成しない。

非正本の改善候補一覧は `BACKLOG.md` に置くが、正本は引き続き `registry.md` と canonical Skills だけである。

## Local clone

想定clone先:

```text
D:\AIproject\workline-core
```

## Claude Codeアプリ運用

### 新規Project

workline-core を Claude Code アプリで開き、ProjectSTART を使う。

```text
Claude Codeアプリで D:\AIproject\workline-core を開く
→ ProjectSTART
→ 対象directoryがWorkline Projectになる
```

ProjectSTARTだけがWorkline root側から使うpre-project操作である。

ProjectSTARTは canonical `.workline` structure に加えて、Project側entryを1個だけ設置する。

```text
<project-root>/.claude/skills/workline/SKILL.md
```

### ProjectSTART後（日常運用）

対象ProjectをClaude Codeアプリから直接開く。日常作業のために毎回workline-coreを開かない。

```text
Claude Codeアプリで <project-root> を開く
→ local bootstrap Skill（.claude/skills/workline/SKILL.md）
→ .workline/project.yaml からWorkline root解決
→ registry validation
→ canonical project-router（workline://skills/project-router）
→ current registryのSkill inventory
→ 該当するcanonical Skill
```

Project側に置かれるのはこのbootstrap 1ファイルだけである。

```text
置かない: canonical Skillのコピー
置かない: 現在のSkill一覧 / Skill対応表
置かない: Workline rootのabsolute path
置かない: junction / symlinkによるcanonical Skill展開
置かない: Workline operation semanticsの複製
```

bootstrapが知るstable IDは `skills/project-router` だけである。

### 新Skill追加

canonical Skillとregistryだけを更新する。

```text
workline-coreに canonical SKILL.md を追加
→ registry.md に workline-id / workline-target / workline-context を登録
→ 完了
```

既存Projectの更新は不要。Project側bootstrapは1byteも変更しない。routerが呼び出し時にregistryからinventoryを取得するため、追加されたSkillはそのまま利用可能になる。

### 境界

```text
Workline root側     : canonical Skill本文・registry・実装
Project側           : .workline（domain正本）＋ bootstrap 1ファイル
Skill追加の影響範囲  : Workline rootのみ
```

### 既存Projectへのbootstrap backfill

bootstrap導入前に初期化されたProjectには、maintenance経路でbootstrapだけを追加する。ProjectSTARTの再実行では行わない（established Projectをpre-project経路へ入れない）。

```bash
python -m workline.cli backfill-bootstrap <project-root>
```

```text
対象: valid established Workline Projectのみ
追加: bootstrap 1ファイルだけ
不変: .workline再初期化なし / project.yaml書き換えなし
      Roadmap / Phase / Work / relations / events変更なし
      .claude/skills の他Skill変更なし
同path異内容: STOP（ownership不明・自動上書きしない）
再実行: idempotent
```

backfillは通常のmaintenanceなので、Project開始の「初期commit必須・push不要」例外を適用しない。remoteがあればcommit後pushまで行う（clone先で利用可能である必要があるため）。

### Push destination pin

remoteがあるProjectのpushは、Project正本が承認したdestinationと一致するときだけ行う（`rules/git`）。承認先を持たない既存Projectは、push系operationで `push_destination_unpinned` としてSTOPする。1回だけ次を実行する。

```bash
python -m workline.cli pin-push-destination <project-root> --url <approved push URL>
```

```text
入力: 承認するlocatorを人間が明示（current remoteから自動生成しない）
検査: credential混入なし / Gitが解決するactive push locatorが正確に1件 /
      明示locatorと文字列一致
変更: .workline/project.yaml の git.push だけ（1 commit）
不変: .workline再初期化なし
      Roadmap / Phase / Work / relations / events変更なし
他のpending mutationがある: STOP
再実行: idempotent
```

承認先は `git remote get-url --push --all` が返したlocatorそのものを使う。`.git` の有無・trailing slash・case差・HTTPS/SSHの違いをWorklineが同一視することはない（サーバによっては別repositoryになり得るため）。両方を使うなら `--url` を複数渡して人間が明示する。表記が違うだけでSTOPすることは、別repositoryを同一と誤認しないための意図した挙動である。

新規Projectはこの承認をProjectSTART時に行える。

```bash
python -m workline.cli project-start <project-root> --workline-root <workline-root> --expected-push-url <approved push URL>
```

remoteを正式に変更する場合の順序:

```text
人間がGit remoteを変更
→ 通常operationは不一致でSTOP（fail-closed）
→ 人間が新destinationを明示して pin-push-destination
→ 通常operation再開
```

Worklineが保証するのは「どのrepositoryへpushするか」まで。HTTPS credential account / SSH identity / credential manager / provider CLIのlogin accountは保証しない。

## Canonical implementation first

canonical implementationが存在する処理を、Skill実行者が独自に再実装しない。

```text
実装の存在を先に確認する
→ 存在する: それを実行する
→ 使用不能: STOPして報告する（manual fallbackへ進まない）
```

SKILL本文を根拠に `.workline` 構造・project.yaml・bootstrap・registry parsingを手作業で再現しない。手組みした構造は未検証の再実装であり、canonical implementationからはbroken / partialとして扱われる。

## Status

- design review: converged for implementation
- repair-induced regression check: PASS
- implementation: core implemented (registry / mutation / project-start / project-router / bootstrap + backfill / phase-create / create / start / roadmap)
- post-project Skill discovery: implemented (Project-side bootstrap → canonical router → dynamic registry inventory)
- push destination identity: implemented (project.yaml pin → entry check → durable git_push destination → pin maintenance)

## Tests

```bash
python -m pytest tests -q
```
