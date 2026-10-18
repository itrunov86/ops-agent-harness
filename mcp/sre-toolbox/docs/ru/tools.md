[English](../tools.md) · **Русский**

# Tools MCP-сервера

← [Обратно в README](../../README.ru.md)

Справочник по всем tools, которые сервер предоставляет Claude. Каждый описан с точки зрения: что делает, какие аргументы, какой ответ, какие меры безопасности применяются.

---

## Сводная таблица

| Категория | Tool | Назначение |
|-----------|------|-----------|
| Алерты | `am_active_alerts` | Активные алерты из Alertmanager |
| Алерты | `am_silences` | Активные silence-ы |
| Метрики | `vm_query` | Instant PromQL |
| Метрики | `vm_query_range` | Range PromQL (агрегаты по умолчанию) |
| Метрики | `vm_label_values` | Discovery значений лейбла |
| Логи | `vl_query` | LogsQL c режимом `patterns` |
| Логи | `vl_streams` | Список потоков |
| Knowledge base | `kb_search` | Поиск по базе знаний через `kb.py` |
| Knowledge base | `kb_list` | Каталог базы знаний с фильтрами |
| Knowledge base | `obsidian_search` | Поиск по vault |
| Knowledge base | `obsidian_read_note` | Чтение конкретной заметки |
| Knowledge base | `obsidian_append_finding` | Запись новой заметки |
| Jira | `jira_get_issue` | Получить задачу по ключу |
| Jira | `jira_search` | Поиск задач по JQL |
| Jira | `jira_create_issue` | Создать задачу (под `allow_writes`) |
| Jira | `jira_update_issue` | Обновить поля задачи |
| Jira | `jira_transition_issue` | Сменить статус |
| Jira | `jira_add_comment` | Добавить комментарий |
| Jira | `jira_list_projects` | Список проектов |
| Jira | `jira_list_boards` | Список Agile-досок |
| Jira | `jira_list_sprints` | Список спринтов |
| Jira | `jira_sprint_issues` | Задачи спринта |
| Confluence | `confluence_get_page` | Страница по id или (space, title) |
| Confluence | `confluence_search` | CQL-поиск |
| Confluence | `confluence_get_page_children` | Дочерние страницы |
| Confluence | `confluence_get_bookmark` | Страница из закладки в конфиге |

---

## Алерты (Alertmanager)

### `am_active_alerts`

Возвращает активные алерты из Alertmanager (`/api/v2/alerts`).

| Параметр | Тип | Описание |
|----------|-----|----------|
| `severity` | string? | Фильтр: `critical`, `warning`, `info` |
| `service` | string? | Фильтр по label `service` (или `job`) |
| `limit` | int | По умолчанию 50, максимум 200 |
| `instance` | string? | Alertmanager из `alertmanager.instances` (имя или alias); по умолчанию `default_instance` |

Несколько Alertmanager задаются в `alertmanager.instances`; общие `verify_ssl`, `timeout_seconds`, `auth` — на верхнем уровне, инстанс их переопределяет. Старый формат с одним `url` работает как инстанс `default`. Неизвестное имя возвращает список доступных, URL параметром не принимается.

**Ответ** — `instance` и компактный JSON: `name`, `severity`, `service`, `started_at`, `summary`, `runbook`. Никаких полных лейблов, generatorURL, fingerprint и прочего шума.

### `am_silences`

Активные silence-ы в Alertmanager (`/api/v2/silences`). Полезно, чтобы Claude видел, что заглушено в данный момент и почему.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `active_only` | bool | По умолчанию `true` — только активные |
| `instance` | string? | Как в `am_active_alerts` |

---

## Отдельный MCP-сервер `victoriametrics`

Если у вас развёрнут отдельный HTTP-сервер VictoriaMetrics MCP, для агентских
запросов метрик приоритетным источником становится он, подключённый в `.mcp.json` проекта (пример — [`.mcp.example.json`](../../.mcp.example.json)):

```json
"victoriametrics": {
  "type": "http",
  "url": "https://vm-mcp.example.com/mcp"
}
```

Это самостоятельный сервер. Его tools вызываются как
`mcp__victoriametrics__query`, `mcp__victoriametrics__query_range`,
`mcp__victoriametrics__label_values` и `mcp__victoriametrics__series`.
Не путай их с локальными `vm_query`, `vm_query_range`, `vm_label_values` из
`sre-toolbox`: последние используют `config.yaml` и предназначены для
fallback/совместимости.

`mcp__victoriametrics__query` принимает `query` и опциональные `time`, `step`,
`timeout`, `nocache`. `mcp__victoriametrics__query_range` принимает `query`,
`start`, `end`, `step`, `timeout`, `nocache`. В отличие от локального
`vm_query_range`, отдельный MCP возвращает сырые точки `[timestamp, value]` и
не имеет `summarize`; используй узкое окно, разумный `step` и агрегирующий
PromQL/MetricsQL для длинной истории.

Для проверки флапа удобно запрашивать `max_over_time((<expr>)[1h:1m])` с
`step=1h`. Для discovery используй `label_values` и `series`, если результат
пустой: отдельный MCP может смотреть в другой VM-инстанс или tenant, а
неверный label/источник даст `result: []` без явной ошибки. Не делай вывод
«метрики отсутствуют», пока не проверил фактические labels и границу retention.

Если отдельный MCP недоступен, зафиксируй ошибку и используй локальный
`sre-toolbox.vm_query`/`vm_query_range` как fallback. Для справки по семантике
VictoriaMetrics доступен `mcp__victoriametrics__documentation`.

## VictoriaMetrics Select

VictoriaMetrics Select имеет Prometheus-совместимый API, поэтому используются стандартные эндпоинты `/api/v1/query`, `/api/v1/query_range`, `/api/v1/label/<name>/values`.

Этот раздел описывает локальные `sre-toolbox` tools. Для нового расследования
сначала используй отдельный MCP из раздела выше.

### Маршрут и тенанты

Tools ходят только в `victoriametrics.url`. Для кластерной VM удобно multitenant-чтение
(`/select/multitenant/prometheus`): видны все тенанты сразу, кластер выбирается label
`vm_account_id` (например 100 — prod, 200 — staging; список —
`vm_label_values("vm_account_id")`). URL и credentials параметрами tools не принимаются.

Общий лимит запроса и ответа задаётся в `victoriametrics.limits`: `request_timeout_seconds`, `max_timeout_seconds`, `max_range_seconds`, `min_step_seconds`, `max_step_seconds`, `max_points_requested`, `max_points_per_series` и `max_response_bytes`.

### `vm_query`

Instant PromQL-запрос. Возвращает текущее значение метрики.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `promql` | string | PromQL-выражение |
| `time_` | string? | RFC3339 timestamp, по умолчанию now |

**Меры безопасности**: проверяется allowlist разрешённых сервисов/неймспейсов. Ответ ограничен `max_series_returned` из конфига (по умолчанию 30 рядов).

Пример instant-запроса по prod:

```json
{
  "promql": "sum by (namespace) (kube_pod_container_status_restarts_total{vm_account_id=\"100\"})"
}
```

### `vm_query_range`

Range PromQL-запрос. По умолчанию возвращает **агрегаты** (min/max/avg/p50/p95/p99), а не сырые точки.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `promql` | string | PromQL-выражение |
| `start`, `end` | string | RFC3339 или Prometheus-style |
| `step` | string | По умолчанию `60s` |
| `summarize` | bool | Если `true` (по умолчанию) — агрегаты, не точки |

**Экономия**: `summarize=true` сжимает ответ в 50-200 раз. Если действительно нужны точки — `summarize=false`, тогда сервер всё равно прорежает их до `max_points_per_series`.

Пример range-запроса:

```json
{
  "promql": "sum(rate(container_cpu_usage_seconds_total{vm_account_id=\"100\", namespace=\"payments-prod\"}[5m]))",
  "start": "2026-10-16T00:00:00Z",
  "end": "2026-10-17T00:00:00Z",
  "step": "5m"
}
```

### `vm_label_values`

Список значений лейбла из `/api/v1/label/<name>/values`. Не возвращает данные, только идентификаторы.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `label` | string | Имя лейбла. Часто `__name__` (имена метрик), `job`, `service` |
| `match` | string? | Селектор `{service="x"}` для фильтрации |

Полезно для discovery: «какие метрики есть у сервиса X», «какие сервисы вообще пишут метрики».

---

## VictoriaLogs

VictoriaLogs — отдельный продукт VictoriaMetrics для логов с собственным языком запросов LogsQL. Основной эндпоинт — `/select/logsql/query` (стрим NDJSON).

### Тенанты

Tools ходят только в `victorialogs.url`. Тенант выбирается параметром `tenant`: имя или AccountID из
server-side карты `victorialogs.tenants`, по умолчанию `victorialogs.default_tenant`. MCP ставит
заголовки `AccountID` и `ProjectID: 0`, поэтому учётке нужен доступ ко всем тенантам (например
отдельный read-only пользователь vmauth). Неизвестный тенант возвращает список доступных; без карты заголовки не ставятся.

Пример запроса логов из тенанта payments-prod:

```json
{
  "tenant": "payments-prod",
  "logsql": "namespace:payments-prod error",
  "start": "2026-10-17T00:00:00Z",
  "end": "2026-10-17T06:00:00Z",
  "limit": 100,
  "mode": "patterns"
}
```

Лимиты задаются в `victorialogs.limits`: `request_timeout_seconds`, `max_timeout_seconds`, `max_query_window_hours`, `max_lines_returned`, `max_streams_returned`, `max_input_bytes` и `max_response_bytes`.

### `vl_query`

LogsQL-запрос к VictoriaLogs.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `logsql` | string | LogsQL-выражение, например `_stream:{service="api"} error` |
| `start`, `end` | string | RFC3339, окно запроса |
| `limit` | int? | максимум строк (потолок `max_lines_returned`) |
| `mode` | enum? | `patterns` (по умолчанию — кластеризация) или `lines` (сырьё) |
| `tenant` | string? | Имя или AccountID из `victorialogs.tenants`; по умолчанию `default_tenant` |

**Ключевая мера экономии — режим `patterns`**: сервер нормализует строки (числа → `<N>`, hex → `<HEX>`, длинные литералы → `<STR>`), группирует и возвращает топ-N шаблонов с счётчиками. Вместо «4521 похожих ERROR-строк» получается одна строка с `count=4521`.

**Лимит окна**: запросы шире `max_query_window_hours` (по умолчанию 24ч) отклоняются — защита от случайной выкачки.

### `vl_streams`

Список потоков (`_stream`) в VictoriaLogs через `/select/logsql/streams`. Полезно, чтобы понять, какие сервисы доступны.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `query` | string | LogsQL-фильтр, по умолчанию `*` |
| `limit` | int | Максимум потоков в ответе |
| `tenant` | string? | Имя или AccountID из `victorialogs.tenants`; по умолчанию `default_tenant` |

---

## База знаний (`kb.py`)

`kb_search` и `kb_list` загружают `kb.py` из agent-harness и возвращают разделы с диапазонами строк, а не документы
целиком. Путь к `kb.py` — `obsidian.kb_tool` (по умолчанию `../../tools/kb.py` относительно `mcp/sre-toolbox`),
корень базы — `paths.kb_root` из конфига harness. Заметки `obsidian.vault_path` добавляются, если vault — отдельная
папка (`include_obsidian`).

### `kb_search`

| Параметр | Тип | Описание |
|----------|-----|----------|
| `query` | string | Симптом, сервис, алерт, ключ задачи (`OPS-1234`) |
| `limit` | int | Сколько документов вернуть (по умолчанию 6, потолок 15) |
| `service`, `ticket`, `doc_type` | string? | Фильтры по метаданным документа |
| `include_obsidian` | bool | Искать и в заметках vault (по умолчанию `true`) |

### `kb_list`

Каталог (новые сверху) с фильтрами `service`, `ticket`, `doc_type`, `since` (YYYY-MM-DD), `limit` (потолок 100).

## Obsidian vault

Локальный knowledge base с runbooks, постмортемами и описаниями сервисов. Самый важный приём экономии токенов — см. [obsidian.md](./obsidian.md) для подробностей и шаблонов.

### `obsidian_search`

Поиск по vault. Простой term-overlap скоринг + бонус за совпадение в заголовке.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `query` | string | Ключевые слова: имя алерта, сервис, симптом |
| `top_k` | int | Сколько лучших совпадений вернуть (по умолчанию 5, потолок 20) |

Возвращает: `{count, vault_size, results: [{path, title, score, snippet}]}`. Snippets ограничены `snippet_chars` (400 символов по умолчанию).

### `obsidian_read_note`

Прочитать конкретную заметку, найденную через search.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `path` | string | Относительный путь от корня vault |

Защита от path traversal. Лимит `max_note_chars` (по умолчанию 8000).

### `obsidian_append_finding`

Записать новую заметку (накопительная память). По умолчанию выключено — включается через `obsidian.allow_writes: true`.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `title` | string | Заголовок — H1 и часть имени файла |
| `content` | string | Тело заметки в markdown |
| `folder` | string | Подпапка vault, по умолчанию `findings` |
| `tags` | list[string]? | Теги для frontmatter |

---

## Jira (Server / Data Center)

Личный PAT передаётся в `jira.auth.bearer_token` (заголовок `Authorization: Bearer ...`).
PAT выдаётся в Jira: `Profile` → `Personal Access Tokens` → `Create token`.

По умолчанию модуль работает **только на чтение**. Запись (создание задач,
обновление полей, transitions, комментарии) включается флагом
`jira.allow_writes: true`. Дополнительно можно ограничить набор проектов
через `jira.allow_projects`.

Ответы максимально сжаты: длинные `description`/`comments` обрезаются до
`limits.max_field_chars`, по умолчанию возвращается компактный набор полей
из `limits.default_fields`.

### `jira_get_issue`

| Параметр | Тип | Описание |
|----------|-----|----------|
| `key` | string | Ключ задачи, например `OPS-123` |
| `fields` | list[string]? | Поля; по умолчанию — из конфига |
| `with_comments` | bool | Подмешать N последних комментариев |

### `jira_search`

JQL-поиск. Поддерживает `startAt` для пагинации.

| Параметр | Тип | Описание |
|----------|-----|----------|
| `jql` | string | JQL-выражение |
| `fields` | list[string]? | Поля; по умолчанию — компактный набор |
| `limit` | int | Потолок `limits.max_issues_returned` |
| `start_at` | int | Offset для пагинации |

### `jira_create_issue` / `jira_update_issue` / `jira_transition_issue` / `jira_add_comment`

Все требуют `jira.allow_writes: true`. `jira_transition_issue` принимает имя
транзишена (а не id) — нужный id ищется автоматически.

### `jira_list_projects` / `jira_list_boards` / `jira_list_sprints` / `jira_sprint_issues`

Чтение через Agile API (`/rest/agile/1.0`). Удобно для «что у меня в спринте».

---

## Confluence (Server / Data Center)

Аналогично Jira — `confluence.auth.bearer_token` (отдельный PAT). По
умолчанию работает только на чтение.

Тело страницы возвращается как plain text (storage XHTML конвертируется
в текст без зависимостей) и обрезается до `limits.max_page_chars` —
это сжимает квартальный план на 100K символов в 12K, экономия токенов.

### `confluence_get_page`

| Параметр | Тип | Описание |
|----------|-----|----------|
| `page_id` | string? | ID страницы |
| `space` | string? | Space key (вместе с `title`) |
| `title` | string? | Точное название страницы |

### `confluence_search`

| Параметр | Тип | Описание |
|----------|-----|----------|
| `cql` | string | CQL-выражение |
| `limit` | int | Потолок `limits.max_search_results` |
| `include_body` | bool | Подмешивать ли тело страниц (дорого) |

### `confluence_get_page_children`

Список child-страниц. Полезно: получить корневую страницу плана, потом
пройтись по разделам.

### `confluence_get_bookmark`

Быстрый доступ к закреплённым страницам из `confluence.bookmarks` в конфиге:

```yaml
confluence:
  bookmarks:
    quarterly_plan:
      space: "TEAM"
      title: "Quarterly Plan Q3 2026"
```

Тогда `confluence_get_bookmark("quarterly_plan")` сразу возвращает страницу.

---

## Расширение собственными tools

В рабочей версии сервера легко добавить свои tools под вашу инфраструктуру:

- `get_recent_deploys` — последние N деплоев сервиса (из Argo CD / GitOps / собственного deploy-tracker).
- `correlate_alert_with_deploys` — был ли деплой в окне ±30 минут до алерта.
- `get_runbook` — runbook для конкретного алерта из Confluence / репозитория.

Шаблон добавления tool описан в [README](../../README.ru.md#расширение).

---

## Tools, которых сознательно НЕТ

Эти tools могли бы быть полезны, но мы их не добавляем по соображениям безопасности и стоимости:

- `get_full_repo` — нет. Если нужен код, есть `search_code` с лимитом 200 строк фрагмента.
- `restart_pod`, `scale_deployment` — нет в первой версии. Destructive actions добавляются только после периода обкатки и с обязательным human-in-the-loop.
- `raw_query` к произвольным API — нет. Только конкретные tools с провалидированными параметрами.
