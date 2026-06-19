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
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton,
    QRadioButton, QStackedWidget, QVBoxLayout, QWidget,
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
            self.done.emit(True, "Flash complete — device is rebooting.")
        except FlashError as e:
            self.done.emit(False, str(e))
        except Exception as e:  # last-resort guard so the thread never dies silently
            self.done.emit(False, f"Unexpected error: {e}")


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
        self._build_ui()
        self.refresh_ports()

    # ── UI construction ─────────────────────────────────────────────────────
    def _build_ui(self):
        outer = QHBoxLayout(self)

        # Left: product banner image.
        banner_pix = QPixmap(str(asset_path("product.png")))
        if not banner_pix.isNull():
            banner = QLabel()
            banner.setPixmap(banner_pix.scaledToHeight(400, Qt.SmoothTransformation))
            banner.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
            outer.addWidget(banner, 0, Qt.AlignTop)

        # Right: all controls.
        root = QVBoxLayout()
        outer.addLayout(root, 1)

        root.addWidget(QLabel(f"<b>{config.PRODUCT} firmware flasher</b>"))

        # Source: GitHub vs local files
        src_box = QGroupBox("Firmware source")
        src_lay = QHBoxLayout(src_box)
        self.rb_github = QRadioButton("Download from GitHub release")
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

        # Port
        port_box = QGroupBox("Device")
        port_lay = QHBoxLayout(port_box)
        port_lay.addWidget(QLabel("Port:"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(280)
        btn_ports = QPushButton("Refresh")
        btn_ports.clicked.connect(self.refresh_ports)
        port_lay.addWidget(self.port_combo, 1)
        port_lay.addWidget(btn_ports)
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
        top = QHBoxLayout()
        self.btn_refresh_rel = QPushButton("Load releases")
        self.btn_refresh_rel.clicked.connect(self.refresh_releases)
        self.cb_prerelease = QCheckBox("Include pre-releases (beta)")
        top.addWidget(self.btn_refresh_rel)
        top.addWidget(self.cb_prerelease)
        top.addStretch()
        lay.addLayout(top)
        self.cb_prerelease.toggled.connect(self.refresh_releases)
        self.release_combo = QComboBox()
        self.release_combo.setMinimumWidth(420)
        lay.addWidget(self.release_combo)
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
        self.port_combo.clear()
        ports = engine.list_ports()
        if not ports:
            self.port_combo.addItem("(no serial ports found)", userData=None)
            return
        for device, desc, likely in ports:
            mark = "  ●" if likely else ""
            self.port_combo.addItem(f"{device} — {desc}{mark}", userData=device)

    def refresh_releases(self):
        self.btn_refresh_rel.setEnabled(False)
        self.log("Querying GitHub for releases…")
        try:
            self._releases = engine.list_releases(include_prereleases=self.cb_prerelease.isChecked())
        except FlashError as e:
            self.log(f"[ERROR] {e}")
            self._releases = []
        finally:
            self.btn_refresh_rel.setEnabled(True)

        self.release_combo.clear()
        if not self._releases:
            self.release_combo.addItem("(no releases found)", userData=-1)
            return
        for i, r in enumerate(self._releases):
            tag = r.get("tag_name", "?")
            when = (r.get("published_at") or "")[:10]
            pre = " [pre-release]" if r.get("prerelease") else ""
            self.release_combo.addItem(f"{tag}{pre}   ({when})", userData=i)
        self.log(f"Found {len(self._releases)} release(s).")

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
        port = self.port_combo.currentData()
        if not port:
            self.log("[ERROR] No serial port selected. Plug in the device and click Refresh.")
            return
        mode = "recovery" if self.rb_recovery.isChecked() else "update"

        try:
            job = self._build_github_job(port, mode) if self.rb_github.isChecked() \
                else self._build_local_job(port, mode)
        except FlashError as e:
            self.log(f"[ERROR] {e}")
            return

        self.log_view.clear()
        self.log(f"=== Flashing ({mode}) on {port} ===")
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

    def _build_github_job(self, port: str, mode: str):
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
            engine.flash(manifest["chip"], int(manifest["baud"]), port, pairs, log_cb=log)

        return job

    def _build_local_job(self, port: str, mode: str):
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
            engine.flash(chip, baud, port, pairs, log_cb=log)

        return job


def main():
    app = QApplication([])
    win = MainWindow()
    win.show()
    return app.exec()
