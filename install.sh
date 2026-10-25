#!/bin/sh
set -e
target=both
codex_dir=${PERSONAL_SKILLS_CODEX_DIR:-$HOME/.agents/skills}
dir=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --claude) target=claude ;;
    --codex) target=codex ;;
    --both) target=both ;;
    -h|--help)
      echo "Usage: install.sh [--claude|--codex|--both] [repo-directory]"
      echo "Default: both; Codex directory: \$HOME/.agents/skills"
      echo "Override Codex directory with PERSONAL_SKILLS_CODEX_DIR."
      exit 0 ;;
    -*) echo "Unknown option: $1" >&2; exit 1 ;;
    *)
      [ -z "$dir" ] || { echo "Only one repository directory is allowed" >&2; exit 1; }
      dir=$1 ;;
  esac
  shift
done
dir=${dir:-$HOME/Projects/personal-skills}
if [ "$target" != codex ]; then
  command -v python3 >/dev/null 2>&1 || {
    echo "Python 3 is required to check Claude marketplace registration." >&2
    exit 1
  }
  command -v claude >/dev/null 2>&1 || {
    echo "Claude CLI not found. Use --codex to install only for Codex." >&2
    exit 1
  }
fi
[ -e "$dir/.git" ] || git clone git@github.com:Shedward/personal-skills.git "$dir"
dir=$(cd "$dir" && pwd -P)
[ -f "$dir/skills/skills-sync/SKILL.md" ] || {
  echo "Not a personal-skills repository: $dir" >&2
  exit 1
}
marketplace_registered=0
if [ "$target" != codex ]; then
  marketplaces=$(claude plugin marketplace list --json) || {
    echo "Could not list Claude marketplaces; installation stopped." >&2
    exit 1
  }
  if printf '%s\n' "$marketplaces" | python3 -c '
import json, os, sys
try:
    entries = json.load(sys.stdin)
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise ValueError("expected a list of marketplaces")
    matches = [e for e in entries if e.get("name") == "personal-skills"]
    if not matches:
        sys.exit(1)
    location = matches[0].get("installLocation")
    if not isinstance(location, str) or not location:
        raise ValueError("personal-skills has no valid installLocation")
    if len(matches) != 1 or os.path.realpath(location) != sys.argv[1]:
        print("Claude marketplace personal-skills points elsewhere; left unchanged.", file=sys.stderr)
        sys.exit(2)
except (ValueError, TypeError) as error:
    print("Invalid Claude marketplace list: " + str(error), file=sys.stderr)
    sys.exit(2)
' "$dir"; then
    marketplace_registered=1
  else
    result=$?
    [ "$result" -eq 1 ] || exit "$result"
  fi
fi
if [ "$target" != claude ]; then
  # Check every destination before creating any links.
  conflict=0
  for skill in "$dir"/skills/*; do
    [ -f "$skill/SKILL.md" ] || continue
    link=$codex_dir/${skill##*/}
    if [ -e "$link" ] || [ -L "$link" ]; then
      if [ -L "$link" ] && [ -d "$link" ] && [ "$(cd "$link" && pwd -P)" = "$skill" ]; then
        continue
      fi
      echo "Conflict (left unchanged): $link" >&2
      conflict=1
    fi
  done
  [ "$conflict" -eq 0 ] || exit 1
  mkdir -p "$codex_dir"
  for skill in "$dir"/skills/*; do
    [ -f "$skill/SKILL.md" ] || continue
    link=$codex_dir/${skill##*/}
    [ -L "$link" ] || ln -s "$skill" "$link"
  done
  echo "Codex skills linked: $codex_dir -> $dir/skills"
fi
if [ "$target" != codex ]; then
  if [ "$marketplace_registered" -eq 0 ]; then
    claude plugin marketplace add "$dir"
  fi
  claude plugin install my@personal-skills
  claude plugin update my@personal-skills
  echo "Claude plugin installed. Run /reload-plugins or start a new session."
fi
