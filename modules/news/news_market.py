import pandas as pd

from modules.industry.company_links_db import THEME_DEFINITIONS
from modules.data_sources.market_watch import load_recent_market_quotes
from modules.data_sources.price_cache import fetch_price_history
from modules.data_sources.revenue_data import build_revenue_momentum_rankings

from modules.news.news_common import attach_company_and_theme_links, attach_zh_translation, fetch_google_news, format_volume, get_industry_mapping, headline_keywords


def build_hot_industry_rankings(anchor_date, top_n=8):
    used_date, quotes_df = load_recent_market_quotes(anchor_date)
    if quotes_df.empty:
        return None

    industry_map_df = get_industry_mapping()
    merged_df = quotes_df.merge(industry_map_df, on="code", how="left")
    merged_df = merged_df[merged_df["industry"].fillna("") != ""].copy()
    if merged_df.empty:
        return None

    industry_summary_df = (
        merged_df.groupby("industry")
        .agg(
            stock_count=("code", "nunique"),
            total_volume=("volume", "sum"),
            avg_change_pct=("change_pct", "mean"),
            positive_count=("change_pct", lambda series: int((series > 0).sum())),
            limit_up_count=("limit_up", "sum"),
            locked_up_count=("locked_limit_up", "sum"),
            total_trades=("trades", "sum"),
        )
        .reset_index()
    )

    top_stock_rows = (
        merged_df.sort_values(["industry", "volume"], ascending=[True, False])
        .groupby("industry")
        .head(3)[["industry", "name", "code"]]
    )
    top_stock_map = (
        top_stock_rows.groupby("industry")
        .apply(lambda group: " / ".join(f"{row['name']}({row['code']})" for _, row in group.iterrows()))
        .to_dict()
    )
    industry_summary_df["代表股"] = industry_summary_df["industry"].map(top_stock_map)

    industry_summary_df["volume_rank"] = industry_summary_df["total_volume"].rank(pct=True)
    industry_summary_df["change_rank"] = industry_summary_df["avg_change_pct"].rank(pct=True)
    industry_summary_df["locked_rank"] = industry_summary_df["locked_up_count"].rank(pct=True)
    industry_summary_df["heat_score"] = (
        industry_summary_df["volume_rank"].fillna(0) * 45
        + industry_summary_df["change_rank"].fillna(0) * 35
        + industry_summary_df["locked_rank"].fillna(0) * 20
    )
    industry_summary_df = industry_summary_df.sort_values(
        ["heat_score", "total_volume", "avg_change_pct"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    display_df = industry_summary_df.head(top_n).copy()
    display_df["成交量"] = display_df["total_volume"].map(format_volume)
    display_df["平均漲跌幅(%)"] = display_df["avg_change_pct"].map(lambda value: f"{value:.2f}" if pd.notna(value) else "-")
    display_df["熱度分數"] = display_df["heat_score"].map(lambda value: f"{value:.1f}")
    display_df = display_df.rename(
        columns={
            "industry": "產業",
            "stock_count": "股票數",
            "positive_count": "上漲家數",
            "limit_up_count": "漲停家數",
            "locked_up_count": "鎖住漲停家數",
            "代表股": "代表股",
        }
    )[
        ["產業", "成交量", "平均漲跌幅(%)", "股票數", "上漲家數", "漲停家數", "鎖住漲停家數", "代表股", "熱度分數"]
    ]

    return {
        "used_date": used_date.strftime("%Y-%m-%d"),
        "industry_df": industry_summary_df,
        "display_df": display_df,
    }


def build_hot_theme_rankings(anchor_date, top_n=8, headlines_per_theme=3):
    used_date, quotes_df = load_recent_market_quotes(anchor_date)
    if quotes_df.empty:
        return None

    theme_rows = []
    theme_news_sections = []
    for definition in THEME_DEFINITIONS:
        theme_df = quotes_df[quotes_df["code"].isin(definition["codes"])].copy()
        if theme_df.empty:
            continue

        representative_df = theme_df.sort_values("volume", ascending=False).head(3)
        representative_text = " / ".join(
            f"{row['name']}({row['code']})" for _, row in representative_df.iterrows()
        )
        total_volume = float(theme_df["volume"].sum())
        avg_change_pct = float(theme_df["change_pct"].mean())
        limit_up_count = int(theme_df["limit_up"].sum())
        locked_up_count = int(theme_df["locked_limit_up"].sum())
        positive_count = int((theme_df["change_pct"] > 0).sum())

        theme_rows.append(
            {
                "theme": definition["theme"],
                "total_volume": total_volume,
                "avg_change_pct": avg_change_pct,
                "stock_count": int(theme_df["code"].nunique()),
                "positive_count": positive_count,
                "limit_up_count": limit_up_count,
                "locked_up_count": locked_up_count,
                "代表股": representative_text,
            }
        )

    if not theme_rows:
        return None

    theme_summary_df = pd.DataFrame(theme_rows)
    theme_summary_df["volume_rank"] = theme_summary_df["total_volume"].rank(pct=True)
    theme_summary_df["change_rank"] = theme_summary_df["avg_change_pct"].rank(pct=True)
    theme_summary_df["locked_rank"] = theme_summary_df["locked_up_count"].rank(pct=True)
    theme_summary_df["heat_score"] = (
        theme_summary_df["volume_rank"].fillna(0) * 45
        + theme_summary_df["change_rank"].fillna(0) * 35
        + theme_summary_df["locked_rank"].fillna(0) * 20
    )
    theme_summary_df = theme_summary_df.sort_values(
        ["heat_score", "total_volume", "avg_change_pct"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    display_df = theme_summary_df.head(top_n).copy()
    display_df["成交量"] = display_df["total_volume"].map(format_volume)
    display_df["平均漲跌幅(%)"] = display_df["avg_change_pct"].map(lambda value: f"{value:.2f}" if pd.notna(value) else "-")
    display_df["熱度分數"] = display_df["heat_score"].map(lambda value: f"{value:.1f}")
    display_df = display_df.rename(
        columns={
            "theme": "主題",
            "stock_count": "股票數",
            "positive_count": "上漲家數",
            "limit_up_count": "漲停家數",
            "locked_up_count": "鎖住漲停家數",
            "代表股": "代表股",
        }
    )[
        ["主題", "成交量", "平均漲跌幅(%)", "股票數", "上漲家數", "漲停家數", "鎖住漲停家數", "代表股", "熱度分數"]
    ]

    top_theme_names = theme_summary_df.head(top_n)["theme"].tolist()
    for theme_name in top_theme_names:
        definition = next((item for item in THEME_DEFINITIONS if item["theme"] == theme_name), None)
        if not definition:
            continue
        news_items = fetch_google_news(
            definition["news_query"],
            max_items=headlines_per_theme,
            anchor_date=anchor_date,
            days_back=7,
        )
        news_items = attach_company_and_theme_links(news_items)
        row = theme_summary_df[theme_summary_df["theme"] == theme_name].iloc[0]
        summary = (
            f"{theme_name} 今日成交量約 {row['total_volume']/1000:,.1f} 張，平均漲跌幅 {row['avg_change_pct']:.2f}%，"
            f"漲停 {int(row['limit_up_count'])} 檔、鎖住漲停 {int(row['locked_up_count'])} 檔；"
            f"代表股有 {row['代表股']}。"
        )
        theme_news_sections.append(
            {
                "theme": theme_name,
                "summary": summary,
                "news_items": news_items,
                "representative_stocks": row["代表股"],
            }
        )

    return {
        "used_date": used_date.strftime("%Y-%m-%d"),
        "theme_df": theme_summary_df,
        "display_df": display_df,
        "sections": theme_news_sections,
    }


def build_industry_overlap_signals(anchor_date, top_n=8):
    hot_result = build_hot_industry_rankings(anchor_date, top_n=top_n)
    revenue_result = build_revenue_momentum_rankings(top_n=50)
    if not hot_result or not revenue_result or revenue_result["top_df"].empty:
        return None

    hot_industry_df = hot_result["industry_df"][["industry", "heat_score", "total_volume", "avg_change_pct", "代表股"]].copy()
    revenue_top_df = revenue_result["top_df"][["industry", "code", "name_zh"]].copy()
    revenue_top_df = revenue_top_df[revenue_top_df["industry"].fillna("") != ""].copy()

    revenue_grouped_df = (
        revenue_top_df.groupby("industry")
        .agg(
            revenue_stock_count=("code", "count"),
            revenue_names=("name_zh", lambda series: " / ".join(series.head(4))),
        )
        .reset_index()
    )

    merged_df = hot_industry_df.merge(
        revenue_grouped_df,
        left_on="industry",
        right_on="industry",
        how="inner",
    )
    if merged_df.empty:
        return None

    merged_df["overlap_score"] = (
        merged_df["heat_score"].fillna(0) * 0.7
        + merged_df["revenue_stock_count"].fillna(0) * 6
        + merged_df["avg_change_pct"].clip(lower=-5, upper=5).fillna(0) * 2
    )
    merged_df = merged_df.sort_values(
        ["overlap_score", "heat_score", "revenue_stock_count"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    display_df = merged_df.head(top_n).copy()
    display_df["成交量"] = display_df["total_volume"].map(format_volume)
    display_df["平均漲跌幅(%)"] = display_df["avg_change_pct"].map(lambda value: f"{value:.2f}" if pd.notna(value) else "-")
    display_df["交集分數"] = display_df["overlap_score"].map(lambda value: f"{value:.1f}")
    display_df = display_df.rename(
        columns={
            "industry": "產業",
            "代表股": "量價代表股",
            "revenue_stock_count": "營收強勢股數",
            "revenue_names": "營收代表股",
        }
    )[
        ["產業", "成交量", "平均漲跌幅(%)", "量價代表股", "營收強勢股數", "營收代表股", "交集分數"]
    ]

    return {
        "used_date": hot_result["used_date"],
        "display_df": display_df,
    }


def _build_industry_narrative(industry_row, news_items):
    avg_change = industry_row.get("avg_change_pct", 0)
    volume = industry_row.get("total_volume", 0)
    limit_up_count = int(industry_row.get("limit_up_count", 0) or 0)
    locked_up_count = int(industry_row.get("locked_up_count", 0) or 0)
    industry_name = industry_row.get("industry", "未知產業")
    top_stocks = industry_row.get("代表股") or "暫無代表股"
    keywords = headline_keywords([item["title"] for item in news_items], top_n=3)

    if avg_change >= 3 or locked_up_count >= 2:
        tone = "資金明顯聚焦，短線熱度偏高"
    elif avg_change >= 1:
        tone = "量能與價格同步偏強，仍在升溫"
    elif avg_change >= 0:
        tone = "量能不差，但價格反應偏溫和"
    else:
        tone = "成交量高，但價格分歧，追價力道要再觀察"

    keyword_text = "、".join(keywords) if keywords else "題材仍在發酵"
    return (
        f"{industry_name} 今日成交量約 {volume/1000:,.1f} 張，平均漲跌幅 {avg_change:.2f}%，"
        f"漲停 {limit_up_count} 檔、鎖住漲停 {locked_up_count} 檔。{tone}。"
        f"代表股有 {top_stocks}；新聞焦點多集中在 {keyword_text}。"
    )


def build_industry_news_report(anchor_date, industry_count=5, headlines_per_industry=4):
    hot_result = build_hot_industry_rankings(anchor_date, top_n=industry_count)
    if not hot_result:
        return None

    industry_rows = hot_result["industry_df"].head(industry_count).copy()
    sections = []
    for _, row in industry_rows.iterrows():
        industry_name = row["industry"]
        query = f"台股 {industry_name}"
        news_items = fetch_google_news(
            query,
            max_items=headlines_per_industry,
            anchor_date=anchor_date,
            days_back=7,
        )
        news_items = attach_company_and_theme_links(news_items)
        sections.append(
            {
                "industry": industry_name,
                "summary": _build_industry_narrative(row, news_items),
                "news_items": news_items,
                "representative_stocks": row.get("代表股", ""),
                "avg_change_pct": row.get("avg_change_pct", 0),
                "total_volume": row.get("total_volume", 0),
            }
        )

    return {
        "used_date": hot_result["used_date"],
        "sections": sections,
        "hot_industry_df": hot_result["display_df"],
    }


def build_us_market_news_report(anchor_date, max_items=8):
    query_map = {
        "大盤": "US stocks OR S&P 500 OR Nasdaq OR Dow Jones market rally",
        "科技": "NVIDIA OR Microsoft OR Apple OR Amazon OR Meta OR AI stocks",
        "宏觀": "Federal Reserve OR Powell OR CPI OR inflation OR Treasury yields stocks",
    }

    bucket_items = {}
    all_titles = []
    merged_items = []
    seen_titles = set()

    for bucket_name, query in query_map.items():
        items = fetch_google_news(
            query,
            max_items=max_items,
            ceid="US:en",
            anchor_date=anchor_date,
            days_back=3,
        )
        items = attach_company_and_theme_links(attach_zh_translation(items))
        bucket_items[bucket_name] = items
        for item in items:
            all_titles.append(item.get("title_zh") or item["title"])
            if item["title"] not in seen_titles:
                seen_titles.add(item["title"])
                merged_items.append(item)

    merged_items = merged_items[:max_items]
    lead_clues = []
    for bucket_name, items in bucket_items.items():
        if items:
            lead_clues.append(f"{bucket_name}：{items[0].get('title_zh') or items[0]['title']}")

    if lead_clues:
        summary = "最近美股焦點主要落在大盤風險偏好、科技 / AI，以及聯準會與通膨三條線；" + "；".join(lead_clues[:3]) + "。"
    else:
        keywords = headline_keywords(all_titles, top_n=5)
        keyword_text = "、".join(keywords) if keywords else "大盤、科技與利率"
        summary = f"最近美股新聞主軸多圍繞 {keyword_text}，可先從大盤方向、科技龍頭與利率題材三條線一起看。"

    return {
        "summary": summary,
        "bucket_items": bucket_items,
        "merged_items": merged_items,
    }


def build_us_market_snapshot(anchor_date):
    _ = anchor_date
    symbols = {
        "S&P 500": "SPY",
        "Nasdaq 100": "QQQ",
        "Dow Jones": "DIA",
        "半導體": "SOXX",
    }
    records = []
    for label, symbol in symbols.items():
        history_df = fetch_price_history(symbol, mode="即時選股", history_buffer_days=30)
        if history_df.empty or len(history_df) < 6:
            continue

        close_series = history_df["Close"].dropna()
        latest_close = float(close_series.iloc[-1])
        one_day_change_pct = (latest_close / float(close_series.iloc[-2]) - 1) * 100 if len(close_series) >= 2 else None
        five_day_change_pct = (latest_close / float(close_series.iloc[-6]) - 1) * 100 if len(close_series) >= 6 else None
        records.append(
            {
                "指標": label,
                "symbol": symbol,
                "收盤": latest_close,
                "單日(%)": one_day_change_pct,
                "近5日(%)": five_day_change_pct,
            }
        )

    if not records:
        return None

    snapshot_df = pd.DataFrame(records)
    strongest_row = snapshot_df.sort_values("近5日(%)", ascending=False).iloc[0]
    weakest_row = snapshot_df.sort_values("近5日(%)", ascending=True).iloc[0]
    summary = (
        f"最近美股相對強的是 {strongest_row['指標']}，近 5 日 {strongest_row['近5日(%)']:.2f}% ；"
        f"相對弱的是 {weakest_row['指標']}，近 5 日 {weakest_row['近5日(%)']:.2f}%。"
    )
    return {
        "snapshot_df": snapshot_df,
        "summary": summary,
    }


def build_daily_news_brief(anchor_date, theme_news, industry_news, overlap_result, us_snapshot, us_news, mna_news=None, earnings_news=None, order_flow_news=None, company_focus_news=None):
    _ = anchor_date
    bullets = []

    if theme_news and theme_news.get("sections"):
        top_theme = theme_news["sections"][0]
        bullets.append(f"盤面最熱的細分主題是 {top_theme['theme']}，{top_theme['summary']}")

    if industry_news and industry_news.get("sections"):
        top_industry = industry_news["sections"][0]
        bullets.append(f"台股熱度最高的產業是 {top_industry['industry']}，{top_industry['summary']}")

    if overlap_result and not overlap_result["display_df"].empty:
        top_overlap = overlap_result["display_df"].iloc[0]
        bullets.append(
            f"量價與基本面交集最明顯的是 {top_overlap['產業']}，量價代表股有 {top_overlap['量價代表股']}，"
            f"營收強勢股則有 {top_overlap['營收代表股']}。"
        )

    if us_snapshot:
        bullets.append(us_snapshot["summary"])

    if us_news:
        bullets.append(us_news["summary"])

    if mna_news and mna_news.get("items"):
        lead_item = mna_news["items"][0]
        bullets.append(f"最近較值得注意的併購消息是「{lead_item.get('title_zh') or lead_item['title']}」。")

    if earnings_news and earnings_news.get("items"):
        lead_item = earnings_news["items"][0]
        bullets.append(f"最近較值得看的財報消息是「{lead_item.get('title_zh') or lead_item['title']}」。")

    if order_flow_news and order_flow_news.get("items"):
        lead_item = order_flow_news["items"][0]
        companies_text = "、".join(link["name_zh"] for link in lead_item.get("company_links", [])[:3]) or "台股供應鏈"
        bullets.append(f"美國大廠接單線索目前先看「{lead_item.get('title_zh') or lead_item['title']}」，對應公司有 {companies_text}。")

    if company_focus_news and company_focus_news.get("bullish_items"):
        lead_item = company_focus_news["bullish_items"][0]
        companies_text = "、".join(link["name_zh"] for link in lead_item.get("company_links", [])[:3]) or "相關公司"
        bullets.append(f"今日較突出的台股利多焦點是「{lead_item.get('title_zh') or lead_item['title']}」，可先看 {companies_text}。")

    return bullets
