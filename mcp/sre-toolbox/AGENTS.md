# AGENTS.md — заметки для разработки sre-toolbox

> **Прочитать перед работой:** [REQUIREMENTS.md](REQUIREMENTS.md) — правила структуры, кода и документации.

> **Команда:** если для назначения задач или фильтра по исполнителю нужен состав команды, держите его в
> локальном `teams.md` (gitignored) по образцу [teams.example.md](teams.example.md).

## Что это

MCP-сервер (`sre-toolbox`) на FastMCP — часть [agent-harness](../../README.md). Даёт агенту доступ к стеку
наблюдаемости и рабочим инструментам команды: Alertmanager, VictoriaMetrics, VictoriaLogs, Jira, Confluence,
GitLab, Mattermost, Grafana, локальный Obsidian-vault и база знаний через `kb.py`. Запускается локально внутри
периметра; **результаты вызовов tools уходят провайдеру модели** как часть контекста (см.
[docs/security.md](docs/security.md)). Какие возможности MCP ждут скиллы harness — [../../docs/mcp.md](../../docs/mcp.md).

Глубокая документация — в [`docs/`](docs/) (architecture, tools, security, token-economy, obsidian, install,
deployment, examples). README — оглавление.

## Команды

```bash
# окружение (python 3.10+)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# запустить сервер (stdio); конфиг — config.yaml рядом или MCP_CONFIG=/path
.venv/bin/python server.py

# smoke-тест: импорт без запуска (проверяет конфиг и регистрацию tools)
MCP_CONFIG=config.example.yaml .venv/bin/python -c "import server; print('ok', server.mcp.name)"

# контрактные тесты (routing метрик, логов, Alertmanager)
.venv/bin/python -m unittest discover -s tests -v
```

Ручной вызов tool через агента остаётся проверкой live credentials/config. См. [docs/install.md](docs/install.md).

## Архитектура

**server.py + tools/.** `server.py` — точка входа: конфиг, клиенты, shared-хелперы, регистрация модулей.
Tools живут в `tools/` — по одному файлу на интеграцию:

| Файл | Tools |
|------|-------|
| `tools/jira.py` | 11 |
| `tools/confluence.py` | 6 |
| `tools/gitlab.py` | 7 |
| `tools/mattermost.py` | 8 |
| `tools/grafana.py` | 5 |
| `tools/alertmanager.py` | 2 |
| `tools/victoria_metrics.py` | 3 |
| `tools/victoria_logs.py` | 2 |
| `tools/obsidian.py` | 5 (`kb_search`, `kb_list`, `obsidian_*`) |

Каждый модуль экспортирует `register(mcp, cfg, client_factory, redactor, audit_fn)` — зависимости явные, импортов
из `server.py` нет. Новый сервис: блок в конфиге, `_client_X` в `server.py`, файл `tools/X.py` с `register()`.

**Конфиг-центричность.** Поведение целиком задаётся `config.yaml` (gitignored; шаблон — `config.example.yaml`).
При старте `load_config` раскрывает `${VAR}` из окружения (`.env` рядом подгружается автоматически). Каждая
интеграция — блок с единой формой: `url` / `auth` (bearer или basic) / `headers` / `timeout_seconds` / `limits`.
Grafana одна (`grafana.url`). VM и VictoriaLogs tools ходят напрямую в настроенный `url`; тенант логов выбирается
только по имени из server-side `victorialogs.tenants`, Alertmanager — по имени из `alertmanager.instances`. URL,
credentials и номера тенантов вне карты аргументами tool не принимаются.

**База знаний.** `kb_search` / `kb_list` загружают `kb.py` по пути `obsidian.kb_tool`; по умолчанию это
`../../tools/kb.py` (копия в agent-harness). Корень базы `kb.py` берёт из конфига harness (`paths.kb_root`).

### Отдельный MCP-сервер VictoriaMetrics (опционально)

Если у вас есть HTTP-сервер VictoriaMetrics MCP, его можно подключить рядом (пример — `.mcp.example.json`).
Тогда при сборе метрик сначала используйте `mcp__victoriametrics__query` / `query_range`, а локальные `vm_*` —
как fallback. Контракт, discovery labels и правила работы с пустым результатом —
[docs/victoriametrics-mcp.md](docs/victoriametrics-mcp.md).

Отдельный MCP возвращает сырые Prometheus timestamps и не поддерживает `summarize`; для длинных окон используйте
агрегирующие выражения, например `max_over_time((<expr>)[1h:1m])` с `step=1h`. `result: []` не означает
автоматически отсутствие метрики: сначала проверьте `label_values` или `series` — подключённый VM может быть
другим инстансом/tenant.

**Сквозные защитные слои** (применяются ко всем ответам, `server.py`):
- `Redactor.scrub_any` — рекурсивно маскирует секреты/PII по regex из `redaction.patterns` перед возвратом.
- `audit(tool, args, size)` — best-effort запись каждого вызова в JSONL (`server.audit_log_path`).
- `check_allowlist` — отклоняет PromQL/LogsQL без упоминания разрешённых `services`/`namespaces`.
- Опциональная токенизация имён сервисов (алиасы вместо реальных имён).

**Write-гейтинг.** Создание/изменение (Jira, Confluence, GitLab, Mattermost, Obsidian) работает только при
`allow_writes: true` в своей секции, плюс allowlist по scope: `jira.allow_projects`, `confluence.allow_spaces`,
`mattermost.allow_channels` и т.п. В `config.example.yaml` все `allow_writes` выключены. Тело Jira/Confluence —
всегда **wiki markup** (`h1.`, `*bold*`, `*` списки, `||` таблицы, `[label|url]`), не markdown.

**Token economy — основной смысл проекта.** Входные токены (логи/метрики) доминируют. Read-сторона уже жмётся:
`vl_query` по умолчанию `patterns` (кластеризация логов), `vm_query_range` — `summarize`
(min/max/p50/p95/p99 вместо точек), лимиты на размеры ответов. Поверх — слой переиспользования (см.
[docs/token-economy.md](docs/token-economy.md)): база знаний (`kb_search`) и Obsidian vault (`obsidian_search` /
`obsidian_read_note` / `obsidian_append_finding`). Хорошо написанный runbook на 500 токенов экономит 10-50K
токенов диагностики. `obsidian_append_finding` генерирует `[[wikilinks]]` автоматически (из `related_notes` и
авто-детекции заголовков).

## Конвенция работы (recall-first)

- **Перед** дорогим анализом (логи/метрики/прод) сначала `kb_search` / `obsidian_search` — возможно, ответ уже есть.
- **После** нетривиального разбора фиксируйте вывод через `obsidian_append_finding` со ссылками `[[...]]`.
- Скиллы, порождающие знание (например `postmortem`), включают шаг записи находки в vault.

## Скиллы

Командные скиллы, которые работают поверх этих tools (postmortem, quarterly-planning, tracker-epic,
tracker-story, alerts-digest, sprint-report, duty-notes), лежат в [`../../team-skills/`](../../team-skills/) и
ставятся через `./harness install`. Скиллы линкуют артефакты ссылками по ключу (`OPS-123`) — формального
issue-link тулинг не умеет.
