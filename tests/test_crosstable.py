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
    # stdin_text 未指定時に標準入力を親プロセス(実行元シェル)の端末へ継承させない。
    # 継承すると rich がその端末の実際の幅を検出してしまい、出力幅に依存するテストが
    # 実行環境(対話端末/非対話)によって結果が変わってしまう(=決定的でなくなる)ため。
    kwargs = {"input": stdin_text} if stdin_text is not None else {"stdin": subprocess.DEVNULL}
    return subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True,
        text=True,
        **kwargs,
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

    def test_quoted_hash_is_not_treated_as_comment(self):
        rows = list(crosstable.parse_rows(['"#foo",1'], ","))
        self.assertEqual(rows, [["#foo", "1"]])

    def test_short_row_raises_data_error_with_line_number(self):
        with self.assertRaises(crosstable.DataError) as ctx:
            list(crosstable.parse_rows(["SrvAlice,1", "SrvBob"], ","))
        self.assertIn("2行目", str(ctx.exception))


class BuildCrosstabTest(unittest.TestCase):
    def test_binary_presence(self):
        rows = [["SrvAlice", "1"], ["SrvBob", "2"]]
        columns, row_names, values, present = crosstable.build_crosstab(rows, numeric=False)
        self.assertEqual(columns, ["SrvAlice", "SrvBob"])
        self.assertEqual(row_names, ["1", "2"])
        self.assertIn(("SrvAlice", "1"), present)
        self.assertNotIn(("SrvAlice", "2"), present)

    def test_numeric_sums_duplicate_pairs(self):
        rows = [["SrvAlice", "1", "3"], ["SrvAlice", "1", "4"]]
        _, _, values, _ = crosstable.build_crosstab(rows, numeric=True)
        self.assertEqual(values[("SrvAlice", "1")], 7)

    def test_numeric_sum_has_no_floating_point_error(self):
        rows = [["SrvAlice", "1", "0.1"], ["SrvAlice", "1", "0.2"]]
        _, _, values, _ = crosstable.build_crosstab(rows, numeric=True)
        self.assertEqual(crosstable.format_number(values[("SrvAlice", "1")]), "0.3")

    def test_numeric_conversion_failure_raises_data_error(self):
        rows = [["SrvAlice", "1", "abc"]]
        with self.assertRaises(crosstable.DataError) as ctx:
            crosstable.build_crosstab(rows, numeric=True)
        self.assertIn("abc", str(ctx.exception))

    def test_columns_and_rows_are_sorted_regardless_of_input_order(self):
        rows = [["SrvCharlie", "99993911"], ["SrvBob", "1"], ["SrvAlice", "50"], ["SrvAlice", "1"]]
        columns, row_names, _, _ = crosstable.build_crosstab(rows, numeric=False)
        self.assertEqual(columns, ["SrvAlice", "SrvBob", "SrvCharlie"])
        self.assertEqual(row_names, ["1", "50", "99993911"])

    def test_rows_are_sorted_naturally_not_lexicographically(self):
        rows = [["A", "100"], ["A", "50"], ["A", "9"]]
        _, row_names, _, _ = crosstable.build_crosstab(rows, numeric=False)
        self.assertEqual(row_names, ["9", "50", "100"])  # 辞書順なら "100","50","9" になる

    def test_numeric_counts_two_column_rows(self):
        rows = [["SrvAlice", "1"], ["SrvAlice", "1"], ["SrvAlice", "2"]]
        _, _, values, _ = crosstable.build_crosstab(rows, numeric=True)
        self.assertEqual(values[("SrvAlice", "1")], 2)
        self.assertEqual(values[("SrvAlice", "2")], 1)

    def test_missing_pair_is_absent_from_values_but_recorded_zero_is_present(self):
        rows = [["SrvAlice", "1", "0"], ["SrvBob", "2", "5"]]
        _, _, values, _ = crosstable.build_crosstab(rows, numeric=True)
        self.assertIn(("SrvAlice", "1"), values)  # 実測値0は記録される
        self.assertEqual(values[("SrvAlice", "1")], 0)
        self.assertNotIn(("SrvAlice", "2"), values)  # 出現しない組み合わせはキー自体が無い


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

    def test_recorded_zero_and_missing_pair_are_shown_differently(self):
        # SrvCharlie,98783914,0 は実測0、SrvCharlie,34112876 は組み合わせ自体が存在しない
        result = run_cli(["--numeric", SAMPLE_NUMERIC])
        self.assertEqual(result.returncode, 0)
        header = next(line for line in result.stdout.splitlines() if "SrvCharlie" in line)
        col_index = header.split("┃").index(" SrvCharlie ")
        zero_row = next(line for line in result.stdout.splitlines() if "98783914" in line)
        missing_row = next(line for line in result.stdout.splitlines() if "34112876" in line)
        self.assertEqual(zero_row.split("│")[col_index].strip(), "0")
        self.assertEqual(missing_row.split("│")[col_index].strip(), crosstable.MARK_ABSENT)


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

    def test_tab_delimiter_shorthand(self):
        result = run_cli(["--delimiter", "\\t", "-"], stdin_text="SrvAlice\t1\nSrvBob\t2\n")
        self.assertEqual(result.returncode, 0)
        self.assertIn("SrvAlice", result.stdout)


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
    # --width を明示固定し、実行環境(端末幅・COLUMNS環境変数など)に依存せず
    # 常に同じ結果になるようにしている(未固定だと実行元シェルの端末幅が使われてしまう)。

    def test_without_col_width_long_names_are_truncated_with_ellipsis(self):
        result = run_cli(["--width", "80", SAMPLE_WIDTH_CHECK])
        self.assertEqual(result.returncode, 0)
        self.assertIn("…", result.stdout)

    def test_col_width_wraps_instead_of_truncating(self):
        result = run_cli(["--width", "80", "--col-width", "8", SAMPLE_WIDTH_CHECK])
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("…", result.stdout)
        self.assertIn("SrvVe", result.stdout)  # 折り返された長い列名の先頭断片が残っている
        self.assertIn("ryLon", result.stdout)

    def test_col_width_also_works_in_ascii_mode(self):
        result = run_cli(["--width", "80", "--ascii", "--col-width", "8", SAMPLE_WIDTH_CHECK])
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("…", result.stdout)
        self.assertNotIn("┏", result.stdout)

    def test_width_option_avoids_ellipsis_by_widening_console(self):
        result = run_cli(["--width", "300", SAMPLE_WIDTH_CHECK])
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("…", result.stdout)
        self.assertIn("SrvVeryLongColumnNameHannah", result.stdout)


class CliErrorHandlingTest(unittest.TestCase):
    def test_empty_stdin_is_an_error(self):
        result = run_cli([], stdin_text="")
        self.assertEqual(result.returncode, 1)
        self.assertIn("エラー", result.stderr)
        self.assertIn("usage", result.stderr)

    def test_short_row_is_a_friendly_error_not_a_traceback(self):
        result = run_cli([], stdin_text="SrvAlice,1\nSrvBob\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("エラー", result.stderr)
        self.assertIn("2行目", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_non_numeric_value_is_a_friendly_error_not_a_traceback(self):
        result = run_cli(["--numeric"], stdin_text="SrvAlice,1,abc\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("エラー", result.stderr)
        self.assertIn("abc", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_file_is_a_friendly_error_not_a_traceback(self):
        result = run_cli(["/no/such/file.csv"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("エラー", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

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
