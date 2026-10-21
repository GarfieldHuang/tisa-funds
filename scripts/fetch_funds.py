"""抓基富通 TISA 專案基金，輸出：

  data/funds.json          清單頁要用的欄位＋持股摘要（搜尋、篩選用）
  data/detail/{代碼}.json   基金頁六個分頁的完整資料（點「更多資料」才載入）

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
DETAIL = ROOT / "data" / "detail"
ETF_DB = ROOT / "data" / "etf_holdings.json"
TW = timezone(timedelta(hours=8))

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://www.fundrich.com.tw",
    "Referer": "https://www.fundrich.com.tw/",
    "User-Agent": "Mozilla/5.0 (tisa-funds daily sync; +https://github.com/GarfieldHuang/tisa-funds)",
}

PERIODS = ["threeMonths", "sixMonths", "sinceThisYear", "oneYear", "twoYears", "threeYears", "fiveYears", "tenYears", "sinceEstablished"]


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


def safe(path: str, data: dict):
    """明細欄位抓不到就給 None，不讓單一欄位拖垮整次更新。"""
    try:
        return post(path, data).get("data")
    except Exception as e:  # noqa: BLE001
        print(f"  {data.get('fundId')} {path}: {e}", file=sys.stderr)
        return None


def num(v):
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def signed(value, direction) -> float | None:
    """基富通的漲跌是「絕對值＋方向」，down 要轉成負數。"""
    v = num(value)
    if v is None:
        return None
    return -abs(v) if direction == "down" else v


def perf(row, key):
    v = row.get(key)
    return signed(v.get("value"), v.get("status")) if isinstance(v, dict) else None


# ---------- 清單 ----------

def fetch_list(extra: dict | None = None) -> list[dict]:
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


# ---------- 單檔明細（對應基金頁六個分頁） ----------

def _pairs(rows, key) -> list[list]:
    return [[r[key], num(r["percent"])] for r in rows or [] if num(r.get("percent"))]


def _rows(items) -> list[list[str]]:
    out = []
    for it in items or []:
        row = it.get("row")
        val = " ".join(x.strip() for x in row if x) if isinstance(row, list) else (row or "").strip()
        out.append([it["header"], " ".join(val.split())])
    return out


def fund_detail(fund_id: str) -> dict:
    q = {"fundId": fund_id}
    head = safe("GetFundDetail", q) or {}
    basic = _rows(safe("GetFundBasicInfo", q))
    buy = _rows(safe("GetFundBuyInfo", q))

    perf_raw = safe("GetFundPerformance", q) or {}
    performance = {}
    for row in (perf_raw.get("tableRowOriData") or [{}])[0].get("upDownType", []):
        key = "lump" if "單筆" in row["title"] else "rsp"
        performance[key] = {p: num(row.get(p, {}).get("rate")) for p in PERIODS}
    for row in (perf_raw.get("tableRow") or [{}])[0].get("percentType", []):
        performance["beat"] = {p: num(row.get(p, {}).get("win")) for p in PERIODS}
    performance["date"] = (perf_raw.get("date") or "").replace("資料日期：", "")

    rating_raw = safe("GetFundRating", q) or {}
    rating = {
        "date": rating_raw.get("date"),
        "rows": [[r["title"], r["oneYear"], r["threeYears"], r["fiveYears"], r["tenYears"]] for r in (rating_raw.get("ratingList") or [])[1:]],
        "risk": (rating_raw.get("risk") or {}).get("riskName"),
    }

    div_info = safe("GetFundDividendInfo", q) or {}
    div_hist = safe("GetFundDividendHistory", q) or {}
    dividend = {
        "frequency": (div_info.get("frequency") or {}).get("text"),
        "history": ((div_hist.get("tableRow") or {}).get("history")) or [],
    }

    days30 = [
        [r["date"], num(r["price"]), signed(r["upDownInfo"]["upDownPrice"], r["upDownInfo"]["upDown"]), signed(r["upDownInfo"]["upDownPercent"], r["upDownInfo"]["upDown"])]
        for r in ((safe("Get30DaysPrice", q) or {}).get("tableRow") or [])
    ]
    chart = ((safe("GetFundChart", {**q, "period": "5Y"}) or {}).get("tableRow") or {}).get("priceHistory") or []
    nav = [[r["date"], num(r["price"])] for r in reversed(chart) if num(r.get("price"))]

    port = {}
    for path, field, key, name in (
        ("GetFundInvestmentCategory", "categories", "category", "assets"),
        ("GetFundInvestmentCountry", "countries", "country", "countries"),
        ("GetFundInvestmentDuty", "dutys", "duty", "sectors"),
        ("GetFundShareholdingTop10", "investmentTargets", "investmentTarget", "top10"),
    ):
        d = safe(path, q) or {}
        port[name] = _pairs(d.get(field), key)
        if d.get("date") and "date" not in port:
            port["date"] = d["date"].replace("資料日期：", "")

    return {
        "id": fund_id,
        "eName": head.get("eName"),
        "riskName": head.get("riskName"),
        "basic": basic,
        "buy": buy,
        "performance": performance,
        "rating": rating,
        "dividend": dividend,
        "days30": days30,
        "nav": nav,
        "portfolio": port,
    }


def main() -> None:
    print("fetching list …")
    rows = fetch_list()
    print(f"  {len(rows)} funds")

    opts = filter_options()
    tisa_tag = tag_by_filter("tisa", opts.get("tisa", []))
    type_tag = tag_by_filter("type_n", opts.get("type_n", []))

    ids = [r["fundId"] for r in rows]
    print("fetching details …")
    with ThreadPoolExecutor(max_workers=5) as ex:
        details = dict(zip(ids, ex.map(fund_detail, ids)))

    etf_db = json.loads(ETF_DB.read_text(encoding="utf-8"))["etfs"] if ETF_DB.exists() else None

    DETAIL.mkdir(parents=True, exist_ok=True)
    funds = []
    for r in rows:
        fid = r["fundId"]
        d = details[fid]
        info = dict(d["basic"])
        perf_lump = d["performance"].get("lump", {})
        f = {
            "id": fid,
            "name": r["name"],
            "company": r.get("cpName") or info.get("基金公司", ""),
            "tisaType": tisa_tag.get(fid, ""),
            "fundType": type_tag.get(fid, ""),
            "msCategory": info.get("基金組別", ""),
            "region": info.get("投資區域", ""),
            "inception": r.get("beginningdate") or info.get("成立日期", ""),
            "risk": int(r["risk"]) if str(r.get("risk", "")).isdigit() else None,
            "morningstar": int(r["morningstar"]) if str(r.get("morningstar", "")).isdigit() and r["morningstar"] != "0" else None,
            "currency": r.get("currency"),
            "nav": num(r.get("price")),
            "navDate": r.get("transdate"),
            "change": perf(r, "updownrate"),
            "aum": num(r.get("assets")),
            "sharpe": num(r.get("sharpe")),
            "stdev1y": num(r.get("stdDev1Y")),
            "ret": {k: perf(r, k) for k in ("quarter", "half", "one", "two", "three", "five", "beginning")},
            "ytd": perf_lump.get("sinceThisYear"),
            "rsp": {k[3:]: perf(r, k) for k in ("rspone", "rsptwo", "rspthree", "rspfive")},
            "fee": dict(d["buy"]).get("基金管理費率(最高)"),
            "portfolio": d["portfolio"],
            "url": f"https://www.fundrich.com.tw/fundCenter/fundOverview/fundContent/{fid}",
        }
        f.update(classify({**f, "region": f["region"]}, etf_db))
        funds.append(f)
        (DETAIL / f"{fid}.json").write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # 下架的基金順手清掉明細檔
    for p in DETAIL.glob("*.json"):
        if p.stem not in details:
            p.unlink()

    payload = {
        "updatedAt": datetime.now(TW).isoformat(timespec="minutes"),
        "source": "基富通 TISA 專案基金",
        "etfHoldingsDate": next(iter(etf_db.values()))["date"] if etf_db else None,
        "funds": funds,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT} ({len(funds)} funds) + {len(funds)} detail files")


if __name__ == "__main__":
    main()
