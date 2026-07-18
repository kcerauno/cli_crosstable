#!/usr/bin/env python3
"""CSV (列名,行名[,値]) からクロス集計表を作成し rich で表示する CLI。

- デフォルト(2列データ): 存在=●, 不在=− のマーク表示
- --numeric 指定 + 3列データ: 3列目の値をセルごとに合計して表示
- --numeric 指定 + 2列データ: (列名,行名) の出現回数を表示
"""
import argparse
import csv
import sys
from collections import defaultdict

from rich.console import Console
from rich.table import Table

MARK_PRESENT = "●"
MARK_ABSENT = "−"


def parse_rows(fp, delimiter):
    reader = csv.reader(fp, delimiter=delimiter)
    for line in reader:
        if not line:
            continue
        if line[0].strip().startswith("#"):
            continue
        fields = [f.strip() for f in line]
        if not fields[0]:
            continue
        yield fields


def build_crosstab(rows, numeric):
    columns = []
    seen_columns = set()
    row_names = []
    seen_rows = set()
    values = defaultdict(float)
    present = defaultdict(bool)

    for fields in rows:
        col, row = fields[0], fields[1]
        if col not in seen_columns:
            seen_columns.add(col)
            columns.append(col)
        if row not in seen_rows:
            seen_rows.add(row)
            row_names.append(row)

        present[(col, row)] = True
        if numeric and len(fields) >= 3:
            values[(col, row)] += float(fields[2])
        elif numeric:
            values[(col, row)] += 1

    return columns, row_names, values, present


def format_number(value):
    if value == int(value):
        return str(int(value))
    return str(value)


def render_table(columns, row_names, values, present, numeric, title):
    table = Table(title=title, show_lines=False)
    table.add_column("")
    for col in columns:
        table.add_column(col, justify="center")

    for row in row_names:
        cells = [row]
        for col in columns:
            key = (col, row)
            if numeric:
                cells.append(format_number(values[key]) if key in values else "0")
            else:
                cells.append(MARK_PRESENT if present.get(key) else MARK_ABSENT)
        table.add_row(*cells)

    Console().print(table)


def fail(parser, message):
    print(f"エラー: {message}", file=sys.stderr)
    parser.print_help(sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="CSV からクロス集計表を作成して表示する")
    parser.add_argument("input", nargs="?", default="-", help="入力CSVファイル (省略時は標準入力)")
    parser.add_argument("-n", "--numeric", action="store_true",
                         help="数値データとして扱う (3列目を集計値として合計、2列データなら出現回数を集計)")
    parser.add_argument("-d", "--delimiter", default=",", help="区切り文字 (デフォルト: ,)")
    parser.add_argument("-t", "--title", default=None, help="表のタイトル")
    args = parser.parse_args()

    if args.input == "-":
        if sys.stdin.isatty():
            fail(parser, "入力データが指定されていません(ファイルを指定するか、標準入力にデータを渡してください)")
        rows = list(parse_rows(sys.stdin, args.delimiter))
    else:
        with open(args.input, newline="") as fp:
            rows = list(parse_rows(fp, args.delimiter))

    if not rows:
        fail(parser, "入力データがありません")

    columns, row_names, values, present = build_crosstab(rows, args.numeric)
    render_table(columns, row_names, values, present, args.numeric, args.title)


if __name__ == "__main__":
    main()
