import plistlib
import shlex

import pytest

from vid2gif import desktop


@pytest.fixture
def fake_exe(tmp_path, monkeypatch):
    exe = tmp_path / "bin dir" / "vid2gif"
    exe.parent.mkdir()
    exe.write_text("#!/bin/sh\n")
    monkeypatch.setenv("VID2GIF_EXE", str(exe))
    return exe


def test_launcher_prefers_homebrew_path(fake_exe):
    assert desktop.launcher() == [str(fake_exe)]


def test_shell_command_quotes_paths(fake_exe):
    cmd = desktop.shell_command('--copy "$@"')
    assert cmd.startswith("cd / && " + shlex.quote(str(fake_exe)) + ' --copy "$@"')
    assert "'" in cmd  # the path with a space is quoted


@pytest.mark.parametrize("wf", desktop.WORKFLOWS, ids=lambda w: w["name"])
def test_workflow_bundle_is_valid(tmp_path, fake_exe, wf):
    bundle = desktop.write_workflow(wf, tmp_path)
    info = plistlib.loads((bundle / "Contents/Info.plist").read_bytes())
    doc = plistlib.loads((bundle / "Contents/document.wflow").read_bytes())

    service = info["NSServices"][0]
    assert service["NSMenuItem"]["default"] == wf["name"]
    assert service["NSMessage"] == "runWorkflowAsService"

    params = doc["actions"][0]["action"]["ActionParameters"]
    assert params["inputMethod"] == 1
    assert str(fake_exe) in params["COMMAND_STRING"]
    assert doc["workflowMetaData"]["serviceInputTypeIdentifier"] == wf["input"]


def test_finder_action_limited_to_movies(tmp_path, fake_exe):
    bundle = desktop.write_workflow(desktop.WORKFLOWS[0], tmp_path)
    service = plistlib.loads((bundle / "Contents/Info.plist").read_bytes())["NSServices"][0]
    assert service["NSSendFileTypes"] == ["public.movie"]


def test_rewrite_replaces_existing_bundle(tmp_path, fake_exe):
    wf = desktop.WORKFLOWS[2]
    bundle = desktop.write_workflow(wf, tmp_path)
    (bundle / "Contents/stale").touch()
    desktop.write_workflow(wf, tmp_path)
    assert not (bundle / "Contents/stale").exists()


def test_setup_refuses_outside_macos(monkeypatch):
    monkeypatch.setattr(desktop, "SYSTEM", "Linux")
    with pytest.raises(desktop.Vid2GifError):
        desktop.setup([])


def test_shortcut_added_once_and_removed(monkeypatch):
    store = {"prefs": {"NSServicesStatus": {"(null) - Autre - runWorkflowAsService": {"key_equivalent": "@k"}}}}
    monkeypatch.setattr(desktop, "_read_pbs", lambda: plistlib.loads(plistlib.dumps(store["prefs"])))
    monkeypatch.setattr(desktop, "_write_pbs", lambda prefs: store.update(prefs=prefs))

    assert desktop.set_shortcut("GIF", "@~^g") is True
    assert store["prefs"]["NSServicesStatus"]["(null) - GIF - runWorkflowAsService"] == {"key_equivalent": "@~^g"}
    # A shortcut that is already set (by the user) is never overwritten.
    assert desktop.set_shortcut("GIF", "@x") is False
    desktop.remove_shortcut("GIF")
    assert list(store["prefs"]["NSServicesStatus"]) == ["(null) - Autre - runWorkflowAsService"]


def test_legacy_french_actions_are_migrated(tmp_path, monkeypatch, fake_exe):
    old_key = "(null) - GIF depuis le lien copié - runWorkflowAsService"
    new_key = "(null) - GIF from Copied Link - runWorkflowAsService"
    store = {"prefs": {"NSServicesStatus": {old_key: {"key_equivalent": "@~^v"}}}}
    monkeypatch.setattr(desktop, "_read_pbs", lambda: plistlib.loads(plistlib.dumps(store["prefs"])))
    monkeypatch.setattr(desktop, "_write_pbs", lambda prefs: store.update(prefs=prefs))
    services = tmp_path / "Services"
    monkeypatch.setattr(desktop, "SERVICES", services)
    for old in desktop.LEGACY_NAMES:
        (services / (old + ".workflow") / "Contents").mkdir(parents=True)

    desktop._remove_legacy()

    assert not any(services.iterdir())
    # The user's own shortcut follows the renamed action.
    assert store["prefs"]["NSServicesStatus"] == {new_key: {"key_equivalent": "@~^v"}}
