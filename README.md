# personal-skills

Личные скиллы Claude Code общего назначения.

## Установка на новой машине

```sh
git clone git@github.com:<user>/personal-skills.git ~/Projects/personal-skills
~/Projects/personal-skills/install.sh
```

`install.sh` линкует каждую папку `skills/<name>` в `~/.claude/skills/<name>`.
Существующую копию заменяет, только если она совпадает с репо; отличающуюся
пропускает (`-f` — заменить всё равно).

## Работа

- Скиллы правятся на месте: симлинк ведёт в рабочую копию репо.
- `/skills-sync` — подтянуть обновления, прилинковать новые, забрать в репо
  скиллы, созданные прямо в `~/.claude/skills`.
- Коммит и push — руками.

## Зависимости скиллов

Скиллы опираются на конвенции из `~/.claude/CLAUDE.md` и раскладку
`~/.claude/docs/<project>/` (ADR, CONTEXT.md, карты подсистем). Без них
работают, но складывают артефакты в никуда.
