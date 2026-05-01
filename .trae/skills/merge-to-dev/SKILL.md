---
name: "merge-to-dev"
description: "Merges current feature branch into dev with --no-ff, auto-generating English merge commit message from diff summary. Invoke when user says 'merge to dev', '合并到dev', or asks to merge feature branch back."
---

# Merge Feature Branch into Dev

Automate the full workflow of merging the current feature branch back into `dev` using `--no-ff`.

## Trigger

User says any of:
- "merge to dev" / "合并到dev"
- "并入dev" / "合回dev"
- "总结变动，合并回dev"
- Any instruction about merging the current branch into dev

## Workflow

### Step 1: Pre-flight Checks

1. Run `git status` to ensure working tree is clean. If dirty:
   - Stage and commit any pending changes first (following atomic commit rules).
   - If unsure what to do with uncommitted changes, ask the user.
2. Run `git branch --show-current` to confirm the current branch name.
3. Verify the current branch is NOT `dev` or `main`. If it is, abort and inform the user.

### Step 2: Summarize Changes

1. Run `git log dev..HEAD --oneline` to list all commits on this branch since diverging from dev.
2. Run `git diff dev...HEAD --stat` to see file-level change summary.
3. Synthesize a concise English summary of what this branch accomplished, grouping by theme if there are many commits.

### Step 3: Draft Merge Commit Message

Generate a merge commit message following this template:

```
Merge branch '<branch-name>' into dev

<One-line summary of the branch's purpose>:

- Change group 1
- Change group 2
- ...

Conflicts resolved:
- <file>: <resolution description>  (only if conflicts occurred)
```

Rules for the message:
- **Language**: English only, ASCII characters.
- **Style**: Imperative mood, concise.
- **Structure**: First line is the standard `Merge branch 'X' into dev` format.
- **Body**: Group related changes thematically, not per-commit.
- Do NOT include trivial changes (e.g., "typo fix" mixed with major features) as top-level items — fold them into relevant groups.

### Step 4: Execute Merge

1. Switch to dev: `git checkout dev`
2. Pull latest dev (if remote exists): `git pull origin dev` (ignore error if no remote)
3. Merge with no-ff: `git merge --no-ff <branch-name> -m "<commit message>"`
   - Use the multi-line commit message drafted in Step 3.

### Step 5: Handle Merge Conflicts (if any)

If conflicts arise:

1. List all conflicted files: `git diff --name-only --diff-filter=U`
2. For each conflicted file:
   - Read the file to understand both sides.
   - Resolve intelligently — keep both sides' intent when possible.
   - If uncertain about a conflict, prefer the incoming branch's change and flag it to the user.
3. After resolving all conflicts:
   - `git add <each-resolved-file>` (only the resolved files, NOT `git add -A`)
   - `git commit --no-edit` to complete the merge
4. Update the merge commit message body to document resolved conflicts under the `Conflicts resolved:` section.

### Step 6: Post-merge Validation

1. Run `pixi run test` to verify the merge doesn't break anything.
2. If tests fail:
   - Report the failures to the user.
   - Suggest `git reset --hard ORIG_HEAD` to undo the merge if needed.
   - Do NOT automatically reset — let the user decide.

### Step 7: Report

Inform the user of the completed merge with:
- Branch name merged
- Number of commits merged
- Whether conflicts were resolved (and how many)
- Test results (pass/fail)
- Suggest deleting the feature branch if no longer needed: `git branch -d <branch-name>`

## Important Notes

- **NEVER use `--squash` or rebase** — this project uses `--no-ff` merge to preserve branch history.
- **NEVER use `git add -A` or `git add .`** during conflict resolution — only stage resolved files.
- **NEVER push to remote** unless the user explicitly asks — this workflow is local only.
- **NEVER delete the feature branch** automatically — suggest it but let the user decide.
- If the user is working in a **git worktree**, be aware that `git checkout dev` may fail if dev is checked out in another worktree. In that case, inform the user and suggest they run the merge from the worktree where dev is checked out, or use `git worktree` commands to manage this.
