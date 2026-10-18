**English** · [Русский](ru/configuration.md)

# Config

One file per machine: `~/.config/agent-harness/config.toml` (a different path — the `AGENT_HARNESS_CONFIG` variable).
A sample with every field — [`config.example.toml`](../config.example.toml). There are no secrets in the config, and there must not be.

After editing the config, run `./harness install`: values are substituted into skills and rules at install time.
The tools (`kb.py`, hooks) read the config on every run and need no reinstall.

## `[org]`

| Field | Default | Purpose |
|---|---|---|
| `name` | `Acme` | Organization name in the header of the agent rules |

## `[paths]`

| Field | Default | Purpose |
|---|---|---|
| `kb_root` | `~/kb` | Knowledge base: a Git repository and Obsidian vault. `kb.py` searches it; journals and auto-commit write to it |
| `work_dir` | `~/work` | The shared folder all chats are opened from. VS Code shows chat history per folder — one folder keeps the whole list |
| `code_root` | — | Where your work repositories live; needed by `agent_bench.py` |
| `reports_dir` | `~/work/reports` | Where `agent_bench.py` puts its results |
| `state_dir` | `~/.agents/state` | Internal: chat-to-journal bindings, auto-commit, context thresholds, install manifest |

## `[tracker]`

| Field | Default | Purpose |
|---|---|---|
| `prefixes` | `["OPS", "INC"]` | Task key prefixes. Hooks use them to find the task in a message, `kb.py` to find documents, auto-commit to get the key for the commit message |
| `example` | `<first prefix>-1234` | Example key in skills and rules |
| `project` | `OPS` | Where the agent creates an issue if there is no key |
| `issue_type` | `Task` | Type of that issue |
| `assignee` | — | Default assignee (tracker login) |
| `url` | — | Tracker address for links |

## `[wiki]`, `[chat]`, `[mcp]`

| Field | Purpose |
|---|---|
| `wiki.space` | Wiki space for on-call articles, postmortems, sprint reports |
| `chat.url` | Corporate chat address: skills parse thread links |
| `chat.alert_channels` | Alert channels for `mattermost-alerts-digest` and `request-triage` |
| `mcp.hub` | Name of the main integrations MCP server: skills and `kb-scout` refer to its tools as `mcp__<hub>__…` |

## `[agents]`

| Field | Default | Purpose |
|---|---|---|
| `claude` | `true` | Install skills (as symlinks), agents, rules and hooks for Claude Code |
| `codex` | `true` | The same for Codex |

## `[skills]`

| Field | Default | Purpose |
|---|---|---|
| `team` | `true` | Install team skills from `team-skills/` (postmortem, epics, sprint, wiki, contractor report) |
| `exclude` | `[]` | Names of skills you don't need, e.g. `["yandex-cloud-devops", "daily-report"]` |

## `[hooks]`

| Field | Default | Purpose |
|---|---|---|
| `handoff_thresholds` | `[50, 75]` | At which context usage (%) the hook asks to update the journal; at the last one it also suggests `/compact`. Overridden by the `AGENT_HANDOFF_THRESHOLDS=60,85` variable |
| `autocommit` | `true` | Commit the agent's edits in `kb_root` at the end of every response |
| `kb_context` | `true` | The `kb.py hook` hook: injects the list of documents for task keys found in the message |

## Placeholders

Which config field becomes which placeholder in the skills — see the table in [CONTRIBUTING.md](../CONTRIBUTING.md).
To see the result for any file: `./harness render <path>`.
