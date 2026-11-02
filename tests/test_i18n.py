import json
import re
import unittest
from pathlib import Path

from app.i18n import msg, render

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "static" / "locales"
FRONTEND = ROOT / "frontend" / "src"
PLURAL = re.compile(r"_(zero|one|two|few|many|other)$")
CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def load(lang: str) -> dict[str, str]:
    return json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))


def base_keys(table: dict[str, str]) -> set[str]:
    return {PLURAL.sub("", key) for key in table}


def placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/|<!--.*?-->", "", text, flags=re.S)


def frontend_sources() -> list[Path]:
    return [path for path in FRONTEND.rglob("*") if path.suffix in {".vue", ".js"}]


class LocaleTests(unittest.TestCase):
    def test_locales_match_source(self):
        source = load("en")
        for path in LOCALES.glob("*.json"):
            table = load(path.stem)
            self.assertEqual(base_keys(table), base_keys(source), path.name)
            for key, text in table.items():
                if key in source:
                    self.assertEqual(placeholders(text), placeholders(source[key]), f"{path.name}: {key}")

    def test_frontend_keys_exist(self):
        keys = base_keys(load("en"))
        source = "\n".join(path.read_text(encoding="utf-8") for path in frontend_sources())
        used = set(re.findall(r"""\bt\(["']([^"']+)["']""", source))
        used |= set(re.findall(r'"((?:column|nav|page|history|settings)\.[A-Za-z.]+)"', source))
        self.assertGreater(len(used), 50)
        self.assertEqual(used - keys, set())

    def test_backend_keys_exist(self):
        source = load("en")
        for path in (ROOT / "app").glob("*.py"):
            for key in re.findall(r"""\bmsg\(\s*['"]([a-z0-9_]+)['"]""", path.read_text(encoding="utf-8")):
                self.assertIn(f"server.{key}", source, path.name)

    def test_no_hardcoded_cyrillic_in_ui(self):
        for path in frontend_sources():
            text = strip_comments(path.read_text(encoding="utf-8"))
            # Названия языков в переключателе пишутся на самих этих языках.
            text = text.replace('ru: "Русский"', "")
            self.assertIsNone(CYRILLIC.search(text), path.name)


class RenderTests(unittest.TestCase):
    def test_render_fills_params_inside_text(self):
        text = f"speedtest: {msg('speedtest_exit_code', code=3)}; raw"
        self.assertEqual(render(text), "speedtest: speedtest exited with code 3; raw")

    def test_render_keeps_unknown_markers_and_plain_text(self):
        self.assertEqual(render("[[nope]] старая запись"), "[[nope]] старая запись")
        self.assertEqual(render(""), "")


if __name__ == "__main__":
    unittest.main()
