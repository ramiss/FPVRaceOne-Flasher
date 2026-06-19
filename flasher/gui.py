"""PySide6 GUI for the FPVRaceOne flasher.

Thin window over flasher.engine.  All network / serial work runs in a Worker
QThread so the UI stays responsive; the window only reads widget state, builds
a job closure, and renders log / progress signals.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QCheckBox, QFileDialog, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
    QProgressBar, QPushButton, QRadioButton, QStackedWidget, QVBoxLayout, QWidget,
)

from . import config, engine
from .engine import FlashError
from .resources import asset_path

CACHE_DIR = Path.home() / ".fpvraceone-flasher" / "cache"


class Worker(QThread):
    log = Signal(str)
    progress = Signal(float)        # 0..1, or -1 for "indeterminate / busy"
    done = Signal(bool, str)        # (ok, message)

    def __init__(self, job):
        super().__init__()
        self._job = job

    def run(self):
        try:
            self._job(self.log.emit, self.progress.emit)
            self.done.emit(True, "Flash complete — device(s) rebooting.")
        except FlashError as e:
            self.done.emit(False, str(e))
        except Exception as e:  # last-resort guard so the thread never dies silently
            self.done.emit(False, f"Unexpected error: {e}")


class ReleaseLoader(QThread):
    """Fetches the GitHub release list off the UI thread so the window can show
    immediately and stay responsive while GitHub is queried."""
    loaded = Signal(list)   # list[dict] of release dicts, newest first
    failed = Signal(str)

    def __init__(self, include_prereleases: bool):
        super().__init__()
        self._include_prereleases = include_prereleases

    def run(self):
        try:
            self.loaded.emit(engine.list_releases(include_prereleases=self._include_prereleases))
        except FlashError as e:
            self.failed.emit(str(e))


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{config.PRODUCT} Flasher")
        self.setMinimumWidth(720)
        icon = asset_path("icon.ico")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self._releases: list[dict] = []
        self._worker: Worker | None = None
        self._rel_loader: ReleaseLoader | None = None
        self._build_ui()
        self.refresh_ports()
        self.refresh_releases()   # populate the version dropdown on startup

    # ── UI construction ─────────────────────────────────────────────────────
    def _build_ui(self):
        outer = QHBoxLayout(self)

        # Left column: product banner image, with developer credit + Etsy link
        # stacked beneath it.
        left = QVBoxLayout()
        banner_pix = QPixmap(str(asset_path("product.png")))
        if not banner_pix.isNull():
            banner = QLabel()
            banner.setPixmap(banner_pix.scaledToHeight(400, Qt.SmoothTransformation))
            banner.setAlignment(Qt.AlignHCenter)
            left.addWidget(banner)

        credit = QLabel(f"Developed by {config.DEVELOPER}")
        credit.setAlignment(Qt.AlignHCenter)
        left.addWidget(credit)

        if config.ETSY_URL:
            etsy = QLabel(f'<a href="{config.ETSY_URL}">{config.ETSY_LINK_TEXT}</a>')
            etsy.setOpenExternalLinks(True)   # opens in the system browser
        else:
            etsy = QLabel("<i>Etsy listing — link coming soon</i>")
        etsy.setAlignment(Qt.AlignHCenter)
        left.addWidget(etsy)

        left.addStretch()
        outer.addLayout(left, 0)

        # Right: all controls.
        root = QVBoxLayout()
        outer.addLayout(root, 1)

        root.addWidget(QLabel(f"<b>{config.PRODUCT} firmware flasher</b>"))

        # Source: GitHub vs local files
        src_box = QGroupBox("Firmware source")
        src_lay = QHBoxLayout(src_box)
        self.rb_github = QRadioButton("Download from GitHub")
        self.rb_local = QRadioButton("Use local files")
        self.rb_github.setChecked(True)
        src_grp = QButtonGroup(self)
        src_grp.addButton(self.rb_github)
        src_grp.addButton(self.rb_local)
        src_lay.addWidget(self.rb_github)
        src_lay.addWidget(self.rb_local)
        src_lay.addStretch()
        root.addWidget(src_box)

        # Stacked source panels
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_github_panel())
        self.stack.addWidget(self._build_local_panel())
        root.addWidget(self.stack)
        self.rb_github.toggled.connect(lambda on: self.stack.setCurrentIndex(0 if on else 1))

        # Flash mode
        mode_box = QGroupBox("Flash mode")
        mode_lay = QVBoxLayout(mode_box)
        self.rb_update = QRadioButton("Update — firmware + filesystem (keeps bootloader)")
        self.rb_recovery = QRadioButton("Recovery — full reflash for a bricked device (merged + filesystem)")
        self.rb_update.setChecked(True)
        mode_grp = QButtonGroup(self)
        mode_grp.addButton(self.rb_update)
        mode_grp.addButton(self.rb_recovery)
        mode_lay.addWidget(self.rb_update)
        mode_lay.addWidget(self.rb_recovery)
        root.addWidget(mode_box)
        self.rb_update.toggled.connect(self._sync_local_rows)
        self.rb_recovery.toggled.connect(self._sync_local_rows)

        # Devices: only ESP32 ports are listed; check one or more to flash them all.
        port_box = QGroupBox("Devices (ESP32)")
        port_lay = QVBoxLayout(port_box)
        head = QHBoxLayout()
        head.addWidget(QLabel("Check each device to flash:"))
        head.addStretch()
        btn_ports = QPushButton("Refresh")
        btn_ports.clicked.connect(self.refresh_ports)
        head.addWidget(btn_ports)
        port_lay.addLayout(head)
        self.port_list = QListWidget()
        self.port_list.setMaximumHeight(120)
        port_lay.addWidget(self.port_list)
        root.addWidget(port_box)

        # Flash button
        self.btn_flash = QPushButton("Flash")
        self.btn_flash.setMinimumHeight(36)
        self.btn_flash.clicked.connect(self.start_flash)
        root.addWidget(self.btn_flash)

        # Progress + log
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(180)
        root.addWidget(self.log_view, 1)

        self._sync_local_rows()

    def _build_github_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Version:"))
        row = QHBoxLayout()
        self.release_combo = QComboBox()
        self.release_combo.setMinimumWidth(420)
        self.btn_refresh_rel = QPushButton("Refresh")
        self.btn_refresh_rel.clicked.connect(self.refresh_releases)
        row.addWidget(self.release_combo, 1)
        row.addWidget(self.btn_refresh_rel)
        lay.addLayout(row)
        self.cb_prerelease = QCheckBox("Include pre-releases (beta)")
        self.cb_prerelease.toggled.connect(self.refresh_releases)
        lay.addWidget(self.cb_prerelease)
        return w

    def _build_local_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.row_merged = self._file_row("Merged image (offset 0x0):")
        self.row_firmware = self._file_row("Firmware (offset 0x10000):")
        self.row_fs = self._file_row("Filesystem (offset 0x320000):")
        for r in (self.row_merged, self.row_firmware, self.row_fs):
            lay.addLayout(r["layout"])
        return w

    def _file_row(self, label: str) -> dict:
        lay = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setMinimumWidth(180)
        edit = QLineEdit()
        btn = QPushButton("Browse…")

        def browse():
            path, _ = QFileDialog.getOpenFileName(self, "Select .bin", "", "Firmware images (*.bin);;All files (*)")
            if path:
                edit.setText(path)

        btn.clicked.connect(browse)
        lay.addWidget(lbl)
        lay.addWidget(edit, 1)
        lay.addWidget(btn)
        return {"layout": lay, "label": lbl, "edit": edit, "btn": btn}

    def _sync_local_rows(self):
        """Enable only the local-file rows relevant to the chosen mode."""
        recovery = self.rb_recovery.isChecked()
        for r, active in (
            (self.row_merged, recovery),
            (self.row_firmware, not recovery),
            (self.row_fs, True),
        ):
            for k in ("label", "edit", "btn"):
                r[k].setEnabled(active)

    # ── Data refresh ──────────────────────────────────────────────────────────
    def refresh_ports(self):
        self.port_list.clear()
        # Only ESP32-like ports (matched by USB vendor id) are offered.
        ports = [p for p in engine.list_ports() if p[2]]
        if not ports:
            item = QListWidgetItem("(no ESP32 devices found — plug one in and click Refresh)")
            item.setFlags(Qt.NoItemFlags)
            self.port_list.addItem(item)
            return
        for device, desc, _likely in ports:
            item = QListWidgetItem(f"{device} — {desc}")
            item.setData(Qt.UserRole, device)
            item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setCheckState(Qt.Checked)   # default: flash every device found
            self.port_list.addItem(item)

    def selected_ports(self) -> list[str]:
        """Devices the user has checked, in list order."""
        out = []
        for i in range(self.port_list.count()):
            item = self.port_list.item(i)
            if (item.flags() & Qt.ItemIsUserCheckable) and item.checkState() == Qt.Checked:
                device = item.data(Qt.UserRole)
                if device:
                    out.append(device)
        return out

    def refresh_releases(self):
        if self._rel_loader and self._rel_loader.isRunning():
            return
        self.btn_refresh_rel.setEnabled(False)
        self.release_combo.clear()
        self.release_combo.addItem("Loading versions…", userData=-1)
        self.log("Querying GitHub for releases…")
        self._rel_loader = ReleaseLoader(self.cb_prerelease.isChecked())
        self._rel_loader.loaded.connect(self._on_releases_loaded)
        self._rel_loader.failed.connect(self._on_releases_failed)
        self._rel_loader.start()

    def _on_releases_loaded(self, releases: list):
        self._releases = releases
        self.btn_refresh_rel.setEnabled(True)
        self.release_combo.clear()
        if not releases:
            self.release_combo.addItem("(no releases found)", userData=-1)
            return
        # Releases come newest-first, so index 0 is the latest.
        for i, r in enumerate(releases):
            tag = r.get("tag_name", "?")
            label = f"{config.PRODUCT} {tag}"
            if i == 0:
                label += " (latest)"
            if r.get("prerelease"):
                label += " — beta"
            self.release_combo.addItem(label, userData=i)
        self.release_combo.setCurrentIndex(0)   # default to the latest
        self.log(f"Found {len(releases)} release(s).")

    def _on_releases_failed(self, message: str):
        self._releases = []
        self.btn_refresh_rel.setEnabled(True)
        self.release_combo.clear()
        self.release_combo.addItem("(could not load releases)", userData=-1)
        self.log(f"[ERROR] {message}")

    # ── Logging / progress slots ────────────────────────────────────────────
    def log(self, text: str):
        self.log_view.appendPlainText(text)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_progress(self, frac: float):
        if frac < 0:
            self.progress.setRange(0, 0)  # busy / indeterminate
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(int(frac * 100))

    # ── Flash orchestration ───────────────────────────────────────────────────
    def start_flash(self):
        if self._worker and self._worker.isRunning():
            return
        ports = self.selected_ports()
        if not ports:
            self.log("[ERROR] No ESP32 device selected. Plug one in, click Refresh, and check it.")
            return
        mode = "recovery" if self.rb_recovery.isChecked() else "update"

        try:
            job = self._build_github_job(ports, mode) if self.rb_github.isChecked() \
                else self._build_local_job(ports, mode)
        except FlashError as e:
            self.log(f"[ERROR] {e}")
            return

        self.log_view.clear()
        self.log(f"=== Flashing ({mode}) on {len(ports)} device(s): {', '.join(ports)} ===")
        self.btn_flash.setEnabled(False)
        self.set_progress(-1)
        self._worker = Worker(job)
        self._worker.log.connect(self.log)
        self._worker.progress.connect(self.set_progress)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_done(self, ok: bool, message: str):
        self.set_progress(1.0 if ok else 0.0)
        self.log("")
        self.log(("SUCCESS — " if ok else "FAILED — ") + message)
        self.btn_flash.setEnabled(True)

    @staticmethod
    def _flash_each(chip, baud, ports, pairs, log):
        """Flash the same images to every selected port in turn. One device
        failing doesn't abort the rest; failures are collected and reported."""
        failures = []
        for n, port in enumerate(ports, 1):
            log("")
            log(f"--- Device {n}/{len(ports)}: {port} ---")
            try:
                engine.flash(chip, baud, port, pairs, log_cb=log)
                log(f"  {port}: done.")
            except FlashError as e:
                failures.append(port)
                log(f"  [ERROR] {port}: {e}")
        if failures:
            raise FlashError(
                f"{len(failures)} of {len(ports)} device(s) failed: {', '.join(failures)}"
            )

    def _build_github_job(self, ports: list[str], mode: str):
        idx = self.release_combo.currentData()
        if idx is None or idx < 0 or idx >= len(self._releases):
            raise FlashError("No release selected. Click 'Load releases' and choose one.")
        release = self._releases[idx]
        manifest = engine.get_manifest(release)
        keys = manifest.get("flash_modes", {}).get(mode)
        if not keys:
            raise FlashError(f"This release doesn't define a '{mode}' flash mode.")
        assets = engine.assets_by_name(release)
        # Validate up front so the user gets an immediate, clear error.
        for key in keys:
            spec = manifest.get("assets", {}).get(key)
            if not spec:
                raise FlashError(f"Release lacks a '{key}' asset needed for {mode} mode.")
            if spec["name"] not in assets:
                raise FlashError(f"Release is missing asset file {spec['name']}.")
        tag = release.get("tag_name", "release")

        def job(log, progress):
            cache = CACHE_DIR / tag
            pairs = []
            for key in keys:
                spec = manifest["assets"][key]
                name, offset = spec["name"], spec["offset"]
                dest = cache / name
                if dest.exists() and dest.stat().st_size > 0:
                    log(f"Using cached {name}")
                else:
                    engine.download(assets[name], dest, progress_cb=progress, log_cb=log)
                pairs.append((offset, dest))
            progress(-1)
            self._flash_each(manifest["chip"], int(manifest["baud"]), ports, pairs, log)

        return job

    def _build_local_job(self, ports: list[str], mode: str):
        fb = config.FALLBACK_MANIFEST
        if mode == "recovery":
            rows = [(self.row_merged, fb["assets"].get("merged", {}).get("offset", "0x0")),
                    (self.row_fs, fb["assets"]["filesystem"]["offset"])]
        else:
            rows = [(self.row_firmware, fb["assets"]["firmware"]["offset"]),
                    (self.row_fs, fb["assets"]["filesystem"]["offset"])]

        pairs = []
        for row, offset in rows:
            path = row["edit"].text().strip().strip('"')
            if not path:
                raise FlashError("Please select all required files for this mode.")
            p = Path(path)
            if not p.is_file():
                raise FlashError(f"File not found: {path}")
            pairs.append((offset, p))

        chip = fb["chip"]
        baud = int(fb["baud"])

        def job(log, progress):
            progress(-1)
            self._flash_each(chip, baud, ports, pairs, log)

        return job


def main():
    app = QApplication([])
    win = MainWindow()
    win.show()
    return app.exec()
