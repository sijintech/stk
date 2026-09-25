# SPDX-License-Identifier: GPL-2.0-or-later
"""Self-test of desktop/app/i18n/check_i18n.py (standard library only)."""

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKER = os.environ.get("STK_I18N_CHECKER") or os.path.join(HERE, "..", "..", "app", "i18n", "check_i18n.py")

spec = importlib.util.spec_from_file_location("check_i18n", CHECKER)
check_i18n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_i18n)


class CheckerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cat = os.path.join(self.tmp.name, "i18n")
        self.src = os.path.join(self.tmp.name, "src")
        os.makedirs(self.cat)
        os.makedirs(self.src)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        with open(os.path.join(self.cat, name), "w", encoding="utf-8") as f:
            if isinstance(data, str):
                f.write(data)
            else:
                json.dump(data, f, ensure_ascii=False)

    def source(self, text):
        with open(os.path.join(self.src, "a.cc"), "w", encoding="utf-8") as f:
            f.write(text)

    def run_checker(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = check_i18n.main(["--catalogs", self.cat, "--scan", self.src, *extra])
        return rc, err.getvalue()

    def test_ok(self):
        self.write("zh_CN.json", {"_comment": "x", "ui.ok": "确定", "ui.n": "共 {n} 项"})
        self.write("en.json", {"ui.ok": "OK", "ui.n": "{n} items"})
        self.source('ctx.tr("ui.ok"); cat.format("ui.n", {{"n", "3"}}); tr("unit." + u);\n// tr("doc.example")\n')
        self.assertEqual(self.run_checker(), (0, ""))

    def test_missing_key_fails(self):
        self.write("zh_CN.json", {"ui.ok": "确定", "ui.cancel": "取消"})
        self.write("en.json", {"ui.ok": "OK"})
        rc, err = self.run_checker()
        self.assertEqual(rc, 1)
        self.assertIn("en.json: missing key 'ui.cancel'", err)

    def test_placeholder_mismatch_fails(self):
        self.write("zh_CN.json", {"ui.n": "共 {n} 项"})
        self.write("en.json", {"ui.n": "{count} items"})
        rc, err = self.run_checker()
        self.assertEqual(rc, 1)
        self.assertIn("placeholders differ for 'ui.n'", err)

    def test_empty_and_non_string_fail(self):
        self.write("zh_CN.json", {"ui.a": "", "ui.b": 3})
        self.write("en.json", {"ui.a": "A", "ui.b": "B"})
        rc, err = self.run_checker()
        self.assertEqual(rc, 1)
        self.assertIn("'ui.a' is empty", err)
        self.assertIn("'ui.b' is not a string", err)

    def test_used_key_missing_from_reference_fails(self):
        self.write("zh_CN.json", {"ui.ok": "确定"})
        self.write("en.json", {"ui.ok": "OK"})
        self.source('l.button("go", ctx.tr("ui.go"), {});\n')
        rc, err = self.run_checker()
        self.assertEqual(rc, 1)
        self.assertIn("key 'ui.go' is missing from zh_CN.json", err)
        self.assertEqual(self.run_checker("--no-scan")[0], 0)

    def test_malformed_json_fails(self):
        self.write("zh_CN.json", "{not json")
        self.write("en.json", {"ui.ok": "OK"})
        self.assertEqual(self.run_checker()[0], 1)

    def test_real_catalogs_pass(self):
        desktop = os.path.join(HERE, "..", "..")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = check_i18n.main(["--scan", desktop])
        self.assertEqual(rc, 0, err.getvalue())


if __name__ == "__main__":
    unittest.main()
