import contextlib, io, json, re, sys, unittest, pintruth

sys.path.insert(0, "tools")
from cpp_lines import lines


def board(url="https://raw.githubusercontent.com/a/b/c/d", **pin):
    p = {"pin": "GPIO1", "function": "TX", "group": "g", "source": "s1", "quote": "q", **pin}
    return {"board": "x", "mcu": "y", "sources": {"s1": {"url": url}}, "pins": [p]}


class Data(unittest.TestCase):
    def setUp(self):
        self.files = {f: json.loads(f.read_text()) for f in pintruth.BOARDS.rglob("*.json")}

    def test_shipped_boards_are_sound(self):
        for f, b in self.files.items():
            self.assertEqual(pintruth.check(b), [], f.name)

    def test_imported_quotes_contain_their_pin_and_name(self):
        for f, b in self.files.items():
            if b["origin"] == "imported":
                for p in b["pins"]:
                    self.assertIn(p["function"], p["quote"], f.name)
                    self.assertIn(re.sub("^GPIO", "", p["pin"]), (p.get("also") or [p["quote"]])[-1], f.name)

    def test_no_commented_out_lines_imported(self):
        for f, b in self.files.items():
            for p in b["pins"]:
                self.assertFalse(p["quote"].lstrip().startswith(("//", "/*", "*")), (f.name, p["quote"]))

    def test_alias_lookup_returns_every_source(self):
        self.assertEqual(pintruth.load("cyd")["board"], "ESP32-2432S028R")
        self.assertEqual(len(pintruth.load_all("adafruit_feather_esp32s2")), 2)


class Regressions(unittest.TestCase):
    def pins(self, board, name):
        return [p for b in pintruth.load_all(board) for p in b["pins"] if p["function"] == name]

    def test_remapped_numbers_never_used_as_gpio(self):
        self.assertEqual([p["pin"] for p in self.pins("arduino_nano_nora", "SCL")], ["GPIO12"])

    def test_nonexistent_gpio_is_flagged(self):
        self.assertIn("does not exist on esp32", self.pins("alksesp32", "D0")[0]["invalid"])

    def test_shadowed_circuitpython_duplicate_is_unreachable(self):
        d11 = self.pins("unexpectedmaker_nanos3", "D11")
        self.assertEqual([p["pin"] for p in d11 if not p.get("unreachable")], ["GPIO10"])


class Errata(unittest.TestCase):
    def test_every_erratum_names_a_real_board_and_has_evidence(self):
        for e in pintruth.errata():
            self.assertTrue(pintruth.load_all(e["board"]))
            self.assertIn(e["confidence"], {"confirmed", "likely", "convention", "unresolved"})
            self.assertTrue(e["evidence"] and all(ev["url"] and ev["quote"] for ev in e["evidence"]))

    def test_show_prints_erratum_under_disagreement(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            pintruth.show(pintruth.load_all("lolin_s3_mini_pro"))
        self.assertIn("DISAGREE: MISO", out.getvalue())
        self.assertIn("ERRATUM [confirmed] MOSI/MISO", out.getvalue())


class Parser(unittest.TestCase):
    def test_comments_and_conditions(self):
        src = "#ifndef PINS_H\n// static const uint8_t A = 1;\n/* B = 2;\n */\n#if defined X\nC\n#else\nD\n#endif\nE\n#endif\n"
        got = [(code, cond) for _, code, cond in lines(src) if code]
        self.assertEqual(got, [("C", "defined X"), ("D", "not (defined X)"), ("E", None)])

    def test_quote_keeps_inline_comment(self):
        (raw, code, _), = lines("static const uint8_t A0 /*ADC*/ = 12;\n")
        self.assertEqual((raw, code), ("static const uint8_t A0 /*ADC*/ = 12;", "static const uint8_t A0  = 12;"))


class Security(unittest.TestCase):
    def test_disallowed_sources_are_not_fetched(self):
        for url in ("file:///etc/hosts", "http://127.0.0.1/", "http://169.254.169.254/", "https://evil.example/x"):
            errs = pintruth.check(board(url), online=True)
            self.assertTrue(errs and "not allowed" in errs[0], url)

    def test_unreachable_source_is_reported_not_crashed(self):
        errs = pintruth.check(board("https://raw.githubusercontent.com/nonexistent-zz/none/0/x"), online=True)
        self.assertIn("cannot check", errs[0])

    def test_terminal_escapes_are_neutralised(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            pintruth.show([board(function="TX\x1b[2J\x1b]0;pwned\x07‮")])
        self.assertNotRegex(out.getvalue(), "[\x1b\x07‮]")

    def test_malformed_board_does_not_crash(self):
        self.assertTrue(pintruth.check([]))
        self.assertTrue(pintruth.check(board(quote="")))


if __name__ == "__main__":
    unittest.main()
