"""把基金歸到投資人常用的分類，並配上可對照的 ETF。

分類以晨星的實際持股分析為主（資產類別、國家、產業、前十大持股），基金名稱只當輔助：
台股基金裡不少名字有「中國」「高股息」，實際持股卻是台股科技成長股。

ETF 對照分四級：
  same     — 追蹤同一指數（ETF 連結基金、指數基金）
  close    — 持股高度重疊（台股：前十大持股重疊 ≥ 70%）或投資範圍相同
  partial  — 部分相似（台股：重疊 40–70%）
  diy      — 沒有單一 ETF 能對上，給可以自己組合的參考

台股基金的重疊度＝Σ min(基金前十大持股權重, ETF 對同一檔股票的權重) ÷ 基金前十大權重合計。
ETF 持股由 etf_holdings.py 從 MoneyDJ 抓，只用來算重疊度，不顯示在網頁上。
"""
from __future__ import annotations

import re

# 非台股 ETF（台股 ETF 名稱直接取自 etf_holdings.json）
E = {
    "0050": ("元大台灣50", "TW"),
    "006208": ("富邦台50", "TW"),
    "006204": ("永豐臺灣加權", "TW"),
    "0056": ("元大高股息", "TW"),
    "00878": ("國泰永續高股息", "TW"),
    "00646": ("元大S&P500", "TW"),
    "00830": ("國泰費城半導體", "TW"),
    "00712": ("復華富時不動產", "TW"),
    "00720B": ("元大投資級公司債", "TW"),
    "00751B": ("元大AAA至A公司債", "TW"),
    "VT": ("Vanguard 全世界股票", "US"),
    "ACWI": ("iShares MSCI ACWI", "US"),
    "VYM": ("Vanguard 美國高股息", "US"),
    "VYMI": ("Vanguard 國際高股息", "US"),
    "QQQ": ("Invesco 那斯達克100", "US"),
    "VGT": ("Vanguard 資訊科技", "US"),
    "SOXX": ("iShares 半導體", "US"),
    "VNQ": ("Vanguard 美國不動產 REITs", "US"),
    "AOA": ("iShares 積極配置 80/20", "US"),
    "AOR": ("iShares 成長配置 60/40", "US"),
    "AOM": ("iShares 穩健配置 40/60", "US"),
    "AOK": ("iShares 保守配置 30/70", "US"),
    "BND": ("Vanguard 美國總體債券", "US"),
    "BNDW": ("Vanguard 全世界債券", "US"),
    "LQD": ("iShares 投資級公司債", "US"),
    "VCIT": ("Vanguard 中期公司債", "US"),
    "EMB": ("iShares 新興市場美元債", "US"),
    "HYG": ("iShares 非投資等級公司債", "US"),
}

# 台股被動 ETF 中，屬於高股息策略的
DIVIDEND_ETFS = {"0056", "00878", "00919", "00713"}

# 股票比重 → 股債配置 ETF
ALLOCATION = [(75, "AOA"), (55, "AOR"), (35, "AOM"), (0, "AOK")]

FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def etf(code: str, match: str, note: str = "", overlap: float | None = None, names: dict | None = None) -> dict:
    if names and code in names:
        name, market = names[code], "TW"
    else:
        name, market = E[code]
    d = {"code": code, "name": name, "market": market, "match": match, "note": note}
    if overlap is not None:
        d["overlap"] = round(overlap)
    return d


def _has(name: str, *words: str) -> bool:
    return any(w in name for w in words)


def _pct(pairs: list, key: str) -> float:
    return dict(pairs or []).get(key, 0.0)


def overlap(top10: list, holdings: dict) -> float:
    total = sum(w for _, w in top10)
    if not total:
        return 0.0
    return sum(min(w, holdings.get(n, 0.0)) for n, w in top10) / total * 100


def allocation_etfs(equity: float, note: str = "", match: str = "close") -> list[dict]:
    """依股票比重挑最接近的兩檔 iShares 股債配置 ETF。"""
    targets = {"AOA": 80, "AOR": 60, "AOM": 40, "AOK": 30}
    ranked = sorted(targets, key=lambda c: abs(targets[c] - equity))[:2]
    return [etf(c, match, note if i == 0 else "") for i, c in enumerate(ranked)]


def taiwan_etf_matches(top10: list, etf_db: dict) -> tuple[list[dict], float]:
    names = {c: e["name"] for c, e in etf_db.items()}
    scores = sorted(((overlap(top10, e["holdings"]), c) for c, e in etf_db.items()), reverse=True)
    level = lambda s: "close" if s >= 70 else "partial" if s >= 40 else "diy"
    active = [(s, c) for s, c in scores if c.endswith("A")][:2]
    passive = [(s, c) for s, c in scores if not c.endswith("A")][:1]
    out = [etf(c, level(s), "主動式 ETF", s, names) for s, c in active if s >= 40]
    out += [etf(c, level(s), "被動指數 ETF", s, names) for s, c in passive]
    div = max((s for s, c in scores if c in DIVIDEND_ETFS), default=0.0)
    return out, div


def classify(f: dict, etf_db: dict | None = None) -> dict:
    name, cat = f["name"], f["msCategory"]
    p = f.get("portfolio") or {}
    plain = re.sub(r"^【[^】]*】", "", name)
    plain = re.sub(r"[(（]原[:：].*?[)）]", "", plain).translate(FULLWIDTH_DIGITS)
    themed = plain.replace("中國信託", "")  # 投信名稱不算主題

    stock = _pct(p.get("assets"), "股票")
    conv = _pct(p.get("assets"), "可換股債券")
    bond = _pct(p.get("assets"), "債券")
    equity = stock + conv / 2  # 可轉債算半股半債
    tw = _pct(p.get("countries"), "台灣")
    cn = _pct(p.get("countries"), "中國") + _pct(p.get("countries"), "香港")
    tech = _pct(p.get("sectors"), "科技")
    reit = _pct(p.get("sectors"), "房地產")
    top10 = p.get("top10") or []
    taiwan = tw >= 80 or (not p.get("countries") and f["region"] == "台灣")

    tags, notes = [], []
    if _has(plain, "ETF連結", "股價指數"):
        tags.append("指數化")
    if "組合" in plain:
        tags.append("組合基金")
    if "多重資產" in plain:
        tags.append("多重資產")
    if _has(plain, "ESG", "永續"):
        tags.append("ESG／永續")
    if tech >= 80:
        tags.append(f"科技 {tech:.0f}%")
    if cn >= 3:
        tags.append(f"中國曝險 {cn:.0f}%")
    if _has(themed, "中國", "大三通", "中概") and cn < 3:
        tags.append("名稱有中國・實際以台股為主")
        notes.append(f"名稱是舊時代的中國題材，晨星持股分析顯示台灣 {tw:.0f}%、中國 {cn:.1f}%。")
    if reit >= 20:
        tags.append(f"REITs {reit:.0f}%")

    etfs: list[dict] = []

    if taiwan and stock >= 60 and not cat.startswith("新台幣"):
        if _has(plain, "台灣50", "卓越50"):
            group = "台股指數型"
            etfs = [etf("0050", "same", "本基金就是 0050 的連結基金"), etf("006208", "same", "同追蹤臺灣50指數，內扣費用較低")]
        elif "加權股價指數" in plain:
            group = "台股指數型"
            etfs = [etf("006204", "same", "同追蹤發行量加權股價指數"), etf("0050", "close", "前十大持股重疊 99%")]
        elif "高股息ETF連結" in plain:
            group = "台股指數型"
            etfs = [etf("0056", "same", "本基金就是 0056 的連結基金"), etf("00878", "partial")]
        else:
            matches, div = taiwan_etf_matches(top10, etf_db or {}) if etf_db else ([], 0.0)
            if div >= 35:
                group = "台股高股息"
                names = {c: e["name"] for c, e in (etf_db or {}).items()}
                ranked = sorted(((overlap(top10, etf_db[c]["holdings"]), c) for c in DIVIDEND_ETFS if c in etf_db), reverse=True)
                etfs = [etf(c, "close" if s >= 70 else "partial", "被動高股息 ETF", s, names) for s, c in ranked[:2]]
                etfs += [m for m in matches if m["code"].endswith("A")][:1]
            else:
                group = "台股主動型"
                etfs = matches
                if not any(m["code"].endswith("A") for m in matches):
                    notes.append("沒有持股重疊超過 40% 的主動式 ETF，選股風格比較獨特。")
                if _has(plain, "高股息", "股息"):
                    tags.append("名稱有股息・持股偏成長")
                    notes.append(f"持股與高股息 ETF（0056、00878、00919、00713）重疊最多只有 {div:.0f}%，實際是科技成長股組合。")
            if "中小" in cat:
                tags.append("晨星：中小型")
    elif taiwan:
        group = "台股平衡"
        if etf_db:
            matches, _ = taiwan_etf_matches(top10, etf_db)
            etfs = [dict(m, match="diy", note="股票部位參考") for m in matches[:1]]
        etfs.append(etf("00720B", "diy", f"債券部位參考；本基金股票約 {stock:.0f}%"))
    elif cat.startswith("目標期限"):
        group = "目標日期"
        yr = re.search(r"20[2-5]\d", plain)
        lead = f"目標 {yr.group()} 年，目前股票約 {equity:.0f}%" if yr else f"目前股票約 {equity:.0f}%"
        etfs = allocation_etfs(equity, lead + "；台灣沒有目標日期 ETF，越接近目標年越該往債券多的那檔移", "diy")
        if any("三倍" in n or "3X" in n.upper() for n, _ in top10):
            tags.append("含槓桿 ETF")
    elif cat in ("美元企業債券", "環球企業債券-美元對沖"):
        group = "投資級債券"
        maturities = [int(m) for n, _ in top10 for m in re.findall(r"\d\d/\d\d/(\d\d)\b", n)]
        long_dur = maturities and sum(maturities) / len(maturities) >= 33
        if long_dur:
            etfs = [etf("00720B", "close", "20 年以上投資級公司債"), etf("00751B", "close"), etf("LQD", "close")]
        else:
            etfs = [etf("VCIT", "close", "中期投資級公司債"), etf("LQD", "partial")]
    elif cat.startswith("環球債券"):
        group = "全球債券"
        hy = sum(w for n, w in top10 if _has(n, "非投資等級", "高收益", "前緣", "新興", "High Yield", "高入息"))
        if hy >= 30:
            etfs = [etf("EMB", "diy", f"前十大有約 {hy:.0f}% 是新興市場／非投資等級債基金"), etf("HYG", "diy"), etf("BNDW", "diy", "投資級部分")]
            tags.append("含非投資等級／新興債")
        elif hy >= 15:
            etfs = [etf("BNDW", "partial", "投資級部分"), etf("EMB", "diy", f"前十大約 {hy:.0f}% 是新興市場／非投資等級債"), etf("HYG", "diy")]
            tags.append("含非投資等級／新興債")
        else:
            etfs = [etf("BNDW", "close"), etf("BND", "partial")]
    elif cat == "環球股票收益":
        group = "全球股票收益"
        etfs = [etf("VYM", "close" if tech < 25 else "diy", "美股高股息"), etf("VYMI", "close" if tech < 25 else "diy", "美國以外高股息")]
        if tech >= 25:
            notes.append(f"科技占 {tech:.0f}%，比一般高股息 ETF（約 10–15%）高很多，ETF 只能近似。")
    elif stock >= 85 or cat.startswith("環球大型"):
        if tech >= 70:
            group = "全球科技"
            etfs = [etf("SOXX", "partial", "半導體"), etf("VGT", "partial", "美國資訊科技"), etf("00830", "partial", "台股可買的費城半導體")]
            if tw >= 20:
                notes.append(f"台股約 {tw:.0f}%，科技 {tech:.0f}%；ETF 只能近似。")
        elif reit >= 20:
            group = "全球股票"
            etfs = [etf("VNQ", "diy", f"REITs 約 {reit:.0f}%"), etf("QQQ", "diy", f"科技約 {tech:.0f}%"), etf("00712", "diy", "台股可買的 REITs ETF")]
        else:
            group = "全球股票"
            etfs = [etf("VT", "close"), etf("ACWI", "close"), etf("00646", "diy", "台股可買的美股大盤（只有美國）")]
    elif equity >= 65:
        group = "股債平衡-積極"
        etfs = allocation_etfs(equity, f"本基金股票約 {equity:.0f}%")
    elif equity >= 45:
        group = "股債平衡-穩健"
        etfs = allocation_etfs(equity, f"本基金股票約 {equity:.0f}%")
    else:
        group = "股債平衡-保守"
        etfs = allocation_etfs(equity, f"本基金股票約 {equity:.0f}%")
        if equity < 20:
            etfs.append(etf("BNDW", "diy", "股票很少，接近純債"))

    if group.startswith("股債平衡") and tech >= 65:
        notes.append(f"股票部位科技占 {tech:.0f}%，比配置型 ETF 集中，可再搭 QQQ 近似。")
        etfs.append(etf("QQQ", "diy", "科技部位"))

    return {
        "group": group,
        "tags": tags,
        "notes": notes,
        "etfs": etfs,
        "mix": {"stock": round(stock, 1), "bond": round(bond + conv, 1), "tw": round(tw, 1), "cn": round(cn, 1), "tech": round(tech, 1)},
    }
