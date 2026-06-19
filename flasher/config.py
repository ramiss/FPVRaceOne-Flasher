"""Static configuration for the FPVRaceOne flasher.

This is a *separate* repo from the firmware, so it can't read the firmware's
git remote at runtime — the source repo is hardcoded here.  Everything about
the *flash layout* (chip, baud, offsets) is read from each release's
`flash-manifest.json` instead, so this file rarely needs to change.
"""

# GitHub repo that publishes the firmware releases.
GITHUB_OWNER = "ramiss"
GITHUB_REPO = "FPVRaceOne"

PRODUCT = "FPVRaceOne"

# Shown under the product banner in the GUI.
DEVELOPER = "Richard Amiss"

# Etsy shop / product link shown under the banner. Leave "" until the listing
# URL is known — the GUI shows a "coming soon" placeholder while it's empty, and
# renders a clickable link once it's filled in.
ETSY_URL = ""            # e.g. "https://www.etsy.com/listing/1234567890/fpvraceone"
ETSY_LINK_TEXT = "Buy on Etsy"

# USB vendor IDs that indicate an attached ESP32 (mirrors the firmware repo's
# scripts/extra_script.py).  Used to pre-select the right COM port.
ESP32_VIDS = {
    0x10C4,  # Silicon Labs CP210x
    0x1A86,  # QinHeng CH340/CH341
    0x0403,  # FTDI
    0x303A,  # Espressif native USB
    0x239A,  # Adafruit
    0x2341,  # Arduino
}

# Fallback layout for releases published *before* flash-manifest.json existed.
# Matches partitions_two_ota_XIAO_ESP32_C6.csv at the time of writing.
FALLBACK_MANIFEST = {
    "schema": 1,
    "product": PRODUCT,
    "chip": "esp32c6",
    "baud": 460800,
    "assets": {
        "firmware": {"name": "FPVRaceOne-firmware.bin", "offset": "0x10000"},
        "filesystem": {"name": "FPVRaceOne-littlefs.bin", "offset": "0x320000"},
        # merged.bin didn't exist in older releases; recovery mode is unavailable
        # for those (the GUI hides it when the asset is absent).
    },
    "flash_modes": {
        "update": ["firmware", "filesystem"],
        "recovery": ["merged", "filesystem"],
    },
}

# Highest manifest schema this build understands.
SUPPORTED_SCHEMA = 1
