# Пример: payments-api, HighErrorRate (вымышленный случай)

Пользователь: «Разбери алерт {{CHAT_URL}}/ops/pl/8k2m4n6p1q3r5s7t9u0v1w2x3y»

1. `mm_resolve_permalink` → пост в канале алертов: `Alert: HighErrorRate`, `Severity: warning`, `Firing`,
   `namespace=payments`, `service=payments-api`, доля 5xx 7% при пороге 5%. `mm_get_thread` → бот дежурства создал
   `{{TICKET_EXAMPLE}}`; в треде разработчик предполагает, что «упала база». `jira_get_issue("{{TICKET_EXAMPLE}}")` →
   канонический текст и исполнитель.
2. `am_active_alerts` → алерт всё ещё горит. Recall-first: `kb_search("payments-api HighErrorRate 5xx {{TICKET_EXAMPLE}}")`
   — того же случая нет, есть смежный документ про лимиты соединений к базе.
3. Диагностика: `vm_query_range` по `http_requests_total{namespace="payments",code=~"5.."}` за 2 часа — рост 5xx начался
   через 4 минуты после выкатки; латентность базы и число соединений не менялись, значит гипотеза про базу неверна.
   `argocd_app_history` показывает новую ревизию чарта в это время, `argocd_app_diff` и `gitlab_get_mr` — в values
   таймаут клиента платёжного шлюза уменьшен с `10s` до `1s`. `vl_query` по `payments-api` кластеризует ошибки в один
   паттерн `upstream timeout after 1s`.
4. В чат: суть, причина с цитатой diff values и графиком 5xx, предложение — вернуть таймаут `10s` через MR в GitOps-
   репозиторий (blast radius — только `payments-api`, rollback — revert MR, проверка — тот же `vm_query_range` по 5xx).
5. Документ `alerts/{{TICKET_EXAMPLE}}-payments-api-higherrorrate-2026-09-17.md` по шаблону `alert_rca.md`:
   `type: rca`, `tickets: [{{TICKET_EXAMPLE}}]`, `services: [payments-api]`, `summary: "5xx 7%: таймаут клиента шлюза
   уменьшен до 1s в новой ревизии чарта; предложено вернуть 10s"`. `kb.py lint` — OK,
   `kb.py search "{{TICKET_EXAMPLE}}"` выдаёт документ первым, коммит `{{TICKET_EXAMPLE}} document payments-api error rate`
   в `main`.
6. Предложение оставить комментарий с диагнозом в `{{TICKET_EXAMPLE}}`; ждём ответа пользователя.
