---
name: contractor-report
description: "Разбор ежемесячного Excel-отчёта подрядчика о трудозатратах: часы по исполнителям и задачам, сверка с Jira, аномалии, страница в Confluence. Триггеры — «разбери отчёт подрядчика», «отчёт по часам подрядчика», «202605 отчёт»."
---

# Skill: contractor-report

Назначение — превращать ежемесячный Excel-файл от подрядчика (`contractor.name` в defaults.yaml) в аналитику в Confluence,
которую можно показать РО и подрядчику: суммарные часы по людям, топ задач,
дневная разбивка реальной работы и отдельная таблица задач с аномалиями.

Дефолты — [`defaults.yaml`](./defaults.yaml). **Не меняй их в рантайме — только через PR.** Перед первым запуском заполни раздел «Настройка под команду» ниже.

## Когда применять

* «разбери отчёт подрядчика за май»
* «сделай аналитику по Excel от подрядчика»
* «проверь отчёт — есть ли левые задачи»
* «202606 отчёт подрядчика DevOps»

Не применять для:
* Планирования задач — [`jira-planning-story`](../jira-planning-story/SKILL.md)
* Постмортемов — [`postmortem`](../postmortem/SKILL.md)

## Что делать (по шагам)

### 1. Прочитай дефолты

`defaults.yaml` содержит название подрядчика, id родительской страницы Confluence, проект Jira, пороги
аномалий, ожидаемую структуру Excel и нормализацию имён. Не подменяй на лету.

```python
import yaml
DEFAULTS = yaml.safe_load(open('<путь к скиллу>/defaults.yaml', encoding='utf-8'))
```

### 2. Найди Excel-файл

Если пользователь не указал путь — ищи в `~/Downloads/` файл, имя которого
содержит `contractor.file_hint` или паттерн `YYYYMM` + «DevOps». Если нашёл несколько —
**обязательно уточни у пользователя**, какой использовать (v1/v2 — разные данные).

### 3. Извлеки данные из Excel

Используй Python + `openpyxl` через Bash-инструмент:

```python
import openpyxl
from collections import defaultdict

wb = openpyxl.load_workbook('<путь>')
ws = wb['Данные отчета']

tasks = defaultdict(lambda: {'hours': 0, 'ext_key': '', 'title': '',
                              'persons': defaultdict(float), 'types': defaultdict(float)})
for row in ws.iter_rows(min_row=2, values_only=True):
    task, link, typ, comment, person, hours = row[0], row[1], row[2], row[3], row[4], row[5]
    if not task or not hours:
        continue
    ext_key = task.split(' ')[0]             # EXT-9xxx — ключ системы подрядчика, НЕ Jira
    jira_key = link.strip().split('/')[-1]   # последний сегмент URL — реальный Jira-ключ
    title = ' '.join(task.split(' ')[1:])
    tasks[jira_key]['ext_key'] = ext_key
    tasks[jira_key]['title'] = title
    tasks[jira_key]['hours'] += float(hours)
    tasks[jira_key]['persons'][person] += float(hours)
    tasks[jira_key]['types'][typ] += float(hours)
```

**Критично:** в колонке «Задача» стоят ключи системы подрядчика (EXT-8xxx/9xxx),
а реальные ключи Jira — в колонке «Ссылка» (последний сегмент URL, VND-1xxx).
Всегда используй ключи из ссылок для обращения к Jira.
Не путай: ключ подрядчика EXT-9237 ≠ ключ Jira; реальный ключ Jira для EXT-9237 — в поле link той же строки.
(Если у подрядчика и в Jira один префикс — путаница ещё опаснее: всегда бери ключ из ссылки.)

### 4. Запроси метаданные задач из Jira (HTTP напрямую)

MCP `jira_get_issue` / `jira_search` может быть ограничен `allow_projects` (по умолчанию `[{{TRACKER_PROJECT}}]`) — проект подрядчика
(`jira.project`) тогда недоступен через MCP. В этом случае используй прямой HTTP только на чтение с `JIRA_PAT` из `.env`
sre-toolbox; токен в чат и в код не вставляй:

```python
import os, httpx
from dotenv import load_dotenv

load_dotenv(os.path.expanduser('{{HARNESS_HOME}}/mcp/sre-toolbox/.env'))
PAT = os.environ['JIRA_PAT']
BASE = '{{TRACKER_URL}}/rest/api/2'
HEADERS = {'Authorization': f'Bearer {PAT}', 'Content-Type': 'application/json'}
VERIFY = os.environ.get('JIRA_CA_BUNDLE') or True   # свой CA — путь к PEM в .env; не отключать проверку
FIELDS = 'summary,status,assignee,timespent,issuetype,created,updated,resolution,description'

jira_data = {}
with httpx.Client(headers=HEADERS, verify=VERIFY, timeout=30) as c:
    for key in tasks.keys():
        r = c.get(f'{BASE}/issue/{key}', params={'fields': FIELDS})
        if r.status_code == 200:
            d = r.json()['fields']
            jira_data[key] = {
                'summary': d.get('summary', ''),
                'status': d.get('status', {}).get('name', ''),
                'timespent_h': round((d.get('timespent') or 0) / 3600, 2),
                'created': d.get('created', '')[:10],
                'resolution': (d.get('resolution') or {}).get('name', ''),
                'has_desc': bool((d.get('description') or '').strip()),
            }
        else:
            jira_data[key] = None
```

**Сверка целостности:** после получения всех задач убедись что
`jira_data[key]['timespent_h'] == tasks[key]['hours']` для каждой задачи.
Если подрядчик синхронизирует часы в Jira (`contractor.syncs_to_jira: true`) — расхождений быть не должно.
Если расхождение есть — сообщи пользователю до создания страницы.

### 5. Определи аномалии

**Категория A — catch-all / нет описания:**
* `not jira_data[key]['has_desc']` — пустое описание
* Название содержит «Проектирование и ревью», «Планирование» + формат `YYYYMM ...`

**Категория B — ретроспективное создание:**
* `created` > 25-го числа отчётного месяца — задача создана в конце периода

**Категория C — старый бэклог:**
* `created` < первого числа отчётного месяца (задача старше 1 месяца)
* `status == 'Бэклог'` (не закрыта)

Задача попадает в «Требующие внимания» при хотя бы одном признаке.

### 6. Вытащи дневные ворклоги из Jira

**Важно:** строй `day_person` по ворклогам из Jira — **никогда не составляй таблицы вручную**.
Ручное заполнение гарантированно даёт ошибки в датах и задачах.

```python
NAME_NORM = DEFAULTS['people']['name_norm']      # «как в Jira» → «как в отчёте», из defaults.yaml
EXCLUDE = set(DEFAULTS['people']['exclude'])      # кого не показывать в дневной разбивке
BUFFER_KEYS = set(DEFAULTS['buffer']['keys'])     # jira-ключи catch-all задач (VND-1370 и т.п.)
BUFFER_TYPES = {'PM'}

day_person = defaultdict(lambda: defaultdict(list))

with httpx.Client(headers=HEADERS, verify=VERIFY, timeout=30) as c:
    for key, task in tasks.items():
        # Пропускаем полностью буферные задачи
        if key in BUFFER_KEYS:
            continue
        non_pm_h = sum(h for t, h in task['types'].items() if t not in BUFFER_TYPES)
        if non_pm_h == 0:
            continue

        dom_type = max(task['types'].items(), key=lambda x: x[1])[0]
        r = c.get(f'{BASE}/issue/{key}/worklog', params={'maxResults': 200})
        if r.status_code != 200:
            continue

        for wl in r.json().get('worklogs', []):
            raw = wl['author'].get('displayName', '')
            name = NAME_NORM.get(raw, raw)
            if name in EXCLUDE:
                continue
            hours = round(wl['timeSpentSeconds'] / 3600, 2)
            date = wl['started'][:10]
            if hours > 0:
                day_person[date][name].append({
                    'key': key,
                    'title': task['title'][:55],
                    'hours': hours,
                    'type': dom_type,
                    'buffer': key in BUFFER_KEYS,
                })
```

**После сбора — обязательная валидация:**
```python
# Суммируем ворклоги по каждой задаче и сравниваем с Jira timespent
for key in tasks:
    wl_total = sum(
        e['hours']
        for day in day_person.values()
        for person_entries in day.values()
        for e in person_entries
        if e['key'] == key
    )
    jira_total = jira_data[key]['timespent_h']
    if abs(wl_total - jira_total) > 0.01:
        print(f'РАСХОЖДЕНИЕ {key}: worklogs={wl_total}h, jira={jira_total}h')
```
Если расхождений нет — пишем «Сверка <подрядчик> ↔ Jira: 0 расхождений» в шапку раздела.

### 7. Сформируй контент Confluence программно

**Всё строить программно из данных** — никогда не вписывать задачи или часы вручную.
Структура страницы:

```
h1. YYYYMM Аналитика трудозатрат DevOps (<подрядчик>)
<вводная строка: период, источник, без цен>

----

h2. Итого по исполнителям
<таблица: Исполнитель | [типы работ] | Итого>
(данные из tasks[key]['persons'] и типов)

h2. Распределение по типам работ
<таблица: Тип | Часы | Доля %>

h2. Топ-10 задач по трудозатратам
<таблица: # | [Jira-ключ|ссылка] Название | Часов>
ВАЖНО: ссылка = {{TRACKER_URL}}/browse/<jira_key> — брать из tasks dict,
НЕ из ключа подрядчика. Никогда не угадывать ссылку вручную.

----

h2. Реальная работа по задачам — разбивка по дням
<примечание: какие задачи исключены как буферные, кол-во расхождений>

h3. Сводная матрица (часов в день, без буферов)
<таблица: Дата | Чел1 | ... | Итого>

h3. Имя — X ч (без буферов)
<таблица: Дата | [Jira-ключ|ссылка] Название | Часов | Тип>
(ячейка Дата: значение для первой строки дня, пробел для остальных)

----

h2. ⚠ Задачи, требующие внимания
<категории A, B, C + итоговая таблица + {warning}>
```

Правила wiki markup:
* `h1.` / `h2.` / `h3.` — заголовки
* `|| col ||` и `| cell |` — таблицы
* `[Ключ|url]` — ссылки
* `*текст*` — жирный, `{note}`, `{warning}` — блоки
* Без markdown (`#`, `**`, `---` — не работают в Confluence wiki)

### 8. Превью и подтверждение

Если `behavior.confirm_before_create: true`, перед созданием покажи:
* заголовок страницы
* суммарные числа: часов всего, исполнителей, задач
* кол-во задач под вопросом и их долю
* спроси «создавать?»

### 9. Создай страницу в Confluence

```python
confluence_create_page(
    space=<confluence.space>,
    title=<заголовок>,
    parent_id=<confluence.parent_page_id>,
    content=<полный wiki markup>,
    content_format="wiki"
)
```

### 10. Верни результат

* ссылка на созданную страницу
* 3–5 строк: суммарные часы, число исполнителей, число задач под вопросом
* если есть задачи категории A — особо выдели (самый высокий риск)

## Известные особенности (обязательно учитывай)

**Двойная нумерация задач.** У подрядчика может быть своя система ключей (EXT-8xxx/9xxx),
которые не совпадают с реальными ключами Jira (VND-1xxx). Реальный ключ
всегда берётся из колонки «Ссылка» Excel. Проверка: `jira_data[jira_key]['summary']`
должна совпадать с `task['title']` — если не совпадает, ключ взят неверно.

**Пустой displayName в ворклогах.** У некоторых аккаунтов Jira displayName пустой. Сопоставь пустую строку
с нужным человеком в `people.name_norm` (`'': 'Имя Фамилия'`), иначе его часы пропадут из дневной разбивки.

**Jira `timespent` = часы подрядчика**, если он синхронизирует данные обратно в Jira из своей системы.
Тогда расхождений по суммам быть не должно; если есть — это баг синхронизации.

**Дневные ворклоги строго из API.** Нельзя восстанавливать даты из суммарных данных
Excel — там дат нет. Только `/worklog` endpoint даёт точные даты списания.
Итоги без буферов у разных людей не совпадают с итогами подрядчика: его итоги включают буферные задачи,
дневной раздел — нет. Это нормально, указывай обе цифры отдельно.

**Ссылки в Топ-10 и таблицах** — всегда генерировать программно из `jira_key`,
никогда не вписывать URL вручную. Ошибки в ручных ссылках (VND-1401 вместо VND-1388)
приводят к тому, что пользователь переходит на чужую задачу.

## Worked example

Пользователь: «сделай аналитику по 202605 Данные к РО (DevOps) v2 (1).xlsx»

Скилл:
1. Читает дефолты.
2. Находит файл в `~/Downloads/` — если несколько версий, спрашивает.
3. openpyxl: 146 строк, 63 Jira-ключа (VND-1xxx), 9 исполнителей, 616,5 ч.
4. HTTP к Jira: все 63 задачи найдены, все в «Бэклог», timespent = часы подрядчика.
5. Аномалии: VND-1370 catch-all (195 ч), 18 задач от 29.05 (80,5 ч), 8 старых бэклогов (66,5 ч).
6. Ворклоги: 19 дней активности, нормализация '' → имя из `people.name_norm`, 0 расхождений.
7. Весь контент страницы строится программно — никаких ручных таблиц.
8. Создаёт страницу под страницей планирования работ подрядчика (parent_id <ID страницы планирования работ подрядчика>).
9. Возвращает ссылку + сводку.

## Настройка под команду

В `defaults.yaml`: `contractor.name` (как подписывать страницу), `contractor.file_hint` (подстрока в имени
файла), `jira.project` (проект, где живут задачи подрядчика), `confluence.parent_page_id`, колонки листа Excel,
`people.name_norm` и `people.exclude`, `buffer.keys` (catch-all задачи). Формат Excel у другого подрядчика может
отличаться — поправь `excel.*` и разбор в шаге 3.

## Чего НЕ делать

* Не включать цены (Ставка, Сумма) — только часы.
* Не использовать MCP `jira_get_issue` / `jira_search` для проекта подрядчика, если он не в `allow_projects`.
* Не вписывать URL задач вручную в таблицы — всегда программно из `jira_key`.
* Не составлять дневные таблицы вручную — только из `/worklog` API.
* Не использовать ключи подрядчика (EXT-9xxx) как Jira-ключи — это разные системы.
* Не выдумывать причины аномалий — только факты. Интерпретацию даёт пользователь.
* Не создавать страницу в другом space или под другим родителем без явной просьбы.
* Не использовать markdown в теле Confluence — только wiki markup.
* Если файлов несколько (v1, v2) — спрашивать, не угадывать.
