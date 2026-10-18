**English** · [Русский](ru/troubleshooting.md)

# Troubleshooting

| Symptom | Cause and what to do |
|---|---|
| In a new chat the agent talks about the wrong task | The key is not at the start of the message, or the chat is bound to another task: `switch to OPS-…`. Bindings are in `<state_dir>/session-tasks.json` |
| The journal was not injected after "OPS-… continue" | The task has no journal (`ls <kb_root>/tasks/ \| grep OPS-…`) — "start a handoff". Or the prefix is not in `tracker.prefixes` |
| The journal is injected into every chat | The shared folder is bound to a task in `active-tasks.json` (old installation) — delete that entry |
| Old chats are not visible in VS Code | Chat history is per opened folder. Open the one the chat was started from (usually `work_dir`) |
| Codex does not run hooks | `/hooks` in Codex → trust; check `~/.codex/hooks.json` |
| Claude Code hooks do not fire | `/hooks`; `./harness doctor`; the harness path in the hook commands matches the current one (after moving the repository, run `./harness install`) |
| «Не закоммичены, их правит и другой чат» ("not committed, another chat is editing them too") | Wait until that chat finishes, then `git -C <kb_root> commit -m "<KEY> …" -- <file>` |
| «похоже на секрет внутри» ("looks like a secret inside") | Remove the value from the file; secrets are not stored in the base |
| `install` says «создан не harness» ("not created by harness") | Your own file with the same name. Compare it with `*.harness-new` and carry over what you need, or `install --force` (the old one is backed up) |
| `{{…}}` left in a skill | Unknown placeholder: `./harness doctor` shows where; add the field to the config/`harness_config.py` |
| `kb.py lint` complains about a navigation link | A backticked path in `AGENTS.md`/`navigation/*.md` points to a file that doesn't exist |
| Search does not find the obvious | Add synonyms to `navigation/glossary.md` and the question to `golden-questions.tsv`, run `kb.py eval` |
| MCP tools fail on internal addresses | The proxy intercepts internal traffic: put internal domains into `NO_PROXY` as `.corp.example.com` |
| The agent does not see a new subagent | A Claude Code subagent is visible only in sessions started after it was installed |
| A hub did not pick up a task journal | The journal has no `services:`/`tickets:` or link to the hub; `build_hubs.py` searches the title, name, tags, these fields and `[[…]]` |
| Everything broke after moving the repository | Tool paths are baked into hooks and skills at install time: run `./harness install` from the new location |
