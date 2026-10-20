**English** · [Русский](README.ru.md)

# sre-toolbox — integrations MCP server

Part of [agent-harness](../../README.md): a "hub" MCP server that gives the agent (Claude Code, Codex) access to the
observability stack and the working tools of a DevOps team: **Alertmanager**, **VictoriaMetrics**, **VictoriaLogs**,
**Jira**, **Confluence**, **GitLab**, **Mattermost**, **Grafana**, a knowledge base through `kb.py`, and a local
**Obsidian** vault. It is meant for on-call SREs: fast alert triage, correlating metrics and logs, first hypotheses
during incidents. Which MCP capabilities the harness skills need and how this server covers them —
[../../docs/mcp.md](../../docs/mcp.md); its name goes into `mcp.hub` in the harness config.

Authors: itrunov86 and Сергей Клецов (Sergey Kletsov).

---

## Documentation

| Section | What it covers |
|--------|-------|
| [docs/architecture.md](./docs/architecture.md) | How it works at a high level |
| [docs/tools.md](./docs/tools.md) | Reference for all tools (parameters, responses) |
| [docs/victoriametrics-mcp.md](./docs/victoriametrics-mcp.md) | The optional external VictoriaMetrics MCP and query rules |
| [docs/security.md](./docs/security.md) | What goes to the model provider — 8 layers of protection, checklist |
| [docs/token-economy.md](./docs/token-economy.md) | Saving tokens — techniques and architecture |
| [docs/obsidian.md](./docs/obsidian.md) | Knowledge base through an Obsidian vault and `kb.py` |
| [docs/install.md](./docs/install.md) | Local installation: venv, config, registration, smoke test |
| [docs/deployment.md](./docs/deployment.md) | Production: systemd, hardening |
| [docs/examples.md](./docs/examples.md) | 10 practical scenarios |

---

## Directory contents

| File / folder | Purpose |
|------|-----------|
| `server.py` | Entry point: config, clients, shared helpers, module registration |
| `tools/` | Tools, one file per integration |
| `tests/` | Routing contract tests (VM, VictoriaLogs, Alertmanager) |
| `scripts/set_grafana_token.py` | Check a Grafana token and write it into `config.yaml` |
| `config.example.yaml` | Config template (everything read-only) — copy it to `config.yaml` |
| `config.yaml`, `.env`, `teams.md` | Local files with addresses and secrets (in `.gitignore`) |
| `teams.example.md` | Format of the team description used for assigning tasks |
| `.mcp.example.json` | Example project-scope registration (with the optional VictoriaMetrics MCP) |
| `AGENTS.md`, `REQUIREMENTS.md` | Notes and rules for developing the server |

The team skills that run on top of these tools live in [`../../team-skills/`](../../team-skills/).

---

## Available tools

| Category | Tool | Purpose |
|-----------|------|-----------|
| Alerts | `am_active_alerts` | Active alerts from Alertmanager |
| Alerts | `am_silences` | Active silences |
| Metrics | `vm_query` | Instant PromQL |
| Metrics | `vm_query_range` | Range PromQL (aggregates by default) |
| Metrics | `vm_label_values` | Label value discovery |
| Logs | `vl_query` | LogsQL with `patterns` mode |
| Logs | `vl_streams` | List of streams |
| Knowledge base | `kb_search` | Knowledge base search (`kb.py`): sections and line ranges |
| Knowledge base | `kb_list` | Knowledge base catalog with filters |
| Knowledge base | `obsidian_search` | Vault search |
| Knowledge base | `obsidian_read_note` | Read a specific note |
| Knowledge base | `obsidian_append_finding` | Write a note with `[[wikilinks]]` |
| Jira | `jira_get_issue` | Get an issue by key |
| Jira | `jira_search` | Search issues with JQL |
| Jira | `jira_create_issue` | Create an issue (allow_writes) |
| Jira | `jira_update_issue` | Update issue fields (allow_writes) |
| Jira | `jira_transition_issue` | Change status (allow_writes) |
| Jira | `jira_add_comment` | Add a comment (allow_writes) |
| Jira | `jira_set_epic` | Link an issue to an epic (allow_writes) |
| Jira | `jira_list_projects` | List projects |
| Jira | `jira_list_boards` | List Agile boards |
| Jira | `jira_list_sprints` | List a board's sprints |
| Jira | `jira_sprint_issues` | Issues in a sprint |
| Confluence | `confluence_get_page` | Page by id or (space, title) |
| Confluence | `confluence_search` | CQL page search |
| Confluence | `confluence_get_page_children` | Child pages |
| Confluence | `confluence_get_bookmark` | Page from a named bookmark |
| Confluence | `confluence_create_page` | Create a page (allow_writes) |
| Confluence | `confluence_update_page` | Update a page (allow_writes) |
| GitLab | `gitlab_list_projects` | List projects |
| GitLab | `gitlab_get_project` | Project details |
| GitLab | `gitlab_list_mrs` | List MRs |
| GitLab | `gitlab_get_mr` | MR with diff/comments |
| GitLab | `gitlab_get_file` | File from a repository |
| GitLab | `gitlab_search` | Search code/commits |
| GitLab | `gitlab_create_mr_note` | Comment on an MR (allow_writes) |
| Mattermost | `mm_list_teams` | List teams |
| Mattermost | `mm_list_channels` | A team's channels |
| Mattermost | `mm_list_channel_posts` | A channel's posts |
| Mattermost | `mm_get_post` | Post by id |
| Mattermost | `mm_get_thread` | Thread |
| Mattermost | `mm_search_posts` | Search posts |
| Mattermost | `mm_resolve_permalink` | Permalink → content |
| Mattermost | `mm_create_post` | Send a message (allow_writes) |
| Grafana | `grafana_search` | Search dashboards |
| Grafana | `grafana_get_dashboard` | Dashboard by uid |
| Grafana | `grafana_list_datasources` | List data sources |
| Grafana | `grafana_get_annotations` | Annotations |
| Grafana | `grafana_list_alert_rules` | List alert rules |

Metrics and logs are read directly from VictoriaMetrics/VictoriaLogs; there is a single Grafana. `vm_*` look into
all tenants at once (the cluster is the `vm_account_id` label), `vl_*` into one tenant from a server-side map
(`tenant`), and `am_*` pick an Alertmanager with the `instance` parameter. Range/step/response limits are in the
[tools reference](./docs/tools.md).

If a separate `victoriametrics` MCP is connected alongside (example: `.mcp.example.json`),
the order is: `mcp__victoriametrics__query` / `mcp__victoriametrics__query_range`,
then the local `vm_*` tools as a fallback. Full rules are in
[docs/victoriametrics-mcp.md](./docs/victoriametrics-mcp.md).

Details are in [docs/tools.md](./docs/tools.md).

---

## Quick start

In brief; the full version is [docs/install.md](./docs/install.md).

### 1. Installation

```bash
cd ~/Projects/ops-agent-harness/mcp/sre-toolbox
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. Configuration

```bash
cp config.example.yaml config.yaml   # config.yaml is in .gitignore
```

Fill in the `url` of the integrations you need (blocks you don't need can stay empty). All `allow_writes` in the
template are off — enable writes selectively, together with an allowlist (`allow_projects`, `allow_spaces`,
`allow_channels`).

Tokens live **only** locally: in `config.yaml`, in `.env` next to `server.py` (substituted through `${VAR}`, see
`.env.example`), or in the environment/Keychain, from where your launcher passes them. `scripts/set_grafana_token.py`
writes the Grafana token straight into `config.yaml` (mode `0600`). Tokens never end up in the repository.

Minimal `config.yaml` example:

```yaml
server:
  name: "sre-toolbox"
  audit_log_path: ""          # or a path to audit.jsonl

alertmanager:
  instances:
    main: {url: "https://am.example.com"}
  auth:
    bearer_token: "${AM_BEARER_TOKEN}"

victoriametrics:
  url: "https://vm.example.com/select/multitenant/prometheus"
  auth:
    bearer_token: "${VM_BEARER_TOKEN}"

victorialogs:
  url: "https://vlogs.example.com"
  auth:
    bearer_token: "${VL_BEARER_TOKEN}"
  default_tenant: "prod"
  tenants: {prod: 0}

grafana:
  url: "https://grafana.example.com"
  auth:
    bearer_token: "${GRAFANA_TOKEN}"

# Knowledge base: kb.py from agent-harness (default ../../tools/kb.py) + Obsidian vault
obsidian:
  vault_path: "~/Documents/Obsidian/SRE"
  # kb_tool: "~/Projects/ops-agent-harness/tools/kb.py"
  allow_writes: false

jira:
  url: "https://jira.example.com"
  auth:
    bearer_token: "${JIRA_PAT}"
  allow_writes: false
  allow_projects: []          # e.g. ["OPS"]

confluence:
  url: "https://confluence.example.com"
  auth:
    bearer_token: "${CONFLUENCE_PAT}"
  allow_writes: false
```

> **Where to get a Jira/Confluence Server token.** Profile → `Personal Access Tokens` → `Create token`. Jira and
> Confluence tokens are separate.

### 3. Verification

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -c "import server; print('ok', server.mcp.name)"
# debugging with MCP Inspector:
.venv/bin/mcp dev server.py
```

### 4. Registration

Claude Code:

```bash
claude mcp add --scope user sre-toolbox -- \
  ~/Projects/ops-agent-harness/mcp/sre-toolbox/.venv/bin/python \
  ~/Projects/ops-agent-harness/mcp/sre-toolbox/server.py
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.sre-toolbox]
command = "/full/path/agent-harness/mcp/sre-toolbox/.venv/bin/python"
args = ["/full/path/agent-harness/mcp/sre-toolbox/server.py"]
# env = { MCP_CONFIG = "/full/path/to/config.yaml" }   # if the config is not next to server.py
```

Then set `hub = "sre-toolbox"` in the `[mcp]` section of `~/.config/agent-harness/config.toml` — `kb-scout` will be
denied its write tools. Systemd and hardening — [docs/deployment.md](./docs/deployment.md).

---

## Example dialogue

> **SRE:** what's on fire right now?
>
> **Claude:** *(calls `am_active_alerts(severity='critical')`)*
> There are 3 critical alerts right now: `HighErrorRate` on `checkout-api` (since 14:23),
> `DBConnectionPoolExhausted` on `payment-service` (since 14:25), `HighLatency`
> on `auth-api` (since 14:31). Looks like a cascading failure; starting with checkout.

> **SRE:** dig into checkout.
>
> **Claude:** *(calls `kb_search("HighErrorRate checkout")`, then `vm_query_range`, `vl_query`)*
> Found the runbook — `runbooks/high-error-rate.md`. The metrics show the error rate
> jumped at 14:18 (there was a deploy `a3f1b2`). The logs have a new pattern
> `payment timeout after <N>ms` (2810 times). This looks like incident INC-42
> from March — I recommend a rollback.

Ten complete scenarios are in [docs/examples.md](./docs/examples.md).

---

## Extending

To add a tool to an existing integration, open the relevant `tools/X.py`
and add a function inside `register()`:

```python
@mcp.tool()
async def my_tool(arg1: str, arg2: int = 10) -> dict[str, Any]:
    """
    Short description for the model: what the tool does, when to call it.

    Args:
        arg1: what it is.
        arg2: what it is.
    """
    async with client_factory() as c:
        resp = await c.get(...)
    payload = redactor.scrub_any({"result": ...})
    audit_fn("my_tool", {"arg1": arg1}, len(json.dumps(payload)))
    return payload
```

To add a **new integration**: add a block to `config.yaml`, a `_client_X` in `server.py`,
a new file `tools/X.py` with a `register(mcp, cfg, client_factory, redactor, audit_fn)` function,
and a `tools.X.register(...)` call in `server.py`.

**Important:**
- The docstring and type hints are the contract with the model. The more precise they are, the better the agent
  (Claude Code or Codex) understands when to call the tool.
- Never use `print` (`stdout` is reserved for JSON-RPC). Log through `logging`.
- Run responses through `redactor.scrub_any(...)` before returning them.

---

## Key ideas

1. **The MCP server is a gateway, not a pass-through channel.** Every tool aggregates, filters and redacts data before it goes to the model.
2. **Protecting code is first of all minimizing context.** The decisive protection is sending 10 lines, not 10 thousand.
3. **Savings and security coincide.** The less you send, the cheaper and safer it is.
4. **A knowledge base in Obsidian** is the most powerful saving technique. A well-written 500-token runbook saves 10–50K tokens of diagnostics. See [docs/obsidian.md](./docs/obsidian.md).
