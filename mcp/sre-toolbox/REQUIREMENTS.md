# Требования к работе с репозиторием

Эти правила применяются ко всем сессиям агентов, которые меняют `mcp/sre-toolbox`.

## Git

- Коммиты и MR — по правилам agent-harness ([CONTRIBUTING.md](../../CONTRIBUTING.md)); `config.yaml`, `.env`, `teams.md`, `certs/` в git не попадают.
- Перед коммитом: `python3 scripts/check_sanitized.py` из корня harness — ни имён организации, ни внутренних хостов.

## Структура

- Командные скиллы живут в `../../team-skills/` agent-harness, не здесь.
- Tools живут в `tools/` — по одному файлу на интеграцию. Каждый экспортирует `register(mcp, cfg, client_factory, redactor, audit_fn)`.
- Новый tool к существующей интеграции — добавить в `tools/X.py` внутри `register()`.
- Новая интеграция — добавить блок в конфиг + `_client_X` в `server.py` + `tools/X.py` + вызов register.

## Код

- Тела Jira/Confluence — всегда **wiki markup** (`h1.`, `*bold*`, `*` списки, `||` таблицы), не markdown.
- Все ответы tools прогонять через `redactor.scrub_any(...)` перед возвратом.
- `print` в stdout запрещён — ломает stdio-протокол. Логировать через `logging`.

## Knowledge base (Obsidian)

- Перед дорогим анализом (логи/метрики/прод) — сначала `obsidian_search`.
- После нетривиального разбора — `obsidian_append_finding` с параметром `related_notes` для `[[wikilinks]]`.
- Скиллы, порождающие знание (`postmortem` и др.), должны включать шаг записи в vault.

## Документация

- При изменении архитектуры обновлять: `AGENTS.md`, `README.md`, `docs/architecture.md`.
- Упоминания удалённых фич (Redis-кэш, Postgres audit) — убирать из всех файлов.
