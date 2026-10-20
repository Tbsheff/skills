import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401

sys.path.insert(0, os.path.join(helpers.MEDIA, "backend"))
import render  # noqa: E402

GREEN = {"exit_code": 0, "stdout": "", "stderr": "Ran 3 tests in 0.01s\n\nOK\n"}


def run(code, text="", timed_out=False):
    return {"exit_code": code, "stdout": "", "stderr": text, "timed_out": timed_out}


class BackendVerdictTest(unittest.TestCase):
    def verdict(self, base, change=GREEN):
        return render.tests_verdict({"base": base, "change": change})

    def test_unittest_assertion_failure_is_red(self):
        self.assertIs(self.verdict(run(1, "Ran 3 tests in 0.01s\n\nFAILED (failures=2)\n"))[0], True)

    def test_unittest_import_error_did_not_run(self):
        passed, why = self.verdict(run(1, "ImportError: cannot import name 'x'\nRan 1 test in 0.0s\n\nFAILED (errors=1)\n"))
        self.assertIsNone(passed)
        self.assertIn("did not run on base", why)

    def test_exit_codes_that_did_not_run(self):
        for code in (124, 126, 127, 137):
            self.assertIsNone(self.verdict(run(code, "boom"))[0], code)
        self.assertIsNone(self.verdict(run(1, "x", timed_out=True))[0])

    def test_pytest(self):
        self.assertIs(self.verdict(run(1, "===== 1 failed, 4 passed in 0.12s =====\n"))[0], True)
        self.assertIsNone(self.verdict(run(2, "===== 1 error in 0.10s =====\n"))[0])
        self.assertIsNone(self.verdict(run(5, "===== no tests ran in 0.01s =====\n"))[0])

    def test_vitest_and_jest(self):
        self.assertIs(self.verdict(run(1, " Test Files  1 failed (1)\n      Tests  2 failed | 3 passed (5)\n"))[0], True)
        self.assertIsNone(self.verdict(run(1, " Test Files  1 failed (1)\n Error: Cannot find module './new'\n"))[0])
        self.assertIsNone(self.verdict(run(1, "No test files found, exiting with code 1\n"))[0])
        self.assertIs(self.verdict(run(1, "Tests:       1 failed, 2 passed, 3 total\n"))[0], True)
        self.assertIsNone(self.verdict(run(1, "Test Suites: 1 failed\nTests:       0 total\n"))[0])

    def test_green_on_both_and_red_on_change(self):
        self.assertIsNone(self.verdict(GREEN)[0])
        self.assertIs(self.verdict(run(1, "Ran 1 test\nFAILED (failures=1)"), run(1, "FAILED"))[0], False)

    def test_title_names_did_not_run(self):
        self.assertEqual(render.tests_title({"base": run(127, "x"), "change": GREEN}),
                         "Tests: did not run on base, green on change")


if __name__ == "__main__":
    unittest.main()
