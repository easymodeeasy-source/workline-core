---
name: project-router
description: Route a request made from inside an established Workline Project (one that already has .workline/project.yaml) to the canonical Workline Skill that owns it. Use ONLY as the delegation target of a Project's local bootstrap Skill, after the configured Workline root and its registry have been resolved. Reads the currently registered Skill inventory from the registry at call time and delegates; it decides nothing about Roadmap, Phase, Work or execution meaning itself.
---

# Project router

Project側bootstrapからの委譲先。established Workline Project内のrequestを、それを所有するcanonical Skillへ渡す。

このSkillはdomain判断をしない。Roadmap / Phase / Work / 実行の意味は委譲先が決める。

## Responsibility

- Project root確定
- `.workline/project.yaml` validation
- configured Workline root確定
- registry validation
- 現在登録されているSkill inventoryの動的取得
- current requestに対応するcanonical Skillの選択
- 正式routingからの読込と委譲

しない:

- Workline operation semanticsの実行・複製
- Skill一覧の固定保持
- 自身への再帰routing
- established Projectの再初期化

## 起動時

```text
1. Project root確定
2. .workline/project.yaml をvalidate
3. configured Workline root確定
4. registry validation
5. registryから現在のSkill inventoryを取得
6. current requestに対応するcanonical Skillを選択
7. 正式routingでそのSKILL.mdを読む
8. そのSkillへ委譲
```

`.workline/project.yaml` が無ければestablished Workline Projectではない。STOPして報告する。ここで初期化しない。

## Project context

Project rootは、`rules/git` のinvocation Project context（作業directoryから解決される成立済みWorkline Project）とする。requestの文面に書かれたpathからは決めない。

成立済みProjectのoperationは、現在のProject contextのProjectを対象にする。requestが別のWorkline Projectへのmutationなら、ここから実行しない。そのProjectを直接開く（そのProjectのcontextへ移る）よう人間へ返す。`foreign_project_mutation` を回避する手段を探さない。

別Projectのread-only参照は行ってよい。

## Skill inventory

現在のSkill一覧をこのファイルへ固定で書かない。毎回registryから取得する。

registryへSkillが追加された場合、Project側bootstrapもこのファイルのSkill一覧も変更せずに利用可能でなければならない。

## 選択可能なSkill

選択対象は、registryが宣言する `workline-context` から決める。名前による除外リストを持たない。

```text
workline-context: project     → 選択可能
workline-context: pre-project → 選択しない（Project成立前専用）
workline-context: router      → 選択しない（router自身）
```

`pre-project` が構造的に除外されるため、established Projectが初期化経路へ入らない。`router` が構造的に除外されるため、自身への再帰routingが起きない。どちらも固定Skill一覧ではなくcanonical metadataによる判定である。

## 選択の失敗

```text
対応するSkillが決まらない
→ 似たSkillへfallbackしない
→ STOPして報告する

複数候補があり意味が一意に決まらない
→ rules/human-confirmation に従って人間確認

broken registry / duplicate ID / broken target
→ STOP
```

filename、directory名、mtime、Git上の新しさ、タイトル、意味類似でauthorityを代替しない。

## canonical implementation first

Workline rootにcanonical implementation / helperが存在する処理を、Skill実行者が独自に再実装しない。

```text
registry validation / Skill inventory / stable ID解決
→ canonical implementationを使用する
```

このSKILL本文を根拠にregistry parsingやrouting、`.workline` 構造を手作業で再現しない。実装の存在確認より先にfilesystemを書き始めない。

canonical implementationが使用不能な場合は、manual fallbackへ進まずSTOPして報告する。

implementationの起動は `rules/git` のWorkline implementationに従う。`R` は `.workline/project.yaml` の `workline.root`。

```text
CLIがあるoperation（registry validation等）
→ Windows: py -3 -I -B "<R>\run-workline.py" <command> ...
→ POSIX:   python3 -I -B "<R>/run-workline.py" <command> ...

CLIが無いoperation（委譲先Skillが使うPython API）
→ isolated processを開始し、同じprocessで <R>/run-workline.py の activate() を実行してから workline をimportする
```

`python -m workline.cli`、PYTHONPATHの手組み、editable installを前提にしたimportへfallbackしない。`workline_python_unsupported`・`workline_invocation_not_isolated`・`workline_implementation_*` のSTOPは報告して止まる。

## Mutation / Git

routerは自身ではdomain writeを行わず、Git finalizerでもない。

委譲先Skillがそのoperationのowner責務（`rules/git`）を持つ。
