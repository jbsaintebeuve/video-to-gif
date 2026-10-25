<img src="assets/icon.svg" width="64" height="64" alt="">

# video-to-gif

[![CI](https://github.com/jbsaintebeuve/video-to-gif/actions/workflows/ci.yml/badge.svg)](https://github.com/jbsaintebeuve/video-to-gif/actions/workflows/ci.yml)
[![Security](https://github.com/jbsaintebeuve/video-to-gif/actions/workflows/security.yml/badge.svg)](https://github.com/jbsaintebeuve/video-to-gif/actions/workflows/security.yml)

Transforme une vidéo (un fichier local, ou un lien X / YouTube / Instagram / TikTok…) en GIF de bonne qualité, prêt à coller (⌘V) ou à enregistrer.

## Installation (macOS)

```sh
brew install jbsaintebeuve/tap/vid2gif
vid2gif setup
```

Homebrew installe aussi `ffmpeg` et `yt-dlp`. La commande `vid2gif setup` ajoute ensuite :

| Où | Action rapide | Ce qu'elle fait |
|---|---|---|
| Finder, clic droit sur une vidéo → **Actions rapides** | **Convertir en GIF** | crée le GIF à côté de la vidéo et le copie |
| N'importe quelle app, clic droit sur un lien sélectionné → **Services** | **Lien vidéo en GIF** | télécharge la vidéo et la convertit |
| Partout, avec **⌃⌥⌘G** | **GIF depuis le lien copié** | utilise le lien présent dans le presse-papiers |

**Pour un post X :** *Partager → Copier le lien*, puis ⌃⌥⌘G. Une notification indique quand le GIF est prêt (il est aussi enregistré dans `~/Downloads`). Il ne reste qu'à le coller avec ⌘V.

Le raccourci clavier peut être changé dans Réglages Système → Clavier → Raccourcis clavier → Services. `vid2gif setup` ne remplace jamais un raccourci que vous avez défini vous-même.

- Mise à jour : `brew upgrade vid2gif` (les actions rapides suivent automatiquement).
- Désinstallation : `vid2gif uninstall && brew uninstall vid2gif`.
- Journal : `~/Library/Logs/vid2gif.log`.

## Linux et Windows

```sh
pipx install git+https://github.com/jbsaintebeuve/video-to-gif
```

Il faut aussi `ffmpeg` et `yt-dlp` (`apt install ffmpeg yt-dlp`, `winget install ffmpeg yt-dlp`). Sous Linux, la copie dans le presse-papiers demande `wl-clipboard` ou `xclip`.

## Utilisation en ligne de commande

```sh
vid2gif https://x.com/weirdnotwild/status/2114199180243857583 --copy
vid2gif clip.mov -w 360 -r 12 -s 1.5 -t 4      # largeur 360px, 12 i/s, de 1,5 s à 5,5 s
vid2gif --clipboard --copy                     # lien copié → GIF copié
```

| Option | Défaut | Rôle |
|---|---|---|
| `-w, --width` | 480 | largeur maximale (la vidéo n'est jamais agrandie) |
| `-r, --fps` | 15 | images par seconde |
| `-s, --start` / `-t, --duration` | toute la vidéo, 60 s max | découpe un extrait |
| `--max-mb` | 15 | réduit automatiquement le GIF pour rester sous ce poids (`0` = pas de limite) |
| `-c, --copy` | — | copie le GIF dans le presse-papiers |
| `-o, --outdir` | à côté du fichier / `~/Downloads` | dossier de sortie |
| `--cookies-from-browser` | — | `chrome`, `safari`, `firefox`… pour les vidéos qui demandent d'être connecté |

## Développement

```sh
python3 -m venv .venv && .venv/bin/pip install pytest ruff
.venv/bin/pytest            # tests (ffmpeg requis pour les tests d'intégration)
.venv/bin/ruff check . && .venv/bin/ruff format --check .
python3 -m vid2gif --help   # lancer depuis les sources
```

La CI (`.github/workflows/ci.yml`) lance le lint et les tests sur macOS, Linux et Windows. Elle installe aussi la formule Homebrew à partir des sources du commit, puis vérifie `brew test`, `brew audit` et `vid2gif setup`. Les contrôles de sécurité sont décrits dans [SECURITY.md](SECURITY.md).

### Publier une version

1. Changer `__version__` dans `vid2gif/__init__.py`, puis commit sur `main`.
2. `git tag v0.2.0 && git push origin v0.2.0`

Le workflow `release.yml` relance la CI, crée la release GitHub et met à jour la formule dans [jbsaintebeuve/homebrew-tap](https://github.com/jbsaintebeuve/homebrew-tap). Il a besoin du secret `HOMEBREW_TAP_TOKEN` : un token *fine-grained* avec les droits Contents en lecture/écriture, limité au dépôt `homebrew-tap`.

## Fonctionnement

`yt-dlp` télécharge la vidéo, puis `ffmpeg` génère une palette optimisée et la convertit en GIF en boucle. Si le GIF dépasse `--max-mb`, l'outil recommence en réduisant la largeur, puis le nombre d'images par seconde et de couleurs.
