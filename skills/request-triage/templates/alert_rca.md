---
type: rca
date: {date}
tickets: [{ticket_key}]
services: [{service}]
status: "{status}"
summary: "{symptom} → {cause} → {fix}"
tags: [{alertname}, {tags}]
---

# {ticket_or_slug} — {short_title}

Дата алерта: {date}
Алерт: `{alertname}`, severity `{severity}`
Namespace/сервис: {namespace_service}
Среда: {environment}
Источник: [чат]({chat_url})
Связанная задача: [{ticket_key}]({tracker_url})

## Краткий вывод

{summary}

## Подтверждённые факты

{evidence_bullets}

## Причина

{root_cause}

## Предложенное решение

{proposed_solution}

> Статус: предложено, не применено (если фикс уже выкатан и подтверждён —
> замени формулировку на факт и добавь раздел «Как исправили» + Timeline
> по примеру прошлого RCA в `alerts/`).

## Проверка при повторении (read-only)

```bash
{verification_commands}
```

## Похожие алерты/инциденты

{related_docs_or_none}

## Ссылки

* Grafana/VM/VL: {observability_links}
* Чат: {chat_url}
* Трекер: {tracker_url}
