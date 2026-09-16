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
MARK = re.compile(r"__CHARTER:([a-z,-]+)__")


def _resolve(body: str) -> str:
    return body.replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT)).replace("${CLAUDE_PROJECT_DIR}", "<project-root>")


def charter(spec: str) -> str:
    """`<agent>[,<skill>,...]`: the agent's system prompt body plus the body of each named skill (the ones its Bootstrap invokes)."""
    agent, *skills = spec.split(",")
    text = (ROOT / "agents" / f"{agent}.md").read_text()
    parts = [re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S).strip()]
    for name in skills:
        skill = (ROOT / "skills" / name / "SKILL.md").read_text()
        parts.append("\n\n<skill name=\"dma:" + name + "\" note=\"invoked at Bootstrap step 0\">\n" + re.sub(r"\A---\n.*?\n---\n", "", skill, flags=re.S).strip() + "\n</skill>")
    resolved = _resolve("".join(parts))
    return "\n".join(("  " + line) if line else "" for line in resolved.splitlines())


for template in sorted((ROOT / "evals").glob("*/prompt.template.md")):
    src = template.read_text()
    m = MARK.search(src)
    if not m:
        raise SystemExit(f"{template}: no __CHARTER:<agent>__ marker")
    template.with_name("prompt.md").write_text(src.replace(m.group(0), charter(m.group(1))))
    print("wrote", template.with_name("prompt.md").relative_to(ROOT), f"(charter: {m.group(1)})")
