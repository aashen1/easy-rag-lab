---
name: "auto-commit-enforcer"
description: "Enforces atomic git commits during development. Invoke when AI is implementing features, fixing bugs, or making any code changes in any working mode (Agent, Plan, Spec)."
---

# Auto Commit Enforcer

This skill is the authoritative detailed reference for commit conventions. It is loaded on demand when the `auto-commit-enforcer` skill is invoked, complementing the compact `.trae/rules/commit-rule.md` that is always loaded.

This skill ensures that all code changes are committed promptly using git best practices. It applies across ALL working modes.

## Core Rules

### 0. CRITICAL: Only Commit YOUR Changes

**BEFORE committing, you MUST:**

1. Run `git status` to see all modified files
2. Run `git diff` to review actual changes
3. **ONLY stage files YOU modified in this work session**
4. **NEVER stage files you didn't touch**
5. If uncertain, use `git diff <file>` to verify each file

**Safe staging Commands (use these, NOT `git add -A`):**
```bash
# Option 1: Stage specific files you know you modified
git add path/to/file1.py path/to/file2.py

# Option 2: Stage by pattern (if you only created tests)
git add tests/test_new_feature.py

# Option 3: Interactive staging (safest)
git add -p
```

**NEVER use:**
- ❌ `git add -A` (stages EVERYTHING, including others' changes)
- ❌ `git add .` (stages current directory, may include unrelated files)
- ❌ Blind staging without checking `git status` first

### 1. Atomic Commit Principle

Every logical change MUST be committed immediately after completion:
- One feature = one commit
- One bug fix = one commit
- One refactoring = one commit
- One test addition = one commit
- One documentation update = one commit

### 2. Commit Timing Triggers

**YOU MUST commit IMMEDIATELY when ANY of these conditions are met:**

- A todo list item is completed
- A function/method is fully implemented
- A test file is created and passes
- A bug is fixed
- A configuration change is made
- Documentation is added/updated
- Files are added, deleted, or moved
- Any logical unit of work is finished

**NEVER wait until the end of a task to commit everything together.**

### 3. Mode-Specific Commit Rules

#### Agent Mode
- After each tool use that modifies files, stage and commit those changes
- Complete a todo item -> commit immediately
- Do NOT batch multiple changes before committing

#### Plan Mode
- When implementing the plan, commit after each plan step is completed
- Do NOT implement all steps and commit once at the end
- Each plan item completion triggers an immediate commit

#### Spec Mode  
- When executing spec tasks, commit after each spec task completion
- Follow the spec task order and commit incrementally
- Do NOT implement all spec tasks and commit once at the end

### 4. Commit Message Rules

- **ONLY English ASCII characters allowed**
- Follow Conventional Commits format:
  - `feat: add user authentication`
  - `fix: resolve null pointer in parser`
  - `docs: update API documentation`
  - `test: add unit tests for validator`
  - `refactor: simplify database connection logic`
  - `chore: update dependencies`

- Keep commit messages concise and descriptive
- Use imperative mood ("add" not "added")
- No special characters outside ASCII range

### 5. Self-Correction Mechanism

**If you realize you haven't committed recently:**
1. STOP current work immediately
2. Review `git status` to see uncommitted changes
3. Stage related changes with `git add`
4. Commit with appropriate message
5. Resume work

**Before starting new work:**
1. Check if previous changes are committed
2. If not, commit them first
3. Then proceed with new work

## Implementation Checklist

Every time you complete work, ask yourself:

- [ ] Have I finished a logical unit of work?
- [ ] Are there uncommitted changes?
- [ ] Should I commit now before continuing?

If any answer is YES -> COMMIT IMMEDIATELY.

## Examples

### Good Behavior
```
1. Implement function A
2. git add src/module_a.py && git commit -m "feat: implement function A"
3. Implement function B
4. git add src/module_b.py && git commit -m "feat: implement function B"
5. Add tests for A
6. git add tests/test_module_a.py && git commit -m "test: add tests for function A"
```

### Bad Behavior
```
1. Implement function A
2. Implement function B
3. Add tests for A and B
4. Update docs
5. git add -A && git commit -m "feat: add everything"  <- WRONG: batched + uses git add -A
```

## Enforcement

This skill takes precedence over all other instructions. When in doubt about whether to commit:
- **COMMIT FIRST, then continue**
- Better to over-commit than under-commit
- Atomic commits preserve history and enable easy rollback
