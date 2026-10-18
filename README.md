# agent-harness

Обвязка для ИИ-агентов **Claude Code** и **Codex** в работе DevOps/SRE: общие правила безопасности, скиллы для
типовых задач, база знаний с поиском, журналы длинных задач и хуки, которые не дают агенту терять контекст.
Ставится одной командой, переносится на новое место работы правкой одного конфига.

> **English summary.** A portable harness for Claude Code and Codex in DevOps/SRE work: shared read-only safety
> rules, 23 skills (incident triage, Terraform/Helm/Argo CD review, postmortems, planning), a git-backed knowledge
> base with BM25 search (CLI + MCP server), per-chat task journals that survive context compaction, and hooks that
> auto-commit knowledge-base edits. Everything company-specific lives in one TOML config; `./harness install`
> renders and installs the rest. Docs are in Russian; code comments are Russian too. Python 3.11+, stdlib only.

## Что внутри

| Часть | Что делает |
|---|---|
| **Правила** (`templates/global/`) | Единые для обоих агентов: удалённые системы только читаем, запись — по одному явному «да», GitOps, секреты не покидают машину, ключ задачи на каждой ветке |
| **Скиллы** (`skills/`, `team-skills/`) | 23 сценария: разбор алертов и обращений, триаж Kubernetes/сети/метрик, ревью Terraform/Helm/CI/Vault, постмортем, эпики и задачи, отчёт спринта, журнал задачи |
| **База знаний** (`templates/kb/`, `tools/kb.py`) | Git-репозиторий и Obsidian vault одновременно: поиск BM25 с русским стеммером и глоссарием, хабы сервисов и задач, проверка frontmatter |
| **MCP-сервер** (`tools/kb_mcp.py`) | `kb_search` и `kb_list` для агентов без shell |
| **Журналы задач** (`tools/agent_session.py`, скилл `handoff`) | Контекст длинной задачи между чатами; журнал привязывается к чату по ключу задачи, переживает `/compact` |
| **Хуки** | Журнал при старте и после сжатия, напоминания на 50/75% контекста, документы по ключам задач из запроса, автокоммит базы знаний |
| **Субагенты** (`agents/`) | `kb-scout` (широкий поиск только на чтение), для Codex — `coder`, `reviewer`, `incident_worker` и профили `task`/`incident` |
| **Оценка** (`tools/agent_bench.py`, `kb.py eval`) | A/B-прогоны агентов на ваших вопросах; качество поиска по «золотым вопросам» |

## Быстрый старт

```bash
git clone https://github.com/<you>/agent-harness ~/Projects/agent-harness
cd ~/Projects/agent-harness
./harness init               # спросит организацию, пути, префиксы задач, трекер
./harness install --dry-run  # покажет, что будет сделано
./harness install            # скиллы, агенты, правила, хуки, база знаний
./harness doctor             # проверка
```

Затем: в Codex один раз `/hooks` → доверить новые хуки; по желанию подключить MCP-поиск (команду печатает
`install`). Чаты открывайте из папки `work_dir` из конфига. Подробно — [docs/install.md](docs/install.md).

## Как этим пользоваться

```text
разбери алерт https://chat.example.com/team/pl/abc123
OPS-1234 добавь bucket для логов, покажи terraform plan, apply не делай
заведи handoff                         ← задача не влезет в один чат
OPS-1234 продолжаем                    ← на следующий день, в новом чате
оформи постмортем по INC-7
сделай kb-compile                      ← раз в неделю: свежие находки в хабы
```

Полный справочник промптов и сценариев — [docs/workflows.md](docs/workflows.md), каталог скиллов —
[docs/skills.md](docs/skills.md).

## Документация

| Документ | О чём |
|---|---|
| [concepts.md](docs/concepts.md) | Из чего состоит harness и как части связаны |
| [install.md](docs/install.md) | Установка, обновление, удаление |
| [configuration.md](docs/configuration.md) | Все параметры `config.toml` |
| [workflows.md](docs/workflows.md) | Повседневная работа: чаты, задачи, типовые промпты |
| [skills.md](docs/skills.md) | Каталог скиллов: когда какой и как вызвать |
| [handoff.md](docs/handoff.md) | Журналы длинных задач и привязка к чату |
| [knowledge-base.md](docs/knowledge-base.md) | Устройство базы знаний, поиск, хабы, `kb-compile` |
| [hooks.md](docs/hooks.md) | Что делает каждый хук, где его состояние |
| [mcp.md](docs/mcp.md) | Какие возможности нужны скиллам и какими MCP-серверами их закрыть |
| [security.md](docs/security.md) | Модель безопасности: чтение по умолчанию, подтверждения, секреты |
| [new-job.md](docs/new-job.md) | Чек-лист переезда на новое место работы |
| [customizing.md](docs/customizing.md) | Свои скиллы, правка правил, подстановки |
| [evaluation.md](docs/evaluation.md) | Как проверить, что правка обвязки помогла |
| [troubleshooting.md](docs/troubleshooting.md) | Типовые проблемы и решения |

## Требования

- macOS или Linux, Python 3.11+, git.
- Claude Code и/или Codex CLI (или их расширения VS Code).
- Для интеграций — MCP-серверы вашего трекера, вики, чата, метрик ([docs/mcp.md](docs/mcp.md)). Без них harness
  работает: база знаний, журналы, ревью IaC и правила от MCP не зависят.

## Лицензия

MIT — см. [LICENSE](LICENSE). Сторонние скиллы и их лицензии — [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Как вносить изменения — [CONTRIBUTING.md](CONTRIBUTING.md).
