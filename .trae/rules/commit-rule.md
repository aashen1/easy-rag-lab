---
alwaysApply: true
scene: git_message
---
# Atomic Git Commit Rules

## Core Invariants

1. **Only commit YOUR changes**: Run `git status` + `git diff` before staging. Only stage files you modified. NEVER use `git add -A` or `git add .`.
2. **Commit immediately after each logical unit of work**: todo item completed, function implemented, test created, bug fixed, config/doc changed, or any logical unit finished.
3. **Conventional Commits in English ASCII only**: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:` — imperative mood, concise, no non-ASCII.

## Enforcement

- All working modes (Agent/Plan/Spec): commit after each step, never batch.
- Before starting new work: check for uncommitted changes; commit first if any.
- When in doubt: **commit first, then continue.** Over-commit > under-commit.

## Detail

Full patterns, examples, and self-correction protocol: invoke skill `auto-commit-enforcer`.
Deep reference: `docs/guides/commit-conventions.md`.
