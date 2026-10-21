"""把基金歸到投資人常用的分類，並配上可對照的 ETF。

分類依據：晨星「基金組別」＋「投資區域」＋基金名稱關鍵字。
ETF 對照分三級：
  same   — 追蹤同一指數（ETF 連結基金、指數基金）
  close  — 投資範圍／風格相近
  diy    — 沒有單一 ETF 能對上，給可以自己組合的參考
"""
from __future__ import annotations

import re

# 台灣上市 ETF（market="TW"）與美股 ETF（market="US"，需透過複委託）
E = {
    "0050": ("元大台灣50", "TW"),
    "006208": ("富邦台50", "TW"),
    "006204": ("永豐臺灣加權", "TW"),
    "0056": ("元大高股息", "TW"),
    "00878": ("國泰永續高股息", "TW"),
    "00919": ("群益台灣精選高息", "TW"),
    "0051": ("元大中型100", "TW"),
    "00733": ("富邦臺灣中小", "TW"),
    "00881": ("國泰台灣5G+", "TW"),
    "00646": ("元大S&P500", "TW"),
    "00720B": ("元大投資級公司債", "TW"),
    "00751B": ("元大AAA至A公司債", "TW"),
    "VT": ("Vanguard 全世界股票", "US"),
    "ACWI": ("iShares MSCI ACWI", "US"),
    "VYM": ("Vanguard 美國高股息", "US"),
    "VYMI": ("Vanguard 國際高股息", "US"),
    "AOA": ("iShares 積極配置 80/20", "US"),
    "AOR": ("iShares 成長配置 60/40", "US"),
    "AOM": ("iShares 穩健配置 40/60", "US"),
    "AOK": ("iShares 保守配置 30/70", "US"),
    "BND": ("Vanguard 美國總體債券", "US"),
    "BNDW": ("Vanguard 全世界債券", "US"),
    "LQD": ("iShares 投資級公司債", "US"),
    "VCIT": ("Vanguard 中期公司債", "US"),
}

FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def etf(code: str, match: str, note: str = "") -> dict:
    name, market = E[code]
    return {"code": code, "name": name, "market": market, "match": match, "note": note}


def _has(name: str, *words: str) -> bool:
    return any(w in name for w in words)


def classify(f: dict) -> dict:
    name, cat, region = f["name"], f["msCategory"], f["region"]
    # 拿掉【TISA級別】前綴與「(原：…)」舊名，避免關鍵字誤判
    plain = re.sub(r"^【[^】]*】", "", name)
    plain = re.sub(r"[(（]原[:：].*?[)）]", "", plain).translate(FULLWIDTH_DIGITS)

    tags = []
    if _has(plain, "ETF連結", "指數基金", "股價指數"):
        tags.append("指數化")
    if "組合" in plain:
        tags.append("組合基金")
    if "多重資產" in plain:
        tags.append("多重資產")
    if _has(plain, "高股息", "股息", "收益", "入息", "收息"):
        tags.append("收益導向")
    if _has(plain, "ESG", "永續"):
        tags.append("ESG／永續")
    if _has(plain, "AI", "科技", "創新"):
        tags.append("科技主題")
    if _has(plain, "中國", "大三通", "中概"):
        tags.append("中國題材")

    etfs: list[dict] = []

    if region == "台灣" and cat.startswith("台灣"):
        if _has(plain, "台灣50", "卓越50"):
            group = "台股指數型"
            etfs = [etf("0050", "same", "本基金就是 0050 的連結基金"), etf("006208", "same", "同追蹤臺灣50指數，內扣費用較低")]
        elif "加權股價指數" in plain:
            group = "台股指數型"
            etfs = [etf("006204", "same", "同追蹤發行量加權股價指數"), etf("0050", "close")]
        elif "高股息ETF連結" in plain:
            group = "台股指數型"
            etfs = [etf("0056", "same", "本基金就是 0056 的連結基金"), etf("00878", "close")]
        elif _has(plain, "高股息", "股息"):
            group = "台股高股息"
            etfs = [etf("0056", "close"), etf("00878", "close"), etf("00919", "close")]
        elif cat == "台灣大型股票":
            group = "台股大型股"
            etfs = [etf("0050", "close"), etf("006208", "close")]
        else:
            group = "台股中小型"
            etfs = [etf("0051", "close", "市值第 51～150 名"), etf("00733", "close", "中小型、因子選股")]
            if "科技主題" in tags:
                etfs.append(etf("00881", "close", "偏電子科技"))
    elif cat.startswith("目標期限"):
        group = "目標日期"
        yr = re.search(r"20[2-5]\d", plain)
        lead = f"目標 {yr.group()} 年；" if yr else ""
        etfs = [
            etf("VT", "diy", f"{lead}台灣沒有目標日期 ETF，離目標越遠股票比重越高"),
            etf("BND", "diy", "越接近目標年越提高債券比重"),
        ]
    elif cat == "環球股票收益":
        group = "全球股票收益"
        etfs = [etf("VYM", "diy", "美股高股息"), etf("VYMI", "diy", "美國以外高股息")]
    elif cat.startswith("環球大型"):
        group = "全球股票"
        etfs = [etf("VT", "close"), etf("ACWI", "close"), etf("00646", "diy", "台股可買到的美股大盤（只有美國）")]
    elif cat in ("美元企業債券", "環球企業債券-美元對沖"):
        group = "投資級債券"
        etfs = [etf("00720B", "close"), etf("00751B", "close"), etf("LQD", "close"), etf("VCIT", "close")]
    elif cat.startswith("環球債券"):
        group = "全球債券"
        etfs = [etf("BNDW", "close"), etf("BND", "close")]
    elif "股債混合" in cat:
        if region == "台灣":
            group = "台股平衡"
            etfs = [etf("0050", "diy", "股票部位"), etf("00720B", "diy", "債券部位")]
        elif "進取" in cat:
            group = "股債平衡-積極"
            etfs = [etf("AOA", "close", "股 80／債 20"), etf("AOR", "close", "股 60／債 40")]
        elif "保守" in cat:
            group = "股債平衡-保守"
            etfs = [etf("AOK", "close", "股 30／債 70"), etf("AOM", "close", "股 40／債 60")]
        else:
            group = "股債平衡-穩健"
            etfs = [etf("AOR", "close", "股 60／債 40"), etf("AOM", "close", "股 40／債 60")]
    else:
        group = "其他"

    return {"group": group, "tags": tags, "etfs": etfs}
