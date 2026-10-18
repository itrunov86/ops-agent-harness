# MCP: какие возможности нужны и чем их закрыть

Скиллы описывают **возможность** («получить задачу трекера»), а инструмент называют примером
(`jira_get_issue`). Так они работают с любым набором MCP-серверов. У каждого шага есть запасной путь — CLI или
`kb.py`, — поэтому отсутствие сервера сужает возможности, но не ломает скилл.

В комплекте два сервера:

- **`mcp/sre-toolbox`** — интеграции для дежурного SRE: Alertmanager, VictoriaMetrics, VictoriaLogs, Jira,
  Confluence, GitLab, Mattermost, Grafana и база знаний (`kb_search`, `kb_list`, `obsidian_*`). Ответы агрегированы
  (шаблоны логов, сводка метрик), запись в каждую систему выключена по умолчанию и включается в `config.yaml`.
  Подготовка — `./harness mcp`, подключение — `./harness mcp --register`; подробности —
  [mcp/sre-toolbox/README.md](../mcp/sre-toolbox/README.md).
- **`tools/kb_mcp.py`** — только поиск по базе, без зависимостей.

`mcp.hub` в конфиге — имя вашего основного сервера интеграций (по умолчанию `sre-toolbox`): `kb-scout` запрещает его пишущие инструменты по
шаблону `mcp__<hub>__<tool>`. Если интеграции разнесены по нескольким серверам, допишите их пишущие инструменты в
`disallowedTools` агента `agents/claude/kb-scout.md` (в репозитории) и переустановите.

## Возможности

| Возможность | Кому нужна | Примеры инструментов | Без MCP |
|---|---|---|---|
| Поиск по базе знаний | все | `kb_search`, `kb_list` — **входит в harness** (`tools/kb_mcp.py`) | `kb.py search` |
| Трекер: прочитать, найти, создать, комментировать, перевести | request-triage, jira-planning-*, postmortem, sprint-report, contractor-report | `jira_get_issue`, `jira_search`, `jira_create_issue`, `jira_add_comment` | веб-интерфейс, `jira` CLI |
| Вики: найти, прочитать, создать, обновить страницу | duty-notes, postmortem, quarterly-planning, sprint-report | `confluence_search`, `confluence_get_page`, `confluence_create_page` | веб-интерфейс |
| Чат: тред по ссылке, посты канала, поиск | request-triage, mattermost-alerts-digest | `mm_resolve_permalink`, `mm_get_thread`, `mm_list_channel_posts` | скопировать текст треда в чат |
| Алерты: активные, silences | request-triage, observability-triage | `am_active_alerts`, `am_silences` | `amtool alert query` |
| Метрики: instant/range запросы с агрегацией | observability-triage, request-triage | `vm_query`, `vm_query_range`, `query_range` | `curl /api/v1/query_range`, Grafana |
| Логи: запрос с группировкой по шаблонам | observability-triage, kubernetes-runtime-triage | `vl_query`, `loki_query` | `kubectl logs`, LogsQL/LogQL в UI |
| Дашборды и алерт-правила | observability-triage | `grafana_search`, `grafana_get_dashboard` | Grafana UI |
| Git-хостинг: MR, файлы, поиск | gitlab-ci-review, request-triage | `gitlab_get_mr`, `gitlab_get_file`, `gitlab_search` | `glab`, `git` |
| IaC/GitOps только на чтение | terraform-terragrunt-review, helm-argocd-gitops, vault-ops | `terraform_plan_summary`, `argocd_app_diff`, `helm_template_summary`, `vault_policy_read` | `terraform plan`, `argocd app diff`, `helm template`, `vault policy read` |
| Документация библиотек | versioned-docs | Context7 `resolve-library-id`, `query-docs` | официальный сайт |

## Если систем нет в sre-toolbox

Публичные серверы под эти возможности есть почти у всех популярных систем: Atlassian (Jira/Confluence), GitLab,
Grafana, VictoriaMetrics, Prometheus, Kubernetes, Context7. Выбирайте серверы, которые:

- работают с вашими учётными данными локально (токены — в Keychain или конфиге сервера, не в промпте);
- умеют агрегировать (сводка метрик вместо сырых точек, шаблоны логов вместо тысяч строк) — это экономит контекст;
- разделяют чтение и запись, чтобы запись можно было выключить или запретить субагенту.

Новую систему проще добавить модулем в `mcp/sre-toolbox/tools/` по образцу соседних: единая аутентификация, общий
«write gate» и агрегация ответов уже есть.

## Поиск по базе как MCP

```bash
claude mcp add --scope user kb -- python3 -I ~/Projects/agent-harness/tools/kb_mcp.py
```

```toml
# ~/.codex/config.toml
[mcp_servers.kb]
command = "python3"
args = ["-I", "/полный/путь/agent-harness/tools/kb_mcp.py"]
```

`./harness doctor` показывает, подключён ли он. Сервер только читает.

## Прокси

Если в сети корпоративный HTTP-прокси, MCP-серверы и агенты могут пускать через него и внутренний трафик — запросы к
внутренним хостам тогда падают. Добавьте внутренние домены в `NO_PROXY` в виде `.corp.example.com` (с точкой, не
`*.corp.example.com`: вариант со звёздочкой понимают не все клиенты, в том числе git по HTTPS).
