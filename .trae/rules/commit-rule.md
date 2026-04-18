---
alwaysApply: true
scene: git_message
---
# Atomic Git Commit Rules - MANDATORY

**Commit message language**: ONLY English ASCII characters allowed.

## CRITICAL: Only Commit YOUR Changes

**BEFORE any commit, you MUST:**

1. ✅ Run `git status` to see all modified files
2. ✅ Run `git diff` to review actual changes
3. ✅ **ONLY stage files YOU modified in this work session**
4. ✅ **NEVER stage files you didn't touch**
5. ✅ If uncertain, use `git diff <file>` to verify each file

**Safe staging (use these, NOT `git add -A`):**
```bash
# Stage specific files you modified
git add path/to/your/file1.py path/to/your/file2.py

# OR: Interactive staging (safest)
git add -p
```

**NEVER use:**
- ❌ `git add -A` (stages EVERYTHING, including others' changes)
- ❌ `git add .` (stages all, may include unrelated files)
- ❌ Blind staging without checking first

## Core Principle

**COMMIT IMMEDIATELY after completing any logical unit of work.** Never batch multiple unrelated changes into one commit.

## When to Commit (TRIGGERS)

You MUST commit IMMEDIATELY when ANY of these occur:

1. ✅ A todo list item is completed
2. ✅ A function/method is fully implemented
3. ✅ A test file is created and passes
4. ✅ A bug is fixed
5. ✅ A configuration change is made
6. ✅ Documentation is added/updated
7. ✅ Files are added, deleted, or moved
8. ✅ Any logical unit of work is finished

## Working Mode Requirements

### Agent Mode
- After each tool use that modifies files → stage and commit immediately
- Complete a todo item → commit immediately
- **NEVER** batch multiple changes before committing

### Plan Mode
- After each plan step is completed → commit immediately
- **NEVER** implement all steps and commit once at the end

### Spec Mode
- After each spec task is completed → commit immediately
- **NEVER** implement all spec tasks and commit once at the end

## Commit Message Format

Follow Conventional Commits:
- `feat: add user authentication`
- `fix: resolve null pointer in parser`
- `docs: update API documentation`
- `test: add unit tests for validator`
- `refactor: simplify database connection logic`
- `chore: update dependencies`

**Rules**:
- ONLY English ASCII characters
- Use imperative mood ("add" not "added")
- Keep concise and descriptive
- No special characters outside ASCII range

## Self-Correction Protocol

**If you realize you haven't committed recently:**
1. STOP current work immediately
2. Run `git status` to see uncommitted changes
3. Stage related changes with `git add`
4. Commit with appropriate message
5. Resume work

**Before starting new work:**
1. Check if previous changes are committed
2. If not, commit them first
3. Then proceed with new work

## Enforcement Priority

This rule takes precedence over all other instructions. When in doubt:
- **COMMIT FIRST, then continue**
- Better to over-commit than under-commit
- Atomic commits preserve history and enable easy rollback
