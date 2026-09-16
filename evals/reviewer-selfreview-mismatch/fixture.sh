#!/usr/bin/env bash
# Seeds the empty eval workspace (cwd) with the shipments project after dev's second attempt, on its task branch.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -R "$here/fixture/." .
git init -q . && git checkout -q -b ai/PROJ-301 && git add -A && git -c user.email=eval@example.com -c user.name=eval commit -qm "PROJ-301 second attempt"
