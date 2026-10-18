**English** · [Русский](ru/new-job.md)

# Moving to a new job

Everything that depends on the organization lives in one config and in your knowledge base. The harness moves over
in an evening.

## What to take and what to leave

| Take | Leave |
|---|---|
| This repository (your fork on GitHub) | The previous job's knowledge base — it is the company's knowledge |
| Your skill and sre-toolbox changes made in the fork | The company's team templates, tokens, `mcp/sre-toolbox/config.yaml` |
| Habits: task journals, kb-compile, retros | Agent memory (`~/.claude/…/memory`) with facts about the previous infrastructure |

## Checklist

**1. Machine** (15 minutes)

```bash
python3 --version                    # 3.11+
git clone https://github.com/<you>/agent-harness ~/Projects/agent-harness
cd ~/Projects/agent-harness
```

Install Claude Code and/or Codex.

**2. Config** (10 minutes)

```bash
./harness init
```

You need to know: the organization's short name, where the knowledge base and the chats folder will be, the task key
prefixes in the tracker (`PLAT`, `SRE`…), the project and issue type for new tasks, your tracker login, the tracker,
wiki and chat URLs, and the alert channels. Whatever you don't know, leave as the example and fix later in
`~/.config/agent-harness/config.toml`.

**3. Install** (5 minutes)

```bash
./harness install --dry-run
./harness install
./harness doctor
```

A new knowledge base is created from the template. In Codex: `/hooks` → trust.

**4. Glossary** (30 minutes, the most valuable step)

In `<kb_root>/navigation/glossary.md` add the new company's services and their internal names, the way your
colleagues call them. Remove the `payments` example and the `services/Payments.md` hub, and create hubs for the 3–5
main services.

**5. MCP servers** (depends on the company)

Run `./harness mcp`, then in `mcp/sre-toolbox/config.yaml` fill in the new company's system URLs (tracker, wiki,
chat, metrics, logs, git hosting) and tokens following its `docs/install.md`; leave everything that doesn't exist
turned off. Don't enable writes to systems until you're comfortable. `./harness mcp --register` connects it to the
agents. If company policy requires other MCP servers, see the capability table in [mcp.md](mcp.md).

**6. Agent permissions** (15 minutes)

In `~/.claude/settings.json` (`permissions`) allow reads (`kubectl get`, `terraform plan`, `argocd app diff`…) and put
write commands into `ask`. If cloud access uses keys, make a wrapper that takes them from Keychain (see
[security.md](security.md)).

**7. Team templates** (as needed)

`team-skills/` holds starting points. Before your first postmortem or sprint report, fill in the skill's
`defaults.yaml`: wiki space, tracker fields, labels, page structure matching what your team uses. If the company has
its own templates, build a skill from them in a private company repository, not in your public fork.

**8. First week**

- Every alert investigation becomes a document in the base. After a week the agent has context.
- On Friday, run `kb-compile`.
- At the end of a large task, run `/retro`: which rules got in the way, what was missing.
- Before publishing changes to your fork, run `python3 scripts/check_sanitized.py` with the new denylist.

## If the company forbids cloud models

The harness does not depend on a specific model, but it is designed for Claude Code and Codex. If only internal
models are allowed, the rules, the knowledge base, `kb.py`, `kb_mcp.py` and journals work with any agent that reads
`AGENTS.md` and supports MCP; the hooks will have to be adapted to its event format.
