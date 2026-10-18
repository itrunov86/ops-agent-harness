# Развёртывание и эксплуатация

← [Обратно в README](../README.md)

---

## Зависимости

```bash
pip install -r requirements.txt
# опционально для DLP более высокого уровня:
pip install presidio-analyzer presidio-anonymizer
```

---

## Конфигурация

Все параметры подключения (URL'ы, токены, лимиты, правила редактуры, allowlist) задаются в `config.yaml`. Шаблон — в `config.example.yaml`.

```bash
cp config.example.yaml config.yaml
# отредактируйте URL VM Select, VictoriaLogs, Alertmanager и (опционально) Obsidian
# секреты подставляются из env через синтаксис ${VAR}
```

Минимальные переменные окружения для production:

```bash
VM_BEARER_TOKEN=...
VL_BEARER_TOKEN=...
AM_BEARER_TOKEN=...
MCP_CONFIG=/etc/mcp/config.yaml
```

---

## Запуск как systemd-сервис

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

## Регистрация в Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) или соответствующий путь на Linux/Windows:

```json
{
  "mcpServers": {
    "sre-toolbox": {
      "command": "/абсолютный/путь/к/.venv/bin/python",
      "args": ["/абсолютный/путь/к/server.py"],
      "env": {
        "AM_BEARER_TOKEN": "...",
        "VM_BEARER_TOKEN": "...",
        "VL_BEARER_TOKEN": "...",
        "MCP_CONFIG": "/абсолютный/путь/к/config.yaml"
      }
    },
    "victoriametrics": {
      "type": "http",
      "url": "https://vm-mcp.example.com/mcp"
    }
  }
}
```

Если MCP-сервер живёт на отдельном хосте — `command` указывает на `ssh`:

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

Перезапустите Claude Desktop. В списке tools появятся все `am_*`, `vm_*`, `vl_*`, `obsidian_*` функции.

---

## Регистрация в Claude Code

```bash
claude mcp add --scope user sre-toolbox -- /абсолютный/путь/к/.venv/bin/python /абсолютный/путь/к/server.py
```

Или редактируется `.mcp.json` в корне проекта (пример — `.mcp.example.json`). Регистрация в Codex — см. [install.md](./install.md#8-регистрация-в-codex).

---

## SLO для самого MCP-сервера

- Доступность tools: 99.5%.
- Latency `am_active_alerts`: p95 < 500 мс.
- Latency `vl_query`: p95 < 3 с (с режимом `patterns`).
- Latency `vm_query_range`: p95 < 1 с.
- Latency `obsidian_search`: p95 < 100 мс (in-memory индекс).

---

## Логирование сервера

**Важно**: при stdio-транспорте `print()` в stdout ломает протокол. Все логи — только в stderr или в файл. Структурированный JSON-формат, чтобы дальше шло в VictoriaLogs как обычный сервис.

В нашей реализации логи идут в stderr через стандартный `logging` с уровнем из `server.log_level`.

---

## Обновление и rollout

- Канарейка: один SRE использует новую версию MCP-сервера день, остальные — стабильную.
- Версионирование tools: добавление tool — minor, изменение сигнатуры существующего — major (нужно перезагружать клиентов).
- Rollback за минуту: systemd revert.

---

## Безопасность в эксплуатации

- Сервисные аккаунты к VictoriaMetrics, VictoriaLogs и Alertmanager — read-only с минимальным scope.
- Регулярная ротация токенов (раз в 90 дней).
- Аудит `mcp_redaction_hits_total > 0` — каждое срабатывание разбирается ИБ.
- Раз в квартал — внутренний red team тест: «попробуйте через Claude выкачать секрет / код / customer-данные».

Полные требования к ИБ-апруву — в [security.md](./security.md).
