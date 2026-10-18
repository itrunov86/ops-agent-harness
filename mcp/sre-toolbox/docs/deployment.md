**English** · [Русский](ru/deployment.md)

# Deployment and operations

← [Back to README](../README.md)

---

## Dependencies

```bash
pip install -r requirements.txt
# optional, for higher-level DLP:
pip install presidio-analyzer presidio-anonymizer
```

---

## Configuration

All connection parameters (URLs, tokens, limits, redaction rules, allowlist) are set in `config.yaml`. The template is `config.example.yaml`.

```bash
cp config.example.yaml config.yaml
# edit the URLs of VM Select, VictoriaLogs, Alertmanager and (optionally) Obsidian
# secrets are substituted from env via the ${VAR} syntax
```

Minimal environment variables for production:

```bash
VM_BEARER_TOKEN=...
VL_BEARER_TOKEN=...
AM_BEARER_TOKEN=...
MCP_CONFIG=/etc/mcp/config.yaml
```

---

## Running as a systemd service

```ini
# /etc/systemd/system/sre-mcp.service
[Unit]
Description=SRE MCP Server
After=network.target

[Service]
Type=simple
User=mcp
Group=mcp
EnvironmentFile=/etc/mcp/env
ExecStart=/opt/mcp/venv/bin/python /opt/mcp/server.py
Environment=MCP_CONFIG=/etc/mcp/config.yaml
Restart=on-failure
RestartSec=5

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/log/mcp

[Install]
WantedBy=multi-user.target
```

---

## Registering in Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or the corresponding path on Linux/Windows:

```json
{
  "mcpServers": {
    "sre-toolbox": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["/absolute/path/to/server.py"],
      "env": {
        "AM_BEARER_TOKEN": "...",
        "VM_BEARER_TOKEN": "...",
        "VL_BEARER_TOKEN": "...",
        "MCP_CONFIG": "/absolute/path/to/config.yaml"
      }
    },
    "victoriametrics": {
      "type": "http",
      "url": "https://vm-mcp.example.com/mcp"
    }
  }
}
```

If the MCP server lives on a separate host, `command` points to `ssh`:

```json
{
  "mcpServers": {
    "sre-toolbox": {
      "command": "ssh",
      "args": ["mcp-host", "/opt/mcp/run.sh"],
      "env": {}
    }
  }
}
```

Restart Claude Desktop. All the `am_*`, `vm_*`, `vl_*`, `obsidian_*` functions will appear in the tool list.

---

## Registering in Claude Code

```bash
claude mcp add --scope user sre-toolbox -- /absolute/path/to/.venv/bin/python /absolute/path/to/server.py
```

Or edit `.mcp.json` in the project root (example: `.mcp.example.json`). Registering in Codex — see [install.md](./install.md#8-register-in-codex).

---

## SLOs for the MCP server itself

- Tool availability: 99.5%.
- `am_active_alerts` latency: p95 < 500 ms.
- `vl_query` latency: p95 < 3 s (with `patterns` mode).
- `vm_query_range` latency: p95 < 1 s.
- `obsidian_search` latency: p95 < 100 ms (in-memory index).

---

## Server logging

**Important**: with the stdio transport, `print()` to stdout breaks the protocol. All logs go only to stderr or to a file. Use a structured JSON format so they can flow on to VictoriaLogs like any other service.

In our implementation logs go to stderr through the standard `logging` module, with the level taken from `server.log_level`.

---

## Updates and rollout

- Canary: one SRE uses the new version of the MCP server for a day, everyone else stays on the stable one.
- Tool versioning: adding a tool is minor, changing the signature of an existing one is major (clients need to be restarted).
- One-minute rollback: systemd revert.

---

## Operational security

- Service accounts for VictoriaMetrics, VictoriaLogs and Alertmanager are read-only with minimal scope.
- Regular token rotation (every 90 days).
- Audit `mcp_redaction_hits_total > 0` — every hit is reviewed by the security team.
- Once a quarter, an internal red team test: "try to exfiltrate a secret / code / customer data through Claude".

Full requirements for security approval are in [security.md](./security.md).
