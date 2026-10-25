#!/usr/bin/env bash
# Replays the README demo against the real vid2gif in a throwaway HOME and prints
# the transcript, with the sandbox path shown as ~. The text in build.mjs must
# match this output. Needs ffmpeg, yt-dlp and network access.
# (The `vid2gif setup` output comes from vid2gif/desktop.py: setup writes to
# ~/Library and system preferences, so it is not replayed here.)
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
SANDBOX=$(cd "$(mktemp -d)" && pwd -P)
trap 'rm -rf "$SANDBOX"' EXIT
export HOME="$SANDBOX"
mkdir -p "$HOME/Downloads" "$HOME/Movies"

vid2gif() { PYTHONPATH="$ROOT" python3 -m vid2gif "$@"; }

ffmpeg -loglevel error -f lavfi -i "testsrc2=duration=20:size=1280x720:rate=30" -vf "noise=alls=12:allf=t" \
  -pix_fmt yuv420p "$HOME/Movies/holiday.mov"

run() {
  printf '%s $ %s\n' "$(pwd | sed "s|^$SANDBOX|~|")" "$*"
  "$@" 2>&1 | sed "s|$SANDBOX|~|g" || true
}

cd "$HOME"
# The demo also shows --copy; it is left out here so the clipboard is untouched.
run vid2gif https://x.com/weirdnotwild/status/2114199180243857583
run vid2gif Movies/holiday.mov -s 12 -t 4 --max-mb 3
