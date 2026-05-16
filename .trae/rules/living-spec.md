---
alwaysApply: true
scene: spec_management
---
# Living Spec Rule

## Core Invariants

1. **One feature, one spec directory**: `.trae/specs/<feature-name>/` contains exactly 4 files: `spec.md`, `progress.md`, `handoff.md`, `checklist.md`.
2. **No numbered subdirectories**: Never create `0-xxx/`, `1-xxx/`, `2-xxx/` etc. inside a spec directory. This is the "numbered snapshot" anti-pattern that misleads AI with stale info.
3. **Current state = overwrite**: The "current state" sections in progress.md and spec.md are always overwritten with the latest info. Never append new status alongside old status.
4. **Changelog = append-only**: The Changelog and Decision Log sections are append-only. Never modify historical entries.
5. **handoff.md = per-session overwrite**: Each session overwrites handoff.md entirely. Only the latest handoff is kept.

## AI Reading Order

When picking up a feature, read in this order:
1. `progress.md` "当前状态" section — FIRST, this is the single source of truth for completion status
2. `spec.md` "当前需求" section — current requirements
3. `checklist.md` "验收项" section — acceptance status
4. `handoff.md` — last session's handoff

**NEVER** read Changelog/Decision Log before reading Current State. Historical info biases AI judgment of current status.

## Prohibited Actions

- Creating numbered subdirectories inside spec directories
- Leaving stale completion percentages in progress.md
- Creating new acceptance reports instead of updating checklist.md
- Having multiple spec.md/progress.md/checklist.md for the same feature
- Quoting completion status from old numbered folders instead of progress.md

## Detail

Full methodology, templates, and migration guide: `docs/dev-guides/living-spec.md`.
