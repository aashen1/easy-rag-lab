---
alwaysApply: true
scene: file_operations
---

# 🛑 Trashbin Rule — Safe File Deletion

## ⚠️ STOP — Before ANY Deletion

**About to call `DeleteFile`, `rm`, `del`, `Remove-Item`? → STOP NOW.**
Move to `.trashbin/` instead. NO exceptions.

### Self-Check

1. Am I deleting/removing/cleaning up a file or directory? → **trashbin move**
2. Am I calling `DeleteFile` tool? → **STOP, trashbin move**
3. Am I writing `rm`/`del`/`Remove-Item` in a command? → **STOP, trashbin move**

If ANY match → DO NOT delete. Use trashbin procedure below.

## Core Rule

**NEVER permanently delete files.** Move to `.trashbin/` instead.

## Triggers

When you think: "删除/delete/remove/clean up/清理/移除" any file → **STOP, use trashbin.**

Applies to ALL files (temp, cache, "doesn't matter") in ALL modes. **No exceptions. Ever.**

## How

```bash
mkdir -p .trashbin && mv <target> .trashbin/<target>_$(date +%Y%m%d_%H%M%S)
```
