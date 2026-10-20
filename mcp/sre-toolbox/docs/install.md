**English** · [Русский](ru/install.md)

# Local installation and running the MCP server

← [Back to README](../README.md)

A document for developers: bring up `sre-toolbox` from agent-harness on your laptop, check the connection to
Jira/Confluence/Obsidian, and register the server in Claude Code and Codex.

For production mode (systemd, token rotation, hardening), see [deployment.md](./deployment.md). Which
MCP capabilities the harness skills need — [../../../docs/mcp.md](../../../docs/mcp.md).

---

## 1. Requirements

- macOS / Linux.
- Python **3.10+** (the code uses `X | None`, PEP 604).
- A clone of agent-harness (below: `~/Projects/ops-agent-harness`).
- A Personal Access Token for each system you connect (see step 3).

---

## 2. Preparing the environment

The venv lives inside the server directory (`mcp/sre-toolbox/.venv`, which is in `.gitignore`):

```bash
cd ~/Projects/ops-agent-harness/mcp/sre-toolbox
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

---

## 3. Secrets

Tokens are stored **only locally** and never end up in the repository. Three options:

1. **`.env` next to `server.py`** — the server loads it itself; values are substituted into `config.yaml` through
   `${VAR}`:

   ```bash
   cp .env.example .env    # .env is in .gitignore
   ```

2. **Environment / Keychain** — the launcher (or the `env` block of the MCP registration) exports the variables from
   Keychain before startup, and `config.yaml` references them through `${VAR}`.
3. **Directly in `config.yaml`** (it is in `.gitignore`; keep its mode at `0600`). This is what
   `scripts/set_grafana_token.py` does: `pbpaste | .venv/bin/python scripts/set_grafana_token.py` checks the Grafana
   token and writes it into `grafana.auth.bearer_token`.

How to get a PAT in Jira Server / Data Center: avatar → **Profile** → **Personal Access Tokens** → **Create token**.
Confluence, GitLab, Mattermost and Grafana each have their own tokens (see the comments in `.env.example`).

---

## 4. Config — `config.yaml`

```bash
cp config.example.yaml config.yaml   # config.yaml is in .gitignore
```

In the template every `allow_writes` is `false` — the server only reads. To let, for example, the `tracker-story`
skill create issues, enable writes selectively and narrow the allowlist:

```yaml
jira:
  url: "https://jira.example.com"     # your instance, no trailing slash
  auth:
    bearer_token: "${JIRA_PAT}"
  allow_writes: true                  # ON: allow creating/changing issues
  allow_projects:
    - "OPS"                           # allowlist of project keys

obsidian:
  vault_path: "~/Documents/Obsidian/SRE"
  # kb.py for kb_search/kb_list; default is ../../tools/kb.py of this repository
  # kb_tool: "~/Projects/ops-agent-harness/tools/kb.py"
  allow_writes: true                  # if the agent should write findings

server:
  audit_log_path: ""                  # disable the JSONL audit (or set a path)
```

`kb_search` / `kb_list` search the knowledge base whose root `kb.py` takes from the harness config
(`paths.kb_root` in `~/.config/agent-harness/config.toml` or the file from `AGENT_HARNESS_CONFIG`).

If the agent needs the team roster to assign issues, create `teams.md` following
[teams.example.md](../teams.example.md) (it is in `.gitignore`).

---

## 5. Obsidian folder

If you use a separate Obsidian vault, create it and its subfolders:

```bash
mkdir -p "$HOME/Documents/Obsidian/SRE"/{runbooks,postmortems,services,findings}
```

The path in `obsidian.vault_path` must match. If the vault is the harness knowledge base itself, set the same path
as `paths.kb_root`.

---

## 6. Verification

```bash
# contract tests (no network access)
.venv/bin/python -m unittest discover -s tests -v

# config is valid, tools get registered
.venv/bin/python -c "import server; print('ok, tools registered as', server.mcp.name)"

# interactively, through MCP Inspector
.venv/bin/mcp dev server.py
```

The server runs in **stdio** mode — JSON-RPC on stdin/stdout, logs to stderr. Calling a tool manually through the
agent (for example `jira_get_issue` with a known key) checks the live credentials.

---

## 7. Register in Claude Code

Globally for the user:

```bash
claude mcp add --scope user sre-toolbox -- \
  ~/Projects/ops-agent-harness/mcp/sre-toolbox/.venv/bin/python \
  ~/Projects/ops-agent-harness/mcp/sre-toolbox/server.py
```

If `config.yaml` is not next to `server.py`, add `--env MCP_CONFIG=/full/path/config.yaml`.
For project scope there is an example [`.mcp.example.json`](../.mcp.example.json) (it also includes the optional
external VictoriaMetrics MCP).

## 8. Register in Codex

`~/.codex/config.toml`:

```toml
[mcp_servers.sre-toolbox]
command = "/full/path/agent-harness/mcp/sre-toolbox/.venv/bin/python"
args = ["/full/path/agent-harness/mcp/sre-toolbox/server.py"]
# env = { MCP_CONFIG = "/full/path/to/config.yaml" }
```

After registering, restart the client: `kb_*`, `jira_*`, `confluence_*`, `gitlab_*`, `mm_*`, `grafana_*`,
`obsidian_*`, `am_*`, `vm_*`, `vl_*` will appear. In the harness config (the `[mcp]` section, `hub = "sre-toolbox"`)
set the server name and run `./harness install` — `kb-scout` will be denied its write tools.

---

## 9. Troubleshooting

| Symptom | What to check |
|--|--|
| `config not found at ...` | `config.yaml` next to `server.py`, or set `MCP_CONFIG=/path/to/config.yaml`. |
| `jira не сконфигурирован в config.yaml` ("jira is not configured") | `jira.url` is not filled in or `jira.auth.bearer_token` is empty → check `.env`/the environment. |
| `запись в jira отключена` ("writing to jira is disabled") | `jira.allow_writes` is not `true`. |
| `проект X не в allow_projects` ("project X is not in allow_projects") | Add the project key to `jira.allow_projects` (an empty list = no restriction). |
| `kb.py не найден: ...` ("kb.py not found") | Set `obsidian.kb_tool` or check that `tools/kb.py` exists in the harness clone. |
| Internal hosts don't respond through the proxy | Add the domains to `NO_PROXY` in the `.corp.example.com` form (see [../../../docs/mcp.md](../../../docs/mcp.md)). |
| The IDE marks `httpx`/`mcp`/`dotenv` as unresolved | Select the `./.venv/bin/python` interpreter. |
