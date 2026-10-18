---
name: observability-triage
description: Investigate alerts, latency, errors and saturation using Grafana, Prometheus/VictoriaMetrics and service logs through the available observability tools.
---

Find the matching runbook in the knowledge base (`{{KB_ROOT}}`, via a search tool such as `kb_search` on `{{MCP_HUB}}`) first when available. Resolve the actual datasource/instance and available tool schemas once. Establish service, environment, incident interval and timezone; use the same absolute interval across evidence sources.

Use metrics and logs tools from the MCP server when present (for example `vm_query` / `vm_query_range` for PromQL/MetricsQL, `vl_query` for logs, Grafana dashboard/annotation reads); otherwise fall back to the HTTP query APIs (`/api/v1/query`, `/api/v1/query_range`) or the Grafana UI. Prefer tools that return aggregated summaries over raw points.

Start with a scoped query and limited series/rows. Use observed metric names and labels; do not invent them. Distinguish instant snapshots from range queries, counters from gauges, and empty results from zero. Choose a range step appropriate to the incident resolution and query cost. Check scrape gaps and resets before interpreting a trend.

Correlate error rate, request volume, latency and saturation with deployment or alert timestamps. Retrieve aggregate log counts before representative redacted messages. Preserve exact queries, time bounds, units and data gaps; avoid entire dashboard JSON and unrestricted log dumps.

State impact and evidence separately from hypotheses. A coincident deployment is not sufficient evidence of causation. Stop broad collection when the decision is supported; identify the smallest next check when it is not. Follow global authorization rules for any remediation or external report publication.

Query semantics: https://prometheus.io/docs/prometheus/latest/querying/basics/
