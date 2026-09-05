"use strict";

const titles = {
  overview: "Visão geral",
  opportunities: "Oportunidades",
  contracts: "Contratos",
  suppliers: "Fornecedores",
  agencies: "Órgãos",
  expenses: "Execução financeira",
  people: "Credores pessoa física",
  quality: "Qualidade dos dados",
};

const exportsByView = {
  overview: "opportunities",
  opportunities: "opportunities",
  contracts: "contracts",
  suppliers: "market-intelligence",
  agencies: "agencies",
  expenses: "expenses",
  people: "person-creditors",
  quality: "opportunities",
};

const appState = {
  currentView: "overview",
  loaded: new Set(),
  pages: { opportunities: 1, contracts: 1, suppliers: 1, agencies: 1, expenses: 1, people: 1 },
};

const marketState = {
  q: "", city: "", district: "", market_sector: "", company_size: "",
  registration_status: "", map_coordinate: "",
};
let marketMapLabel = "";

const currency = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL", maximumFractionDigits: 2,
});
const compactCurrency = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL", notation: "compact", maximumFractionDigits: 1,
});
const integer = new Intl.NumberFormat("pt-BR");

if (window.Charts) {
  Charts.applyPalette({
    n0: "#ffffff", n0a: "#f3f6f3", n1: "#dce4e1", n2a: "#bec0be",
    n2: "#a4a7a4", n3: "#8b8d8b", n4: "#708087", n5: "#666666",
    n6: "#4d4d4d", n7: "#344b54", n8: "#10252d", n9: "#0b1f27",
    nInverse: "#ffffff", s1: "#10252d", s2: "#097e5d", s3: "#0f9770",
    s4: "#39ae86", s5: "#68c39f", s6: "#8ed7b9", s7: "#9ad4c6",
    accent: "#3b82f6", annotation: "#a43c43", counter: "#e99b25",
  });
}

function element(selector) { return document.querySelector(selector); }
function html(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}
function text(value, fallback = "Não informado") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}
function money(value, compact = false) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? (compact ? compactCurrency : currency).format(numeric) : "—";
}
function date(value) {
  if (!value) return "—";
  const [year, month, day] = String(value).slice(0, 10).split("-");
  return year && month && day ? `${day}/${month}/${year}` : "—";
}
function dateTime(value) {
  if (!value) return "Não informado";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? text(value) : parsed.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
function cnpj(value) {
  const digits = String(value ?? "").replace(/\D/g, "");
  return digits.length === 14 ? digits.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5") : text(value, "—");
}
function phone(value) {
  const digits = String(value ?? "").replace(/\D/g, "");
  if (digits.length === 11) return digits.replace(/^(\d{2})(\d{5})(\d{4})$/, "($1) $2-$3");
  if (digits.length === 10) return digits.replace(/^(\d{2})(\d{4})(\d{4})$/, "($1) $2-$3");
  return text(value, "—");
}
function normalized(value) {
  return String(value ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR");
}
function clipped(value, length = 105) {
  const clean = text(value);
  return clean.length > length ? `${clean.slice(0, length).trim()}…` : clean;
}
function statusClass(status) {
  const normalized = String(status ?? "").toUpperCase();
  if (normalized.includes("ANDAMENTO") || normalized.includes("VIGENTE") || normalized === "ATIVA") return "green";
  if (normalized.includes("PARALIS") || normalized.includes("TERMINANDO") || normalized.includes("PRORROG")) return "amber";
  if (normalized.includes("EXPIR") || normalized.includes("REVOG") || normalized.includes("FRACASS")) return "red";
  return "gray";
}
function badge(value) { return `<span class="badge ${statusClass(value)}">${html(text(value))}</span>`; }

async function api(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`A API respondeu ${response.status}`);
  return response.json();
}

let bannerTimer;
function showStatus(message, kind = "loading") {
  clearTimeout(bannerTimer);
  const banner = element("#status-banner");
  banner.className = `status-banner ${kind}`;
  element("#status-message").textContent = message;
  banner.querySelector(".spinner").style.display = kind === "loading" ? "inline-block" : "none";
  if (kind === "success") bannerTimer = setTimeout(() => { banner.className = "status-banner"; }, 2600);
}
function showError(error) {
  console.error(error);
  showStatus("Não foi possível consultar os dados. Confirme se o ETL foi executado e tente novamente.", "error");
}
function emptyRow(columns, label = "Nenhum registro encontrado para estes filtros.") {
  return `<tr><td colspan="${columns}" class="empty-row"><span>⌕</span><strong>${html(label)}</strong><small>Tente ampliar ou limpar os filtros.</small></td></tr>`;
}
function renderPagination(selector, payload, callback) {
  const container = element(selector);
  const start = payload.total ? (payload.page - 1) * payload.page_size + 1 : 0;
  const end = Math.min(payload.page * payload.page_size, payload.total);
  container.innerHTML = `<span>${integer.format(start)}–${integer.format(end)} de ${integer.format(payload.total)}</span>
    <button type="button" data-direction="previous" ${payload.page <= 1 ? "disabled" : ""} aria-label="Página anterior">←</button>
    <button type="button" data-direction="next" ${payload.page >= payload.total_pages ? "disabled" : ""} aria-label="Próxima página">→</button>`;
  container.querySelectorAll("button:not(:disabled)").forEach((button) => {
    button.addEventListener("click", () => callback(payload.page + (button.dataset.direction === "next" ? 1 : -1)));
  });
}
function queryString(values) {
  const parameters = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined && value !== false) parameters.set(key, String(value));
  });
  return parameters.toString();
}

function monthLabel(value, withYear = false) {
  const [year, month] = String(value).split("-");
  const names = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const name = names[Number(month) - 1] || value;
  return withYear ? `${name}/${String(year).slice(-2)}` : name;
}

function monthLongLabel(value) {
  const [year, month] = String(value).split("-");
  const names = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
  return `${names[Number(month) - 1] || value} de ${year}`;
}

function shortName(value, limit = 42) {
  const clean = text(value).replace(/^SECRETARIA MUNICIPAL D[AEOS]*\s+/i, "");
  const readable = clean.toLocaleLowerCase("pt-BR").replace(/(^|[\s,/()-])\p{L}/gu, (letter) => letter.toLocaleUpperCase("pt-BR"));
  return clipped(readable, limit);
}

function headlineName(value, limit = 30) {
  return clipped(shortName(value, 100).split(",")[0], limit);
}

function rounded(value, digits = 1) {
  const scale = 10 ** digits;
  return Math.round((Number(value) + Number.EPSILON) * scale) / scale;
}

let contextPromise;
let analyticsPromise;
let marketPromise;

function getContext(force = false) {
  if (force || !contextPromise) {
    contextPromise = Promise.all([api("/api/summary"), api("/api/meta")]);
  }
  return contextPromise;
}

function getAnalytics(force = false) {
  if (force || !analyticsPromise) analyticsPromise = api("/api/analytics");
  return analyticsPromise;
}

function getMarket(force = false) {
  if (force || !marketPromise) marketPromise = api("/api/market-intelligence");
  return marketPromise;
}

function applyContext(summary, metadata) {
  element("#nav-open-count").textContent = integer.format(summary.open_procurements);
  element("#last-updated").textContent = dateTime(metadata.dataset.built_at);
  element("#source-link").href = metadata.source_url;

  element("#dataset-year").textContent = summary.year;
  element("#kpi-estimated").textContent = money(summary.estimated_value, true);
  element("#kpi-estimated").title = money(summary.estimated_value);
  element("#kpi-procurement-count").textContent = `${integer.format(summary.procurement_count)} processos publicados`;
  element("#kpi-awarded").textContent = money(summary.awarded_value, true);
  element("#kpi-awarded").title = money(summary.awarded_value);
  element("#kpi-savings-detail").textContent = `${money(summary.procurement_savings, true)} de economia sobre o estimado`;
  element("#kpi-open").textContent = integer.format(summary.open_procurements);
  element("#kpi-contracts").textContent = money(summary.contract_value, true);
  element("#kpi-contracts").title = money(summary.contract_value);
  element("#kpi-contract-count").textContent = `${integer.format(summary.contract_count)} contratos analisados`;
  element("#kpi-paid").textContent = money(summary.paid_value, true);
  element("#kpi-paid").title = money(summary.paid_value);
  element("#kpi-creditors").textContent = `${integer.format(summary.company_creditor_count)} empresas + ${integer.format(summary.person_creditor_count)} pessoas`;

  element("#opportunities-live").textContent = integer.format(summary.open_procurements);
  element("#opportunities-estimated").textContent = money(summary.estimated_value, true);
  element("#contracts-active").textContent = integer.format(summary.active_contracts);
  element("#contracts-value").textContent = money(summary.contract_value, true);
  element("#agencies-procurements").textContent = integer.format(summary.procurement_count);
  element("#agencies-open").textContent = integer.format(summary.open_procurements);
  element("#agencies-contracts").textContent = integer.format(summary.contract_count);
  element("#expenses-committed").textContent = money(summary.company_committed_value, true);
  element("#expenses-paid").textContent = money(summary.company_paid_value, true);
  element("#expenses-balance").textContent = money(summary.company_committed_balance, true);
  element("#people-count").textContent = integer.format(summary.person_creditor_count);
  element("#people-committed").textContent = money(summary.person_committed_value, true);
  element("#people-paid").textContent = money(summary.person_paid_value, true);
  element("#people-scope").textContent = `${metadata.source} · ano ${summary.year} · filtros atuam no detalhamento`;
}

async function loadContext(force = false) {
  try {
    const [summary, metadata] = await getContext(force);
    applyContext(summary, metadata);
    return [summary, metadata];
  } catch (error) {
    contextPromise = undefined;
    throw error;
  }
}

function renderOverviewCharts(summary, analytics) {
  if (!window.Charts) throw new Error("Biblioteca de gráficos indisponível");

  const procurementMonths = analytics.procurements_by_month;
  Charts.column("procurements-month-chart", {
    title: "Estimado x homologado por mês",
    subtitle: `Licitações publicadas em ${summary.year} · R$ milhões`,
    xAxis: { categories: procurementMonths.map((item) => monthLabel(item.month)) },
    yAxis: { suffix: " mi" },
    tooltip: { valuePrefix: "R$ ", valueSuffix: " mi", valueDecimals: 1 },
    plotOptions: { column: { dataLabels: false, pointPadding: 0.08, groupPadding: 0.14 } },
    series: [
      { name: "Estimado", color: "#a4a7a4", data: procurementMonths.map((item) => Number(item.estimated_value) / 1e6) },
      { name: "Homologado", color: "#097e5d", data: procurementMonths.map((item) => Number(item.awarded_value) / 1e6) },
    ],
  });

  const paymentRate = Number(summary.paid_value) / Math.max(Number(summary.committed_value), 1) * 100;
  Charts.barList("finance-stage-chart", {
    title: "Do empenho ao pagamento",
    subtitle: `${paymentRate.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}% do empenhado já foi pago · empresas e pessoas · R$ bilhões`,
    plotOptions: { barList: { autoHeight: false, valueSuffix: " bi", barHeight: 23, rowGap: 24 } },
    series: [{ name: "Valor", data: [
      { name: "Empenhado", y: rounded(Number(summary.committed_value) / 1e9, 2), color: "#10252d" },
      { name: "Liquidado", y: rounded(Number(summary.settled_value) / 1e9, 2), color: "#3b82f6" },
      { name: "Pago", y: rounded(Number(summary.paid_value) / 1e9, 2), color: "#097e5d" },
    ] }],
  });

  const leadingAgency = analytics.top_agencies[0] || { agency: "Órgão líder" };
  Charts.barList("agency-chart", {
    title: `${headlineName(leadingAgency.agency)} lidera o valor contratado`,
    subtitle: `Cinco maiores órgãos · contratos assinados em ${summary.year} · R$ milhões`,
    plotOptions: { barList: { autoHeight: false, valueSuffix: " mi", barHeight: 18, rowGap: 14 } },
    series: [{ name: "Contratado", data: analytics.top_agencies.slice(0, 5).map((item, index) => ({
      name: shortName(item.agency), y: rounded(Number(item.contract_value) / 1e6),
      color: index === 0 ? "#097e5d" : "#8b8d8b",
    })) }],
  });

  const statuses = analytics.procurement_statuses;
  const homologated = statuses.filter((item) => item.status === "HOMOLOGADO").reduce((sum, item) => sum + item.procurement_count, 0);
  const moving = statuses.filter((item) => ["EM ANDAMENTO", "PARALISADO", "PRORROGAÇÃO"].includes(item.status)).reduce((sum, item) => sum + item.procurement_count, 0);
  const totalStatuses = statuses.reduce((sum, item) => sum + item.procurement_count, 0);
  const other = Math.max(0, totalStatuses - homologated - moving);
  const homologatedRate = totalStatuses ? homologated / totalStatuses * 100 : 0;
  Charts.donut("status-chart", {
    title: `${homologatedRate.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}% dos processos foram homologados`,
    subtitle: `Situação das ${integer.format(totalStatuses)} licitações publicadas em ${summary.year}`,
    plotOptions: { pie: {
      innerSize: "64%", showPercentages: true, dataLabels: { enabled: false },
      centerText: { value: integer.format(totalStatuses), label: "processos", color: "#10252d" },
    } },
    series: [{ name: "Processos", data: [
      { name: "Homologados", y: homologated, color: "#097e5d" },
      { name: "Em movimento", y: moving, color: "#3b82f6" },
      { name: "Outros", y: other, color: "#8b8d8b" },
    ] }],
  });

  const renewals = analytics.renewals_by_month;
  const renewalPeak = renewals.reduce(
    (leader, item) => item.contract_count > leader.contract_count ? item : leader,
    { month: `${summary.year}-01`, contract_count: 0 },
  );
  Charts.column("renewals-chart", {
    title: renewals.length ? `${monthLongLabel(renewalPeak.month)} concentra ${integer.format(renewalPeak.contract_count)} vencimentos` : "Vencimentos nos próximos 365 dias",
    subtitle: "Contratos com vigência terminando nos próximos 365 dias · quantidade",
    xAxis: { categories: renewals.map((item) => monthLabel(item.month, true)) },
    yAxis: { suffix: "" },
    tooltip: { valueSuffix: " contratos", valueDecimals: 0 },
    plotOptions: { column: { dataLabels: true, pointPadding: 0.12, groupPadding: 0.1 } },
    series: [{ name: "Contratos", color: "#097e5d", data: renewals.map((item) => item.contract_count) }],
  });

  const opportunityLeader = analytics.open_opportunities_by_agency[0] || { agency: "Nenhum órgão" };
  Charts.barList("opportunity-agency-chart", {
    title: `${headlineName(opportunityLeader.agency)} concentra as oportunidades abertas`,
    subtitle: "Processos em andamento, paralisados ou em prorrogação · quantidade",
    plotOptions: { barList: { autoHeight: false, valueSuffix: "", barHeight: 18, rowGap: 14 } },
    series: [{ name: "Oportunidades", data: analytics.open_opportunities_by_agency.slice(0, 5).map((item, index) => ({
      name: shortName(item.agency), y: item.opportunity_count,
      color: index === 0 ? "#3b82f6" : "#8b8d8b",
    })) }],
  });
}

function renderOpportunityCharts(analytics) {
  const opportunityLeader = analytics.open_opportunities_by_agency[0] || { agency: "Nenhum órgão", opportunity_count: 0 };
  Charts.barList("opportunities-agency-chart", {
    title: `${headlineName(opportunityLeader.agency)} tem ${integer.format(opportunityLeader.opportunity_count)} oportunidades em movimento`,
    subtitle: "Processos abertos por órgão comprador · quantidade",
    plotOptions: { barList: { autoHeight: false, barHeight: 18, rowGap: 13 } },
    series: [{ name: "Oportunidades", data: analytics.open_opportunities_by_agency.slice(0, 7).map((item, index) => ({
      name: shortName(item.agency), y: item.opportunity_count,
      color: index === 0 ? "#3b82f6" : "#8b8d8b",
    })) }],
  });

  const leadingModality = analytics.procurement_modalities[0] || { modality: "Nenhuma modalidade" };
  Charts.barList("modalities-chart", {
    title: `${shortName(leadingModality.modality, 34)} é a modalidade mais frequente`,
    subtitle: "Todos os processos publicados no ano · quantidade",
    plotOptions: { barList: { autoHeight: false, barHeight: 18, rowGap: 13 } },
    series: [{ name: "Processos", data: analytics.procurement_modalities.map((item, index) => ({
      name: shortName(item.modality), y: item.procurement_count,
      color: index === 0 ? "#097e5d" : "#8b8d8b",
    })) }],
  });
}

function renderContractCharts(analytics) {
  const months = analytics.contracts_by_month;
  const peakMonth = months.reduce(
    (leader, item) => Number(item.contract_value) > Number(leader.contract_value) ? item : leader,
    { month: "2026-01", contract_value: 0 },
  );
  Charts.column("contracts-month-chart", {
    title: months.length ? `${monthLongLabel(peakMonth.month)} concentrou ${money(peakMonth.contract_value, true)} em contratos` : "Contratos assinados por mês",
    subtitle: "Valor atual dos contratos por mês de assinatura · R$ milhões",
    xAxis: { categories: months.map((item) => monthLabel(item.month)) },
    yAxis: { suffix: " mi" },
    tooltip: { valuePrefix: "R$ ", valueSuffix: " mi", valueDecimals: 1 },
    plotOptions: { column: { dataLabels: false, pointPadding: 0.1, groupPadding: 0.12 } },
    series: [{ name: "Contratado", color: "#097e5d", data: months.map((item) => rounded(Number(item.contract_value) / 1e6)) }],
  });

  const leadingCategory = analytics.contract_categories[0] || { category: "Nenhuma categoria" };
  Charts.barList("categories-chart", {
    title: `${shortName(leadingCategory.category, 34)} lidera as categorias`,
    subtitle: "Cinco maiores categorias por valor atual · R$ milhões",
    plotOptions: { barList: { autoHeight: false, valueSuffix: " mi", barHeight: 18, rowGap: 14 } },
    series: [{ name: "Contratado", data: analytics.contract_categories.slice(0, 5).map((item, index) => ({
      name: shortName(item.category, 48), y: rounded(Number(item.contract_value) / 1e6),
      color: index === 0 ? "#097e5d" : "#8b8d8b",
    })) }],
  });
}

function renderSupplierCharts(items) {
  const leaders = [...items].sort((a, b) => Number(b.paid_value) - Number(a.paid_value)).slice(0, 6);
  const leader = leaders[0] || { supplier_name: "Nenhuma empresa", paid_value: 0 };
  Charts.barList("supplier-payment-chart", {
    title: `${shortName(leader.supplier_name, 34)} lidera o valor pago no recorte`,
    subtitle: "Empresas enriquecidas · execução municipal · R$ milhões",
    plotOptions: { barList: { autoHeight: false, valueSuffix: " mi", barHeight: 18, rowGap: 13 } },
    series: [{ name: "Pago", data: leaders.map((item, index) => ({
      name: shortName(item.trade_name || item.supplier_name),
      y: rounded(Number(item.paid_value) / 1e6, 2),
      color: index === 0 ? Charts.theme.colors[1] : Charts.theme.muted,
    })) }],
  });

  const points = items.filter((item) => Number(item.contract_value) > 0 || Number(item.paid_value) > 0);
  const distinctContractValues = new Set(
    points.map((item) => rounded(Number(item.contract_value) / 1e6, 2)),
  );
  Charts.scatter("suppliers-contract-chart", {
    title: "Contratos e pagamentos revelam perfis comerciais distintos",
    subtitle: "Cada ponto é uma empresa enriquecida · R$ milhões",
    xAxis: { title: "Valor contratado", suffix: " mi" },
    yAxis: { title: "Valor pago", suffix: " mi" },
    tooltip: { valuePrefix: "R$ ", valueSuffix: " mi", valueDecimals: 2 },
    series: [{
      name: "Empresas",
      color: Charts.theme.colors[2],
      regression: points.length > 2 && distinctContractValues.size > 1,
      showLabels: false,
      data: points.map((item) => ({
        name: item.trade_name || item.supplier_name,
        x: rounded(Number(item.contract_value) / 1e6, 2),
        y: rounded(Number(item.paid_value) / 1e6, 2),
      })),
    }],
  });
}

function marketFiltered(items, ignoredDimension = "") {
  const query = normalized(marketState.q);
  return items.filter((item) => {
    if (query) {
      const haystack = normalized([
        item.supplier_name, item.legal_name, item.trade_name, item.cnpj,
        item.primary_cnae, item.primary_cnae_description, item.market_sector,
        item.phone_primary, item.phone_secondary, item.email, item.city,
        item.district, item.postal_code,
      ].join(" "));
      const queryDigits = query.replace(/\D/g, "");
      const digitMatch = queryDigits.length >= 3
        && haystack.replace(/\D/g, "").includes(queryDigits);
      if (!haystack.includes(query) && !digitMatch) return false;
    }
    if (marketState.map_coordinate) {
      const coordinate = `${Number(item.longitude).toFixed(5)},${Number(item.latitude).toFixed(5)}`;
      if (coordinate !== marketState.map_coordinate) return false;
    }
    return ["city", "district", "market_sector", "company_size", "registration_status"].every(
      (dimension) => dimension === ignoredDimension || !marketState[dimension]
        || item[dimension] === marketState[dimension],
    );
  });
}

function marketAggregate(items, dimension) {
  const grouped = new Map();
  items.forEach((item) => {
    const label = text(item[dimension], "Não informado");
    const current = grouped.get(label) || { label, paid: 0, companies: 0 };
    current.paid += Number(item.paid_value) || 0;
    current.companies += 1;
    grouped.set(label, current);
  });
  return [...grouped.values()].sort((a, b) => b.paid - a.paid || b.companies - a.companies);
}

function renderMarketDimension(selector, items, dimension) {
  const rows = marketAggregate(marketFiltered(items, dimension), dimension).slice(0, 7);
  const maximum = Math.max(...rows.map((row) => row.paid), 1);
  element(selector).innerHTML = rows.length ? rows.map((row) => {
    const active = marketState[dimension] === row.label;
    return `<button class="dimension-row${active ? " active" : ""}" type="button" data-market-dimension="${html(dimension)}" data-market-value="${html(row.label)}" aria-pressed="${active}">
      <span><strong>${html(shortName(row.label, 44))}</strong><small>${integer.format(row.companies)} empresas</small></span>
      <b>${html(money(row.paid, true))}</b><i><span style="width:${Math.max(2, row.paid / maximum * 100)}%"></span></i>
    </button>`;
  }).join("") : `<div class="dimension-empty">Nenhuma categoria neste recorte.</div>`;
}

function renderMarketMap(items) {
  const boundary = window.CUIABA_BOUNDARY || [];
  const width = 1000;
  const height = 560;
  const padding = 42;
  const longitudes = boundary.map((point) => point[0]);
  const latitudes = boundary.map((point) => point[1]);
  const minLongitude = Math.min(...longitudes);
  const maxLongitude = Math.max(...longitudes);
  const minLatitude = Math.min(...latitudes);
  const maxLatitude = Math.max(...latitudes);
  const located = items.filter((item) => {
    const longitude = Number(item.longitude);
    const latitude = Number(item.latitude);
    return normalized(item.city) === "cuiaba" && Number.isFinite(longitude)
      && Number.isFinite(latitude) && longitude >= minLongitude && longitude <= maxLongitude
      && latitude >= minLatitude && latitude <= maxLatitude;
  });
  const locationLongitudes = located.length
    ? located.map((item) => Number(item.longitude)) : [minLongitude, maxLongitude];
  const locationLatitudes = located.length
    ? located.map((item) => Number(item.latitude)) : [minLatitude, maxLatitude];
  const longitudeSpan = Math.max(Math.max(...locationLongitudes) - Math.min(...locationLongitudes), 0.012);
  const latitudeSpan = Math.max(Math.max(...locationLatitudes) - Math.min(...locationLatitudes), 0.012);
  const urbanBounds = {
    minLongitude: Math.min(...locationLongitudes) - longitudeSpan * 0.12,
    maxLongitude: Math.max(...locationLongitudes) + longitudeSpan * 0.12,
    minLatitude: Math.min(...locationLatitudes) - latitudeSpan * 0.12,
    maxLatitude: Math.max(...locationLatitudes) + latitudeSpan * 0.12,
  };
  const project = (longitude, latitude) => ({
    x: padding + (longitude - urbanBounds.minLongitude) / (urbanBounds.maxLongitude - urbanBounds.minLongitude) * (width - padding * 2),
    y: padding + (urbanBounds.maxLatitude - latitude) / (urbanBounds.maxLatitude - urbanBounds.minLatitude) * (height - padding * 2),
  });
  const inset = { x: 825, y: 26, width: 138, height: 112, padding: 8 };
  const projectInset = (longitude, latitude) => ({
    x: inset.x + inset.padding + (longitude - minLongitude) / (maxLongitude - minLongitude)
      * (inset.width - inset.padding * 2),
    y: inset.y + inset.padding + (maxLatitude - latitude) / (maxLatitude - minLatitude)
      * (inset.height - inset.padding * 2),
  });
  const insetPath = boundary.map((point, index) => {
    const projected = projectInset(point[0], point[1]);
    return `${index ? "L" : "M"}${projected.x.toFixed(1)},${projected.y.toFixed(1)}`;
  }).join(" ") + " Z";
  const insetUrbanStart = projectInset(urbanBounds.minLongitude, urbanBounds.maxLatitude);
  const insetUrbanEnd = projectInset(urbanBounds.maxLongitude, urbanBounds.minLatitude);
  const grouped = new Map();
  located.forEach((item) => {
    const longitude = Number(item.longitude);
    const latitude = Number(item.latitude);
    const key = `${longitude.toFixed(5)},${latitude.toFixed(5)}`;
    const current = grouped.get(key) || {
      key, longitude, latitude, companies: 0, paid: 0, districts: new Set(),
    };
    current.companies += 1;
    current.paid += Number(item.paid_value) || 0;
    if (item.district) current.districts.add(item.district);
    grouped.set(key, current);
  });
  const clusters = [...grouped.values()];
  const maximum = Math.max(...clusters.map((item) => item.paid), 1);
  const markers = clusters.map((cluster) => {
    const point = project(cluster.longitude, cluster.latitude);
    const size = 15 + Math.sqrt(Math.max(0, cluster.paid) / maximum) * 19
      + Math.min(8, Math.sqrt(cluster.companies));
    const district = [...cluster.districts].slice(0, 2).join(" / ") || "CEP geocodificado";
    const label = `${district} · ${integer.format(cluster.companies)} ${cluster.companies === 1 ? "empresa" : "empresas"} · ${money(cluster.paid)} pagos`;
    return `<button class="map-marker${cluster.companies > 1 ? " cluster" : ""}" type="button" style="--x:${point.x / width * 100}%;--y:${point.y / height * 100}%;--size:${size}px;--z:${cluster.companies + 2}" data-market-coordinate="${html(cluster.key)}" data-market-label="${html(`${district} · ${integer.format(cluster.companies)} empresas`)}" aria-label="Filtrar por ${html(label)}" title="${html(label)}"><span>${cluster.companies > 1 ? integer.format(cluster.companies) : ""}</span></button>`;
  }).join("");
  element("#market-map").innerHTML = `<svg viewBox="0 0 ${width} ${height}" aria-hidden="true"><defs><pattern id="map-grid" width="54" height="54" patternUnits="userSpaceOnUse"><path d="M54 0H0V54" fill="none" stroke="currentColor" stroke-opacity=".08"/></pattern></defs><rect width="100%" height="100%" fill="url(#map-grid)"/><g class="map-inset"><rect class="map-inset-frame" x="${inset.x}" y="${inset.y}" width="${inset.width}" height="${inset.height}" rx="10"/><path class="map-inset-shape" d="${insetPath}"/><rect class="map-inset-viewport" x="${insetUrbanStart.x.toFixed(1)}" y="${insetUrbanStart.y.toFixed(1)}" width="${Math.max(3, insetUrbanEnd.x - insetUrbanStart.x).toFixed(1)}" height="${Math.max(3, insetUrbanEnd.y - insetUrbanStart.y).toFixed(1)}"/><text class="map-inset-label" x="${inset.x + 9}" y="${inset.y + inset.height + 17}">MUNICÍPIO</text></g><text x="44" y="520">CUIABÁ · ÁREA URBANA AMPLIADA</text></svg><span class="map-zoom-label">VISÃO URBANA</span>${markers}${located.length ? "" : '<div class="map-empty">Nenhuma sede geocodificada em Cuiabá neste recorte.</div>'}`;
  element("#market-map-count").textContent = `${integer.format(located.length)} sedes · ${integer.format(clusters.length)} pontos`;
}

function renderMarketTable(items) {
  const sorted = [...items].sort((a, b) => Number(b.paid_value) - Number(a.paid_value));
  element("#market-table-count").textContent = `${integer.format(sorted.length)} resultados enriquecidos`;
  element("#suppliers-body").innerHTML = sorted.length ? sorted.slice(0, 30).map((item) => {
    const address = [item.street, item.street_number, item.district].filter(Boolean).join(", ");
    const contact = item.phone_primary
      ? `<a href="tel:${html(item.phone_primary)}"><strong>${html(phone(item.phone_primary))}</strong></a>`
      : "<strong>Sem telefone</strong>";
    const email = item.email ? `<small title="${html(item.email)}">${html(clipped(item.email, 34))}</small>` : "<small>E-mail não informado</small>";
    return `<tr><td><strong>${html(clipped(item.trade_name || item.legal_name || item.supplier_name, 54))}</strong><small>${html(cnpj(item.cnpj))} · ${html(item.market_sector)}</small></td>
      <td>${badge(item.registration_status)}<small>${html(text(item.company_size))} · ${html(text(item.tax_regime, item.simples ? "Simples Nacional" : "Regime não informado"))}</small></td>
      <td>${contact}${email}</td><td><strong>${html(`${text(item.city, "—")}/${text(item.state, "—")}`)}</strong><small title="${html(address)}">${html(clipped(address, 42))}</small></td>
      <td class="numeric"><strong>${integer.format(item.contract_count)}</strong><small>${html(money(item.contract_value))}</small></td><td class="numeric"><strong>${html(money(item.paid_value))}</strong><small>${html(clipped(item.primary_cnae_description, 42))}</small></td></tr>`;
  }).join("") : emptyRow(6, "Nenhuma empresa enriquecida atende a este cruzamento.");
}

function renderMarketActiveFilters() {
  const labels = {
    q: "Busca", city: "Cidade", district: "Bairro", market_sector: "Nicho",
    company_size: "Porte", registration_status: "Situação", map_coordinate: "Mapa",
  };
  const active = Object.entries(marketState).filter(([, value]) => value);
  element("#market-active-filters").innerHTML = active.length
    ? `<span>Recorte ativo:</span>${active.map(([key, value]) => `<button type="button" data-remove-market-filter="${html(key)}">${html(labels[key])}: ${html(shortName(key === "map_coordinate" ? marketMapLabel : value, 34))} ×</button>`).join("")}`
    : "<span>Sem filtros: exibindo todo o conjunto enriquecido.</span>";
}

function renderMarket(payload) {
  const items = marketFiltered(payload.items);
  const phoneCount = items.filter((item) => item.phone_primary).length;
  const locationCount = items.filter((item) => item.longitude !== null && item.latitude !== null).length;
  const paid = items.reduce((sum, item) => sum + Number(item.paid_value || 0), 0);
  element("#suppliers-coverage").textContent = `${integer.format(payload.coverage.enriched_count)} de ${integer.format(payload.coverage.supplier_count)} enriquecidas`;
  element("#market-company-count").textContent = integer.format(items.length);
  element("#market-phone-count").textContent = integer.format(phoneCount);
  element("#market-location-count").textContent = integer.format(locationCount);
  element("#market-paid-value").textContent = money(paid, true);
  renderMarketDimension("#market-sector-chart", payload.items, "market_sector");
  renderMarketDimension("#market-city-chart", payload.items, "city");
  renderMarketDimension("#market-size-chart", payload.items, "company_size");
  renderMarketMap(items);
  renderSupplierCharts(items);
  renderMarketTable(items);
  renderMarketActiveFilters();
}

function populateMarketFilters(items) {
  const dimensions = {
    "#market-city": ["city", "Todas"],
    "#market-district": ["district", "Todos"],
    "#market-sector": ["market_sector", "Todos"],
    "#market-size": ["company_size", "Todos"],
    "#market-status": ["registration_status", "Todas"],
  };
  Object.entries(dimensions).forEach(([selector, [dimension, emptyLabel]]) => {
    const select = element(selector);
    const values = [...new Set(items.map((item) => item[dimension]).filter(Boolean))]
      .sort((a, b) => String(a).localeCompare(String(b), "pt-BR"));
    select.innerHTML = `<option value="">${emptyLabel}</option>${values.map((value) => `<option value="${html(value)}">${html(shortName(value, 52))}</option>`).join("")}`;
    select.value = marketState[dimension];
  });
}

function renderAgencyCharts(analytics) {
  const agencies = analytics.top_agencies.slice(0, 8);
  const firstAgency = agencies[0] || { agency: "Órgãos" };
  const secondAgency = agencies[1] || { agency: "compradores" };
  Charts.bar("agencies-value-chart", {
    title: `${headlineName(firstAgency.agency, 18)} e ${headlineName(secondAgency.agency, 18)} lideram contratos`,
    subtitle: "Oito maiores órgãos · valores licitados, homologados e contratados · R$ milhões",
    xAxis: { categories: agencies.map((item) => shortName(item.agency, 34)) },
    yAxis: { suffix: "" },
    tooltip: { valuePrefix: "R$ ", valueSuffix: " mi", valueDecimals: 1 },
    plotOptions: { bar: { dataLabels: false, pointPadding: 0.06, groupPadding: 0.12 } },
    series: [
      { name: "Estimado", color: "#a4a7a4", data: agencies.map((item) => rounded(Number(item.estimated_value) / 1e6)) },
      { name: "Homologado", color: "#3b82f6", data: agencies.map((item) => rounded(Number(item.awarded_value) / 1e6)) },
      { name: "Contratado", color: "#097e5d", data: agencies.map((item) => rounded(Number(item.contract_value) / 1e6)) },
    ],
  });
}

function renderExpenseCharts(analytics) {
  const leaders = analytics.expense_leaders.slice(0, 6);
  const paymentLeader = leaders[0] || { supplier_name: "Nenhum credor", paid_value: 0 };
  Charts.barList("expenses-leaders-chart", {
    title: `${shortName(paymentLeader.supplier_name, 32)} recebeu ${money(paymentLeader.paid_value, true)}`,
    subtitle: "Seis empresas com maior valor pago · R$ milhões",
    plotOptions: { barList: { autoHeight: false, valueSuffix: " mi", barHeight: 18, rowGap: 13 } },
    series: [{ name: "Pago", data: leaders.map((item, index) => ({
      name: shortName(item.supplier_name), y: rounded(Number(item.paid_value) / 1e6),
      color: index === 0 ? "#097e5d" : "#8b8d8b",
    })) }],
  });

  const rates = leaders.map((item) => Number(item.payment_rate));
  const minimumRate = rates.length ? Math.min(...rates) : 0;
  const maximumRate = rates.length ? Math.max(...rates) : 0;
  Charts.barList("expenses-rate-chart", {
    title: `Conversão do empenho em pagamento varia de ${minimumRate.toLocaleString("pt-BR")}% a ${maximumRate.toLocaleString("pt-BR")}%`,
    subtitle: "Taxa de pagamento dos seis maiores recebedores · percentual",
    plotOptions: { barList: { autoHeight: false, valueSuffix: "%", barHeight: 18, rowGap: 13 } },
    series: [{ name: "Taxa paga", data: leaders.map((item) => ({
      name: shortName(item.supplier_name), y: Number(item.payment_rate),
      color: Number(item.payment_rate) >= 75 ? "#097e5d" : "#8b8d8b",
    })) }],
  });
}

function renderPeopleCharts(summary, analytics) {
  const leaders = analytics.top_person_creditors.slice(0, 7);
  const paymentLeader = leaders[0] || { person_name: "Nenhum credor", paid_value: 0 };
  Charts.barList("people-leaders-chart", {
    title: `${shortName(paymentLeader.person_name, 34)} recebeu ${money(paymentLeader.paid_value, true)}`,
    subtitle: `Sete maiores pagamentos a pessoas físicas · ${summary.year} · R$ milhões`,
    plotOptions: { barList: { autoHeight: false, valueSuffix: " mi", barHeight: 18, rowGap: 11 } },
    series: [{ name: "Pago", data: leaders.map((item, index) => ({
      name: shortName(item.person_name), y: rounded(Number(item.paid_value) / 1e6, 2),
      color: index === 0 ? Charts.theme.colors[1] : Charts.theme.muted,
    })) }],
  });

  const paymentRate = Number(summary.person_paid_value) / Math.max(Number(summary.person_committed_value), 1) * 100;
  Charts.barList("people-stages-chart", {
    title: `${paymentRate.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}% do empenhado para PF foi pago`,
    subtitle: `Execução agregada · ${summary.year} · R$ milhões`,
    plotOptions: { barList: { autoHeight: false, valueSuffix: " mi", barHeight: 23, rowGap: 24 } },
    series: [{ name: "Valor", data: [
      { name: "Empenhado", y: rounded(Number(summary.person_committed_value) / 1e6, 2), color: Charts.theme.colors[0] },
      { name: "Liquidado", y: rounded(Number(summary.person_settled_value) / 1e6, 2), color: Charts.theme.colors[2] },
      { name: "Pago", y: rounded(Number(summary.person_paid_value) / 1e6, 2), color: Charts.theme.colors[1] },
    ] }],
  });
}

async function rerenderCurrentCharts() {
  const view = appState.currentView;
  if (!appState.loaded.has(view) || view === "quality") return;
  try {
    if (view === "suppliers") {
      renderMarket(await getMarket());
      return;
    }
    const analytics = await getAnalytics();
    if (view === "overview") {
      const [summary] = await getContext();
      renderOverviewCharts(summary, analytics);
    } else if (view === "opportunities") renderOpportunityCharts(analytics);
    else if (view === "contracts") renderContractCharts(analytics);
    else if (view === "agencies") renderAgencyCharts(analytics);
    else if (view === "expenses") renderExpenseCharts(analytics);
    else if (view === "people") {
      const [summary] = await getContext();
      renderPeopleCharts(summary, analytics);
    }
  } catch (error) {
    showError(error);
  }
}

async function loadOverview(force = false) {
  if (appState.loaded.has("overview") && !force) return;
  showStatus("Atualizando indicadores executivos…");
  try {
    const [[summary], analytics, renewals] = await Promise.all([
      loadContext(force), getAnalytics(force),
      api("/api/renewals?page_size=6&within_days=365"),
    ]);
    renderOverviewCharts(summary, analytics);
    renderRenewals(renewals.items);
    appState.loaded.add("overview");
    showStatus(`Dados de ${summary.year} carregados com sucesso.`, "success");
  } catch (error) { showError(error); }
}
function renderRenewals(items) {
  element("#renewals-body").innerHTML = items.length ? items.map((item) => `<tr>
    <td><strong>${html(text(item.supplier_name))}</strong><small title="${html(item.object_text)}">Contrato ${html(text(item.number, "s/n"))} · ${html(clipped(item.object_text, 72))}</small></td>
    <td><span title="${html(item.agency)}">${html(clipped(item.agency, 38))}</span></td><td>${date(item.ends_on)}</td>
    <td>${badge(`${integer.format(item.days_to_end)} dias`)}</td><td class="numeric"><strong>${html(money(item.current_value))}</strong></td></tr>`).join("") : emptyRow(5, "Nenhum contrato termina nos próximos 365 dias.");
}

async function loadOpportunities(page = 1) {
  showStatus("Consultando oportunidades…");
  const parameters = queryString({ page, page_size: 20, q: element("#opportunities-search").value.trim(), status: element("#opportunities-status").value });
  try {
    const needsCharts = !appState.loaded.has("opportunities");
    const [payload, analytics] = await Promise.all([
      api(`/api/opportunities?${parameters}`),
      needsCharts ? getAnalytics() : Promise.resolve(null),
    ]);
    appState.pages.opportunities = page;
    element("#opportunities-total").textContent = integer.format(payload.total);
    const futureSessions = payload.items.map((item) => item.session_on).filter((value) => value && new Date(`${value}T23:59:59`) >= new Date()).sort();
    element("#opportunities-next").textContent = futureSessions.length ? date(futureSessions[0]) : "Sem data futura";
    element("#opportunities-body").innerHTML = payload.items.length ? payload.items.map((item) => `<tr>
      <td><strong>${html(text(item.number, "s/n"))} / ${html(item.year)}</strong><small title="${html(item.object_text)}">${html(clipped(item.object_text))}</small></td>
      <td><span title="${html(item.agency)}">${html(clipped(item.agency, 42))}</span></td><td>${badge(item.status)}</td><td>${date(item.session_on)}</td>
      <td class="numeric"><strong>${html(money(item.estimated_value))}</strong></td><td><div class="score"><strong>${integer.format(item.relevance_score)}</strong><span>/ 115</span></div></td></tr>`).join("") : emptyRow(6);
    renderPagination("#opportunities-pagination", payload, loadOpportunities);
    if (analytics) renderOpportunityCharts(analytics);
    appState.loaded.add("opportunities"); showStatus("Oportunidades atualizadas.", "success");
  } catch (error) { showError(error); }
}

async function loadContracts(page = 1) {
  showStatus("Consultando contratos…");
  const parameters = queryString({ page, page_size: 20, q: element("#contracts-search").value.trim(), status: element("#contracts-status").value });
  try {
    const needsCharts = !appState.loaded.has("contracts");
    const [payload, analytics] = await Promise.all([
      api(`/api/contracts?${parameters}`),
      needsCharts ? getAnalytics() : Promise.resolve(null),
    ]);
    appState.pages.contracts = page;
    element("#contracts-total").textContent = integer.format(payload.total);
    element("#contracts-body").innerHTML = payload.items.length ? payload.items.map((item) => `<tr>
      <td><strong>${html(text(item.number, "s/n"))} / ${html(item.year)}</strong><small title="${html(item.object_text)}">${html(clipped(item.object_text))}</small></td>
      <td><strong>${html(clipped(item.supplier_name, 48))}</strong><small>${html(cnpj(item.cnpj))}</small></td><td>${badge(item.status)}</td><td>${date(item.ends_on)}</td>
      <td class="numeric"><strong>${html(money(item.current_value))}</strong><small>${item.procurement_linked ? "Licitação vinculada" : "Sem vínculo no recorte"}</small></td></tr>`).join("") : emptyRow(5);
    renderPagination("#contracts-pagination", payload, loadContracts);
    if (analytics) renderContractCharts(analytics);
    appState.loaded.add("contracts"); showStatus("Contratos atualizados.", "success");
  } catch (error) { showError(error); }
}

async function loadSuppliers() {
  showStatus("Conectando contratos, pagamentos e perfis empresariais…");
  try {
    const payload = await getMarket();
    populateMarketFilters(payload.items);
    renderMarket(payload);
    appState.loaded.add("suppliers");
    showStatus("Inteligência empresarial conectada.", "success");
  } catch (error) { showError(error); }
}

async function loadAgencies(page = 1) {
  showStatus("Consultando órgãos…");
  const parameters = queryString({ page, page_size: 20, q: element("#agencies-search").value.trim() });
  try {
    const needsCharts = !appState.loaded.has("agencies");
    const [payload, analytics] = await Promise.all([
      api(`/api/agencies?${parameters}`),
      needsCharts ? getAnalytics() : Promise.resolve(null),
    ]);
    appState.pages.agencies = page;
    element("#agencies-total").textContent = integer.format(payload.total);
    element("#agencies-body").innerHTML = payload.items.length ? payload.items.map((item) => `<tr>
      <td><strong>${html(item.agency)}</strong><small>${money(item.estimated_value)} estimados em licitações</small></td><td class="numeric">${integer.format(item.procurement_count)}</td>
      <td class="numeric">${item.open_procurements ? badge(item.open_procurements) : "—"}</td><td class="numeric">${integer.format(item.contract_count)}</td>
      <td class="numeric"><strong>${html(money(item.contract_value))}</strong></td></tr>`).join("") : emptyRow(5);
    renderPagination("#agencies-pagination", payload, loadAgencies);
    if (analytics) renderAgencyCharts(analytics);
    appState.loaded.add("agencies"); showStatus("Órgãos atualizados.", "success");
  } catch (error) { showError(error); }
}

async function loadExpenses(page = 1) {
  showStatus("Consultando execução financeira…");
  const parameters = queryString({ page, page_size: 20, q: element("#expenses-search").value.trim() });
  try {
    const needsCharts = !appState.loaded.has("expenses");
    const [payload, analytics] = await Promise.all([
      api(`/api/expenses?${parameters}`),
      needsCharts ? getAnalytics() : Promise.resolve(null),
    ]);
    appState.pages.expenses = page;
    element("#expenses-total").textContent = integer.format(payload.total);
    element("#expenses-body").innerHTML = payload.items.length ? payload.items.map((item) => {
      const ratio = Number(item.committed_value) > 0 ? Math.min(100, Number(item.paid_value) / Number(item.committed_value) * 100) : 0;
      return `<tr><td><strong>${html(clipped(item.supplier_name, 58))}</strong></td><td>${html(cnpj(item.cnpj))}</td><td class="numeric">${integer.format(item.expense_records)}</td>
        <td class="numeric"><strong>${html(money(item.committed_value))}</strong></td><td class="numeric"><strong>${html(money(item.paid_value))}</strong></td>
        <td><div class="progress"><div class="progress-track"><i style="width:${ratio}%"></i></div><small>${ratio.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%</small></div></td></tr>`;
    }).join("") : emptyRow(6);
    renderPagination("#expenses-pagination", payload, loadExpenses);
    if (analytics) renderExpenseCharts(analytics);
    appState.loaded.add("expenses"); showStatus("Execução financeira atualizada.", "success");
  } catch (error) { showError(error); }
}

async function loadPeople(page = 1) {
  showStatus("Consultando credores pessoa física…");
  const parameters = queryString({ page, page_size: 20, q: element("#people-search").value.trim() });
  try {
    const needsCharts = !appState.loaded.has("people");
    const [payload, analytics, context] = await Promise.all([
      api(`/api/person-creditors?${parameters}`),
      needsCharts ? getAnalytics() : Promise.resolve(null),
      needsCharts ? getContext() : Promise.resolve(null),
    ]);
    appState.pages.people = page;
    element("#people-total").textContent = integer.format(payload.total);
    element("#people-body").innerHTML = payload.items.length ? payload.items.map((item) => {
      const ratio = Number(item.committed_value) > 0 ? Number(item.paid_value) / Number(item.committed_value) * 100 : 0;
      const trackRatio = Math.max(0, Math.min(100, ratio));
      return `<tr><td><strong>${html(clipped(item.person_name, 58))}</strong><small>Registro público ${html(item.creditor_id)} · ano ${html(item.year)}</small></td>
        <td><span class="document-mask">${html(text(item.cpf_masked, "CPF não informado"))}</span></td>
        <td class="numeric"><strong>${html(money(item.committed_value))}</strong></td><td class="numeric"><strong>${html(money(item.settled_value))}</strong></td>
        <td class="numeric"><strong>${html(money(item.paid_value))}</strong></td><td><div class="progress"><div class="progress-track"><i style="width:${trackRatio}%"></i></div><small>${ratio.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%</small></div></td></tr>`;
    }).join("") : emptyRow(6);
    renderPagination("#people-pagination", payload, loadPeople);
    if (analytics && context) renderPeopleCharts(context[0], analytics);
    appState.loaded.add("people");
    showStatus("Credores pessoa física atualizados.", "success");
  } catch (error) { showError(error); }
}

async function loadQuality() {
  showStatus("Verificando cobertura do ETL…");
  try {
    const items = await api("/api/quality");
    element("#quality-grid").innerHTML = items.map((item) => `<article class="quality-card">
      <header><h2>${html(item.resource)}</h2>${badge(item.acceptance_rate === 100 ? "Íntegro" : "Com ressalvas")}</header>
      <strong>${Number(item.acceptance_rate).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%</strong><p>taxa de aceitação · ano ${html(item.year)}</p>
      <div class="quality-stats"><span>Origem<strong>${integer.format(item.source_records)}</strong></span><span>Rejeitados<strong>${integer.format(item.rejected_records)}</strong></span>
      <span>CPF mascarado<strong>${integer.format(item.cpf_masked_records ?? item.cpf_suppressed_records ?? 0)}</strong></span></div></article>`).join("");
    appState.loaded.add("quality"); showStatus("Qualidade verificada.", "success");
  } catch (error) { showError(error); }
}

const loaders = { overview: loadOverview, opportunities: loadOpportunities, contracts: loadContracts, suppliers: loadSuppliers, agencies: loadAgencies, expenses: loadExpenses, people: loadPeople, quality: loadQuality };
let reportInProgress = false;
async function generatePdfReport() {
  if (reportInProgress) return;
  reportInProgress = true;
  const currentView = appState.currentView;
  const button = element("#report-button");
  const originalLabel = button.innerHTML;
  button.disabled = true;
  button.textContent = "Preparando…";
  showStatus("Montando todas as páginas do relatório…");
  document.body.classList.add("report-building");
  try {
    await Promise.all([
      loadOverview(true), loadOpportunities(1), loadContracts(1), loadSuppliers(),
      loadAgencies(1), loadExpenses(1), loadPeople(1), loadQuality(),
    ]);
    const [[summary], analytics, market] = await Promise.all([
      getContext(), getAnalytics(), getMarket(),
    ]);
    renderOverviewCharts(summary, analytics);
    renderOpportunityCharts(analytics);
    renderContractCharts(analytics);
    renderMarket(market);
    renderAgencyCharts(analytics);
    renderExpenseCharts(analytics);
    renderPeopleCharts(summary, analytics);
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    showStatus("Relatório pronto. Escolha “Salvar como PDF” na janela de impressão.", "success");
    window.addEventListener("afterprint", () => {
      document.body.classList.remove("report-building");
      navigate(currentView);
    }, { once: true });
    window.print();
  } catch (error) {
    document.body.classList.remove("report-building");
    showError(error);
  } finally {
    button.disabled = false;
    button.innerHTML = originalLabel;
    reportInProgress = false;
  }
}

function navigate(viewName) {
  const target = titles[viewName] ? viewName : "overview";
  appState.currentView = target;
  document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${target}`));
  document.querySelectorAll(".nav-link[data-view]").forEach((link) => {
    const active = link.dataset.view === target;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  element("#page-context").textContent = titles[target].toUpperCase();
  element("#export-button").href = `/api/export/${exportsByView[target]}.csv`;
  setMenu(false);
  loadContext().catch(showError);
  loaders[target]();
}

function setMenu(open) {
  element("#sidebar").classList.toggle("open", open);
  document.body.classList.toggle("menu-open", open);
  element("#menu-button").setAttribute("aria-expanded", String(open));
}
element("#menu-button").addEventListener("click", (event) => {
  setMenu(event.currentTarget.getAttribute("aria-expanded") !== "true");
});
element("#sidebar-close").addEventListener("click", () => setMenu(false));
element("#sidebar-backdrop").addEventListener("click", () => setMenu(false));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setMenu(false);
});
element("#refresh-button").addEventListener("click", () => {
  const view = appState.currentView;
  appState.loaded.delete(view);
  if (view === "overview") {
    loadOverview(true);
  } else {
    analyticsPromise = undefined;
    if (view === "suppliers") marketPromise = undefined;
    loadContext(true).catch(showError);
    loaders[view](appState.pages[view] || 1);
  }
});
element("#report-button").addEventListener("click", generatePdfReport);
document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => loaders[button.dataset.filter](1)));
document.querySelectorAll(".filter-bar input").forEach((input) => input.addEventListener("keydown", (event) => {
  if (event.key === "Enter") event.currentTarget.closest(".filter-bar").querySelector("[data-filter]").click();
}));

const marketSelectDimensions = {
  "market-city": "city",
  "market-district": "district",
  "market-sector": "market_sector",
  "market-size": "company_size",
  "market-status": "registration_status",
};
function updateMarketView() {
  getMarket().then(renderMarket).catch(showError);
}
Object.entries(marketSelectDimensions).forEach(([id, dimension]) => {
  element(`#${id}`).addEventListener("change", (event) => {
    marketState[dimension] = event.currentTarget.value;
    updateMarketView();
  });
});
let marketSearchTimer;
element("#market-search").addEventListener("input", (event) => {
  clearTimeout(marketSearchTimer);
  marketState.q = event.currentTarget.value.trim();
  marketSearchTimer = setTimeout(updateMarketView, 160);
});
element("#market-clear").addEventListener("click", () => {
  Object.keys(marketState).forEach((key) => { marketState[key] = ""; });
  marketMapLabel = "";
  element("#market-search").value = "";
  Object.keys(marketSelectDimensions).forEach((id) => { element(`#${id}`).value = ""; });
  updateMarketView();
});
element("#view-suppliers").addEventListener("click", (event) => {
  const dimensionButton = event.target.closest("[data-market-dimension]");
  const mapButton = event.target.closest("[data-market-coordinate]");
  const companyButton = event.target.closest("[data-market-company]");
  const removeButton = event.target.closest("[data-remove-market-filter]");
  if (dimensionButton) {
    const dimension = dimensionButton.dataset.marketDimension;
    const value = dimensionButton.dataset.marketValue;
    marketState[dimension] = marketState[dimension] === value ? "" : value;
    const selectId = Object.entries(marketSelectDimensions)
      .find(([, candidate]) => candidate === dimension)?.[0];
    if (selectId) element(`#${selectId}`).value = marketState[dimension];
    updateMarketView();
  } else if (mapButton) {
    const coordinate = mapButton.dataset.marketCoordinate;
    marketState.map_coordinate = marketState.map_coordinate === coordinate ? "" : coordinate;
    marketMapLabel = marketState.map_coordinate ? mapButton.dataset.marketLabel : "";
    updateMarketView();
  } else if (companyButton) {
    marketState.q = companyButton.dataset.marketCompany;
    element("#market-search").value = marketState.q;
    updateMarketView();
  } else if (removeButton) {
    const dimension = removeButton.dataset.removeMarketFilter;
    marketState[dimension] = "";
    if (dimension === "map_coordinate") marketMapLabel = "";
    if (dimension === "q") element("#market-search").value = "";
    const selectId = Object.entries(marketSelectDimensions)
      .find(([, candidate]) => candidate === dimension)?.[0];
    if (selectId) element(`#${selectId}`).value = "";
    updateMarketView();
  }
});
let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(rerenderCurrentCharts, 180);
});
window.addEventListener("hashchange", () => navigate(location.hash.slice(1)));
navigate(location.hash.slice(1));
