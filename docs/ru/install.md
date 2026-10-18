[English](../install.md) · **Русский**

# Установка, обновление, удаление

## Требования

- macOS или Linux; Python 3.11+ (`python3 --version`), git.
- Claude Code и/или Codex — CLI или расширение VS Code.
- Права на запись в `~/.agents`, `~/.claude`, `~/.codex`, `~/.config`.

## Установка

```bash
git clone https://github.com/<you>/agent-harness ~/Projects/agent-harness
cd ~/Projects/agent-harness
./harness init
```

`init` спрашивает основные значения (Enter оставляет пример) и пишет `~/.config/agent-harness/config.toml`. Без
вопросов: `./harness init --defaults`, потом поправить файл руками. Все параметры — [configuration.md](configuration.md).

```bash
./harness install --dry-run   # список действий, ничего не меняется
./harness install
./harness doctor
```

Что делает `install`:

| Шаг | Куда | Что |
|---|---|---|
| Скиллы | `~/.agents/skills/<имя>/` | копия из `skills/` и `team-skills/` с заполненными подстановками, метка `.harness-managed` |
| Скиллы для Claude | `~/.claude/skills/<имя>` | симлинк на копию выше |
| Правила | `~/.codex/AGENTS.md`, `~/.claude/CLAUDE.md` | из `templates/global/`; CLAUDE.md импортирует AGENTS.md |
| Субагенты | `~/.claude/agents/`, `~/.codex/agents/` | `kb-scout`; для Codex ещё `coder`, `reviewer`, `incident_worker` |
| Профили Codex | `~/.codex/task.config.toml`, `incident.config.toml` | оркестраторы задач и инцидентов |
| Хуки | `~/.claude/settings.json`, `~/.codex/hooks.json` | добавляются к вашим, ваши не удаляются |
| База знаний | `paths.kb_root` | если папки нет: шаблон из `templates/kb/`, `git init`, первый коммит |
| Папки | `paths.work_dir`, `paths.state_dir` | создаются |
| Манифест | `<state_dir>/harness-manifest.json` | что поставлено — для `doctor` и `uninstall` |

### Чужие файлы

`install` не перезаписывает то, что создали не вы через harness:

- свой `~/.codex/AGENTS.md` остаётся, рядом появляется `AGENTS.md.harness-new` — сравните и перенесите нужное;
- свой скилл с тем же именем пропускается;
- `install --force` заменяет такие файлы, предварительно сохранив их в `~/.agents/backups/<время>/`.

Перед любой правкой `settings.json` и `hooks.json` делается бэкап туда же. Существующая база знаний не трогается.

### После установки

1. **Codex:** один раз выполнить `/hooks` и доверить новые хуки — без этого Codex их не запускает.
2. **MCP-сервер sre-toolbox:** `./harness mcp` создаёт `mcp/sre-toolbox/.venv`, ставит зависимости и кладёт
   `config.yaml` из примера — впишите адреса своих систем и токены по `mcp/sre-toolbox/docs/install.md`.
   `./harness mcp --register` подключает его к Claude Code (`claude mcp add`) и Codex (`~/.codex/config.toml`),
   сделав бэкап. Без MCP агенты ищут по базе через `python3 <harness>/tools/kb.py search`.
3. **Другие MCP-серверы** — [mcp.md](mcp.md).
4. **Проверка:** открыть новый чат в `work_dir`, спросить «какие у тебя скиллы?» и «найди в базе payments».

## Обновление

```bash
cd ~/Projects/agent-harness
git pull
./harness install --dry-run && ./harness install
./harness doctor
```

`doctor` сообщает, если установленные скиллы отстают от репозитория. Повторный `install` безопасен: обновляет
поставленное harness, хуки не дублирует.

Свои правки скиллов делайте в репозитории (или своём форке), а не в `~/.agents/skills` — там их перезапишет
следующий `install`. Как — [customizing.md](customizing.md).

## Удаление

```bash
./harness uninstall --dry-run
./harness uninstall
```

Удаляются скиллы, симлинки, правила, агенты и профили, поставленные harness, и его хуки из `settings.json` и
`hooks.json` (ваши хуки остаются). База знаний, конфиг и бэкапы остаются. Вернуть свои прежние файлы — из
`~/.agents/backups/<время>/`.

## Проверка без установки

```bash
python3 -m unittest discover -s tests -v   # тесты на временном HOME, ваши настройки не трогаются
./harness render skills/handoff/SKILL.md     # как выглядит скилл с вашими значениями
```
