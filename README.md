# FPVRaceOne Flasher

A portable Windows GUI for flashing the FPVRaceOne (FPV Personal Lap Timer) hardware. 
It can pull any published release straight from GitHub, or
flash local `.bin` files you browse to — useful for recovering a bricked device
or as an alternative to over-the-air (OTA) updates.

No installation: the released `FPVRaceOne-Flasher.exe` (for Windows only) is a single self-contained
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

The flasher does **not** hardcode flash offsets. It pulls automatically from the 
[FPVRaceOne Releases](https://github.com/ramiss/FPVRaceOne/releases)
