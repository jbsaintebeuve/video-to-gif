"""Ligne de commande vid2gif.

Dépendances externes : ffmpeg (obligatoire), yt-dlp (pour les liens).
Fonctionne sur macOS, Linux et Windows (Python 3.9+, bibliothèque standard uniquement).

Sécurité : aucune commande ne passe par un shell ; les entrées utilisateur sont
toujours transmises comme arguments distincts (jamais interpolées dans du code).
"""

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from vid2gif import __version__

SYSTEM = platform.system()  # "Darwin", "Linux", "Windows"

URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
URL_FIND_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
VIDEO_EXTS = {
    ".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".gifv",
    ".3gp", ".mpg", ".mpeg", ".wmv", ".flv",
}  # fmt: skip
MAX_DOWNLOAD = "500M"


class Vid2GifError(Exception):
    pass


# --------------------------------------------------------------------------- helpers


def extend_path():
    """Les Quick Actions lancent les commandes avec un PATH minimal (/usr/bin:/bin)."""
    current = os.environ.get("PATH", "").split(os.pathsep)
    for extra in ("/opt/homebrew/bin", "/usr/local/bin"):
        if extra not in current and Path(extra).is_dir():
            current.append(extra)
    os.environ["PATH"] = os.pathsep.join(p for p in current if p)


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-8:])
        raise Vid2GifError("La commande %s a échoué :\n%s" % (Path(cmd[0]).name, tail))
    return proc.stdout


def require(tool, hint):
    path = shutil.which(tool)
    if not path:
        raise Vid2GifError("%s introuvable. %s" % (tool, hint))
    return path


def human_size(n):
    if n < 1024:
        return "%d o" % n
    for unit in ("Ko", "Mo", "Go"):
        n /= 1024.0
        if n < 1024 or unit == "Go":
            return "%.1f %s" % (n, unit)


# Le titre et le message passent en argv : rien n'est interprété comme de l'AppleScript.
_MAC_NOTIFY = "on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv)\nend run"


def notify(title, message):
    try:
        if SYSTEM == "Darwin":
            subprocess.run(["osascript", "-e", _MAC_NOTIFY, title, message], check=False)
        elif SYSTEM == "Linux" and shutil.which("notify-send"):
            subprocess.run(["notify-send", "--", title, message], check=False)
    except OSError:
        pass


def read_clipboard_text():
    if SYSTEM == "Darwin":
        cmd = ["pbpaste"]
    elif SYSTEM == "Windows":
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard"]
    else:
        candidates = (["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"], ["xsel", "-b"])
        cmd = next((c for c in candidates if shutil.which(c[0])), None)
        if cmd is None:
            raise Vid2GifError("Impossible de lire le presse-papiers (installez wl-clipboard ou xclip).")
    return subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=False).stdout


# JXA : met dans le presse-papiers à la fois les données GIF (collage dans les apps
# qui acceptent une image animée) et une référence fichier (Finder, Slack, Messages…).
_MAC_COPY_JXA = r"""
ObjC.import('AppKit');
function run(argv) {
  var path = argv[0];
  var data = $.NSData.dataWithContentsOfFile(path);
  var url = $.NSURL.fileURLWithPath(path);
  var item = $.NSPasteboardItem.alloc.init;
  item.setDataForType(data, 'com.compuserve.gif');
  item.setStringForType(url.absoluteString, 'public.file-url');
  var pb = $.NSPasteboard.generalPasteboard;
  pb.clearContents;
  return pb.writeObjects($([item]));
}
"""

# Le chemin est passé en argument PowerShell ($args), jamais concaténé à la commande.
_WIN_COPY_PS = "Set-Clipboard -LiteralPath $args[0]"


def copy_gif_to_clipboard(gif):
    gif = str(Path(gif).resolve())
    if SYSTEM == "Darwin":
        run(["osascript", "-l", "JavaScript", "-e", _MAC_COPY_JXA, gif])
    elif SYSTEM == "Windows":
        run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _WIN_COPY_PS, gif])
    else:
        data = Path(gif).read_bytes()
        if shutil.which("wl-copy"):
            subprocess.run(["wl-copy", "--type", "image/gif"], input=data, check=True)
        elif shutil.which("xclip"):
            subprocess.run(["xclip", "-selection", "clipboard", "-t", "image/gif"], input=data, check=True)
        else:
            raise Vid2GifError("Installez wl-clipboard ou xclip pour copier dans le presse-papiers.")


def reveal(path):
    path = str(Path(path).resolve())
    if SYSTEM == "Darwin":
        subprocess.run(["open", "-R", path], check=False)
    elif SYSTEM == "Windows":
        subprocess.run(["explorer", "/select," + path], check=False)
    elif shutil.which("xdg-open"):
        subprocess.run(["xdg-open", str(Path(path).parent)], check=False)


def safe_name(s, limit=60):
    """Nom de fichier sûr : pas de séparateur de chemin, pas de '..', pas de '-' initial."""
    s = re.sub(r"[^\w\-. ]+", "", s, flags=re.UNICODE).strip().replace(" ", "_")
    s = s[:limit].strip("._-")
    return s or "video"


def unique_path(path):
    path = Path(path)
    if not path.exists():
        return path
    i = 2
    while True:
        candidate = path.with_name("%s-%d%s" % (path.stem, i, path.suffix))
        if not candidate.exists():
            return candidate
        i += 1


# --------------------------------------------------------------------------- download


def download(url, workdir, cookies_from_browser=None):
    ytdlp = require("yt-dlp", "Installez-le : brew install yt-dlp  (ou pipx install yt-dlp)")
    cmd = [
        ytdlp, "--no-playlist", "--no-progress", "--quiet", "--no-warnings",
        "--max-filesize", MAX_DOWNLOAD, "--restrict-filenames",
        # Pas besoin de son pour un GIF : meilleure vidéo seule si possible.
        "-f", "bv*[height<=1080]/b[height<=1080]/bv*/b",
        "-o", str(Path(workdir) / "%(id)s.%(ext)s"),
        "--print", "after_move:%(filepath)s\t%(uploader_id,uploader|)s\t%(id)s",
    ]  # fmt: skip
    if cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]
    cmd += ["--", url]  # l'URL ne peut pas être interprétée comme une option
    out = run(cmd).strip().splitlines()
    if not out:
        raise Vid2GifError("Aucune vidéo trouvée à cette adresse.")
    workdir = Path(workdir).resolve()
    results = []
    for line in out:  # un post peut contenir plusieurs vidéos
        parts = line.split("\t")
        filepath = Path(parts[0]).resolve()
        if workdir not in filepath.parents or not filepath.is_file():
            raise Vid2GifError("Fichier téléchargé inattendu : %s" % parts[0])
        uploader = parts[1] if len(parts) > 1 else ""
        vid = parts[2] if len(parts) > 2 else filepath.stem
        name = safe_name("%s_%s" % (uploader, vid) if uploader else vid)
        results.append((filepath, name))
    return results


# --------------------------------------------------------------------------- convert

# Seuls les fichiers locaux sont lus : une vidéo piégée (playlist HLS, concat…)
# ne peut pas faire ouvrir d'URL ou d'autres fichiers à ffmpeg.
_FF_SAFE = ["-protocol_whitelist", "file"]


def probe(video):
    out = run(
        ["ffprobe", "-v", "error", *_FF_SAFE, "-select_streams", "v:0",
         "-show_entries", "stream=width,height:format=duration",
         "-of", "default=noprint_wrappers=1", str(Path(video).resolve())]
    )  # fmt: skip
    info = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)

    def num(key, cast):
        try:
            return cast(info.get(key, ""))
        except ValueError:
            return None

    return num("width", int), num("height", int), num("duration", float)


def ffmpeg_to_gif(video, gif, width, fps, start=None, duration=None, colors=256):
    vf = (
        "fps={fps},scale='min({w},iw)':-2:flags=lanczos,split[a][b];"
        "[a]palettegen=max_colors={c}:stats_mode=diff[p];"
        "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
    ).format(fps=int(fps), w=int(width), c=int(colors))
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *_FF_SAFE]
    if start:
        cmd += ["-ss", str(start)]
    if duration:
        cmd += ["-t", str(duration)]
    cmd += ["-i", str(Path(video).resolve()), "-an", "-vf", vf, "-loop", "0", str(Path(gif).resolve())]
    run(cmd)


def convert(video, gif, width, fps, max_bytes, start=None, duration=None, log=print):
    """Convertit en réduisant progressivement taille/fps/couleurs si le GIF dépasse max_bytes."""
    src_w, _, _ = probe(video)
    if src_w:
        width = min(width, src_w)
    colors = 256
    size = 0
    for attempt in range(8):
        ffmpeg_to_gif(video, gif, width, fps, start, duration, colors)
        size = Path(gif).stat().st_size
        if not max_bytes or size <= max_bytes:
            break
        log("  %s > limite %s, nouvel essai plus léger…" % (human_size(size), human_size(max_bytes)))
        # Le poids d'un GIF varie à peu près avec largeur² × fps.
        ratio = (max_bytes / float(size)) ** 0.5
        width = max(160, int(width * max(0.6, min(0.92, ratio)) // 2 * 2))
        if attempt % 2 == 1 and fps > 10:
            fps = max(10, fps - 3)
        if attempt >= 4 and colors > 64:
            colors //= 2
    return size, width, fps


# --------------------------------------------------------------------------- inputs


def expand_inputs(raw):
    """Garde les fichiers existants tels quels ; ailleurs, extrait les URLs du texte
    (utile pour un texte sélectionné ou copié qui contient un lien)."""
    items = []
    for chunk in raw:
        chunk = chunk.strip()
        if not chunk:
            continue
        as_path = Path(chunk[7:] if chunk.startswith("file://") else chunk).expanduser()
        if as_path.is_file():
            items.append(str(as_path.resolve()))
            continue
        urls = [u.rstrip(").,;»>") for u in URL_FIND_RE.findall(chunk)]
        if not urls:
            raise Vid2GifError("Ni un fichier ni un lien : %s" % chunk[:120])
        items += urls
    return list(dict.fromkeys(items))


def default_outdir():
    d = Path.home() / "Downloads"
    return d if d.is_dir() else Path.home()


def positive(cast):
    def parse(value):
        v = cast(value)
        if v <= 0:
            raise argparse.ArgumentTypeError("doit être > 0")
        return v

    return parse


def time_value(value):
    if not re.match(r"^\d+(\.\d+)?$|^\d{1,2}(:\d{1,2}){1,2}(\.\d+)?$", value):
        raise argparse.ArgumentTypeError("format attendu : 2.5 ou 00:01:02.5")
    return value


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="vid2gif",
        description="Convertit des vidéos (fichiers ou liens X, YouTube, Instagram…) en GIF.",
        epilog="Sous macOS, « vid2gif setup » ajoute le clic droit « Convertir en GIF ».",
    )
    p.add_argument("inputs", nargs="*", help="fichiers vidéo ou URLs")
    p.add_argument("--clipboard", action="store_true", help="prend le lien ou le chemin présent dans le presse-papiers")
    p.add_argument("-o", "--outdir", help="dossier de sortie (défaut : à côté du fichier, ou ~/Downloads pour un lien)")
    p.add_argument("-w", "--width", type=positive(int), default=480, help="largeur max en px (défaut 480)")
    p.add_argument("-r", "--fps", type=positive(int), default=15, help="images/seconde (défaut 15)")
    p.add_argument("-s", "--start", type=time_value, help="début, ex. 2.5 ou 00:00:02.5")
    p.add_argument("-t", "--duration", type=time_value, help="durée, ex. 4 (défaut : toute la vidéo, 60 s max)")
    p.add_argument("--max-mb", type=float, default=15.0, help="poids max visé en Mo, 0 = illimité (défaut 15)")
    p.add_argument("-c", "--copy", action="store_true", help="copie le GIF dans le presse-papiers")
    p.add_argument("--reveal", action="store_true", help="affiche le GIF dans le Finder / Explorateur")
    p.add_argument("--notify", action="store_true", help="notifications système (utile depuis un clic droit)")
    p.add_argument(
        "--cookies-from-browser",
        metavar="NAVIGATEUR",
        help="ex. chrome, safari, firefox — pour les vidéos qui demandent d'être connecté",
    )
    p.add_argument("-V", "--version", action="version", version="vid2gif " + __version__)
    return p.parse_args(argv)


# --------------------------------------------------------------------------- main

MAX_SECONDS = 60


def convert_all(args):
    inputs = list(args.inputs)
    if args.clipboard or not inputs:
        clip = read_clipboard_text().strip()
        if not clip:
            raise Vid2GifError("Rien à convertir : donnez un fichier ou un lien, ou copiez un lien vidéo.")
        inputs.append(clip)
    inputs = expand_inputs(inputs)

    require("ffmpeg", "Installez-le : brew install ffmpeg  (Windows : winget install ffmpeg)")
    require("ffprobe", "ffprobe est fourni avec ffmpeg.")

    max_bytes = int(args.max_mb * 1024 * 1024) if args.max_mb > 0 else 0
    produced = []

    with tempfile.TemporaryDirectory(prefix="vid2gif-") as tmp:
        for item in inputs:
            if URL_RE.match(item):
                if args.notify:
                    notify("vid2gif", "Téléchargement de la vidéo…")
                print("↓ %s" % item)
                sources = download(item, tmp, args.cookies_from_browser)
                outdir = Path(args.outdir).expanduser() if args.outdir else default_outdir()
            else:
                path = Path(item)
                if path.suffix.lower() not in VIDEO_EXTS:
                    print("! extension inhabituelle (%s), on tente quand même" % path.suffix)
                sources = [(path, safe_name(path.stem))]
                outdir = Path(args.outdir).expanduser() if args.outdir else path.parent

            outdir.mkdir(parents=True, exist_ok=True)
            for video, name in sources:
                duration = args.duration
                if not duration:
                    total = probe(video)[2]
                    if total and total > MAX_SECONDS:
                        print("! vidéo de %d s : on garde les %d premières secondes (option -t)" % (total, MAX_SECONDS))
                        duration = str(MAX_SECONDS)
                gif = unique_path(outdir / (name + ".gif"))
                if args.notify:
                    notify("vid2gif", "Conversion en GIF…")
                print("→ %s" % gif)
                size, w, fps = convert(video, gif, args.width, args.fps, max_bytes, args.start, duration)
                print("✓ %s (%dpx, %d i/s)" % (human_size(size), w, fps))
                produced.append((gif, size))

    if not produced:
        raise Vid2GifError("Aucun GIF produit.")

    last_gif, last_size = produced[-1]
    msg = "%s — %s" % (last_gif.name, human_size(last_size))
    if args.copy:
        copy_gif_to_clipboard(last_gif)
        msg += " · copié, prêt à coller ⌘V" if SYSTEM == "Darwin" else " · copié"
    if args.reveal:
        reveal(last_gif)
    if args.notify:
        notify("GIF prêt ✅", msg)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    extend_path()
    # Sous-commandes : `vid2gif setup` / `vid2gif uninstall` (sauf si un fichier porte ce nom).
    if argv and argv[0] in ("setup", "uninstall") and not Path(argv[0]).exists():
        from vid2gif import desktop

        return desktop.setup(argv[1:]) if argv[0] == "setup" else desktop.uninstall()
    return convert_all(parse_args(argv))


def entry():
    try:
        sys.exit(main())
    except Vid2GifError as e:
        print("Erreur : %s" % e, file=sys.stderr)
        if "--notify" in sys.argv:
            notify("vid2gif — échec", str(e).splitlines()[0][:200])
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
