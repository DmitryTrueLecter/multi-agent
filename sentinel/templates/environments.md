# Environments

Single source of truth for environment topology, service endpoints, deploy mechanics, and access constraints. Read by `agents/devops.md` on every spawn. Update whenever an environment changes.

**Never paste real secrets in this file.** Use placeholders (`<DB_PASSWORD>`) and reference where the human reads the actual value (vault, CI secret store, password manager).

## Local

- **Status:** <fill in — e.g. used daily, available on this machine only, intermittent>
- **Runtime:** <e.g. docker compose, native Python venv, ...>
- **Services:** <list each with port — e.g. backend `:8000`, frontend `:5173`, postgres `:5432`>
- **Database:** <how to reach, credentials reference>
- **Build / start:** <command, e.g. `just up`>
- **Logs:** <where they go — stdout, log file, ...>
- **Common breakage modes:** <where local tends to fail>

## Staging

- **Status:** <fill in — does this environment exist for this project?>
- **Host:** <where it runs>
- **Services:** <list>
- **Deploy mechanic:** <how a change gets there — manual, CI workflow, manual push to registry, ...>
- **Logs:** <where to read them, retention>
- **Database:** <name + how to reach it; placeholders for secrets>
- **Access:** <how a human reaches it — SSH path, jump host, kubeconfig name, web console URL>
- **Common breakage modes:** <fill in>

## Production

- **Status:** <fill in>
- **Host:** <where it runs>
- **Services:** <list>
- **Deploy mechanic:** <step-by-step at high level — what the human does to ship>
- **Logs:** <where to read; retention policy>
- **Database:** <name + access path; placeholders only>
- **Access:** <SSH path, MFA, jump host>
- **Backup policy:** <fill in>
- **Rollback:** <how to roll a deploy back, time-to-rollback>
- **Common breakage modes:** <fill in>
- **IRREVERSIBLE actions:** <list any operation that cannot be undone — destructive migrations, data deletions, DNS cuts>

---

## Update log

- <YYYY-MM-DD> — <one-line summary of what changed in the environment>
