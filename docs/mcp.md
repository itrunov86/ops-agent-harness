**English** · [Русский](ru/mcp.md)

# MCP: which capabilities are needed and how to cover them

Skills describe a **capability** ("get a tracker issue") and name a tool only as an example (`jira_get_issue`). That
way they work with any set of MCP servers. Every step has a fallback — a CLI or `kb.py` — so a missing server narrows
what you can do but does not break the skill.

Two servers are included:

- **`mcp/sre-toolbox`** — integrations for an on-call SRE: Alertmanager, VictoriaMetrics, VictoriaLogs, Jira,
  Confluence, GitLab, Mattermost, Grafana and the knowledge base (`kb_search`, `kb_list`, `obsidian_*`). Responses are
  aggregated (log patterns, metric summaries); writes to every system are off by default and are enabled in
  `config.yaml`. Setup: `./harness mcp`; registration: `./harness mcp --register`; details in
  [mcp/sre-toolbox/README.md](../mcp/sre-toolbox/README.md).
- **`tools/kb_mcp.py`** — knowledge-base search only, no dependencies.

`mcp.hub` in the config is the name of your main integrations server (`sre-toolbox` by default): `kb-scout` denies
its write tools by the pattern `mcp__<hub>__<tool>`. If your integrations are spread across several servers, add their
write tools to `disallowedTools` of the `agents/claude/kb-scout.md` agent (in the repository) and reinstall.

## Capabilities

| Capability | Needed by | Example tools | Without MCP |
|---|---|---|---|
| Knowledge base search | all | `kb_search`, `kb_list` — **included in the harness** (`tools/kb_mcp.py`) | `kb.py search` |
| Tracker: read, find, create, comment, transition | request-triage, jira-planning-*, postmortem, sprint-report, contractor-report | `jira_get_issue`, `jira_search`, `jira_create_issue`, `jira_add_comment` | web UI, `jira` CLI |
| Wiki: find, read, create, update a page | duty-notes, postmortem, quarterly-planning, sprint-report | `confluence_search`, `confluence_get_page`, `confluence_create_page` | web UI |
| Chat: thread by link, channel posts, search | request-triage, mattermost-alerts-digest | `mm_resolve_permalink`, `mm_get_thread`, `mm_list_channel_posts` | copy the thread text into the chat |
| Alerts: active, silences | request-triage, observability-triage | `am_active_alerts`, `am_silences` | `amtool alert query` |
| Metrics: instant/range queries with aggregation | observability-triage, request-triage | `vm_query`, `vm_query_range`, `query_range` | `curl /api/v1/query_range`, Grafana |
| Logs: query grouped into patterns | observability-triage, kubernetes-runtime-triage | `vl_query`, `loki_query` | `kubectl logs`, LogsQL/LogQL in the UI |
| Dashboards and alert rules | observability-triage | `grafana_search`, `grafana_get_dashboard` | Grafana UI |
| Git hosting: MRs, files, search | gitlab-ci-review, request-triage | `gitlab_get_mr`, `gitlab_get_file`, `gitlab_search` | `glab`, `git` |
| Read-only IaC/GitOps | terraform-terragrunt-review, helm-argocd-gitops, vault-ops | `terraform_plan_summary`, `argocd_app_diff`, `helm_template_summary`, `vault_policy_read` | `terraform plan`, `argocd app diff`, `helm template`, `vault policy read` |
| Library documentation | versioned-docs | Context7 `resolve-library-id`, `query-docs` | the official website |

## If your systems are not in sre-toolbox

Almost every popular system has public servers for these capabilities: Atlassian (Jira/Confluence), GitLab, Grafana,
VictoriaMetrics, Prometheus, Kubernetes, Context7. Choose servers that:

- work with your credentials locally (tokens in Keychain or the server's config, not in the prompt);
- can aggregate (a metric summary instead of raw points, log patterns instead of thousands of lines) — this saves
  context;
- separate reads from writes, so writes can be turned off or denied to a subagent.

A new system is easiest to add as a module in `mcp/sre-toolbox/tools/`, following the neighbouring ones: unified
authentication, a shared "write gate" and response aggregation are already there.

## Knowledge base search as MCP

```bash
claude mcp add --scope user kb -- python3 -I ~/Projects/ops-agent-harness/tools/kb_mcp.py
```

```toml
# ~/.codex/config.toml
[mcp_servers.kb]
command = "python3"
args = ["-I", "/full/path/agent-harness/tools/kb_mcp.py"]
```

`./harness doctor` shows whether it is connected. The server is read-only.

## Proxy

If your network has a corporate HTTP proxy, MCP servers and agents may send internal traffic through it too — then
requests to internal hosts fail. Add internal domains to `NO_PROXY` in the form `.corp.example.com` (with a leading
dot, not `*.corp.example.com`: not every client understands the asterisk form, git over HTTPS among them).
