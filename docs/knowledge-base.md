**English** · [Русский](ru/knowledge-base.md)

# Knowledge base

A single git repository (`paths.kb_root`) that also opens in Obsidian as a vault. `harness install` creates it from
`templates/kb/` if the folder does not exist. Rules for agents are in `AGENTS.md` at the root of the base.

## Structure

| Folder | Contents |
|---|---|
| `alerts/` | Alert investigations (RCA) |
| `duty/` | Requests and on-call investigations |
| `incidents/` | Incidents |
| `tasks/<KEY>-<slug>/` | A task's plans, ADRs, evidence and `handoff.md` journal |
| `decisions/` | Accepted decisions (ADRs), valid until superseded |
| `reference/` | Durable reference: where a config lives, how a route works |
| `findings/` | Short findings agents record along the way |
| `services/` | Service hubs: "State" and a list of all documents |
| `tickets/` | Task hubs |
| `navigation/` | Glossary, golden questions, questions for `agent_bench` |
| `exports/` | Exports from other wikis: context, not truth; search skips them unless `--all` is given |

A document starts with frontmatter (`type`, `date`, `tickets`, `services`, `summary`, `lifecycle`), followed by a
3–5 line TL;DR. Format and rules are in the base's `AGENTS.md`.

## Search

```bash
python3 <harness>/tools/kb.py search "registry 504 timeout"
python3 <harness>/tools/kb.py search --service payments --since 2026-01-01 "timeout"
python3 <harness>/tools/kb.py list --ticket OPS-1234
```

- BM25 over document sections, Russian and English stemming (таймаут/таймаута/таймауты, timeout/timeouts count as
  one word), synonyms from `navigation/glossary.md`, extra weight for headings, `summary` and task keys.
- Returns up to 6 documents with the matching section and a **line range** — the agent reads only those lines
  (`sed -n 'A,Bp' <path>`), not the whole file.
- `historical` documents describe the past: the agent confirms the current state live before asserting it.
- The same over MCP: the `kb_search` and `kb_list` tools of the `tools/kb_mcp.py` server.

Embeddings are deliberately not used: on a base of a few hundred documents they gave no gain over BM25 with synonyms
and were an order of magnitude slower.

## Glossary

`navigation/glossary.md`: one line per entry, `- canonical: synonym, synonym`. The canonical name is the lowercase
service name; it is what goes into `services:` and `--service`. Add your services and their internal names — this is
the main lever for search quality. Do not add overly generic words ("metrics", "logs"): they would tag half the base.

## Hubs

`services/<Name>.md` and `tickets/<KEY>.md` with a `hub_match` field (a regex). `build_hubs.py` finds documents where
the regex occurs in the title, file name, tags, `services`/`tickets` fields or `[[…]]` links, and rewrites the list
between `<!-- hub:notes -->` and `<!-- /hub:notes -->`. The rest of the hub text is yours.

The "Состояние на <date>" (State as of <date>) section is a snapshot drawn from the notes: what is currently true about the service, each
item with a date and a link to its source. It is updated by the `kb-compile` skill.

## `kb-compile` — once a week

Notes and journals accumulate on their own, but the "State" in hubs does not update itself. `kb-compile`:

1. finds documents and task journals that appeared since the previous pass;
2. rewrites the "State" of the affected hubs, removing what has been disproved;
3. marks replaced documents with `lifecycle: superseded` + `superseded_by`;
4. creates a hub for a topic referenced by three or more documents;
5. moves accepted decisions and durable reference into `decisions/` and `reference/`;
6. commits only its own changes.

Unfinished tasks are not a problem: their state goes into the hub as interim. Run it once a week and after major
events (a migration, an incident, closing a large task).

## Checks

```bash
python3 <harness>/tools/kb.py lint    # frontmatter, types, dates, superseded_by, navigation links
python3 <harness>/tools/kb.py eval    # golden questions: hit@3 ≥ 80%
```

Golden questions live in `navigation/golden-questions.tsv`: `query<TAB>regex of the expected path`. When search
misses on a real question, add it here — that shows whether things got worse. Questions written by the documents'
author inflate the score: add the phrasings your colleagues actually use.

## Git

Documents are committed directly to `main` with the task key in the message: a branch per ticket would keep documents
out of `main` for months. Agents commit only their own files; whatever they leave uncommitted is committed by the
`Stop` hook ([hooks.md](hooks.md)). A remote (GitLab/GitHub) is optional; the base is local — push it if you want to
share it with your team.
