**English** · [Русский](ru/workflows.md)

# Day-to-day work

## The essentials

1. **Open every chat from `work_dir`.** As many in parallel as you like, in Claude Code and Codex.
2. **Continuing a task in a new chat — start the message with the key:** `OPS-1234 continue`. Write the rest as usual.
3. **Long task — journal:** "start a handoff". Next day — a new chat with the key, not a continuation of the old one.
4. **The agent only reads remote systems.** Apply, sync, delete — after your "yes" to that one action.
5. **Knowledge goes into the base.** The agent searches it first and puts a finished review there too.
6. **Code — in a worktree on a branch named after the task key;** push and MR only on request.
7. **Knowledge-base edits are committed automatically** at the end of every agent response.

## Where to open a chat

Always `work_dir`. VS Code shows chat history per open folder: one folder — one shared list. The first message
becomes the chat title — a key at the start keeps the list readable.

The agent edits code not in the shared checkout but in a worktree on the task branch, so parallel chats don't
share one working directory:

```bash
git -C ~/work/git/infra worktree add --no-track -b OPS-1234 ~/work/chats/OPS-1234-infra origin/main
```

`--no-track` matters: a branch from `origin/main` that tracks main can be pushed straight into main by the
editor's sync.

## When to write the task key

| Situation | You write | What happens |
|---|---|---|
| Alert, question, report | as usual | no journal is injected |
| Task number in the middle of a sentence | as usual | nothing — it's a mention |
| A journal was started during the conversation | nothing | the agent runs `start`, the chat is bound automatically |
| Continue a task in a new chat | `OPS-1234 continue` | journal injected, chat bound |
| Started without a key, a journal exists | `working on OPS-1234` | bound from this message on |
| Switch to another task | `switch to OPS-1240` | chat re-bound |
| `/compact`, `--resume` | nothing | the journal is injected automatically |
| `/clear` | the key again | the chat gets a new ID |

Both English and Russian forms work: `OPS-1234 продолжаем`, `работаем по OPS-1234`, `переключаемся на OPS-1240`.
Details — [handoff.md](handoff.md).

## Typical scenarios

### An alert or request from the chat

```text
triage this alert https://chat.example.com/team/pl/abc123
```

The `request-triage` skill: thread → task key → is it firing right now → search the knowledge base for similar
cases → metrics and logs in a narrow window → cause and fix → a document in `alerts/` or `duty/`. If it turned into
real work — "start a handoff for OPS-…". For an article for the team — "write this up in duty-notes".

### A Terraform / Terragrunt change

```text
OPS-1234 we need an S3 bucket for backups in prod. Do it in a worktree, show the plan, don't apply.
```

The agent checks the key, creates a worktree, reads module versions and the backend, makes the change, runs `plan
-lock=false`, shows the result and commits. Apply — you do it yourself, or with a separate "yes, apply this module".

### Argo CD / Helm

```text
OPS-1234 bump the ingress-nginx chart to 4.11 in the gitops repo, show the helm template diff and argocd app diff.
```

The change is a commit to Git; Argo CD does the sync. The agent will not run `argocd app sync` without your "yes".

### A task without a key

```text
need to figure out why the registry is slow to serve images, create an issue
```

No key — the agent creates one issue in the project from the config and works on a branch with that key.

### Incident

```text
prod has been returning 502 since 10:15, here's the alert <link>. Investigate and find the cause.
write a postmortem for INC-7
```

### Planning

```text
create a Jira issue: move secrets to cloud storage for dev
create an epic for retiring the old cluster with subtasks per service
make a sprint report
```

### What we already know

```text
what do we have on OPS-1234?
use kb-scout to find every case where the registry returned 504
```

A hook injects the list of documents for task keys in the message on its own.

### Routine

```text
digest of the alert channel for last night
what's firing in alertmanager right now
run kb-compile                   ← once a week
Сформируй daily report           ← only this exact phrase, daily-report skill
```

The daily-report skill fires only on the exact Russian phrase `Сформируй daily report` ("generate the daily report").

## Which agent to use

| Task | Best choice |
|---|---|
| Quick alert triage, a question, tracker/wiki | either |
| Multi-file IaC change with an independent review | Codex with the `task` profile, or Claude Code + `/code-review` at the end |
| Incident with a large volume of logs | Codex with the `incident` profile, or Claude Code + `kb-scout` |
| A second pair of eyes | the other agent: Codex did it — check in Claude Code, and vice versa |

## Saving context

- Narrow the request: service, namespace, time window. "payments-api logs for the 30 minutes before 14:10" beats "look at the logs".
- Broad searches — through `kb-scout`: the chat gets a summary back, not thousands of lines.
- One chat — one task. New topic — new chat.
- At 75% context, don't start a new stage: let the agent update the journal, then `/compact` or a new chat.
- Don't keep going in chats tens of megabytes in size: a new chat + the journal is cheaper and more accurate.

## Commands at hand

```bash
H=~/Projects/agent-harness
python3 $H/tools/kb.py search "registry 504"
python3 $H/tools/kb.py list --service vault --since 2026-01-01
python3 $H/tools/kb.py lint                 # check documents
python3 $H/tools/kb.py eval                 # search quality, target hit@3 ≥ 80%
python3 $H/tools/build_hubs.py              # rebuild the lists in hubs
python3 $H/tools/agent_session.py start OPS-1234 short-slug   # journal (usually done by the agent)
cat ~/.agents/state/session-tasks.json      # which chat is bound to which task
```

Claude Code: `/compact <what to keep>`, `/clear`, `claude --resume`, `/hooks`, `/mcp`, `/agents`, `Shift+Tab` —
modes (normal / auto / plan). Codex: `/hooks`, `/compact`, `/status`.
