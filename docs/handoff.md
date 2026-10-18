**English** · [Русский](ru/handoff.md)

# Long-task journals

A task that does not fit into one chat keeps a journal at `<kb_root>/tasks/<KEY>-<slug>/handoff.md`. The journal is a
note to the next agent, not a chat history: the goal, where work stopped, one next action, decisions, what was done,
pitfalls. Hooks inject it into the context automatically, and a new chat picks up where the last one stopped.

## Lifecycle

| Moment | What you do | What happens |
|---|---|---|
| The task clearly won't fit into one chat | "start a handoff" | `agent_session.py start <KEY> <slug>` creates the journal and binds the chat; the agent fills in the goal and the definition of done |
| A stage is finished, a decision is made | nothing (or "update the handoff") | the agent rewrites "Сейчас" (Now) and appends to "Решения", "Сделано", "Грабли" |
| Context at 50% | nothing | a hook reminds the agent, which briefly updates the journal |
| Context at 75% | wait for the update → `/compact` or a new chat | the agent updates and commits the journal |
| Continue tomorrow | **a new chat** in `work_dir`: `OPS-1234 continue` | the hook injects the journal, the agent starts from "Next step" |
| The task is done | "close the task" | `lifecycle: historical`; durable facts go to `decisions/` and `reference/` |

Check: make your first message in a new chat "what has been done so far?" — the agent should name the right task.

## Journal sections

The journal template uses Russian headings; the English names are given in parentheses.

| Section | How it is maintained |
|---|---|
| Цель и критерий готовности (Goal and definition of done) | Once, when the journal is created |
| Сейчас (Now) | **Overwritten**: where work stopped, one next action, what we are waiting for from the user |
| Решения (Decisions) | Appended: what was chosen and why, including what was rejected — so it is not proposed again |
| Сделано (Done) | Appended: commit, MR, check with its result |
| Грабли (Pitfalls) | Appended: what broke or misled and how to work around it |
| Уроки (Lessons) | Appended: input for `/retro` |

Keep the journal under 120 lines: details go into commits, task documents and links.

## Binding to a chat

A journal is bound to a **chat** (the session ID), not to a folder. So all chats can live in one `work_dir`, and
each gets its own journal.

The hook finds a chat's journal in this order:

1. the task key in the git branch name of the chat's folder (if the chat is opened directly in the task worktree);
2. the chat binding (`<state_dir>/session-tasks.json`);
3. the folder binding (`<state_dir>/active-tasks.json`) — only for folders whose path contains a task key.

A chat is bound when:

- the message **starts** with the key of a task that has a journal (`OPS-1234 continue`, `OPS-1234 продолжаем`);
- the message contains "working on / continue / switch to" + the key (`working on OPS-1234`, `switch to OPS-1240`),
  or the Russian equivalents "работаем по / продолжаем / переключаемся на" + the key;
- the agent runs `agent_session.py start <KEY>` (actually runs it, not just mentions it in text);
- the agent writes to `tasks/<KEY>-*/handoff.md`.

A key in the middle of an ordinary sentence ("looks like OPS-1234") does not bind the chat — otherwise an alert
investigation would pick up the journal of a neighbouring task. A key without a journal does not bind either.

After `/compact` and `--resume` the chat ID stays the same, so the journal is injected automatically. After `/clear`
the ID is new: name the key again. Bindings older than 30 days are removed.

## Why not continue the old chat

A chat of tens of megabytes is compacted right away when resumed — you get almost the same thing as the journal,
only more expensive and lossy. The journal is written for continuation: it holds the next step, not a retelling.

Rule: if a decision, a contractor's answer or an MR number exists "only in the chat", the next agent will not see it.
Ask "write it to the handoff".
