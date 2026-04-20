---
name: "todo-archiver"
description: "Archives TODO.md issues to docs/backlog.md. Invoke when starting a new conversation, when user says '打扫卫生'/'归档TODO', or when checking for unarchived issues."
---

# TODO Archiver

This skill implements the one-way archival mechanism from `TODO.md` (human-managed) to `docs/backlog.md` (AI-managed), with reverse sync for completed issues.

## Core Principle

- **TODO.md** belongs to the human. AI may only APPEND timestamps and MODIFY checkboxes. AI must NEVER alter the human's original text.
- **docs/backlog.md** belongs to the AI. AI manages its structure, IDs, and status.
- Archival is one-way: TODO → backlog. Completion sync is reverse: backlog → TODO.

## Trigger Conditions

Invoke this skill when ANY of these conditions are met:

1. A new conversation starts (check for unarchived issues)
2. User says "打扫卫生", "归档TODO", "check TODO", "archive TODO", or similar
3. AI notices unarchived `- [ ]` items in TODO.md during any task

## Step-by-Step Procedure

### Phase 1: Read and Parse

1. Read `TODO.md` in full
2. Read `docs/backlog.md` in full
3. Parse all `- [ ]` and `- [x]` items in TODO.md
4. Categorize each item by its current state:

| State | Pattern | Action |
|-------|---------|--------|
| **New** | `- [ ] text` (no `📋` marker) | Archive to backlog |
| **Archived** | `- [ ] text 📋 YYYY-MM-DD 归档为 [ID]` | Check completion |
| **Completed** | `- [x] text 📋 ... ✅ YYYY-MM-DD ...` | No action needed |

### Phase 2: Archive New Issues

For each **New** item (`- [ ]` without `📋`):

1. **Classify** the issue into one of these categories:
   - `BUG-NNN`: Something is broken or incorrect
   - `FEAT-NNN`: New functionality to add
   - `RF-NNN`: Code restructuring without behavior change
   - `OPT-NNN`: Performance improvement
   - `INV-NNN`: Investigation, research, or analysis needed

2. **Assign ID**: Find the highest existing NNN in that category in backlog.md, increment by 1

3. **Assess scale** (for Feature and Refactor only):
   - 小 (small): Single file, < 50 lines changed
   - 中 (medium): Multiple files, 50-200 lines changed
   - 大 (large): Cross-module, > 200 lines changed

4. **Write to backlog.md**: Add the issue to the appropriate section table with:
   - ID
   - Concise description (summarized from the verbose TODO text)
   - Source: `[TODO.md](../TODO.md)`
   - Status: `📋 待处理`
   - Scale (if applicable)
   - Notes (key details from the verbose text that affect implementation)

5. **Update TODO.md**: Append archive timestamp to the original item:
   ```
   - [ ] original text 📋 2026-04-21 归档为 [RF-007]
   ```
   - Do NOT modify the original text
   - Do NOT check the checkbox
   - Do NOT move the item

6. **Update backlog.md statistics**: Recalculate the counts in the overview table

### Phase 3: Sync Completed Issues

For each **Archived** item (`- [ ]` with `📋` but without `✅`):

1. Extract the backlog ID from the `📋` marker (e.g., `[RF-007]`)
2. Look up this ID in backlog.md
3. If the ID's status is `✅ 已完成`:
   a. Change `- [ ]` to `- [x]` in TODO.md
   b. Append completion timestamp after the archive marker:
      ```
      - [x] original text 📋 2026-04-21 归档为 [RF-007] ✅ 2026-04-22 该issue已确认完成
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
   - Include the backlog ID if available
3. Do NOT remove or modify the verbose subsection

### Phase 5: Update Metadata

1. Update `docs/backlog.md`:
   - Set `最后更新` to today's date
   - Recalculate all counts in the statistics overview table
2. Verify consistency: every `📋` ID in TODO.md should exist in backlog.md

## Formatting Rules

### Archive Timestamp Format
```
📋 YYYY-MM-DD 归档为 [CATEGORY-NNN]
```
Example: `📋 2026-04-21 归档为 [RF-007]`

### Completion Timestamp Format
```
✅ YYYY-MM-DD 该issue已确认完成
```
Example: `✅ 2026-04-22 该issue已确认完成`

### Full Item Lifecycle Example
```
New:        - [ ] 优化"新用户"链路的性能
Archived:   - [ ] 优化"新用户"链路的性能 📋 2026-04-21 归档为 [OPT-001]
Completed:  - [x] 优化"新用户"链路的性能 📋 2026-04-21 归档为 [OPT-001] ✅ 2026-04-25 该issue已确认完成
```

## Safety Rules

1. **NEVER modify the human's original text** — only append timestamps and change checkbox state
2. **NEVER delete items from TODO.md** — only move them between sections
3. **NEVER create duplicate IDs** — always check existing IDs in backlog.md first
4. **NEVER mark an issue as completed in TODO.md unless it is confirmed completed in backlog.md**
5. **When in doubt about classification, use INV (Investigation)** — it can always be reclassified later
6. **Preserve all existing content** — if a date section already has a summary, only add new items to it, don't rewrite existing summaries

## Backlog.md Writing Convention

When adding a new issue to backlog.md, follow the existing table format:

### For Bug/Optimization/Investigation:
```markdown
| ID | 描述 | 来源 | 状态 | 备注 |
|----|------|------|------|------|
| BUG-017 | description | [TODO.md](../TODO.md) | 📋 待处理 | key details |
```

### For Feature/Refactor:
```markdown
| ID | 描述 | 来源 | 状态 | 规模 | 备注 |
|----|------|------|------|------|------|
| RF-007 | description | [TODO.md](../TODO.md) | 📋 待处理 | 中 | key details |
```
