[English](README.md) · **Русский**

# sre-toolbox — MCP-сервер интеграций

Часть [agent-harness](../../README.ru.md): MCP-сервер-«хаб», который даёт агенту (Claude Code, Codex) доступ к стеку
наблюдаемости и рабочим инструментам команды DevOps: **Alertmanager**, **VictoriaMetrics**, **VictoriaLogs**,
**Jira**, **Confluence**, **GitLab**, **Mattermost**, **Grafana**, база знаний через `kb.py` и локальный
**Obsidian** vault. Предназначен для дежурных SRE: быстрый разбор алертов, корреляция метрик и логов, первичные
гипотезы по инцидентам. Какие возможности MCP нужны скиллам harness и как этот сервер их закрывает —
[../../docs/mcp.md](../../docs/ru/mcp.md); его имя указывается в `mcp.hub` конфига harness.

Авторы: itrunov86 и Сергей Клецов.

---

## Документация

| Раздел | О чём |
|--------|-------|
| [docs/architecture.md](./docs/ru/architecture.md) | Как работает в общих чертах |
| [docs/tools.md](./docs/ru/tools.md) | Справочник по всем tools (параметры, ответы) |
| [docs/victoriametrics-mcp.md](./docs/ru/victoriametrics-mcp.md) | Опциональный внешний MCP VictoriaMetrics и правила запросов |
| [docs/security.md](./docs/ru/security.md) | Что уходит провайдеру модели — 8 слоёв защиты, чек-лист |
| [docs/token-economy.md](./docs/ru/token-economy.md) | Экономия токенов — приёмы и архитектура |
| [docs/obsidian.md](./docs/ru/obsidian.md) | Knowledge base через Obsidian vault и `kb.py` |
| [docs/install.md](./docs/ru/install.md) | Локальная установка: venv, конфиг, регистрация, smoke-тест |
| [docs/deployment.md](./docs/ru/deployment.md) | Production: systemd, hardening |
| [docs/examples.md](./docs/ru/examples.md) | 10 практических сценариев |

---

## Состав каталога

| Файл / папка | Назначение |
|------|-----------|
| `server.py` | Точка входа: конфиг, клиенты, shared-хелперы, регистрация модулей |
| `tools/` | Tools по одному файлу на интеграцию |
| `tests/` | Контрактные тесты routing (VM, VictoriaLogs, Alertmanager) |
| `scripts/set_grafana_token.py` | Проверить токен Grafana и записать его в `config.yaml` |
| `config.example.yaml` | Шаблон конфига (всё read-only) — скопировать в `config.yaml` |
| `config.yaml`, `.env`, `teams.md` | Локальные файлы с адресами и секретами (в `.gitignore`) |
| `teams.example.ru.md` | Формат описания команды для назначения задач |
| `.mcp.example.json` | Пример project-scope регистрации (с опциональным VictoriaMetrics MCP) |
| `AGENTS.md`, `REQUIREMENTS.ru.md` | Заметки и правила для разработки сервера |

Командные скиллы, которые работают поверх этих tools, лежат в [`../../team-skills/`](../../team-skills/).

---

## Доступные tools

| Категория | Tool | Назначение |
|-----------|------|-----------|
| Алерты | `am_active_alerts` | Активные алерты из Alertmanager |
| Алерты | `am_silences` | Активные silence-ы |
| Метрики | `vm_query` | Instant PromQL |
| Метрики | `vm_query_range` | Range PromQL (агрегаты по умолчанию) |
| Метрики | `vm_label_values` | Discovery значений лейбла |
| Логи | `vl_query` | LogsQL с режимом `patterns` |
| Логи | `vl_streams` | Список потоков |
| Knowledge base | `kb_search` | Поиск по базе знаний (`kb.py`): разделы и диапазоны строк |
| Knowledge base | `kb_list` | Каталог базы знаний с фильтрами |
| Knowledge base | `obsidian_search` | Поиск по vault |
| Knowledge base | `obsidian_read_note` | Чтение конкретной заметки |
| Knowledge base | `obsidian_append_finding` | Запись заметки с `[[wikilinks]]` |
| Jira | `jira_get_issue` | Получить задачу по ключу |
| Jira | `jira_search` | Поиск задач по JQL |
| Jira | `jira_create_issue` | Создать задачу (allow_writes) |
| Jira | `jira_update_issue` | Обновить поля задачи (allow_writes) |
| Jira | `jira_transition_issue` | Сменить статус (allow_writes) |
| Jira | `jira_add_comment` | Добавить комментарий (allow_writes) |
| Jira | `jira_set_epic` | Привязать задачу к эпику (allow_writes) |
| Jira | `jira_list_projects` | Список проектов |
| Jira | `jira_list_boards` | Список Agile-досок |
| Jira | `jira_list_sprints` | Список спринтов доски |
| Jira | `jira_sprint_issues` | Задачи спринта |
| Confluence | `confluence_get_page` | Страница по id или (space, title) |
| Confluence | `confluence_search` | CQL-поиск страниц |
| Confluence | `confluence_get_page_children` | Дочерние страницы |
| Confluence | `confluence_get_bookmark` | Страница из именованной закладки |
| Confluence | `confluence_create_page` | Создать страницу (allow_writes) |
| Confluence | `confluence_update_page` | Обновить страницу (allow_writes) |
| GitLab | `gitlab_list_projects` | Список проектов |
| GitLab | `gitlab_get_project` | Детали проекта |
| GitLab | `gitlab_list_mrs` | Список MR'ов |
| GitLab | `gitlab_get_mr` | MR с diff/комментариями |
| GitLab | `gitlab_get_file` | Файл из репозитория |
| GitLab | `gitlab_search` | Поиск по коду/коммитам |
| GitLab | `gitlab_create_mr_note` | Комментарий к MR (allow_writes) |
| Mattermost | `mm_list_teams` | Список команд |
| Mattermost | `mm_list_channels` | Каналы команды |
| Mattermost | `mm_list_channel_posts` | Посты канала |
| Mattermost | `mm_get_post` | Пост по id |
| Mattermost | `mm_get_thread` | Тред |
| Mattermost | `mm_search_posts` | Поиск постов |
| Mattermost | `mm_resolve_permalink` | Permalink → контент |
| Mattermost | `mm_create_post` | Отправить сообщение (allow_writes) |
| Grafana | `grafana_search` | Поиск дашбордов |
| Grafana | `grafana_get_dashboard` | Дашборд по uid |
| Grafana | `grafana_list_datasources` | Список источников данных |
| Grafana | `grafana_get_annotations` | Аннотации |
| Grafana | `grafana_list_alert_rules` | Список alert rules |

Метрики и логи читаются напрямую из VictoriaMetrics/VictoriaLogs, Grafana одна. `vm_*` смотрят во
все тенанты сразу (кластер — label `vm_account_id`), `vl_*` — в один тенант из server-side карты
(`tenant`), `am_*` выбирают Alertmanager параметром `instance`. Лимиты range/step/ответа — в
[справочнике tools](./docs/ru/tools.md).

Если рядом подключён отдельный MCP `victoriametrics` (пример — `.mcp.example.json`),
порядок такой: `mcp__victoriametrics__query` / `mcp__victoriametrics__query_range`,
затем локальные `vm_*` tools как fallback. Полные правила — в
[docs/victoriametrics-mcp.md](./docs/ru/victoriametrics-mcp.md).

Подробности — в [docs/tools.md](./docs/ru/tools.md).

---

## Быстрый старт

Коротко; подробно — [docs/install.md](./docs/ru/install.md).

### 1. Установка

```bash
cd ~/Projects/agent-harness/mcp/sre-toolbox
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. Конфигурация

```bash
cp config.example.yaml config.yaml   # config.yaml в .gitignore
```

Заполните `url` нужных интеграций (ненужные блоки можно оставить пустыми). Все `allow_writes` в шаблоне
выключены — включайте запись точечно, вместе с allowlist (`allow_projects`, `allow_spaces`, `allow_channels`).

Токены живут **только** локально: в `config.yaml`, в `.env` рядом с `server.py` (подставляются через `${VAR}`, см.
`.env.example`) или в окружении/Keychain, откуда их передаёт ваш лаунчер. `scripts/set_grafana_token.py` пишет
токен Grafana прямо в `config.yaml` (права `0600`). В репозиторий токены не попадают никогда.

Минимальный пример `config.yaml`:

```yaml
server:
  name: "sre-toolbox"
  audit_log_path: ""          # или путь к audit.jsonl

alertmanager:
  instances:
    main: {url: "https://am.example.com"}
  auth:
    bearer_token: "${AM_BEARER_TOKEN}"

victoriametrics:
  url: "https://vm.example.com/select/multitenant/prometheus"
  auth:
    bearer_token: "${VM_BEARER_TOKEN}"

victorialogs:
  url: "https://vlogs.example.com"
  auth:
    bearer_token: "${VL_BEARER_TOKEN}"
  default_tenant: "prod"
  tenants: {prod: 0}

grafana:
  url: "https://grafana.example.com"
  auth:
    bearer_token: "${GRAFANA_TOKEN}"

# База знаний: kb.py из agent-harness (по умолчанию ../../tools/kb.py) + Obsidian vault
obsidian:
  vault_path: "~/Documents/Obsidian/SRE"
  # kb_tool: "~/Projects/agent-harness/tools/kb.py"
  allow_writes: false

jira:
  url: "https://jira.example.com"
  auth:
    bearer_token: "${JIRA_PAT}"
  allow_writes: false
  allow_projects: []          # например ["OPS"]

confluence:
  url: "https://confluence.example.com"
  auth:
    bearer_token: "${CONFLUENCE_PAT}"
  allow_writes: false
```

> **Где взять токен Jira/Confluence Server.** Профиль → `Personal Access Tokens` → `Create token`. У Jira и
> Confluence токены разные.

### 3. Проверка

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -c "import server; print('ok', server.mcp.name)"
# отладка через MCP Inspector:
.venv/bin/mcp dev server.py
```

### 4. Регистрация

Claude Code:

```bash
claude mcp add --scope user sre-toolbox -- \
  ~/Projects/agent-harness/mcp/sre-toolbox/.venv/bin/python \
  ~/Projects/agent-harness/mcp/sre-toolbox/server.py
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.sre-toolbox]
command = "/полный/путь/agent-harness/mcp/sre-toolbox/.venv/bin/python"
args = ["/полный/путь/agent-harness/mcp/sre-toolbox/server.py"]
# env = { MCP_CONFIG = "/полный/путь/к/config.yaml" }   # если конфиг не рядом с server.py
```

Затем в `~/.config/agent-harness/config.toml` в секции `[mcp]` укажите `hub = "sre-toolbox"` — `kb-scout` получит запрет на
его пишущие tools. Systemd и hardening — [docs/deployment.md](./docs/ru/deployment.md).

---

## Пример диалога

> **SRE:** что сейчас горит?
>
> **Claude:** *(вызывает `am_active_alerts(severity='critical')`)*
> Сейчас 3 critical-алерта: `HighErrorRate` на `checkout-api` (с 14:23),
> `DBConnectionPoolExhausted` на `payment-service` (с 14:25), `HighLatency`
> на `auth-api` (с 14:31). Похоже на каскадный сбой, начинаю с checkout.

> **SRE:** разбери checkout.
>
> **Claude:** *(вызывает `kb_search("HighErrorRate checkout")`, потом `vm_query_range`, `vl_query`)*
> Runbook найден — `runbooks/high-error-rate.md`. По метрикам error rate
> подскочил с 14:18 (был деплой `a3f1b2`). В логах новый паттерн
> `payment timeout after <N>ms` (2810 раз). Это похоже на инцидент INC-42
> от марта — рекомендую rollback.

Десять полных сценариев — в [docs/examples.md](./docs/ru/examples.md).

---

## Расширение

Чтобы добавить tool к существующей интеграции — открываешь нужный `tools/X.py`
и добавляешь функцию внутри `register()`:

```python
@mcp.tool()
async def my_tool(arg1: str, arg2: int = 10) -> dict[str, Any]:
    """
    Краткое описание для Claude — что делает tool, когда вызывать.

    Args:
        arg1: что это.
        arg2: что это.
    """
    async with client_factory() as c:
        resp = await c.get(...)
    payload = redactor.scrub_any({"result": ...})
    audit_fn("my_tool", {"arg1": arg1}, len(json.dumps(payload)))
    return payload
```

Чтобы добавить **новую интеграцию**: добавь блок в `config.yaml`, `_client_X` в `server.py`,
новый файл `tools/X.py` с функцией `register(mcp, cfg, client_factory, redactor, audit_fn)`,
и вызов `tools.X.register(...)` в `server.py`.

**Важно:**
- Docstring и type-hints — это контракт с моделью. Чем точнее, тем лучше Claude поймёт, когда вызывать tool.
- Никогда не используйте `print` (`stdout` зарезервирован для JSON-RPC). Логируйте через `logging`.
- Прогоняйте ответы через `redactor.scrub_any(...)` перед возвратом.

---

## Ключевые идеи

1. **MCP-сервер — это шлюз, а не транзитный канал.** Каждый tool агрегирует, фильтрует и редактирует данные перед тем, как они уйдут к Claude.
2. **Защита кода — это в первую очередь минимизация контекста.** Решающая защита — отправить 10 строк, а не 10 тысяч.
3. **Экономия и безопасность совпадают.** Чем меньше отправляется, тем дешевле и безопаснее.
4. **Knowledge base в Obsidian** — самый мощный приём экономии. Хорошо написанный runbook на 500 токенов экономит 10–50K токенов диагностики. См. [docs/obsidian.md](./docs/ru/obsidian.md).
