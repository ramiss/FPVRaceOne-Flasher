# FPVRaceOne Flasher

A portable Windows GUI for flashing FPVRaceOne firmware onto a Seeed XIAO
ESP32-C6 timer node. It can pull any published release straight from GitHub, or
flash local `.bin` files you browse to — useful for recovering a bricked device
or as an alternative to over-the-air (OTA) updates.

No installation: the released `FPVRaceOne-Flasher.exe` is a single self-contained
file (Python, esptool and the UI are all bundled).

## What it does

- **Download from GitHub** — lists every release (optionally including betas),
  downloads the binaries for the one you pick, and flashes them.
- **Use local files** — browse for firmware / filesystem / merged images on disk.
- **Two flash modes**
  - **Update** — firmware + filesystem (leaves the bootloader and partition
    table alone, exactly like an OTA update).
  - **Recovery** — a full reflash (merged bootloader+partitions+app image at
    `0x0`, plus the filesystem). Use this when a device is bricked.
- Auto-detects the ESP32 USB serial port (ESP32-like ports are marked ●).

## Using it (customers)

1. Plug the device into a USB port with a **data** USB-C cable (not charge-only).
2. Run `FPVRaceOne-Flasher.exe`.
3. Pick a source and a release (or browse for files), choose **Update** or
   **Recovery**, confirm the **Port**, and click **Flash**.

## How it stays compatible with the firmware

The flasher does **not** hardcode flash offsets. Each firmware release publishes
a `flash-manifest.json` describing the chip, baud rate, and which asset goes to
which offset. The flasher reads that manifest from the chosen release, so the
partition layout can change in the firmware without breaking this tool.

The required release assets (produced by the firmware repo's
`.github/workflows/release.yml`) are:

| Asset | Purpose | Offset |
|-------|---------|--------|
| `FPVRaceOne-firmware.bin`  | application image (OTA slot) | `0x10000` |
| `FPVRaceOne-littlefs.bin`  | web UI filesystem            | `0x320000` |
| `FPVRaceOne-merged.bin`    | full recovery image          | `0x0` |
| `flash-manifest.json`      | layout description           | — |

Releases published before the manifest existed fall back to the built-in
layout in [`flasher/config.py`](flasher/config.py); recovery mode is unavailable
for those (no merged image).

The source repo is configured in [`flasher/config.py`](flasher/config.py)
(`GITHUB_OWNER` / `GITHUB_REPO`).

## Developing

```sh
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

## Building the .exe

```sh
pip install -r requirements.txt pyinstaller
pyinstaller flasher.spec
# → dist/FPVRaceOne-Flasher.exe
```

CI ([`.github/workflows/build.yml`](.github/workflows/build.yml)) builds the
same exe on every push and attaches it to a GitHub Release when you push a `v*`
tag.

## Artwork

`flasher/assets/` (committed) holds the GUI banner (`product.png`) and the app
icon (`icon.png` / `icon.ico`, a stripes-only crop of the product render). To
regenerate them after updating the source render:

```sh
pip install Pillow
python tools/make_assets.py            # defaults to ../FPV_Lap_Timer/screenshots/FPVRaceOne_Product.png
python tools/make_assets.py path/to/FPVRaceOne_Product.png
```

Pillow is a build-time tool only — it is not bundled into the exe.
