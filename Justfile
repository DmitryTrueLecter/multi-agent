# Shared dma-plugin recipes — imported by each project's root Justfile.
#
# Usage in the project's root Justfile:
#
#     import '.claude/dma/Justfile'
#
# This file lives at `.claude/dma/Justfile` in the project (installed from the dma
# plugin, not a symlink). The launch recipes start Claude with the namespaced
# plugin agent, e.g. `claude --agent dma:team-lead`, so the dma plugin must be
# enabled in that session (marketplace/skills-dir install, or `--plugin-dir`).
#
# Variables `project` and `session` are defined here so that imported
# recipes work on every just version, including ones where `import`
# does not share variable scope with the importing file. They derive
# from `justfile_directory()`, which always points at the *root*
# Justfile (the one the user invoked), so the values are correct
# regardless of which project imports this file.

# Last segment of the project directory; used as the Claude Remote
# Control session label visible at claude.ai/code.
project := file_name(justfile_directory())
# tmux session name (per-project, no collisions across checkouts).
session := "claude-" + project

# Auto-resume claude after rate-limit reset (logs: /tmp/claude-resume-<session>.log)
claude-resume:
    @pgrep -f "claude-resume.sh {{session}}" > /dev/null && echo "already running" || (cd "{{justfile_directory()}}" && nohup bash .claude/dma/scripts/claude-resume.sh {{session}}:0 > /tmp/claude-resume-{{session}}.log 2>&1 & disown ; echo started)

# Stop claude auto-resume (only this project's watchdog)
claude-resume-stop:
    @pkill -f "claude-resume.sh {{session}}" && echo stopped || echo "not running"

# Start claude in a per-project tmux session + auto-resume watchdog, then attach
claude-start:
    @tmux has-session -t {{session}} 2>/dev/null || tmux new-session -d -s {{session}} -c "{{justfile_directory()}}" 'claude --agent dma:team-lead --permission-mode bypassPermissions --rc "{{project}}"'
    @just claude-resume
    @tmux attach -t {{session}}

# Attach to the existing per-project claude tmux session (does not create one)
claude-attach:
    @tmux has-session -t {{session}} 2>/dev/null || (echo "session {{session}} not running — start it with: just claude-start | just claude-start-detached" >&2 ; exit 1)
    @tmux attach -t {{session}}

# Stop this project's claude session: kill the tmux session and the resume watchdog
claude-stop:
    @just claude-resume-stop >/dev/null 2>&1 || true
    @tmux has-session -t {{session}} 2>/dev/null && (tmux kill-session -t {{session}} && echo "killed tmux session {{session}}") || echo "session {{session}} not running"

# Start claude detached + watchdog and print the remote-control chat URL
claude-start-detached:
    #!/usr/bin/env bash
    set -e
    if tmux has-session -t {{session}} 2>/dev/null; then
        echo "session {{session}} already running"
    else
        tmux new-session -d -s {{session}} -c "{{justfile_directory()}}" 'claude --agent dma:team-lead --permission-mode bypassPermissions --rc "{{project}}"'
    fi
    just claude-resume >/dev/null
    for i in $(seq 1 30); do
        url=$(tmux capture-pane -p -S -1000 -t {{session}} | grep -oE 'https://claude\.ai/code/session_[A-Za-z0-9_-]+' | tail -1)
        if [ -n "$url" ]; then
            echo "session: {{session}}"
            echo "url:     $url"
            exit 0
        fi
        sleep 1
    done
    echo "URL not detected within 30s. Inspect with: tmux attach -t {{session}}" >&2
    exit 1

# Print the remote-control chat URL of this project's running session (most recent)
claude-url:
    #!/usr/bin/env bash
    url=$(tmux capture-pane -p -S -1000 -t {{session}} 2>/dev/null | grep -oE 'https://claude\.ai/code/session_[A-Za-z0-9_-]+' | tail -1)
    if [ -n "$url" ]; then
        echo "$url"
    else
        echo "session {{session}} not found or URL not in scrollback" >&2
        exit 1
    fi

# Launch the sentinel meta-agent in the foreground
sentinel:
    claude --agent dma:sentinel --permission-mode bypassPermissions
