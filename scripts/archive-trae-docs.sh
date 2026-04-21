#!/usr/bin/env bash
# Archive .trae documents to docs/archive/.trae-docs/
# Usage: bash scripts/archive-trae-docs.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TRAE_DOCS="$PROJECT_ROOT/.trae/documents"
ARCHIVE_DIR="$PROJECT_ROOT/docs/archive/.trae-docs"
ARCHIVE_LOG="$PROJECT_ROOT/docs/archive/archive-log.md"

mkdir -p "$ARCHIVE_DIR"

DATE=$(date +%Y-%m-%d)
COUNT=0

echo "Archiving .trae/documents to $ARCHIVE_DIR ..."

for f in "$TRAE_DOCS"/*.md; do
    [ -e "$f" ] || continue
    BASENAME=$(basename "$f")
    
    if [ "$BASENAME" = "plan-fix-independent-issues.md" ]; then
        echo "  SKIP: $BASENAME (active plan)"
        continue
    fi
    
    if [ -f "$ARCHIVE_DIR/$BASENAME" ]; then
        echo "  SKIP: $BASENAME (already archived)"
        continue
    fi
    
    cp "$f" "$ARCHIVE_DIR/$BASENAME"
    echo "  ARCHIVED: $BASENAME"
    COUNT=$((COUNT + 1))
done

echo ""
echo "Done. Archived $COUNT files."
echo ""

if [ $COUNT -gt 0 ]; then
    echo "## $DATE — Archive $COUNT files" >> "$ARCHIVE_LOG"
    for f in "$TRAE_DOCS"/*.md; do
        [ -e "$f" ] || continue
        BASENAME=$(basename "$f")
        if [ "$BASENAME" = "plan-fix-independent-issues.md" ]; then
            continue
        fi
        if [ ! -f "$ARCHIVE_DIR/$BASENAME" ]; then
            continue
        fi
        echo "- $BASENAME" >> "$ARCHIVE_LOG"
    done
    echo "" >> "$ARCHIVE_LOG"
    echo "Archive log updated: $ARCHIVE_LOG"
fi
