**English** · [Русский](ru/skills.md)

# Skill catalog

A skill activates on its own when a request matches its description. Explicit call: in Claude Code — `/skill-name`,
in Codex — by naming the skill in the text ("use request-triage"). To disable the ones you don't need —
`skills.exclude` in the config; all team skills at once — `skills.team = false`.

## On-call and incidents

| Skill | When | Example prompt |
|---|---|---|
| `request-triage` | Work a request or alert through to the cause, the fix and a document in the knowledge base | `triage this alert https://chat.example.com/team/pl/abc123` |
| `observability-triage` | Latency, errors, saturation from metrics and logs | `why did gateway 5xx go up in prod since 14:00` |
| `kubernetes-runtime-triage` | Failing pods: restarts, probes, pending, node pressure, PVC | `registry-core pods are in CrashLoopBackOff, figure it out` |
| `service-network-triage` | DNS, TLS, ingress, API gateway, service unreachable | `registry.example.com doesn't open from inside the cluster, why` |
| `mattermost-alerts-digest` | Summary of alerts from a Mattermost channel over a window: repeats, flapping, long-running, noisy namespaces | `digest of the alert channel for last night` |
| `postmortem` | Review page in the wiki, incident tracker issue, action items | `write a postmortem for INC-7` |
| `duty-notes` | On-call wiki article for a resolved case | `document the case from this thread <link>` |

## Infrastructure

| Skill | When | Example prompt |
|---|---|---|
| `terraform-terragrunt-review` | Changes, plan, drift, provider and module upgrades | `OPS-1234 add a bucket for logs in prod, show the plan` |
| `helm-argocd-gitops` | Charts, values, Argo CD Application, diff and history | `why is argocd app payments OutOfSync, show the diff` |
| `gitlab-ci-review` | `.gitlab-ci.yml`, rules, runners, lint, pipeline risks | `review the deploy pipeline for risks` |
| `vault-ops` | Policies, auth, AppRole, KV metadata, access denied | `why does the payments approle have no access to kv/payments/prod` |
| `yandex-cloud-devops` | Yandex Cloud: IAM, Managed Kubernetes, VPC, registry, Lockbox (optional) | `which SAs in the dev folder have editor` |
| `versioned-docs` | Documentation for a specific version of a library or tool (Context7) | `what changed in External Secrets 0.10 for ClusterSecretStore` |

## Planning and reports

| Skill | When | Example prompt |
|---|---|---|
| `jira-planning-story` | Planned task from the template "Problem → Plan → Requirements → Acceptance criteria → Links" | `create a Jira issue for moving the registry` |
| `jira-planning-epic` | Epic with correctly linked subtasks (Epic Name, Epic Link) | `create an epic for retiring the old cluster` |
| `quarterly-planning` | Quarterly goal: a wiki page, then an epic and subtasks | `set up the goal for Q3` |
| `sprint-report` | Sprint snapshot in the wiki | `make a sprint report` |
| `contractor-report` | Review of a contractor's monthly Excel timesheet: reconciliation with Jira, anomalies, a wiki page | `review the contractor report for May` |
| `daily-report` | Daily report in the knowledge base | exactly `Сформируй daily report` (Russian for "generate the daily report"; only this phrase triggers it) |

Team skills (`team-skills/`) are written for the Jira + Confluence + Mattermost combination and work through
`sre-toolbox`. Before first use, fill in the skill's `defaults.yaml`: wiki page IDs (`<ID …>`), Jira field IDs
(`customfield_<ID …>`), theme labels, channels. Substituted values (project, space, assignee) are taken from the
harness config at install time.

## Working on the agents themselves

| Skill | When | Example prompt |
|---|---|---|
| `handoff` | Long-task journal | `start a handoff`, `update the handoff`, `close the task` |
| `kb-compile` | Roll fresh findings and journals up into hubs (once a week) | `run kb-compile` / `/kb-compile` |
| `retro` | Session retro: what to improve in the harness (manual only) | `/retro` at the end of a big task |
| `writing-for-agents` | Editing skills, AGENTS.md, CLAUDE.md | `add a rule about … to AGENTS.md` |

## Built into Claude Code

`/code-review` (finds bugs in a diff), `/simplify` (code cleanup), `/security-review`, `/loop 10m <prompt>` (repeat
on a timer), `/schedule` (a cloud agent on a schedule). These are not part of the harness, but they pair well with it.

## Subagents and profiles

| Who | Where | What it does |
|---|---|---|
| `kb-scout` | Claude Code | Broad search across the knowledge base, repositories, logs, metrics; write tools are forbidden; returns a summary with paths. "use kb-scout to find …" |
| `kb_scout` | Codex | The same for Codex; the rule is to call it once the context is more than half full |
| `task` profile | Codex | Orchestrator: plan → `coder` implements → `reviewer` independently checks → rework until accepted |
| `incident` profile | Codex | `incident_worker` gathers logs and metrics read-only, the orchestrator draws the conclusions |

The models in the agent files are examples; set the ones available to you.
