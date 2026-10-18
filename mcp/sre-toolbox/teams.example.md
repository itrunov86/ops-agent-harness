**English** · [Русский](teams.example.ru.md)

# Team (format example)

Copy to `teams.md` (it is in `.gitignore`) and fill in your team. The agent reads this file before assigning tasks
or filtering by assignee: the "Tracker login" column is the value for `assignee` in `jira_create_issue` and JQL.

| Name | Role | Tracker login | Email | Chat |
|------|------|---------------|-------|------|
| Alice Example | team lead | `aexample` | alice@example.com | `@alice` |
| Bob Tester | SRE, on call | `btester` | bob@example.com | `@bob` |
| Vera Sample | DevOps, CI/CD | `vsample` | vera@example.com | `@vera` |
