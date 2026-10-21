"""從 MoneyDJ 抓台股 ETF 持股明細，輸出 data/etf_holdings.json。

ETF 持股一季內變動不大，這支每週跑一次就夠；分類時用它算「持股重疊度」。
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "etf_holdings.json"
URL = "https://www.moneydj.com/ETF/X/Basic/Basic0007a.xdjhtm?etfid={}.TW"

# 代號: (簡稱, 類型)  類型：passive＝被動指數、active＝主動式
CANDIDATES = {
    "0050": ("元大台灣50", "passive"),
    "006208": ("富邦台50", "passive"),
    "006204": ("永豐臺灣加權", "passive"),
    "0052": ("富邦科技", "passive"),
    "0051": ("元大中型100", "passive"),
    "00733": ("富邦臺灣中小", "passive"),
    "00935": ("野村臺灣新科技50", "passive"),
    "00881": ("國泰台灣科技龍頭", "passive"),
    "00891": ("中信關鍵半導體", "passive"),
    "0056": ("元大高股息", "passive"),
    "00878": ("國泰永續高股息", "passive"),
    "00919": ("群益台灣精選高息", "passive"),
    "00713": ("元大台灣高息低波", "passive"),
    "00929": ("復華台灣科技優息", "passive"),
    "00980A": ("主動野村臺灣優選", "active"),
    "00981A": ("主動統一台股增長", "active"),
    "00982A": ("主動群益台灣強棒", "active"),
    "00984A": ("主動安聯台灣高息", "active"),
    "00985A": ("主動野村台灣50", "active"),
    "00987A": ("主動台新優勢成長", "active"),
    "00991A": ("主動復華未來50", "active"),
    "00992A": ("主動群益科技創新", "active"),
    "00993A": ("主動安聯台灣", "active"),
    "00994A": ("主動第一金台股優", "active"),
    "00995A": ("主動中信台灣卓越", "active"),
    "00996A": ("主動兆豐台灣豐收", "active"),
    "00999A": ("主動野村臺灣高息", "active"),
    "00400A": ("主動國泰動能高息", "active"),
    "00401A": ("主動摩根台灣鑫收", "active"),
    "00403A": ("主動統一升級50", "active"),
    "00404A": ("主動聯博動能", "active"),
    "00405A": ("主動富邦台灣龍耀", "active"),
    "00406A": ("主動中信台灣收益", "active"),
    "00407A": ("主動凱基台灣", "active"),
    "00408A": ("主動第一金優股息", "active"),
    "00410A": ("主動永豐科技趨勢", "active"),
}


def text(page: str) -> str:
    page = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    page = re.sub(r"<[^>]+>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(page))


def holdings(code: str) -> dict | None:
    req = urllib.request.Request(URL.format(code), headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                t = text(r.read().decode("utf-8", "replace"))
            break
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                print(f"  {code}: {e}", file=sys.stderr)
                return None
            time.sleep(2)
    m = re.search(r"持股明細 資料日期：(\d{4}/\d\d/\d\d) 股票名稱 持股\(千股\) 比例 增減 (.*?)(?: 註|$)", t)
    if not m:
        print(f"  {code}: 找不到持股表", file=sys.stderr)
        return None
    rows = re.findall(r"(\S+?) [\d,]+\.\d+ ([\d.]+) [-+]?[\d.]+%", m.group(2))
    title = re.search(r"首頁 / ETF介紹 / 持股狀況 (\S+?)〈", t)
    return {"title": title.group(1) if title else "", "date": m.group(1), "holdings": {n: float(w) for n, w in rows}}


def main() -> None:
    with ThreadPoolExecutor(max_workers=4) as ex:
        got = dict(zip(CANDIDATES, ex.map(holdings, CANDIDATES)))
    out = {}
    for code, h in got.items():
        if h and h["holdings"]:
            name, kind = CANDIDATES[code]
            out[code] = {"name": h.pop("title") or name, "kind": kind, **h}
    if len(out) < len(CANDIDATES) * 0.7 and OUT.exists():
        print(f"只抓到 {len(out)}/{len(CANDIDATES)} 檔，保留舊的 {OUT.name}", file=sys.stderr)
        return
    payload = {"updatedAt": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="minutes"), "etfs": out}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT} ({len(out)}/{len(CANDIDATES)} ETFs)")


if __name__ == "__main__":
    main()
