#!/usr/bin/env bash
# Prepare Phase 2 shared runtime lib (copy jars; never modify Downloads sources).
set -euo pipefail
SRC="/mnt/c/Users/laksh/Downloads/OpenAS20/lib"
DEST="/mnt/c/OpenAS2/runtime/lib"
mkdir -p "$DEST"
cp -n "$SRC"/*.jar "$DEST/" 2>/dev/null || cp "$SRC"/*.jar "$DEST/"
ls "$DEST"/openas2-server-*.jar
echo "Prepared $DEST (source $SRC untouched)"
