[English](../victoriametrics-mcp.md) · **Русский**

# Отдельный MCP-сервер VictoriaMetrics

## Подключение

Если у вас есть отдельный HTTP-сервер VictoriaMetrics MCP, подключите его через `.mcp.json` проекта (пример — [`.mcp.example.json`](../../.mcp.example.json)):

```json
{
  "mcpServers": {
    "victoriametrics": {
      "type": "http",
      "url": "https://vm-mcp.example.com/mcp"
    }
  }
}
```

После перезапуска Claude Code/Claude Desktop инструменты сервера доступны с
именами вида `mcp__victoriametrics__query_range`.

Это отдельный MCP-сервер VictoriaMetrics, а не `vm_query_range` из локального
`sre-toolbox`. Локальные `vm_*` tools используют `config.yaml` и могут идти
через настроенный endpoint или Grafana datasource proxy. Для получения самих
метрик приоритет всегда у отдельного `victoriametrics` MCP; локальный
`sre-toolbox.vm_*` — fallback, если отдельный сервер недоступен.

Не используй Grafana или произвольный HTTP/curl для получения метрик, если
доступен MCP. Grafana можно использовать для дашбордов, alert rules и
контекста источника.

## Основные tools

| MCP tool | Назначение |
|---|---|
| `mcp__victoriametrics__query` | Instant PromQL/MetricsQL-запрос |
| `mcp__victoriametrics__query_range` | Range-запрос за интервал |
| `mcp__victoriametrics__label_values` | Значения заданного label |
| `mcp__victoriametrics__series` | Discovery временных рядов по selector |
| `mcp__victoriametrics__metrics` | Имена доступных метрик |
| `mcp__victoriametrics__metrics_metadata` | Тип, help и unit метрики |
| `mcp__victoriametrics__rules` | Recording/alerting rules |
| `mcp__victoriametrics__alerts` | Pending/firing alerts |
| `mcp__victoriametrics__documentation` | Поиск официальной документации VictoriaMetrics |

`query` принимает `query`, опционально `time`, `step`, `timeout`, `nocache` и
возвращает instant result. `query_range` принимает `query`, `start`, `end`,
`step`, опционально `timeout` и `nocache`.

Пример:

```text
mcp__victoriametrics__query_range(
  query='sum(rate(http_requests_total{service="checkout"}[5m]))',
  start='2026-07-21T10:00:00Z',
  end='2026-07-21T11:00:00Z',
  step='1m',
  nocache=true
)
```

## Правильный порядок работы

1. Перед дорогим расследованием сначала проверь `obsidian_search` в
   `sre-toolbox` — готовый runbook может уже содержать PromQL и контекст.
2. Получив PromQL из алерта, правила или runbook, сначала выполни его через
   `mcp__victoriametrics__query` или `mcp__victoriametrics__query_range`.
3. Начни с узкого окна вокруг события. Для проверки длительности превышения
   threshold используй шаг `1m` или фактический шаг данных.
4. Для проверки flap/истории используй более широкое окно и агрегирующий
   subquery, например `max_over_time((<expr>)[1h:1m])` с `step=1h`.
5. В результате укажи источник, точное окно и timezone (обычно UTC), selector,
   threshold, максимум и длительность превышения. Не смешивай данные этого
   сервера с Grafana proxy без явной пометки.

## Формат результата и экономия токенов

`query_range` отдельного MCP возвращает стандартный Prometheus-ответ с сырыми
точками вида `[unix_timestamp, value]`. У него нет параметра `summarize`, как у
локального `sre-toolbox.vm_query_range`, поэтому:

- для обычного просмотра предпочитай агрегирующие PromQL/MetricsQL-выражения;
- для длинного окна увеличивай `step`, но не пропускай короткие пики;
- при необходимости сворачивай точки локально в min/max/avg/p95 и сохраняй
  timestamp пика;
- не передавай модели большой массив сырых точек без необходимости.

## Пустой результат — не доказательство отсутствия метрики

Отдельный MCP может смотреть в другой VM-инстанс или tenant, чем источник
алерта. `result: []`, `seriesFetched: 0` или пустой `query_range` сначала нужно
проверить:

```text
mcp__victoriametrics__label_values(
  label_name='namespace',
  match='{__name__=~"..."}',
  limit=100
)
```

Если label называется иначе, проверь `exported_namespace`, `service`, `job`
и другие labels через `label_values` или `series`. Только после discovery
делай вывод: данных нет, label указан неверно или подключённый MCP смотрит не
в тот источник.

Не выдумывай PromQL, labels, retention или глубину истории. Если сервер
возвращает данные только начиная с более поздней даты, фиксируй фактическую
границу retention.

## Ограничения и безопасность

- URL datasource, tenant, credentials и токены не являются аргументами tools.
- Все запросы к production должны быть read-only и максимально узкими.
- Для вопросов о семантике VictoriaMetrics сначала используй
  `mcp__victoriametrics__documentation`, а не догадки.
- Если отдельный сервер недоступен, явно сообщи об этом и используй
  `sre-toolbox.vm_query`/`vm_query_range` как fallback; не подменяй ошибку
  нулевыми метриками.
