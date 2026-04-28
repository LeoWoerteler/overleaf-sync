# Overleaf-Sync
### Easy Overleaf Two-Way Synchronization

![Made In Austria](https://img.shields.io/badge/Made%20in-Austria-%23ED2939.svg) ![PyPI - License](https://img.shields.io/pypi/l/overleaf-sync.svg) ![PyPI](https://img.shields.io/pypi/v/overleaf-sync.svg) ![PyPI - Python Version](https://img.shields.io/pypi/pyversions/overleaf-sync.svg)

This tool provides an easy way to synchronize Overleaf projects from and to your local computer. No paid account necessary. Works with both [overleaf.com](https://www.overleaf.com) and self-hosted Overleaf / ShareLaTeX Server Pro instances.

----

## Features
- Two-way sync: each file is evaluated once and the right action (upload, download, or skip) is determined automatically based on content and timestamps
- Works with free Overleaf accounts
- Works with self-hosted Overleaf / ShareLaTeX Server Pro instances via `--server`
- No Git or Dropbox required
- Does not steal or store your login credentials — login is handled by a real browser window on the official Overleaf site; only the resulting session cookie is stored locally

## Install
The package is available via [PyPI](https://pypi.org/project/overleaf-sync/):

```
pip install overleaf-sync
```

## Usage

### Login
```
ols login [--path PATH] [--server URL] [--no-verify]
```

A browser window opens on the official Overleaf website (or your private instance). Log in normally — including any CAPTCHA or SSO step. Once logged in, the session cookie is saved to `.olauth` in the current directory (use `--path` to store it elsewhere). Your credentials are never seen or stored by this tool.

For a private instance:
```
ols login --server https://overleaf.example.com
```

The server URL is remembered in `.olauth` and used automatically for subsequent `ols` invocations from the same directory.

Use `--no-verify` to disable SSL certificate verification (e.g. for self-signed certificates). This is also persisted in `.olauth`.

Keep `.olauth` safe — it grants access to your account.

### Syncing
```
ols [-l/--local-only] [-r/--remote-only] [-n/--name NAME]
    [--store-path PATH] [-p/--path PATH] [-i/--olignore PATH]
    [-v/--verbose] [-d/--dry-run] [--server URL] [--no-verify]
```

Running `ols` without subcommands syncs the current directory against the Overleaf project whose name matches the current folder name (override with `-n`).

**Sync behaviour:**

| Situation | Default (two-way) | `-r` remote-only | `-l` local-only |
|---|---|---|---|
| File only on remote | download | download | prompt |
| File only on local | upload | prompt | upload |
| Both sides differ, remote newer | download | download | skip |
| Both sides differ, local newer | upload | skip | upload |
| Both sides identical | — | — | — |

In one-way mode, files that exist only on the "other" side trigger a prompt asking whether to delete them or ignore them.

**`.olignore`:** Place an `.olignore` file in your sync folder to exclude files from local→remote sync. Uses [`fnmatch`](https://docs.python.org/3/library/fnmatch.html) pattern matching. For example, to exclude a folder named `out`, write `out/*`. Build artefacts (`.aux`, `.log`, etc.) are a common use case.

**`-d/--dry-run`:** Show what would be synced without making any changes.

Sample output:
```
✓ Project queried.
✓ Project downloaded.
✓ Project details queried.

local ↔ remote
  ↓  sections/introduction.tex
  ↑  sections/conclusion.tex
  ↑  figures/diagram.pdf
  -  scratch.tex  (deleted from remote)
  36 unchanged
```

### Listing projects
```
ols list [--store-path PATH] [--server URL] [--no-verify] [-v/--verbose]
```

Lists all active projects in your account, sorted by last-modified date:
```
✓ Projects listed.
04/28/2026, 14:23:01 - My Thesis
03/15/2026, 09:10:44 - Conference Paper
```

### Downloading the compiled PDF
```
ols download [-n/--name NAME] [--download-path PATH]
             [--store-path PATH] [--server URL] [--no-verify] [-v/--verbose]
```

Triggers a compile on Overleaf and downloads the resulting PDF to the current directory (or `--download-path`).

## Known Issues
- Changes made on Overleaf may take 1–2 minutes to appear in a downloaded zip. If a remote change is not picked up immediately, wait a moment and sync again.

## Contributing

All pull requests and change/feature requests are welcome.

## Disclaimer
THE AUTHOR OF THIS SOFTWARE AND THIS SOFTWARE IS NOT ENDORSED BY, DIRECTLY AFFILIATED WITH, MAINTAINED, AUTHORIZED, OR SPONSORED BY OVERLEAF OR WRITELATEX LIMITED. ALL PRODUCT AND COMPANY NAMES ARE THE REGISTERED TRADEMARKS OF THEIR ORIGINAL OWNERS. THE USE OF ANY TRADE NAME OR TRADEMARK IS FOR IDENTIFICATION AND REFERENCE PURPOSES ONLY AND DOES NOT IMPLY ANY ASSOCIATION WITH THE TRADEMARK HOLDER OF THEIR PRODUCT BRAND.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

THIS SOFTWARE WAS DESIGNED TO BE USED ONLY FOR RESEARCH PURPOSES. THIS SOFTWARE COMES WITH NO WARRANTIES OF ANY KIND WHATSOEVER. USE IT AT YOUR OWN RISK! IF THESE TERMS ARE NOT ACCEPTABLE, YOU AREN'T ALLOWED TO USE THE CODE.
