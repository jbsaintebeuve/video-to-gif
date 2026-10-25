# Security

## Reporting a vulnerability

Please don't open a public issue. Use **Security → Report a vulnerability** on GitHub to report privately. You'll get an answer within 7 days.

## Threat model

vid2gif handles untrusted data: copied links, downloaded videos, and text selected in any app. Protections in place:

| Risk | Protection |
|---|---|
| Command injection | No shell is used: `subprocess` gets argument lists. Text passed to AppleScript, JXA or PowerShell goes through `argv` and is never concatenated into code. |
| Option injection into yt-dlp | The URL comes after `--`. Only `http(s)://` links are accepted. |
| Booby-trapped video (HLS playlist, `concat:`…) | ffmpeg and ffprobe run with `-protocol_whitelist file`, so they cannot open any network URL. |
| Output path (`../`, names starting with `-`) | `safe_name` cleans file names. Downloaded files must stay inside the temporary work folder. |
| Resource abuse | Downloads are capped at 500 MB. GIFs keep only the first 60 seconds unless you pass `-t`. The target size is 15 MB. |
| Python module hijacking | The Homebrew launcher runs `python -P -s`, and the Quick Actions `cd /` first, so a `vid2gif/` folder in the current directory is never loaded. |
| Supply chain | No Python dependencies. GitHub Actions are pinned by SHA and updated by Dependabot after a 7-day cooldown. The Homebrew formula checks the archive's SHA-256. |

## Automated checks (`.github/workflows/security.yml`)

- **CodeQL** (`security-extended`) scans the Python code and the workflows.
- **Bandit** runs static analysis on the Python code. B404, B603 and B607 are skipped: they flag the deliberate `subprocess` use described above.
- **zizmor** audits the security of the GitHub Actions workflows.
- **Dependency Review** runs on every pull request.
- These scans also run every week, even without new commits.
