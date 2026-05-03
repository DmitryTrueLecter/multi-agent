# Shared claude-multi-agent-jira recipes — imported by each project's Justfile.
#
# Usage in the project's root Justfile:
#
#     project := file_name(justfile_directory())
#     session := "claude-" + project
#
#     import '.claude/Justfile'
#
# The import resolves through the conventional symlink
#     .claude/Justfile -> .claude-multi-agent-jira/Justfile
# created alongside the existing .claude/agents, .claude/commands, etc.
#
# Expected variables in the importing Justfile:
#   project — last segment of the project directory; used as the Claude
#             Remote Control session label visible at claude.ai/code.
#   session — tmux session name (typically "claude-" + project).

# Auto-resume claude after rate-limit reset (logs: /tmp/claude-resume-<session>.log)
claude-resume:
    @pgrep -f "claude-resume.sh {{session}}" > /dev/null && echo "already running" || (nohup bash .claude/scripts/claude-resume.sh {{session}}:0 > /tmp/claude-resume-{{session}}.log 2>&1 & disown ; echo started)

# Stop claude auto-resume (only this project's watchdog)
claude-resume-stop:
    @pkill -f "claude-resume.sh {{session}}" && echo stopped || echo "not running"

# Start claude in a per-project tmux session + auto-resume watchdog, then attach
claude-start:
    @tmux has-session -t {{session}} 2>/dev/null || tmux new-session -d -s {{session}} 'claude --agent team-lead --rc "{{project}}"'
    @just claude-resume
    @tmux attach -t {{session}}

# Start claude detached + watchdog and print the remote-control chat URL
claude-start-detached:
    #!/usr/bin/env bash
    set -e
    if tmux has-session -t {{session}} 2>/dev/null; then
        echo "session {{session}} already running"
    else
        tmux new-session -d -s {{session}} 'claude --agent team-lead --rc "{{project}}"'
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
