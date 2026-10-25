import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from vid2gif import __version__, cli

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg absent")


def make_video(path, seconds=2, size="640x360", rate=25):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "testsrc2=duration=%s:size=%s:rate=%s" % (seconds, size, rate),
         "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )  # fmt: skip
    return path


# --------------------------------------------------------------------------- pure helpers


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("weirdnotwild_2114199158982606849", "weirdnotwild_2114199158982606849"),
        ("../../etc/passwd", "etcpasswd"),
        ("..", "video"),
        ("-rf", "rf"),
        ("a/b\\c:d*e?f", "abcdef"),
        ("vidéo été", "vidéo_été"),
        ("", "video"),
    ],
)
def test_safe_name(raw, expected):
    assert cli.safe_name(raw) == expected


def test_safe_name_is_bounded():
    assert len(cli.safe_name("x" * 500)) == 60


def test_unique_path(tmp_path):
    first = tmp_path / "a.gif"
    assert cli.unique_path(first) == first
    first.touch()
    assert cli.unique_path(first) == tmp_path / "a-2.gif"
    (tmp_path / "a-2.gif").touch()
    assert cli.unique_path(first) == tmp_path / "a-3.gif"


def test_expand_inputs_extracts_urls_from_text():
    text = "look at this https://x.com/weirdnotwild/status/2114199180243857583 !"
    assert cli.expand_inputs([text]) == ["https://x.com/weirdnotwild/status/2114199180243857583"]


def test_expand_inputs_strips_punctuation_and_dedupes():
    raw = ["(https://youtu.be/abc).", "https://youtu.be/abc"]
    assert cli.expand_inputs(raw) == ["https://youtu.be/abc"]


def test_expand_inputs_files(tmp_path):
    f = tmp_path / "clip.mp4"
    f.touch()
    assert cli.expand_inputs([str(f), "file://" + str(f)]) == [str(f.resolve())]


def test_expand_inputs_rejects_garbage():
    with pytest.raises(cli.Vid2GifError):
        cli.expand_inputs(["--exec rm -rf ~"])


def test_url_option_injection_is_not_a_url():
    # A "URL" that starts with an option must never be accepted.
    assert not cli.URL_RE.match("--exec=touch /tmp/pwned")


@pytest.mark.parametrize("value", ["2", "2.5", "00:01", "00:00:02.5"])
def test_time_value_ok(value):
    assert cli.time_value(value) == value


@pytest.mark.parametrize("value", ["-1", "abc", "1;rm", "2s"])
def test_time_value_rejects(value):
    with pytest.raises(argparse.ArgumentTypeError):
        cli.time_value(value)


@pytest.mark.parametrize("flag", ["-w", "-r"])
def test_positive_args(flag):
    with pytest.raises(SystemExit):
        cli.parse_args([flag, "0", "x.mp4"])


def test_human_size():
    assert cli.human_size(512) == "512 B"
    assert cli.human_size(2048) == "2.0 KB"
    assert cli.human_size(5 * 1024 * 1024) == "5.0 MB"


def test_version_flag(capsys):
    with pytest.raises(SystemExit):
        cli.parse_args(["--version"])
    assert __version__ in capsys.readouterr().out


def test_download_rejects_paths_outside_workdir(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "require", lambda *a: "yt-dlp")
    monkeypatch.setattr(cli, "run", lambda cmd: "/etc/passwd\tevil\t1\n")
    with pytest.raises(cli.Vid2GifError):
        cli.download("https://example.com/v", tmp_path)


def test_download_passes_url_after_double_dash(tmp_path, monkeypatch):
    seen = {}
    video = tmp_path / "1.mp4"
    video.touch()

    def fake_run(cmd):
        seen["cmd"] = cmd
        return "%s\tsomeone\t1\n" % video

    monkeypatch.setattr(cli, "require", lambda *a: "yt-dlp")
    monkeypatch.setattr(cli, "run", fake_run)
    assert cli.download("https://example.com/v", tmp_path) == [(video.resolve(), "someone_1")]
    assert seen["cmd"][-2:] == ["--", "https://example.com/v"]


# --------------------------------------------------------------------------- ffmpeg


@needs_ffmpeg
def test_convert_end_to_end(tmp_path):
    video = make_video(tmp_path / "clip.mp4")
    assert cli.main([str(video), "-w", "200", "-r", "10"]) == 0
    gif = tmp_path / "clip.gif"
    assert gif.read_bytes()[:6] == b"GIF89a"
    w, h, _ = cli.probe(gif)
    assert (w, h) == (200, 112)


@needs_ffmpeg
def test_never_upscales(tmp_path):
    video = make_video(tmp_path / "small.mp4", size="160x90")
    cli.main([str(video), "-w", "800"])
    assert cli.probe(tmp_path / "small.gif")[0] == 160


@needs_ffmpeg
def test_max_size_shrinks(tmp_path):
    video = make_video(tmp_path / "big.mp4", seconds=3, size="1280x720")
    size, width, _ = cli.convert(video, tmp_path / "big.gif", 640, 15, 300 * 1024, log=lambda *_: None)
    assert width < 640
    assert size <= 300 * 1024 or width == 160


@needs_ffmpeg
def test_start_and_duration(tmp_path):
    video = make_video(tmp_path / "clip.mp4", seconds=4)
    cli.main([str(video), "-s", "1", "-t", "1", "-r", "10", "-o", str(tmp_path / "out")])
    _, _, duration = cli.probe(tmp_path / "out" / "clip.gif")
    assert duration == pytest.approx(1.0, abs=0.2)


@needs_ffmpeg
def test_ffmpeg_refuses_network_playlists(tmp_path):
    # A "video" that is really a playlist pointing to a URL.
    evil = tmp_path / "evil.m3u8"
    evil.write_text("#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nhttp://127.0.0.1:9/x.ts\n#EXT-X-ENDLIST\n")
    with pytest.raises(cli.Vid2GifError, match="not on whitelist 'file'"):
        cli.main([str(evil), "-o", str(tmp_path)])


@needs_ffmpeg
def test_module_entrypoint(tmp_path):
    video = make_video(tmp_path / "m.mp4", seconds=1)
    root = Path(__file__).resolve().parent.parent
    proc = subprocess.run([sys.executable, "-m", "vid2gif", str(video)], cwd=str(root), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "m.gif").exists()
