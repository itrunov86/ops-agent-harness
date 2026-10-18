---
type: request
date: {date}
tickets: [{ticket_key}]
services: [{service}]
status: "{status}"
summary: "{symptom} → {cause} → {fix}"
tags: [{tags}]
---

# {ticket_or_slug} — {short_title}

Дата обращения: {date}
Источник обращения: [чат]({chat_url})
Связанная задача: [{ticket_key}]({tracker_url})
Сервис/компонент: {service}
Среда: {environment}

## Суть обращения

{summary}

## Диагностика

{diagnosis_steps}

## Причина

{root_cause}

## Предложенное решение

{proposed_solution}

> Статус: предложено, не применено. Изменения в GitOps/коде/инфраструктуре
> вносятся только после отдельного явного подтверждения.

## Проверено (read-only)

| Объект | Результат |
|---|---|
| {check_1} | {result_1} |

## Похожие обращения

{related_docs_or_none}

## Ссылки

* Репозиторий: {repo_links}
* Чат: {chat_url}
* Трекер: {tracker_url}
