#!/usr/bin/env python3
"""PreToolUse hook for Bash.

Blocks shell operations that are irreversible, contradict the multi-agent
contract, or bypass project conventions:

  - force pushes (any branch)
  - direct push to main / master / development
  - deleting remote main / master / development
  - git reset --hard, git clean -f, git checkout ., git restore .
  - git push --mirror, git filter-branch / filter-repo, git stash clear
  - deleting protected branches
  - rm -rf at root or HOME
  - hand-creating files under migrations/alembic/versions/
  - curl / wget piped into a shell, bash -c "$(curl ...)" obfuscated form
  - docker run --privileged, host-root volume mount, prune --volumes
  - psql DROP DATABASE / SCHEMA / ROLE / USER
  - alembic downgrade base

Note: shell-escaped commands the user types (`! some-cmd`) do not go through
the Bash tool and are not affected by this hook.

Exit codes:
  0 - allow
  2 - block (stderr is shown to the model)
"""

from __future__ import annotations

import json
import re
import sys

# Each entry: (compiled regex, human-readable reason).
# Patterns are intentionally narrow — we'd rather miss a rare form than
# false-positive on common dev operations.
DENY = [
    (
        re.compile(r"\bgit\s+push\b[^|;&]*\s(?:--force(?:-with-lease)?|-f)\b"),
        "git push --force* is blocked. Resolve the divergence properly.",
    ),
    (
        re.compile(
            r"\bgit\s+push\s+(?:-[\w-]+(?:=\S+)?\s+)*(?:\S+\s+)?(?:HEAD:)?(?:main|master|development)(?:\s|$|;|&|\|)"
        ),
        "Direct push to main / master / development is blocked. Push to a feature/epic branch and merge through the workflow.",
    ),
    (
        re.compile(r"\bgit\s+push\s+\S+\s+:(?:main|master|development)\b"),
        "Deleting the remote main / master / development branch is blocked.",
    ),
    (
        re.compile(r"\bgit\s+reset\s+--hard\b"),
        "git reset --hard is blocked — it discards uncommitted work. If this is genuinely needed, ask the user.",
    ),
    (
        re.compile(r"\bgit\s+branch\s+-[Dd]\s+(?:main|master|development)\b"),
        "Deleting main / master / development locally is blocked.",
    ),
    (
        re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*[fdx]"),
        "git clean -f* is blocked — it discards untracked files.",
    ),
    (
        re.compile(r"\bgit\s+checkout\s+(?:\.\s*|--\s)"),
        "git checkout . / -- is blocked — it discards uncommitted work.",
    ),
    (
        re.compile(r"\bgit\s+restore\s+(?:\.\s*|--source=)"),
        "git restore . / --source= is blocked — it discards uncommitted work.",
    ),
    (
        re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?[a-zA-Z]*\s+/(?:\s|$|;|&|\|)"),
        "rm -rf / is blocked.",
    ),
    (
        re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?[a-zA-Z]*\s+~/?(?:\s|$|;|&|\|)"),
        "rm -rf ~ is blocked.",
    ),
    (
        re.compile(r"(?:echo|cat|tee|touch|cp|mv|printf)\s+[^|;&]*\bmigrations/alembic/versions/"),
        'Creating files in migrations/alembic/versions/ by hand is blocked. Use: cd migrations && alembic revision --autogenerate -m "..."',
    ),
    (
        re.compile(r">\s*[^|;&]*\bmigrations/alembic/versions/"),
        'Writing into migrations/alembic/versions/ via redirection is blocked. Use: cd migrations && alembic revision --autogenerate -m "..."',
    ),
    (
        re.compile(r"\b(?:curl|wget)\b[^|;&]*\|\s*(?:sudo\s+)?(?:bash|sh|zsh|fish)\b"),
        "curl/wget piped into a shell is blocked — running arbitrary code from a URL. Download to a file, inspect, then run.",
    ),
    (
        re.compile(r"\b(?:bash|sh|zsh|fish)\s+-c\s+[\"']?\$\(\s*(?:curl|wget)\b"),
        'shell -c "$(curl ...)" is blocked — running arbitrary code from a URL.',
    ),
    (
        re.compile(r"\bdocker\s+run\b[^|;&]*\s--privileged\b"),
        "docker run --privileged is blocked — escapes container isolation.",
    ),
    (
        re.compile(r"\bdocker\s+run\b[^|;&]*\s(?:-v\s+|--volume(?:=|\s+))/[:\s]"),
        "docker run with host-root volume mount (-v /:...) is blocked.",
    ),
    (
        re.compile(r"\bdocker\s+(?:system\s+prune\b[^|;&]*--volumes|volume\s+prune)\b"),
        "docker volume / system prune --volumes is blocked — destroys named volumes irreversibly.",
    ),
    (
        re.compile(r"\bgit\s+filter-(?:branch|repo)\b"),
        "git filter-branch / filter-repo is blocked — rewrites history. If genuinely needed, ask the user.",
    ),
    (
        re.compile(r"\bgit\s+stash\s+clear\b"),
        "git stash clear is blocked — drops every stash silently. Use 'git stash drop <id>' for a single entry.",
    ),
    (
        re.compile(r"\bgit\s+push\b[^|;&]*\s--mirror\b"),
        "git push --mirror is blocked — overwrites all remote refs.",
    ),
    (
        re.compile(r"\bpsql\b[^|;&]*\bDROP\s+(?:DATABASE|SCHEMA|ROLE|USER)\b", re.IGNORECASE),
        "psql DROP DATABASE / SCHEMA / ROLE / USER is blocked. If genuinely needed, do it explicitly with the user.",
    ),
    (
        re.compile(r"\balembic\b[^|;&]*\bdowngrade\s+base\b"),
        "alembic downgrade base is blocked — wipes the entire migration history.",
    ),
    (
        re.compile(r"\b(?:cat|head|tail|less|more|bat|grep)\b[^|;&]*(?<!\w)\.env(?:\.[\w-]+)?(?!\w)"),
        "Reading .env files via shell is blocked — same policy as Read(**/.env). Ask the user if you need a specific value.",
    ),
    (
        re.compile(r"\b(?:ls|cat|head|tail|less|more|bat|grep)\b[^|;&]*[/~]\.ssh(?:\b|/)"),
        "Reading ~/.ssh contents via shell is blocked — exposes SSH key material.",
    ),
    (
        re.compile(r"\b(?:ls|cat|head|tail|less|more|bat|grep)\b[^|;&]*\s/etc/(?:shadow|gshadow|sudoers)(?:\.d)?\b"),
        "Reading /etc/shadow / gshadow / sudoers is blocked.",
    ),
    (
        re.compile(r"\bfind\s+/(?:\s|$|;|&|\||\*)"),
        "find / starts a full filesystem scan that can saturate CPU/IO on large trees. To locate a binary use `command -v <name>` or `which <name>`. To search files, use `find .` or a specific path (e.g. `find /usr/local/bin`, `find /home/<user>/<project>`).",
    ),
    (
        re.compile(r"\bsource\s+\S*activate\b\s*&&"),
        "`source <venv>/bin/activate && <cmd>` is blocked. In a non-interactive Bash tool call, call the venv's binary directly: `<venv>/bin/python -m pytest ...` or `<venv>/bin/<tool> ...`. Equivalent behavior, no need to whitelist the broad `source` builtin.",
    ),
    (
        re.compile(r"\b(?:ba)?sh\s+(?:-l\s*-c|-lc|-cl)\b"),
        "`bash -lc '...'` / `sh -lc '...'` wrappers are blocked. A Bash tool call is already a fresh shell — the login wrapper just adds nondeterministic `.bash_profile` / `.bashrc` sourcing without benefit. Run the command directly. If a tool needs a specific runtime, call its binary by absolute path (e.g. `<venv>/bin/python`, `<project>/node_modules/.bin/<tool>`) and pass env vars as a single-segment prefix.",
    ),
]


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    cmd = (payload.get("tool_input") or {}).get("command") or ""
    for pattern, reason in DENY:
        if pattern.search(cmd):
            print(f"bash_safety: {reason}\nCommand: {cmd}", file=sys.stderr)
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
