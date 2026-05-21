import altair as alt
import pandas as pd
import streamlit as st

from modules.data_sources.price_cache import fetch_price_history


def _param_value(params, field_name, default=None):
    if isinstance(params, dict):
        return params.get(field_name, default)
    return getattr(params, field_name, default)


def build_buy_context(trade, selected_strategies):
    contexts = []
    strategy_labels = {
        "VCP 收斂突破": "VCP",
    }
    for strategy_name in selected_strategies:
        label = strategy_labels.get(strategy_name)
        if label:
            contexts.append(label)

    if trade.get("buy_rs_spread_pct") is not None:
        contexts.append(f"RS +{trade['buy_rs_spread_pct']:.2f}%")
    if trade.get("w_support_price") is not None:
        contexts.append(f"W支撐 {trade['w_support_price']:.2f}")
    if trade.get("gap_support_price") is not None:
        contexts.append(f"缺口支撐 {trade['gap_support_price']:.2f}")

    return "｜".join(contexts) if contexts else "符合所選買入條件"


def _build_trade_event_rows(trades, selected_strategies):
    rows = []
    for index, trade in enumerate(trades, start=1):
        buy_context = build_buy_context(trade, selected_strategies)
        rows.append(
            {
                "trade_index": index,
                "Date": pd.to_datetime(trade["buy_date"]),
                "Price": float(trade["buy_price"]),
                "Event": "買入",
                "Reason": buy_context,
                "ReturnPct": float(trade["return_pct"]),
            }
        )
        rows.append(
            {
                "trade_index": index,
                "Date": pd.to_datetime(trade["sell_date"]),
                "Price": float(trade["sell_price"]),
                "Event": "賣出",
                "Reason": trade["reason"],
                "ReturnPct": float(trade["return_pct"]),
            }
        )
    return pd.DataFrame(rows)


def _build_trade_level_rows(trade):
    start_date = pd.to_datetime(trade["buy_date"])
    end_date = pd.to_datetime(trade["sell_date"])
    level_specs = [
        ("W支撐", trade.get("w_support_price")),
        ("W停損", trade.get("w_stop_price")),
        ("W目標", trade.get("w_target_price")),
        ("缺口支撐", trade.get("gap_support_price")),
        ("缺口停損", trade.get("gap_stop_price")),
    ]

    rows = []
    for label, value in level_specs:
        if value is None:
            continue
        rows.append(
            {
                "TradeLine": f"{label}-{start_date:%Y%m%d}-{end_date:%Y%m%d}",
                "LineLabel": label,
                "Date": start_date,
                "Value": float(value),
            }
        )
        rows.append(
            {
                "TradeLine": f"{label}-{start_date:%Y%m%d}-{end_date:%Y%m%d}",
                "LineLabel": label,
                "Date": end_date,
                "Value": float(value),
            }
        )
    return pd.DataFrame(rows)


def _slice_trade_window(history_df, trade, bars_before=18, bars_after=10):
    if history_df.empty:
        return history_df

    buy_ts = pd.to_datetime(trade["buy_date"])
    sell_ts = pd.to_datetime(trade["sell_date"])
    index = history_df.index
    buy_loc = max(index.searchsorted(buy_ts) - bars_before, 0)
    sell_loc = min(index.searchsorted(sell_ts, side="right") + bars_after, len(index))
    return history_df.iloc[buy_loc:sell_loc].copy()


def _prepare_chart_df(history_df):
    if history_df.empty:
        return history_df

    chart_df = history_df.reset_index().rename(columns={"index": "Date"}).copy()
    chart_df["Date"] = pd.to_datetime(chart_df["Date"])
    chart_df["DateLabel"] = chart_df["Date"].dt.strftime("%Y-%m-%d")
    chart_df["DateSort"] = chart_df["Date"].astype("int64")
    chart_df["CandleColor"] = chart_df.apply(
        lambda row: "#dc2626" if row["Close"] >= row["Open"] else "#16a34a",
        axis=1,
    )

    close = chart_df["Close"].astype("float64")
    for window in (5, 20, 60, 120, 240):
        column_name = f"MA{window}"
        if column_name not in chart_df.columns:
            chart_df[column_name] = close.rolling(window=window).mean()
    chart_df["VolMA20"] = chart_df["Volume"].astype("float64").rolling(window=20).mean()

    if "RSI14" not in chart_df.columns:
        delta = close.diff()
        gains = delta.clip(lower=0)
        losses = (-delta).clip(lower=0)
        avg_gain = gains.rolling(window=14, min_periods=14).mean()
        avg_loss = losses.rolling(window=14, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, pd.NA)
        chart_df["RSI14"] = 100 - (100 / (1 + rs))

    if not {"MACD", "MACDSignal", "MACDHist"} <= set(chart_df.columns):
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        chart_df["MACD"] = ema12 - ema26
        chart_df["MACDSignal"] = chart_df["MACD"].ewm(span=9, adjust=False).mean()
        chart_df["MACDHist"] = chart_df["MACD"] - chart_df["MACDSignal"]

    chart_df["BBMiddle"] = close.rolling(window=20).mean()
    bb_std = close.rolling(window=20).std()
    chart_df["BBUpper"] = chart_df["BBMiddle"] + (bb_std * 2)
    chart_df["BBLower"] = chart_df["BBMiddle"] - (bb_std * 2)
    return chart_df


def _style_composite_chart(chart):
    return (
        chart.configure_view(strokeOpacity=0)
        .configure_axis(
            gridColor="#e2e8f0",
            gridOpacity=0.55,
            domainColor="#cbd5e1",
            tickColor="#cbd5e1",
            labelColor="#475569",
            titleColor="#334155",
            labelFontSize=11,
            titleFontSize=11,
        )
        .configure_legend(
            orient="top",
            titleColor="#334155",
            labelColor="#475569",
            symbolStrokeWidth=2,
        )
    )


def _render_centered_chart(chart, *, width_ratio=(0.04, 0.89, 0.07)):
    left_col, chart_col, right_col = st.columns(width_ratio)
    with chart_col:
        st.altair_chart(chart, use_container_width=True)


def _pick_bar_size(point_count, *, minimum=2, maximum=7):
    if point_count <= 0:
        return maximum
    if point_count >= 320:
        return minimum
    if point_count >= 240:
        return max(minimum, maximum - 4)
    if point_count >= 160:
        return max(minimum, maximum - 3)
    if point_count >= 100:
        return max(minimum, maximum - 2)
    if point_count >= 60:
        return max(minimum, maximum - 1)
    return maximum


def _build_discrete_x_axis(*, show_axis):
    return alt.X(
        "DateLabel:N",
        sort=alt.SortField(field="DateSort", order="ascending"),
        axis=alt.Axis(
            title=None,
            labelAngle=0,
            grid=False,
            labels=show_axis,
            ticks=show_axis,
            domain=show_axis,
            labelColor="#64748b" if show_axis else None,
            tickColor="#cbd5e1" if show_axis else None,
            domainColor="#cbd5e1" if show_axis else None,
        ),
    )


def _build_indicator_panel(chart_df, sub_indicator, hover_selection=None):
    point_count = len(chart_df)
    base_x = _build_discrete_x_axis(show_axis=True)
    hover_rule = None
    if hover_selection is not None:
        hover_rule = alt.Chart(chart_df).mark_rule(
            color="#94a3b8",
            strokeWidth=0.9,
            opacity=0.75,
        ).encode(x=base_x).transform_filter(hover_selection)

    if sub_indicator == "RSI":
        rsi_chart = alt.Chart(chart_df).mark_line(color="#7c3aed", strokeWidth=1.8).encode(
            x=base_x,
            y=alt.Y("RSI14:Q", title="RSI", scale=alt.Scale(domain=[0, 100])),
            tooltip=[
                alt.Tooltip("Date:T", title="日期"),
                alt.Tooltip("RSI14:Q", title="RSI14", format=".2f"),
            ],
        )
        rsi_levels = pd.DataFrame({"Level": [30, 70]})
        rsi_rules = alt.Chart(rsi_levels).mark_rule(strokeDash=[5, 4], color="#94a3b8").encode(
            y="Level:Q"
        )
        layers = [rsi_chart, rsi_rules]
        if hover_selection is not None:
            hover_targets = alt.Chart(chart_df.dropna(subset=["RSI14"])).mark_point(
                opacity=0,
                size=90,
            ).encode(
                x=base_x,
                y="RSI14:Q",
            ).add_params(hover_selection)
            layers.extend([hover_targets, hover_rule])
        return alt.layer(*layers).properties(height=120)

    if sub_indicator == "MACD":
        zero_rule = alt.Chart(pd.DataFrame({"Level": [0]})).mark_rule(
            color="#94a3b8",
            strokeDash=[4, 4],
        ).encode(y="Level:Q")
        macd_bar = alt.Chart(chart_df).mark_bar(opacity=0.55).encode(
            x=base_x,
            y=alt.Y("MACDHist:Q", title="MACD"),
            color=alt.condition(
                alt.datum.MACDHist >= 0,
                alt.value("#dc2626"),
                alt.value("#16a34a"),
            ),
            tooltip=[
                alt.Tooltip("Date:T", title="日期"),
                alt.Tooltip("MACD:Q", title="MACD", format=".3f"),
                alt.Tooltip("MACDSignal:Q", title="Signal", format=".3f"),
                alt.Tooltip("MACDHist:Q", title="Hist", format=".3f"),
            ],
        )
        macd_lines = alt.Chart(chart_df).transform_fold(
            ["MACD", "MACDSignal"],
            as_=["LineLabel", "Value"],
        ).mark_line(strokeWidth=1.7).encode(
            x=base_x,
            y="Value:Q",
            color=alt.Color(
                "LineLabel:N",
                title="MACD",
                scale=alt.Scale(
                    domain=["MACD", "MACDSignal"],
                    range=["#0f172a", "#2563eb"],
                ),
            ),
        )
        layers = [zero_rule, macd_bar, macd_lines]
        if hover_selection is not None:
            hover_targets = alt.Chart(chart_df.dropna(subset=["MACDSignal"])).mark_point(
                opacity=0,
                size=90,
            ).encode(
                x=base_x,
                y="MACDSignal:Q",
            ).add_params(hover_selection)
            layers.extend([hover_targets, hover_rule])
        return alt.layer(*layers).properties(height=132)

    volume_bar = alt.Chart(chart_df).mark_bar(
        opacity=0.72,
        size=_pick_bar_size(point_count, minimum=2, maximum=9),
    ).encode(
        x=base_x,
        y=alt.Y("Volume:Q", title="成交量"),
        color=alt.Color("CandleColor:N", scale=None, legend=None),
        tooltip=[
            alt.Tooltip("Date:T", title="日期"),
            alt.Tooltip("Volume:Q", title="成交量", format=",.0f"),
            alt.Tooltip("VolMA20:Q", title="20日均量", format=",.0f"),
        ],
    )
    volume_ma = alt.Chart(chart_df.dropna(subset=["VolMA20"])).mark_line(
        color="#2563eb",
        strokeWidth=1.8,
    ).encode(
        x=base_x,
        y=alt.Y("VolMA20:Q", title="成交量"),
        tooltip=[
            alt.Tooltip("Date:T", title="日期"),
            alt.Tooltip("VolMA20:Q", title="20日均量", format=",.0f"),
        ],
    )
    layers = [volume_bar, volume_ma]
    if hover_selection is not None:
        hover_targets = alt.Chart(chart_df).mark_bar(
            opacity=0.001,
            size=max(8, _pick_bar_size(point_count, minimum=2, maximum=9) * 2),
        ).encode(
            x=base_x,
            y="Volume:Q",
        ).add_params(hover_selection)
        layers.extend([hover_targets, hover_rule])
    return alt.layer(*layers).properties(height=132)


def _build_volume_profile_df(chart_df, profile_bins):
    if chart_df.empty:
        return pd.DataFrame()

    min_price = float(chart_df["Low"].min())
    max_price = float(chart_df["High"].max())
    if pd.isna(min_price) or pd.isna(max_price):
        return pd.DataFrame()

    working_df = chart_df.copy()
    working_df["ProfilePrice"] = (
        working_df["High"].astype("float64")
        + working_df["Low"].astype("float64")
        + working_df["Close"].astype("float64")
    ) / 3
    working_df["Direction"] = working_df.apply(
        lambda row: "上漲量" if row["Close"] >= row["Open"] else "下跌量",
        axis=1,
    )
    working_df["DirectionOrder"] = working_df["Direction"].map({"上漲量": 0, "下跌量": 1})

    if min_price == max_price:
        grouped = working_df.groupby("Direction", as_index=False)["Volume"].sum()
        grouped["BinStart"] = min_price - 0.01
        grouped["BinEnd"] = max_price + 0.01
        grouped["PriceRange"] = f"{min_price:.2f} - {max_price:.2f}"
        grouped["DirectionOrder"] = grouped["Direction"].map({"上漲量": 0, "下跌量": 1})
        grouped["TotalVolume"] = grouped["Volume"].sum()
        grouped["BinMid"] = (grouped["BinStart"] + grouped["BinEnd"]) / 2
        grouped["IsPOC"] = True
        return grouped

    working_df["PriceBin"] = pd.cut(
        working_df["ProfilePrice"],
        bins=profile_bins,
        include_lowest=True,
        duplicates="drop",
    )
    grouped = (
        working_df.groupby(["PriceBin", "Direction", "DirectionOrder"], observed=False)["Volume"]
        .sum()
        .reset_index()
    )
    if grouped.empty:
        return grouped

    grouped["BinStart"] = grouped["PriceBin"].apply(lambda interval: float(interval.left)).astype("float64")
    grouped["BinEnd"] = grouped["PriceBin"].apply(lambda interval: float(interval.right)).astype("float64")
    grouped["PriceRange"] = grouped.apply(
        lambda row: f"{row['BinStart']:.2f} - {row['BinEnd']:.2f}",
        axis=1,
    )
    grouped["BinMid"] = (grouped["BinStart"] + grouped["BinEnd"]) / 2
    total_by_bin = (
        grouped.groupby(["BinStart", "BinEnd", "BinMid", "PriceRange"], as_index=False)["Volume"]
        .sum()
        .rename(columns={"Volume": "TotalVolume"})
    )
    grouped = grouped.merge(
        total_by_bin,
        on=["BinStart", "BinEnd", "BinMid", "PriceRange"],
        how="left",
    )
    max_total = grouped["TotalVolume"].max()
    grouped["IsPOC"] = grouped["TotalVolume"] == max_total
    return grouped


def _build_volume_profile_chart(chart_df, profile_bins, chart_height):
    profile_df = _build_volume_profile_df(chart_df, profile_bins)
    if profile_df.empty:
        return None
    max_total = float(profile_df["TotalVolume"].max() or 0)
    if max_total <= 0:
        return None

    base = alt.Chart(profile_df)
    poc_df = profile_df.loc[profile_df["IsPOC"]].drop_duplicates(subset=["BinStart", "BinEnd"])
    poc_band = alt.Chart(poc_df).mark_rect(
        color="#0f172a",
        opacity=0.08,
    ).encode(
        y=alt.Y(
            "BinStart:Q",
            title=None,
            axis=alt.Axis(labels=False, ticks=False, domain=False),
        ),
        y2="BinEnd:Q",
        x=alt.value(0),
        x2=alt.value(96),
        tooltip=[
            alt.Tooltip("PriceRange:N", title="POC 區間"),
            alt.Tooltip("TotalVolume:Q", title="總成交量", format=",.0f"),
        ],
    )
    profile_bars = base.mark_bar(
        size=12,
        cornerRadiusTopLeft=2,
        cornerRadiusBottomLeft=2,
        opacity=0.92,
    ).encode(
        y=alt.Y(
            "BinStart:Q",
            title=None,
            axis=alt.Axis(labels=False, ticks=False, domain=False),
        ),
        y2="BinEnd:Q",
        x=alt.X(
            "Volume:Q",
            title=None,
            stack="zero",
            scale=alt.Scale(domain=[max_total * 1.06, 0], nice=False),
            axis=alt.Axis(labels=False, ticks=False, domain=False, grid=False),
        ),
        order=alt.Order("DirectionOrder:Q"),
        color=alt.Color(
            "Direction:N",
            legend=None,
            scale=alt.Scale(
                domain=["上漲量", "下跌量"],
                range=["#67e8f9", "#f472b6"],
            ),
        ),
        tooltip=[
            alt.Tooltip("PriceRange:N", title="價格區間"),
            alt.Tooltip("Direction:N", title="成交類型"),
            alt.Tooltip("Volume:Q", title="成交量", format=",.0f"),
            alt.Tooltip("TotalVolume:Q", title="總成交量", format=",.0f"),
        ],
    )
    poc_outline = alt.Chart(poc_df).mark_rect(
        color="#0f172a",
        stroke="#0f172a",
        strokeWidth=1.2,
        opacity=0,
    ).encode(
        y="BinStart:Q",
        y2="BinEnd:Q",
        x=alt.value(0),
        x2=alt.value(96),
    )
    return alt.layer(poc_band, profile_bars, poc_outline).properties(
        width=96,
        height=chart_height,
    )


def _render_chart_controls(key_prefix, default_ma_windows=None):
    if default_ma_windows is None:
        default_ma_windows = [5, 20, 60]

    control_cols = st.columns([1.65, 1.1, 0.8, 0.95, 1.0])
    ma_windows = control_cols[0].multiselect(
        "均線",
        options=[5, 20, 60, 120, 240],
        default=default_ma_windows,
        key=f"{key_prefix}_ma_windows",
    )
    sub_indicator = control_cols[1].segmented_control(
        "副圖指標",
        options=["成交量", "RSI", "MACD"],
        default="成交量",
        key=f"{key_prefix}_sub_indicator",
        width="stretch",
    )
    show_bollinger = control_cols[2].toggle(
        "布林通道",
        value=False,
        key=f"{key_prefix}_show_bollinger",
    )
    show_volume_profile = control_cols[3].toggle(
        "顯示成交區間",
        value=False,
        key=f"{key_prefix}_show_volume_profile",
    )
    profile_bins = 24
    if show_volume_profile:
        profile_bins = control_cols[4].select_slider(
            "區間層數",
            options=[12, 16, 20, 24, 28, 32, 36, 40, 44, 48],
            value=24,
            key=f"{key_prefix}_profile_bins",
        )
    else:
        control_cols[4].caption("成交區間關閉")
    return sorted(ma_windows), sub_indicator, show_bollinger, show_volume_profile, profile_bins


def _build_candlestick_chart(
    history_df,
    event_df,
    *,
    level_df=None,
    chart_height=420,
    ma_windows=None,
    sub_indicator="成交量",
    show_bollinger=False,
    show_volume_profile=False,
    profile_bins=24,
):
    if history_df.empty:
        return None

    chart_df = _prepare_chart_df(history_df)
    if chart_df.empty:
        return None

    if ma_windows is None:
        ma_windows = [5, 20, 60]
    point_count = len(chart_df)
    x_hidden = _build_discrete_x_axis(show_axis=False)

    if level_df is not None and not level_df.empty:
        level_df = level_df.copy()
        level_df["Date"] = pd.to_datetime(level_df["Date"])
        level_df["DateLabel"] = level_df["Date"].dt.strftime("%Y-%m-%d")
        level_df["DateSort"] = level_df["Date"].astype("int64")

    if event_df is not None and not event_df.empty:
        event_df = event_df.copy()
        event_df["Date"] = pd.to_datetime(event_df["Date"])
        event_df["DateLabel"] = event_df["Date"].dt.strftime("%Y-%m-%d")
        event_df["DateSort"] = event_df["Date"].astype("int64")

    zoom_brush = alt.selection_interval(
        name="time_window",
        encodings=["x"],
    )
    hover_selection = alt.selection_point(
        name="chart_hover",
        fields=["DateLabel"],
        nearest=True,
        on="pointermove",
        empty=False,
        clear="pointerout",
    )

    base = alt.Chart(chart_df).encode(
        x=x_hidden,
    )

    wick = base.mark_rule().encode(
        y=alt.Y("Low:Q", title="價格"),
        y2="High:Q",
        color=alt.Color("CandleColor:N", scale=None, legend=None),
        tooltip=[
            alt.Tooltip("Date:T", title="日期"),
            alt.Tooltip("Open:Q", title="開盤", format=".2f"),
            alt.Tooltip("High:Q", title="最高", format=".2f"),
            alt.Tooltip("Low:Q", title="最低", format=".2f"),
            alt.Tooltip("Close:Q", title="收盤", format=".2f"),
            alt.Tooltip("Volume:Q", title="成交量", format=",.0f"),
        ],
    )
    hover_hitbox = base.mark_bar(
        size=max(18, _pick_bar_size(point_count, minimum=4, maximum=10) * 3),
        opacity=0.001,
        color="#0f172a",
    ).encode(
        y=alt.Y("Low:Q", title="價格"),
        y2="High:Q",
        tooltip=[
            alt.Tooltip("Date:T", title="日期"),
            alt.Tooltip("Open:Q", title="開盤", format=".2f"),
            alt.Tooltip("High:Q", title="最高", format=".2f"),
            alt.Tooltip("Low:Q", title="最低", format=".2f"),
            alt.Tooltip("Close:Q", title="收盤", format=".2f"),
            alt.Tooltip("Volume:Q", title="成交量", format=",.0f"),
        ],
    ).add_params(hover_selection)
    body = base.mark_bar(size=_pick_bar_size(point_count, minimum=4, maximum=10)).encode(
        y=alt.Y("Open:Q", title="價格"),
        y2="Close:Q",
        color=alt.Color("CandleColor:N", scale=None, legend=None),
    )

    ma_columns = [
        column_name
        for column_name in [f"MA{window}" for window in ma_windows]
        if column_name in chart_df.columns
    ]
    ma_chart = alt.Chart(chart_df).transform_fold(
        ma_columns,
        as_=["LineLabel", "Value"],
    ).mark_line(strokeWidth=1.6).encode(
        x=x_hidden,
        y="Value:Q",
        color=alt.Color(
            "LineLabel:N",
            title="均線",
            scale=alt.Scale(
                domain=["MA5", "MA20", "MA60", "MA120", "MA240"],
                range=["#f59e0b", "#2563eb", "#7c3aed", "#0f766e", "#be185d"],
            ),
        ),
    ) if ma_columns else None

    hover_rule = alt.Chart(chart_df).mark_rule(
        color="#94a3b8",
        strokeWidth=0.9,
        opacity=0.78,
    ).encode(
        x=x_hidden,
    ).transform_filter(hover_selection)

    layers = [hover_hitbox, wick, body, hover_rule]
    if ma_chart is not None:
        layers.append(ma_chart)

    if show_bollinger:
        bollinger_df = chart_df.dropna(subset=["BBUpper", "BBLower"]).copy()
        if not bollinger_df.empty:
            band_area = alt.Chart(bollinger_df).mark_area(
                color="#60a5fa",
                opacity=0.08,
            ).encode(
                x=x_hidden,
                y="BBLower:Q",
                y2="BBUpper:Q",
            )
            mid_line = alt.Chart(bollinger_df).mark_line(
                color="#2563eb",
                strokeWidth=1.35,
                opacity=0.9,
            ).encode(
                x=x_hidden,
                y="BBMiddle:Q",
                tooltip=[
                    alt.Tooltip("Date:T", title="日期"),
                    alt.Tooltip("BBUpper:Q", title="布林上軌", format=".2f"),
                    alt.Tooltip("BBMiddle:Q", title="布林中軌", format=".2f"),
                    alt.Tooltip("BBLower:Q", title="布林下軌", format=".2f"),
                ],
            )
            edge_lines = alt.Chart(bollinger_df).transform_fold(
                ["BBUpper", "BBLower"],
                as_=["BandEdge", "Value"],
            ).mark_line(
                color="#60a5fa",
                strokeWidth=0.9,
                opacity=0.5,
                strokeDash=[5, 4],
            ).encode(
                x=x_hidden,
                y="Value:Q",
                detail="BandEdge:N",
            )
            layers.extend([band_area, edge_lines, mid_line])

    if level_df is not None and not level_df.empty:
        level_chart = alt.Chart(level_df).mark_line(strokeDash=[6, 4], strokeWidth=1.4).encode(
            x=x_hidden,
            y="Value:Q",
            color=alt.Color(
                "LineLabel:N",
                title="結構線",
                scale=alt.Scale(
                    domain=["W支撐", "W停損", "W目標", "缺口支撐", "缺口停損"],
                    range=["#0f766e", "#ef4444", "#f59e0b", "#0369a1", "#be123c"],
                ),
            ),
            detail="TradeLine:N",
            tooltip=[
                alt.Tooltip("LineLabel:N", title="結構"),
                alt.Tooltip("Value:Q", title="價格", format=".2f"),
            ],
        )
        layers.append(level_chart)

    if event_df is not None and not event_df.empty:
        point_chart = alt.Chart(event_df).mark_point(filled=True, size=130).encode(
            x=x_hidden,
            y="Price:Q",
            color=alt.Color(
                "Event:N",
                scale=alt.Scale(domain=["買入", "賣出"], range=["#dc2626", "#16a34a"]),
                legend=alt.Legend(title="事件"),
            ),
            shape=alt.Shape(
                "Event:N",
                scale=alt.Scale(domain=["買入", "賣出"], range=["triangle", "diamond"]),
                legend=alt.Legend(title="事件"),
            ),
            tooltip=[
                alt.Tooltip("trade_index:Q", title="交易"),
                alt.Tooltip("Event:N", title="事件"),
                alt.Tooltip("Date:T", title="日期"),
                alt.Tooltip("Price:Q", title="價格", format=".2f"),
                alt.Tooltip("Reason:N", title="說明"),
                alt.Tooltip("ReturnPct:Q", title="淨報酬(%)", format=".2f"),
            ],
        )
        text_chart = alt.Chart(event_df).mark_text(
            dy=-14,
            fontSize=10,
            fontWeight="bold",
        ).encode(
            x=x_hidden,
            y="Price:Q",
            text="Event:N",
            color=alt.Color(
                "Event:N",
                scale=alt.Scale(domain=["買入", "賣出"], range=["#991b1b", "#166534"]),
                legend=None,
            ),
        )
        layers.extend([point_chart, text_chart])

    price_chart = alt.layer(*layers).properties(height=chart_height).transform_filter(zoom_brush)
    indicator_chart = _build_indicator_panel(
        chart_df,
        sub_indicator,
        hover_selection=hover_selection,
    ).transform_filter(zoom_brush)
    top_row = price_chart
    if show_volume_profile:
        volume_profile_chart = _build_volume_profile_chart(chart_df, profile_bins, chart_height)
        if volume_profile_chart is not None:
            top_row = alt.hconcat(
                price_chart,
                volume_profile_chart,
                spacing=8,
            ).resolve_scale(y="shared")
    navigator_chart = (
        alt.Chart(chart_df)
        .mark_area(color="#94a3b8", opacity=0.22, line={"color": "#475569", "strokeWidth": 1.1})
        .encode(
            x=_build_discrete_x_axis(show_axis=True),
            y=alt.Y("Close:Q", title=None, axis=None),
            tooltip=[
                alt.Tooltip("Date:T", title="日期"),
                alt.Tooltip("Close:Q", title="收盤", format=".2f"),
            ],
        )
        .properties(height=54)
        .add_params(zoom_brush)
    )
    navigator_rule = alt.Chart(chart_df).mark_rule(
        color="#64748b",
        strokeWidth=0.8,
        opacity=0.55,
    ).encode(
        x=_build_discrete_x_axis(show_axis=True),
    ).transform_filter(hover_selection)
    navigator_selectors = alt.Chart(chart_df).mark_point(
        opacity=0,
        size=75,
    ).encode(
        x=_build_discrete_x_axis(show_axis=True),
        y="Close:Q",
    ).add_params(hover_selection)
    navigator_chart = alt.layer(navigator_chart, navigator_rule, navigator_selectors)
    combined_chart = alt.vconcat(
        top_row,
        indicator_chart,
        navigator_chart,
        spacing=14,
    ).resolve_scale(x="shared")
    return _style_composite_chart(combined_chart)


def render_trade_reason_visuals(code, info, params, selected_strategies):
    if not info.get("trades"):
        return

    start_date = _param_value(params, "start_date")
    end_date = _param_value(params, "end_date")
    try:
        history_df = fetch_price_history(
            code,
            mode="歷史回測",
            start_date=start_date,
            end_date=end_date,
            history_buffer_days=120,
            include_indicators=True,
        )
    except Exception as exc:
        st.warning(f"K 線資料讀取失敗：{exc}")
        return
    if history_df.empty:
        st.caption("目前抓不到這檔股票的 K 線資料，先略過圖解。")
        return

    ma_windows, sub_indicator, show_bollinger, show_volume_profile, profile_bins = _render_chart_controls(
        f"trade_chart_{code}",
        default_ma_windows=[5, 20, 60],
    )
    event_df = _build_trade_event_rows(info["trades"], selected_strategies)
    st.write("**買賣點總覽**")
    st.caption("這張圖會把整段回測期間的 K 線、均線、成交量與所有買賣點放在一起。底下小圖可直接拖曳放大時間區間。")
    overview_chart = _build_candlestick_chart(
        history_df,
        event_df,
        level_df=None,
        chart_height=360,
        ma_windows=ma_windows,
        sub_indicator=sub_indicator,
        show_bollinger=show_bollinger,
        show_volume_profile=show_volume_profile,
        profile_bins=profile_bins,
    )
    if overview_chart is not None:
        _render_centered_chart(overview_chart)

    trade_options = [
        f"第 {index} 筆｜{trade['buy_date']} -> {trade['sell_date']}｜{trade['return_pct']:.2f}%｜{trade['reason']}"
        for index, trade in enumerate(info["trades"], start=1)
    ]
    selected_option = st.selectbox(
        "交易圖解",
        trade_options,
        key=f"trade_focus_{code}",
    )
    selected_index = trade_options.index(selected_option)
    focus_trade = info["trades"][selected_index]
    focus_df = _slice_trade_window(history_df, focus_trade)
    focus_event_df = event_df[event_df["trade_index"] == (selected_index + 1)].copy()
    level_df = _build_trade_level_rows(focus_trade)

    summary_cols = st.columns(4)
    summary_cols[0].metric("買入", f"{focus_trade['buy_date']} @ {focus_trade['buy_price']:.2f}")
    summary_cols[1].metric("賣出", f"{focus_trade['sell_date']} @ {focus_trade['sell_price']:.2f}")
    summary_cols[2].metric("淨報酬", f"{focus_trade['return_pct']:.2f}%")
    summary_cols[3].metric("平倉原因", focus_trade["reason"])
    st.caption(f"買入脈絡：{build_buy_context(focus_trade, selected_strategies)}")

    focus_chart = _build_candlestick_chart(
        focus_df,
        focus_event_df,
        level_df=level_df,
        chart_height=360,
        ma_windows=ma_windows,
        sub_indicator=sub_indicator,
        show_bollinger=show_bollinger,
        show_volume_profile=show_volume_profile,
        profile_bins=profile_bins,
    )
    if focus_chart is not None:
        _render_centered_chart(focus_chart)


def render_stock_detail_workspace(symbol, title, *, start_date, end_date, key_prefix):
    try:
        history_df = fetch_price_history(
            symbol,
            mode="歷史回測",
            start_date=start_date,
            end_date=end_date,
            history_buffer_days=260,
            include_indicators=True,
        )
    except Exception as exc:
        st.error(f"讀取 {title} 的 K 線資料失敗：{exc}")
        return

    if history_df.empty:
        st.warning("目前抓不到這檔股票的歷史價格資料。")
        return

    ma_windows, sub_indicator, show_bollinger, show_volume_profile, profile_bins = _render_chart_controls(
        f"{key_prefix}_{symbol}",
        default_ma_windows=[5, 20, 60, 120],
    )

    latest_close = float(history_df["Close"].iloc[-1])
    prev_close = float(history_df["Close"].iloc[-2]) if len(history_df) >= 2 else latest_close
    day_change_pct = ((latest_close / prev_close) - 1) * 100 if prev_close else 0.0
    chart_df = _prepare_chart_df(history_df)
    latest_rsi = chart_df["RSI14"].dropna().iloc[-1] if chart_df["RSI14"].notna().any() else None
    latest_macd = chart_df["MACD"].dropna().iloc[-1] if chart_df["MACD"].notna().any() else None

    metric_cols = st.columns(4)
    metric_cols[0].metric("最新收盤", f"{latest_close:.2f}")
    metric_cols[1].metric("單日變動", f"{day_change_pct:.2f}%")
    metric_cols[2].metric("RSI14", f"{latest_rsi:.2f}" if latest_rsi is not None else "資料不足")
    metric_cols[3].metric("MACD", f"{latest_macd:.3f}" if latest_macd is not None else "資料不足")

    detail_chart = _build_candlestick_chart(
        history_df,
        event_df=None,
        level_df=None,
        chart_height=420,
        ma_windows=ma_windows,
        sub_indicator=sub_indicator,
        show_bollinger=show_bollinger,
        show_volume_profile=show_volume_profile,
        profile_bins=profile_bins,
    )
    if detail_chart is not None:
        _render_centered_chart(detail_chart)
