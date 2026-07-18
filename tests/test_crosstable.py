import os
import pty
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "crosstable.py")
SAMPLE_BINARY = os.path.join(ROOT, "sample_data", "binary.csv")
SAMPLE_NUMERIC = os.path.join(ROOT, "sample_data", "numeric.csv")
SAMPLE_WIDTH_CHECK = os.path.join(ROOT, "sample_data", "width_check.csv")

sys.path.insert(0, ROOT)
import crosstable  # noqa: E402


def run_cli(args, stdin_text=None):
    return subprocess.run(
        [sys.executable, SCRIPT] + args,
        input=stdin_text,
        capture_output=True,
        text=True,
    )


class ParseRowsTest(unittest.TestCase):
    def test_skips_comments_and_blank_lines(self):
        lines = [
            "# 数値データ",
            "",
            "SrvAlice,34112876,3",
            "  ",
            "SrvBob,98783911,9",
        ]
        rows = list(crosstable.parse_rows(lines, ","))
        self.assertEqual(rows, [["SrvAlice", "34112876", "3"], ["SrvBob", "98783911", "9"]])

    def test_strips_whitespace(self):
        rows = list(crosstable.parse_rows([" SrvAlice , 34112876 "], ","))
        self.assertEqual(rows, [["SrvAlice", "34112876"]])


class BuildCrosstabTest(unittest.TestCase):
    def test_binary_presence(self):
        rows = [["SrvAlice", "1"], ["SrvBob", "2"]]
        columns, row_names, values, present = crosstable.build_crosstab(rows, numeric=False)
        self.assertEqual(columns, ["SrvAlice", "SrvBob"])
        self.assertEqual(row_names, ["1", "2"])
        self.assertTrue(present[("SrvAlice", "1")])
        self.assertFalse(present[("SrvAlice", "2")])

    def test_numeric_sums_duplicate_pairs(self):
        rows = [["SrvAlice", "1", "3"], ["SrvAlice", "1", "4"]]
        _, _, values, _ = crosstable.build_crosstab(rows, numeric=True)
        self.assertEqual(values[("SrvAlice", "1")], 7)

    def test_columns_and_rows_are_sorted_regardless_of_input_order(self):
        rows = [["SrvCharlie", "99993911"], ["SrvBob", "1"], ["SrvAlice", "50"], ["SrvAlice", "1"]]
        columns, row_names, _, _ = crosstable.build_crosstab(rows, numeric=False)
        self.assertEqual(columns, ["SrvAlice", "SrvBob", "SrvCharlie"])
        self.assertEqual(row_names, ["1", "50", "99993911"])

    def test_numeric_counts_two_column_rows(self):
        rows = [["SrvAlice", "1"], ["SrvAlice", "1"], ["SrvAlice", "2"]]
        _, _, values, _ = crosstable.build_crosstab(rows, numeric=True)
        self.assertEqual(values[("SrvAlice", "1")], 2)
        self.assertEqual(values[("SrvAlice", "2")], 1)


class FormatNumberTest(unittest.TestCase):
    def test_integer_valued_float_has_no_decimal(self):
        self.assertEqual(crosstable.format_number(3.0), "3")

    def test_non_integer_float_keeps_decimal(self):
        self.assertEqual(crosstable.format_number(2.5), "2.5")


class CliBinaryModeTest(unittest.TestCase):
    def test_marks_presence_and_absence(self):
        result = run_cli([SAMPLE_BINARY])
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.splitlines()
        bob_row = next(line for line in lines if "98793914" in line)
        self.assertIn(crosstable.MARK_PRESENT, bob_row)
        alice_row = next(line for line in lines if "34112876" in line)
        self.assertIn(crosstable.MARK_ABSENT, alice_row)


class CliNumericModeTest(unittest.TestCase):
    def test_three_column_values(self):
        result = run_cli(["--numeric", SAMPLE_NUMERIC])
        self.assertEqual(result.returncode, 0)
        row = next(line for line in result.stdout.splitlines() if "98783911" in line)
        self.assertIn("9", row)  # SrvBob = 9

    def test_two_column_counts(self):
        result = run_cli(["--numeric", SAMPLE_BINARY])
        self.assertEqual(result.returncode, 0)
        row = next(line for line in result.stdout.splitlines() if "98793914" in line)
        cells = [c.strip() for c in row.strip("│| \n").split("│") if c.strip()]
        self.assertIn("1", cells)


class CliAsciiModeTest(unittest.TestCase):
    def test_uses_ascii_box_and_marks(self):
        result = run_cli(["--ascii", SAMPLE_BINARY])
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("┏", result.stdout)
        self.assertNotIn("●", result.stdout)
        self.assertNotIn("−", result.stdout)
        self.assertIn("+", result.stdout)
        self.assertIn(crosstable.MARK_PRESENT_ASCII, result.stdout)
        self.assertIn(crosstable.MARK_ABSENT_ASCII, result.stdout)

    def test_default_mode_still_uses_unicode_box(self):
        result = run_cli([SAMPLE_BINARY])
        self.assertIn("┏", result.stdout)


class CliInputSourceTest(unittest.TestCase):
    def test_reads_from_stdin(self):
        with open(SAMPLE_BINARY, encoding="utf-8") as fp:
            data = fp.read()
        result = run_cli([], stdin_text=data)
        self.assertEqual(result.returncode, 0)
        self.assertIn("SrvAlice", result.stdout)

    def test_custom_delimiter(self):
        result = run_cli(["--delimiter", ";", "-"], stdin_text="SrvAlice;1\nSrvBob;2\n")
        self.assertEqual(result.returncode, 0)
        self.assertIn("SrvAlice", result.stdout)

    def test_title_is_shown(self):
        result = run_cli(["--title", "テスト表", SAMPLE_BINARY])
        self.assertIn("テスト表", result.stdout)


def table_lines(stdout):
    return [line for line in stdout.splitlines() if line.strip()]


class ColumnWidthAutoAdjustTest(unittest.TestCase):
    SHORT_CSV = "Alice,1\nAlice,2\nBob,1\nBob,2\n"
    LONG_ROW_NAME = "a-very-long-row-name-1234567890"
    LONG_COL_NAME = "ExtremelyLongColumnNameForServerXYZ"

    def _widths(self, csv_text, ascii_mode):
        args = ["--ascii"] if ascii_mode else []
        result = run_cli(args, stdin_text=csv_text)
        self.assertEqual(result.returncode, 0)
        lines = table_lines(result.stdout)
        widths = {len(line) for line in lines}
        # 罫線・ヘッダー・データ行すべての文字数が揃っている(=列幅が正しく揃えられている)ことを確認
        self.assertEqual(len(widths), 1, f"行ごとに幅が異なる: {lines}")
        return widths.pop(), result.stdout

    def _assert_widens_for_long_content(self, csv_text_with_long, ascii_mode):
        baseline_width, _ = self._widths(self.SHORT_CSV, ascii_mode)
        long_width, stdout = self._widths(csv_text_with_long, ascii_mode)
        self.assertGreater(long_width, baseline_width)
        return stdout

    def test_long_row_name_default(self):
        csv_text = f"Alice,1\nAlice,{self.LONG_ROW_NAME}\nBob,1\nBob,{self.LONG_ROW_NAME}\n"
        stdout = self._assert_widens_for_long_content(csv_text, ascii_mode=False)
        self.assertIn(self.LONG_ROW_NAME, stdout)

    def test_long_row_name_ascii(self):
        csv_text = f"Alice,1\nAlice,{self.LONG_ROW_NAME}\nBob,1\nBob,{self.LONG_ROW_NAME}\n"
        stdout = self._assert_widens_for_long_content(csv_text, ascii_mode=True)
        self.assertIn(self.LONG_ROW_NAME, stdout)

    def test_long_column_name_default(self):
        csv_text = f"Alice,1\n{self.LONG_COL_NAME},1\nAlice,2\n{self.LONG_COL_NAME},2\n"
        stdout = self._assert_widens_for_long_content(csv_text, ascii_mode=False)
        self.assertIn(self.LONG_COL_NAME, stdout)

    def test_long_column_name_ascii(self):
        csv_text = f"Alice,1\n{self.LONG_COL_NAME},1\nAlice,2\n{self.LONG_COL_NAME},2\n"
        stdout = self._assert_widens_for_long_content(csv_text, ascii_mode=True)
        self.assertIn(self.LONG_COL_NAME, stdout)


class CliColWidthOptionTest(unittest.TestCase):
    def test_without_col_width_long_names_are_truncated_with_ellipsis(self):
        result = run_cli([SAMPLE_WIDTH_CHECK])
        self.assertEqual(result.returncode, 0)
        self.assertIn("…", result.stdout)

    def test_col_width_wraps_instead_of_truncating(self):
        result = run_cli(["--col-width", "8", SAMPLE_WIDTH_CHECK])
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("…", result.stdout)
        self.assertIn("SrvVe", result.stdout)  # 折り返された長い列名の先頭断片が残っている
        self.assertIn("ryLon", result.stdout)

    def test_col_width_also_works_in_ascii_mode(self):
        result = run_cli(["--ascii", "--col-width", "8", SAMPLE_WIDTH_CHECK])
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("…", result.stdout)
        self.assertNotIn("┏", result.stdout)


class CliErrorHandlingTest(unittest.TestCase):
    def test_empty_stdin_is_an_error(self):
        result = run_cli([], stdin_text="")
        self.assertEqual(result.returncode, 1)
        self.assertIn("エラー", result.stderr)
        self.assertIn("usage", result.stderr)

    def test_no_tty_no_pipe_is_an_error(self):
        # 実端末(pty)を使って isatty() 分岐(引数なし・パイプなしで起動)を検証する
        master_fd, slave_fd = pty.openpty()
        try:
            proc = subprocess.run(
                [sys.executable, SCRIPT],
                stdin=slave_fd,
                capture_output=True,
                text=True,
                timeout=5,
            )
        finally:
            os.close(master_fd)
            os.close(slave_fd)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("エラー", proc.stderr)


if __name__ == "__main__":
    unittest.main()
