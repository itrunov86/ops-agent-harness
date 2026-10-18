---
name: daily-report
description: Use this skill only when the user writes exactly "Сформируй daily report". Create or append a concise Russian daily SRE/DevOps Markdown report in the knowledge base. Do not use for incident reports, postmortems, runbooks, or generic report requests.
---

# Daily SRE/DevOps Report

## Trigger Guard

Use this skill only when the latest user request contains the exact phrase:

`Сформируй daily report`

If the phrase is absent, do not create or update a daily report. Continue without this skill.

This skill is separate from incident reports, postmortems, runbooks, and findings saved to vault. Do not use it for incident-summary persistence unless the user explicitly uses the trigger phrase above.

## Goal

Create a concise Markdown report in Russian for the current day's agent work, using only the available chat context, accessible project files, and commands actually run in the current conversation.

Do not invent tasks, commands, causes, diagnostic results, fixes, or outcomes. When information is missing, write one of:

- `Не указано`
- `Не зафиксировано`
- `Требует уточнения`

## Output File

Directory:

`{{KB_ROOT}}/daily_report`

Filename format:

`DD_MM_YY_report.md`

Example:

`30_05_26_report.md`

Use the user's current local date and time. If needed, run `date '+%d.%m.%y %H:%M'` to confirm.

The directory is the knowledge base root from the harness config plus `daily_report`; to keep reports elsewhere, change the path in your installed copy.

## Write Rules

1. Ensure the output directory exists.
2. If today's report file does not exist, create it.
3. If today's report file exists, append a new block to the end.
4. Each task block must start and end with exactly 80 `=` characters:

`================================================================================`

5. If filesystem sandboxing blocks the write, request approval for the required file operation instead of choosing another path.

## Report Template

Create one block per independent task or problem discussed in the current conversation.

````markdown
================================================================================

# Отчет за DD.MM.YY

**Время составления:** HH:MM
**Контекст:** краткое описание темы общения

## 1. Задача / проблема

Кратко описать, с какой задачей или проблемой пришел пользователь.

## 2. Что было сделано

* Описать выполненные или предложенные действия.
* Указать важные изменения, проверки, исправления.
* Не добавлять действия, которых не было в общении.

## 3. Диагностические команды

Если команды были, перечислить каждую отдельно:

```bash
команда
```

**Назначение:** зачем использовалась команда.  
**Результат:** какой результат был получен или `Не зафиксировано`.

Если диагностических команд не было:

`Диагностические команды не использовались.`

## 4. Итог

**Статус:** Решено / Частично решено / Не решено / Требует проверки / Требует уточнения

Кратко объяснить итог.

================================================================================
````

## Status Selection

- `Решено` - задача доведена до рабочего состояния и это подтверждено.
- `Частично решено` - часть задачи выполнена, но остались незавершенные действия.
- `Не решено` - проблема не устранена.
- `Требует проверки` - решение предложено или применено, но результат не подтвержден.
- `Требует уточнения` - не хватает данных для корректного вывода.

## Style

- Write in Russian.
- Keep the report brief, technical, and factual.
- Do not retell the whole dialog.
- Focus on task, actions, diagnostic commands, and outcome.
- Format commands only as fenced Markdown code blocks.
- Do not include secrets, tokens, private keys, kubeconfigs, secret-store values, OAuth/JWT values, or customer data.

## Final Response

After writing the file, reply with exactly one of these messages, using the real date and path:

- `Отчет за DD.MM.YY сохранен в: {{KB_ROOT}}/daily_report/DD_MM_YY_report.md`
- `Отчет за DD.MM.YY дописан в существующий файл: {{KB_ROOT}}/daily_report/DD_MM_YY_report.md`
