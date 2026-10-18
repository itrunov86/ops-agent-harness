---
name: service-network-triage
description: Diagnose DNS, TLS, ingress, API gateway routing and Kubernetes Service reachability failures for a specific endpoint.
---

Identify the failing source, destination, environment, protocol and time window. Separate workstation/VPN/proxy behavior from in-cluster behavior; a local failure does not establish a cluster failure. Check proxy environment variables (`HTTPS_PROXY`, `NO_PROXY`) when a workstation tool fails against internal hosts: a corporate proxy can intercept traffic meant to bypass it.

Trace only the relevant path: DNS resolution, TCP reachability, TLS hostname/chain/expiry, ingress or API gateway (for example Kong, NGINX, Traefik) route, Service ports/selectors and EndpointSlice readiness. Read the deployed controller version before using version-specific settings. Compare a working path when available. Keep curl/connect timeouts bounded and record where each observation was made.

Prefer existing read-only metrics, logs and configuration. Do not dump request authorization headers, cookies, private keys, or whole Secret resources. Certificate metadata suffices for TLS checks. Requests to business endpoints can have side effects even with GET; use a known diagnostic endpoint. Do not introduce insecure TLS bypass as a fix.

Report the failing layer, supporting evidence, unresolved alternatives and smallest proposed change. Diagnostic Pods, route edits and controller restarts remain subject to global remote-write approval rules.

Service reference: https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/
