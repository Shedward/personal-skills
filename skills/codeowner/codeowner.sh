#!/usr/bin/env bash
# Владельцы кода по CODEOWNERS в формате Forgejo/Gitea (шаблоны — регулярки).
# Без зависимостей, совместим с bash 3.2 (macOS).

set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: codeowner.sh [--file CODEOWNERS] <path>... | -
  -            читать пути из stdin (по одному на строку)
  --file F     файл правил; иначе $CODEOWNERS_FILE; иначе первый файл с правилами
               в корне репо: CODEOWNERS, .forgejo/, .gitea/, .github/, docs/, CODEOWNERS_*
Вывод на путь: <path>\t<владельцы через пробел | ->\t<комментарий правила>
EOF
  exit 2
}

has_rules() {
  [[ -f "$1" ]] && grep -qvE '^[[:space:]]*(#|$)' "$1"
}

find_codeowners() {
  local root="$1" candidate
  for candidate in "$root/CODEOWNERS" "$root/.forgejo/CODEOWNERS" "$root/.gitea/CODEOWNERS" \
    "$root/.github/CODEOWNERS" "$root/docs/CODEOWNERS" "$root"/CODEOWNERS_*; do
    if has_rules "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

file=""
paths=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --file) [[ $# -ge 2 ]] || usage; file="$2"; shift ;;
    -h|--help) usage ;;
    -) while IFS= read -r line; do [[ -n "$line" ]] && paths+=("$line"); done ;;
    *) paths+=("$1") ;;
  esac
  shift
done
[[ ${#paths[@]} -gt 0 ]] || usage

root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
file="${file:-${CODEOWNERS_FILE:-}}"
if [[ -z "$file" ]]; then
  [[ -n "$root" ]] || { echo "Not inside a git repository; pass --file" >&2; exit 2; }
  file="$(find_codeowners "$root")" || { echo "No CODEOWNERS with rules in $root" >&2; exit 2; }
fi

patterns=()
rules=()
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
  patterns+=("${line%%[[:space:]]*}")
  rules+=("$line")
done < "$file"

for raw in "${paths[@]}"; do
  path="${raw#./}"
  path="${path%/}"
  if [[ "$path" == /* && -n "$root" ]]; then
    path="${path#"$root"/}"
  fi

  matched=""
  for i in "${!patterns[@]}"; do
    pattern="${patterns[$i]}"
    if [[ "$path" =~ ^${pattern}$ || "$path/" =~ ^${pattern}$ || "$path" =~ ^${pattern}/ ]]; then
      matched="${rules[$i]}"
    fi
  done

  if [[ -z "$matched" ]]; then
    printf '%s\t-\t\n' "$path"
    continue
  fi

  body="${matched#*[[:space:]]}"
  note=""
  if [[ "$body" == *"#"* ]]; then
    note="${body#*#}"
    note="${note#"${note%%[![:space:]]*}"}"
    body="${body%%#*}"
  fi
  owners=""
  for token in $body; do
    [[ "$token" == @* || "$token" == *@*.* ]] && owners="${owners:+$owners }$token"
  done
  printf '%s\t%s\t%s\n' "$path" "${owners:--}" "$note"
done
