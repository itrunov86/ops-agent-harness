---
name: jira-planning-epic
description: "Эпик в Jira с подзадачами (Epic Name, Epic Link). Триггеры — «заведи эпик про X», «оформи эпик и подзадачи». Квартальная цель — quarterly-planning, одиночная задача — jira-planning-story."
---

# Skill: jira-planning-epic

Назначение — создать в Jira эпик и (если перечислены) подзадачи под ним по
единому командному паттерну с правильным Epic Name / Epic Link.

Скилл фокусируется на **Jira-части**. Confluence-структура и формулировка
цели в квартальном плане живут в [`quarterly-planning`](../quarterly-planning/SKILL.md);
этот скилл вызывается оттуда для шага «создать Jira-артефакты», либо
работает самостоятельно для эпика, не привязанного к квартальному плану.

Шаблон тела эпика — [`templates/epic.wiki`](./templates/epic.wiki).
Дефолты команды (project, customfield'ы, лейблы) — в
[`defaults.yaml`](./defaults.yaml).
**Никогда не правь шаблон/дефолты в рантайме — только через PR.**

## Когда применять

* «заведи эпик про cleanup tech debt»
* «нужен epic под миграцию X»
* «создай эпик и нарежь подзадачи: A, B, C»
* Вызывается изнутри [quarterly-planning](../quarterly-planning/SKILL.md) для Jira-шага.

Не применять для:

* Квартальной цели команды как самостоятельной задачи — используй
  [quarterly-planning](../quarterly-planning/SKILL.md), он сам делегирует
  Jira-часть сюда.
* Обычной плановой задачи / Story — [jira-planning-story](../jira-planning-story/SKILL.md).
* Багов и инцидентов.
* Подзадач под уже существующий эпик — `jira_create_issue` + `jira_update_issue`
  с `customfield_<Epic Link>` напрямую.

## Что делать (по шагам)

### 1. Прочитай дефолты

`defaults.yaml` — контракт команды. Не подменяй значения «на лету». Если
пользователь явно сказал «в другой проект» — перебивай дефолт его словами.

### 2. Собери данные

Если ты вызван из `quarterly-planning`, входные данные уже сформированы
(summary, описание, список подзадач) — переходи к шагу 4.

Если стандалон-вызов — собери:

* *summary* эпика (≤120 символов, без точки в конце);
* *Epic Name* — короткое имя (1–4 слова) для customfield Epic Name;
* *описание*: проблема, что хотим получить, как поймём (см. шаблон
  `templates/epic.wiki`);
* *подзадачи* (если есть) — список с короткой формулировкой каждой.

Если чего-то не хватает, задай **одно** компактное уточнение, не
раскидывай вопросы.

### 3. Отрендери тело эпика

Используй [`templates/epic.wiki`](./templates/epic.wiki) как структурный
ориентир. Все списки оформляй в Jira wiki markup:

* `h1./h2.` для заголовков;
* `*` или `**` для буллетов / вложенных буллетов;
* `[label|https://...]` для ссылок;
* `{{...}}` для inline-кода;
* `{noformat}...{noformat}` или `{code:language}...{code}` для блоков.

Никакого markdown (`#`, `**`, `-`).

### 4. Покажи превью

Если `behavior.confirm_before_create: true` — покажи summary, project,
issue_type, лейблы, рендер тела (~10 строк), список подзадач. Спроси:
«создавать?». Если `false` — пропускай.

### 5. Создай эпик

```
jira_create_issue(
  project=<project_key>,
  issue_type=<issue_type>,                # обычно "Epic"
  summary=<summary>,
  description=<wiki body>,
  labels=<jira.labels + пользовательские + квартальный, если уместно>,
  priority=<jira.priority>,
  assignee=<jira.default_assignee>,
  extra_fields={"<epic_name_field>": "<Epic Name>"}
)
```

Важно:

* `epic_name_field` берётся из `defaults.yaml` (на вашем инстансе —
  `customfield_<ID Epic Name>`). Без него Jira вернёт 400 «Epic Name обязательно».
* Если `epic_name_field` в дефолтах `null` — спроси у пользователя или
  попробуй создать без него (узнаешь из текста ошибки).

После успеха — запомни `key` и `url` эпика.

### 6. Создай подзадачи (если перечислены)

Только если `behavior.create_children_if_listed: true` и пользователь
их перечислил. Иначе пропускай.

Описание каждой подзадачи обязательно включает четыре блока строго в
этом порядке:

* `h1. Зачем мы это делаем` — 1–3 фразы про проблему/последствия именно
  для этой задачи (не для эпика в целом). Без этого блока таск выглядит
  «потому что было в плане», и исполнитель не понимает контекста.
* `h1. Что нужно сделать` — постановка одной-двумя фразами.
* `h1. Что считаем готовым` — 2–4 проверяемых критерия (артефакты,
  чек-листы, метрики).
* `h1. Контекст` — ссылки на эпик и (если есть) страницу квартала.

Если у тебя нет основания для «Зачем» — спроси у пользователя, не сочиняй.

Если `behavior.confirm_children_before_create: true` — сначала покажи
список «создаю N подзадач под <KEY>?» и жди подтверждения.

Для каждой:

```
jira_create_issue(
  project=<project_key>,
  issue_type=<child_issue_type>,          # обычно "Task"
  summary=<summary>,
  description=<wiki по 4 блокам выше>,
  labels=<jira.child_labels + квартальный, если уместно>,
  priority=<jira.priority>,
  assignee=<jira.default_assignee>,
  extra_fields={"<epic_link_field>": "<EPIC-KEY>"}    # сразу линкуем
)
```

* `epic_link_field` берётся из `defaults.yaml` (на вашем инстансе —
  `customfield_<ID Epic Link>`). Это **не** `parent_key` — последний только для
  Sub-task.
* Если `epic_link_field` в дефолтах `null` — найди его одним из способов:
  1. `jira_get_issue` на любой существующей задаче проекта с привязкой
     к эпику; через `httpx` или `curl` запросить `fields=*all` и найти
     `customfield_XXXXX` со значением вида `<PROJECT-NNN>`.
  2. Спросить пользователя.
  После того как нашёл — попроси прописать в `defaults.yaml` через PR.

Если хотя бы одна подзадача не создалась/не слинковалась — не падай
молча, перечисли в финальном сообщении, что вышло, а что нет.

### 7. Верни результат

Коротко (3–6 строк):

* `*<EPIC-KEY>* — <summary>` (ссылкой);
* лейблы;
* список ключей подзадач одной строкой («созданы и слинкованы:
  {{TRACKER_PROJECT}}-…, {{TRACKER_PROJECT}}-…»);
* если что-то не вышло — отдельной строкой, прямо.

Если ты вызван из `quarterly-planning` — верни также объект с ключами
и URL'ами, чтобы родительский скилл смог прописать обратные ссылки в
Confluence.

## Worked example (standalone-эпик, без квартальной привязки)

Пользователь: «заведи эпик про чистку флапающих алертов, подзадачи —
аудит топ-20 флапающих, правила муты, owner-review».

Скилл:

1. `defaults.yaml` → project={{TRACKER_PROJECT}}, issue_type=Epic, labels=[from-claude,
   planning, epic], assignee={{TRACKER_ASSIGNEE}}, epic_name_field=customfield_<ID Epic Name>,
   epic_link_field=customfield_<ID Epic Link>.
2. Собирает данные. Уточняет одно: «как поймём, что готово?». Получает:
   «количество флапающих алертов <5 за неделю».
3. Рендерит тело по `templates/epic.wiki`.
4. Показывает превью, получает «да».
5. `jira_create_issue(project="{{TRACKER_PROJECT}}", issue_type="Epic",
   summary="Чистка флапающих алертов: аудит, муты, ownership",
   description=<wiki>, labels=[from-claude,planning,epic,observability],
   priority="Medium", assignee="{{TRACKER_ASSIGNEE}}",
   extra_fields={"customfield_<ID Epic Name>": "Чистка флапающих алертов"})`
   → `OPS-3000`.
6. Создаёт 3 подзадачи с правильным шаблоном описания и линкует через
   `customfield_<ID Epic Link>`.
7. Возвращает короткий отчёт со ссылками.

## Чего НЕ делать

* Не использовать `parent_key` для линковки Task → Epic — это поле
  предназначено только для Sub-task. Только Epic Link customfield.
* Не создавать эпик в проекте, не упомянутом в `defaults.yaml` /
  сообщении пользователя.
* Не использовать markdown в теле — только Jira wiki markup.
* Не дублировать создание: если в чате уже создавался этот эпик
  (есть `key` в истории) — предложить обновить через `jira_update_issue`.
* Не вписывать в описание секретов, паролей, токенов, доменов из
  `redaction` в `config.yaml`.
* Не падать молча при ошибке создания дочерней задачи.
* Не управлять Confluence-страницами квартала — это зона
  `quarterly-planning`. Если квартальная цель упомянута пользователем —
  лучше передай управление в `quarterly-planning`.
