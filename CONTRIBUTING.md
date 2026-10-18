**English** · [Русский](CONTRIBUTING.ru.md)

# How the repository is organized and how to contribute

## Placeholders

The skills, agents and templates in this repository do not know a single concrete path, host, tracker project or
person. Everything that depends on the workplace is written as a `{{NAME}}` placeholder; `./harness install`
replaces them with values from `~/.config/agent-harness/config.toml` and puts the result in place.

| Placeholder | What it is | Example value |
|---|---|---|
| `{{HARNESS_HOME}}` | where this repository lives | `~/Projects/agent-harness` |
| `{{KB_ROOT}}` | the knowledge base (a Git repository that is also an Obsidian vault) | `~/work/docs` |
| `{{WORK_DIR}}` | the shared folder all chats are opened from | `~/work/chats` |
| `{{ORG_NAME}}` | short organization name | `Acme` |
| `{{TICKET_PREFIXES}}` | tracker key prefixes separated by `\|` | `OPS\|INC` |
| `{{TICKET_EXAMPLE}}` | example key | `OPS-1234` |
| `{{TRACKER_PROJECT}}` | project for new issues | `OPS` |
| `{{TRACKER_ISSUE_TYPE}}` | type of a new issue | `Task` |
| `{{TRACKER_ASSIGNEE}}` | default assignee (tracker login) | `jdoe` |
| `{{TRACKER_URL}}` | tracker address | `https://jira.example.com` |
| `{{WIKI_SPACE}}` | wiki space for articles and reviews | `OPS` |
| `{{CHAT_URL}}` | corporate chat address (thread links) | `https://chat.example.com` |
| `{{ALERT_CHANNELS}}` | alert channels, comma-separated | `alerts, infra-alerts` |
| `{{MCP_HUB}}` | name of the main integrations MCP server | `sre-toolbox` |

Rule for authors: a file that goes into the repository must not contain a single real organization name, host,
IP, cloud ID, login or task key. `scripts/check_sanitized.py` checks generic patterns (internal IPs, tokens,
private keys) and your personal denylist `.sanitize-denylist` (it is in `.gitignore`).

## MCP capabilities instead of tool names

Skills describe the capability they need and name a concrete tool only as an example: "get the tracker issue
(`jira_get_issue`)". The table of capabilities and which MCP servers provide them is in `docs/mcp.md`. If the user
has no such MCP server, every step has a fallback (CLI, `kb.py`).

## Language

Documentation is in English, with a Russian translation in `docs/ru/` and `*.ru.md`. Team skills are in Russian,
infrastructure skills are in English (as in the sources). Keep skill trigger phrases in the language the user
will type them in.

## Checks

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_sanitized.py
./harness doctor
```
