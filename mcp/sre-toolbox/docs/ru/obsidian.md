[English](../obsidian.md) · **Русский**

# Knowledge base через Obsidian

← [Обратно в README](../../README.ru.md)

Самый мощный приём экономии токенов — больше, чем все остальные вместе взятые. Потому что он избавляет от необходимости каждый раз заново «открывать» одни и те же проблемы.

---

## Идея

У SRE-команды есть неявная общая память: «эта проблема была год назад, мы тогда рестартовали Redis», «вот этот сервис каждый понедельник в 9 утра тормозит из-за крон-джобы», «runbook для алерта X лежит у Васи в личных заметках». Эта память живёт в головах, чатах и закладках, и Claude её не видит. Поэтому каждый раз он начинает с нуля и тратит токены на повторный анализ.

Obsidian-vault превращает эту память в локальную базу данных, которую Claude умеет искать через MCP:

- **runbooks/** — что делать при конкретных алертах.
- **postmortems/** — итоги прошлых инцидентов.
- **services/** — описания сервисов: владелец, зависимости, SLO, особенности.
- **patterns/** — типичные паттерны деградации.
- **glossary.md** — словарь внутренних терминов.

MCP-сервер индексирует vault в памяти (просто ходит по `*.md`), и tools `obsidian_search`, `obsidian_read_note`, `obsidian_append_finding` дают Claude к нему доступ.

---

## Экономика

Сравнение «холодного» и «горячего» разбора одного и того же алерта:

| Шаг | Без Obsidian | С Obsidian |
|-----|--------------|-----------|
| Понять, что значит алерт | Тянем 3-5K токенов из VM + VictoriaLogs + контекст пользователя | `obsidian_search("HighErrorRate checkout")` → 500 токенов из runbook |
| Понять, был ли похожий инцидент | Не сможет узнать — нет такой информации | `obsidian_search` находит постмортем годовалой давности — 800 токенов |
| Знать, кто owner | Дёргаем kube-аннотации, лейблы, гадаем | В `services/checkout.md` написано прямо — 50 токенов |
| Сформулировать гипотезу | На основе сырых данных, может промахнуться | На основе уже описанных паттернов |
| **Итого вход в модель** | **~20-50K токенов** | **~2-5K токенов** |

Экономия 10x — типичный результат. И, что важно, **качество ответа выше**: Claude опирается на проверенный опыт команды, а не угадывает по логам.

---

## Рекомендуемая структура vault

```
SRE-vault/
├── glossary.md                          # словарь сервисов, терминов, owners
├── services/
│   ├── checkout-api.md                  # описание сервиса
│   ├── payment-service.md
│   └── ...
├── runbooks/
│   ├── high-error-rate.md               # один runbook = одно имя алерта
│   ├── db-connection-pool-exhausted.md
│   ├── disk-space-low.md
│   └── ...
├── postmortems/
│   ├── 2024-03-15-checkout-outage.md
│   ├── 2024-08-02-payment-degradation.md
│   └── ...
├── patterns/
│   ├── monday-morning-cron-spike.md     # повторяющиеся паттерны
│   └── deploy-rollback-checklist.md
└── findings/                            # сюда Claude пишет автозаметки
    └── 2026-05-18-...md
```

---

## Шаблон runbook'а

Хороший runbook структурирован — это помогает и людям, и Claude:

```markdown
---
alert: HighErrorRate
service: checkout-api
severity: critical
tags: [runbook, http, payment]
---

# HighErrorRate на checkout-api

## Что это значит
Доля 5xx-ответов > 5% за последние 5 минут.

## Первичная проверка
1. vm_query: `sum(rate(http_requests_total{service="checkout-api",code=~"5.."}[5m]))`
2. vl_query по сервису с режимом patterns
3. Был ли деплой в последние 30 минут

## Типичные причины
- Деплой регрессии — rollback
- Падение зависимости payment-service
- Лимит коннекшнов к БД

## Действия
1. Rollback: argocd app rollback checkout-api
2. Если payment-service: …
3. Если БД: …

## Эскалация
@checkout-team в Slack #incident-checkout
```

При таком формате Claude по запросу `HighErrorRate checkout` получает 300-500 токенов готового плана действий вместо 20K токенов сырых логов.

---

## Шаблон постмортема

```markdown
---
date: 2026-05-18
incident: INC-42
service: checkout-api
duration_min: 47
root_cause: regression
tags: [postmortem, payment-service]
---

# Outage checkout-api 2026-05-18

## TL;DR
Деплой checkout-api в 14:18 содержал регрессию обработки таймаутов в
коде payment_service.process_refund. Error rate подскочил до 23%.
Rollback в 14:47 решил проблему.

## Timeline
- 14:18 — deploy checkout-api commit a3f1b2
- 14:23 — HighErrorRate fires
- 14:31 — дежурный начал разбор
- 14:45 — найден коммит, принят rollback
- 14:47 — rollback завершён, метрики в норме

## Что мы узнали
Коммит a3f1b2 поменял timeout с 5s на 500ms.

## Action items
- [ ] Добавить integration test на retry-логику
- [ ] Сделать deploy canary > 5 минут
```

Спустя полгода `obsidian_search("payment_service refund timeout")` найдёт этот постмортем за 100 мс и Claude поймёт, что подобная проблема уже была.

---

## Шаблон описания сервиса

```markdown
---
service: checkout-api
team: checkout
slack: "#team-checkout"
tier: critical
slo:
  availability: 99.95
  latency_p99_ms: 800
tags: [service, payment]
---

# checkout-api

## Назначение
Принимает запросы на оформление заказов от веб и моб приложений.

## Зависимости
- payment-service (синхронно)
- inventory-service (синхронно)
- redis-checkout (cache, асинхронно)
- postgres-checkout (state)

## Особенности
- Пиковая нагрузка в пятницу 18:00-22:00.
- Каждый понедельник в 9:00 — фоновая cron-job rebuilds-cart-cache, генерирует
  всплеск CPU (это нормально).

## Owner
@vasily-petrov

## Runbook'и
- [HighErrorRate](../../runbooks/high-error-rate.md)
- [HighLatency](../../runbooks/high-latency-checkout.md)
```

---

## Tools

Поиск по общей базе знаний harness — `kb_search` / `kb_list` (через `kb.py`, путь — `obsidian.kb_tool`,
см. [tools.md](./tools.md)); `obsidian_*` работают с vault из `obsidian.vault_path`.

| Tool | Назначение |
|------|-----------|
| `obsidian_search(query, top_k)` | Семантический-ish поиск по vault. Простой term-overlap скоринг, бонус за попадание в заголовок/имя файла. Возвращает snippets, не файлы целиком. |
| `obsidian_read_note(path)` | Прочитать конкретную заметку, найденную через search. Лимит `max_note_chars` (по умолчанию 8000). |
| `obsidian_append_finding(title, content, folder, tags)` | Записать новую заметку (по умолчанию в `findings/`). Включается через `obsidian.allow_writes: true`. |

Подробнее по параметрам — в [tools.md](./tools.md).

---

## Безопасность

- Все три tool'а применяют redactor — даже если в заметке окажется секрет, он замаскируется перед отдачей Claude.
- `path traversal` защита: нельзя через `path="../etc/passwd"` выйти за пределы vault.
- Запись по умолчанию выключена. Если включена — запись только в подпапки vault, имя файла нормализуется (slug + дата).
- Vault лежит локально и не покидает машину, пока Claude явно не вернёт его содержимое в ответе.

---

## Развёртывание vault

Два сценария:

**Локальный vault на машине SRE.** Claude Desktop + MCP-сервер на ноутбуке. Vault — обычная папка Obsidian. Когда команда обновляет заметки, Obsidian Sync / git / iCloud Drive раскатывают изменения. Index в MCP обновляется по `mtime` — изменили файл → следующий поиск увидит свежую версию.

**Общий vault на сервере.** Vault лежит на shared-сервере (git-репозиторий с auto-pull). Все SRE используют один и тот же набор runbooks. Изменения через PR в git. MCP-сервер живёт там же, обновляется по cron `git pull`.

Второй вариант сильнее в команде из 5+ человек — централизованное знание. Первый — для индивидуальной работы.

---

## Маленькое правило

«Если ты разобрал инцидент и тебе пришлось что-то выяснять руками — это знак, что нужна заметка в vault». Через год vault — главный SRE-актив команды, и Claude становится тем сильнее, чем больше в нём накоплено.

Практические примеры использования Obsidian в инцидентах — см. [examples.md](./examples.md).
