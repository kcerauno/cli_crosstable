# cli_crosstable

CSV データから [rich](https://github.com/Textualize/rich) を使ってクロス集計表を作成し、ターミナルに表示するシンプルな CLI ツールです。

## 特徴

- **二値データモード**: 存在=`●`、不在=`−` のマークで表示
- **数値データモード**: 3列目の値をセルごとに合計して表示(2列データの場合は出現回数を集計)
- **行名・列名は常にソートされて表示**(左から右・上から下)
- **`--ascii` オプション**: 罫線・マークをASCII文字(`+ - |`, `O`, `.`)のみに変換。SSHログの保存やエディタへの貼り付け時にUnicode文字の幅ズレでレイアウトが崩れるのを防止
- **`--col-width` オプション**: 列名や値が長い場合に省略(`…`)せず、指定幅で折り返して全文を表示
- 標準入力からの読み込みに対応、パイプ運用が可能

## インストール

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使い方

### 1. 二値データ(存在/不在)

入力(1列目: 列名, 2列目: 行名):

```
SrvAlice,34112876
SrvAlice,98783911
SrvBob,34112876
SrvCharlie,98783914
```

```bash
python crosstable.py sample_data/binary.csv
```

```
┏━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━┓
┃          ┃ SrvAlice ┃ SrvBob ┃ SrvCharlie ┃
┡━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━┩
│ 34112876 │    ●     │   ●    │     −      │
│ 98783911 │    ●     │   ●    │     −      │
│ ...      │          │        │            │
└──────────┴──────────┴────────┴────────────┘
```

### 2. 数値データ(集計値)

入力(1列目: 列名, 2列目: 行名, 3列目: 値):

```
SrvAlice,34112876,3
SrvAlice,98783911,1
SrvBob,34112876,3
```

```bash
python crosstable.py --numeric sample_data/numeric.csv
```

同じ(列名, 行名)の組み合わせが複数行あった場合は値が合計されます。

### 3. 二値データ + `--numeric`(出現回数の集計)

2列データに `--numeric` を指定すると、(列名, 行名) の組み合わせの出現回数を集計します。

```bash
python crosstable.py --numeric sample_data/binary.csv
```

### 標準入力から

```bash
cat sample_data/numeric.csv | python crosstable.py --numeric
```

### ASCIIセーフな出力(ログ保存向け)

```bash
python crosstable.py --ascii sample_data/binary.csv
```

```
+-------------------------------------------+
|          | SrvAlice | SrvBob | SrvCharlie |
|----------+----------+--------+------------|
| 34112876 |    O     |   O    |     .      |
| ...      |          |        |            |
+-------------------------------------------+
```

### 長い列名/行名を省略せず折り返す

```bash
python crosstable.py --col-width 10 sample_data/long_row_name.csv
```

## オプション一覧

| オプション | 説明 |
|---|---|
| `input` (位置引数) | 入力CSVファイル。省略時は標準入力を読み込む |
| `-n`, `--numeric` | 数値データとして扱う(3列目を合計、2列データなら出現回数を集計) |
| `-d`, `--delimiter` | 区切り文字(デフォルト: `,`) |
| `-t`, `--title` | 表のタイトル |
| `-a`, `--ascii` | 罫線・マークをASCII文字のみで出力する |
| `-w`, `--col-width` | 1列あたりの最大表示幅(文字数)。超える内容は省略せず折り返す |

入力ファイルが指定されず、標準入力からもデータが渡されない場合(例: 端末で引数なしに実行した場合)や、データが空の場合はエラーメッセージと使い方を表示して終了します(終了コード1)。`#` で始まる行、空行はコメントとして無視されます。

## サンプルデータ (`sample_data/`)

| ファイル | 内容 |
|---|---|
| `binary.csv` | 二値データの基本サンプル |
| `numeric.csv` | 数値データの基本サンプル |
| `long_row_name.csv` | 長い行名を含むサンプル(`--col-width` の折り返し確認用) |
| `width_check.csv` | 列数が多く、長い列名/行名も含む幅の自動調整・省略確認用サンプル |

## テスト

標準ライブラリの `unittest` で単体テスト・CLI結合テストを実施しています。

```bash
python -m unittest discover -s tests -v
```

## ライセンス

[MIT License](LICENSE)
