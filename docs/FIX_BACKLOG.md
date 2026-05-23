# 修正清單

以下是目前專案最值得優先處理的修正項目，按照「先穩定、再加速、再搬前端」排序。

## P0 先穩定跑

1. `主站切頁不應重跑資料`
   - 首頁與主動 ETF 已經開始改成背景任務 + cache loader
   - 下一步是把相同模式擴到產業地圖、個股詳頁、研究頁常用資料

2. `所有內部導航都要留在同一個 app 分頁`
   - 已建立 `internal_nav.py`
   - 已改主動 ETF、產業地圖、個股入口
   - 下一步是把其他內部入口全部收斂到同一套 helper

3. `首頁不應因 fallback 同步重算而卡住`
   - 已移除最重的同步 fallback
   - 下一步要觀察還有哪些 background job 沒完成前會導致體感卡頓

## P1 資料快取與持久化

4. `首頁摘要需要落地快照`
   - 現在多數是 process cache
   - 建議補成 sqlite snapshot，避免重開服務後又重算

5. `主動 ETF 歷史快照要更完整`
   - 台股型 ETF 已能近 30 日
   - 全球型 ETF 目前受限於外部來源，只能補公開拿得到的日期
   - 需要再找第二資料源或做缺資料日期的 UI 表達

6. `產業地圖快照要延續現在的 snapshot 模式`
   - 現在方向正確
   - 下一步是讓更多題材 detail payload 直接讀 snapshot，而不是頁面內再組

## P2 前端遷移

7. `HTML beta 先完整搬主動 ETF`
   - `web_app/` 骨架已建立
   - 下一步搬 `主動ETF detail` 的三個主 tab

8. `產業地圖搬到 HTML`
   - 第二個搬運目標
   - 先搬 overview + detail + heatmap

9. `個股詳頁搬到 HTML`
   - 第三階段
   - 等 API 介面穩定後再搬

## P3 結構整理

10. `把頁面自管 query/session 更新逐步抽乾淨`
    - 避免每頁自己 patch `st.query_params`

11. `把共用資料 loader 集中到 ui_data / api 層`
    - 減少頁面直接碰底層抓資料函式

12. `把 run / deploy 指令標準化`
    - 已新增 `scripts/run_streamlit.sh`
    - 已新增 `scripts/run_web_beta.sh`
