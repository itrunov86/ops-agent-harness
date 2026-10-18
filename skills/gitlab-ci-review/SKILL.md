---
name: gitlab-ci-review
description: Use this skill for GitLab CI/CD pipelines, .gitlab-ci.yml review, includes, rules, stages, jobs, runners, artifacts, cache, Terraform/Helm deployment jobs, and CI linting or pipeline-risk analysis. Trigger on GitLab CI, .gitlab-ci.yml, pipeline, job, runner, rules, include, artifact, cache, deployment job, or CI/CD review.
---

# GitLab CI Review

Analyze pipeline behavior before suggesting changes. Keep CI mutations in Git unless the user explicitly asks for API actions.

## Workflow

1. Read `.gitlab-ci.yml` and included local files.
2. Use read-only analysis tools when available:
   - Structure analysis (MCP tool such as `gitlab_ci_analyze`, else read the YAML directly).
   - Lint (MCP tool such as `gitlab_ci_lint`, else `glab ci lint` or the project CI Lint API in dry-run mode).
   - Include resolution (MCP tool such as `gitlab_ci_includes`, else read `include:` entries and fetch remote/project templates read-only).
3. Identify stages, dependencies, rules, manual gates, deploy jobs, artifacts, cache, variables, and runner tags.
4. Patch CI config with minimal changes and explain pipeline behavior changes.

## Guardrails

- Do not trigger, cancel, retry, approve, or mutate pipelines through API without explicit approval.
- Flag jobs that run `terraform apply/destroy`, `terragrunt apply/destroy`, `helm upgrade/uninstall`, `kubectl apply/delete/patch`, `argocd app sync/rollback`, cloud CLI `create/update/delete`, or `vault write/delete`.
- Do not print masked variables or secrets.

## Review Checklist

- Rules match intended branches/tags/MR events.
- Manual gates protect production changes.
- Caches and artifacts have bounded scope and expiry.
- Deployment jobs are serialized when needed.
- CI variables are referenced safely and not hardcoded.
