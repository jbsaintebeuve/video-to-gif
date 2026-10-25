"""Intégration bureau : `vid2gif setup` / `vid2gif uninstall`.

macOS : crée des Quick Actions dans ~/Library/Services (clic droit dans le Finder,
menu Services, raccourci clavier ⌃⌥⌘G pour « GIF depuis le lien copié »).
"""

import argparse
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from vid2gif.cli import SYSTEM, Vid2GifError

SERVICES = Path.home() / "Library/Services"
LOG = "$HOME/Library/Logs/vid2gif.log"
PBS = "/System/Library/CoreServices/pbs"
CLIPBOARD_SERVICE = "GIF depuis le lien copié"
DEFAULT_SHORTCUT = "@~^g"  # ⌃⌥⌘G (@ = ⌘, ~ = ⌥, ^ = ⌃, $ = ⇧)

WORKFLOWS = [
    {
        "name": "Convertir en GIF",
        "input": "com.apple.Automator.fileSystemObject.movie",
        "send_file_types": ["public.movie"],
        "args": '--copy --notify "$@"',
    },
    {
        "name": "Lien vidéo en GIF",
        "input": "com.apple.Automator.text",
        "send_types": ["public.utf8-plain-text"],
        "args": '--copy --notify "$@"',
    },
    {
        "name": CLIPBOARD_SERVICE,
        "input": "com.apple.Automator.nothing",
        "args": "--clipboard --copy --notify",
    },
]


def launcher():
    """Commande stable pour relancer vid2gif depuis une Quick Action."""
    exe = os.environ.get("VID2GIF_EXE")  # défini par le lanceur Homebrew (chemin opt/, stable)
    if exe and Path(exe).is_file():
        return [exe]
    found = shutil.which("vid2gif")
    if found:
        return [str(Path(found).absolute())]
    return [sys.executable, "-m", "vid2gif"]


def shell_command(args):
    # `cd /` : le dossier courant ne peut pas masquer le module vid2gif.
    return 'cd / && %s %s >>"%s" 2>&1' % (" ".join(shlex.quote(p) for p in launcher()), args, LOG)


def info_plist(wf):
    service = {
        "NSMenuItem": {"default": wf["name"]},
        "NSMessage": "runWorkflowAsService",
        "NSIconName": "NSActionTemplate",
    }
    if "send_file_types" in wf:
        service["NSSendFileTypes"] = wf["send_file_types"]
        service["NSRequiredContext"] = {"NSApplicationIdentifier": "com.apple.finder"}
    if "send_types" in wf:
        service["NSSendTypes"] = wf["send_types"]
    return {"NSServices": [service]}


def document_wflow(wf, command):
    def arg(i, name, default):
        return {"default value": default, "name": name, "required": "0", "type": "0", "uuid": str(i)}

    params = ("COMMAND_STRING", "CheckedForUserDefaultShell", "inputMethod", "shell", "source")
    action = {
        "AMAccepts": {"Container": "List", "Optional": True, "Types": ["com.apple.cocoa.string"]},
        "AMActionVersion": "2.0.3",
        "AMApplication": ["Automator"],
        "AMParameterProperties": {k: {} for k in params},
        "AMProvides": {"Container": "List", "Types": ["com.apple.cocoa.string"]},
        "ActionBundlePath": "/System/Library/Automator/Run Shell Script.action",
        "ActionName": "Run Shell Script",
        "ActionParameters": {
            "COMMAND_STRING": command,
            "CheckedForUserDefaultShell": True,
            "inputMethod": 1,  # entrée passée en arguments ("$@")
            "shell": "/bin/zsh",
            "source": "",
        },
        "BundleIdentifier": "com.apple.RunShellScript",
        "CFBundleVersion": "2.0.3",
        "CanShowSelectedItemsWhenRun": False,
        "CanShowWhenRun": True,
        "Category": ["AMCategoryUtilities"],
        "Class Name": "RunShellScriptAction",
        "InputUUID": str(uuid.uuid4()).upper(),
        "Keywords": ["Shell", "Script", "Command", "Run", "Unix"],
        "OutputUUID": str(uuid.uuid4()).upper(),
        "UUID": str(uuid.uuid4()).upper(),
        "UnlocalizedApplications": ["Automator"],
        "arguments": {
            "0": arg(0, "inputMethod", 0),
            "1": arg(1, "CheckedForUserDefaultShell", False),
            "2": arg(2, "source", ""),
            "3": arg(3, "COMMAND_STRING", ""),
            "4": arg(4, "shell", "/bin/sh"),
        },
        "conversionLabel": 0,
        "isViewVisible": 1,
        "location": "309.000000:305.000000",
        "nibPath": "/System/Library/Automator/Run Shell Script.action/Contents/Resources/Base.lproj/main.nib",
    }
    return {
        "AMApplicationBuild": "534",
        "AMApplicationVersion": "2.10",
        "AMDocumentVersion": "2",
        "actions": [{"action": action, "isViewVisible": 1}],
        "connectors": {},
        "workflowMetaData": {
            "applicationBundleIDsByPath": {},
            "applicationPaths": [],
            "inputTypeIdentifier": wf["input"],
            "outputTypeIdentifier": "com.apple.Automator.nothing",
            "presentationMode": 15,
            "processesInput": False,
            "serviceInputTypeIdentifier": wf["input"],
            "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
            "serviceProcessesInput": False,
            "systemImageName": "NSActionTemplate",
            "useAutomaticInputType": False,
            "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
        },
    }


def write_workflow(wf, services_dir=SERVICES):
    bundle = Path(services_dir) / (wf["name"] + ".workflow")
    if bundle.exists():
        shutil.rmtree(bundle)
    contents = bundle / "Contents"
    contents.mkdir(parents=True)
    with open(contents / "Info.plist", "wb") as fh:
        plistlib.dump(info_plist(wf), fh)
    with open(contents / "document.wflow", "wb") as fh:
        plistlib.dump(document_wflow(wf, shell_command(wf["args"])), fh)
    return bundle


def _service_key(name):
    return "(null) - %s - runWorkflowAsService" % name


def _read_pbs():
    out = subprocess.run(["defaults", "export", "pbs", "-"], capture_output=True, check=False).stdout
    return plistlib.loads(out) if out else {}


def _write_pbs(prefs):
    subprocess.run(["defaults", "import", "pbs", "-"], input=plistlib.dumps(prefs), check=True)


def set_shortcut(name, key):
    """Ajoute un raccourci clavier au service, sans écraser un réglage existant."""
    prefs = _read_pbs()
    entry = prefs.setdefault("NSServicesStatus", {}).setdefault(_service_key(name), {})
    if entry.get("key_equivalent"):
        return False
    entry["key_equivalent"] = key
    _write_pbs(prefs)
    return True


def remove_shortcut(name):
    prefs = _read_pbs()
    if prefs.get("NSServicesStatus", {}).pop(_service_key(name), None) is not None:
        _write_pbs(prefs)


def refresh_services():
    if Path(PBS).exists():
        subprocess.run([PBS, "-flush"], check=False)
        subprocess.run([PBS, "-update"], check=False)


def _remove_legacy():
    """Nettoie l'ancienne installation par script (avant le paquet)."""
    legacy_dir = Path.home() / "Library/Application Support/vid2gif"
    legacy_bin = Path.home() / ".local/bin/vid2gif"
    if legacy_bin.is_symlink() and legacy_dir in Path(os.readlink(legacy_bin)).parents:
        legacy_bin.unlink()
    shutil.rmtree(legacy_dir, ignore_errors=True)


def _require_macos():
    if SYSTEM != "Darwin":
        raise Vid2GifError("L'intégration bureau n'existe pour l'instant que sur macOS. Utilisez la commande vid2gif.")


def setup(argv=()):
    p = argparse.ArgumentParser(prog="vid2gif setup", description="Installe les Quick Actions macOS.")
    p.add_argument("--no-shortcut", action="store_true", help="ne pas définir le raccourci ⌃⌥⌘G")
    args = p.parse_args(list(argv))
    _require_macos()

    _remove_legacy()
    SERVICES.mkdir(parents=True, exist_ok=True)
    for wf in WORKFLOWS:
        write_workflow(wf)
        print("✓ Quick Action « %s »" % wf["name"])
    if not args.no_shortcut and set_shortcut(CLIPBOARD_SERVICE, DEFAULT_SHORTCUT):
        print("✓ Raccourci ⌃⌥⌘G → « %s »" % CLIPBOARD_SERVICE)
    refresh_services()

    missing = [t for t in ("ffmpeg", "yt-dlp") if not shutil.which(t)]
    if missing:
        print("⚠️  À installer : brew install %s" % " ".join(missing))
    print(
        "\nC'est prêt :\n"
        "  • Finder : clic droit sur une vidéo → Actions rapides → Convertir en GIF\n"
        "  • Lien X copié → ⌃⌥⌘G (raccourci modifiable dans Réglages Système → Clavier → Raccourcis → Services)\n"
        "Le GIF est copié dans le presse-papiers : collez-le avec ⌘V."
    )
    return 0


def uninstall():
    _require_macos()
    for wf in WORKFLOWS:
        shutil.rmtree(SERVICES / (wf["name"] + ".workflow"), ignore_errors=True)
    remove_shortcut(CLIPBOARD_SERVICE)
    _remove_legacy()
    refresh_services()
    print("Quick Actions vid2gif supprimées.")
    return 0
