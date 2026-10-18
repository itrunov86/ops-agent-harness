**English** · [Русский](ru/architecture.md)

# Architecture

← [Back to README](../README.md)

## What it is and why

An MCP (Model Context Protocol) server is a local process that exposes to Claude a set of tools for working with your infrastructure. Claude decides on its own which tools to call, in what order and with what parameters, and then interprets the results in natural language.

**Problems it solves**

- Incident triage: an alert fires → Claude pulls the relevant metrics, logs and deploy history itself → produces a hypothesis.
- Postmortems: automatic timeline collection from VictoriaMetrics, VictoriaLogs and Alertmanager.
- Routine ops: "show the top 10 errors in service X over the last hour", "which alerts have been firing for more than 30 minutes".
- Developer self-service: questions like "why is my service slow" can be answered without escalating to SRE.

**What to understand right away**

The MCP server itself runs locally inside your perimeter. But Claude is a cloud model, so **tool call results are sent to Anthropic** as part of the context used to generate the answer. Details are in [security.md](./security.md).

---

## High-level diagram

```
┌──────────────────────────────────────────────────────────────┐
│                  Company perimeter (VPC)                     │
│                                                              │
│   ┌──────────────┐                                           │
│   │ Alertmanager │──┐                                        │
│   └──────────────┘  │   ┌──────────────────────┐             │
│   ┌──────────────┐  │   │      MCP server      │             │
│   │ VictoriaMetr │──┼──▶│   (FastMCP, stdio)   │             │
│   └──────────────┘  │   │                      │             │
│   ┌──────────────┐  │   │  ┌────────────────┐  │             │
│   │ VictoriaLogs │──┘   │  │ Redactor /     │  │             │
│   └──────────────┘      │  │ Tokenizer /    │  │             │
│   ┌──────────────┐      │  │ Audit log      │  │             │
│   │ Obsidian     │──────│  └────────────────┘  │             │
│   │ vault        │      │                      │             │
│   └──────────────┘      └──────────┬───────────┘             │
│                                    │                         │
│                         ┌──────────▼───────────┐             │
│                         │ Egress proxy + DLP   │             │
│                         └──────────┬───────────┘             │
└────────────────────────────────────┼─────────────────────────┘
                                     │ PrivateLink / mTLS
                                     ▼
                         ┌──────────────────────┐
                         │ Claude API (Bedrock  │
                         │ or Anthropic direct) │
                         └──────────────────────┘
```

---

## Data flow during incident triage

1. The alert is registered in Alertmanager.
2. The on-call SRE opens Claude (Desktop / Code / Cowork) and asks: "what's wrong with the checkout service?".
3. Claude calls `obsidian_search` to check whether a runbook already exists (see [obsidian.md](./obsidian.md)).
4. Claude calls `am_active_alerts` through MCP — Alertmanager returns a compact list.
5. `mcp__victoriametrics__query_range` against the separate VictoriaMetrics MCP gets the error rate curve; the local `vm_query_range` is used only as a fallback.
6. `vl_query` against VictoriaLogs in `patterns` mode — the top error patterns for the window after the alert started.
7. (Optional) `get_recent_deploys` — if a deploy tracker is connected.
8. Claude formulates a hypothesis and returns it to the user.

At every step the MCP server applies redaction, tokenization and auditing (see [security.md](./security.md)).

---

## Where the MCP server lives

Recommended topology:

- **Production**: a container in the operations Kubernetes cluster (not the product one), or a dedicated VM. Service accounts with the minimum permissions needed to read metrics and logs.
- **Dev**: the same binary runs locally on the SRE's laptop with a tunnel to the dev environment (for developing tools).
- **Transport**: stdio (over an SSH tunnel or locally) for individual work; HTTP/SSE with mTLS if the server has to serve the whole team.

---

## Implementation

The working server code is in [server.py](../server.py). Connection parameters come from `config.yaml` (template: [config.example.yaml](../config.example.yaml)).

Key implementation features:

- **FastMCP** as the framework — minimal boilerplate.
- **YAML configuration** + `${ENV_VAR}` substitution for secrets.
- **Redactor** with configurable regexes (AWS keys, JWT, email, INN, SNILS, internal hosts).
- **Allowlist** of permitted services and namespaces, checked on every request.
- **Audit log** — every tool call is written to JSONL with the response size and a redaction hit counter.
- **Limits** on response size (number of series, points, lines) — configurable.
- **A single Grafana** — `grafana.url`; metrics and logs bypass Grafana and go directly to VictoriaMetrics/VictoriaLogs.
- **Log tenants and Alertmanager instances** — `vl_*` accept a `tenant` from the server-side map `victorialogs.tenants` (the `AccountID` header), `am_*` accept an `instance` from `alertmanager.instances`; an arbitrary URL or a number outside the map is rejected.
- **Separate VictoriaMetrics MCP (optional)** — an external HTTP server connected in the project's `.mcp.json`; the agent uses `mcp__victoriametrics__query*` to fetch metrics directly, and the local `vm_*` tools remain as a fallback. An empty result is checked through label/series discovery, because the external MCP may be looking at a different VM instance or tenant.
- **PromQL guard limits** — timeout, maximum range window, allowed step, estimated point count and serialized response size are checked before/during the query.
- **LogsQL guard limits** — timeout, maximum window, input NDJSON and serialized response size are capped before/during the query.
- **Streaming NDJSON** for VictoriaLogs (the right way to read `/select/logsql/query`).
- **`summarize=true` by default** in `vm_query_range` — 50-200x savings compared to raw points.
- **`patterns` mode by default** in `vl_query` — server-side clustering.
- **In-memory Obsidian index** with incremental updates by `mtime`.

---

## Next

- [tools.md](./tools.md) — reference for every tool.
- [security.md](./security.md) — protecting code from Anthropic.
- [token-economy.md](./token-economy.md) — saving tokens.
- [obsidian.md](./obsidian.md) — knowledge base through Obsidian.
- [deployment.md](./deployment.md) — installation and operations.
- [examples.md](./examples.md) — practical usage scenarios.
