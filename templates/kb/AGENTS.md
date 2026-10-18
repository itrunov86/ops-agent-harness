# AGENTS.md

Rules for AI agents working in this knowledge base ({{ORG_NAME}}; Codex reads this file directly, Claude Code via
`CLAUDE.md`). The tools live in agent-harness: `{{HARNESS_HOME}}/tools/`.

## Finding things

1. Search: `python3 {{HARNESS_HOME}}/tools/kb.py search "<symptom | service | alert | ticket>"` (or the MCP
   tool `kb_search`). It returns up to six documents with the matching section and line range; read only those
   lines (`sed -n 'A,Bp' <path>`). Narrow with `--service`, `--ticket`, `--type`, `--lifecycle`, `--since`.
2. Browse: `python3 {{HARNESS_HOME}}/tools/kb.py list --service <name>`, `list --since <YYYY-MM-DD>`, `list --stats`.
3. Agent findings (`findings/`) are searched together with everything else. For a service or ticket, open its hub
   first: `services/<Name>.md` or `tickets/<KEY>.md` (state snapshot plus the list of every related document;
   refresh lists with `python3 {{HARNESS_HOME}}/tools/build_hubs.py`).
4. Task journals: `handoff.md` inside `tasks/<KEY>-<slug>/` (skill `handoff`). They often hold the freshest state of a
   service; `kb-compile` folds them into hubs.

Raw CSV/JSON/TXT is opened only through its `.summary.md` or with a concrete resource id.

When search misses a document that answers a real question, add that question to
`navigation/golden-questions.tsv` and keep `python3 {{HARNESS_HOME}}/tools/kb.py eval` at hit@3 ≥ 80%.

## Trust

- `lifecycle: historical` (RCAs, requests, plans, snapshots) describes the past: confirm current state
  live, read-only, before stating it. A `superseded` document names its replacement in `superseded_by`.
- `current` runbooks and references can still drift: compare their `date` with the live system.
- Exports from other wikis (`exports/`) are context, not truth, and are skipped by search unless `--all`.
- Documentation never carries secret values, JWT, kubeconfigs, tokens, private keys, passwords or
  customer data.

## Adding a document

This repo is also an Obsidian vault. Short notes made during a session go to `findings/`; a finished
investigation, plan, runbook or decision goes to the folders below.

1. Place it by kind: `alerts/` (alert RCA), `duty/` (request or on-call investigation), `incidents/`,
   `tasks/<KEY>-<slug>/` (plans, ADRs, evidence, journal), `decisions/` (ADR), `reference/` (stable facts:
   where a config lives, how a route works).
2. Start it with frontmatter, then a TL;DR of 3–5 lines, then sections with stable headings:

   ```yaml
   ---
   type: request          # rca | request | runbook | plan | decision | review | reference | snapshot | task
   date: 2026-01-31       # when the events happened or the state was captured
   tickets: [{{TICKET_EXAMPLE}}]
   services: [payments]   # canonical names from navigation/glossary.md
   status: "outcome in free text"
   summary: "Symptom → cause → fix, one or two sentences"
   lifecycle: historical  # optional: runbook/reference/decision default to current, the rest to historical
   ---
   ```

   Large raw evidence goes to a sibling file with a `<name>.summary.md` next to it.
3. The document is done when `python3 {{HARNESS_HOME}}/tools/kb.py lint` reports `OK`.
4. When a document replaces another, mark the old one `lifecycle: superseded` and
   `superseded_by: <path from the KB root>.md`.

## Git

Commit documentation straight to `main` with the ticket key in the subject (`{{TICKET_EXAMPLE}} document …`);
this repo has no task branches: a branch per ticket keeps documents out of `main` for weeks.
Stage only your own files (`git add <paths>`, never `git add -A`): several agents write here in parallel.
A `Stop` hook commits whatever files your chat changed here at the end of each reply (`<KEY> docs: <files>`), so
nothing is left uncommitted; commit yourself first when the change deserves its own message. It skips a file
another chat also edited in the last hour, or one that looks like it holds a secret, and tells the user.

## Responses

Keep the final answer short: what changed or was found, source files used, verification commands,
and any unresolved stale/duplicate/raw-doc risks.
