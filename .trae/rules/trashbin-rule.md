---
alwaysApply: true
scene: file_operations
---

# Trashbin Rule — Safe File Deletion

## Core Rule

**NEVER permanently delete files using `DeleteFile`, `rm`, `del`, or any other tool.**  
Instead, **move** files/directories to the project's trashbin folder:

```
<current-folder>\.trashbin\
```

## When to Apply

- Any time you would delete a file or directory (code, config, data, cache, etc.)
- This includes files removed during refactoring, cache invalidation, or cleanup
- Applies in ALL working modes (Agent / Plan / Spec)

## How to Move to Trashbin

1. Create a timestamped subdirectory under `.trashbin/` to avoid name collisions:
   ```
   .trashbin/<original_name>_<YYYYMMDD_HHMMSS>/
   ```
2. Move the entire file or directory there using `shutil.move()` or equivalent
3. Log the move action so the user can review later

## Examples

```python
# Python (preferred in code)
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
# Bash fallback (when Python not available)
mkdir -p .trashbin && mv target_file .trashbin/target_file_$(date +%Y%m%d_%H%M%S)
```

## Exceptions

- There is no exceptions. ALWAYS move to `.trashbin` when you need to delete something.

## Rationale

IDE delete confirmations interrupt development flow. The trashbin lets AI work at full speed while keeping deleted items recoverable. The user can periodically clean `.trashbin/` at their convenience.
