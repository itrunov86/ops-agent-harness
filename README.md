**English** · [Русский](README.ru.md)

# agent-harness

A harness for the **Claude Code** and **Codex** AI agents in DevOps/SRE work: shared safety rules, skills for
routine tasks, a searchable knowledge base, journals for long-running tasks, and hooks that keep the agent from
losing context. It installs with one command and moves to a new job by editing a single config file.

## What's inside

| Part | What it does |
|---|---|
| **Rules** (`templates/global/`) | Shared by both agents: remote systems are read-only, a write needs one explicit "yes", GitOps, secrets never leave the machine, a task key on every branch |
| **Skills** (`skills/`, `team-skills/`) | 23 playbooks: alert and request triage, Kubernetes/network/metrics triage, Terraform/Helm/CI/Vault review, postmortems, epics and tasks, sprint reports, task journals |
| **Knowledge base** (`templates/kb/`, `tools/kb.py`) | A Git repository and an Obsidian vault at the same time: BM25 search with a Russian stemmer and a glossary, service and task hubs, frontmatter checks |
| **sre-toolbox MCP server** (`mcp/sre-toolbox/`) | Alertmanager, VictoriaMetrics/Logs, Jira, Confluence, GitLab, Mattermost, Grafana and the knowledge base; responses are aggregated to fit the agent's context, writes are off by default and enabled by an allowlist |
| **kb MCP server** (`tools/kb_mcp.py`) | Only `kb_search` and `kb_list`, no dependencies — for when you don't need sre-toolbox |
| **Task journals** (`tools/agent_session.py`, the `handoff` skill) | Carry a long task's context across chats; a journal is bound to a chat by the task key and survives `/compact` |
| **Hooks** | Journal on startup and after compaction, reminders at 50/75% context, documents for task keys found in the prompt, knowledge-base auto-commit |
| **Subagents** (`agents/`) | `kb-scout` (read-only broad search); for Codex — `coder`, `reviewer`, `incident_worker` and the `task`/`incident` profiles |
| **Evaluation** (`tools/agent_bench.py`, `kb.py eval`) | A/B runs of agents on your own questions; search quality measured on "golden questions" |

## Quick start

```bash
git clone https://github.com/<you>/agent-harness ~/Projects/agent-harness
cd ~/Projects/agent-harness
./harness init               # asks for organization, paths, task prefixes, tracker
./harness install --dry-run  # shows what will be done
./harness install            # skills, agents, rules, hooks, knowledge base
./harness mcp --register     # optional: sre-toolbox for Claude Code and Codex
./harness doctor             # check
```

Then: in Codex, run `/hooks` once → trust the new hooks; put your systems' addresses into
`mcp/sre-toolbox/config.yaml`. Open chats from the `work_dir` folder set in the config. Details —
[docs/install.md](docs/install.md).

## How to use it

```text
triage this alert https://chat.example.com/team/pl/abc123
OPS-1234 add a bucket for logs, show terraform plan, don't apply
start a handoff                        ← the task won't fit into one chat
OPS-1234 continue                      ← next day, in a new chat
write a postmortem for INC-7
run kb-compile                         ← once a week: fresh findings into hubs
```

The full reference of prompts and scenarios is [docs/workflows.md](docs/workflows.md), the skill catalog is
[docs/skills.md](docs/skills.md).

## Documentation

Russian translations of all documents are in [docs/ru/](docs/ru/).

| Document | About |
|---|---|
| [concepts.md](docs/concepts.md) | What the harness consists of and how the parts connect |
| [install.md](docs/install.md) | Install, update, uninstall |
| [configuration.md](docs/configuration.md) | Every `config.toml` parameter |
| [workflows.md](docs/workflows.md) | Day-to-day work: chats, tasks, typical prompts |
| [skills.md](docs/skills.md) | Skill catalog: which one when, and how to invoke it |
| [handoff.md](docs/handoff.md) | Long-task journals and binding them to a chat |
| [knowledge-base.md](docs/knowledge-base.md) | Knowledge base layout, search, hubs, `kb-compile` |
| [hooks.md](docs/hooks.md) | What each hook does and where its state lives |
| [mcp.md](docs/mcp.md) | Which capabilities the skills need and which MCP servers provide them |
| [security.md](docs/security.md) | Security model: read by default, confirmations, secrets |
| [new-job.md](docs/new-job.md) | Checklist for moving to a new job |
| [customizing.md](docs/customizing.md) | Your own skills, editing the rules, placeholders |
| [evaluation.md](docs/evaluation.md) | How to check that a harness change actually helped |
| [troubleshooting.md](docs/troubleshooting.md) | Common problems and fixes |

## Requirements

- macOS or Linux, Python 3.11+, git.
- Claude Code and/or Codex CLI (or their VS Code extensions).
- For integrations — `mcp/sre-toolbox` (bundled) or your own MCP servers ([docs/mcp.md](docs/mcp.md)). The
  harness works without them: the knowledge base, journals, IaC review and rules do not depend on MCP.

## License

MIT — see [LICENSE](LICENSE). sre-toolbox authors: itrunov86 and Сергей Клецов (Sergey Kletsov). Third-party skills and their licenses — [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
How to contribute — [CONTRIBUTING.md](CONTRIBUTING.md).
