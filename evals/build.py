#!/usr/bin/env python3
"""Render each case's prompt.md from prompt.template.md, inlining an agent charter.

The eval child session has no agent system prompt, so a template carries the marker
`__CHARTER:<agent>__` and this script appends the body of agents/<agent>.md (minus
frontmatter) via `append_system_prompt`. Placeholders are resolved for the sandbox:
${CLAUDE_PLUGIN_ROOT} -> this plugin's absolute path; ${CLAUDE_PROJECT_DIR} ->
`<project-root>` (the prompt tells the agent how to find it). Re-run after editing a charter.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
MARK = re.compile(r"__CHARTER:([a-z-]+)__")


def charter(agent: str) -> str:
    text = (ROOT / "agents" / f"{agent}.md").read_text()
    body = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S).strip()
    body = body.replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT)).replace("${CLAUDE_PROJECT_DIR}", "<project-root>")
    return "\n".join(("  " + line) if line else "" for line in body.splitlines())


for template in sorted((ROOT / "evals").glob("*/prompt.template.md")):
    src = template.read_text()
    m = MARK.search(src)
    if not m:
        raise SystemExit(f"{template}: no __CHARTER:<agent>__ marker")
    template.with_name("prompt.md").write_text(src.replace(m.group(0), charter(m.group(1))))
    print("wrote", template.with_name("prompt.md").relative_to(ROOT), f"(charter: {m.group(1)})")
