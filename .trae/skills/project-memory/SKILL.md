---
name: "project-memory"
description: "Project memory system guide. Invoke when a new session starts, when you need to understand project state, or when writing work results into project memory."
---

# Project Memory — Cross-Session Project Memory System

This skill teaches AI sessions how to correctly use the project's documentation system as a **project-specific memory system**, enabling cross-session continuity for stateless AI agents.

## Core Concepts

1. **Documentation = Project Memory**
   - The docs system serves dual purposes: human-readable documentation AND AI-readable project state
   - It is the project's "evolution rings" (年轮) — every session's work is deposited here
   - Without reading docs first, a new session is completely blind to project history

2. **Sessions are Stateless**
   - Every AI session starts from zero — no memory of previous conversations
   - The ONLY continuity mechanism is the documentation system
   - What you don't write down is lost forever

3. **Read-Write Separation**
   - **Read memory** to understand current state before acting
   - **Write memory** to preserve your work for future sessions
   - Both operations are equally important — skipping either breaks the chain

4. **Docs are Intent Source Code**
   - "文档是意图源码，代码是编译产物" — documentation captures WHY, code captures HOW
   - Design decisions must be documented, not just implemented
   - Future sessions need to understand intent, not just output

## Reading Memory: New Session Startup Checklist

When a new session starts, follow this ordered reading sequence:

### Tier 1: Essential (always read first)

| Order | File | Purpose |
|-------|------|---------|
| 1 | `CLAUDE.md` | Project identity, current version, dev conventions, active rules |
| 2 | `docs/backlog.md` statistics table | Issue backlog health — pending/completed/deferred counts |
| 3 | `TODO.md` "My Backlog" section | Human's latest unstructured intent and notes |

### Tier 2: Contextual (read based on task)

| Order | File | Purpose |
|-------|------|---------|
| 4 | `docs/version-history.md` | Version evolution timeline — understand how we got here |
| 5 | `docs/inbox/` | Check for unprocessed incoming documents |
| 6 | `docs/reviews/vX.X.X/` | Latest version's acceptance report and known issues |

### Tier 3: Deep Dive (read when working on specific areas)

| Order | File | Purpose |
|-------|------|---------|
| 7 | `docs/guides/operations/<topic>.md` | Detailed feature documentation |
| 8 | `docs/guides/development/<topic>.md` | Development workflow guides |
| 9 | `docs/architecture.md` | System architecture overview |
| 10 | `docs/config-reference.md` | Configuration parameter reference |

### Reading Anti-Patterns

- ❌ Starting to code without reading CLAUDE.md first
- ❌ Reading only code and ignoring docs when investigating an issue
- ❌ Assuming you understand the project from the task description alone
- ❌ Skipping the backlog when planning work — you may duplicate or conflict with existing issues

## Writing Memory: Session Output Checklist

Before ending a session (or after completing a logical work unit), ensure:

### Code Changes

| Change Type | Memory Action |
|-------------|---------------|
| New feature | Create or update `docs/guides/operations/<feature>.md` |
| Bug fix (non-trivial) | Create `docs/troubleshooting/<bug-name>.md` |
| Config change | Update `docs/config-reference.md` |
| API change | Update `CHANGELOG.md` + relevant guide |
| Refactoring | Update affected architecture/guide docs |

### Issue Management

| Discovery Type | Memory Action |
|----------------|---------------|
| New bug/feature idea | Archive to `docs/backlog.md` (use `todo-archiver` skill) |
| Code review finding | Add to backlog with source reference |
| Deferred work | Mark in backlog with reason and conditions for resuming |

### Decision Documentation

| Decision Type | Memory Action |
|---------------|---------------|
| Architecture choice | Record in relevant guide: options considered, choice made, rationale |
| Technology selection | Record in guide: alternatives, trade-offs, why this one |
| Scope change | Update backlog + version direction doc |

### Progress Preservation

| Situation | Memory Action |
|-----------|---------------|
| Incomplete work | Leave progress note in TODO.md or backlog.md with current state |
| Blocked task | Document blocker in backlog + what's needed to unblock |
| Partial implementation | Document what's done, what's remaining, and any gotchas |

## Cross-Session Relay Principles

1. **Commit + Document atomically** — every logical work unit gets both a commit AND a doc update
2. **Never assume implicit understanding** — if a future session needs to know something, write it down
3. **Design decisions must be documented** — code comments are NOT sufficient for cross-session continuity
4. **Follow the "Evolution Ring" pattern** — each version creates its review docs in `docs/reviews/vX.X.X/`
5. **Keep docs honest** — if something is outdated, mark it `<!-- status: needs-update -->` rather than leaving stale info

## Anti-Patterns (Forbidden)

| Anti-Pattern | Why It's Harmful |
|-------------|-----------------|
| Not reading docs before coding | Repeats past mistakes, contradicts existing design |
| Changing code without updating docs | Future sessions can't understand your changes |
| Leaving stale info without marking it | Misleads future sessions into wrong assumptions |
| Assuming "the next AI will know why I did this" | They won't — sessions are stateless |
| Keeping important context only in conversation | Conversation dies when session ends |
| Creating docs without following naming conventions | Breaks the navigation system |
| Writing verbose docs when concise would suffice | Wastes future sessions' context budget |

## Relationship to Existing Mechanisms

```
┌─────────────────────────────────────────────────────────┐
│                   project-memory                         │
│            (This skill — the meta-guide)                 │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ todo-archiver │  │ auto-commit- │  │   inbox      │  │
│  │    skill      │  │  enforcer    │  │  mechanism   │  │
│  │              │  │    skill     │  │              │  │
│  │ Issue CRUD   │  │ Atomic       │  │ External     │  │
│  │ TODO↔backlog │  │ commits      │  │ info ingest  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │           Evolution Ring (年轮) System            │   │
│  │  version-history.md + reviews/vX.X.X/ + backlog  │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

- **todo-archiver skill**: Manages issue lifecycle (TODO → backlog → completion sync)
- **auto-commit-enforcer skill**: Ensures atomic commits that preserve history
- **inbox mechanism**: External information ingestion pipeline
- **Evolution Ring system**: Version-level documentation (reviews, outcomes, directions)

## When to Invoke This Skill

1. **New conversation starts** — read the startup checklist to orient yourself
2. **About to make significant changes** — re-read relevant docs to avoid conflicts
3. **Completing a work session** — run the output checklist to preserve your work
4. **Feeling uncertain about project state** — re-read Tier 1 docs for grounding
5. **User says "打扫卫生"** — this skill + todo-archiver work together
