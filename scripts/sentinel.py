"""Flags: a defect in a prompt, a skill or a process step, filed for sentinel.

    dma sentinel flag <TYPE> "<problem>" --where <file:section> --reporter <role>
                      [--originating <KEY>] [--details <text> | -]

Files one Task in the tracker's Sentinel queue and puts it there — creation and
the move are one call, because a flag left in the project's default status is
invisible to the queue sentinel reads.

Runs alongside the caller's own task and never blocks it: a flag is a note about
the prompt, not a step of the work in hand.
"""

import sys

import issue

TYPES = {
    "PROMPT-UNCLEAR": "Instruction unfollowable without guessing.",
    "PROMPT-INCOMPLETE": "Workflow has no path for a case that actually occurred.",
    "PROMPT-CONTRADICTION": "Two instructions cannot both be true.",
    "PROMPT-FRAGMENTED": "Rule extended by appending; voices conflict.",
    "PROMPT-SCOPE-LEAK": "Agent instructed into another agent's territory.",
    "RULE-CONTRADICTION": "Rule vs its detection method, or two rules vs the same fragment.",
    "ARCH-ROLE-GAP": "No agent owns a needed responsibility.",
    "ARCH-ROLE-OVERLAP": "Two agents handle the same thing, no delegation declared.",
    "ENV-FRICTION": "Hook, credential or binary blocks a prescribed command, no fallback.",
    "PATTERN-REPEAT": "Same mistake across unrelated tasks; the prescribed steps produce it.",
}

FLAGS = ("--where", "--reporter", "--originating", "--details")


def usage():
    lines = [__doc__.strip(), "", "Types:"]
    lines += [f"  {name:22} {why}" for name, why in TYPES.items()]
    return "\n".join(lines)


def cmd_flag(tracker, config, argv):
    if len(argv) < 2:
        issue.die(usage())
    flag_type, problem, options, rest = argv[0].upper(), argv[1], {}, argv[2:]
    while rest:
        if rest[0] not in FLAGS or len(rest) < 2:
            issue.die(usage())
        options[rest[0][2:]] = rest[1]
        rest = rest[2:]

    if flag_type not in TYPES:
        issue.die(f"unknown flag type '{flag_type}'\n\n" + usage())
    if not options.get("where"):
        issue.die("--where is required: the prompt location of the defect, "
                  "e.g. --where 'agents/dev.md / ## Task workflow step 2'")
    reporter = options.get("reporter") or "-"

    description = [f"**Where:** {options['where']}", f"**Reporter:** {reporter}"]
    if options.get("originating"):
        description.append(f"**Originating:** {options['originating']}")
    if options.get("details"):
        description.append(f"**Details:** {issue.read_body(options['details'])}")

    labels = ["sentinel-flag", f"flag-type:{flag_type.lower()}", "agent:sentinel"]
    key = tracker.create("task", f"[{flag_type}] {problem}", "\n\n".join(description),
                         labels, None, "sentinel_inbox")
    print(f"FLAGGED {key}")
    print(f"type: {flag_type}")
    print(f"where: {options['where']}")


def main(argv):
    if not argv or argv[0] != "flag":
        print(usage(), file=sys.stderr)
        return 1

    import tracker as tracker_module

    config = issue.load_config()
    if "sentinel_inbox" not in config["tasks"]["workflow"]["statuses"]:
        issue.die("tasks.workflow.statuses.sentinel_inbox is not configured — "
                  "the flag would land in a queue nobody reads")
    try:
        tracker = tracker_module.open_tracker(config)
        cmd_flag(tracker, config, argv[1:])
    except tracker_module.Unsupported as e:
        issue.die(str(e), 2)
    except tracker_module.TrackerError as e:
        issue.die(str(e))
    return 0
