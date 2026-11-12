#!/bin/bash
# Signing for tsk-go/openpilot in Claude Code cloud sessions: every commit here is by tsk-go and signed with one of
# the owner's two SSH keys, so GitHub shows it as Verified. The cloud environment's global git config signs with its
# own key (gpg.ssh.program /tmp/code-sign, shown as Unverified); this sets repo-local config that overrides it.
# The keys: as in CLAUDE.md "Commits" (the same script is in tsk-go/starview-data). What this prints goes into the
# session's context. Without one of the two keys (or with another one) commits in this clone fail instead of being
# signed with the wrong key.
set -u

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0                     # the owner's own machine: leave his git setup alone
fi

NAME="openpilot"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
# Both are Signing Keys on the tsk-go GitHub account; only these two may sign here.
MAIN_PUB="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFgAaE174fTZQ1Z9Ks/WMMnBHjM3lUsvrsvamI7ZrNXL"   # private key: GIT_SIGNING_KEY_B64
MAIN_FP="SHA256:ituxS1NO/VJowXXhvOv/nUdnZQYSQkHbkSL4fQIDC2E"
CHAT_PUB="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGAojto2C+2H/F8PZ7pC8QIrNzCzuVbYf11rVhZub9UH"   # "StarView chat": ~/.ssh/chat_signing
CHAT_FP="SHA256:98d19r36BEJtwbf8sddMlMqnjrmEf1dEHMqNcT3u9ww"
g() { git -C "$REPO" config "$@"; }

block() {
  g user.name tsk-go
  g user.email cmc686@gmail.com
  g commit.gpgsign true
  g gpg.format ssh
  g gpg.ssh.program false    # signing always fails -> no commit with the cloud key
  echo "$NAME signing: $1 Commits in $REPO are blocked (they would be Unverified). Don't commit or push here; tell the owner."
  exit 0
}

command -v ssh-keygen >/dev/null 2>&1 || block "ssh-keygen is missing (apt-get install -y openssh-client)."
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
umask 077

if [ -n "${GIT_SIGNING_KEY_B64:-}" ]; then
  # cloud sessions: the main key, from the environment
  KEY="$HOME/.ssh/claude_signing"
  WANT="$MAIN_FP"
  printf '%s' "$GIT_SIGNING_KEY_B64" | base64 -d > "$KEY.tmp" 2>/dev/null && mv "$KEY.tmp" "$KEY" || block "GIT_SIGNING_KEY_B64 isn't valid base64."
  chmod 600 "$KEY"
  ssh-keygen -y -f "$KEY" > "$KEY.pub" 2>/dev/null || block "GIT_SIGNING_KEY_B64 isn't an OpenSSH private key."
elif [ -f "$HOME/.ssh/chat_signing" ]; then
  # the claude.ai StarView chat (no environment variables): its own key file, left as it is
  KEY="$HOME/.ssh/chat_signing"
  WANT="$CHAT_FP"
  ssh-keygen -y -f "$KEY" > "$KEY.pub" 2>/dev/null || block "~/.ssh/chat_signing can't be read as an OpenSSH private key (it must be chmod 600)."
else
  block "neither GIT_SIGNING_KEY_B64 nor ~/.ssh/chat_signing is here."
fi

FP="$(ssh-keygen -lf "$KEY.pub" | awk '{print $2}')"
[ "$FP" = "$WANT" ] || block "$KEY is $FP, not the owner's $WANT."
printf 'cmc686@gmail.com %s\ncmc686@gmail.com %s\n' "$MAIN_PUB" "$CHAT_PUB" > "$HOME/.ssh/allowed_signers"

g user.name tsk-go
g user.email cmc686@gmail.com
g gpg.format ssh
g gpg.ssh.program ssh-keygen
g user.signingkey "$KEY.pub"
g gpg.ssh.allowedSignersFile "$HOME/.ssh/allowed_signers"
g commit.gpgsign true
g tag.gpgsign true
echo "$NAME signing: commits in $REPO are by tsk-go <cmc686@gmail.com>, signed with $FP ($KEY)."
