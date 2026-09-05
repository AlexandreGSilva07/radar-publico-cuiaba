"use strict";

const titles = {
  overview: "Visão geral",
  opportunities: "Oportunidades",
  contracts: "Contratos",
  suppliers: "Fornecedores",
  agencies: "Órgãos",
  expenses: "Execução financeira",
  quality: "Qualidade dos dados",
};

const exportsByView = {
  overview: "opportunities",
  opportunities: "opportunities",
  contracts: "contracts",
  suppliers: "suppliers",
  agencies: "agencies",
  expenses: "expenses",
  quality: "opportunities",
};

const appState = {
  currentView: "overview",
  loaded: new Set(),
  pages: { opportunities: 1, contracts: 1, suppliers: 1, agencies: 1, expenses: 1 },
};

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

function shortName(value, limit = 42) {
  const clean = text(value).replace(/^SECRETARIA MUNICIPAL D[AEOS]*\s+/i, "");
  const readable = clean.toLocaleLowerCase("pt-BR").replace(/(^|[\s,/()-])\p{L}/gu, (letter) => letter.toLocaleUpperCase("pt-BR"));
  return clipped(readable, limit);
}

function rounded(value, digits = 1) {
  const scale = 10 ** digits;
  return Math.round((Number(value) + Number.EPSILON) * scale) / scale;
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
    subtitle: `${paymentRate.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}% do empenhado já foi pago · R$ bilhões`,
    plotOptions: { barList: { autoHeight: false, valueSuffix: " bi", barHeight: 23, rowGap: 24 } },
    series: [{ name: "Valor", data: [
      { name: "Empenhado", y: rounded(Number(summary.committed_value) / 1e9, 2), color: "#10252d" },
      { name: "Liquidado", y: rounded(Number(summary.settled_value) / 1e9, 2), color: "#3b82f6" },
      { name: "Pago", y: rounded(Number(summary.paid_value) / 1e9, 2), color: "#097e5d" },
    ] }],
  });

  Charts.barList("agency-chart", {
    title: "Educação lidera o valor contratado",
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
  Charts.column("renewals-chart", {
    title: "Renovações se concentram no 1º trimestre de 2027",
    subtitle: "Contratos com vigência terminando nos próximos 365 dias · quantidade",
    xAxis: { categories: renewals.map((item) => monthLabel(item.month, true)) },
    yAxis: { suffix: "" },
    tooltip: { valueSuffix: " contratos", valueDecimals: 0 },
    plotOptions: { column: { dataLabels: true, pointPadding: 0.12, groupPadding: 0.1 } },
    series: [{ name: "Contratos", color: "#097e5d", data: renewals.map((item) => item.contract_count) }],
  });

  Charts.barList("opportunity-agency-chart", {
    title: "Saúde concentra as oportunidades abertas",
    subtitle: "Processos em andamento, paralisados ou em prorrogação · quantidade",
    plotOptions: { barList: { autoHeight: false, valueSuffix: "", barHeight: 18, rowGap: 14 } },
    series: [{ name: "Oportunidades", data: analytics.open_opportunities_by_agency.slice(0, 5).map((item, index) => ({
      name: shortName(item.agency), y: item.opportunity_count,
      color: index === 0 ? "#3b82f6" : "#8b8d8b",
    })) }],
  });
}

async function loadOverview(force = false) {
  if (appState.loaded.has("overview") && !force) return;
  showStatus("Atualizando indicadores executivos…");
  try {
    const [summary, metadata, analytics, renewals] = await Promise.all([
      api("/api/summary"), api("/api/meta"), api("/api/analytics"),
      api("/api/renewals?page_size=6&within_days=365"),
    ]);
    element("#dataset-year").textContent = summary.year;
    element("#kpi-estimated").textContent = money(summary.estimated_value, true);
    element("#kpi-estimated").title = money(summary.estimated_value);
    element("#kpi-procurement-count").textContent = `${integer.format(summary.procurement_count)} processos publicados`;
    element("#kpi-awarded").textContent = money(summary.awarded_value, true);
    element("#kpi-awarded").title = money(summary.awarded_value);
    element("#kpi-savings-detail").textContent = `${money(summary.procurement_savings, true)} de economia sobre o estimado`;
    element("#kpi-open").textContent = integer.format(summary.open_procurements);
    element("#nav-open-count").textContent = integer.format(summary.open_procurements);
    element("#kpi-contracts").textContent = money(summary.contract_value, true);
    element("#kpi-contracts").title = money(summary.contract_value);
    element("#kpi-contract-count").textContent = `${integer.format(summary.contract_count)} contratos analisados`;
    element("#kpi-paid").textContent = money(summary.paid_value, true);
    element("#kpi-paid").title = money(summary.paid_value);
    element("#kpi-creditors").textContent = `${integer.format(summary.creditor_count)} credores consolidados`;
    element("#last-updated").textContent = dateTime(metadata.dataset.built_at);
    element("#source-link").href = metadata.source_url;
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
    const payload = await api(`/api/opportunities?${parameters}`);
    appState.pages.opportunities = page;
    element("#opportunities-total").textContent = integer.format(payload.total);
    element("#opportunities-body").innerHTML = payload.items.length ? payload.items.map((item) => `<tr>
      <td><strong>${html(text(item.number, "s/n"))} / ${html(item.year)}</strong><small title="${html(item.object_text)}">${html(clipped(item.object_text))}</small></td>
      <td><span title="${html(item.agency)}">${html(clipped(item.agency, 42))}</span></td><td>${badge(item.status)}</td><td>${date(item.session_on)}</td>
      <td class="numeric"><strong>${html(money(item.estimated_value))}</strong></td><td><div class="score"><strong>${integer.format(item.relevance_score)}</strong><span>/ 115</span></div></td></tr>`).join("") : emptyRow(6);
    renderPagination("#opportunities-pagination", payload, loadOpportunities);
    appState.loaded.add("opportunities"); showStatus("Oportunidades atualizadas.", "success");
  } catch (error) { showError(error); }
}

async function loadContracts(page = 1) {
  showStatus("Consultando contratos…");
  const parameters = queryString({ page, page_size: 20, q: element("#contracts-search").value.trim(), status: element("#contracts-status").value });
  try {
    const payload = await api(`/api/contracts?${parameters}`);
    appState.pages.contracts = page;
    element("#contracts-total").textContent = integer.format(payload.total);
    element("#contracts-body").innerHTML = payload.items.length ? payload.items.map((item) => `<tr>
      <td><strong>${html(text(item.number, "s/n"))} / ${html(item.year)}</strong><small title="${html(item.object_text)}">${html(clipped(item.object_text))}</small></td>
      <td><strong>${html(clipped(item.supplier_name, 48))}</strong><small>${html(cnpj(item.cnpj))}</small></td><td>${badge(item.status)}</td><td>${date(item.ends_on)}</td>
      <td class="numeric"><strong>${html(money(item.current_value))}</strong><small>${item.procurement_linked ? "Licitação vinculada" : "Sem vínculo no recorte"}</small></td></tr>`).join("") : emptyRow(5);
    renderPagination("#contracts-pagination", payload, loadContracts);
    appState.loaded.add("contracts"); showStatus("Contratos atualizados.", "success");
  } catch (error) { showError(error); }
}

async function loadSuppliers(page = 1) {
  showStatus("Consultando fornecedores…");
  const parameters = queryString({ page, page_size: 20, q: element("#suppliers-search").value.trim(), contracted_only: element("#contracted-only").checked });
  try {
    const payload = await api(`/api/suppliers?${parameters}`);
    appState.pages.suppliers = page;
    element("#suppliers-total").textContent = integer.format(payload.total);
    element("#suppliers-body").innerHTML = payload.items.length ? payload.items.map((item) => {
      const profile = item.profile;
      const profileText = profile ? `${text(profile.company_size, "Porte não informado")} · ${text(profile.city, "—")}/${text(profile.state, "—")}` : "Aguardando enriquecimento";
      return `<tr><td><strong>${html(clipped(profile?.legal_name || item.supplier_name, 55))}</strong><small>${html(cnpj(item.cnpj))}</small></td>
        <td>${profile ? badge(profile.registration_status) : badge("Não enriquecido")}<small title="${html(profile?.primary_cnae_description)}">${html(clipped(profileText, 52))}</small></td>
        <td class="numeric">${integer.format(item.contract_count)}</td><td class="numeric"><strong>${html(money(item.contract_value))}</strong></td>
        <td class="numeric"><strong>${html(money(item.paid_value))}</strong></td></tr>`;
    }).join("") : emptyRow(5);
    renderPagination("#suppliers-pagination", payload, loadSuppliers);
    appState.loaded.add("suppliers"); showStatus("Fornecedores atualizados.", "success");
  } catch (error) { showError(error); }
}

async function loadAgencies(page = 1) {
  showStatus("Consultando órgãos…");
  const parameters = queryString({ page, page_size: 20, q: element("#agencies-search").value.trim() });
  try {
    const payload = await api(`/api/agencies?${parameters}`);
    appState.pages.agencies = page;
    element("#agencies-total").textContent = integer.format(payload.total);
    element("#agencies-body").innerHTML = payload.items.length ? payload.items.map((item) => `<tr>
      <td><strong>${html(item.agency)}</strong><small>${money(item.estimated_value)} estimados em licitações</small></td><td class="numeric">${integer.format(item.procurement_count)}</td>
      <td class="numeric">${item.open_procurements ? badge(item.open_procurements) : "—"}</td><td class="numeric">${integer.format(item.contract_count)}</td>
      <td class="numeric"><strong>${html(money(item.contract_value))}</strong></td></tr>`).join("") : emptyRow(5);
    renderPagination("#agencies-pagination", payload, loadAgencies);
    appState.loaded.add("agencies"); showStatus("Órgãos atualizados.", "success");
  } catch (error) { showError(error); }
}

async function loadExpenses(page = 1) {
  showStatus("Consultando execução financeira…");
  const parameters = queryString({ page, page_size: 20, q: element("#expenses-search").value.trim() });
  try {
    const payload = await api(`/api/expenses?${parameters}`);
    appState.pages.expenses = page;
    element("#expenses-total").textContent = integer.format(payload.total);
    element("#expenses-body").innerHTML = payload.items.length ? payload.items.map((item) => {
      const ratio = Number(item.committed_value) > 0 ? Math.min(100, Number(item.paid_value) / Number(item.committed_value) * 100) : 0;
      return `<tr><td><strong>${html(clipped(item.supplier_name, 58))}</strong></td><td>${html(cnpj(item.cnpj))}</td><td class="numeric">${integer.format(item.expense_records)}</td>
        <td class="numeric"><strong>${html(money(item.committed_value))}</strong></td><td class="numeric"><strong>${html(money(item.paid_value))}</strong></td>
        <td><div class="progress"><div class="progress-track"><i style="width:${ratio}%"></i></div><small>${ratio.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%</small></div></td></tr>`;
    }).join("") : emptyRow(6);
    renderPagination("#expenses-pagination", payload, loadExpenses);
    appState.loaded.add("expenses"); showStatus("Execução financeira atualizada.", "success");
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
      <span>CPF protegido<strong>${integer.format(item.cpf_suppressed_records)}</strong></span></div></article>`).join("");
    appState.loaded.add("quality"); showStatus("Qualidade verificada.", "success");
  } catch (error) { showError(error); }
}

const loaders = { overview: loadOverview, opportunities: loadOpportunities, contracts: loadContracts, suppliers: loadSuppliers, agencies: loadAgencies, expenses: loadExpenses, quality: loadQuality };
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
  if (appState.currentView === "overview") loadOverview(true);
  else loaders[appState.currentView](appState.pages[appState.currentView] || 1);
});
document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => loaders[button.dataset.filter](1)));
document.querySelectorAll(".filter-bar input").forEach((input) => input.addEventListener("keydown", (event) => {
  if (event.key === "Enter") event.currentTarget.closest(".filter-bar").querySelector("[data-filter]").click();
}));
document.querySelectorAll("[data-go]").forEach((link) => link.addEventListener("click", () => navigate(link.dataset.go)));
window.addEventListener("hashchange", () => navigate(location.hash.slice(1)));
navigate(location.hash.slice(1));
