#!/usr/bin/env bash
# Merge firestar5683/StarPilot Dom into StarPilot-Dom, keeping every change made on StarPilot-Dom.
# Pushes only when the merge is clean and every changed Python file still compiles; otherwise nothing changes on
# GitHub and the run's summary says why. Run by .github/workflows/sync_upstream.yaml ("Run workflow" button).
set -euo pipefail

UPSTREAM_URL="${UPSTREAM_URL:-https://github.com/firestar5683/StarPilot}"
UPSTREAM_BRANCH="${UPSTREAM_BRANCH:-Dom}"
TARGET="${TARGET:-StarPilot-Dom}"
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/stdout}"
PUSH="${PUSH:-1}"

git fetch --no-tags "$UPSTREAM_URL" "$UPSTREAM_BRANCH"
UP=$(git rev-parse FETCH_HEAD)
if git merge-base --is-ancestor "$UP" HEAD; then
  echo "### Already up to date with firestar's $UPSTREAM_BRANCH" >> "$SUMMARY"
  exit 0
fi

BEFORE=$(git rev-parse HEAD)
NEW=$(git log --no-merges --format='- %h %s (%an)' "HEAD..$UP")

if ! git merge --no-edit -m "Merge firestar5683/StarPilot $UPSTREAM_BRANCH into $TARGET" "$UP"; then
  {
    echo "### Not synced: firestar's changes conflict with ours"
    echo "Nothing was pushed. Files changed on both sides:"
    git diff --name-only --diff-filter=U | sed 's/^/- /'
  } >> "$SUMMARY"
  git merge --abort
  exit 1
fi

# every Python file the merge changed must still compile (catches a broken merge before the car gets it)
mapfile -t CHANGED < <(git diff --name-only --diff-filter=AM "$BEFORE" HEAD -- '*.py')
if [ "${#CHANGED[@]}" -gt 0 ]; then
  if ! ERR=$(PYTHONPYCACHEPREFIX="$(mktemp -d)" python3 -m py_compile "${CHANGED[@]}" 2>&1); then
    {
      echo "### Not synced: a merged Python file doesn't compile"
      echo "Nothing was pushed."
      echo '```'
      echo "$ERR" | tail -20
      echo '```'
    } >> "$SUMMARY"
    exit 1
  fi
fi

if [ "$PUSH" = "1" ]; then
  git push origin "HEAD:refs/heads/$TARGET"
fi
{
  echo "### Synced: firestar's $UPSTREAM_BRANCH merged into $TARGET"
  echo "Press update on the comma to get it. New from firestar:"
  echo "$NEW"
} >> "$SUMMARY"
