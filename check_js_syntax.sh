#!/bin/bash
set -e
cd "$(dirname "$0")/.."
for f in openas2_manager/public/js/*.js; do
  echo "=== $f ==="
  node --check "$f" && echo OK || echo FAIL
done
