async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function toNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function formatPct(value, digits = 2, signed = false) {
  const num = toNumber(value);
  if (num === null) return "-";
  return `${signed && num > 0 ? "+" : ""}${num.toFixed(digits)}%`;
}

function formatNumber(value, digits = 0) {
  const num = toNumber(value);
  if (num === null) return "-";
  return num.toLocaleString("zh-TW", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function pctClass(value) {
  const num = toNumber(value);
  if (num === null || num === 0) return "neutral";
  return num > 0 ? "up" : "down";
}

function signedClassFromLabel(label) {
  if (label === "新增") return "new";
  if (label === "加碼") return "up";
  if (label === "減碼") return "down";
  if (label === "刪除") return "muted-tone";
  return "neutral";
}

function setRoute(route, params = {}) {
  const url = new URL(window.location.href);
  url.searchParams.set("route", route);
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") {
      url.searchParams.delete(key);
    } else {
      url.searchParams.set(key, value);
    }
  });
  window.history.pushState({}, "", url);
  render();
}

function getRouteState() {
  const url = new URL(window.location.href);
  return {
    route: url.searchParams.get("route") || "active-etf-overview",
    code: url.searchParams.get("code") || "",
    tab: url.searchParams.get("tab") || "overview",
    snapshotDate: url.searchParams.get("date") || "",
  };
}

function renderOverviewCard(item) {
  const todayClass = pctClass(item.today_pct);
  return `
    <button class="etf-card" data-etf-code="${escapeHtml(item.code)}">
      <div class="etf-card-top">
        <div>
          <div class="card-code">${escapeHtml(item.code)}</div>
          <div class="card-name">${escapeHtml(item.name)}</div>
        </div>
        <div class="tag ${item.scope === "foreign" ? "tag-cyan" : "tag-violet"}">
          ${item.scope === "foreign" ? "全球持股" : "台股持股"}
        </div>
      </div>
      <div class="metric-row">
        <div class="metric-block">
          <div class="metric-label">最新持股日</div>
          <div class="metric-value sm">${escapeHtml(item.latest_snapshot_date || "-")}</div>
        </div>
        <div class="metric-block right">
          <div class="metric-label">最新異動筆數</div>
          <div class="metric-value sm">${formatNumber(item.change_count)}</div>
        </div>
      </div>
      <div class="etf-card-performance">
        <div class="perf-chip ${todayClass}">單日 ${formatPct(item.today_pct)}</div>
        <div class="perf-chip ${pctClass(item.week_pct)}">單週 ${formatPct(item.week_pct)}</div>
        <div class="perf-chip ${pctClass(item.month_pct)}">單月 ${formatPct(item.month_pct)}</div>
      </div>
      <div class="etf-card-footer">
        <span>規模 ${formatNumber(item.aum_100m, 1)} 億</span>
        <span>${escapeHtml(item.issuer || "-")}</span>
      </div>
    </button>
  `;
}

function renderTopSummary(payload) {
  return `
    <div class="summary-grid">
      <div class="summary-card">
        <div class="metric-label">更新時間</div>
        <div class="metric-value sm">${escapeHtml(payload.updated_at || "-")}</div>
        <div class="muted">最新市場日 ${escapeHtml(payload.latest_market_date || "-")}</div>
      </div>
      <div class="summary-card">
        <div class="metric-label">最大規模 ETF</div>
        <div class="metric-value sm">${escapeHtml(payload.largest_etf || "-")}</div>
        <div class="muted">${formatNumber(payload.largest_aum_100m, 1)} 億</div>
      </div>
      <div class="summary-card">
        <div class="metric-label">異動最多</div>
        <div class="metric-value sm">${escapeHtml(payload.busiest_etf || "-")}</div>
        <div class="muted">${formatNumber(payload.busiest_change_count)} 筆</div>
      </div>
      <div class="summary-card">
        <div class="metric-label">今日最強</div>
        <div class="metric-value sm">${escapeHtml(payload.strongest_today_etf || "-")}</div>
        <div class="muted ${pctClass(payload.strongest_today_pct)}">${formatPct(payload.strongest_today_pct)}</div>
      </div>
    </div>
  `;
}

async function renderOverview() {
  const app = document.getElementById("app");
  app.innerHTML = `<h3>主動 ETF 清單</h3><div class="muted">正在讀取資料...</div>`;
  const payload = await fetchJson("/api/active-etf/overview?top_n=20");
  app.innerHTML = `
    <div class="section-head">
      <div>
        <div class="eyebrow">Overview</div>
        <h3>主動 ETF 清單</h3>
      </div>
      <div class="muted">點卡片進入單一 ETF detail 頁</div>
    </div>
    ${renderTopSummary(payload)}
    <div class="grid overview-grid">
      ${payload.items.map(renderOverviewCard).join("")}
    </div>
  `;
  app.querySelectorAll("[data-etf-code]").forEach((node) => {
    node.addEventListener("click", () => {
      setRoute("active-etf-detail", {
        code: node.dataset.etfCode,
        tab: "overview",
        date: null,
      });
    });
  });
}

function renderDetailHeader(payload, state) {
  const overview = payload.overview || {};
  const tabs = [
    ["overview", "概覽"],
    ["holdings", "成分股"],
    ["changes", "持股變動"],
  ];
  return `
    <div class="detail-header">
      <div>
        <button id="backBtn" class="ghost-btn">返回清單</button>
        <div class="detail-title-row">
          <div class="detail-code">${escapeHtml(payload.code)}</div>
          <h3>${escapeHtml(payload.name)}</h3>
          <div class="tag ${overview.scope === "foreign" ? "tag-cyan" : "tag-violet"}">
            ${overview.scope === "foreign" ? "全球持股" : "台股持股"}
          </div>
        </div>
        <div class="muted">
          最新持股日 ${escapeHtml(overview.holdings_snapshot_date || "-")} ｜ 發行公司 ${escapeHtml(overview.issuer || "-")} ｜ 經理人 ${escapeHtml(overview.manager || "-")}
        </div>
      </div>
      <div class="detail-tabs">
        ${tabs.map(([key, label]) => `
          <button class="tab-btn ${state.tab === key ? "active" : ""}" data-tab="${key}">
            ${label}
          </button>
        `).join("")}
      </div>
    </div>
  `;
}

function renderMetricCard(label, value, note = "", tone = "") {
  return `
    <div class="summary-card ${tone}">
      <div class="metric-label">${label}</div>
      <div class="metric-value sm">${value}</div>
      ${note ? `<div class="muted">${note}</div>` : ""}
    </div>
  `;
}

function renderOverviewTab(payload) {
  const o = payload.overview || {};
  return `
    <div class="summary-grid">
      ${renderMetricCard("管理費", o.management_fee === null ? "-" : `${o.management_fee}%`, `保管費 ${o.custody_fee === null ? "-" : `${o.custody_fee}%`}`)}
      ${renderMetricCard("配息頻率", escapeHtml(o.dividend_frequency || "-"), escapeHtml(o.dividend_policy || "-"))}
      ${renderMetricCard("基金規模", `${formatNumber(o.aum_100m, 2)} 億`, `受益人 ${formatNumber(o.beneficiary_10k, 2)} 萬`)}
      ${renderMetricCard("追蹤指數", escapeHtml(o.tracking_index || o.management_style || "-"), escapeHtml(o.management_style || "主動管理"))}
      ${renderMetricCard("市價 / NAV", `${formatNumber(o.price, 2)} / ${formatNumber(o.nav, 2)}`, `溢價 ${formatPct(o.premium)}`)}
      ${renderMetricCard("成立日期", escapeHtml(o.launch_date || "-"), `持股檔數 ${formatNumber(o.holdings_count)}`)}
    </div>
    <div class="summary-grid perf-grid">
      ${renderMetricCard("近 1 年", formatPct(o.return_1y), "", pctClass(o.return_1y))}
      ${renderMetricCard("近 3 年", formatPct(o.return_3y), "", pctClass(o.return_3y))}
      ${renderMetricCard("近 5 年", formatPct(o.return_5y), "", pctClass(o.return_5y))}
      ${renderMetricCard("單日市價", formatPct(o.market_change_pct), "", pctClass(o.market_change_pct))}
    </div>
  `;
}

function renderHoldingCard(row) {
  return `
    <div class="holding-card">
      <div class="holding-card-top">
        <div class="card-code">${escapeHtml(row.code || "-")}</div>
        <div class="holding-weight">${formatPct(row.weight)}</div>
      </div>
      <div class="holding-name">${escapeHtml(row.name || "-")}</div>
      <div class="muted">${escapeHtml(row.industry || "-")}</div>
      <div class="muted" style="margin-top:8px;">持有股數 ${formatNumber(row.shares)} ｜ 估值 ${formatNumber(row.holding_amount_100m, 2)} 億</div>
    </div>
  `;
}

function renderIndustryBreakdown(rows) {
  if (!rows.length) return "";
  return `
    <div class="industry-stack">
      ${rows.slice(0, 8).map((row) => `
        <div class="industry-row">
          <div class="industry-row-left">
            <span class="industry-dot"></span>
            <span>${escapeHtml(row.industry || "未分類")}</span>
          </div>
          <div class="industry-row-right">
            <span>${formatNumber(row.company_count)} 檔</span>
            <span>${formatPct(row.industry_weight)}</span>
          </div>
        </div>
      `).join("")}
    </div>
  `;
}

function renderHoldingsTab(payload) {
  const holdings = payload.holdings || [];
  const breakdown = payload.industry_breakdown || [];
  return `
    <div class="section-head">
      <div>
        <div class="eyebrow">Holdings</div>
        <h4>成分股概覽</h4>
      </div>
      <div class="muted">先用前十大看主軸，再看產業分布</div>
    </div>
    <div class="grid holdings-grid">
      ${holdings.slice(0, 12).map(renderHoldingCard).join("")}
    </div>
    <div class="subpanel" style="margin-top:18px;">
      <div class="section-head">
        <div>
          <div class="eyebrow">Industry Mix</div>
          <h4>持股產業分布</h4>
        </div>
      </div>
      ${renderIndustryBreakdown(breakdown)}
    </div>
  `;
}

function renderTimelineCard(row, isActive) {
  const total =
    (toNumber(row.add_count) || 0) +
    (toNumber(row.increase_count) || 0) +
    (toNumber(row.decrease_count) || 0) +
    (toNumber(row.remove_count) || 0);
  const weekday = new Date(`${row.snapshot_date}T00:00:00`).toLocaleDateString("zh-TW", { weekday: "short" });
  const label = row.snapshot_date ? row.snapshot_date.slice(5).replace("-", "/") : "-";
  return `
    <button class="timeline-card ${isActive ? "active" : ""}" data-snapshot-date="${escapeHtml(row.snapshot_date)}">
      <div class="timeline-date">${label}</div>
      <div class="timeline-weekday">${weekday}</div>
      <div class="timeline-dots">
        ${(toNumber(row.add_count) || 0) > 0 ? '<span class="dot new"></span>' : ""}
        ${(toNumber(row.increase_count) || 0) > 0 ? '<span class="dot up"></span>' : ""}
        ${(toNumber(row.decrease_count) || 0) > 0 ? '<span class="dot down"></span>' : ""}
        ${(toNumber(row.remove_count) || 0) > 0 ? '<span class="dot neutral"></span>' : ""}
      </div>
      <div class="timeline-total">${total}</div>
    </button>
  `;
}

function renderChangeList(title, count, rows, tone) {
  if (!rows.length) {
    return `
      <div class="change-panel">
        <div class="change-panel-head ${tone}">
          <span>${title}</span>
          <span>${count}</span>
        </div>
        <div class="empty-state">這一天沒有相關變動。</div>
      </div>
    `;
  }
  return `
    <div class="change-panel">
      <div class="change-panel-head ${tone}">
        <span>${title}</span>
        <span>${count}</span>
      </div>
      <div class="change-list">
        ${rows.map((row) => `
          <div class="change-row">
            <div class="change-row-left">
              <div class="change-row-weight">${formatPct(row.new_weight)}</div>
              <div>
                <div class="change-row-name">${escapeHtml(row.stock_name || row.name || "-")}</div>
                <div class="muted">${escapeHtml(row.stock_code || row.code || "-")} ｜ ${escapeHtml(row.industry || "-")}</div>
              </div>
            </div>
            <div class="change-row-right ${signedClassFromLabel(row.change_label)}">
              <div>${escapeHtml(row.change_label || "-")}</div>
              <div>${formatNumber(row.shares_delta_lots, 1)} 張</div>
              <div>${formatPct(row.weight_delta, 2, true)}</div>
            </div>
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

function renderChangesTab(payload, historyRows, selectedDate, snapshotRows) {
  const summaryRow = historyRows.find((row) => row.snapshot_date === selectedDate) || historyRows[0] || {};
  const addRows = snapshotRows.filter((row) => ["新增", "加碼"].includes(row.change_label));
  const trimRows = snapshotRows.filter((row) => ["減碼", "刪除"].includes(row.change_label));

  return `
    <div class="section-head">
      <div>
        <div class="eyebrow">Changes</div>
        <h4>持股變動</h4>
      </div>
      <div class="muted">用可滑動的日期時間軸切換不同快照日，再往下看增減持股。</div>
    </div>

    <div class="timeline-shell">
      <div class="timeline-head">
        <span>每日變動時間軸</span>
        <span class="muted">新增 / 加碼 / 減碼 / 移出</span>
      </div>
      <div class="timeline-scroll">
        ${historyRows.map((row) => renderTimelineCard(row, row.snapshot_date === selectedDate)).join("")}
      </div>
    </div>

    <div class="date-range-grid">
      <div class="summary-card">
        <div class="metric-label">前次持股日</div>
        <div class="metric-value sm">${escapeHtml(summaryRow.from_date || "-")}</div>
      </div>
      <div class="summary-card">
        <div class="metric-label">本次持股日</div>
        <div class="metric-value sm">${escapeHtml(summaryRow.to_date || summaryRow.snapshot_date || "-")}</div>
      </div>
    </div>

    <div class="summary-grid">
      ${renderMetricCard("新增", formatNumber(summaryRow.add_count), "", "tone-new")}
      ${renderMetricCard("加碼", formatNumber(summaryRow.increase_count), "", "tone-up")}
      ${renderMetricCard("減碼", formatNumber(summaryRow.decrease_count), "", "tone-down")}
      ${renderMetricCard("移出", formatNumber(summaryRow.remove_count), "", "tone-neutral")}
    </div>

    <div class="changes-grid">
      ${renderChangeList("新增 / 加碼", addRows.length, addRows, "up")}
      ${renderChangeList("減碼 / 移出", trimRows.length, trimRows, "down")}
    </div>
  `;
}

async function loadChangesForDate(payload, selectedDate) {
  const currentDate = payload.change_summary?.to_date || payload.change_summary?.snapshot_date || "";
  if (!selectedDate || selectedDate === currentDate) {
    return payload.changes || [];
  }
  try {
    const historyPayload = await fetchJson(`/api/active-etf/${payload.code}/changes/${selectedDate}`);
    return historyPayload.items || [];
  } catch (error) {
    return [];
  }
}

async function renderDetail(code) {
  const state = getRouteState();
  const app = document.getElementById("app");
  app.innerHTML = `<h3>ETF Detail</h3><div class="muted">正在讀取 ${escapeHtml(code)} ...</div>`;

  const payload = await fetchJson(`/api/active-etf/${code}`);
  const historyRows = (payload.history_summary || []).slice().sort((a, b) => String(a.snapshot_date).localeCompare(String(b.snapshot_date)));
  const validDates = new Set(historyRows.map((row) => row.snapshot_date));
  const fallbackDate = historyRows[historyRows.length - 1]?.snapshot_date || payload.change_summary?.to_date || "";
  const selectedDate = validDates.has(state.snapshotDate) ? state.snapshotDate : fallbackDate;
  const snapshotRows = await loadChangesForDate(payload, selectedDate);

  let tabContent = "";
  if (state.tab === "holdings") {
    tabContent = renderHoldingsTab(payload);
  } else if (state.tab === "changes") {
    tabContent = renderChangesTab(payload, historyRows, selectedDate, snapshotRows);
  } else {
    tabContent = renderOverviewTab(payload);
  }

  app.innerHTML = `
    ${renderDetailHeader(payload, state)}
    <div class="detail-body">${tabContent}</div>
  `;

  document.getElementById("backBtn").addEventListener("click", () => {
    setRoute("active-etf-overview", { code: null, tab: null, date: null });
  });

  app.querySelectorAll("[data-tab]").forEach((node) => {
    node.addEventListener("click", () => {
      setRoute("active-etf-detail", {
        code: payload.code,
        tab: node.dataset.tab,
        date: state.tab === "changes" ? selectedDate : state.snapshotDate || null,
      });
    });
  });

  app.querySelectorAll("[data-snapshot-date]").forEach((node) => {
    node.addEventListener("click", () => {
      setRoute("active-etf-detail", {
        code: payload.code,
        tab: "changes",
        date: node.dataset.snapshotDate,
      });
    });
  });
}

async function render() {
  const state = getRouteState();
  try {
    if (state.route === "active-etf-detail" && state.code) {
      await renderDetail(state.code);
    } else {
      await renderOverview();
    }
  } catch (error) {
    document.getElementById("app").innerHTML = `
      <h3>載入失敗</h3>
      <div class="muted">${escapeHtml(error.message)}</div>
    `;
  }
}

window.addEventListener("popstate", render);
render();
