"""抓基富通 TISA 專案基金清單＋基本資料，輸出 data/funds.json。

只用標準函式庫，GitHub Actions 上不必裝任何套件。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from classify import classify  # noqa: E402

API = "https://apis.fundrich.com.tw/FRSDataCenter"
LIST_ID = "root.TISA.FundList_Web"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "funds.json"
TW = timezone(timedelta(hours=8))

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://www.fundrich.com.tw",
    "Referer": "https://www.fundrich.com.tw/",
    "User-Agent": "Mozilla/5.0 (tisa-funds daily sync; +https://github.com/GarfieldHuang/tisa-funds)",
}


def post(path: str, data: dict, retries: int = 3) -> dict:
    body = json.dumps({"data": data}).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(f"{API}/{path}", body, HEADERS, method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.loads(r.read().decode("utf-8"))
            if res.get("status") not in (0, None):
                raise RuntimeError(f"{path}: {res.get('msg')}")
            return res
        except Exception as e:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            print(f"  retry {path} ({e})", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    raise AssertionError


def fetch_list(extra: dict | None = None) -> list[dict]:
    """逐頁抓清單，回傳 tablebox 列。"""
    rows, page = [], 1
    while True:
        res = post("FundTableInfo", {"list": LIST_ID, "currentPage": page, "userstock": False, **(extra or {})})
        d = res["data"][0]
        box = d.get("tablebox") or []
        rows += box
        if not box or len(rows) >= d["resultCount"]:
            return rows
        page += 1


def filter_options() -> dict[str, list[tuple[str, str]]]:
    res = post("AdvancedFilters", {"type": LIST_ID})
    out = {}
    for grp in res["data"]:
        for c in grp["contents"]:
            out[c["id"]] = [(o["value"], o["name"]) for o in c.get("option", []) if o["value"] != "ALL"]
    return out


def tag_by_filter(key: str, options: list[tuple[str, str]]) -> dict[str, str]:
    """用網站自己的篩選器反查每檔基金屬於哪個選項。"""
    tags = {}
    for value, name in options:
        for row in fetch_list({key: [value]}):
            tags[row["fundId"]] = name
    return tags


def basic_info(fund_id: str) -> dict:
    res = post("GetFundBasicInfo", {"fundId": fund_id})
    info = {item["header"]: " ".join(x.strip() for x in item.get("row") or [] if x) for item in res["data"] or []}
    return info


def num(v):
    try:
        return float(str(v).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def perf(row, key):
    v = row.get(key)
    return num(v.get("value")) if isinstance(v, dict) else None


def main() -> None:
    print("fetching list …")
    rows = fetch_list()
    print(f"  {len(rows)} funds")

    opts = filter_options()
    tisa_tag = tag_by_filter("tisa", opts.get("tisa", []))
    type_tag = tag_by_filter("type_n", opts.get("type_n", []))
    print(f"  tagged tisa={len(tisa_tag)} type={len(type_tag)}")

    ids = [r["fundId"] for r in rows]
    with ThreadPoolExecutor(max_workers=6) as ex:
        infos = dict(zip(ids, ex.map(basic_info, ids)))

    funds = []
    for r in rows:
        fid = r["fundId"]
        info = infos.get(fid, {})
        f = {
            "id": fid,
            "name": r["name"],
            "company": r.get("cpName") or info.get("基金公司", ""),
            "tisaType": tisa_tag.get(fid, ""),
            "fundType": type_tag.get(fid, ""),
            "msCategory": info.get("基金組別", ""),
            "region": info.get("投資區域", ""),
            "fundKind": info.get("基金類型", ""),
            "isin": info.get("ISIN Code", ""),
            "inception": r.get("beginningdate") or info.get("成立日期", ""),
            "risk": int(r["risk"]) if str(r.get("risk", "")).isdigit() else None,
            "currency": r.get("currency"),
            "nav": num(r.get("price")),
            "navDate": r.get("transdate"),
            "change": perf(r, "updownrate"),
            "aum": num(r.get("assets")),
            "dividend": r.get("dividendrate"),
            "sharpe": num(r.get("sharpe")),
            "stdev1y": num(r.get("stdDev1Y")),
            "ret": {k: perf(r, k) for k in ("quarter", "half", "one", "two", "three", "five", "beginning")},
            "rsp": {k[3:]: perf(r, k) for k in ("rspone", "rsptwo", "rspthree", "rspfive")},
            "strategy": info.get("投資目標/策略", "")[:400],
            "url": f"https://www.fundrich.com.tw/fundCenter/fundOverview/fundContent/{fid}",
        }
        f.update(classify(f))
        funds.append(f)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updatedAt": datetime.now(TW).isoformat(timespec="minutes"), "source": "基富通 TISA 專案基金", "funds": funds}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT} ({len(funds)} funds)")


if __name__ == "__main__":
    main()
