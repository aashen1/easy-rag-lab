---
name: "archive-conventions"
description: "Defines conventions for archiving docs to docs/archive/. Invoke when user asks to archive documents, move completed plans/specs/reports to archive, or says '归档'."
---

# Archive Conventions

This skill defines the directory structure, naming rules, and workflow for archiving documents to `docs/archive/`.

## Directory Structure

```
docs/archive/
├── archive-log.md              # Archive operation log (append-only)
├── idea-ai-era-git-practice.md # Standalone essay (root level)
│
├── plans/                      # All plan documents
│   ├── v0.1.8/                 # Version-specific plans
│   ├── v0.1.9/
│   └── documents-refactor/     # Topic-specific plan groups
│
├── reports/                    # All report documents
│
├── specs/                      # All spec triplets (spec.md/checklist.md/tasks.md)
│   └── v0.1.9/                 # Version-specific specs
│
├── flagembedding-to-transformers/  # Standalone topic directories
├── meal/
└── test-suite-analysis/
```

## Classification Rules

### plans/
Any document that describes **intended work** or **how to do something**:
- Feature plans, bug fix plans, refactoring plans
- Release plans, merge plans
- Optimization plans, integration plans
- Research plans with action items

### reports/
Any document that **analyzes** or **investigates** without prescribing action:
- Deep inspection reports, analysis reports
- Merge conflict analyses, project status analyses
- Research documents without action items

### specs/
Any spec triplet directory containing `spec.md` + `checklist.md` + `tasks.md`:
- Keep the triplet together as a subdirectory
- Named by feature/issue (e.g., `fix-baseline-evaluation-issues/`)

### Standalone topic directories
Coherent topic groups that don't fit plans/reports/specs:
- Must be self-contained (all related files in one directory)
- Examples: `meal/`, `test-suite-analysis/`, `flagembedding-to-transformers/`

## Version Grouping

When archiving documents tied to a specific version:
- Plans → `plans/vX.Y.Z/`
- Specs → `specs/vX.Y.Z/`
- Reports stay in `reports/` (no version subdirectory needed)

## Naming Rules

1. **English only** — no Chinese characters in filenames
2. **Lowercase with hyphens** — no underscores, no spaces, no CamelCase
   - ✅ `ragas-integration-plan.md`
   - ❌ `ragas_integration_plan.md`
   - ❌ `Ragas_Integration_Plan.md`
3. **Spec triplet files** — always `spec.md`, `checklist.md`, `tasks.md` (no prefix)
4. **Descriptive names** — `<topic>-<type>.md` pattern for standalone files
   - `fix-evaluation-bugs.md` (not just `fix.md`)
   - `v0.1.8-merge-and-release-plan.md` (version prefix for version-specific docs)

## Archive Workflow

1. **Classify** the document: plan → `plans/`, report → `reports/`, spec → `specs/`
2. **Check version**: if tied to a specific version, place in version subdirectory
3. **Rename** if needed: Chinese → English, underscores → hyphens, spaces → hyphens
4. **Move** the file to the correct location
5. **Check for duplicates**: if the same content already exists in archive, move duplicate to `.trashbin/`
6. **Log** the operation in `archive-log.md`
7. **Commit** with message: `chore: archive <description>`

## archive-log.md Format

Append a new section with date:

```markdown
## YYYY-MM-DD — <Brief description>

### Plans (docs/archive/plans/)
- filename.md (brief description)

### Reports (docs/archive/reports/)
- filename.md (brief description)

### Specs (docs/archive/specs/)
- directory-name/ (brief description)

### Renamed
| Old name | New name |
|----------|----------|
| old-name.md | new-name.md |
```

## Anti-Patterns (DO NOT)

1. **DO NOT** create new top-level directories under `docs/archive/` unless it's a standalone topic group
2. **DO NOT** use source-based directory names like `trae-documents/`, `trae-plans/`, `trae-specs/` — classify by content type, not by origin
3. **DO NOT** archive duplicate files — check for existing copies first
4. **DO NOT** use Chinese filenames — always rename to English before archiving
5. **DO NOT** use underscore or space in filenames — always use hyphens
6. **DO NOT** nest spec directories inside plans/ or reports/ — specs always go to specs/
7. **DO NOT** forget to update archive-log.md after every archive operation
