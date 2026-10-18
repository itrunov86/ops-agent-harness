**English** · [Русский](ru/security.md)

# Security — protecting code from Anthropic

← [Back to README](../README.md)

This section answers the question: **"we use cloud Claude — how do we make sure our code and logs don't leak to Anthropic?"**

---

## What Anthropic technically receives

When Claude calls a tool, the following happens:

1. Claude sends a request to the API: "call tool X with these parameters".
2. The API returns this request to your client.
3. The client executes the tool locally (through the MCP server).
4. The client sends the **tool result** back to the API as a message in the conversation.
5. Claude generates a response based on the whole conversation.

**This means**: the result of every tool — log fragments, code fragments, metrics — physically passes through Anthropic's infrastructure to generate the response. This is the basic nature of a cloud LLM, and there is no way around it while staying on a cloud model.

**What follows from this**: the goal is not "send nothing" but **"send the minimum, and whatever is sent must not be scary to lose"**.

---

## What Anthropic does NOT receive (when configured correctly)

- Direct access to your repositories, clusters, databases — no. Only through your tools.
- Contents of tools that were not called — no.
- Long-term storage of requests — no, if Zero Data Retention is enabled.
- Use of your data for training — no, this is a baseline API guarantee.

---

## Protection layers

Protection follows the defense-in-depth principle. Layers are sorted from most to least important.

### 1. Context minimization — the most powerful tool

If you send 500 lines, the risk is exactly 500 lines. If you send 5 lines, the risk is 5 lines. This works better than any contract.

Specific techniques:

- **Summaries instead of raw data.** For metrics — aggregates (min/max/p99), not points. For logs — patterns and counters, not lines.
- **Hard limits in every tool.** In our server: `vl_query` has a 500-line ceiling, `obsidian_read_note` a limit of 8000 characters, `vm_query_range` ≤120 points per series.
- **Routing without SSRF.** `vm_*` and `vl_*` go only to the `url` from the config; `vl_*` accept a tenant name from the server-side `victorialogs.tenants`, `am_*` a name from `alertmanager.instances`. URLs, credentials and tenant numbers outside the map are not accepted.
- **A separate VictoriaMetrics MCP is a separate trust boundary.** Responses from `mcp__victoriametrics__query*` do not pass through this `sre-toolbox`'s local `Redactor` and `audit`; so the agent must request only a narrow window and the minimum necessary aggregates/points. Do not put secrets, tokens or unnecessary high-cardinality labels into PromQL.
- **Only relevant fields.** Do not return the full Kubernetes pod object — return `{name, phase, restarts, ready}`.
- **No "return everything".** Any tool returns no more than needed for the specific answer.

### 2. Tokenization (aliasing)

Before sending to Claude, internal names are replaced with tokens:

```
payment-service           → service-A
auth-prod-eu              → service-B-eu
internal-billing-api.corp → api-X
customer_email            → field_001
```

The MCP server keeps the mapping (in-memory, for the duration of the session). Claude works perfectly well with anonymized names and solves the task. In the final answer to the user, the tokens are restored.

Effect: even if Anthropic had an API log leak (which won't happen, but let's imagine), this data would give no insight into the structure of your business.

### 3. Redaction (masking)

Regexes and DLP on every tool response, before it is returned to Claude:

- AWS access keys (`AKIA...`)
- SSH/PGP private keys
- JWT tokens
- Base URLs of internal systems (`*.corp`, `*.internal`)
- Email addresses (if not needed for the task)
- Card numbers, passport numbers, IBANs (for fintech/banks)
- Russian INN and SNILS numbers
- Customer IDs — replaced with hashes

Implementation: libraries like `presidio` or your own set of regexes plus rules. **Important**: redaction must fail closed — if a rule fires, the tool must return nothing; an error is better.

All rules are configured in `config.yaml` in the `redaction.patterns` section.

### 4. Code-specific protection

When a tool returns code or log fragments:

- Comments with potentially sensitive data are removed (TODOs mentioning customers, temporary configs, forgotten URLs).
- String literals longer than N characters in a fragment are replaced with `<STRING>`.
- Private package names in a fragment are tokenized.

Additionally: for critical repositories (payment logic, ML models) `search_code` can be disabled entirely, with access only to file names and function signatures.

### 5. Contractual protections from Anthropic

These must be stated explicitly in the contract:

- **Zero Data Retention (ZDR)**: requests are not stored after the response, not even for anti-abuse. Enabled in the enterprise plan.
- **No-training**: data is not used to train models. This is a baseline rule for the whole API.
- **Certifications**: SOC 2 Type II, ISO 27001, ISO 42001. For healthcare — BAA (HIPAA). For the EU — GDPR DPA.
- **Region pinning**: Bedrock lets you pin inference to a region (eu-central-1, for example).

### 6. Network protections

- **AWS Bedrock via PrivateLink**. Traffic from your VPC does not go out to the public internet. This is the strongest network control.
- **GCP Vertex AI with Private Service Connect** — the same on Google Cloud.
- **Direct Anthropic API through an egress proxy** with an allowlist for specific domains, mTLS, IP whitelist.

### 7. Egress proxy + DLP

A proxy (Envoy/Squid/commercial DLP) is placed between the MCP server and the Claude API:

- Allowlist only for the LLM endpoint.
- A DLP scanner checks every outgoing request once more — a second check on top of the redactor.
- Rate limit, volume anomalies.

### 8. Audit log

Every outgoing request is written to a SIEM (Splunk/Elastic):

- Who initiated it (the SRE engineer's Claude account).
- Which tool, with which parameters.
- What was returned (full text or its hash + length).
- What ended up being sent to the Claude API.

This is needed for after-the-fact investigations and for passing a compliance audit.

In our server, the audit log is written as JSONL to the `server.audit_log_path` path from the config.

---

## Checklist for security approval

Before a production rollout, the security team usually wants confirmation of each item:

- [ ] Contract with Anthropic with a ZDR clause.
- [ ] No-training confirmed in writing.
- [ ] Traffic goes through Bedrock PrivateLink (or Vertex PSC).
- [ ] Egress proxy with an allowlist installed and tested.
- [ ] DLP rules cover known secret and PII patterns.
- [ ] All tools have hard limits on response size.
- [ ] Redaction fails closed, covered by unit tests.
- [ ] Audit log in the SIEM with retention ≥ 1 year.
- [ ] Per-tool RBAC: not every employee has access to every tool.
- [ ] Regular red team review (every six months).
- [ ] Revocation plan: how quickly we can cut off Claude's access to a specific tool or the whole system.

---

## When cloud Claude is still not a fit

There are cases where even all of the above will not pass security review:

- Government information systems, critical information infrastructure, defense.
- R&D with patent-sensitive code.
- Regulated financial systems of a certain level.

In such cases the only way is a self-hosted LLM (Llama 3.x, Qwen, DeepSeek-Coder) on your own GPUs. The MCP architecture does not change; only the last step changes — where the request goes.

---

## Key idea

Cloud Claude security is not "we trust Anthropic", but **"we send only what is not scary to lose, over a network that physically does not go through the internet, under a contract that forbids storage, and we log every byte"**. Each of the four elements must be in place.
