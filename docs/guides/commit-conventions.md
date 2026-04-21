# Commit Conventions — Deep Reference

This document is the Layer 3 reference for commit conventions. It is not auto-loaded; read it when you need detailed examples, edge cases, or self-correction guidance.

For the compact always-loaded rules, see `.trae/rules/commit-rule.md`. For the full skill with examples, invoke skill `auto-commit-enforcer`.

---

## Conventional Commits — Complete Type List

| Type | Usage | Example |
|------|-------|---------|
| `feat` | New feature | `feat: add hybrid retrieval support` |
| `fix` | Bug fix | `fix: resolve NDCG out-of-range values` |
| `docs` | Documentation only | `docs: update ragas evaluation guide` |
| `test` | Adding or updating tests | `test: add unit tests for chunker` |
| `refactor` | Code restructuring, no behavior change | `refactor: extract create_anthropic_client` |
| `chore` | Build, config, tooling, dependencies | `chore: update ruff configuration` |
| `style` | Formatting, whitespace (no logic change) | `style: fix trailing whitespace` |
| `perf` | Performance improvement | `perf: cache embedding results` |
| `ci` | CI/CD configuration | `ci: add github actions workflow` |
| `build` | Build system or external dependencies | `build: upgrade pixi manifest` |

### Scope (Optional)

Append scope in parentheses for large projects: `feat(retriever): add BM25 hybrid search`

### Breaking Changes

Use `!` after type or add `BREAKING CHANGE:` in footer:
```
feat!: change API response format
BREAKING CHANGE: response.data is now response.results
```

---

## What Counts as a "Logical Unit of Work"

A logical unit is a change that makes sense on its own — you could revert it without breaking other unrelated changes.

| Clearly one commit | Clearly NOT one commit |
|--------------------|-----------------------|
| Implement a single function | Implement 5 functions across 3 modules |
| Fix one bug | Fix 3 unrelated bugs |
| Add tests for one module | Add tests + fix bugs + update docs all at once |
| Update one config file | Update config + refactor code that uses it |
| Add a new CLI flag | Add flag + change 5 commands to use it |

### Gray Areas

**Bug fix + test for that bug**: One commit is fine — the test validates the fix.

**Refactor + feature that depends on it**: Two commits — the refactor should stand alone.

**Multiple files changed for one feature**: One commit — e.g., `feat: add reranker support` may touch retriever, config, and tests.

---

## Common Anti-Patterns

### 1. The Mega Commit
```
git add -A && git commit -m "feat: add everything"
```
**Problem**: Impossible to revert selectively. Mixes features, fixes, and chores.

### 2. The Half-Commit
```
git add src/parser.py && git commit -m "feat: add PDF parser"
```
**Problem**: If parser.py depends on a new utility in utils.py that wasn't staged, the commit is broken.

### 3. The Formatting Commit
```
git commit -m "style: fix lint errors"
```
**Better**: Let `pixi run lint` and pre-commit hooks handle formatting automatically. Don't waste a commit on it unless it's a deliberate style change.

### 4. The Vague Message
```
git commit -m "fix: stuff"
git commit -m "update"
git commit -m "wip"
```
**Problem**: Future you (or a teammate) cannot understand what changed.

---

## Complex Scenarios

### Scenario: Bug fix that requires a refactor

```
1. git add src/retriever.py && git commit -m "refactor: extract score normalization"
2. git add src/retriever.py tests/test_retriever.py && git commit -m "fix: resolve NDCG out-of-range values"
```

### Scenario: Feature spanning multiple files

```
1. git add src/reranker.py src/config.yaml && git commit -m "feat: add reranker module and config"
2. git add src/pipeline.py && git commit -m "feat: integrate reranker into pipeline"
3. git add tests/test_reranker.py && git commit -m "test: add reranker unit tests"
```

### Scenario: Accidentally modified unrelated files

```
1. git status  # discover you also touched .env by accident
2. git diff .env  # verify it's not your change
3. git checkout .env  # discard the accidental change
4. git add src/your_file.py && git commit -m "feat: your actual change"
```

---

## Self-Correction Protocol

If you realize you haven't committed recently:

1. **STOP** current work immediately
2. Run `git status` to see uncommitted changes
3. Group changes into logical units
4. Stage and commit each unit separately
5. Resume work

Before starting new work:

1. Check if previous changes are committed (`git status`)
2. If not, commit them first
3. Then proceed with new work

---

## Integration with Pre-commit Hooks

This project uses pre-commit hooks (see `docs/guides/lint-and-precommit.md`):

- **ruff**: Auto-formats and lints Python files on commit
- **trailing-whitespace**: Removes trailing whitespace
- **yaml**: Validates YAML files
- **merge-conflict**: Detects unresolved conflict markers

If a hook fails, the commit is aborted. Fix the issues and re-commit. Do NOT use `--no-verify` to bypass hooks.
