#!/usr/bin/env bash
# claude-resume.sh — auto-resume a Claude Code session after a rate-limit reset.
#
# Watches a tmux pane that runs `claude`. When it sees a rate-limit banner
# ("You're out of extra usage · resets HH:MM<am|pm> (TZ)"), it parses the
# reset moment, sleeps until then, and types a nudge into the pane via
# `tmux send-keys` — which is the only thing that unsticks the local session
# (web/mobile remote-control does not).
#
# Requires: tmux, GNU/BSD date. Tested on macOS (BSD date).
#
# Usage:
#   .claude/dma/scripts/claude-resume.sh                       # default target claude:0
#   .claude/dma/scripts/claude-resume.sh my-session:0          # positional target
#   TARGET=work:1 .claude/dma/scripts/claude-resume.sh         # env-var target
#
# Passing the target as a positional argument is preferred when running
# multiple watchdogs side-by-side — argv shows up in `pgrep -f` / `pkill -f`,
# so per-project filtering works. Env vars do not.
#
# Run via `just claude-resume` or directly.

set -u

TARGET="${1:-${TARGET:-claude:0}}"
NUDGE="${NUDGE:-continue}"
POLL_INTERVAL="${POLL_INTERVAL:-60}"   # seconds between pane reads
COOLDOWN="${COOLDOWN:-900}"            # seconds to skip after a successful nudge
EXTRA_DELAY="${EXTRA_DELAY:-60}"       # seconds added to reset time as safety

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; }

parse_reset_epoch() {
    # $1 = "11:10am", $2 = "UTC"
    local hhmm="$1" tz="$2" epoch
    if date --version >/dev/null 2>&1; then
        # GNU date (Linux)
        epoch=$(TZ="$tz" date -d "$hhmm" +%s 2>/dev/null) || return 1
    else
        # BSD date (macOS)
        epoch=$(TZ="$tz" date -j -f "%I:%M%p" "$hhmm" +%s 2>/dev/null) || return 1
    fi
    printf '%s' "$epoch"
}

if ! command -v tmux >/dev/null 2>&1; then
    log "tmux not found in PATH"
    exit 1
fi

log "watchdog started, target=$TARGET nudge=$NUDGE"

while true; do
    if ! pane=$(tmux capture-pane -p -t "$TARGET" 2>/dev/null); then
        log "cannot capture pane $TARGET (not running yet?)"
        sleep "$POLL_INTERVAL"
        continue
    fi

    line=$(printf '%s\n' "$pane" | grep -oE 'resets [0-9]{1,2}:[0-9]{2}(am|pm)? \([A-Z]+\)' | tail -1)
    if [ -z "$line" ]; then
        sleep "$POLL_INTERVAL"
        continue
    fi

    hhmm=$(printf '%s' "$line" | awk '{print $2}')
    tz=$(printf '%s' "$line" | sed -E 's/.*\(([A-Z]+)\).*/\1/')

    if ! target_epoch=$(parse_reset_epoch "$hhmm" "$tz"); then
        log "failed to parse reset time: $line"
        sleep "$POLL_INTERVAL"
        continue
    fi

    now=$(date +%s)
    wait=$(( target_epoch - now + EXTRA_DELAY ))
    if [ "$wait" -lt 0 ]; then
        wait=$(( wait + 86400 ))   # reset time already passed today → wait until tomorrow
    fi

    log "rate-limit detected: reset at $hhmm $tz, sleeping ${wait}s"
    sleep "$wait"

    log "nudging pane $TARGET with: $NUDGE"
    tmux send-keys -t "$TARGET" "$NUDGE" Enter

    sleep "$COOLDOWN"
done
