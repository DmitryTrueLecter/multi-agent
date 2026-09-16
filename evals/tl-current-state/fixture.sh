#!/usr/bin/env bash
# Seeds the empty eval workspace (cwd) with the fictional "members" project.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -R "$here/fixture/." .
git init -q . && git add -A && git -c user.email=eval@example.com -c user.name=eval commit -qm "fixture"
