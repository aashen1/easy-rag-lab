---
name: "todo-archiver"
description: "Archives TODO.md issues to .issues/ directory using issue CLI. Invoke when starting a new conversation, when user says '打扫卫生'/'归档TODO', or when checking for unarchived issues."
---

# TODO Archiver

This skill implements the one-way archival mechanism from `TODO.md` (human-managed) to `.issues/` (AI-managed issue system), with reverse sync for completed issues.

## Core Principle

- **TODO.md** belongs to the human. AI may only APPEND timestamps and MODIFY checkboxes. AI must NEVER alter the human's original text.
- **.issues/** is the issue management system. AI manages issues via CLI commands.
- Archival is one-way: TODO → .issues/. Completion sync is reverse: .issues/ → TODO.

## Trigger Conditions

Invoke this skill when ANY of these conditions are met:

1. A new conversation starts (check for unarchived issues)
2. User says "打扫卫生", "归档TODO", "check TODO", "archive TODO", or similar
3. AI notices unarchived `- [ ]` items in TODO.md during any task

## Step-by-Step Procedure

### Phase 1: Read and Parse

1. Read `TODO.md` in full
2. Run `pixi run issue summary` to get current issue statistics
3. Parse all `- [ ]` and `- [x]` items in TODO.md
4. Categorize each item by its current state:

| State | Pattern | Action |
|-------|---------|--------|
| **New** | `- [ ] text` (no `📋` marker) | Archive to .issues/ |
| **Archived** | `- [ ] text 📋 YYYY-MM-DD 归档为 [ID]` | Check completion |
| **Completed** | `- [x] text 📋 ... ✅ YYYY-MM-DD ...` | No action needed |

### Phase 2: Archive New Issues

For each **New** item (`- [ ]` without `📋`):

1. **Classify** the issue into one of these categories:
   - `bug`: Something is broken or incorrect
   - `feat`: New functionality to add
   - `rf`: Code restructuring without behavior change
   - `opt`: Performance improvement
   - `inv`: Investigation, research, or analysis needed
   - `test`: Test-related work

2. **Assess priority**:
   - `high`: Blocking, critical, or urgent
   - `medium`: Normal priority (default)
   - `low`: Nice-to-have, can wait

3. **Create issue via CLI**:
   ```bash
   pixi run issue create --type <type> --title "<title>" --priority <priority>
   ```
   
   Example:
   ```bash
   pixi run issue create --type bug --title "Fix login error" --priority high
   pixi run issue create -t feat -T "Add dark mode" -p medium -l "ui,enhancement"
   ```

4. **Parse CLI output** to get the generated issue ID (format: `TYPE-YYYYMMDD-SEQ-WTID`)

5. **Update TODO.md**: Append archive timestamp to the original item:
   ```
   - [ ] original text 📋 2026-04-27 归档为 [BUG-20260427-001-wt1]
   ```
   - Do NOT modify the original text
   - Do NOT check the checkbox
   - Do NOT move the item

### Phase 3: Sync Completed Issues

For each **Archived** item (`- [ ]` with `📋` but without `✅`):

1. Extract the issue ID from the `📋` marker (e.g., `[BUG-20260427-001-wt1]`)
2. Check issue status via CLI:
   ```bash
   pixi run issue show <issue_id>
   ```
3. If the issue status is `done`:
   a. Change `- [ ]` to `- [x]` in TODO.md
   b. Append completion timestamp after the archive marker:
      ```
      - [x] original text 📋 2026-04-27 归档为 [BUG-20260427-001-wt1] ✅ 2026-04-28 该issue已确认完成
      ```
   c. **Move** the entire line from its current location to the completion date's section:
      - Find or create the `## YYYY-MM-DD` heading (today's date)
      - Find or create the `### verbose` subsection under that date
      - Place the item there
      - Remove the item from its original location (My Backlog or previous date section)

### Phase 4: Generate Summaries

For each date heading (`## YYYY-MM-DD`) in TODO.md:

1. Read all items under the `### verbose` subsection
2. If the `### summary` subsection is missing or incomplete, generate it:
   - Each verbose item gets a concise one-line summary
   - Format: `- [x] concise description（ID）` or `- [x] concise description`
   - Keep summaries factual and action-oriented
   - Include the issue ID if available
3. Do NOT remove or modify the verbose subsection

### Phase 5: Update Context

Run `pixi run issue context` to update the current focused issues context file at `.issues/context.md`.

## Formatting Rules

### Archive Timestamp Format
```
📋 YYYY-MM-DD 归档为 [TYPE-YYYYMMDD-SEQ-WTID]
```
Example: `📋 2026-04-27 归档为 [BUG-20260427-001-wt1]`

### Completion Timestamp Format
```
✅ YYYY-MM-DD 该issue已确认完成
```
Example: `✅ 2026-04-28 该issue已确认完成`

### Full Item Lifecycle Example
```
New:        - [ ] 优化"新用户"链路的性能
Archived:   - [ ] 优化"新用户"链路的性能 📋 2026-04-27 归档为 [OPT-20260427-001-wt1]
Completed:  - [x] 优化"新用户"链路的性能 📋 2026-04-27 归档为 [OPT-20260427-001-wt1] ✅ 2026-04-28 该issue已确认完成
```

## Safety Rules

1. **NEVER modify the human's original text** — only append timestamps and change checkbox state
2. **NEVER delete items from TODO.md** — only move them between sections
3. **NEVER create duplicate issues** — always check if an issue already exists
4. **NEVER mark an issue as completed in TODO.md unless it is confirmed done in .issues/**
5. **When in doubt about classification, use `inv` (Investigation)** — it can always be reclassified later
6. **Preserve all existing content** — if a date section already has a summary, only add new items to it, don't rewrite existing summaries

## CLI Command Reference

| Command | Description |
|---------|-------------|
| `pixi run issue create -t <type> -T "<title>"` | Create new issue |
| `pixi run issue list` | List active issues |
| `pixi run issue list --all` | List all issues |
| `pixi run issue show <id>` | Show issue details |
| `pixi run issue update <id> --status <status>` | Update issue status |
| `pixi run issue start <id>` | Mark issue as in_progress |
| `pixi run issue done <id>` | Mark issue as done |
| `pixi run issue summary` | Generate statistics summary |
| `pixi run issue context` | Show focused issues |

## Issue Type Mapping

| Old Category | New CLI Type | Description |
|--------------|--------------|-------------|
| BUG-NNN | `bug` | Something broken |
| FEAT-NNN | `feat` | New feature |
| RF-NNN | `rf` | Refactoring |
| OPT-NNN | `opt` | Optimization |
| INV-NNN | `inv` | Investigation |
| TEST-NNN | `test` | Test-related |

## Migration Note

The old `docs/backlog.md` system has been migrated to `.issues/` directory. Legacy IDs like `BUG-001` are preserved in the `legacy_id` field of new issue files. Use `pixi run issue migrate --verify` to verify migration results.
