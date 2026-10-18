**English** · [Русский](ru/token-economy.md)

# Saving tokens and cost

← [Back to README](../README.md)

The cost of using Claude consists of input tokens (prompt + tool results) and output tokens (the model's response). For an SRE workload, **input tokens dominate** by a factor of 10-50, because logs and metrics are massive while answers are short.

> **The biggest source of savings is the knowledge base in Obsidian.** It has its own file: [obsidian.md](./obsidian.md).

---

## Sources of cost

| Source | Share of cost | What to do |
|----------|--------------|------------|
| Raw logs in the `vl_query` response | up to 70% | `patterns` mode (clustering on the MCP side) |
| Full metric series | 10-20% | `summarize=true` by default |
| Repeated system prompts and tool descriptions | 10-15% | Prompt caching |
| Generating the answer itself | 5-10% | `max_tokens` limit |

---

## Minimization at the MCP server level

This is the most effective place to save — it saves both tokens and leak risk at the same time.

**Specific techniques:**

- Return JSON, not YAML or plain text — JSON is more compact and tokenizes better.
- Do not return fields that are not needed for the answer. A Kubernetes Pod object has 200+ fields; you need 5.
- Deduplicate: 10000 identical log lines → one line + a counter.
- Shorten field names where it does not hurt readability (`timestamp` → `ts`).
- Return the top N, not everything: the top 10 errors instead of all 4000.

---

## Prompt caching

The Anthropic API supports caching of prompt prefixes. Cached blocks are **10 times cheaper** on input.

What to cache:

- The system prompt describing the role (SRE assistant, rules, response format).
- Descriptions of all tools and their JSON schemas.
- Standard runbook templates.
- The glossary of your services (if you use consistent names).

Implementation: add `cache_control` to these blocks in the API call. TTL is 5 minutes by default and can be extended.

Effect on a typical SRE workload: -40-60% on input tokens.

---

## Multi-model pipeline

Use cheap models for preparatory work and expensive ones only for final decisions.

**Recommended combination:**

| Stage | Model | Cost relative to Opus |
|------|--------|------------------------------|
| Alert classification, log parsing, filtering | Haiku | ~1/15 |
| Main incident analysis, diagnostics | Sonnet | ~1/3 |
| Complex cases, writing the postmortem | Opus | 1 |

Implementation: the MCP server can pre-process with a cheap model itself before handing the result to the main model. For example, `vl_query` under the hood asks Haiku to cluster lines → returns patterns directly.

---

## Semantic pre-search

Instead of dumping a pile of code into Claude in search of the relevant fragment:

1. A vector index of the codebase (Qdrant/Weaviate/pgvector) is kept locally on the MCP server.
2. A `search_code` request first runs a semantic search and picks the top 5 fragments.
3. Only these 5 fragments go to Claude, not the whole file or the whole repo.

The same logic applies to runbooks and postmortems — implemented via [Obsidian](./obsidian.md).

---

## Techniques for VictoriaMetrics

- **Always aggregate in PromQL**: `sum by (service) (rate(...))`, not raw per-pod points.
- **Use a coarser step**: 60s instead of 15s if you need the overall trend.
- **Use `summarize=true`** in `vm_query_range` — returns only min/max/p50/p95/p99 instead of the series.
- **High-cardinality protection**: the PromQL parser rejects queries like `{*}` or grouping by `instance` without aggregation.
- **Pre-computed recording rules**: for typical questions ("error rate of service X") keep ready-made series in VM so Claude queries them instead of complex computations.

---

## Techniques for VictoriaLogs

VictoriaLogs is the main source of expensive tokens. A few rules:

- **`patterns` mode by default**: clustering on the MCP server side. It returns a template + counter, not lines.
- **Filter in LogsQL**, not in Claude: let VictoriaLogs discard what is irrelevant (`_stream:{service="x"} error -healthcheck`).
- **Use the `_stream:{...}` selector** — it is the cheapest filter in LogsQL; it works on the index.
- **A 500-line ceiling**, 100 by default. If an SRE really needs more, they should phrase the query more precisely.
- **Structured JSON parsing on the server**: after extracting the needed fields (`_msg`, `level`, `trace_id`) return only them, not the whole line.
- **Deduplication by hash**: if there are 200 identical lines, return one with `count=200` (this is what `patterns` mode does).
- **Narrow time window**: `max_query_window_hours` in the config forbids queries wider than 24h.

---

## Cost metrics and alerts

The MCP server should export metrics to Prometheus/VictoriaMetrics itself:

- `mcp_tool_calls_total{tool, status}` — call counter.
- `mcp_tokens_estimated_total{tool, direction}` — estimate of sent and received tokens (by JSON length).
- `mcp_tool_response_size_bytes` — histogram of response sizes.
- `mcp_redaction_hits_total{rule}` — how many times a redaction rule fired (important for security).

Alerts:

- Anomalous growth of `mcp_tokens_estimated_total` (cost explosion).
- Anomalies in `mcp_tool_response_size_bytes` (someone started sending huge responses).
- Any `mcp_redaction_hits_total > 0` — to the SIEM for review.

---

## Cost estimate — order of magnitude

A rough estimate for a team of 10 SREs using Sonnet with prompt caching and all the optimizations above:

- 50-200 incidents per day
- Average investigation: 5-10 tool calls, 20-50K input tokens, 1-2K output
- With cached input ~$0.30 / 1M, output ~$15 / 1M

That comes to roughly **$50-200 per day for the whole team** with a reasonable setup. Without optimizations it is easily 5-10 times more.

---

## The main rule

**Savings and security coincide.** The less you send, the cheaper and safer it is. Most token optimizations also reduce the risk of leaking code — see [security.md](./security.md).
