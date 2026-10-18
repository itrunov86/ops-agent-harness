---
name: kubernetes-runtime-triage
description: Diagnose failing Pods, restarts, scheduling, probes, node pressure or PVC attachment in a live Kubernetes workload. For chart changes use the helm-argocd-gitops skill.
---

Establish the requested context, namespace, workload and incident time window from local context. Pass context and namespace explicitly; do not change the default kube context. Search relevant runbooks in the knowledge base (`{{KB_ROOT}}`, through a knowledge-base search tool such as `kb_search` on `{{MCP_HUB}}` when available) before a broad dig.

Start with workload status and a narrowly selected Pod. Follow owner references; correlate conditions, container last termination reason, restart counts and relevant events. Fetch one container's timestamped logs with a time bound and line limit; inspect previous logs when a restart makes them relevant. Expand to node conditions, PVC events or quotas only when evidence points there.

Distinguish Pending scheduling/volume failures, image failures, application crashes and readiness failures. A current Running phase is not proof of service health. Absence of retained events or logs is a data gap, not proof that no failure occurred.

Return observed impact, timestamped evidence, hypotheses and the next discriminating check. Preserve global remote-write approval rules: debug containers and diagnostic Pod creation are mutations; exec depends on the command and is not automatically read-only. For a GitOps fix use the helm-argocd-gitops workflow.

Version-specific reference: https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/
