# crosstable.py テスト仕様書

対象ファイル: [`tests/test_crosstable.py`](../tests/test_crosstable.py)

本書は `tests/test_crosstable.py` に実装されている自動テストの内容を、
「何を」「どういう入力で」「何が正しければ合格とするか」という観点で整理したものです。
プログラム自体の仕様は [doc/SPEC.md](SPEC.md) を、使い方は [README.md](../README.md) を参照してください。

実行方法:

```bash
python -m unittest discover -s tests -v
```

2026-07-19 時点で **37件** のテストがあり、すべて合格しています。

---

## 1. テストの2つの層

このテストは、検証する範囲が異なる2つの層(レイヤー)で構成されています。

| 層 | 何を検証するか | 呼び出し方 | 該当するクラス |
|---|---|---|---|
| ① ユニットテスト | `crosstable.py` 内の個々の関数(部品)が、単体で正しく動くか | `crosstable` モジュールを直接 `import` し、関数を呼び出す | `ParseRowsTest`, `BuildCrosstabTest`, `FormatNumberTest` |
| ② CLI結合テスト | ユーザーが実際にコマンドを打ったときと同じ形で、プログラム全体(入力→集計→表示、またはエラー表示)が正しく動くか | `python crosstable.py ...` を子プロセスとして起動し、画面出力・エラー出力・終了コードを確認する | それ以外の全クラス(`Cli` から始まるクラス、`ColumnWidthAutoAdjustTest`) |

①は「部品(歯車)が1つずつ正しく回るか」、②は「実際に組み立てた機械(コマンド)が正しく動くか」を確認するもの、とイメージすると分かりやすいです。①だけでは気づけない不具合(例: コマンドライン引数の受け渡し忘れ)を②が補っています。

### 共通の補助部品(ヘルパー関数)

| 名前 | 役割 |
|---|---|
| `run_cli(args, stdin_text=None)` | `crosstable.py` を実際にコマンドとして起動し、引数(`args`)と標準入力(`stdin_text`)を渡した結果(標準出力・標準エラー・終了コード)を返す。CLI結合テストの土台。`stdin_text` を渡さない場合、標準入力は実行元シェルの端末へ継承させず明示的に閉じる(`/dev/null` 相当)。継承させてしまうと、rich が実行元の端末幅を検出してしまい、テストの結果が「対話端末から実行したか」によって変わってしまう(=不安定になる)ため |
| `table_lines(stdout)` | 画面出力から空行を取り除き、表を構成する行だけを取り出す |

---

## 2. テストクラス一覧(サマリー)

| # | クラス名 | 検証対象 | 層 | ケース数 |
|---|---|---|---|---|
| 1 | `ParseRowsTest` | `parse_rows`(CSVの1行を読み解く処理) | ① | 4 |
| 2 | `BuildCrosstabTest` | `build_crosstab`(集計処理) | ① | 8 |
| 3 | `FormatNumberTest` | `format_number`(数値の表示整形) | ① | 2 |
| 4 | `CliBinaryModeTest` | 二値モードの表示(`●`/`−`) | ② | 1 |
| 5 | `CliNumericModeTest` | 数値モードの集計・表示 | ② | 3 |
| 6 | `CliAsciiModeTest` | `--ascii` オプション | ② | 2 |
| 7 | `CliInputSourceTest` | 入力元(標準入力・区切り文字・タイトル) | ② | 4 |
| 8 | `ColumnWidthAutoAdjustTest` | 列幅の自動拡大 | ② | 4 |
| 9 | `CliColWidthOptionTest` | `--col-width` / `--width` オプション | ② | 4 |
| 10 | `CliErrorHandlingTest` | 異常系(エラー処理) | ② | 5 |
| | **合計** | | | **37** |

### 使用しているサンプルデータ

| ファイル | 主な用途 | 主に使うテストクラス |
|---|---|---|
| `sample_data/binary.csv` | 二値データの基本ケース | `CliBinaryModeTest`, `CliNumericModeTest`, `CliAsciiModeTest`, `CliInputSourceTest` |
| `sample_data/numeric.csv` | 数値データ(実測0を含む)の基本ケース | `CliNumericModeTest` |
| `sample_data/width_check.csv` | 列数が多く長い列名/行名を含むケース | `CliColWidthOptionTest` |

---

## 3. 詳細テストケース一覧

### 3.1 `ParseRowsTest` — CSVの1行を読み解く処理の検証

| # | テスト名 | 目的 | 入力 | 期待結果 |
|---|---|---|---|---|
| 1 | `test_skips_comments_and_blank_lines` | コメント行(`#`)・空行が正しく無視されること | `# 数値データ` / 空行 / `SrvAlice,34112876,3` / 空白のみの行 / `SrvBob,98783911,9` | コメント・空行を除いた2件の行のみが取り出される |
| 2 | `test_strips_whitespace` | 各項目の前後の余分な空白が取り除かれること | `" SrvAlice , 34112876 "` | `["SrvAlice", "34112876"]`(空白なし) |
| 3 | `test_quoted_hash_is_not_treated_as_comment` | `"#foo"` のように値の中に `#` を含む場合、誤ってコメント扱いされないこと | `'"#foo",1'` | `[["#foo", "1"]]` として正しく読み取られる |
| 4 | `test_short_row_raises_data_error_with_line_number` | 列が1つしかない行があった場合、行番号付きのエラーになること | `["SrvAlice,1", "SrvBob"]`(2行目が列不足) | `DataError` が発生し、メッセージに `"2行目"` を含む |

### 3.2 `BuildCrosstabTest` — 集計処理の検証

| # | テスト名 | 目的 | 入力 | 期待結果 |
|---|---|---|---|---|
| 1 | `test_binary_presence` | 二値モードで、出現した組み合わせだけが「存在」として記録されること | `SrvAlice-1`, `SrvBob-2` | `columns=["SrvAlice","SrvBob"]`, `row_names=["1","2"]`。`(SrvAlice,1)` は存在、`(SrvAlice,2)` は不在 |
| 2 | `test_numeric_sums_duplicate_pairs` | 数値モードで、同じ組み合わせの値が合算されること | `SrvAlice-1` に `3` と `4` | 合計 `7` |
| 3 | `test_numeric_sum_has_no_floating_point_error` | 小数の合算に誤差が出ないこと(`Decimal` 化の検証) | `SrvAlice-1` に `0.1` と `0.2` | 表示すると `"0.3"`(`0.30000000000000004` にならない) |
| 4 | `test_numeric_conversion_failure_raises_data_error` | 3列目が数値に変換できない場合、エラーになること | `SrvAlice,1,abc` | `DataError` が発生し、メッセージに `"abc"` を含む |
| 5 | `test_columns_and_rows_are_sorted_regardless_of_input_order` | 入力順に関係なく、列名・行名がソートされること | `SrvCharlie, SrvBob, SrvAlice, SrvAlice` の順で入力 | `columns=["SrvAlice","SrvBob","SrvCharlie"]` の順に並び替わる |
| 6 | `test_rows_are_sorted_naturally_not_lexicographically` | 行名の並びが「辞書順」ではなく「自然順(数値として比較)」であること | 行名 `100, 50, 9` を入力 | `["9","50","100"]` の順(辞書順なら `["100","50","9"]` になってしまう) |
| 7 | `test_numeric_counts_two_column_rows` | 数値モード・2列データで、出現回数が数えられること | `SrvAlice-1` が2回、`SrvAlice-2` が1回出現 | `(SrvAlice,1)=2`, `(SrvAlice,2)=1` |
| 8 | `test_missing_pair_is_absent_from_values_but_recorded_zero_is_present` | 「実測値が0」と「データが存在しない」が区別できること | `SrvAlice,1,0`(実測0)と `SrvBob,2,5` のみ入力(`SrvAlice,2` は未入力) | `(SrvAlice,1)` は値`0`として記録される/`(SrvAlice,2)` はキー自体が存在しない |

### 3.3 `FormatNumberTest` — 数値の表示整形の検証

| # | テスト名 | 目的 | 入力 | 期待結果 |
|---|---|---|---|---|
| 1 | `test_integer_valued_float_has_no_decimal` | 整数値は小数点なしで表示されること | `3.0` | `"3"` |
| 2 | `test_non_integer_float_keeps_decimal` | 整数でない値はそのまま表示されること | `2.5` | `"2.5"` |

### 3.4 `CliBinaryModeTest` — 二値モードのCLI出力検証

| # | テスト名 | 目的 | 入力 | 期待結果 |
|---|---|---|---|---|
| 1 | `test_marks_presence_and_absence` | 実際のコマンド実行結果で `●`/`−` が正しいセルに表示されること | `sample_data/binary.csv` | 出現する組み合わせの行に `●`、出現しない組み合わせの行に `−` を含む |

### 3.5 `CliNumericModeTest` — 数値モードのCLI出力検証

| # | テスト名 | 目的 | 入力 | 期待結果 |
|---|---|---|---|---|
| 1 | `test_three_column_values` | 3列データの集計値が正しく表示されること | `--numeric sample_data/numeric.csv` | `SrvBob` の行に集計値 `9` を含む |
| 2 | `test_two_column_counts` | 2列データ+`--numeric` で出現回数が表示されること | `--numeric sample_data/binary.csv` | 出現回数 `1` がセルに表示される |
| 3 | `test_recorded_zero_and_missing_pair_are_shown_differently` | 実測0のセルと未出現のセルが画面上で異なる表示になること | `--numeric sample_data/numeric.csv`(`SrvCharlie,98783914,0` は実測0、`SrvCharlie,34112876` は未出現) | 実測0のセルは `"0"`、未出現のセルは `−` |

### 3.6 `CliAsciiModeTest` — `--ascii` オプションの検証

| # | テスト名 | 目的 | 入力 | 期待結果 |
|---|---|---|---|---|
| 1 | `test_uses_ascii_box_and_marks` | `--ascii` 指定時、罫線・マークがASCII文字のみになること | `--ascii sample_data/binary.csv` | `┏`・`●`・`−` を含まない/`+`・`O`・`.` を含む |
| 2 | `test_default_mode_still_uses_unicode_box` | `--ascii` 未指定時は従来通りUnicode罫線のままであること(回帰確認) | `sample_data/binary.csv`(オプションなし) | `┏` を含む |

### 3.7 `CliInputSourceTest` — 入力元・オプションの検証

| # | テスト名 | 目的 | 入力 | 期待結果 |
|---|---|---|---|---|
| 1 | `test_reads_from_stdin` | ファイル指定なしで標準入力からデータを読めること | `binary.csv` の内容を標準入力から渡す | 正常終了し、`SrvAlice` を含む出力 |
| 2 | `test_custom_delimiter` | `--delimiter` で任意の区切り文字を指定できること | `--delimiter ;`、入力 `SrvAlice;1` 等 | 正常終了し、`SrvAlice` を含む出力 |
| 3 | `test_title_is_shown` | `--title` で指定したタイトルが表示されること | `--title テスト表` | 出力に `テスト表` を含む |
| 4 | `test_tab_delimiter_shorthand` | `--delimiter '\t'` の指定でタブ区切りとして読めること | `--delimiter \t`、タブ区切りの入力 | 正常終了し、`SrvAlice` を含む出力 |

### 3.8 `ColumnWidthAutoAdjustTest` — 列幅の自動拡大の検証

長い列名・行名があるとき、表の列幅が自動的に広がり、かつ罫線の縦の位置がずれない(全行の文字数が揃う)ことを検証します。`--ascii`・通常モードの両方で確認します。

| # | テスト名 | 目的 | 入力 | 期待結果 |
|---|---|---|---|---|
| 1 | `test_long_row_name_default` | 行名が長い場合、通常モードで表の幅が広がること | 32文字の長い行名を含むデータ | 短い行名だけの表より横幅が広くなり、行名が省略されずに含まれる |
| 2 | `test_long_row_name_ascii` | 同上(`--ascii` 版) | 同上 + `--ascii` | 同上 |
| 3 | `test_long_column_name_default` | 列名が長い場合、通常モードで表の幅が広がること | 36文字の長い列名を含むデータ | 短い列名だけの表より横幅が広くなり、列名が省略されずに含まれる |
| 4 | `test_long_column_name_ascii` | 同上(`--ascii` 版) | 同上 + `--ascii` | 同上 |

> 全4ケース共通で、出力の全行(罫線・ヘッダー・データ行)の文字数が一致していること(=列幅の計算がずれていないこと)も併せて確認しています(`_widths` 内部で検証)。

### 3.9 `CliColWidthOptionTest` — `--col-width` / `--width` オプションの検証

| # | テスト名 | 目的 | 入力 | 期待結果 |
|---|---|---|---|---|
| 1 | `test_without_col_width_long_names_are_truncated_with_ellipsis` | オプション未指定時は、従来通り長い列名が `…` で省略されること(回帰確認) | `--width 80 sample_data/width_check.csv`(`--col-width` なし) | 出力に `…` を含む |
| 2 | `test_col_width_wraps_instead_of_truncating` | `--col-width` 指定時、省略せず折り返して表示されること | `--width 80 --col-width 8 sample_data/width_check.csv` | `…` を含まない/折り返された長い列名の断片(`SrvVe`, `ryLon`)を含む |
| 3 | `test_col_width_also_works_in_ascii_mode` | `--col-width` が `--ascii` と併用できること | `--width 80 --ascii --col-width 8 sample_data/width_check.csv` | `…` を含まない/Unicode罫線(`┏`)を含まない |

> **注**: 1〜3は `--width` を明示的に固定しています。固定しない場合、`run_cli` が標準入力を明示的に閉じていないと実行元シェルの端末幅が rich に伝わってしまい、実行環境によって結果が変わる(テストが不安定になる)ため、表全体の幅を固定して環境非依存にしています。
| 4 | `test_width_option_avoids_ellipsis_by_widening_console` | `--width` で表全体の幅を広げ、省略を防げること | `--width 300 sample_data/width_check.csv` | `…` を含まない/長い列名 `SrvVeryLongColumnNameHannah` がそのまま含まれる |

### 3.10 `CliErrorHandlingTest` — 異常系(エラー処理)の検証

| # | テスト名 | 目的 | 入力 | 期待結果 |
|---|---|---|---|---|
| 1 | `test_empty_stdin_is_an_error` | 標準入力が空の場合にエラーとして扱われること | 標準入力に何も渡さない(空文字) | 終了コード `1`、標準エラーに `エラー` と `usage` を含む |
| 2 | `test_short_row_is_a_friendly_error_not_a_traceback` | 列不足の行があっても、Pythonの生エラー(トレースバック)ではなく短いメッセージになること | `SrvAlice,1` の後に `SrvBob`(列不足)を入力 | 終了コード `1`、`エラー`・`2行目` を含み `Traceback` を含まない |
| 3 | `test_non_numeric_value_is_a_friendly_error_not_a_traceback` | 数値モードで3列目が数値でない場合も、同様に短いメッセージになること | `--numeric`、入力 `SrvAlice,1,abc` | 終了コード `1`、`エラー`・`abc` を含み `Traceback` を含まない |
| 4 | `test_missing_file_is_a_friendly_error_not_a_traceback` | 存在しないファイルを指定した場合も、同様に短いメッセージになること | 入力ファイルに `/no/such/file.csv` を指定 | 終了コード `1`、`エラー` を含み `Traceback` を含まない |
| 5 | `test_no_tty_no_pipe_is_an_error` | 端末上で引数なし・パイプなしで実行した場合にエラーとして扱われること(疑似端末を使って検証) | 疑似端末(pty)経由で引数なし実行 | 終了コード `1`、標準エラーに `エラー` を含む |

---

## 4. 仕様との対応(トレーサビリティ)

主要な仕様が、どのテストケースで担保されているかの対応表です。

| 仕様 | 担保するテストケース |
|---|---|
| 二値データの存在/不在表示 | `CliBinaryModeTest#1`, `BuildCrosstabTest#1` |
| 数値データの合計集計 | `CliNumericModeTest#1`, `BuildCrosstabTest#2` |
| 二値データ+`--numeric` の出現回数集計 | `CliNumericModeTest#2`, `BuildCrosstabTest#7` |
| 実測0とデータなしの区別 | `CliNumericModeTest#3`, `BuildCrosstabTest#8` |
| 行名・列名の自然順ソート | `BuildCrosstabTest#5`, `BuildCrosstabTest#6` |
| 小数集計の精度(`Decimal`化) | `BuildCrosstabTest#3` |
| `--ascii`(ASCII安全出力) | `CliAsciiModeTest#1`, `#2` |
| `--col-width`(折り返し表示) | `CliColWidthOptionTest#1`〜`#3` |
| `--width`(表全体の幅指定) | `CliColWidthOptionTest#4` |
| 列幅の自動拡大 | `ColumnWidthAutoAdjustTest#1`〜`#4` |
| 標準入力・区切り文字・タイトル | `CliInputSourceTest#1`〜`#4` |
| コメント行・引用符付き`#`の扱い | `ParseRowsTest#1`, `#3` |
| 入力エラー時の短いメッセージ表示 | `CliErrorHandlingTest#1`〜`#5`, `ParseRowsTest#4`, `BuildCrosstabTest#4` |
