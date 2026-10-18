**English** · [Русский](ru/customizing.md)

# Customizing

Edit the **repository** (preferably your own fork), not the installed copies: the next `install` overwrites
`~/.agents/skills` and the rules.

## Your own skill

```text
skills/my-skill/
  SKILL.md              # required: frontmatter name + description, then the instructions
  agents/openai.yaml    # optional: metadata for Codex
  references/ templates/
```

```markdown
---
name: my-skill
description: "What it does and when to use it. Triggers — \"a user phrase\", \"another phrase\". What it is not — other-skill."
---

# my-skill

Steps, each with a "done when …" criterion. What to read, which tool to use (capability + example + fallback),
how to finish.
```

Tips:

- `description` is the only thing the agent uses to decide whether to load the skill: list real phrases and the
  boundaries with neighbouring skills.
- Values that depend on the job go in as placeholders `{{KB_ROOT}}`, `{{TICKET_EXAMPLE}}`… ([CONTRIBUTING.md](../CONTRIBUTING.md)).
- Write steps come with a draft and a confirmation.
- Before editing a skill, invoke the `writing-for-agents` skill — it has the rules for writing text for agents.

Install: `./harness install`. Check placeholders: `./harness render skills/my-skill/SKILL.md`.

A skill just for yourself on this machine: there is no point keeping it in `skills.exclude`; either put it in the
repository and install it, or keep it outside the repository directly in `~/.agents/skills/` (the harness won't touch
it: it has no `.harness-managed` marker).

## Agent rules

`templates/global/AGENTS.md` holds the shared rules, `templates/global/CLAUDE.md` the Claude Code additions. A rule
that the agent breaks mechanically (a command pattern, a path) is better enforced by a check (permissions in
`settings.json`, a hook, a lint) than by one more line in the rules: rules are for decisions, checks are for
mechanics.

## Hooks

The handler is `tools/agent_session.py` (`cmd_hook`). Add new behaviour there, with a test in
`tests/test_agent_session.py`. A hook must not fail or block: any error means a silent exit.

## Subagents

`agents/claude/*.md` (Claude Code frontmatter: `name`, `description`, `model`, `disallowedTools`) and
`agents/codex/*.toml`. The models in the files are examples. A new Claude Code agent is visible only in sessions
started after it was installed.

## Checking changes

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_sanitized.py
./harness install --dry-run
```

Whether a change helped in practice: [evaluation.md](evaluation.md).
