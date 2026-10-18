**English** · [Русский](ru/victoriametrics-mcp.md)

# Separate VictoriaMetrics MCP server

## Connecting

If you have a separate VictoriaMetrics MCP HTTP server, connect it through the project's `.mcp.json` (example — [`.mcp.example.json`](../.mcp.example.json)):

```json
{
  "mcpServers": {
    "victoriametrics": {
      "type": "http",
      "url": "https://vm-mcp.example.com/mcp"
    }
  }
}
```

After restarting Claude Code/Claude Desktop, the server's tools are available
under names like `mcp__victoriametrics__query_range`.

This is a separate VictoriaMetrics MCP server, not `vm_query_range` from the local
`sre-toolbox`. The local `vm_*` tools use `config.yaml` and can go
through a configured endpoint or a Grafana datasource proxy. For fetching the
metrics themselves, the separate `victoriametrics` MCP always takes priority; the local
`sre-toolbox.vm_*` is a fallback if the separate server is unavailable.

Do not use Grafana or arbitrary HTTP/curl to fetch metrics when
the MCP is available. Grafana can be used for dashboards, alert rules and
data source context.

## Main tools

| MCP tool | Purpose |
|---|---|
| `mcp__victoriametrics__query` | Instant PromQL/MetricsQL query |
| `mcp__victoriametrics__query_range` | Range query over an interval |
| `mcp__victoriametrics__label_values` | Values of a given label |
| `mcp__victoriametrics__series` | Time series discovery by selector |
| `mcp__victoriametrics__metrics` | Names of available metrics |
| `mcp__victoriametrics__metrics_metadata` | Metric type, help and unit |
| `mcp__victoriametrics__rules` | Recording/alerting rules |
| `mcp__victoriametrics__alerts` | Pending/firing alerts |
| `mcp__victoriametrics__documentation` | Search the official VictoriaMetrics documentation |

`query` accepts `query`, optionally `time`, `step`, `timeout`, `nocache`, and
returns an instant result. `query_range` accepts `query`, `start`, `end`,
`step`, optionally `timeout` and `nocache`.

Example:

```text
mcp__victoriametrics__query_range(
  query='sum(rate(http_requests_total{service="checkout"}[5m]))',
  start='2026-07-21T10:00:00Z',
  end='2026-07-21T11:00:00Z',
  step='1m',
  nocache=true
)
```

## The right order of work

1. Before an expensive investigation, first check `obsidian_search` in
   `sre-toolbox` — a ready runbook may already contain the PromQL and context.
2. Once you have PromQL from an alert, rule or runbook, first run it through
   `mcp__victoriametrics__query` or `mcp__victoriametrics__query_range`.
3. Start with a narrow window around the event. To check how long the
   threshold was exceeded, use a `1m` step or the actual data step.
4. To check flapping/history, use a wider window and an aggregating
   subquery, for example `max_over_time((<expr>)[1h:1m])` with `step=1h`.
5. In the result, state the source, the exact window and timezone (usually UTC), selector,
   threshold, maximum and duration of the breach. Do not mix data from this
   server with the Grafana proxy without an explicit note.

## Result format and token savings

`query_range` of the separate MCP returns a standard Prometheus response with raw
points of the form `[unix_timestamp, value]`. It has no `summarize` parameter like
the local `sre-toolbox.vm_query_range`, so:

- for regular viewing, prefer aggregating PromQL/MetricsQL expressions;
- for a long window, increase `step`, but do not miss short spikes;
- if needed, collapse points locally into min/max/avg/p95 and keep the
  peak timestamp;
- do not pass a large array of raw points to the model unless necessary.

## An empty result is not proof that a metric is missing

The separate MCP may look at a different VM instance or tenant than the alert's
source. `result: []`, `seriesFetched: 0` or an empty `query_range` must first be
checked:

```text
mcp__victoriametrics__label_values(
  label_name='namespace',
  match='{__name__=~"..."}',
  limit=100
)
```

If the label has a different name, check `exported_namespace`, `service`, `job`
and other labels via `label_values` or `series`. Only after discovery
draw a conclusion: there is no data, the label is wrong, or the connected MCP is looking at
the wrong source.

Do not invent PromQL, labels, retention or history depth. If the server
returns data only from a later date onward, record the actual
retention boundary.

## Limitations and security

- Datasource URL, tenant, credentials and tokens are not tool arguments.
- All queries to production must be read-only and as narrow as possible.
- For questions about VictoriaMetrics semantics, use
  `mcp__victoriametrics__documentation` first rather than guessing.
- If the separate server is unavailable, say so explicitly and use
  `sre-toolbox.vm_query`/`vm_query_range` as a fallback; do not replace the error
  with zero metrics.
