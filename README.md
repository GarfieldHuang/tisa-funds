# TISA 基金查找

把基富通的 [TISA 專案基金](https://www.fundrich.com.tw/themeFund/promotionDetail?type=root.TISA.FundList_Web)整理成可以搜尋、篩選的靜態網頁，部署在 GitHub Pages。

- 常見分類：台股指數型／大型股／高股息／中小型、全球股票、目標日期、股債平衡（積極／穩健／保守）、債券等
- 每檔基金標出可對照的 ETF：追蹤同一指數、範圍相近、或自組參考
- 單筆與定期定額績效、風險等級、夏普值、規模
- 篩選條件會寫進網址 `#`，可以直接分享

## 自動更新

`.github/workflows/update.yml` 每天台灣時間 22:30 執行 `scripts/fetch_funds.py`，資料有變動才 commit `data/funds.json`，GitHub Pages 隨之重新部署。也可以在 Actions 頁手動按 *Run workflow*。

## 本機執行

```bash
python scripts/fetch_funds.py
```

```bash
python -m http.server 8000
```

只用 Python 標準函式庫，不用裝套件。

## 調整分類或 ETF 對照

都在 `scripts/classify.py`：`E` 是 ETF 清單，`classify()` 依晨星基金組別、投資區域與名稱關鍵字決定分類。改完重跑抓資料即可。

## 免責

資料來自基富通公開頁面，分類與 ETF 對照是推算的參考，不構成投資建議。
