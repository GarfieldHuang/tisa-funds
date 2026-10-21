# TISA 基金查找

把基富通的 [TISA 專案基金](https://www.fundrich.com.tw/themeFund/promotionDetail?type=root.TISA.FundList_Web)整理成可以搜尋、篩選的靜態網頁，部署在 GitHub Pages。

- **依實際持股分類**：用晨星的資產類別、國家、產業、前十大持股判斷，不只看基金名稱（例如「台新中國通」實際台灣 92%、中國 1.3%）
- **ETF 對照**：台股基金用「前十大持股重疊度」找最像的主動式／被動 ETF；其他類型依股票比重、債券種類對到配置型或債券 ETF
- **資產配置篩選**：股票比重、國家＋門檻、產業＋門檻、中國曝險；搜尋框可以打持股名稱（例如「台積電」）
- **更多資料**：對應基富通基金頁的六個分頁——基金總覽（含淨值走勢圖）、基金資料、績效/淨值、資產配置、風險評等、配息紀錄
- 篩選條件會寫進網址 `#`，可以直接分享

## 資料檔

| 檔案 | 內容 | 來源 |
|---|---|---|
| `data/funds.json` | 清單、分類、ETF 對照、持股摘要 | 基富通 API、晨星持股分析 |
| `data/detail/{代碼}.json` | 六個分頁的完整資料、5 年淨值 | 基富通 API |
| `data/etf_holdings.json` | 36 檔台股 ETF 持股（只用來算重疊度，不顯示） | MoneyDJ |

原始資料照來源呈現，不做修正或換算。

## 自動更新

`.github/workflows/update.yml` 每天台灣時間 22:30 先跑 `scripts/etf_holdings.py`，再跑 `scripts/fetch_funds.py`，資料有變動才 commit，GitHub Pages 隨之重新部署。也可以在 Actions 頁手動按 *Run workflow*。

## 本機執行

```bash
python scripts/etf_holdings.py
```

```bash
python scripts/fetch_funds.py
```

```bash
python -m http.server 8000
```

只用 Python 標準函式庫，不用裝套件。

## 調整分類或 ETF 對照

都在 `scripts/classify.py`；候選台股 ETF 清單在 `scripts/etf_holdings.py` 的 `CANDIDATES`。

## 免責

資料來自基富通、晨星與 MoneyDJ 公開頁面，分類與 ETF 對照是依持股推算的參考，不構成投資建議。
