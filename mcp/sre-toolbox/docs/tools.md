**English** · [Русский](ru/tools.md)

# MCP server tools

← [Back to README](../README.md)

A reference of all tools the server provides to the agent (Claude Code or Codex). Each is described in terms of what it does, its arguments, its response, and the security measures applied.

---

## Summary table

| Category | Tool | Purpose |
|-----------|------|-----------|
| Alerts | `am_active_alerts` | Active alerts from Alertmanager |
| Alerts | `am_silences` | Active silences |
| Metrics | `vm_query` | Instant PromQL |
| Metrics | `vm_query_range` | Range PromQL (aggregates by default) |
| Metrics | `vm_label_values` | Label value discovery |
| Logs | `vl_query` | LogsQL with `patterns` mode |
| Logs | `vl_streams` | List of streams |
| Knowledge base | `kb_search` | Knowledge base search via `kb.py` |
| Knowledge base | `kb_list` | Knowledge base catalog with filters |
| Knowledge base | `obsidian_search` | Vault search |
| Knowledge base | `obsidian_read_note` | Read a specific note |
| Knowledge base | `obsidian_append_finding` | Write a new note |
| Jira | `jira_get_issue` | Get an issue by key |
| Jira | `jira_search` | Search issues by JQL |
| Jira | `jira_create_issue` | Create an issue (under `allow_writes`) |
| Jira | `jira_update_issue` | Update issue fields |
| Jira | `jira_transition_issue` | Change status |
| Jira | `jira_add_comment` | Add a comment |
| Jira | `jira_list_projects` | List projects |
| Jira | `jira_list_boards` | List Agile boards |
| Jira | `jira_list_sprints` | List sprints |
| Jira | `jira_sprint_issues` | Sprint issues |
| Confluence | `confluence_get_page` | Page by id or (space, title) |
| Confluence | `confluence_search` | CQL search |
| Confluence | `confluence_get_page_children` | Child pages |
| Confluence | `confluence_get_bookmark` | Page from a bookmark in the config |

---

## Alerts (Alertmanager)

### `am_active_alerts`

Returns active alerts from Alertmanager (`/api/v2/alerts`).

| Parameter | Type | Description |
|----------|-----|----------|
| `severity` | string? | Filter: `critical`, `warning`, `info` |
| `service` | string? | Filter by the `service` (or `job`) label |
| `limit` | int | 50 by default, max 200 |
| `instance` | string? | Alertmanager from `alertmanager.instances` (name or alias); defaults to `default_instance` |

Multiple Alertmanagers are defined in `alertmanager.instances`; the shared `verify_ssl`, `timeout_seconds`, `auth` live at the top level, and an instance overrides them. The old single-`url` format works as the `default` instance. An unknown name returns the list of available ones; a URL is not accepted as a parameter.

**Response** — `instance` and compact JSON: `name`, `severity`, `service`, `started_at`, `summary`, `runbook`. No full labels, generatorURL, fingerprint or other noise.

### `am_silences`

Active silences in Alertmanager (`/api/v2/silences`). Useful so the agent can see what is currently silenced and why.

| Parameter | Type | Description |
|----------|-----|----------|
| `active_only` | bool | `true` by default — active only |
| `instance` | string? | Same as in `am_active_alerts` |

---

## Separate `victoriametrics` MCP server

If you have a separate VictoriaMetrics MCP HTTP server deployed, it becomes the
priority source for agent metric queries, connected in the project's `.mcp.json` (example — [`.mcp.example.json`](../.mcp.example.json)):

```json
"victoriametrics": {
  "type": "http",
  "url": "https://vm-mcp.example.com/mcp"
}
```

This is a standalone server. Its tools are called as
`mcp__victoriametrics__query`, `mcp__victoriametrics__query_range`,
`mcp__victoriametrics__label_values` and `mcp__victoriametrics__series`.
Do not confuse them with the local `vm_query`, `vm_query_range`, `vm_label_values` from
`sre-toolbox`: the latter use `config.yaml` and are meant for
fallback/compatibility.

`mcp__victoriametrics__query` accepts `query` and optional `time`, `step`,
`timeout`, `nocache`. `mcp__victoriametrics__query_range` accepts `query`,
`start`, `end`, `step`, `timeout`, `nocache`. Unlike the local
`vm_query_range`, the separate MCP returns raw `[timestamp, value]` points and
has no `summarize`; use a narrow window, a reasonable `step` and aggregating
PromQL/MetricsQL for long history.

To check flapping, it is convenient to query `max_over_time((<expr>)[1h:1m])` with
`step=1h`. For discovery, use `label_values` and `series` if the result is
empty: the separate MCP may look at a different VM instance or tenant, and
a wrong label/source gives `result: []` without an explicit error. Do not conclude
"metrics are missing" until you have checked the actual labels and the retention boundary.

If the separate MCP is unavailable, record the error and use the local
`sre-toolbox.vm_query`/`vm_query_range` as a fallback. For reference on
VictoriaMetrics semantics, `mcp__victoriametrics__documentation` is available.

## VictoriaMetrics Select

VictoriaMetrics Select has a Prometheus-compatible API, so the standard endpoints `/api/v1/query`, `/api/v1/query_range`, `/api/v1/label/<name>/values` are used.

This section describes the local `sre-toolbox` tools. For a new investigation,
use the separate MCP from the section above first.

### Route and tenants

Tools go only to `victoriametrics.url`. For a cluster VM, multitenant reads are convenient
(`/select/multitenant/prometheus`): all tenants are visible at once, and the cluster is selected by the
`vm_account_id` label (for example 100 — prod, 200 — staging; list —
`vm_label_values("vm_account_id")`). URLs and credentials are not accepted as tool parameters.

The overall request and response limits are set in `victoriametrics.limits`: `request_timeout_seconds`, `max_timeout_seconds`, `max_range_seconds`, `min_step_seconds`, `max_step_seconds`, `max_points_requested`, `max_points_per_series` and `max_response_bytes`.

### `vm_query`

Instant PromQL query. Returns the current value of a metric.

| Parameter | Type | Description |
|----------|-----|----------|
| `promql` | string | PromQL expression |
| `time_` | string? | RFC3339 timestamp, defaults to now |

**Security measures**: an allowlist of permitted services/namespaces is checked. The response is limited by `max_series_returned` from the config (30 series by default).

Example of an instant query against prod:

```json
{
  "promql": "sum by (namespace) (kube_pod_container_status_restarts_total{vm_account_id=\"100\"})"
}
```

### `vm_query_range`

Range PromQL query. By default returns **aggregates** (min/max/avg/p50/p95/p99), not raw points.

| Parameter | Type | Description |
|----------|-----|----------|
| `promql` | string | PromQL expression |
| `start`, `end` | string | RFC3339 or Prometheus-style |
| `step` | string | `60s` by default |
| `summarize` | bool | If `true` (default) — aggregates, not points |

**Savings**: `summarize=true` compresses the response 50-200 times. If you really need points, use `summarize=false`; the server still thins them out to `max_points_per_series`.

Example of a range query:

```json
{
  "promql": "sum(rate(container_cpu_usage_seconds_total{vm_account_id=\"100\", namespace=\"payments-prod\"}[5m]))",
  "start": "2026-10-16T00:00:00Z",
  "end": "2026-10-17T00:00:00Z",
  "step": "5m"
}
```

### `vm_label_values`

List of label values from `/api/v1/label/<name>/values`. Returns no data, only identifiers.

| Parameter | Type | Description |
|----------|-----|----------|
| `label` | string | Label name. Often `__name__` (metric names), `job`, `service` |
| `match` | string? | A `{service="x"}` selector for filtering |

Useful for discovery: "what metrics does service X have", "which services write metrics at all".

---

## VictoriaLogs

VictoriaLogs is a separate VictoriaMetrics product for logs with its own query language, LogsQL. The main endpoint is `/select/logsql/query` (an NDJSON stream).

### Tenants

Tools go only to `victorialogs.url`. The tenant is selected with the `tenant` parameter: a name or AccountID from
the server-side `victorialogs.tenants` map, defaulting to `victorialogs.default_tenant`. The MCP sets the
`AccountID` and `ProjectID: 0` headers, so the account needs access to all tenants (for example
a dedicated read-only vmauth user). An unknown tenant returns the list of available ones; without a map, no headers are set.

Example of a log query against the payments-prod tenant:

```json
{
  "tenant": "payments-prod",
  "logsql": "namespace:payments-prod error",
  "start": "2026-10-17T00:00:00Z",
  "end": "2026-10-17T06:00:00Z",
  "limit": 100,
  "mode": "patterns"
}
```

Limits are set in `victorialogs.limits`: `request_timeout_seconds`, `max_timeout_seconds`, `max_query_window_hours`, `max_lines_returned`, `max_streams_returned`, `max_input_bytes` and `max_response_bytes`.

### `vl_query`

LogsQL query to VictoriaLogs.

| Parameter | Type | Description |
|----------|-----|----------|
| `logsql` | string | LogsQL expression, e.g. `_stream:{service="api"} error` |
| `start`, `end` | string | RFC3339, query window |
| `limit` | int? | max lines (capped at `max_lines_returned`) |
| `mode` | enum? | `patterns` (default — clustering) or `lines` (raw) |
| `tenant` | string? | Name or AccountID from `victorialogs.tenants`; defaults to `default_tenant` |

**The key savings measure is `patterns` mode**: the server normalizes lines (numbers → `<N>`, hex → `<HEX>`, long literals → `<STR>`), groups them and returns the top N templates with counters. Instead of "4521 similar ERROR lines" you get one line with `count=4521`.

**Window limit**: queries wider than `max_query_window_hours` (24h by default) are rejected — protection against accidental bulk export.

### `vl_streams`

List of streams (`_stream`) in VictoriaLogs via `/select/logsql/streams`. Useful for understanding which services are available.

| Parameter | Type | Description |
|----------|-----|----------|
| `query` | string | LogsQL filter, `*` by default |
| `limit` | int | Max streams in the response |
| `tenant` | string? | Name or AccountID from `victorialogs.tenants`; defaults to `default_tenant` |

---

## Knowledge base (`kb.py`)

`kb_search` and `kb_list` load `kb.py` from agent-harness and return sections with line ranges, not whole
documents. The path to `kb.py` is `obsidian.kb_tool` (by default `../../tools/kb.py` relative to `mcp/sre-toolbox`),
and the knowledge base root is `paths.kb_root` from the harness config. Notes from `obsidian.vault_path` are added if the vault is a separate
folder (`include_obsidian`).

### `kb_search`

| Parameter | Type | Description |
|----------|-----|----------|
| `query` | string | Symptom, service, alert, issue key (`OPS-1234`) |
| `limit` | int | How many documents to return (6 by default, capped at 15) |
| `service`, `ticket`, `doc_type` | string? | Filters on document metadata |
| `include_obsidian` | bool | Also search vault notes (`true` by default) |

### `kb_list`

Catalog (newest first) with filters `service`, `ticket`, `doc_type`, `since` (YYYY-MM-DD), `limit` (capped at 100).

## Obsidian vault

A local knowledge base with runbooks, postmortems and service descriptions. The most important token-saving technique — see [obsidian.md](./obsidian.md) for details and templates.

### `obsidian_search`

Vault search. Simple term-overlap scoring + a bonus for a match in the heading.

| Parameter | Type | Description |
|----------|-----|----------|
| `query` | string | Keywords: alert name, service, symptom |
| `top_k` | int | How many best matches to return (5 by default, capped at 20) |

Returns: `{count, vault_size, results: [{path, title, score, snippet}]}`. Snippets are limited by `snippet_chars` (400 characters by default).

### `obsidian_read_note`

Read a specific note found via search.

| Parameter | Type | Description |
|----------|-----|----------|
| `path` | string | Path relative to the vault root |

Path traversal protection. Limit `max_note_chars` (8000 by default).

### `obsidian_append_finding`

Write a new note (cumulative memory). Disabled by default — enabled with `obsidian.allow_writes: true`.

| Parameter | Type | Description |
|----------|-----|----------|
| `title` | string | Title — the H1 and part of the file name |
| `content` | string | Note body in markdown |
| `folder` | string | Vault subfolder, `findings` by default |
| `tags` | list[string]? | Tags for the frontmatter |

---

## Jira (Server / Data Center)

A personal PAT is passed in `jira.auth.bearer_token` (the `Authorization: Bearer ...` header).
The PAT is issued in Jira: `Profile` → `Personal Access Tokens` → `Create token`.

By default the module is **read-only**. Writes (creating issues,
updating fields, transitions, comments) are enabled with the
`jira.allow_writes: true` flag. You can additionally restrict the set of projects
with `jira.allow_projects`.

Responses are compressed as much as possible: long `description`/`comments` are truncated to
`limits.max_field_chars`, and by default a compact set of fields
from `limits.default_fields` is returned.

### `jira_get_issue`

| Parameter | Type | Description |
|----------|-----|----------|
| `key` | string | Issue key, e.g. `OPS-123` |
| `fields` | list[string]? | Fields; defaults come from the config |
| `with_comments` | bool | Include the N latest comments |

### `jira_search`

JQL search. Supports `startAt` for pagination.

| Parameter | Type | Description |
|----------|-----|----------|
| `jql` | string | JQL expression |
| `fields` | list[string]? | Fields; a compact set by default |
| `limit` | int | Capped at `limits.max_issues_returned` |
| `start_at` | int | Offset for pagination |

### `jira_create_issue` / `jira_update_issue` / `jira_transition_issue` / `jira_add_comment`

All require `jira.allow_writes: true`. `jira_transition_issue` takes the transition
name (not the id) — the required id is looked up automatically.

### `jira_list_projects` / `jira_list_boards` / `jira_list_sprints` / `jira_sprint_issues`

Reads via the Agile API (`/rest/agile/1.0`). Handy for "what's in my sprint".

---

## Confluence (Server / Data Center)

Same as Jira — `confluence.auth.bearer_token` (a separate PAT). Read-only
by default.

The page body is returned as plain text (storage XHTML is converted
to text without dependencies) and truncated to `limits.max_page_chars` —
this compresses a 100K-character quarterly plan to 12K, saving tokens.

### `confluence_get_page`

| Parameter | Type | Description |
|----------|-----|----------|
| `page_id` | string? | Page ID |
| `space` | string? | Space key (together with `title`) |
| `title` | string? | Exact page title |

### `confluence_search`

| Parameter | Type | Description |
|----------|-----|----------|
| `cql` | string | CQL expression |
| `limit` | int | Capped at `limits.max_search_results` |
| `include_body` | bool | Whether to include page bodies (expensive) |

### `confluence_get_page_children`

List of child pages. Useful: get the root page of a plan, then
walk through its sections.

### `confluence_get_bookmark`

Quick access to pinned pages from `confluence.bookmarks` in the config:

```yaml
confluence:
  bookmarks:
    quarterly_plan:
      space: "TEAM"
      title: "Quarterly Plan Q3 2026"
```

Then `confluence_get_bookmark("quarterly_plan")` returns the page right away.

---

## Extending with your own tools

In a working version of the server it is easy to add your own tools for your infrastructure:

- `get_recent_deploys` — the last N deploys of a service (from Argo CD / GitOps / your own deploy tracker).
- `correlate_alert_with_deploys` — whether there was a deploy within ±30 minutes before the alert.
- `get_runbook` — the runbook for a specific alert from Confluence / a repository.

The template for adding a tool is described in the [README](../README.md#extending).

---

## Tools we deliberately do NOT have

These tools could be useful, but we do not add them for security and cost reasons:

- `get_full_repo` — no. If you need code, there is `search_code` with a 200-line fragment limit.
- `restart_pod`, `scale_deployment` — not in the first version. Destructive actions are added only after a trial period and with a mandatory human-in-the-loop.
- `raw_query` to arbitrary APIs — no. Only specific tools with validated parameters.
