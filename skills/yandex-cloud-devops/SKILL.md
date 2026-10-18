---
name: yandex-cloud-devops
description: Use this skill for Yandex Cloud infrastructure work: yc CLI inventory, IAM/service accounts, Managed Kubernetes, Compute, VPC, Container Registry, Lockbox metadata, Logging, Monitoring, Terraform-backed YC changes, and read-only cloud diagnostics. Prefer this skill whenever the user mentions Yandex Cloud, YC, cloud folders, service accounts, managed Kubernetes, registries, VPC, Lockbox, or cloud-level DevOps troubleshooting.
---

# Yandex Cloud DevOps

Optional cloud-specific skill. Use a read-only Yandex Cloud MCP server first when one is installed; otherwise use the `yc` CLI with read-only `list`/`get` commands. Keep cloud access read-only unless the user explicitly approves one concrete write action.

## Workflow

1. Identify the cloud/folder context before inspecting resources:
   - Clouds: MCP tool such as `yc_clouds`, else `yc resource-manager cloud list`
   - Folders: MCP tool such as `yc_folders`, else `yc resource-manager folder list --cloud-id <id>`
   - A generic read-only passthrough (such as `yc_read`) only for `yc ... list/get` gaps not covered by a specific tool.
2. For service or cluster diagnostics, gather only the scoped inventory (always pass `--folder-id` explicitly):
   - Compute: `yc_compute_instances`, else `yc compute instance list`
   - Managed Kubernetes: `yc_k8s_clusters`, else `yc managed-kubernetes cluster list`
   - VPC: `yc_vpc_networks`, else `yc vpc network list` / `yc vpc subnet list`
   - Container Registry: `yc_container_registries`, else `yc container registry list`
   - IAM: `yc_iam_service_accounts`, else `yc iam service-account list`
   - Lockbox metadata: `yc_lockbox_secrets`, else `yc lockbox secret list` (metadata only, never `payload get`)
   - Logging/Monitoring: `yc_logging_groups` / `yc_monitoring_read`, else `yc logging group list`
3. Correlate with local IaC before recommending changes. Search the repo for folder IDs, resource names, service account names, labels, and Terraform resources.
4. Produce repo patches for desired-state changes. Avoid direct `yc update/delete/create` operations.

## Guardrails

- Do not request or print OAuth tokens, IAM tokens, service account keys, kubeconfigs, Lockbox secret payloads, private keys, or cloud access keys.
- Do not run `yc delete`, `yc update`, `yc create`, `yc set`, `yc add-*`, `yc remove-*`, or equivalent mutating commands.
- Treat `yc managed-kubernetes cluster get-credentials` as write-sensitive because it modifies local kubeconfig.
- `yc config set` / `yc config profile activate` change local CLI state; pass `--folder-id` / `--profile` per command instead.
- Prefer folder-scoped queries and return summaries when inventories are large.

## Output

When proposing a cloud change, include:

- cloud and folder scope;
- affected resources;
- IaC file or module to edit;
- expected blast radius;
- verification commands;
- rollback path.
