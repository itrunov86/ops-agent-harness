**English** · [Русский](ru/hooks.md)

# Hooks

A hook is a command the agent runs on an event, passing it JSON on stdin. The harness installs two handlers:
`tools/agent_session.py hook` (journals, context, autocommit) and `tools/kb.py hook` (documents by task keys).
Neither ever fails or blocks anything: on any error they exit silently.

| Event | Claude Code | Codex | What it does |
|---|---|---|---|
| `SessionStart` | ✓ | ✓ | Injects the task journal after `/compact`, `/clear`, `--resume`, and on start in a task folder |
| `UserPromptSubmit` | ✓ | ✓ | Binds the chat by the key at the start of the message; 50/75% context signal; `kb.py hook` — list of documents for the task keys in the message |
| `PreToolUse` | ✓ | ✓ | Snapshot of the knowledge base `git status` before the tool runs (for autocommit) |
| `PostToolUse` | ✓ | ✓ | Which knowledge-base files the call changed; binds the chat if the agent created or writes to a journal; context signal |
| `Stop` | ✓ | ✓ | Autocommits the knowledge-base files changed by this chat |
| `PostCompact` | ✓ | — | Saves the compaction summary to `<state_dir>/compact/` |

Codex runs new hooks only after `/hooks` → trust.

## Context fill signals

`hooks.handoff_thresholds` (50 and 75 by default). At each threshold — once per chat — the hook asks the agent to
update the journal; at the last one, to finish the current step and suggest `/compact`. After compaction the
thresholds are re-armed. Fill level is computed from the last `usage` in the session transcript.

## Knowledge base autocommit

Problem: several parallel chats edit the base, someone forgets to commit, and other chats' unfinished edits end up in
the next commit.

Solution:

1. **PreToolUse / PostToolUse:** before and after every tool call the hook compares the base's `git status` and
   records which files this chat changed — with any tool, including edits through the shell.
2. **Stop:** at the end of the response it commits **only those files**: `<KEY> docs: <files>`. The key comes from
   the chat binding or from the file names.
3. **Does not commit, and warns about:** a file that another chat also edited within the last hour; a file that
   looks like a secret (private key, JWT, Vault/GitLab/AWS/Yandex Cloud tokens).
4. If the agent committed by itself, the hook does nothing. Nothing is pushed. During a merge/rebase it postpones.

To turn it off: `hooks.autocommit = false`. Autocommit does not touch code repositories — only `kb_root`.

## State

`<state_dir>` (`~/.agents/state` by default):

| File | Contents |
|---|---|
| `session-tasks.json` | chat → task journal |
| `active-tasks.json` | folder with a key in its path → journal |
| `pressure/<session>.json` | which context thresholds have already fired |
| `autocommit/<session>.json`, `owners.json` | knowledge-base files changed by chats |
| `compact/*.md` | Claude Code compaction summaries |
| `harness-manifest.json` | what `harness install` installed |

All of it can be deleted — the hooks will start from a clean slate.

## Manual check

```bash
echo '{"hook_event_name":"UserPromptSubmit","session_id":"t","cwd":"'$PWD'","prompt":"OPS-1234 continue"}' \
  | python3 -I ~/Projects/agent-harness/tools/agent_session.py hook
```

Tests for all scenarios are in `tests/test_agent_session.py`.
