---
name: helm-argocd-gitops
description: Use this skill for Helm charts, values files, Kubernetes manifests, Argo CD Applications, GitOps reconciliation, argocd app diff/history/get, helm lint/template, chart schema review, and safe Kubernetes deployment analysis. Trigger on helm, chart, values.yaml, Argo CD, argocd, Application, GitOps, sync, rollback, Kubernetes manifests, or release diagnostics.
---

# Helm, Argo CD, and GitOps

Prefer GitOps changes in the repository. Direct cluster mutation is break-glass only and requires explicit user approval.

## Workflow

1. Locate the chart, values, and Argo CD Application definition.
2. Inspect current controller state with read-only tools (MCP tools where available, CLI otherwise):
   - App list: `argocd_apps`, else `argocd app list`
   - App state: `argocd_app_get`, else `argocd app get <app>`
   - Diff: `argocd_app_diff`, else `argocd app diff <app>` (add `--local <path>` to diff a working copy)
   - History: `argocd_app_history`, else `argocd app history <app>`
3. Validate chart output:
   - Lint: `helm_lint`, else `helm lint <chart> -f <values>`
   - Render: `helm_template_summary`, else `helm template <release> <chart> -f <values>`
   - Schema: `helm_values_schema`, else read `values.schema.json`
4. Compare desired Git state with rendered manifests and Argo CD diff.
5. Patch chart/values/Application manifests rather than running imperative cluster commands.

## Guardrails

- Do not run `argocd app sync`, `argocd app rollback`, `argocd app delete`, `helm upgrade`, `helm uninstall`, `kubectl apply`, `kubectl delete`, or `kubectl patch` without explicit approval for that one action.
- Treat CRDs, hooks, jobs, PVCs, ingress changes, and RBAC changes as higher risk.
- Removing an Application or resource from Git can cascade into deleting managed resources (finalizers, prune, operators that own external objects such as databases or users). Check what the controller will prune before proposing removal.
- When suggesting a sync, include the exact app, revision, expected diff, health checks, and rollback command.

## Review Checklist

- Values are environment-specific and do not duplicate chart defaults unnecessarily.
- Resources have requests/limits where expected.
- Probes, PDBs, HPA, affinity/tolerations, and rollout strategy fit the workload.
- Secrets are referenced, not embedded.
- Argo CD sync waves/hooks are intentional.
