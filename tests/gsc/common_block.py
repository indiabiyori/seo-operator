# ---------------------------------------------------------------------------
# 共通部分（striking_distance.py / low_ctr.py / decay.py で同じコード。単体で動かすためにコピーしている）
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_INPUT_ERROR = 2

COLUMN_ALIASES = (
    ("query", ("Top queries", "Query", "Queries", "Search query",
               "上位のクエリ", "クエリ", "検索クエリ")),
    ("page", ("Top pages", "Page", "Pages", "Landing Page", "URL", "Address",
              "上位のページ", "ページ", "ランディング ページ", "ランディングページ")),
    ("clicks", ("Clicks", "Url Clicks", "URL Clicks", "クリック数", "クリック")),
    ("impressions", ("Impressions", "表示回数", "インプレッション", "インプレッション数")),
    ("ctr", ("CTR", "URL CTR", "Site CTR", "クリック率")),
    ("position", ("Position", "Average position", "Avg. position", "Average Position",
                  "掲載順位", "平均掲載順位")),
)
ALIAS_MAP = dict(COLUMN_ALIASES)
FIELD_LABELS = {
    "query": "クエリ",
    "page": "ページ",
    "clicks": "クリック数",
    "impressions": "表示回数",
    "ctr": "CTR",
    "position": "掲載順位",
}
REQUIRED_METRICS = ("clicks", "impressions", "position")
NUMERIC_FIELDS = ("clicks", "impressions", "ctr", "position")
METRIC_FIELDS = NUMERIC_FIELDS
DELIMITERS = ((",", "カンマ"), ("\t", "タブ"), (";", "セミコロン"))

# Search Console の画面で「~」「-」と表示される値は、ダウンロードしたファイルでは 0 になる。
# 掲載順位は最小 1 なので、掲載順位 0 は「値なし」とみなす（負の値とは別に数える）
ZERO_POSITION_LABEL = "掲載順位 0（エクスポートで値なしが 0 になったもの）"
ZERO_POSITION_MODES = ("exclude", "missing")

# CSV インジェクション対策: 表計算ソフトが数式として解釈しうる先頭の文字（OWASP の推奨に合わせた）
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
TEXT_OUTPUT_COLUMNS = ("query", "page")

# 列名の照合で無視する見えない文字（BOM、ゼロ幅スペースなど）
INVISIBLE_CHARS = dict.fromkeys((0xFEFF, 0x200B, 0x200C, 0x200D, 0x2060), None)

# 比較表示のままのエクスポートで、指標名の前後に付く期間ラベルらしい語
PERIOD_LABEL_RE = re.compile(
    r"[0-9]|last|previous|prev|current|compare|comparison|\bvs\b|change|diff|"
    r"期間|前期|今期|当期|前年|昨年|過去|直近|前の|今の|日間|か月|ヶ月|カ月|週間|比較|差分|変化|増減")

# 数値の表記（小数点がカンマか点か）の判定に使うパターン
EU_NUMBER_RE = re.compile(r"-?\d{1,3}(?:\.\d{3})+,\d+")      # 1.234,5
US_NUMBER_RE = re.compile(r"-?\d{1,3}(?:,\d{3})+\.\d+")      # 1,234.5
DOT_GROUPED_RE = re.compile(r"-?\d{1,3}(?:\.\d{3})+")        # 1.234（件数の列では桁区切り）
COMMA_GROUPED_RE = re.compile(r"-?\d{1,3}(?:,\d{3})+")       # 1,234（件数の列では桁区切り）
DECIMAL_COMMA_RE = re.compile(r"-?\d*,\d+")                  # 3,5（掲載順位・CTR の列では小数）
DECIMAL_POINT_RE = re.compile(r"-?\d*\.\d+")                 # 3.5

# Search Console の zip（「エクスポート」で CSV を選んだもの）を展開せずに読むための設定
ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06")  # 通常の zip、空の zip
ZIP_TABLES = (
    ("query", "クエリの表", ("クエリ.csv", "Queries.csv")),
    ("page", "ページの表", ("ページ.csv", "Pages.csv")),
)
ZIP_TABLE_LABELS = {key: label for key, label, _names in ZIP_TABLES}
# 展開後の大きさの上限（1 つの表）。画面からのエクスポートは 1 表 1,000 行で、数百 KB にもならない。
# 小さな zip が展開すると膨らむ場合（zip 爆弾）に、メモリを使い切らないための上限
ZIP_MEMBER_LIMIT = 100 * 1024 * 1024
ZIP_METHODS = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
# zip の読み込みで起きうる例外（壊れた zip、CRC の不一致、名前の文字コードの不整合など）
ZIP_ERRORS = (zipfile.BadZipFile, zlib.error, EOFError, OSError, ValueError, NotImplementedError, RuntimeError)


class InputError(Exception):
    """入力エラー。main() で受け取り、終了コード 2 で終了する。"""


def log(message=""):
    """進捗・サマリーを標準エラー出力に書く。"""
    print(message, file=sys.stderr)


def setup_stderr():
    """表示できない文字があっても止まらないようにする。"""
    try:
        sys.stderr.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass


def command_line(parts):
    """表示用のコマンド行を作る。コピーしてそのまま実行できるように引用する（Windows では空白を含む語だけを " で囲む）。"""
    if os.name == "nt":
        return " ".join(f'"{p}"' if (not p or " " in p) else p for p in parts)
    return shlex.join(parts)


def missing_packages(packages, argv=None):
    """必要なパッケージがないときに、用意の方法を表示して終了コード 2 を返す。

    import に失敗した時点で終了すると --help も表示できないため、main() が parse_args の後に呼ぶ。
    """
    script = os.path.abspath(__file__)
    requirements = os.path.join(os.path.dirname(os.path.dirname(script)), "requirements.txt")
    args = list(sys.argv[1:] if argv is None else argv)
    log(f"エラー: 必要なパッケージが見つかりません（{', '.join(packages)}）。")
    log("次のどちらかの方法で実行してください。")
    log("  uv を使う場合（必要なパッケージを自動で入れて実行します）:")
    log("    uv run " + command_line([script] + args))
    log("  pip を使う場合（仮想環境を作って有効にし、パッケージを入れてから、もう一度実行します）:")
    log("    pip install -r " + command_line([requirements]))
    return EXIT_INPUT_ERROR


def normalize_header(name):
    """列名を照合用に正規化する（BOM・ゼロ幅文字・前後の空白・全角空白を除き、英字を小文字にする）。"""
    text = unicodedata.normalize("NFKC", str(name)).translate(INVISIBLE_CHARS)
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()


def zip_message(path):
    """zip（または .xlsx）を受け付けない入力（low_ctr.py の --benchmark）に渡されたときのメッセージ。"""
    return (f"zip ファイル（または Excel の .xlsx）は、この入力には使えません: {path}\n"
            "  対処: CSV を指定してください。Excel で作った表は、CSV 形式で保存し直してください。")


def input_file_error(path, error):
    """入力ファイルを開けない・読めないときの入力エラー。"""
    if isinstance(error, FileNotFoundError):
        return InputError(f"ファイルが見つかりません: {path}\n  対処: パスとファイル名を確認してください。")
    if isinstance(error, IsADirectoryError):
        return InputError(f"ファイルではなくフォルダが指定されています: {path}")
    return InputError(f"ファイルを読み込めません: {path}（{error}）")


def read_bytes(path):
    """ファイル全体をバイト列で読む。"""
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as e:
        raise input_file_error(path, e)


def looks_like_zip(data):
    return data[:4] in ZIP_MAGICS


def escape_controls(text):
    """改行などの制御文字を \\n や \\u202e の表記に置き換える（zip の中の名前で、表示の行を偽れないようにする）。"""
    return "".join(
        c.encode("unicode_escape").decode("ascii")
        if unicodedata.category(c)[0] == "C" or unicodedata.category(c) in ("Zl", "Zp") else c
        for c in text)


def zip_member_names(info):
    """zip の中のファイル名の候補を返す（先頭を表示に使う）。

    UTF-8 のフラグがない名前を zipfile は cp437 として読むため、cp437 でバイト列に戻し、UTF-8 → cp932 の順に読み直す
    （macOS で圧縮し直した zip は UTF-8 をフラグなしで、日本語版 Windows の古い圧縮機能は cp932 で書く）。
    読めた候補はすべて残す。filename ではなく orig_filename を使う（Windows では filename の \\ が / に置き換わり、
    cp932 の 2 バイト目の 0x5C が壊れるため）。
    """
    names = []
    if not info.flag_bits & 0x800:
        raw = info.orig_filename.encode("cp437")
        for encoding in ("utf-8", "cp932"):
            try:
                names.append(raw.decode(encoding))
            except UnicodeDecodeError:
                pass
        # Python 3.12 以降は、Unicode Path 拡張フィールド（0x7075）の名前が filename に入る
        if info.filename.replace("\\", "/") != info.orig_filename.replace("\\", "/"):
            names.insert(0, info.filename)
    names.append(info.filename)
    return list(dict.fromkeys(names))


def zip_member_key(name):
    """照合用に、フォルダを除いたファイル名を正規化する（NFKC で分解された濁点をまとめ、英字の大文字・小文字をそろえる）。"""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    return unicodedata.normalize("NFKC", base).casefold()


def is_zip_junk(name):
    """フォルダ、macOS が付ける __MACOSX/ の中と ._ で始まるファイル、空の名前なら True。"""
    parts = name.replace("\\", "/").split("/")
    return name.endswith(("/", "\\")) or "__MACOSX" in parts or parts[-1].startswith("._") or not parts[-1]


def format_mb(size):
    """バイト数を MB（1,048,576 バイト）で小数第 1 位まで表す（上限と紛れないように切り上げる）。"""
    tenths = -(-size * 10 // 1048576)
    return f"{tenths // 10:,}.{tenths % 10} MB"


def zip_broken(path, error, member=None):
    """zip を読めないときの入力エラー（壊れている、途中で切れている、名前の文字コードが不正など）。"""
    detail = f"{type(error).__name__}: {error}"
    if member:
        detail = f"{member}: {detail}"
    return InputError(f"zip ファイルを読めません（壊れているか、ダウンロードが途中で止まった可能性があります）: {path}\n"
                      f"  詳細: {escape_controls(detail)}\n"
                      "  対処: Search Console からダウンロードし直してください。展開できる場合は、中の CSV を直接指定しても構いません。")


def find_zip_tables(archive, path):
    """zip の中のクエリの表とページの表を探す。

    戻り値は ({"query": [(ZipInfo, 表示名), ...], "page": [...]}, zip の中の CSV の表示名のリスト)。
    名前は、フォルダを除いた部分が ZIP_TABLES のどれかと一致するものを選ぶ（endswith は ._クエリ.csv も拾うので使わない）。
    """
    entries = []
    for info in archive.infolist():
        names = zip_member_names(info)
        first = unicodedata.normalize("NFC", names[0])
        entries.append((info, first, escape_controls(first), names))
    shown = [first for _info, first, _display, _names in entries]
    if "[Content_Types].xml" in shown and any(n.startswith("xl/") for n in shown):
        raise InputError(f"Excel の .xlsx ファイルのようです: {path}\n"
                         "  対処: Search Console の「エクスポート」では CSV を選んでください。"
                         "Excel で作った表は、CSV 形式で保存し直してください。")
    files = [entry for entry in entries if not is_zip_junk(entry[1])]
    found = {}
    for key, _label, wanted in ZIP_TABLES:
        wanted_keys = {zip_member_key(w) for w in wanted}
        found[key] = [(info, display) for info, _first, display, names in files
                      if any(zip_member_key(n) in wanted_keys for n in names)]
    csvs = [display for _info, first, display, _names in files if first.lower().endswith(".csv")]
    return found, csvs


def zip_not_found(path, key_option, found, csvs):
    """--key に合う表が zip にないときの入力エラー。"""
    order = ("query", "page") if key_option == "auto" else (key_option,)
    wanted = ", ".join(name for key, _label, names in ZIP_TABLES if key in order for name in names)
    listed = (", ".join(csvs[:10]) + (f" ほか {len(csvs) - 10} 件" if len(csvs) > 10 else "")) if csvs else "（なし）"
    if key_option == "auto":
        lines = [f"zip の中にクエリの表もページの表も見つかりません: {path}"]
    else:
        lines = [f"zip の中に{ZIP_TABLE_LABELS[key_option]}が見つかりません: {path}"]
    lines.append(f"  探した名前: {wanted}（英字の大文字・小文字は区別しない。zip の中のフォルダも探す）")
    lines.append(f"  zip の中の CSV: {listed}")
    other = "page" if key_option == "query" else "query"
    if key_option != "auto" and found[other]:
        label = ZIP_TABLE_LABELS[other]
        lines.append(f"  {label}（{found[other][0][1]}）はあります。{label}を使うなら --key {other} を指定してください。")
    lines.append("  対処: Search Console の「検索パフォーマンス」→「エクスポート」で CSV を選んで書き出した zip を"
                 "指定してください。画面の言語が日本語・英語以外の zip は、ファイル名も列名も訳されているため読めません。"
                 "表示言語を日本語か英語にしてから書き出し直してください。名前を変えた CSV を入れた zip は、"
                 "展開して中の CSV を直接指定してください。")
    return InputError("\n".join(lines))


def read_zip_table(archive, path, found, key, limit):
    """zip の中の表を 1 つ読み、(テキスト, 文字コード名, 警告のリスト, 表示名) を返す。

    同じ種類の表が 2 つ以上ある、パスワード付き、対応していない圧縮方式、展開後の大きさが上限を超えるものは
    入力エラーにする。展開後の大きさは中央ディレクトリの申告で先に調べ、読む量も上限 + 1 バイトまでにする。
    """
    if len(found[key]) > 1:
        raise InputError(f"zip の中に{ZIP_TABLE_LABELS[key]}が複数あります: {path}\n"
                         "  候補: " + ", ".join(display for _info, display in found[key]) + "\n"
                         "  対処: zip を展開して、使う CSV を直接指定してください。")
    info, member = found[key][0]
    source = f"{path} の中の {member}"
    if info.flag_bits & 0x1:
        raise InputError(f"パスワード付きの zip は読めません: {source}\n"
                         "  対処: zip を展開して、中の CSV を直接指定してください。")
    if info.compress_type not in ZIP_METHODS:
        raise InputError(f"この zip の圧縮方式（番号 {info.compress_type}）には対応していません: {source}\n"
                         "  対処: zip を展開して、中の CSV を直接指定してください"
                         "（Search Console からダウンロードしたままの zip は読めます）。")
    too_big = ("  対処: 画面からのエクスポートは 1 つの表が最大 1,000 行で、この大きさにはなりません。"
               "API や BigQuery で取った大きなデータは、期間とキー（クエリ・URL）ごとに集計してから渡してください。"
               "集計済みで大きいだけなら、zip を展開して CSV を直接指定してください。")
    if info.file_size > limit:
        raise InputError(f"zip の中の CSV が大きすぎます（展開後 {format_mb(info.file_size)}、"
                         f"上限 {limit // 1048576} MB）: {source}\n" + too_big)
    try:
        with archive.open(info) as f:
            data = f.read(limit + 1)
    except ZIP_ERRORS as e:
        raise zip_broken(path, e, member)
    # zipfile は申告の大きさを超えて返さない（超えると CRC の不一致になる）。zipfile の実装が変わったときのために残す
    if len(data) > limit:
        raise InputError(f"zip の中の CSV が大きすぎます（展開後 {limit // 1048576} MB を超えています）: {source}\n"
                         + too_big)
    text, encoding, warnings = decode_text(data, source)
    return text, encoding, warnings, source


def read_zip_export(fileobj, path, key_option, limit=ZIP_MEMBER_LIMIT):
    """Search Console の zip を展開せずに読み、--key に合う表を (テキスト, 文字コード名, 警告のリスト, 表示名) で返す。

    --key query はクエリの表（クエリ.csv / Queries.csv）、page はページの表（ページ.csv / Pages.csv）を読み、
    もう一方には切り替えない。auto はクエリの表を読む。ただし、クエリの表にデータ行がなく、ページの表があれば、
    ページの表を読む（ページで絞り込んだエクスポートでは、クエリの表がヘッダー行だけのことがある）。
    ディスクには何も書かない。
    """
    try:
        archive = zipfile.ZipFile(fileobj)
    except ZIP_ERRORS as e:
        raise zip_broken(path, e)
    with archive:
        found, csvs = find_zip_tables(archive, path)
        order = ("query", "page") if key_option == "auto" else (key_option,)
        chosen = next((key for key in order if found[key]), None)
        if chosen is None:
            raise zip_not_found(path, key_option, found, csvs)
        text, encoding, warnings, source = read_zip_table(archive, path, found, chosen, limit)
        notes = []
        if key_option == "auto" and chosen == "query" and found["page"]:
            page_member = found["page"][0][1]
            if has_data_rows(text):
                notes.append(f"注意: zip にはページの表（{page_member}）もあります。--key auto ではクエリの表を使います。"
                             "ページ別に見るなら --key page を付けてください。")
            else:
                query_member = found["query"][0][1]
                text, encoding, warnings, source = read_zip_table(archive, path, found, "page", limit)
                notes.append(f"注意: zip のクエリの表（{query_member}）にデータ行がないため、ページの表（{page_member}）を"
                             "使います。ページで絞り込んだエクスポートでは、クエリの表が空のことがあります。")
    return text, encoding, notes + warnings, source


def guess_utf16_without_bom(data):
    """BOM のない UTF-16 を NUL バイトの位置から推定する。該当しなければ None。"""
    sample = data[:65536]
    half = len(sample) // 2
    if half < 2:
        return None
    even_nuls = sample[0::2].count(0)
    odd_nuls = sample[1::2].count(0)
    if odd_nuls >= max(2, half // 20) and odd_nuls > 4 * even_nuls:
        return "utf-16-le"
    if even_nuls >= max(2, half // 20) and even_nuls > 4 * odd_nuls:
        return "utf-16-be"
    return None


def decode_text(data, source):
    """バイト列の文字コードを判定して (テキスト, 文字コード名, 警告のリスト) を返す。source はメッセージに使う名前。

    BOM があればそれに従う（UTF-8 / UTF-16）。BOM がなければ NUL バイトの位置で BOM なしの UTF-16 を見分け、
    それ以外は UTF-8 → cp932 の順に試す。UTF-8 としてほぼ正しく、壊れたバイトが少しだけある場合は
    そのバイトを置き換えて読み、標準エラー出力に警告を出す（cp932 として読むと全体が文字化けするため）。
    """
    undecodable = InputError(
        f"文字コードを判定できません: {source}\n"
        "  対処: UTF-8、cp932（Shift_JIS）、UTF-16 のいずれかで保存し直してください。")
    text = None
    encoding = None
    warnings = []
    if data.startswith(codecs.BOM_UTF8):
        encoding = "utf-8-sig"
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            text = data.decode(encoding, errors="replace")
            warnings.append(f"警告: UTF-8 として不正なバイトが {text.count(chr(0xFFFD))} 個あり、"
                            "置き換えて読みました（該当する文字は記号に置き換わります）。")
    elif data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        encoding = "utf-16"
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            raise undecodable
    else:
        utf16 = guess_utf16_without_bom(data)
        if utf16:
            encoding = utf16
            try:
                text = data.decode(encoding)
            except UnicodeDecodeError:
                raise undecodable
        else:
            try:
                text = data.decode("utf-8")
                encoding = "utf-8"
            except UnicodeDecodeError:
                replaced = data.decode("utf-8", errors="replace")
                n_bad = replaced.count("�")
                n_ok = sum(1 for ch in replaced if ord(ch) > 127) - n_bad
                if n_ok >= 10 * n_bad:
                    text, encoding = replaced, "utf-8"
                else:
                    try:
                        text = data.decode("cp932")
                        encoding = "cp932"
                    except UnicodeDecodeError:
                        if n_bad <= max(3, n_ok // 10):
                            text, encoding = replaced, "utf-8"
                        else:
                            raise undecodable
                if encoding == "utf-8":
                    warnings.append(f"警告: UTF-8 として不正なバイトが {n_bad} 個あり、置き換えて読みました"
                                    "（該当する文字は記号に置き換わります）。")
    if "\x00" in text:
        warnings.append(f"警告: NUL 文字が {text.count(chr(0))} 個あり、取り除いて読みました。")
        text = text.replace("\x00", "")
    return text, encoding, warnings


def has_data_rows(text):
    """ヘッダー行のほかに、空でない行が 1 行でもあれば True（区切り文字によらず、行の数だけを見る）。"""
    seen = 0
    try:
        for record in csv.reader(io.StringIO(text, newline="")):
            if any(cell.strip() for cell in record):
                seen += 1
                if seen > 1:
                    return True
    except csv.Error:
        return True  # 形式の問題は、この後の parse_csv_text で知らせる
    return False


def read_text(path):
    """zip を受け付けない入力（low_ctr.py の --benchmark）のファイルを読み、(テキスト, 文字コード名, 警告のリスト) を返す。"""
    data = read_bytes(path)
    if looks_like_zip(data):
        raise InputError(zip_message(path))
    return decode_text(data, path)


def read_export_text(path, key_option):
    """Search Console のエクスポートを読み、(テキスト, 文字コード名, 警告のリスト, 表示名) を返す。

    先頭の 4 バイトで zip かどうかを判定する（拡張子は見ない）。zip なら展開せずに、--key に合う表を読む。
    zip はファイル全体をメモリに読まず、中央ディレクトリと選んだ表だけを読む（シークできない入力だけはメモリに読む）。
    表示名は、CSV ならパス、zip なら「x.zip の中の クエリ.csv」。
    """
    try:
        f = open(path, "rb")
    except OSError as e:
        raise input_file_error(path, e)
    with f:
        try:
            head = f.read(4)
            is_zip = head in ZIP_MAGICS
            data = None if (is_zip and f.seekable()) else head + f.read()
        except OSError as e:
            raise input_file_error(path, e)
        if is_zip:
            return read_zip_export(f if data is None else io.BytesIO(data), path, key_option)
    text, encoding, warnings = decode_text(data, path)
    return text, encoding, warnings, path


def first_record(text, delimiter):
    """空行を飛ばして最初の行（ヘッダー行）を返す。"""
    try:
        for record in csv.reader(io.StringIO(text, newline=""), delimiter=delimiter):
            if any(cell.strip() for cell in record):
                return record
    except csv.Error:
        return []
    return []


def count_known_headers(header):
    known = {normalize_header(a) for _field, aliases in COLUMN_ALIASES for a in aliases}
    return sum(1 for name in header if normalize_header(name) in known)


def parse_csv_text(text, path):
    """CSV を読み、(ヘッダー, データ行のリスト, 区切り文字の名前, 読み飛ばした空行の数) を返す。

    区切り文字はカンマ・タブ・セミコロンのうち、ヘッダー行で既知の列名が最も多く見つかるものを使う
    （同数なら列の数が多いもの、それも同じならカンマ → タブ → セミコロンの順）。
    すべてのセルが空の行は読み飛ばす。ヘッダーより列が多い行は、余分なセルが空なら切り捨て、
    値があれば入力エラーにする（列がずれて別の列の値を読むのを防ぐため）。閉じていない引用符も入力エラーにする。
    """
    if not text.strip():
        raise InputError(
            f"ファイルが空です（ヘッダー行もありません）: {path}\n"
            "  対処: Search Console からエクスポートし直してください。"
        )
    try:
        csv.field_size_limit(2 ** 31 - 1)
    except OverflowError:  # pragma: no cover
        csv.field_size_limit(2 ** 24)
    best = None
    for delimiter, name in DELIMITERS:
        header = first_record(text, delimiter)
        score = (count_known_headers(header), len(header))
        if best is None or score > best[0]:
            best = (score, delimiter, name)
    _score, delimiter, delimiter_name = best

    # strict=True: 閉じていない引用符や、閉じた引用符の直後の文字を入力エラーにする（黙って列がずれるのを防ぐ）
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    header = None
    width = 0
    rows = []
    n_blank = 0
    try:
        for record in reader:
            if not any(cell.strip() for cell in record):
                if header is not None:
                    n_blank += 1
                continue
            if header is None:
                header = record
                width = len(header)
                continue
            if len(record) > width:
                if any(cell.strip() for cell in record[width:]):
                    raise InputError(
                        f"CSV の形式が不正です: {path}\n"
                        f"  詳細: {reader.line_num} 行目のセルの数が {len(record)} 個で、ヘッダーの {width} 個より多い\n"
                        "  対処: 行ごとに列の数がそろっているか確認してください。"
                        "桁区切りのカンマを含む数値（1,234）や小数点がカンマの数値（3,5）は引用符で囲む必要があります。"
                    )
                record = record[:width]
            elif len(record) < width:
                record = record + [""] * (width - len(record))
            rows.append(record)
    except csv.Error as e:
        raise InputError(
            f"CSV の形式が不正です: {path}\n"
            f"  詳細: {reader.line_num} 行目付近: {e}\n"
            '  対処: 引用符（"）が閉じているか確認してください。セルの中の " は "" のように 2 つ重ねる必要があります。'
        )
    if header is None:
        raise InputError(
            f"ファイルが空です（ヘッダー行もありません）: {path}\n"
            "  対処: Search Console からエクスポートし直してください。"
        )
    return header, rows, delimiter_name, n_blank


def find_columns(header):
    """列名を正規化して照合し、({項目名: 列番号}, {項目名: [重複した列番号]}) を返す。"""
    alias_norms = {field: {normalize_header(a) for a in aliases} for field, aliases in COLUMN_ALIASES}
    matches = {}
    for idx, name in enumerate(header):
        norm = normalize_header(name)
        for field, _aliases in COLUMN_ALIASES:
            if norm in alias_norms[field]:
                matches.setdefault(field, []).append(idx)
                break
    found = {field: idxs[0] for field, idxs in matches.items() if len(idxs) == 1}
    conflicts = {field: idxs for field, idxs in matches.items() if len(idxs) > 1}
    return found, conflicts


def period_labeled_columns(header):
    """指標名に期間ラベルが付いた列名（比較表示のままのエクスポートらしい列）を返す。"""
    hits = []
    for name in header:
        norm = normalize_header(name)
        for field in METRIC_FIELDS:
            matched = False
            for alias in ALIAS_MAP[field]:
                a = normalize_header(alias)
                if a != norm and a in norm and PERIOD_LABEL_RE.search(norm.replace(a, " ")):
                    matched = True
                    break
            if matched:
                hits.append(name)
                break
    return hits


def comparison_hint():
    return ("  ヒント: 列名に期間のラベルが付いているようです。Search Console の比較表示のまま"
            "エクスポートした CSV は使えません。期間ごとに 1 回ずつエクスポートしてください。")


def missing_columns_message(path, fields, header, either=False):
    """必須列がないときのメッセージ（見つかった列名と受け付ける列名）を作る。"""
    names = [f"{f}（{FIELD_LABELS[f]}）" for f in fields]
    joined = " または ".join(names) if either else "、".join(names)
    shown = ", ".join(f"'{c}'" for c in header) if len(header) else "（なし）"
    lines = [
        f"必須の列が見つかりません: {path}",
        f"  見つからない項目: {joined}",
        f"  CSV にあった列名: {shown}",
        "  受け付ける列名（英字の大文字・小文字、前後の空白、全角・半角は区別しない）:",
    ]
    for f in fields:
        lines.append(f"    {f}: " + ", ".join(ALIAS_MAP[f]))
    if period_labeled_columns(header):
        lines.append(comparison_hint())
    found, _conflicts = find_columns(header)
    if "impressions" in found and "clicks" not in found and "position" not in found:
        lines.append(
            "  対処: 表示回数だけの表は、生成 AI パフォーマンス レポートなど、「検索結果」以外のレポートの"
            "エクスポートのようです。Search Console の「検索パフォーマンス」→「検索結果」からエクスポートし直してください。"
        )
    else:
        lines.append(
            "  対処: Search Console の「検索パフォーマンス」からエクスポートした CSV を使うか、"
            "列名を上のいずれかに変えてください。"
        )
    return "\n".join(lines)


def conflict_message(path, field, header, indices):
    cols = ", ".join(f"'{header[i]}'（{i + 1} 列目）" for i in indices)
    return (f"同じ項目を表す列が複数あります: {path}\n"
            f"  項目: {field}（{FIELD_LABELS[field]}）: {cols}\n"
            "  どの列を使うか決められないため中止しました。\n"
            "  対処: 使う列だけを残すか、使わない列の名前を変えてください。")


def resolve_key(found, key_option, path, header):
    """キー列（query / page）を決める。auto では query を優先する。"""
    if key_option == "auto":
        if "query" in found:
            key = "query"
        elif "page" in found:
            key = "page"
        else:
            raise InputError(missing_columns_message(path, ["query", "page"], header, either=True))
    else:
        if key_option not in found:
            raise InputError(missing_columns_message(path, [key_option], header))
        key = key_option
    other = "page" if key == "query" else "query"
    if other not in found:
        other = None
    return key, other


def number_text(value):
    """数値の文字列を全角 → 半角にし、空白（桁区切りの空白を含む）を除く。"""
    text = unicodedata.normalize("NFKC", str(value)).replace("−", "-")
    return re.sub(r"\s+", "", text)


def column_decimal_evidence(field, texts):
    """列の値から、小数点がカンマ（3,5）か点（3.5）かの手がかりを探す。戻り値は (カンマ, 点)。"""
    comma = point = False
    counts = field in ("clicks", "impressions")
    for raw in texts:
        t = raw.replace("%", "")
        if not t:
            continue
        if EU_NUMBER_RE.fullmatch(t):
            comma = True
        elif US_NUMBER_RE.fullmatch(t):
            point = True
        elif counts:
            # 件数は整数なので、3 桁ごとの点は桁区切り（小数点はカンマ）、3 桁ごとのカンマは桁区切り（小数点は点）
            if DOT_GROUPED_RE.fullmatch(t):
                comma = True
            elif COMMA_GROUPED_RE.fullmatch(t):
                point = True
        else:
            # 掲載順位と CTR は 1,000 を超えないので、数字の間のカンマは小数点とみなす
            if DECIMAL_COMMA_RE.fullmatch(t):
                comma = True
            elif DECIMAL_POINT_RE.fullmatch(t):
                point = True
        if comma and point:
            break
    return comma, point


def decide_decimal_marks(texts_by_field):
    """列ごとに小数点の表記を決める。戻り値は ({項目名: "comma" または "point"}, 説明)。"""
    evidence = {f: column_decimal_evidence(f, t) for f, t in texts_by_field.items()}
    any_comma = any(c and not p for c, p in evidence.values())
    any_point = any(p for _c, p in evidence.values())
    modes = {}
    for field, (comma, point) in evidence.items():
        if comma and not point:
            modes[field] = "comma"
        elif point:
            modes[field] = "point"
        else:
            modes[field] = "comma" if (any_comma and not any_point) else "point"
    note = ""
    comma_fields = [f for f in texts_by_field if modes[f] == "comma"]
    if comma_fields:
        note = ("小数点がカンマの表記（3,5 や 1.234,5）とみなした列: " + ", ".join(comma_fields)
                + "（点は桁区切りとして扱う）")
        if any_point:
            note += "。警告: 小数点がカンマの列と点の列が混在しています。値を確認してください"
    mixed = [f for f, (c, p) in evidence.items() if c and p]
    if mixed:
        note = (note + "。" if note else "") + (
            "警告: 次の列で小数点の表記（3,5 と 3.5）が混在しています。点を小数点とみなしました: " + ", ".join(mixed))
    return modes, note


def parse_numbers(texts, mode, index):
    """number_text() 済みの文字列のリストを float の Series にする。解析できない値・無限大は NaN。"""
    cleaned = []
    for t in texts:
        if mode == "comma":
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
        cleaned.append(t)
    values = pd.to_numeric(pd.Series(cleaned, index=index, dtype=object), errors="coerce").astype(float)
    return values.where(values.abs() != float("inf"))


def compute_ctr(clicks, impressions):
    """クリック数 / 表示回数。表示回数が 0 の行は 0。"""
    safe = impressions.where(impressions > 0)
    return (clicks / safe).fillna(0.0)


def detect_ctr_scale(values, clicks, impressions):
    """数値だけの CTR 列が比率か百分率かを判定する。戻り値は (scale, 理由)。"""
    mask = values.notna() & clicks.notna() & impressions.notna() & (impressions > 0)
    if mask.any():
        calc = clicks[mask] / impressions[mask]
        diff_ratio = float((values[mask] - calc).abs().median())
        diff_pct = float((values[mask] / 100.0 - calc).abs().median())
        detail = (f"クリック数 / 表示回数との差の中央値: 比率とみなすと {diff_ratio:.4g}、"
                  f"百分率とみなすと {diff_pct:.4g}")
        if diff_ratio < diff_pct:
            return "ratio", f"比率とみなす（{detail}）"
        if diff_pct < diff_ratio:
            return "percent", f"百分率とみなして 100 で割る（{detail}）"
    max_value = values.max()
    if pd.notna(max_value) and max_value > 1:
        return "percent", "最大値が 1 を超えるため百分率とみなして 100 で割る"
    return "ratio", "最大値が 1 以下のため比率とみなす"


def parse_ctr(texts, mode, clicks, impressions, unit, index):
    """CTR 列を比率（0〜1）に変換する。戻り値は (Series, 判定の説明)。"""
    is_pct = pd.Series(["%" in t for t in texts], index=index, dtype=bool)
    values = parse_numbers([t.replace("%", "") for t in texts], mode, index)
    values = values.where(~(values < 0))
    has_value = values.notna()
    pct_rows = is_pct & has_value
    plain_rows = (~is_pct) & has_value
    notes = []
    if pct_rows.any():
        notes.append(f"% 付きの値 {int(pct_rows.sum())} 行は百分率として 100 で割る")
    divide = pct_rows
    if plain_rows.any():
        n_plain = int(plain_rows.sum())
        if unit == "percent":
            scale, reason = "percent", "--ctr-unit percent の指定により百分率とみなして 100 で割る"
        elif unit == "ratio":
            scale, reason = "ratio", "--ctr-unit ratio の指定により比率とみなす"
        else:
            scale, reason = detect_ctr_scale(values[plain_rows], clicks[plain_rows], impressions[plain_rows])
        notes.append(f"数値だけの値 {n_plain} 行: {reason}")
        if scale == "percent":
            divide = pct_rows | plain_rows
    ctr = values.where(~divide, values / 100.0)
    missing = ctr.isna()
    if missing.any():
        ctr = ctr.where(~missing, compute_ctr(clicks, impressions))
        notes.append(f"CTR が空・解析できない・負の値の {int(missing.sum())} 行はクリック数 / 表示回数で補う")
    return ctr, "。".join(notes) if notes else "CTR 列に値がない"


def check_ctr_consistency(ctr, clicks, impressions):
    """変換後の CTR がクリック数 / 表示回数と大きく違えば警告の文を返す（なければ None）。"""
    mask = ctr.notna() & clicks.notna() & impressions.notna() & (impressions > 0)
    if not mask.any():
        return None
    calc = clicks[mask] / impressions[mask]
    diff = float((ctr[mask] - calc).abs().median())
    reference = float(calc.median())
    if diff > max(0.005, 0.5 * reference):
        return (f"警告: CTR 列の値がクリック数 / 表示回数と大きく違います（差の中央値 {diff:.4g}）。"
                "--ctr-unit の指定と、列がずれていないかを確認してください。")
    return None


def load_gsc_csv(path, key_option, ctr_unit, zero_position="exclude"):
    """GSC のエクスポート（CSV か Search Console の zip）を読み、列を正規化した DataFrame と読み込み情報を返す。

    掲載順位が 0（"0"、"0.0"、"0,0" などを解析した結果が 0）の値は「値なし」とみなす。
    zero_position="exclude" ではその行を除外し、"missing" では掲載順位を NaN にして行を残す。
    """
    if zero_position not in ZERO_POSITION_MODES:
        raise ValueError(f"zero_position: {zero_position!r}")
    text, encoding, warnings, source = read_export_text(path, key_option)
    header, rows, delimiter_name, n_blank = parse_csv_text(text, source)
    found, conflicts = find_columns(header)
    ctr_conflict = conflicts.pop("ctr", None)
    for field in ("query", "page", "clicks", "impressions", "position"):
        if field in conflicts:
            raise InputError(conflict_message(source, field, header, conflicts[field]))
    key, other = resolve_key(found, key_option, source, header)
    missing = [f for f in REQUIRED_METRICS if f not in found]
    if missing:
        raise InputError(missing_columns_message(source, missing, header))
    labeled = period_labeled_columns(header)
    if labeled:
        warnings.append("警告: 期間ラベル付きらしい列があります（" + ", ".join(f"'{c}'" for c in labeled[:4])
                        + "）。比較表示のままのエクスポートなら、期間ごとに出し直してください。"
                        "今回はラベルのない列を使います。")

    index = pd.RangeIndex(len(rows))

    def column(field):
        idx = found[field]
        return [row[idx] for row in rows]

    texts = {f: [number_text(v) for v in column(f)] for f in NUMERIC_FIELDS if f in found}
    modes, decimal_note = decide_decimal_marks(texts)
    clicks = parse_numbers(texts["clicks"], modes["clicks"], index)
    impressions = parse_numbers(texts["impressions"], modes["impressions"], index)
    position = parse_numbers(texts["position"], modes["position"], index)
    negative = (clicks < 0) | (impressions < 0) | (position < 0)
    unparsed = (clicks.isna() | impressions.isna() | position.isna()) & ~negative
    # 掲載順位 0 は値なし（負の値・解析できない行は、そちらの件数に数える）
    zero_position_rows = (position == 0) & ~negative & ~unparsed
    clicks = clicks.where(~negative)
    impressions = impressions.where(~negative)
    position = position.where(~negative & (position != 0))
    if ctr_conflict:
        cols = ", ".join(f"'{header[i]}'" for i in ctr_conflict)
        ctr = compute_ctr(clicks, impressions)
        ctr_note = f"CTR の列が複数ある（{cols}）ため使わず、クリック数 / 表示回数で計算"
    elif "ctr" in found:
        ctr, ctr_note = parse_ctr(texts["ctr"], modes["ctr"], clicks, impressions, ctr_unit, index)
        inconsistent = check_ctr_consistency(ctr, clicks, impressions)
        if inconsistent:
            warnings.append(inconsistent)
    else:
        ctr = compute_ctr(clicks, impressions)
        ctr_note = "CTR 列がないためクリック数 / 表示回数で計算"

    data = {key: pd.Series([v.strip() for v in column(key)], index=index, dtype=object)}
    if other:
        data[other] = pd.Series([v.strip() for v in column(other)], index=index, dtype=object)
    data["clicks"] = clicks
    data["impressions"] = impressions
    data["ctr"] = ctr
    data["position"] = position
    df = pd.DataFrame(data, index=index)

    bad = unparsed | negative
    if zero_position == "exclude":
        bad = bad | zero_position_rows
    empty_key = (df[key] == "") & ~bad
    keep = ~(bad | empty_key)
    n_zero_position = int((zero_position_rows & ~empty_key).sum())
    df = df[keep].reset_index(drop=True)
    info = {
        "path": source,
        # decay.py の「同じ内容」の判定に使う（zip は中の時刻が違っても、同じ表なら同じ値になる）
        "content_sha256": hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest(),
        "encoding": encoding,
        "sep_name": delimiter_name,
        "n_input": int(len(rows)),
        "n_blank": int(n_blank),
        "n_bad_metric": int(unparsed.sum()),
        "n_negative": int(negative.sum()),
        "n_zero_position": n_zero_position,
        "zero_position": zero_position,
        "n_empty_key": int(empty_key.sum()),
        "key": key,
        "other": other,
        "found": {field: header[idx] for field, idx in found.items()},
        "ctr_note": ctr_note,
        "decimal_note": decimal_note,
        "warnings": warnings,
        "has_ctr_column": "ctr" in found,
    }
    return df, info


def log_load_info(info, label=""):
    keys = info["key"] + (f" + {info['other']}" if info["other"] else "")
    log(f"{label}入力: {info['path']}（文字コード {info['encoding']}、{info['sep_name']}区切り、"
        f"{info['n_input']} 行、キー列 {keys}）")
    mapping = ", ".join(f"{field}='{col}'" for field, col in info["found"].items())
    log(f"  列の対応: {mapping}")
    log(f"  CTR の単位: {info['ctr_note']}")
    if info["decimal_note"]:
        log(f"  数値の表記: {info['decimal_note']}")
    for warning in info["warnings"]:
        log(f"  {warning}")
    if info["n_blank"]:
        log(f"  空行 {info['n_blank']} 行を読み飛ばしました")
    if info["n_bad_metric"]:
        log(f"  除外: クリック数・表示回数・掲載順位のいずれかが空か解析できない行 {info['n_bad_metric']} 行")
    if info["n_negative"]:
        log(f"  除外: クリック数・表示回数・掲載順位のいずれかが負の値の行 {info['n_negative']} 行")
    if info["n_zero_position"]:
        if info["zero_position"] == "exclude":
            log(f"  除外: {ZERO_POSITION_LABEL}の行 {info['n_zero_position']} 行（掲載順位は最小 1 のため値なしとみなす）")
        else:
            log(f"  {ZERO_POSITION_LABEL}の行 {info['n_zero_position']} 行: 掲載順位を空欄（値なし）として扱います")
    if info["n_empty_key"]:
        log(f"  除外: キー列が空の行 {info['n_empty_key']} 行")


def excluded_summary(info, n_regex):
    """除外行数の合計と内訳の文字列を返す（掲載順位 0 は、除外する場合だけ内訳に入れる）。"""
    total = info["n_bad_metric"] + info["n_negative"] + info["n_empty_key"] + n_regex
    detail = f"数値を解析できない {info['n_bad_metric']}、負の値 {info['n_negative']}、"
    if info["zero_position"] == "exclude":
        total += info["n_zero_position"]
        detail += f"{ZERO_POSITION_LABEL} {info['n_zero_position']}、"
    detail += f"キー列が空 {info['n_empty_key']}、正規表現 {n_regex}"
    return total, detail


def compile_regex(pattern, option_name):
    if not pattern:
        return None
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        raise InputError(f"{option_name} の正規表現が不正です: {pattern}（{e}）")


def apply_filters(df, key, include_re, exclude_re):
    """キー列に --include-regex / --exclude-regex を適用する。戻り値は (DataFrame, 除外行数)。"""
    if include_re is None and exclude_re is None:
        return df, 0

    def hit(regex, value):
        return bool(regex.search(value) or regex.search(unicodedata.normalize("NFKC", value)))

    keep = []
    for value in df[key]:
        ok = True
        if include_re is not None and not hit(include_re, value):
            ok = False
        if ok and exclude_re is not None and hit(exclude_re, value):
            ok = False
        keep.append(ok)
    mask = pd.Series(keep, index=df.index, dtype=bool)
    return df[mask].reset_index(drop=True), int((~mask).sum())


def as_int_if_integral(series):
    """すべて整数値なら int64 にする（CSV に 12.0 ではなく 12 と出すため）。"""
    s = series.astype(float)
    if len(s) and bool(s.notna().all()) and bool(((s % 1) == 0).all()):
        return s.astype("int64")
    return s


def format_pct(value):
    if pd.isna(value):
        return ""
    return f"{value * 100:.2f}%"


def is_formula_like(value):
    """表計算ソフトが数式として解釈しうる文字列（先頭が = + - @ タブ CR）なら True。"""
    return isinstance(value, str) and value.startswith(FORMULA_PREFIXES)


def count_formula_cells(df):
    """query / page 列で、先頭が = + - @ タブ CR のセルの数を返す（値は変えない）。"""
    return sum(1 for col in TEXT_OUTPUT_COLUMNS if col in df.columns for v in df[col] if is_formula_like(v))


def sanitize_text_cells(df):
    """query / page 列で、先頭が = + - @ タブ CR のセルの前に ' を付ける。戻り値は (DataFrame, 件数)。"""
    count = 0
    updates = {}
    for col in TEXT_OUTPUT_COLUMNS:
        if col not in df.columns:
            continue
        values = []
        for v in df[col]:
            if is_formula_like(v):
                values.append("'" + v)
                count += 1
            else:
                values.append(v)
        updates[col] = pd.Series(values, index=df.index, dtype=object)
    if updates:
        df = df.assign(**updates)
    return df, count


def check_output_path(output, inputs):
    """-o が入力ファイルと同じなら入力エラーにする（入力を上書きしないため）。"""
    if not output or not os.path.exists(output):
        return
    for path in inputs:
        try:
            same = bool(path) and os.path.exists(path) and os.path.samefile(output, path)
        except OSError:
            same = False
        if same:
            raise InputError(f"-o の出力先が入力ファイルと同じです: {output}\n"
                             "  対処: 別のファイル名を指定してください（入力ファイルを上書きしないため）。")


def write_csv(df, output, sanitize=True):
    """-o があればファイルへ UTF-8（BOM 付き）で、なければ標準出力へ UTF-8（BOM なし）で書く。

    CSV インジェクション対策（' を付ける）は -o のファイルだけに適用する（sanitize=False で無効）。
    標準出力は Claude や他のプログラムが読む経路なので、値を変えずに書く。
    """
    if output:
        n_sanitized = 0
        if sanitize:
            df, n_sanitized = sanitize_text_cells(df)
        try:
            df.to_csv(output, index=False, encoding="utf-8-sig")
        except OSError as e:
            raise InputError(f"出力ファイルに書き込めません: {output}（{e}）")
        log(f"出力ファイル: {output}（{len(df)} 行、UTF-8 BOM 付き）")
        if n_sanitized:
            log(f"CSV インジェクション対策: query / page 列で先頭が = + - @ タブ CR のセル {n_sanitized} 個の前に "
                "' を付けました（-o のファイルだけ。pandas などで読むときは先頭の ' を除くか、--no-sanitize で出し直す）")
        return
    n_formula = count_formula_cells(df)
    data = df.to_csv(index=False).encode("utf-8")
    try:
        sys.stdout.buffer.write(data)
        sys.stdout.flush()
    except BrokenPipeError:
        # head などで途中まで読まれた場合は静かに終わる
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    if n_formula:
        log(f"注意: query / page 列に、先頭が = + - @ タブ CR のセルが {n_formula} 個あります。標準出力には ' を付けず"
            "そのまま書きました。Excel で開くなら -o でファイルに書き出してください（-o のファイルでは ' を付けて、"
            "数式として扱われるのを防ぐ）。")


def add_common_args(parser):
    parser.add_argument(
        "--key", choices=["auto", "query", "page"], default="auto",
        help="キー列。auto はクエリ列があればクエリ、なければページ（デフォルト: %(default)s）。"
             "クエリ × ページの CSV では、キーにしなかった列も出力に残す。Search Console の zip では、"
             "query はクエリの表、page はページの表を読む（auto はクエリの表。データ行がなければページの表）")
    parser.add_argument(
        "--ctr-unit", choices=["auto", "percent", "ratio"], default="auto",
        help="CTR 列の単位（デフォルト: %(default)s）。auto は数値だけの列をクリック数 / 表示回数と"
             "照合して判定する。「3.5%%」のように %% が付いた値は指定にかかわらず百分率として扱う")
    parser.add_argument(
        "--include-regex", metavar="正規表現",
        help="キー列がこの正規表現に一致する行だけを使う（大文字・小文字を区別しない。全角・半角をそろえた値にも照合する）")
    parser.add_argument(
        "--exclude-regex", metavar="正規表現",
        help="キー列がこの正規表現に一致する行を除く。ブランド名クエリの除外などに使う（照合の仕方は --include-regex と同じ）")
    parser.add_argument(
        "-o", "--output", metavar="FILE",
        help="出力 CSV のパス。Excel 向けに UTF-8（BOM 付き）で書き、CSV インジェクション対策をする"
             "（--no-sanitize を参照）。省略すると標準出力に UTF-8（BOM なし）で、値を変えずに書く"
             "（' は付けない）。Excel で開くなら -o を使う。入力ファイルと同じパスは指定できない")
    parser.add_argument(
        "--top", type=int, default=0, metavar="N",
        help="上位 N 件だけを出力する（デフォルト: 0 = 全件）")
    parser.add_argument(
        "--no-sanitize", dest="sanitize", action="store_false",
        help="-o のファイルの CSV インジェクション対策を無効にする。既定では -o のファイルで、"
             "query / page 列の先頭が「=」「+」「-」「@」（またはタブ・CR）のセルの前に ' を付ける"
             "（標準出力には付けない）。「-」で始まる正当なクエリ（例:「-20度 寝袋」）にも付くので、"
             "-o のファイルを pandas などで読むときは先頭の ' を除くか、このオプションで出し直す。"
             "数値の列は変えない")


def validate_common_args(args):
    if args.top < 0:
        raise InputError("--top には 0 以上の整数を指定してください。")


