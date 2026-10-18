---
name: mattermost-alerts-digest
description: "Сводка алертов из канала Mattermost за окно (по умолчанию 24 ч): повторы, flapping, затяжные, шумные namespace. Триггеры — «проверь алерты за день», «дайджест по infra-alerts», «что было в алерт-канале за ночь». Один алерт — request-triage."
---

# Skill: mattermost-alerts-digest

Назначение — дать команде быструю сводку по алерт-каналу: что было за окно,
что повторялось, что подозрительно. Цель — не пересказывать каждое
сообщение, а вытащить *сигнал* из шума.

Дефолты (канал, окно, пороги аномалий, поля парсера) — в
[`defaults.yaml`](./defaults.yaml). **Никогда не правь дефолты в рантайме
— только через PR.**

## Когда применять

* «проверь алерты за день»
* «дай дайджест по infra-alerts»
* «какие алерты повторялись за ночь»
* «что у нас в алертах за последние X часов»
* На дежурке утром — «что я пропустил».

Не применять для:

* Разбора одного конкретного инцидента — `mm_get_thread(post_id)` или
  `mm_resolve_permalink(url)` дают точечный ответ.
* Создания задач из инцидента — для этого есть jira_create_issue
  (или скилл `jira-planning-story`).
* Анализа сообщений в нон-алерт каналах — структура парсера заточена под
  Alertmanager-нотификации, в обычной переписке даст мусор.

## Что делать (по шагам)

### 1. Прочитай дефолты

`defaults.yaml` — контракт. Если пользователь явно указал другой канал /
окно — перебивай дефолт его словами.

### 2. Разреши канал

* Если у тебя нет `channel_id` — вызови `mm_list_channels(team=<default_team>)`
  и найди канал по `name == <default_channel>`. Запомни `id`.
* Если в чате уже был resolved канал (есть `channel_id` в истории) — используй его.

### 3. Вытащи посты за окно

* Вычисли `since_ms = now_ms - window.hours * 3600 * 1000`.
* `mm_list_channel_posts(channel_id=<id>, since_ms=<since_ms>, per_page=200)`.
* Если ответ содержит `next_post_id` ≠ null — значит, постов больше, чем
  одна страница. Пагинируй через `mm_list_channel_posts(channel_id,
  before=<oldest_post_id_so_far>, per_page=200)`, пока:
  * либо все ответы пустые,
  * либо самый старый пост в полученной странице старше `since_ms`,
  * либо собрано `window.max_pages` страниц (защита от убегания).
* Объедини и отсортируй посты по `create_at` (возрастание).

### 4. Парсинг сообщений

Для каждого поста извлеки:

* **`status`** — по первому совпадению с `parser.status_emoji`.
* **`alert_name`** — первое `**...**` в сообщении, чьё содержимое **не**
  входит в `parser.field_names`. Пример: `**ExternalSecretNotReadyNonProd**`
  — это имя; `**Severity**` — поле.
* **`severity`** — после `**Severity**:`.
* **`namespace`** — после `**Namespace**:`.
* **`cluster`** — после `**K8s cluster**:` или `**Cluster**:`.
* **`description`** — после `**Description**:` (первая строка).

Классификация поста:

* Если первая строка содержит маркер из `parser.ticket_markers` — это
  `ticket` (авто-регистрация задачи), отдельная категория, не «алерт».
* Если нет ни одного эмодзи статуса И нет `**AlertName**` — это `chat`
  (человеческое сообщение в треде). В дайджесте игнорировать.
* Иначе — `alert` со статусом из эмодзи.

### 5. Агрегация

Посчитай:

* **Объём** — N всего, M алертов, K тикетов, C чата.
* **Топ по `alert_name`** — Counter + распределение статусов (firing /
  warning / resolved) и severity.
* **Топ по `namespace`** — Counter.
* **По severity** — Counter (critical / warning / info).
* **Хронология тикетов** — какие auto-tickets создались, когда.

### 6. Поиск аномалий

* **🔁 Flap-кандидаты:** `alert_name`, у которого общее количество ≥
  `anomalies.flap_threshold`. Если все статусы — `resolved`/`warning` без
  ongoing firing, это явный flap. Стоит подсветить.
* **🔥 Ongoing firing:** алерты со статусом `firing` (или последний
  статус в треде с этим именем) без последующего `resolved` в окне.
  Проверка: у `alert_name` есть пост с `firing` позже самого позднего
  `resolved` (либо `resolved` вообще нет).
* **🌶️ Нездоровые namespace:** namespace, где встречаются ≥
  `anomalies.unhealthy_namespace_distinct_alerts` **разных** типов
  алертов (не повторов одного). Это уже не флап — кластер сам по себе плохо.
* **💥 Burst:** скользящее окно `anomalies.burst_minutes` минут с ≥
  `anomalies.burst_count` алертов. Если есть — упомяни время и количество.

### 7. Сборка сводки

Markdown, ≤30 строк, в таком порядке:

```
## Алерты {channel} за {window_human}  ({from_time} → {to_time})

**Объём:** N сообщений → M алертов ({firing} firing, {warning} warning,
{resolved} resolved) + {tickets} тикетов.

### 🔥 Открытые critical            ← только если есть ongoing firing
| Время | Алерт | Где | Кратко |
|...|

### 🔁 Подозрения на flap            ← только если есть кандидаты
| Алерт | × | Severity | Где |
|...|

### 🌶️ Нездоровые namespace          ← только если есть
| Namespace | × разных | Имена алертов |
|...|

### 💥 Всплеск                       ← только если есть burst
В {time} — {N} алертов за {Δ} минут: {имена}

### 📊 Топ по типу
{top_alerts_rows строк: имя × кол-во, severity, статусы}

### 🧭 Топ по namespace
{top_namespaces_rows строк: имя × кол-во}
```

Что НЕ выводить:

* полный список тикетов — достаточно числа;
* хронологию каждого сообщения — пользователь её увидит в Mattermost;
* «человеческие» сообщения и реакции.

Если `behavior.use_tables: false` — заменяй таблицы на компактные списки
вида `* Name — count, severity`.

### 8. Опционально: предложи следующий шаг

Если в дайджесте видны open firing или явный flap — предложи:

* для open firing: «открыть тред: `mm_get_thread(<post_id>)`» или
  «глянуть Jira-тикеты по списку: `jira_search(...)`».
* для flap: «оформить задачу в эпике OPS-2944 на тюнинг этого алерта?» —
  но это пас от тебя, не делай сам без подтверждения.

## Контракт ответа пользователю

Только markdown-сводка из шага 7 + 1–2 строки про «следующий шаг», если
уместно. Без отдельного длинного пересказа.

## Worked example (24h окно, канал infra-alerts)

Сегодня 2026-05-22.

1. defaults → team=<команда>, channel=infra-alerts, window=24h, flap_threshold=4.
2. `mm_list_channels(team="<команда>")` → находит канал, id = `<channel_id>`.
3. since_ms = now - 86400000. `mm_list_channel_posts(channel_id, since_ms)` →
   25 постов (next_post_id=null, пагинация не нужна).
4. Парсер выделяет: 19 resolved, 2 firing, 3 ticket, 1 chat.
5. Агрегация: топ — NginxIngressHighRequestLatencyPayments ×5,
   ExternalSecretNotReadyNonProd ×4, KubernetesStatefulsetDown ×2 (critical),
   и т.д. Namespace vmcluster-dev — 4 разных алерта.
6. Аномалии:
   * flap: NginxIngressHighRequestLatencyPayments (5 ≥ 4), ExternalSecretNotReadyNonProd (4 ≥ 4);
   * ongoing firing: MongoDBDiskUsageHighCritical (16:07, без resolved), CloudQuotasIsOver90% (22:30, без resolved);
   * unhealthy namespace: vmcluster-dev (4 разных типа ≥ 3);
   * burst — нет.
7. Сводка по шаблону.
8. «Хочешь оформить тюнинг flap'ов в подзадачу под OPS-2944?»

## Чего НЕ делать

* Не пересказывать содержимое алертов построчно — это шум.
* Не угадывать имя алерта, если регекс не нашёл явное `**Name**` — в
  таком случае относи к `unparsed` и считай отдельной строкой; не пихай
  в топ.
* Не открывать треды каждого ongoing firing «на всякий случай» — это
  N запросов и токены. Только если пользователь явно попросит.
* Не делать write-операции (ни Jira, ни Mattermost) без подтверждения.
* Не использовать `mm_search_posts` для полного дайджеста — она режется
  на `limits.max_search_results` (30). Только для точечного поиска.
* Не пагинировать бесконечно — `window.max_pages` обязательно соблюдать.
