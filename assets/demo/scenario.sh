#!/usr/bin/env bash
# Rejoue la démo du README avec le vrai vid2gif dans un HOME jetable et affiche
# la transcription, le chemin du bac à sable étant remplacé par ~. Le texte de
# build.mjs doit correspondre à cette sortie. Nécessite ffmpeg, yt-dlp et le réseau.
# (La sortie de `vid2gif setup` vient de vid2gif/desktop.py : setup écrit dans
# ~/Library et les préférences système, il n'est donc pas rejoué ici.)
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
SANDBOX=$(cd "$(mktemp -d)" && pwd -P)
trap 'rm -rf "$SANDBOX"' EXIT
export HOME="$SANDBOX"
mkdir -p "$HOME/Downloads" "$HOME/Movies"

vid2gif() { PYTHONPATH="$ROOT" python3 -m vid2gif "$@"; }

ffmpeg -loglevel error -f lavfi -i "testsrc2=duration=20:size=1280x720:rate=30" -vf "noise=alls=12:allf=t" \
  -pix_fmt yuv420p "$HOME/Movies/vacances.mov"

run() {
  printf '%s $ %s\n' "$(pwd | sed "s|^$SANDBOX|~|")" "$*"
  "$@" 2>&1 | sed "s|$SANDBOX|~|g" || true
}

cd "$HOME"
# La démo montre aussi --copy ; il est omis ici pour ne pas toucher au presse-papiers.
run vid2gif https://x.com/weirdnotwild/status/2114199180243857583
run vid2gif Movies/vacances.mov -s 12 -t 4 --max-mb 3
