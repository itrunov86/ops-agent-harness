**English** · [Русский](ru/security.md)

# Security

## Model

| What | Default |
|---|---|
| Reading the cloud, clusters, secrets manager, Argo CD, CI, tracker, wiki, chat | allowed |
| Writing to any of the above | only after an explicit "yes" for one specific action |
| Edits in work repositories | on the task branch; commit after verification; push and MR on request |
| Edits in the knowledge base | allowed; committed directly to `main`, autocommit at the end of each response |
| Creating a tracker issue when there is no key | standing permission for one issue (rule in AGENTS.md) |

Before asking for confirmation the agent must state: what will change, what it affects, how to roll back, how to
verify. A "yes" covers one action; the agent asks again for the next one. A permissive sandbox mode is not
confirmation.

Hard ban without confirmation: `terraform|terragrunt apply|destroy`, `kubectl delete|patch|scale|rollout restart`,
`argocd app sync|rollback|delete`, `helm upgrade|uninstall`, `vault write|delete`, cloud CLI `delete|update`,
CI mutations. When the agent is unsure whether a command writes, it assumes it does.

## Layers of protection

Rules in AGENTS.md are a request to the model, not a guarantee. The real restrictions are outside it:

1. **Agent permissions.** Claude Code: `permissions.allow / ask / deny` in `~/.claude/settings.json` — write commands
   go into `ask` or `deny`. Codex: `approval_policy = "on-request"`, `read-only`/`workspace-write` sandbox.
2. **Read-only credentials.** Where possible, a separate read-only token/role for the agent: then writes are
   impossible even if the model makes a mistake.
3. **Write gate in the MCP server.** In sre-toolbox the write tools of every system are off (`allow_writes: false`)
   and are enabled in `config.yaml` on the server side, not in the prompt.
4. **Subagents without writes.** `kb-scout` has no write tools at all.
5. **Credential wrappers.** Cloud access goes through a wrapper script that takes keys from Keychain and sets the
   variables for a single command only, instead of an `export` in your profile. In the agent's settings allow
   specific wrapper subcommands (`<wrapper> terraform plan`) and keep `apply` in `ask`.

## Secrets

- Do not paste tokens, keys, kubeconfigs or secret values into the chat — the agent reads them itself through
  wrappers and MCP.
- The rules forbid the agent from printing secrets in responses, documents, commits, artifacts and logs.
- Autocommit does not commit a file that appears to contain a secret, and warns about it.
- External searches (documentation, web) carry only generic technology questions, without internal names or data.

## Publishing your fork

Before `git push` to a public repository:

```bash
python3 scripts/check_sanitized.py
```

The check looks for private keys, tokens, internal IPs, personal home paths, email addresses not on `example.*`, and
everything in your personal denylist `.sanitize-denylist` (it is in `.gitignore`): put your company name, internal
domains, logins and task prefixes there. CI runs the same check on every push.

Your company's team processes (postmortem, task and sprint page templates) may be its property. `team-skills/` in
this repository contains anonymized method templates; keep your own team templates in a private fork or in a separate
company repository.
