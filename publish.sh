#!/bin/sh
# Выпуск одной командой из develop: версия, CHANGELOG, ветка, тег, образ и push.
# Образ собирается здесь и уходит в реестр раньше git push, чтобы сбой сборки
# не оставил на GitHub тег без образа.
set -eu

cd "$(dirname "$0")"

image=nokk3r/bababui
repo_url=https://github.com/nokk3r/bababui
source_branch=develop

usage() {
  echo "Использование: ./publish.sh <patch|minor|major|X.Y.Z> [--dry-run]" >&2
  exit 2
}

die() {
  echo "$1" >&2
  exit 1
}

replace() {
  sed "$2" "$1" >"$1.tmp"
  mv "$1.tmp" "$1"
}

bump=
dry_run=
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=1 ;;
    -*) usage ;;
    *)
      [ -z "$bump" ] || usage
      bump=$arg
      ;;
  esac
done
[ -n "$bump" ] || usage

current=$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' app/config.py)
[ -n "$current" ] || die "В app/config.py нет APP_VERSION"

case "$bump" in
  major) version=$(echo "$current" | awk -F. '{print $1 + 1 ".0.0"}') ;;
  minor) version=$(echo "$current" | awk -F. '{print $1 "." $2 + 1 ".0"}') ;;
  patch) version=$(echo "$current" | awk -F. '{print $1 "." $2 "." $3 + 1}') ;;
  *) version=$bump ;;
esac
echo "$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || usage

newest=$(printf '%s\n%s\n' "$current" "$version" | sort -V | tail -1)
[ "$version" != "$current" ] && [ "$newest" = "$version" ] \
  || die "Версия $version должна быть новее $current"

tag="v$version"
branch="release/$tag"

[ "$(git rev-parse --abbrev-ref HEAD)" = "$source_branch" ] \
  || die "Релиз выпускается из ветки $source_branch"
[ -z "$(git status --porcelain)" ] || die "Есть незакоммиченные изменения"
grep -q 'index.docker.io' "${DOCKER_CONFIG:-$HOME/.docker}/config.json" \
  || die "Нет входа в Docker Hub: docker login"

git fetch --quiet --tags origin
[ "$(git rev-parse HEAD)" = "$(git rev-parse "origin/$source_branch")" ] \
  || die "Локальная $source_branch расходится с origin/$source_branch"
git merge-base --is-ancestor origin/main HEAD \
  || die "origin/main не входит в $source_branch: сначала слейте его"
git merge-base --is-ancestor main HEAD \
  || die "Локальная main не входит в $source_branch"

if git rev-parse --quiet --verify "refs/tags/$tag" >/dev/null; then
  die "Тег $tag уже есть"
fi
if git rev-parse --quiet --verify "refs/heads/$branch" >/dev/null \
  || [ -n "$(git ls-remote --heads origin "$branch")" ]; then
  die "Ветка $branch уже есть"
fi

awk '
  /^## / { if (seen) exit; seen = ($0 == "## Не выпущено"); next }
  seen && NF && !/^### / { found = 1 }
  END { exit !found }
' CHANGELOG.md || die "В CHANGELOG.md пустой раздел «Не выпущено»"

docker run --rm -v "$PWD:/src:ro" -w /src \
  -e DATA_DIR=/tmp/data -e PYTHONDONTWRITEBYTECODE=1 \
  python:3.12-slim-bookworm \
  sh -c 'pip install --quiet --root-user-action=ignore -r requirements.txt \
    && python -m unittest discover -s tests' \
  || die "Тесты не прошли"

cat <<EOF

bababui $current -> $version
  ветка: $branch от $source_branch
  тег:   $tag
  образ: $image:$version и :latest, amd64 и arm64
  push:  $branch, main, $source_branch, $tag
EOF

[ -z "$dry_run" ] || exit 0

printf 'Выпускаем? [y/N] '
read -r answer
[ "$answer" = y ] || die "Отменено"

rollback() {
  git switch --quiet --force "$source_branch"
  git branch --quiet -D "$branch" 2>/dev/null || true
  git tag --delete "$tag" >/dev/null 2>&1 || true
}
trap rollback EXIT
trap 'exit 130' INT TERM

git switch --quiet -c "$branch"

replace app/config.py "s/^APP_VERSION = .*/APP_VERSION = \"$version\"/"
replace docker-compose.prod.yml "s#image: $image:.*#image: $image:$version#"
grep -q "image: $image:$version\$" docker-compose.prod.yml \
  || die "В docker-compose.prod.yml нет образа $image"

awk -v heading="## $version — $(date +%F)" '
  $0 == "## Не выпущено" && !done {
    print
    print ""
    print "### RU"
    print ""
    print "### EN"
    print ""
    print heading
    done = 1
    next
  }
  { print }
' CHANGELOG.md >CHANGELOG.md.tmp
mv CHANGELOG.md.tmp CHANGELOG.md

git add app/config.py docker-compose.prod.yml CHANGELOG.md
git commit --quiet -m "release $version"
git tag -a "$tag" -m "bababui $version"

# Атомарно: при отказе хоть в одной ссылке на GitHub не меняется ничего.
# Пробный push ловит отказ заранее, пока образ ещё не опубликован.
git push --quiet --dry-run --atomic origin \
  "$branch" "$branch:main" "$branch:$source_branch" "refs/tags/$tag"

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --label "org.opencontainers.image.source=$repo_url" \
  --label "org.opencontainers.image.version=$version" \
  --label "org.opencontainers.image.licenses=MIT" \
  --label "org.opencontainers.image.description=Local speed test for subscription nodes with a web interface" \
  -t "$image:$version" \
  -t "$image:latest" \
  --push \
  .

git push --quiet --atomic origin \
  "$branch" "$branch:main" "$branch:$source_branch" "refs/tags/$tag"

trap - EXIT
git fetch --quiet . "$branch:main"
git switch --quiet "$source_branch"
git merge --quiet --ff-only "$branch"

if command -v gh >/dev/null; then
  {
    awk -v heading="## $version " '
      index($0, heading) == 1 { found = 1; next }
      found && /^## / { exit }
      found
    ' CHANGELOG.md
    printf '\n**Docker:** [%s](https://hub.docker.com/r/%s/tags)\n\n```bash\ndocker pull %s\n```\n' \
      "$image:$version" "$image" "$image:$version"
  } | gh release create "$tag" --verify-tag --title "$tag" --notes-file - \
    || echo "GitHub Release не создан: gh release create $tag" >&2
else
  echo "gh не установлен, GitHub Release не создан"
fi

echo "Выпущено $tag, образ $image:$version"
