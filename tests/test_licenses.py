import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPDX = "MIT AND MPL-2.0 AND OFL-1.1"
PINS = {
    "XRAY_VERSION": "Xray-core",
    "HYSTERIA_VERSION": "Hysteria",
    "SPEEDTEST_VERSION": "speedtest-go",
}
TEXTS = {
    "xray/LICENSE": "Mozilla Public License Version 2.0",
    "hysteria/LICENSE": "Copyright 2023 Toby",
    "speedtest-go/LICENSE": "Copyright (c) 2015 ITO Shogo",
    "inter/OFL.txt": "SIL OPEN FONT LICENSE Version 1.1",
}


def dockerfile_args() -> dict[str, str]:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    return dict(re.findall(r"^ARG ([A-Z0-9_]+)=(\S+)", text, re.M))


class ThirdPartyLicenseTests(unittest.TestCase):
    def test_notice_matches_pinned_versions(self):
        args = dockerfile_args()
        notice = (ROOT / "third_party" / "NOTICE").read_text(encoding="utf-8")
        for arg, name in PINS.items():
            self.assertIn(f"{name} {args[arg]}", notice)
        lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
        inter = lock["packages"]["node_modules/@fontsource-variable/inter"]["version"]
        self.assertIn(f"Inter {inter}", notice)

    def test_license_texts_are_the_upstream_notices(self):
        for rel, marker in TEXTS.items():
            text = (ROOT / "third_party" / rel).read_text(encoding="utf-8")
            self.assertIn(marker, text)
            self.assertGreater(len(text), len(marker))

    def test_image_ships_the_notices_under_one_spdx_label(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        publish = (ROOT / "publish.sh").read_text(encoding="utf-8")
        self.assertIn(f'org.opencontainers.image.licenses="{SPDX}"', dockerfile)
        self.assertIn(f"org.opencontainers.image.licenses={SPDX}", publish)
        self.assertIn("COPY third_party/ /usr/local/share/licenses/", dockerfile)
        self.assertIn("COPY LICENSE /usr/local/share/licenses/bababui/LICENSE", dockerfile)
