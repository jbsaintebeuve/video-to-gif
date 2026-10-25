# Sécurité

## Signaler une vulnérabilité

Merci de ne pas ouvrir d'issue publique. Utilisez **Security → Report a vulnerability** sur GitHub (signalement privé). Une réponse est donnée sous 7 jours.

## Modèle de menace

vid2gif traite des données non fiables : des liens copiés, des vidéos téléchargées, et du texte sélectionné dans n'importe quelle application. Les protections en place :

| Risque | Protection |
|---|---|
| Injection de commande | Aucun shell n'est utilisé (`subprocess` reçoit des listes d'arguments). Les textes passés à AppleScript, JXA ou PowerShell transitent par `argv` et ne sont jamais concaténés au code. |
| Injection d'options dans yt-dlp | L'URL est placée après `--`. Seuls les liens `http(s)://` sont acceptés. |
| Vidéo piégée (playlist HLS, `concat:`…) | ffmpeg et ffprobe sont lancés avec `-protocol_whitelist file` : ils ne peuvent ouvrir aucune URL réseau. |
| Chemin de sortie (`../`, nom commençant par `-`) | Les noms de fichiers sont nettoyés par `safe_name`. Les fichiers téléchargés doivent se trouver dans le dossier temporaire de travail. |
| Abus de ressources | Téléchargement limité à 500 Mo, GIF limité aux 60 premières secondes sauf avec `-t`, taille cible fixée à 15 Mo. |
| Détournement du module Python | Le lanceur Homebrew utilise `python -P -s` et les Quick Actions font `cd /` : un dossier `vid2gif/` posé dans le répertoire courant n'est jamais chargé. |
| Chaîne d'approvisionnement | Aucune dépendance Python. Les Actions GitHub sont épinglées par SHA et mises à jour par Dependabot (après 7 jours de délai). La formule Homebrew vérifie le SHA-256 de l'archive. |

## Contrôles automatiques (`.github/workflows/security.yml`)

- **CodeQL** (`security-extended`) analyse le code Python et les workflows.
- **Bandit** fait une analyse statique Python. B404, B603 et B607 sont ignorés : ce sont les usages volontaires de `subprocess` décrits plus haut.
- **zizmor** audite la sécurité des workflows GitHub Actions.
- **Dependency Review** s'exécute sur chaque pull request.
- Ces analyses tournent aussi chaque semaine, même sans nouveau commit.
