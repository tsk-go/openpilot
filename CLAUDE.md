# Commits

- Every commit (including merges) is authored and committed as `tsk-go <cmc686@gmail.com>`. Before committing, run
  `git config user.name tsk-go && git config user.email cmc686@gmail.com`.
- Never mention Claude or Anthropic in commits: no `Co-Authored-By` trailer, no session links, no attribution lines.

# Syncing upstream

"Sync" means: merge https://github.com/firestar5683/StarPilot branch `SecretGoodStarPilot` into this repo's
`SecretGoodStarPilot_v2` with a merge commit (`git fetch https://github.com/firestar5683/StarPilot.git SecretGoodStarPilot
&& git merge --no-edit -m "Merge upstream StarPilot SecretGoodStarPilot" FETCH_HEAD`), then a normal push.
Never rebase or force-push for a sync: the local commits must be kept as they are. On a conflict, stop and ask.
