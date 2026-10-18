**English** · [Русский](ru/obsidian.md)

# Knowledge base with Obsidian

← [Back to README](../README.md)

The most powerful token-saving technique — more than all the others combined. It removes the need to "rediscover" the same problems over and over.

---

## The idea

An SRE team has an implicit shared memory: "we had this problem a year ago, we restarted Redis back then", "this service slows down every Monday at 9 a.m. because of a cron job", "the runbook for alert X is in Vasya's personal notes". This memory lives in people's heads, chats and bookmarks, and the agent (Claude Code or Codex) cannot see it. So every time it starts from scratch and spends tokens on repeating the analysis.

An Obsidian vault turns this memory into a local database that the agent can search through MCP:

- **runbooks/** — what to do for specific alerts.
- **postmortems/** — outcomes of past incidents.
- **services/** — service descriptions: owner, dependencies, SLO, quirks.
- **patterns/** — typical degradation patterns.
- **glossary.md** — a glossary of internal terms.

The MCP server indexes the vault in memory (it simply walks `*.md`), and the tools `obsidian_search`, `obsidian_read_note`, `obsidian_append_finding` give the agent access to it.

---

## Economics

Comparing a "cold" and a "warm" investigation of the same alert:

| Step | Without Obsidian | With Obsidian |
|-----|--------------|-----------|
| Understand what the alert means | Pull 3-5K tokens from VM + VictoriaLogs + user context | `obsidian_search("HighErrorRate checkout")` → 500 tokens from a runbook |
| Find out whether there was a similar incident | Cannot find out — no such information | `obsidian_search` finds a year-old postmortem — 800 tokens |
| Know who the owner is | Poke kube annotations, labels, guess | `services/checkout.md` says it directly — 50 tokens |
| Form a hypothesis | Based on raw data, may miss | Based on already documented patterns |
| **Total model input** | **~20-50K tokens** | **~2-5K tokens** |

A 10x saving is a typical result. And, importantly, **the answer quality is higher**: the agent relies on the team's proven experience instead of guessing from logs.

---

## Recommended vault structure

```
SRE-vault/
├── glossary.md                          # glossary of services, terms, owners
├── services/
│   ├── checkout-api.md                  # service description
│   ├── payment-service.md
│   └── ...
├── runbooks/
│   ├── high-error-rate.md               # one runbook = one alert name
│   ├── db-connection-pool-exhausted.md
│   ├── disk-space-low.md
│   └── ...
├── postmortems/
│   ├── 2024-03-15-checkout-outage.md
│   ├── 2024-08-02-payment-degradation.md
│   └── ...
├── patterns/
│   ├── monday-morning-cron-spike.md     # recurring patterns
│   └── deploy-rollback-checklist.md
└── findings/                            # Claude writes auto-notes here
    └── 2026-05-18-...md
```

---

## Runbook template

A good runbook is structured — this helps both people and the agent:

```markdown
---
alert: HighErrorRate
service: checkout-api
severity: critical
tags: [runbook, http, payment]
---

# HighErrorRate on checkout-api

## What it means
Share of 5xx responses > 5% over the last 5 minutes.

## Initial check
1. vm_query: `sum(rate(http_requests_total{service="checkout-api",code=~"5.."}[5m]))`
2. vl_query for the service in patterns mode
3. Was there a deploy in the last 30 minutes

## Typical causes
- Regression deploy — rollback
- payment-service dependency failure
- DB connection limit

## Actions
1. Rollback: argocd app rollback checkout-api
2. If payment-service: …
3. If DB: …

## Escalation
@checkout-team in Slack #incident-checkout
```

With this format, a request for `HighErrorRate checkout` gives the agent 300-500 tokens of a ready action plan instead of 20K tokens of raw logs.

---

## Postmortem template

```markdown
---
date: 2026-05-18
incident: INC-42
service: checkout-api
duration_min: 47
root_cause: regression
tags: [postmortem, payment-service]
---

# Outage checkout-api 2026-05-18

## TL;DR
The checkout-api deploy at 14:18 contained a timeout-handling regression in
payment_service.process_refund. Error rate jumped to 23%.
A rollback at 14:47 fixed the problem.

## Timeline
- 14:18 — deploy checkout-api commit a3f1b2
- 14:23 — HighErrorRate fires
- 14:31 — on-call engineer started the investigation
- 14:45 — commit found, rollback decided
- 14:47 — rollback finished, metrics back to normal

## What we learned
Commit a3f1b2 changed the timeout from 5s to 500ms.

## Action items
- [ ] Add an integration test for the retry logic
- [ ] Make the deploy canary > 5 minutes
```

Six months later, `obsidian_search("payment_service refund timeout")` will find this postmortem in 100 ms, and the agent will see that a similar problem has happened before.

---

## Service description template

```markdown
---
service: checkout-api
team: checkout
slack: "#team-checkout"
tier: critical
slo:
  availability: 99.95
  latency_p99_ms: 800
tags: [service, payment]
---

# checkout-api

## Purpose
Accepts order checkout requests from the web and mobile apps.

## Dependencies
- payment-service (synchronous)
- inventory-service (synchronous)
- redis-checkout (cache, asynchronous)
- postgres-checkout (state)

## Quirks
- Peak load on Friday 18:00-22:00.
- Every Monday at 9:00 the background cron job rebuilds-cart-cache generates
  a CPU spike (this is normal).

## Owner
@vasily-petrov

## Runbooks
- [HighErrorRate](../../runbooks/high-error-rate.md)
- [HighLatency](../../runbooks/high-latency-checkout.md)
```

---

## Tools

Search across the shared harness knowledge base is `kb_search` / `kb_list` (via `kb.py`, path — `obsidian.kb_tool`,
see [tools.md](./tools.md)); `obsidian_*` work with the vault from `obsidian.vault_path`.

| Tool | Purpose |
|------|-----------|
| `obsidian_search(query, top_k)` | Semantic-ish search over the vault. Simple term-overlap scoring, with a bonus for hits in the heading/file name. Returns snippets, not whole files. |
| `obsidian_read_note(path)` | Read a specific note found via search. Limit `max_note_chars` (8000 by default). |
| `obsidian_append_finding(title, content, folder, tags)` | Write a new note (to `findings/` by default). Enabled with `obsidian.allow_writes: true`. |

Parameter details are in [tools.md](./tools.md).

---

## Security

- All three tools apply the redactor — even if a note contains a secret, it is masked before being returned to the agent.
- `path traversal` protection: you cannot escape the vault with `path="../etc/passwd"`.
- Writing is disabled by default. If enabled, writes go only to vault subfolders, and the file name is normalized (slug + date).
- The vault is stored locally and does not leave the machine unless the agent explicitly returns its contents in a response.

---

## Vault deployment

Two scenarios:

**A local vault on the SRE's machine.** Claude Desktop + the MCP server on a laptop. The vault is a regular Obsidian folder. When the team updates notes, Obsidian Sync / git / iCloud Drive roll out the changes. The MCP index refreshes by `mtime` — change a file and the next search sees the fresh version.

**A shared vault on a server.** The vault lives on a shared server (a git repository with auto-pull). All SREs use the same set of runbooks. Changes go through PRs in git. The MCP server runs there too and is updated by a `git pull` cron.

The second option is stronger in a team of 5+ people — centralized knowledge. The first is for individual work.

---

## A small rule

"If you investigated an incident and had to figure something out by hand, that is a sign a note is needed in the vault." In a year the vault becomes the team's main SRE asset, and the agent becomes stronger the more has accumulated in it.

Practical examples of using Obsidian in incidents — see [examples.md](./examples.md).
