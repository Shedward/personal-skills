#!/bin/sh
cd "$(dirname "$0")/skills" || exit 1
mkdir -p ~/.claude/skills
for skill in */; do
  skill=${skill%/}
  target=~/.claude/skills/$skill
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    if [ "$1" = -f ] || diff -rq -x .DS_Store "$skill" "$target" >/dev/null; then
      rm -rf "$target"
    else
      echo "skip $skill: $target отличается от репо (diff -r, затем install.sh -f)"
      continue
    fi
  fi
  ln -sfn "$PWD/$skill" "$target"
done
