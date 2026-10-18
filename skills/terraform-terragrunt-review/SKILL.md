---
name: terraform-terragrunt-review
description: Use this skill for Terraform or Terragrunt analysis, validation, plan review, module/provider upgrades, backend/state inspection, drift diagnostics, cloud provider changes, and infrastructure code review. Trigger on terraform, terragrunt, .tf, .tfvars, providers, modules, state, plan, drift, or IaC requests.
---

# Terraform and Terragrunt Review

Default to read-only review and patch preparation. Never run apply or destroy without explicit approval for the exact working directory and command.

## Workflow

1. Discover roots: an IaC root-discovery MCP tool (such as `iac_find_roots`), else `rg --files -g '*.tf' -g 'terragrunt.hcl'`.
2. Inspect backend, provider constraints, module sources, and lock files before suggesting changes.
3. Run read-only checks when useful:
   - Provider/module inventory (MCP tool such as `iac_providers_modules`, else read `required_providers`, `module` sources and `.terraform.lock.hcl`).
   - Validation (MCP tool such as `terraform_validate`, else `terraform init -backend=false && terraform validate`).
   - Plan summary (MCP tool such as `terraform_plan_summary` with `refresh=false`, else `terraform plan -refresh=false -lock=false`) unless the user asks for live drift.
   - Terragrunt equivalents (`terragrunt_validate`, `terragrunt_plan_summary`, or `terragrunt validate` / `terragrunt plan`) only in the smallest affected directory.
4. Prefer focused patches over broad formatting/refactoring.
5. For cloud resources, verify account/project/folder IDs, service accounts, network/subnet placement, labels, and IAM blast radius.

## Guardrails

- Do not run `terraform apply`, `terraform destroy`, `terraform import`, `terraform state rm/mv/push`, or `terragrunt run-all apply/destroy`.
- Treat provider upgrades as risky: inspect changelogs when version changes are requested, and call out migration notes.
- Do not print state contents if it may contain secrets.
- Avoid `run-all plan` by default; ask for scope when the repo layout can trigger many modules.

## Review Checklist

- Backend and workspace are correct.
- Provider and module versions are pinned or intentionally ranged.
- Resource names, labels, and IAM bindings are consistent.
- Lifecycle settings are justified.
- Secret values come from a secret manager (Vault, cloud secret store) or CI variables, not plaintext.
- Plan summary has no unexpected replacements or deletes.
