#!/usr/bin/env python3
"""gsc-export-ja.zip を作り直す（架空の日本語 UI の Search Console のエクスポート）。

使い方: python3 build.py（このフォルダに gsc-export-ja.zip を書く）
本物のエクスポートと同じ形にそろえる: 最上位に CSV が 7 つ、名前は UTF-8 でフラグ 0x0808
（UTF-8 とデータ ディスクリプタ）、BOM なしの UTF-8、LF、最後の行に改行なし、CTR は「2.62%」の形。
ドメイン・URL・数値はすべて架空。
"""
import csv
import io
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = "https://example.jp"

# (パス, クリック数, 表示回数, 掲載順位)。low_ctr.py --key page で抽出されるのは
# dining-table（2.4 位）・wood-care（3.5 位）・kids-chair（4.8 位）と、--max-pos 10 なら oil-finish（7.2 位）
PAGES = [
    ("/", 400, 900, 1.1), ("/contact/", 40, 120, 1.2), ("/about/", 90, 300, 1.3), ("/shop/", 150, 500, 1.5),
    ("/products/walnut-shelf/", 100, 400, 1.8),
    ("/products/oak-bench/", 90, 600, 2.2), ("/products/dining-table/", 30, 1800, 2.4),
    ("/column/choose-wood/", 84, 700, 2.5), ("/products/cutting-board/", 70, 500, 2.7), ("/products/stool/", 33, 300, 2.9),
    ("/column/order-flow/", 30, 300, 3.1), ("/products/tv-board/", 36, 400, 3.2), ("/products/coat-hanger/", 20, 250, 3.4),
    ("/column/wood-care/", 26, 2600, 3.5), ("/column/workshop-tour/", 28, 350, 3.8),
    ("/products/desk/", 35, 500, 4.2), ("/news/exhibition/", 9, 150, 4.6), ("/products/kids-chair/", 9, 900, 4.8),
    ("/products/bookshelf/", 18, 300, 5.1), ("/column/maintenance-oil/", 24, 400, 5.5),
    ("/products/side-table/", 12, 300, 6.5), ("/products/tray/", 8, 200, 6.8), ("/column/oil-finish/", 5, 1200, 7.2),
    ("/column/tree-species/", 14, 400, 7.5), ("/news/holiday/", 4, 120, 7.9),
    ("/column/sanding/", 8, 400, 8.4), ("/news/recruit/", 2, 100, 8.8), ("/products/chair-cushion/", 5, 300, 9.1),
    ("/column/diy-shelf/", 9, 600, 9.8), ("/products/mirror/", 3, 200, 10.2),
    ("/column/finish-types/", 2, 350, 12.6), ("/products/lamp/", 1, 150, 14.3), ("/column/wood-grain/", 1, 280, 17.9),
]
QUERIES = [
    ("森ねずみ木工", 380, 820, 1.0), ("森ねずみ木工 評判", 45, 110, 1.4), ("無垢 棚 ウォールナット", 60, 380, 1.9),
    ("オーク ベンチ", 55, 520, 2.3), ("無垢 ダイニングテーブル", 20, 1300, 2.6), ("木 まな板 おすすめ", 50, 450, 2.8),
    ("木材 選び方 家具", 40, 500, 3.0), ("無垢材 手入れ", 12, 1900, 3.6), ("テレビボード 無垢", 25, 300, 3.3),
    ("オーダー家具 流れ", 20, 260, 3.9), ("学習机 無垢", 22, 380, 4.4), ("子供 椅子 木製", 6, 700, 5.0),
    ("本棚 無垢", 12, 240, 5.3), ("オイル 仕上げ 手入れ", 3, 900, 7.4), ("サイドテーブル 木", 9, 250, 6.6),
    ("木のトレイ", 6, 170, 6.9), ("樹種 違い", 10, 330, 7.7), ("紙やすり 番手 木工", 6, 300, 8.6),
    ("椅子 クッション 木", 4, 240, 9.3), ("棚 diy 無垢", 7, 480, 9.9), ("木枠 鏡", 2, 160, 10.4),
    ("木 仕上げ 種類", 1, 300, 12.9), ("木製 照明", 1, 130, 14.6), ("木目 種類", 1, 250, 18.2),
]


def table(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for key, clicks, impressions, position in rows:
        w.writerow([key, clicks, impressions, f"{clicks / impressions * 100:.2f}%".replace(".00%", "%"), position])
    return buf.getvalue().rstrip("\n").encode("utf-8")


class Unseekable(io.RawIOBase):
    """シークできない出力。zipfile はデータ ディスクリプタ（フラグ 0x08）付きで書く（本物のエクスポートと同じ）。"""

    def __init__(self):
        self.buf = io.BytesIO()

    def writable(self):
        return True

    def write(self, b):
        return self.buf.write(b)


def main():
    head = ["クリック数", "表示回数", "CTR", "掲載順位"]
    members = [
        ("平均読み込み時間のチャート.csv", "日付,クリック数,表示回数,CTR,掲載順位\n2026-09-24,21,610,3.44%,6.2\n2026-09-25,19,590,3.22%,6.4".encode()),
        ("クエリ.csv", table(["上位のクエリ"] + head, QUERIES)),
        ("ページ.csv", table(["上位のページ"] + head, [(SITE + p, c, i, pos) for p, c, i, pos in PAGES])),
        ("国.csv", "国,クリック数,表示回数,CTR,掲載順位\n日本,1593,17990,8.86%,5.1".encode()),
        ("デバイス.csv", "デバイス,クリック数,表示回数,CTR,掲載順位\nモバイル,1020,12100,8.43%,5.3\nPC,540,5500,9.82%,4.7\nタブレット,33,390,8.46%,5.6".encode()),
        ("検索での見え方.csv", "検索での見え方,クリック数,表示回数,CTR,掲載順位".encode()),
        ("フィルタ.csv", "フィルタ,値\n検索タイプ,ウェブ\n期間,過去 3 か月間".encode()),
    ]
    out = Unseekable()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members:
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 27, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    path = os.path.join(HERE, "gsc-export-ja.zip")
    with open(path, "wb") as f:
        f.write(out.buf.getvalue())
    with zipfile.ZipFile(path) as z:
        flags = {hex(i.flag_bits) for i in z.infolist()}
    print(f"{path}: {len(members)} 個、フラグ {sorted(flags)}")


if __name__ == "__main__":
    main()
