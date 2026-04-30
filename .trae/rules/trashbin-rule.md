---
alwaysApply: true
scene: file_operations
---

# 🛑 Trashbin Rule — Safe File Deletion

## ⚠️ STOP — Read This BEFORE Any Deletion

**If you are about to call `DeleteFile`, `rm`, `del`, `Remove-Item`, or ANY deletion tool → STOP NOW.**

You MUST move the file to `.trashbin/` instead. There are NO exceptions.

### Self-Check Before Deletion

Before performing ANY file removal, ask yourself:

1. Am I about to delete, remove, or clean up a file or directory? → **Use trashbin move**
2. Am I calling `DeleteFile` tool? → **STOP, use trashbin move**
3. Am I writing `rm`, `del`, `Remove-Item` in a command? → **STOP, use trashbin move**
4. Am I "cleaning up" or "removing" something? → **Use trashbin move**

**If any of these match → DO NOT proceed with deletion. Use the trashbin procedure below.**

---

## Core Rule

**NEVER permanently delete files using `DeleteFile`, `rm`, `del`, `Remove-Item`, or any other tool.**
Instead, **move** files/directories to the project's trashbin folder:

```
<current-folder>\.trashbin\
```

## Trigger Conditions

When you think ANY of these thoughts, the trashbin rule activates:

- "删除这个文件" / "delete this file"
- "remove this file/directory"
- "clean up this directory"
- "delete the cache/old files"
- "this file is no longer needed"
- "remove the old version"
- "清理/删除/移除" any file or directory

→ **STOP immediately and use trashbin move instead.**

## When to Apply

- Any time you would delete a file or directory (code, config, data, cache, etc.)
- This includes files removed during refactoring, cache invalidation, or cleanup
- Applies in ALL working modes (Agent / Plan / Spec)
- **No exceptions. Ever.**

## How to Move to Trashbin

1. Create a timestamped subdirectory under `.trashbin/` to avoid name collisions:
   ```
   .trashbin/<original_name>_<YYYYMMDD_HHMMSS>/
   ```
2. Move the entire file or directory there using `shutil.move()` or equivalent
3. Log the move action so the user can review later

## Examples

```python
import shutil
from datetime import datetime
from pathlib import Path

trashbin = Path("<current-folder>/.trashbin")
trashbin.mkdir(parents=True, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
dest = trashbin / f"{target.name}_{timestamp}"
shutil.move(str(target), str(dest))
```

```bash
# Git Bash on Windows
mkdir -p .trashbin && mv target_file .trashbin/target_file_$(date +%Y%m%d_%H%M%S)
```

```powershell
# PowerShell on Windows
New-Item -ItemType Directory -Force -Path .trashbin | Out-Null
Move-Item -Path "target_file" -Destination ".trashbin/target_file_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
```

## Exceptions

**There are NO exceptions. ALWAYS move to `.trashbin/` when you need to delete something.**

This includes:
- Temporary files → trashbin
- Cache files → trashbin
- Files you just created and want to undo → trashbin
- Files that "don't matter" → trashbin
- Files in `.trashbin/` itself → still trashbin (use a subdirectory)

## Rationale

IDE delete confirmations interrupt development flow. The trashbin lets AI work at full speed while keeping deleted items recoverable. The user can periodically clean `.trashbin/` at their convenience.
