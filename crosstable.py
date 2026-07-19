#!/usr/bin/env python3
"""CSV (列名,行名[,値]) からクロス集計表を作成し rich で表示する CLI。

- デフォルト(2列データ): 存在=●, 不在=− のマーク表示
- --numeric 指定 + 3列データ: 3列目の値をセルごとに合計して表示
- --numeric 指定 + 2列データ: (列名,行名) の出現回数を表示
"""
import argparse
import csv
import re
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from rich import box
from rich.console import Console
from rich.table import Table

MARK_PRESENT = "●"
MARK_ABSENT = "−"
MARK_PRESENT_ASCII = "O"
MARK_ABSENT_ASCII = "."

_NUMBER_RE = re.compile(r"(\d+)")


class DataError(Exception):
    """入力データの内容に起因するエラー"""


def natural_sort_key(value):
    return [int(part) if part.isdigit() else part.lower() for part in _NUMBER_RE.split(value)]


def parse_rows(fp, delimiter):
    for line_num, raw_line in enumerate(fp, start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = [f.strip() for f in next(csv.reader([raw_line], delimiter=delimiter))]
        if not fields or not fields[0]:
            continue
        if len(fields) < 2:
            raise DataError(f"{line_num}行目: 列が不足しています(列名,行名の2列以上が必要です): {stripped}")
        yield fields


def build_crosstab(rows, numeric):
    seen_columns = set()
    seen_rows = set()
    values = defaultdict(Decimal)
    present = set()

    for fields in rows:
        col, row = fields[0], fields[1]
        seen_columns.add(col)
        seen_rows.add(row)
        present.add((col, row))

        if numeric:
            if len(fields) >= 3:
                try:
                    values[(col, row)] += Decimal(fields[2])
                except InvalidOperation:
                    raise DataError(f"数値に変換できません: {fields[2]!r} (列={col}, 行={row})")
            else:
                values[(col, row)] += 1

    columns = sorted(seen_columns, key=natural_sort_key)
    row_names = sorted(seen_rows, key=natural_sort_key)
    return columns, row_names, values, present


def format_number(value):
    if value == int(value):
        return str(int(value))
    return str(value)


def render_table(columns, row_names, values, present, numeric, title,
                  ascii_mode=False, col_width=None, console_width=None):
    mark_present = MARK_PRESENT_ASCII if ascii_mode else MARK_PRESENT
    mark_absent = MARK_ABSENT_ASCII if ascii_mode else MARK_ABSENT
    table_kwargs = {"box": box.ASCII} if ascii_mode else {}
    table = Table(title=title, show_lines=False, **table_kwargs)
    column_kwargs = {"max_width": col_width, "overflow": "fold"} if col_width else {}
    table.add_column("", **column_kwargs)
    for col in columns:
        table.add_column(col, justify="center", **column_kwargs)

    for row in row_names:
        cells = [row]
        for col in columns:
            key = (col, row)
            if numeric:
                cells.append(format_number(values[key]) if key in values else mark_absent)
            else:
                cells.append(mark_present if key in present else mark_absent)
        table.add_row(*cells)

    console_kwargs = {"width": console_width} if console_width else {}
    Console(**console_kwargs).print(table)


def fail(parser, message):
    print(f"エラー: {message}", file=sys.stderr)
    parser.print_help(sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="CSV からクロス集計表を作成して表示する")
    parser.add_argument("input", nargs="?", default="-", help="入力CSVファイル (省略時は標準入力)")
    parser.add_argument("-n", "--numeric", action="store_true",
                         help="数値データとして扱う (3列目を集計値として合計、2列データなら出現回数を集計)")
    parser.add_argument("-d", "--delimiter", default=",",
                         help="区切り文字 (デフォルト: , / '\\t' でタブ区切りとして扱う)")
    parser.add_argument("-t", "--title", default=None, help="表のタイトル")
    parser.add_argument("-a", "--ascii", action="store_true",
                         help="罫線・マークをASCII文字のみで出力する (ログ保存やエディタ貼り付け時の崩れ防止)")
    parser.add_argument("-w", "--col-width", type=int, default=None,
                         help="1列あたりの最大表示幅(文字数)。指定すると、超える列名/値は省略せず折り返して表示する")
    parser.add_argument("--width", type=int, default=None,
                         help="表全体の描画幅(文字数)。未指定時は端末幅(非対話環境では既定80)に自動追従する")
    args = parser.parse_args()

    delimiter = "\t" if args.delimiter == "\\t" else args.delimiter

    try:
        if args.input == "-":
            if sys.stdin.isatty():
                fail(parser, "入力データが指定されていません(ファイルを指定するか、標準入力にデータを渡してください)")
            rows = list(parse_rows(sys.stdin, delimiter))
        else:
            with open(args.input, newline="", encoding="utf-8") as fp:
                rows = list(parse_rows(fp, delimiter))

        if not rows:
            fail(parser, "入力データがありません")

        columns, row_names, values, present = build_crosstab(rows, args.numeric)
    except OSError as e:
        fail(parser, f"ファイルを開けません: {args.input} ({e.strerror})")
    except DataError as e:
        fail(parser, str(e))

    render_table(columns, row_names, values, present, args.numeric, args.title,
                 args.ascii, args.col_width, args.width)


if __name__ == "__main__":
    main()
