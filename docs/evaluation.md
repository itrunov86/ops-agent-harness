**English** · [Русский](ru/evaluation.md)

# How to check that a harness change helped

A change to the rules or a skill is easy to make and hard to judge by eye. There are two tools.

## Search quality: `kb.py eval`

`<kb_root>/navigation/golden-questions.tsv` — `query<TAB>regex of the expected path`. `kb.py eval` runs all the
questions and computes hit@1 and hit@3; below `--min-hit3` (0.8) it exits with code 1.

- Add a question every time search misses on a real question.
- Phrase it the way colleagues ask, not the way the document is titled: the author's own questions inflate the score
  several times over.
- Run it after changing the glossary, the weights or the document structure.

## Agent behaviour: `agent_bench.py`

An A/B run of agents on your questions about the knowledge base and code — read-only, live systems are forbidden.

```bash
python3 tools/agent_bench.py run --variants A,B --jobs 3          # Claude Code
python3 tools/agent_bench.py run --agent codex --ids 1,2,3
python3 tools/agent_bench.py report <results folder>
```

Questions are in `<kb_root>/navigation/agent-bench-tasks.json`:

```json
[{"id": 1, "kind": "rca", "q": "why was the registry returning 504 in January?", "facts": ["proxy-body-size", "OPS-12\\d\\d"]}]
```

`facts` are regexes for the key facts of a correct answer. Metrics: share of facts found, peak context of the main
agent, cost, time, steps. Built-in variants: A — the main agent searches by itself, B — search is delegated to
`kb-scout`. Your own variants: edit `run_one` (a different system prompt, a different tool set).

The loop that works:

1. Notice a problem (in `/retro` or in the journal's "Lessons" section).
2. Formulate a harness change: a rule, a skill, a hook, a tool.
3. Run the bench without and with the change on 5–10 questions.
4. Accept the change only if facts went up, or context/cost went down without losing facts.
5. Record the decision in the base's `decisions/` with the numbers.
