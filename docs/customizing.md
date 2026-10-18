# Настройка под себя

Правьте **репозиторий** (лучше — свой форк), а не установленные копии: `~/.agents/skills` и правила перезаписывает
следующий `install`.

## Свой скилл

```text
skills/my-skill/
  SKILL.md              # обязательно: frontmatter name + description, затем инструкция
  agents/openai.yaml    # необязательно: метаданные для Codex
  references/ templates/
```

```markdown
---
name: my-skill
description: "Что делает и когда включать. Триггеры — «фраза пользователя», «другая фраза». Чем не является — other-skill."
---

# my-skill

Шаги с критерием «готово, когда …» на каждом. Что читать, какой инструмент взять (возможность + пример + запасной
путь), чем закончить.
```

Советы:

- `description` — единственное, по чему агент решает включить скилл: перечислите реальные фразы и границы с
  соседними скиллами.
- Значения, зависящие от работы, — подстановками `{{KB_ROOT}}`, `{{TICKET_EXAMPLE}}`… ([CONTRIBUTING.md](../CONTRIBUTING.md)).
- Пишущие шаги — с черновиком и подтверждением.
- Перед правкой скилла вызовите скилл `writing-for-agents` — там правила текста для агентов.

Поставить: `./harness install`. Проверить подстановки: `./harness render skills/my-skill/SKILL.md`.

Скилл только для себя на этой машине — в `skills.exclude` его нет смысла держать; положите в репозиторий и
поставьте, или держите вне репозитория прямо в `~/.agents/skills/` (harness его не тронет: у него нет метки
`.harness-managed`).

## Правила агентов

`templates/global/AGENTS.md` — общие правила, `templates/global/CLAUDE.md` — добавки для Claude Code. Правило,
которое агент нарушает механически (шаблон команды, путь), лучше закрыть проверкой (права в `settings.json`, хук,
lint), чем ещё одной строкой в правилах: правила — для решений, проверки — для механики.

## Хуки

Обработчик — `tools/agent_session.py` (`cmd_hook`). Новое поведение добавляйте туда же, с тестом в
`tests/test_agent_session.py`. Хук не должен падать и блокировать: любая ошибка — молчаливый выход.

## Субагенты

`agents/claude/*.md` (frontmatter Claude Code: `name`, `description`, `model`, `disallowedTools`) и
`agents/codex/*.toml`. Модели в файлах — примеры. Новый агент Claude Code виден только в сессиях, начатых после
установки.

## Проверка изменений

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_sanitized.py
./harness install --dry-run
```

Помогла ли правка в работе — [evaluation.md](evaluation.md).
