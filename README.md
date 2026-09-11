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

## Runtime

Workline implementationはinstallせず、Workline rootのsourceをそのまま実行する。以下 `<R>` はconfigured Workline root（成立済みProjectでは `.workline/project.yaml` の `workline.root`）。正式な規則は `registry.md` の `rules/git`（Workline implementation）にある。

```text
Python      : 3.11以上（exact versionは固定しない）
Windows     : py -3
POSIX       : python3
entry       : <R>/run-workline.py
runtime源   : <R>/src/workline（working tree。install・venv・runtime依存なし）
```

CLIがあるoperationはlauncherから起動する。`-I -B` は必須。

```text
Windows: py -3 -I -B "<R>\run-workline.py" <command> ...
POSIX:   python3 -I -B "<R>/run-workline.py" <command> ...
```

CLIが無いoperation（Roadmap / START等）はPython APIを使う。isolated processで先に `<R>/run-workline.py` の `activate()` を実行し、その後にだけ `workline` をimportする。activateはそのprocessだけで有効で、別processへは何も引き継がない。

Windows PowerShell（5.1 / 7）:

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

正式な起動ではないもの（動いてもcanonicalではない）:

```text
python -m workline.cli ...
workline（console script）
PYTHONPATHの手作業設定
editable install（pip install -e）を前提にしたimport
site-packagesのworklineの直接起動
```

保証すること:

```text
Python 3.11以上で起動する
実際にloadされたworkline（全moduleのorigin）が <R>/src/workline であることを検査する
成立済みProjectの操作は、そのProjectのconfigured rootのimplementationでなければSTOPし、lockも書込みも作らない
```

`-I` はPYTHONPATH・user site-packages・作業directory由来のimportを抑えるが、system site-packagesやその `.pth` は残り得る。identityを保証するのは `-I` ではなく、load済みmoduleのorigin検証である。これはsecurity sandboxではない。`-B`（とlauncher自身の設定）により、canonical runtimeはWorkline rootへbytecode cacheを書かない。

保証しないこと（`BACKLOG.md` BL-013）: committed revision・main branch・clean tree・released version・dev / runtime分離・process間のrevision一致・実行中のsource変更。`<R>` のworking treeが、未commitの変更も含めてそのまま実行される。

## Claude Codeアプリ運用

### 新規Project

workline-core を Claude Code アプリで開き、ProjectSTART を使う。

```text
Claude Codeアプリで D:\AIproject\workline-core を開く
→ ProjectSTART
→ 対象directoryがWorkline Projectになる
```

ProjectSTARTだけがWorkline root側から使うpre-project操作である。

Workline root自身はProjectSTARTのtargetにしない（self-hostingは現在サポートしない）。

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

対象Projectを直接開き、作業directoryをProject内にして実行する（`<R>` はそのProjectのconfigured Workline root。Runtime参照）。

```powershell
py -3 -I -B "<R>\run-workline.py" backfill-bootstrap .
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

remoteがあるProjectのpushは、Project正本が承認したdestinationと一致するときだけ行う（`rules/git`）。承認先を持たない既存Projectは、push系operationで `push_destination_unpinned` としてSTOPする。対象Projectを直接開き、Project内で1回だけ次を実行する。

```powershell
py -3 -I -B "<R>\run-workline.py" pin-push-destination . --url <approved push URL>
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

新規Projectはこの承認をProjectSTART時に行える（Workline rootから実行する）。

```powershell
py -3 -I -B "<R>\run-workline.py" project-start <project-root> --workline-root <R> --expected-push-url <approved push URL>
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

implementationは [Runtime](#runtime) の起動形だけで起動する。`python -m workline.cli`・PYTHONPATHの手組み・editable installへfallbackしない。

## Status

- design review: converged for implementation
- repair-induced regression check: PASS
- implementation: core implemented (registry / mutation / project-start / project-router / bootstrap + backfill / phase-create / create / start / roadmap)
- post-project Skill discovery: implemented (Project-side bootstrap → canonical router → dynamic registry inventory)
- push destination identity: implemented (project.yaml pin → entry check → durable git_push destination → pin maintenance)

## Tests

Windowsの開発環境では、ambientの `python` ではなくPython launcherで3.11以上を選ぶ（そのinterpreterにpytestが必要）。これはtestの実行例であり、Workline runtimeの起動方法ではない。

```powershell
py -3 -m pytest tests -q
```
