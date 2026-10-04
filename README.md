# personal-skills

Личные скиллы Claude Code общего назначения. Репозиторий — маркетплейс с
одним плагином `my`; скиллы вызываются как `/my:<name>`.

## Установка

```sh
git clone git@github.com:<user>/personal-skills.git ~/Projects/personal-skills
claude plugin marketplace add ~/Projects/personal-skills
claude plugin install my@personal-skills
```

Маркетплейс добавлен из локальной папки, поэтому Claude Code читает скиллы
прямо из клона: правка на месте действует со следующей сессии или после
`/reload-plugins`.

Только на чтение, без клона: `claude plugin marketplace add <user>/personal-skills`.

## Работа

- `/my:skills-sync` — подтянуть обновления, забрать в репо скиллы, созданные
  прямо в `~/.claude/skills`, показать незакоммиченное.
- Новый скилл — папка `skills/<name>/SKILL.md`.
- Коммит и push — руками.

## Зависимости скиллов

Скиллы опираются на конвенции из `~/.claude/CLAUDE.md` и раскладку
`~/.claude/docs/<project>/` (ADR, CONTEXT.md, карты подсистем). Без них
работают, но складывают артефакты в никуда.
