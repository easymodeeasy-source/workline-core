# workline-core

Workline の実装・正式仕様リポジトリ。

## Authority

この repository への初期移行完了後、現在仕様の正本は次だけとする。

```text
registry.md
.claude/skills/project-start/SKILL.md
.claude/skills/roadmap/SKILL.md
.claude/skills/phase-create/SKILL.md
.claude/skills/create/SKILL.md
.claude/skills/start/SKILL.md
```

旧 `aiproject-vault/new-dev-os-redesign/` の checkpoint / audit / fix / live-spec は設計履歴・rationaleとして保持するが、実装時のnormative sourceとして横断合成しない。

## Local clone

想定clone先:

```text
D:\AIproject\workline-core
```

## Status

- design review: converged for implementation
- repair-induced regression check: PASS
- implementation: core implemented (registry / mutation / project-start / phase-create / create / start / roadmap)
