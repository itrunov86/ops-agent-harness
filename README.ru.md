[English](README.md) · **Русский**

# ops-agent-harness

Обвязка для ИИ-агентов **Claude Code** и **Codex** в работе DevOps/SRE: общие правила безопасности, скиллы для
типовых задач, база знаний с поиском, журналы длинных задач и хуки, которые не дают агенту терять контекст.
Ставится одной командой, переносится на новое место работы правкой одного конфига.

## Что внутри

| Часть | Что делает |
|---|---|
| **Правила** (`templates/global/`) | Единые для обоих агентов: удалённые системы только читаем, запись — по одному явному «да», GitOps, секреты не покидают машину, ключ задачи на каждой ветке |
| **Скиллы** (`skills/`, `team-skills/`) | 23 сценария: разбор алертов и обращений, триаж Kubernetes/сети/метрик, ревью Terraform/Helm/CI/Vault, постмортем, эпики и задачи, отчёт спринта, журнал задачи |
| **База знаний** (`templates/kb/`, `tools/kb.py`) | Git-репозиторий и Obsidian vault одновременно: поиск BM25 с русским стеммером и глоссарием, хабы сервисов и задач, проверка frontmatter |
| **MCP-сервер sre-toolbox** (`mcp/sre-toolbox/`) | Alertmanager, VictoriaMetrics/Logs, Jira, Confluence, GitLab, Mattermost, Grafana и база знаний; ответы агрегированы под контекст агента, запись выключена по умолчанию и включается списком |
| **MCP-сервер kb** (`tools/kb_mcp.py`) | Только `kb_search` и `kb_list`, без зависимостей — если sre-toolbox не нужен |
| **Журналы задач** (`tools/agent_session.py`, скилл `handoff`) | Контекст длинной задачи между чатами; журнал привязывается к чату по ключу задачи, переживает `/compact` |
| **Хуки** | Журнал при старте и после сжатия, напоминания на 50/75% контекста, документы по ключам задач из запроса, автокоммит базы знаний |
| **Субагенты** (`agents/`) | `kb-scout` (широкий поиск только на чтение), для Codex — `coder`, `reviewer`, `incident_worker` и профили `task`/`incident` |
| **Оценка** (`tools/agent_bench.py`, `kb.py eval`) | A/B-прогоны агентов на ваших вопросах; качество поиска по «золотым вопросам» |

## Быстрый старт

```bash
git clone https://github.com/itrunov86/ops-agent-harness ~/Projects/ops-agent-harness
cd ~/Projects/ops-agent-harness
./harness init               # спросит организацию, пути, префиксы задач, трекер
./harness install --dry-run  # покажет, что будет сделано
./harness install            # скиллы, агенты, правила, хуки, база знаний
./harness mcp --register     # по желанию: sre-toolbox для Claude Code и Codex
./harness doctor             # проверка
```

Затем: в Codex один раз `/hooks` → доверить новые хуки; в `mcp/sre-toolbox/config.yaml` вписать адреса своих
систем. Чаты открывайте из папки `work_dir` из конфига. Подробно — [docs/install.md](docs/ru/install.md).

## Как этим пользоваться

```text
разбери алерт https://chat.example.com/team/pl/abc123
OPS-1234 добавь bucket для логов, покажи terraform plan, apply не делай
заведи handoff                         ← задача не влезет в один чат
OPS-1234 продолжаем                    ← на следующий день, в новом чате
оформи постмортем по INC-7
сделай kb-compile                      ← раз в неделю: свежие находки в хабы
```

Полный справочник промптов и сценариев — [docs/workflows.md](docs/ru/workflows.md), каталог скиллов —
[docs/skills.md](docs/ru/skills.md).

## Документация

| Документ | О чём |
|---|---|
| [concepts.md](docs/ru/concepts.md) | Из чего состоит harness и как части связаны |
| [install.md](docs/ru/install.md) | Установка, обновление, удаление |
| [configuration.md](docs/ru/configuration.md) | Все параметры `config.toml` |
| [workflows.md](docs/ru/workflows.md) | Повседневная работа: чаты, задачи, типовые промпты |
| [skills.md](docs/ru/skills.md) | Каталог скиллов: когда какой и как вызвать |
| [handoff.md](docs/ru/handoff.md) | Журналы длинных задач и привязка к чату |
| [knowledge-base.md](docs/ru/knowledge-base.md) | Устройство базы знаний, поиск, хабы, `kb-compile` |
| [hooks.md](docs/ru/hooks.md) | Что делает каждый хук, где его состояние |
| [mcp.md](docs/ru/mcp.md) | Какие возможности нужны скиллам и какими MCP-серверами их закрыть |
| [security.md](docs/ru/security.md) | Модель безопасности: чтение по умолчанию, подтверждения, секреты |
| [new-job.md](docs/ru/new-job.md) | Чек-лист переезда на новое место работы |
| [customizing.md](docs/ru/customizing.md) | Свои скиллы, правка правил, подстановки |
| [evaluation.md](docs/ru/evaluation.md) | Как проверить, что правка обвязки помогла |
| [troubleshooting.md](docs/ru/troubleshooting.md) | Типовые проблемы и решения |

## Требования

- macOS или Linux, Python 3.11+, git.
- Claude Code и/или Codex CLI (или их расширения VS Code).
- Для интеграций — `mcp/sre-toolbox` (входит в комплект) или свои MCP-серверы ([docs/mcp.md](docs/ru/mcp.md)). Без
  них harness работает: база знаний, журналы, ревью IaC и правила от MCP не зависят.

## Лицензия

MIT — см. [LICENSE](LICENSE). Авторы sre-toolbox — itrunov86 и Сергей Клецов. Сторонние скиллы и их лицензии — [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Как вносить изменения — [CONTRIBUTING.md](CONTRIBUTING.ru.md).
