**English** · [Русский](REQUIREMENTS.ru.md)

# Repository requirements

These rules apply to every agent session that changes `mcp/sre-toolbox`.

## Git

- Commits and MRs follow the agent-harness rules ([CONTRIBUTING.md](../../CONTRIBUTING.md)); `config.yaml`, `.env`, `teams.md`, `certs/` never go into git.
- Before committing: `python3 scripts/check_sanitized.py` from the harness root — no organization names, no internal hosts.

## Structure

- Team skills live in agent-harness `../../team-skills/`, not here.
- Tools live in `tools/` — one file per integration. Each exports `register(mcp, cfg, client_factory, redactor, audit_fn)`.
- A new tool for an existing integration goes into `tools/X.py` inside `register()`.
- A new integration: a config block + `_client_X` in `server.py` + `tools/X.py` + the register call.

## Code

- Jira/Confluence bodies are always **wiki markup** (`h1.`, `*bold*`, `*` lists, `||` tables), not markdown.
- Pass every tool response through `redactor.scrub_any(...)` before returning it.
- `print` to stdout is forbidden — it breaks the stdio protocol. Log through `logging`.

## Knowledge base (Obsidian)

- Before expensive analysis (logs/metrics/prod) — `obsidian_search` first.
- After a non-trivial investigation — `obsidian_append_finding` with `related_notes` for `[[wikilinks]]`.
- Skills that produce knowledge (`postmortem` and others) must include a step that writes to the vault.

## Documentation

- When the architecture changes, update `AGENTS.md`, `README.md`, `docs/architecture.md`.
- Mentions of removed features (Redis cache, Postgres audit) are removed from all files.
