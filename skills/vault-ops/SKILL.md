---
name: vault-ops
description: Use this skill for HashiCorp Vault operational analysis: vault status, policies, auth methods, mounts, KV metadata, access troubleshooting, secret path inventory, Terraform Vault provider review, and safe secret-management workflows. Trigger on vault, policy, token, auth method, approle, kv, secret metadata, mount, or access denied requests.
---

# Vault Ops

Use metadata-first diagnostics. Do not read or expose secret values unless the user explicitly requests a specific path and confirms the data can be shown.

## Workflow

1. Check health and scope (MCP tools where available, CLI otherwise):
   - `vault_status`, else `vault status`
   - `vault_auth_list`, else `vault auth list`
   - `vault_secrets_list`, else `vault secrets list`
2. For access issues, inspect policy names and path capabilities via policy text, not secret data:
   - `vault_policy_read`, else `vault policy read <name>`; `vault token capabilities <path>` for a quick check.
3. For KV paths, inspect metadata/listing only:
   - `vault_kv_metadata_list`, else `vault kv list <mount>/<path>`
   - `vault_kv_metadata_get`, else `vault kv metadata get <mount>/<path>`
4. Cross-check Terraform or repo policy definitions before recommending changes.

## Guardrails

- Do not run `vault kv get`, `vault read` on secret payload paths, `vault write`, `vault delete`, `vault token create`, `vault operator`, or policy writes without explicit approval.
- Redact tokens, accessors, secret IDs, wrapping tokens, private keys, and certificate private material.
- Prefer policy diffs in Git over direct Vault mutation.
- Place new secrets, mounts, policies and AppRoles by purpose; do not reuse another component's mount, policy or role just because it already has access.

## Output

For policy changes, include affected path patterns, capabilities, principal/auth method, risk, verification command, and rollback patch.
