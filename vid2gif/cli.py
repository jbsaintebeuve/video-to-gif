"""vid2gif command line.

External tools: ffmpeg (required), yt-dlp (for links).
Runs on macOS, Linux and Windows (Python 3.9+, standard library only).

Security: no command goes through a shell; user input is always passed as
separate arguments, never interpolated into code.
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
    """Quick Actions run commands with a minimal PATH (/usr/bin:/bin)."""
    current = os.environ.get("PATH", "").split(os.pathsep)
    for extra in ("/opt/homebrew/bin", "/usr/local/bin"):
        if extra not in current and Path(extra).is_dir():
            current.append(extra)
    os.environ["PATH"] = os.pathsep.join(p for p in current if p)


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-8:])
        raise Vid2GifError("%s failed:\n%s" % (Path(cmd[0]).name, tail))
    return proc.stdout


def require(tool, hint):
    path = shutil.which(tool)
    if not path:
        raise Vid2GifError("%s not found. %s" % (tool, hint))
    return path


def human_size(n):
    if n < 1024:
        return "%d B" % n
    for unit in ("KB", "MB", "GB"):
        n /= 1024.0
        if n < 1024 or unit == "GB":
            return "%.1f %s" % (n, unit)


# Title and message are passed as argv, so nothing is interpreted as AppleScript.
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
            raise Vid2GifError("Cannot read the clipboard (install wl-clipboard or xclip).")
    return subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=False).stdout


# JXA: puts both the GIF data (for apps that accept a pasted animated image) and a
# file reference (Finder, Slack, Messages…) on the clipboard.
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

# The path is passed as a PowerShell argument ($args), never concatenated into the command.
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
            raise Vid2GifError("Install wl-clipboard or xclip to copy to the clipboard.")


def reveal(path):
    path = str(Path(path).resolve())
    if SYSTEM == "Darwin":
        subprocess.run(["open", "-R", path], check=False)
    elif SYSTEM == "Windows":
        subprocess.run(["explorer", "/select," + path], check=False)
    elif shutil.which("xdg-open"):
        subprocess.run(["xdg-open", str(Path(path).parent)], check=False)


def safe_name(s, limit=60):
    """Safe file name: no path separator, no '..', no leading '-'."""
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
    ytdlp = require("yt-dlp", "Install it: brew install yt-dlp  (or pipx install yt-dlp)")
    cmd = [
        ytdlp, "--no-playlist", "--no-progress", "--quiet", "--no-warnings",
        "--max-filesize", MAX_DOWNLOAD, "--restrict-filenames",
        # A GIF has no sound: prefer the best video-only stream.
        "-f", "bv*[height<=1080]/b[height<=1080]/bv*/b",
        "-o", str(Path(workdir) / "%(id)s.%(ext)s"),
        "--print", "after_move:%(filepath)s\t%(uploader_id,uploader|)s\t%(id)s",
    ]  # fmt: skip
    if cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]
    cmd += ["--", url]  # the URL can never be parsed as an option
    out = run(cmd).strip().splitlines()
    if not out:
        raise Vid2GifError("No video found at this URL.")
    workdir = Path(workdir).resolve()
    results = []
    for line in out:  # a post can hold several videos
        parts = line.split("\t")
        filepath = Path(parts[0]).resolve()
        if workdir not in filepath.parents or not filepath.is_file():
            raise Vid2GifError("Unexpected downloaded file: %s" % parts[0])
        uploader = parts[1] if len(parts) > 1 else ""
        vid = parts[2] if len(parts) > 2 else filepath.stem
        name = safe_name("%s_%s" % (uploader, vid) if uploader else vid)
        results.append((filepath, name))
    return results


# --------------------------------------------------------------------------- convert

# Only local files are read: a booby-trapped video (HLS playlist, concat…)
# cannot make ffmpeg open URLs.
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
    """Converts, shrinking width/fps/colors step by step while the GIF exceeds max_bytes."""
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
        log("  %s > %s limit, retrying smaller…" % (human_size(size), human_size(max_bytes)))
        # GIF size scales roughly with width² × fps.
        ratio = (max_bytes / float(size)) ** 0.5
        width = max(160, int(width * max(0.6, min(0.92, ratio)) // 2 * 2))
        if attempt % 2 == 1 and fps > 10:
            fps = max(10, fps - 3)
        if attempt >= 4 and colors > 64:
            colors //= 2
    return size, width, fps


# --------------------------------------------------------------------------- inputs


def expand_inputs(raw):
    """Keeps existing files as is; otherwise extracts URLs from the text
    (handy for selected or copied text that contains a link)."""
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
            raise Vid2GifError("Neither a file nor a link: %s" % chunk[:120])
        items += urls
    return list(dict.fromkeys(items))


def default_outdir():
    d = Path.home() / "Downloads"
    return d if d.is_dir() else Path.home()


def positive(cast):
    def parse(value):
        v = cast(value)
        if v <= 0:
            raise argparse.ArgumentTypeError("must be > 0")
        return v

    return parse


def time_value(value):
    if not re.match(r"^\d+(\.\d+)?$|^\d{1,2}(:\d{1,2}){1,2}(\.\d+)?$", value):
        raise argparse.ArgumentTypeError("expected format: 2.5 or 00:01:02.5")
    return value


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="vid2gif",
        description="Turn videos (files or X, YouTube, Instagram… links) into GIFs.",
        epilog='On macOS, "vid2gif setup" adds a "Convert to GIF" right-click action.',
    )
    p.add_argument("inputs", nargs="*", help="video files or URLs")
    p.add_argument("--clipboard", action="store_true", help="use the link or path on the clipboard")
    p.add_argument("-o", "--outdir", help="output folder (default: next to the file, or ~/Downloads for a link)")
    p.add_argument("-w", "--width", type=positive(int), default=480, help="max width in px (default 480)")
    p.add_argument("-r", "--fps", type=positive(int), default=15, help="frames per second (default 15)")
    p.add_argument("-s", "--start", type=time_value, help="start, e.g. 2.5 or 00:00:02.5")
    p.add_argument("-t", "--duration", type=time_value, help="duration, e.g. 4 (default: whole video, 60 s max)")
    p.add_argument("--max-mb", type=float, default=15.0, help="target max size in MB, 0 = no limit (default 15)")
    p.add_argument("-c", "--copy", action="store_true", help="copy the GIF to the clipboard")
    p.add_argument("--reveal", action="store_true", help="reveal the GIF in Finder / Explorer")
    p.add_argument("--notify", action="store_true", help="system notifications (useful from a right-click action)")
    p.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        help="e.g. chrome, safari, firefox, for videos that require being logged in",
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
            raise Vid2GifError("Nothing to convert: pass a file or a link, or copy a video link.")
        inputs.append(clip)
    inputs = expand_inputs(inputs)

    require("ffmpeg", "Install it: brew install ffmpeg  (Windows: winget install ffmpeg)")
    require("ffprobe", "ffprobe ships with ffmpeg.")

    max_bytes = int(args.max_mb * 1024 * 1024) if args.max_mb > 0 else 0
    produced = []

    with tempfile.TemporaryDirectory(prefix="vid2gif-") as tmp:
        for item in inputs:
            if URL_RE.match(item):
                if args.notify:
                    notify("vid2gif", "Downloading video…")
                print("↓ %s" % item)
                sources = download(item, tmp, args.cookies_from_browser)
                outdir = Path(args.outdir).expanduser() if args.outdir else default_outdir()
            else:
                path = Path(item)
                if path.suffix.lower() not in VIDEO_EXTS:
                    print("! unusual extension (%s), trying anyway" % path.suffix)
                sources = [(path, safe_name(path.stem))]
                outdir = Path(args.outdir).expanduser() if args.outdir else path.parent

            outdir.mkdir(parents=True, exist_ok=True)
            for video, name in sources:
                duration = args.duration
                if not duration:
                    total = probe(video)[2]
                    if total and total > MAX_SECONDS:
                        print("! %d s video: keeping the first %d s (see -t)" % (total, MAX_SECONDS))
                        duration = str(MAX_SECONDS)
                gif = unique_path(outdir / (name + ".gif"))
                if args.notify:
                    notify("vid2gif", "Converting to GIF…")
                print("→ %s" % gif)
                size, w, fps = convert(video, gif, args.width, args.fps, max_bytes, args.start, duration)
                print("✓ %s (%dpx, %d fps)" % (human_size(size), w, fps))
                produced.append((gif, size))

    if not produced:
        raise Vid2GifError("No GIF produced.")

    last_gif, last_size = produced[-1]
    msg = "%s — %s" % (last_gif.name, human_size(last_size))
    if args.copy:
        copy_gif_to_clipboard(last_gif)
        msg += " · copied, paste with ⌘V" if SYSTEM == "Darwin" else " · copied"
    if args.reveal:
        reveal(last_gif)
    if args.notify:
        notify("GIF ready ✅", msg)
    return 0


def safe_console():
    """Windows consoles (cp1252) cannot print → ✓…: replace them instead of crashing."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    safe_console()
    extend_path()
    # Subcommands: `vid2gif setup` / `vid2gif uninstall` (unless a file has that name).
    if argv and argv[0] in ("setup", "uninstall") and not Path(argv[0]).exists():
        from vid2gif import desktop

        return desktop.setup(argv[1:]) if argv[0] == "setup" else desktop.uninstall()
    return convert_all(parse_args(argv))


def entry():
    try:
        sys.exit(main())
    except Vid2GifError as e:
        print("Error: %s" % e, file=sys.stderr)
        if "--notify" in sys.argv:
            notify("vid2gif failed", str(e).splitlines()[0][:200])
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
