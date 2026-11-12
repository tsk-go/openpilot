#!/bin/bash
# Signing for tsk-go/openpilot in Claude Code cloud sessions: every commit here is by tsk-go and signed with the
# owner's SSH key, so GitHub shows it as Verified. The cloud environment's global git config signs with its own key
# (gpg.ssh.program /tmp/code-sign, shown as Unverified); this sets repo-local config that overrides it.
# Key and fingerprint: as in CLAUDE.md "Commits" (the same script is in tsk-go/starview-data). What this prints goes into the session's context.
# Without the key (or with a different one) commits in this clone fail instead of being signed with the wrong key.
set -u

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0                     # the owner's own machine: leave his git setup alone
fi

WANT="SHA256:ituxS1NO/VJowXXhvOv/nUdnZQYSQkHbkSL4fQIDC2E"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
KEY="$HOME/.ssh/claude_signing"
g() { git -C "$REPO" config "$@"; }

block() {
  g user.name tsk-go
  g user.email cmc686@gmail.com
  g commit.gpgsign true
  g gpg.format ssh
  g gpg.ssh.program false    # signing always fails -> no commit with the cloud key
  echo "openpilot signing: $1 Commits in $REPO are blocked (they would be Unverified). Don't commit or push here; tell the owner."
  exit 0
}

[ -n "${GIT_SIGNING_KEY_B64:-}" ] || block "GIT_SIGNING_KEY_B64 is not set in this environment."
command -v ssh-keygen >/dev/null 2>&1 || block "ssh-keygen is missing (apt-get install -y openssh-client)."

mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
umask 077
printf '%s' "$GIT_SIGNING_KEY_B64" | base64 -d > "$KEY.tmp" 2>/dev/null && mv "$KEY.tmp" "$KEY" || block "GIT_SIGNING_KEY_B64 isn't valid base64."
chmod 600 "$KEY"
ssh-keygen -y -f "$KEY" > "$KEY.pub" 2>/dev/null || block "GIT_SIGNING_KEY_B64 isn't an OpenSSH private key."
FP="$(ssh-keygen -lf "$KEY.pub" | awk '{print $2}')"
[ "$FP" = "$WANT" ] || block "the key in GIT_SIGNING_KEY_B64 is $FP, not the owner's $WANT."
echo "cmc686@gmail.com $(cut -d' ' -f1,2 "$KEY.pub")" > "$HOME/.ssh/allowed_signers"

g user.name tsk-go
g user.email cmc686@gmail.com
g gpg.format ssh
g gpg.ssh.program ssh-keygen
g user.signingkey "$KEY.pub"
g gpg.ssh.allowedSignersFile "$HOME/.ssh/allowed_signers"
g commit.gpgsign true
g tag.gpgsign true
echo "openpilot signing: commits in $REPO are by tsk-go <cmc686@gmail.com>, signed with $WANT."
