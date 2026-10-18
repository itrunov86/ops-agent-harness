**English** · [Русский](ru/examples.md)

# Practical usage examples

← [Back to README](../README.md)

Complete scenarios of "how to use this in real SRE work". Each example shows the prompt the user gives and which tools Claude calls under the hood.

---

## B.1. Morning round — what happened overnight

**Prompt:**
> What happened to the infrastructure over the last 12 hours? Which critical alerts fired, which are resolved now, and what needs my attention?

**What Claude does:**
1. `am_active_alerts(severity="critical")` — what is firing now.
2. `am_silences(active_only=true)` — what is silenced and why.
3. `vm_query_range` for basic availability metrics (`up`, error rate for the top services) with `summarize=true`.
4. `obsidian_search("incident yesterday")` — in case there is a fresh postmortem.

**What you get:** a short dashboard-style answer in 30 seconds: "there were 3 critical incidents, 2 self-resolved, 1 needs investigation — the vault already contains a draft from the night on-call engineer".

---

## B.2. Initial alert triage

**Prompt:**
> `HighErrorRate` is firing on `checkout-api`. What's going on with it?

**What Claude does:**
1. `obsidian_search("HighErrorRate checkout")` — ALWAYS first! Often this is an already documented pattern.
2. If a runbook is found — `obsidian_read_note(runbooks/high-error-rate.md)`.
3. `vm_query_range` for the error rate over the last hour (`summarize=true`).
4. `vl_query` in `patterns` mode for the window after the alert started.
5. Comparison with typical patterns from postmortems/.

**What you get:** "This looks like incident INC-42 from March — it had the same `payment timeout` pattern. A rollback fixed it then. There was a deploy at 14:18 — I recommend reverting commit a3f1b2."

---

## B.3. Correlating metrics and logs

**Prompt:**
> p99 latency of `payment-service` jumped at 14:30. What's in the logs at that time?

**What Claude does:**
1. `vm_query_range` on p99 latency for the 14:00-15:00 window — confirms the anomaly.
2. `vl_query` with `start=14:25, end=14:35`, `logsql='_stream:{service="payment-service"}'`, `mode=patterns`.
3. Compares the patterns before and after 14:30.

**What you get:** "Before 14:30 — 4 patterns, the usual ERRORs as a steady background. After 14:30 — a new pattern `connection reset by peer downstream-db-replica-2` (1820 times). Looks like a DB replica dropped out."

---

## B.4. Comparison with a baseline from a week ago

**Prompt:**
> Compare the behavior of `checkout-api` today with the same time a week ago. What's different?

**What Claude does:**
1. `vm_query_range` for two windows, today and a week ago, `summarize=true` — gets p50/p95/p99/throughput.
2. `vl_query` in `patterns` mode for both periods.
3. A diff of the patterns: what appeared, what disappeared, what grew many times over.

**What you get:** "p99 today is 1240ms vs 380ms a week ago. A new pattern appeared: `slow query: SELECT … FROM orders WHERE customer_id=` (3200 times). Most likely a new feature without an index."

---

## B.5. Creating a postmortem with Claude

**Prompt:**
> Incident INC-42 lasted from 14:18 to 14:47, the cause was a regression in payment_service.process_refund. Put together a postmortem using our template and save it to the vault.

**What Claude does:**
1. `vm_query_range` for the incident window — collects metric values.
2. `vl_query patterns` — the top error patterns.
3. `am_active_alerts` — which alerts fired during the window.
4. `obsidian_search("postmortem template")` — finds your template.
5. `obsidian_append_finding(title="Outage payment-service 2026-05-18", folder="postmortems", tags=["postmortem", "payment-service"])` — writes the result.

**What you get:** a ready file at `postmortems/2026-05-18-outage-payment-service.md` with a TL;DR, timeline, root cause and action items. All that is left is to review and commit it.

---

## B.6. Capacity / SLO check

**Prompt:**
> Top 10 services by growth of the 95th percentile of CPU over the week. Where are we approaching the limits?

**What Claude does:**
1. `vm_label_values("__name__", match='{name=~"container_cpu.*"}')` — metric discovery.
2. `vm_query_range` with PromQL like `topk(10, …)`, a 7-day window, a 1h step, `summarize=true`.
3. `obsidian_search("CPU limits services")` — in case there is a document with historical thresholds.

**What you get:** a list of 10 services with the p95 CPU delta and, for each, how far it is from the limit in the service description.

---

## B.7. Updating a runbook

**Prompt:**
> I just finished an incident: on `auth-service` the `HighLatency` alert always means the expired JWT cache case. Update the runbook.

**What Claude does:**
1. `obsidian_search("HighLatency auth")` — finds the existing runbook.
2. `obsidian_read_note(...)` — reads the current version.
3. `obsidian_append_finding(...)` or (if allow_writes=false) produces a text diff to apply manually.

**What you get:** an updated runbook with a new section on the JWT cache that will help the next on-call engineer.

---

## B.8. Discovery — "what is anything even called here"

**Prompt:**
> Which of our services write to `payment*`? What do we know about them?

**What Claude does:**
1. `vm_label_values(label="job", match='{job=~"payment.*"}')` — the list of services.
2. For each: `obsidian_search("<service-name>")` — what the vault knows about it.
3. A brief summary.

**What you get:** an inventory of the payment stack in 10 seconds, without digging through Confluence.

---

## B.9. Suspecting a problem before anything fires

**Prompt:**
> Subjective feeling: payments are getting a bit sluggish, but no alert is firing yet. Check it.

**What Claude does:**
1. `vm_query_range` p95/p99 latency of `payment-service` over the last hour, 1 min step, `summarize=true`.
2. Comparison with the usual baseline (from the vault or vm_query for a week ago).
3. `vl_query patterns` for the last 10 minutes.

**What you get:** "Yes, p99 is up 40% from normal, but still below the SLO. +1 new pattern in the logs. Worth watching for another 10 minutes."

---

## B.10. Eat-your-own-dogfood — what the MCP server knows about itself

**Prompt:**
> Show what the MCP server cost us this week. How many calls, which are the most expensive, are there any anomalies?

**What Claude does:**
1. `vm_query_range` for the MCP server's own metrics (`mcp_tool_calls_total`, `mcp_tokens_estimated_total`).
2. `vl_query patterns` over the server's own audit log.

**What you get:** a token usage report broken down by tools and users. The report is local: user names in it remain real.

---

## Pro tips

- **Teach Claude to call `obsidian_search` first** — add a rule to the MCP server's system prompt: "Before going to VM/VL/AM, always check the vault with obsidian_search first". 5-10x savings on a typical investigation.
- **Don't load Claude with philosophy** — be specific: "top 10 errors", "compare with a week ago", "find the pattern". A vague "what's going on" costs 5x more tokens.
- **Record findings**. After every non-standard investigation, ask Claude to run `obsidian_append_finding`. In half a year the vault becomes a collective brain, and the cost of later investigations drops.
- **Write runbooks in one format** (frontmatter + sections). Then Claude finds them deterministically and fast.
- **Control time windows**. Not "look at the logs" but "logs for 14:25-14:35". That is both more precise and 10-100x cheaper.

See also: [obsidian.md](./obsidian.md) — how the knowledge base is organized and note templates.
