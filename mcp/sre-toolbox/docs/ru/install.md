[English](../install.md) · **Русский**

# Локальная установка и запуск MCP-сервера

← [Обратно в README](../../README.ru.md)

Документ для разработчика: поднять `sre-toolbox` из agent-harness на своём ноуте, проверить подключение к
Jira/Confluence/Obsidian и зарегистрировать сервер в Claude Code и Codex.

Для production-режима (systemd, ротация токенов, hardening) — смотри [deployment.md](./deployment.md). Какие
возможности MCP нужны скиллам harness — [../../../docs/mcp.md](../../../../docs/ru/mcp.md).

---

## 1. Требования

- macOS / Linux.
- Python **3.10+** (в коде используется `X | None`, PEP 604).
- Клон agent-harness (ниже — `~/Projects/agent-harness`).
- Personal Access Token от тех систем, которые подключаете (см. шаг 3).

---

## 2. Подготовка окружения

venv живёт внутри каталога сервера (`mcp/sre-toolbox/.venv`, он в `.gitignore`):

```bash
cd ~/Projects/agent-harness/mcp/sre-toolbox
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

---

## 3. Секреты

Токены хранятся **только локально** и никогда не попадают в репозиторий. Три способа:

1. **`.env` рядом с `server.py`** — сервер подгружает его сам; в `config.yaml` значения подставляются через
   `${VAR}`:

   ```bash
   cp .env.example .env    # .env в .gitignore
   ```

2. **Окружение / Keychain** — лаунчер (или блок `env` регистрации MCP) экспортирует переменные из Keychain перед
   стартом, `config.yaml` ссылается на них через `${VAR}`.
3. **Прямо в `config.yaml`** (он в `.gitignore`, держите права `0600`). Так делает
   `scripts/set_grafana_token.py`: `pbpaste | .venv/bin/python scripts/set_grafana_token.py` проверяет токен Grafana
   и записывает его в `grafana.auth.bearer_token`.

Как получить PAT в Jira Server / Data Center: аватар → **Profile** → **Personal Access Tokens** → **Create token**.
У Confluence, GitLab, Mattermost и Grafana токены свои (см. комментарии в `.env.example`).

---

## 4. Конфиг — `config.yaml`

```bash
cp config.example.yaml config.yaml   # config.yaml в .gitignore
```

В шаблоне все `allow_writes: false` — сервер только читает. Чтобы, например, скилл `tracker-story` мог создавать
задачи, включите запись точечно и сузьте её allowlist:

```yaml
jira:
  url: "https://jira.example.com"     # свой инстанс, без слеша
  auth:
    bearer_token: "${JIRA_PAT}"
  allow_writes: true                  # ВКЛ: разрешаем создавать/менять задачи
  allow_projects:
    - "OPS"                           # белый список project keys

obsidian:
  vault_path: "~/Documents/Obsidian/SRE"
  # kb.py для kb_search/kb_list; по умолчанию ../../tools/kb.py этого репозитория
  # kb_tool: "~/Projects/agent-harness/tools/kb.py"
  allow_writes: true                  # если агент должен писать findings

server:
  audit_log_path: ""                  # отключить JSONL-аудит (или укажите путь)
```

`kb_search` / `kb_list` ищут в базе знаний, корень которой `kb.py` берёт из конфига harness
(`paths.kb_root` в `~/.config/agent-harness/config.toml` или файл из `AGENT_HARNESS_CONFIG`).

Если состав команды нужен агенту для назначения задач — создайте `teams.md` по образцу
[teams.example.ru.md](../../teams.example.ru.md) (он в `.gitignore`).

---

## 5. Obsidian-папка

Если используете отдельный Obsidian vault — создайте его и подпапки:

```bash
mkdir -p "$HOME/Documents/Obsidian/SRE"/{runbooks,postmortems,services,findings}
```

Путь в `obsidian.vault_path` должен совпадать. Если vault и есть база знаний harness, укажите тот же путь, что и
`paths.kb_root`.

---

## 6. Проверка

```bash
# контрактные тесты (не ходят в сеть)
.venv/bin/python -m unittest discover -s tests -v

# конфиг валиден, tools регистрируются
.venv/bin/python -c "import server; print('ok, tools registered as', server.mcp.name)"

# интерактивно — через MCP Inspector
.venv/bin/mcp dev server.py
```

Сервер работает в **stdio**-режиме — JSON-RPC на stdin/stdout, логи в stderr. Ручной вызов tool через агента
(например `jira_get_issue` по известному ключу) — проверка живых credentials.

---

## 7. Регистрация в Claude Code

Глобально для пользователя:

```bash
claude mcp add --scope user sre-toolbox -- \
  ~/Projects/agent-harness/mcp/sre-toolbox/.venv/bin/python \
  ~/Projects/agent-harness/mcp/sre-toolbox/server.py
```

Если `config.yaml` лежит не рядом с `server.py`, добавьте `--env MCP_CONFIG=/полный/путь/config.yaml`.
Для project-scope есть пример [`.mcp.example.json`](../../.mcp.example.json) (в нём же — опциональный внешний
VictoriaMetrics MCP).

## 8. Регистрация в Codex

`~/.codex/config.toml`:

```toml
[mcp_servers.sre-toolbox]
command = "/полный/путь/agent-harness/mcp/sre-toolbox/.venv/bin/python"
args = ["/полный/путь/agent-harness/mcp/sre-toolbox/server.py"]
# env = { MCP_CONFIG = "/полный/путь/к/config.yaml" }
```

После регистрации перезапустите клиент: появятся `kb_*`, `jira_*`, `confluence_*`, `gitlab_*`, `mm_*`,
`grafana_*`, `obsidian_*`, `am_*`, `vm_*`, `vl_*`. В конфиге harness (секция `[mcp]`, `hub = "sre-toolbox"`)
укажите имя сервера и выполните `./harness install` — `kb-scout` получит запрет на его пишущие tools.

---

## 9. Траблшутинг

| Симптом | Что проверить |
|--|--|
| `config not found at ...` | `config.yaml` рядом с `server.py` или задайте `MCP_CONFIG=/path/to/config.yaml`. |
| `jira не сконфигурирован в config.yaml` | Не заполнен `jira.url` или `jira.auth.bearer_token` пустой → проверьте `.env`/окружение. |
| `запись в jira отключена` | `jira.allow_writes` не `true`. |
| `проект X не в allow_projects` | Добавьте project key в `jira.allow_projects` (пустой список = без ограничения). |
| `kb.py не найден: ...` | Задайте `obsidian.kb_tool` или проверьте, что `tools/kb.py` есть в клоне harness. |
| Внутренние хосты не отвечают за прокси | Добавьте домены в `NO_PROXY` в форме `.corp.example.com` (см. [../../../docs/mcp.md](../../../../docs/ru/mcp.md)). |
| IDE подсвечивает `httpx`/`mcp`/`dotenv` как unresolved | Выберите интерпретатор `./.venv/bin/python`. |
