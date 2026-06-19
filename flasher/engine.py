"""Flash engine — GUI-agnostic.

Ported from the firmware repo's scripts/flash_published_release.py, generalised
to (a) list *all* releases for a picker, (b) read the per-release
flash-manifest.json instead of hardcoding offsets, and (c) drive esptool
in-process (so it works inside a PyInstaller one-file bundle, where there is no
`python -m esptool` subprocess to call).

Nothing here imports PySide6 — the GUI layer wraps these functions in a worker
thread and passes callbacks for logging / progress.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import config

GITHUB_API = "https://api.github.com"
_UA = "FPVRaceOne-Flasher"
MANIFEST_ASSET = "flash-manifest.json"


class FlashError(Exception):
    """Any user-facing failure (network, missing asset, esptool error)."""


# ── GitHub release discovery ────────────────────────────────────────────────

def _api_get(url: str):
    req = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": _UA})
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        if e.code == 404:
            raise FlashError(f"Not found on GitHub: {url}")
        if e.code == 403:
            raise FlashError("GitHub API rate limit reached. Try again in a few minutes.")
        raise FlashError(f"GitHub returned HTTP {e.code}.")
    except URLError as e:
        raise FlashError(f"Could not reach GitHub: {e.reason}. Check your internet connection.")


def list_releases(include_prereleases: bool = True, limit: int = 30) -> list[dict]:
    """Return published releases, newest first, as the raw GitHub release dicts."""
    url = f"{GITHUB_API}/repos/{config.GITHUB_OWNER}/{config.GITHUB_REPO}/releases?per_page={limit}"
    releases = _api_get(url)
    out = []
    for r in releases:
        if r.get("draft"):
            continue
        if r.get("prerelease") and not include_prereleases:
            continue
        out.append(r)
    return out


def assets_by_name(release: dict) -> dict[str, str]:
    """Map asset filename -> browser_download_url for a release."""
    return {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}


def get_manifest(release: dict) -> dict:
    """Fetch and validate a release's flash-manifest.json, or fall back to the
    built-in layout for older releases that predate it."""
    assets = assets_by_name(release)
    url = assets.get(MANIFEST_ASSET)
    if not url:
        manifest = dict(config.FALLBACK_MANIFEST)
        manifest["_source"] = "fallback"
        return manifest

    req = Request(url, headers={"User-Agent": _UA})
    try:
        with urlopen(req, timeout=30) as resp:
            manifest = json.loads(resp.read())
    except (HTTPError, URLError, json.JSONDecodeError) as e:
        raise FlashError(f"Could not read {MANIFEST_ASSET}: {e}")

    schema = manifest.get("schema", 0)
    if schema > config.SUPPORTED_SCHEMA:
        raise FlashError(
            f"This release needs a newer flasher (manifest schema {schema}, "
            f"this build supports {config.SUPPORTED_SCHEMA}). Please update the tool."
        )
    manifest["_source"] = "release"
    return manifest


# ── Download ────────────────────────────────────────────────────────────────

def download(url: str, dest: Path, progress_cb=None, log_cb=None) -> Path:
    """Download `url` to `dest`. progress_cb(fraction 0..1) and log_cb(str) optional."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if log_cb:
        log_cb(f"Downloading {dest.name} ...")
    req = Request(url, headers={"User-Agent": _UA})
    try:
        with urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            read = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    read += len(chunk)
                    if total and progress_cb:
                        progress_cb(read / total)
    except (HTTPError, URLError) as e:
        raise FlashError(f"Download failed for {dest.name}: {e}")
    if log_cb:
        log_cb(f"  saved {read:,} bytes")
    return dest


# ── Serial port detection ─────────────────────────────────────────────────────

def list_ports() -> list[tuple[str, str, bool]]:
    """Return [(device, description, is_likely_esp32), ...]."""
    try:
        import serial.tools.list_ports
    except ImportError:
        return []
    out = []
    for p in serial.tools.list_ports.comports():
        likely = p.vid in config.ESP32_VIDS
        out.append((p.device, p.description or "", likely))
    # ESP32-looking ports first.
    out.sort(key=lambda t: (not t[2], t[0]))
    return out


# ── Flashing (in-process esptool) ──────────────────────────────────────────────

class _Tee(io.TextIOBase):
    """Forwards everything esptool prints to a line-oriented callback, handling
    the in-place '\\r' progress updates esptool emits during write_flash."""

    def __init__(self, log_cb):
        self._log_cb = log_cb
        self._buf = ""

    def write(self, s):
        if not s:
            return 0
        self._buf += s
        # esptool uses both \n (lines) and \r (progress redraws); split on both.
        while True:
            idx = min((i for i in (self._buf.find("\n"), self._buf.find("\r")) if i >= 0), default=-1)
            if idx < 0:
                break
            line, self._buf = self._buf[:idx], self._buf[idx + 1:]
            if line.strip():
                self._log_cb(line)
        return len(s)

    def flush(self):
        if self._buf.strip():
            self._log_cb(self._buf)
            self._buf = ""


def flash(chip: str, baud: int, port: str, pairs: list[tuple[str, str]], log_cb=None):
    """Flash (offset, file) pairs to `port` using esptool in-process.

    pairs: list of (offset_hex_str, absolute_file_path).
    Raises FlashError on any failure.
    """
    try:
        import esptool
    except ImportError:
        raise FlashError("esptool is not bundled with this build (developer error).")

    argv = [
        "--chip", chip,
        "--port", port,
        "--baud", str(baud),
        "--before", "default_reset",
        "--after", "hard_reset",
        "write_flash", "-z",
        "--flash_mode", "dio",
        "--flash_freq", "80m",
        "--flash_size", "detect",
    ]
    for offset, path in pairs:
        argv += [offset, str(path)]

    sink = _Tee(log_cb or (lambda _l: None))
    if log_cb:
        log_cb(f"$ esptool {' '.join(argv)}")
    try:
        with redirect_stdout(sink), redirect_stderr(sink):
            esptool.main(argv)
    except SystemExit as e:  # esptool calls sys.exit() on argument/usage errors
        sink.flush()
        if e.code not in (0, None):
            raise FlashError(f"esptool exited with code {e.code}.")
    except Exception as e:  # serial errors, sync failures, etc.
        sink.flush()
        raise FlashError(f"Flashing failed: {e}")
    finally:
        sink.flush()
