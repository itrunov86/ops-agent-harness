**English** · [Русский](ru/install.md)

# Install, update, uninstall

## Requirements

- macOS or Linux; Python 3.11+ (`python3 --version`), git.
- Claude Code and/or Codex — CLI or VS Code extension.
- Write access to `~/.agents`, `~/.claude`, `~/.codex`, `~/.config`.

## Installation

```bash
git clone https://github.com/itrunov86/ops-agent-harness ~/Projects/ops-agent-harness
cd ~/Projects/ops-agent-harness
./harness init
```

`init` asks for the main values (Enter keeps the example) and writes `~/.config/agent-harness/config.toml`. To skip
the questions: `./harness init --defaults`, then edit the file by hand. All parameters — [configuration.md](configuration.md).

```bash
./harness install --dry-run   # list of actions, nothing changes
./harness install
./harness doctor
```

What `install` does:

| Step | Where | What |
|---|---|---|
| Skills | `~/.agents/skills/<name>/` | a copy from `skills/` and `team-skills/` with placeholders filled in, marked `.harness-managed` |
| Skills for Claude | `~/.claude/skills/<name>` | symlink to the copy above |
| Rules | `~/.codex/AGENTS.md`, `~/.claude/CLAUDE.md` | from `templates/global/`; CLAUDE.md imports AGENTS.md |
| Subagents | `~/.claude/agents/`, `~/.codex/agents/` | `kb-scout`; for Codex also `coder`, `reviewer`, `incident_worker` |
| Codex profiles | `~/.codex/task.config.toml`, `incident.config.toml` | task and incident orchestrators |
| Hooks | `~/.claude/settings.json`, `~/.codex/hooks.json` | added to yours, yours are not removed |
| Knowledge base | `paths.kb_root` | if the folder doesn't exist: template from `templates/kb/`, `git init`, first commit |
| Folders | `paths.work_dir`, `paths.state_dir` | created |
| Manifest | `<state_dir>/harness-manifest.json` | what was installed — for `doctor` and `uninstall` |

### Files you already have

`install` does not overwrite anything you created outside the harness:

- your own `~/.codex/AGENTS.md` stays, and `AGENTS.md.harness-new` appears next to it — compare them and carry over what you need;
- your own skill with the same name is skipped;
- `install --force` replaces such files, saving them first to `~/.agents/backups/<timestamp>/`.

Before any edit to `settings.json` and `hooks.json`, a backup goes to the same place. An existing knowledge base is left untouched.

### After installation

1. **Codex:** run `/hooks` once and trust the new hooks — without this Codex will not run them.
2. **sre-toolbox MCP server:** `./harness mcp` creates `mcp/sre-toolbox/.venv`, installs dependencies and puts
   `config.yaml` in place from the example — fill in your systems' addresses and tokens following
   `mcp/sre-toolbox/docs/install.md`. `./harness mcp --register` connects it to Claude Code (`claude mcp add`) and
   Codex (`~/.codex/config.toml`), making a backup first. Without MCP, agents search the knowledge base via
   `python3 <harness>/tools/kb.py search`.
3. **Other MCP servers** — [mcp.md](mcp.md).
4. **Check:** open a new chat in `work_dir`, ask "what skills do you have?" and "search the knowledge base for payments".

## Updating

```bash
cd ~/Projects/ops-agent-harness
git pull
./harness install --dry-run && ./harness install
./harness doctor
```

`doctor` reports when installed skills lag behind the repository. Re-running `install` is safe: it updates what
the harness installed and does not duplicate hooks.

Make your own skill edits in the repository (or your fork), not in `~/.agents/skills` — the next `install` will
overwrite them there. How — [customizing.md](customizing.md).

## Uninstalling

```bash
./harness uninstall --dry-run
./harness uninstall
```

This removes the skills, symlinks, rules, agents and profiles installed by the harness, and its hooks from
`settings.json` and `hooks.json` (your hooks stay). The knowledge base, config and backups stay. To restore your
previous files — `~/.agents/backups/<timestamp>/`.

## Checking without installing

```bash
python3 -m unittest discover -s tests -v   # tests run on a temporary HOME, your settings are untouched
./harness render skills/handoff/SKILL.md     # what a skill looks like with your values
```
