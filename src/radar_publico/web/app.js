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

async function loadOverview(force = false) {
  if (appState.loaded.has("overview") && !force) return;
  showStatus("Atualizando indicadores executivos…");
  try {
    const [summary, metadata, pipeline, agencies, renewals, opportunities] = await Promise.all([
      api("/api/summary"), api("/api/meta"), api("/api/pipeline"),
      api("/api/agencies?page_size=5"), api("/api/renewals?page_size=6&within_days=365"),
      api("/api/opportunities?page_size=100"),
    ]);
    element("#dataset-year").textContent = summary.year;
    element("#period-label").textContent = `Ano de ${summary.year}`;
    element("#hero-open").textContent = integer.format(summary.open_procurements);
    element("#kpi-open").textContent = integer.format(summary.procurement_count);
    element("#kpi-open-detail").textContent = `${integer.format(summary.open_procurements)} em andamento agora`;
    element("#nav-open-count").textContent = integer.format(summary.open_procurements);
    element("#kpi-contracts").textContent = money(summary.contract_value, true);
    element("#kpi-contracts").title = money(summary.contract_value);
    element("#kpi-contract-count").textContent = `${integer.format(summary.contract_count)} contratos analisados`;
    element("#kpi-paid").textContent = money(summary.paid_value, true);
    element("#kpi-paid").title = money(summary.paid_value);
    element("#kpi-creditors").textContent = `${integer.format(summary.creditor_count)} credores consolidados`;
    element("#kpi-savings").textContent = money(summary.procurement_savings, true);
    element("#kpi-savings").title = money(summary.procurement_savings);
    element("#last-updated").textContent = dateTime(metadata.dataset.built_at);
    element("#source-link").href = metadata.source_url;
    renderPipeline(pipeline);
    renderAgencyRanking(agencies.items);
    renderRenewals(renewals.items);
    renderHeroOpportunity(opportunities.items);
    appState.loaded.add("overview");
    showStatus(`Dados de ${summary.year} carregados com sucesso.`, "success");
  } catch (error) { showError(error); }
}

function renderPipeline(items) {
  const total = items.reduce((sum, item) => sum + item.procurement_count, 0);
  const colors = ["#0ba879", "#3b82f6", "#e99b25", "#8067dc", "#d6565c", "#7e949c", "#58c4aa"];
  let offset = 0;
  const segments = items.map((item, index) => {
    const start = offset;
    offset += total ? item.procurement_count / total * 100 : 0;
    return `${colors[index % colors.length]} ${start}% ${offset}%`;
  }).join(", ");
  element("#pipeline-chart").innerHTML = `<div class="pipeline-layout">
    <div class="donut-shell"><div class="donut" style="background:conic-gradient(${segments})"></div>
      <div class="donut-center"><strong>${integer.format(total)}</strong><span>processos mapeados</span></div></div>
    <div class="legend-list">${items.map((item, index) => `<div class="legend-row">
      <span class="legend-color" style="--legend-color:${colors[index % colors.length]}"></span>
      <div class="legend-copy"><strong>${html(item.status)}</strong><small>${money(item.awarded_value, true)} homologados</small></div>
      <b>${integer.format(item.procurement_count)}</b></div>`).join("")}</div></div>`;
}
function renderHeroOpportunity(items) {
  if (!items.length) {
    element("#hero-highlight-number").textContent = "Nenhum processo aberto";
    element("#hero-highlight-object").textContent = "O radar não encontrou oportunidades neste recorte.";
    element("#hero-highlight-agency").textContent = "Amplie os filtros para consultar o histórico.";
    element("#hero-highlight-date").textContent = "—";
    element("#hero-score").textContent = "0";
    return;
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const upcoming = items.filter((item) => item.session_on && new Date(`${item.session_on}T00:00:00`) >= today)
    .sort((left, right) => left.session_on.localeCompare(right.session_on));
  const featured = upcoming[0] || items[0];
  element("#hero-highlight-number").textContent = `${text(featured.number, "s/n")} / ${featured.year}`;
  element("#hero-highlight-object").textContent = text(featured.object_text);
  element("#hero-highlight-agency").textContent = text(featured.agency);
  element("#hero-highlight-date").textContent = date(featured.session_on);
  element("#hero-score").textContent = integer.format(featured.relevance_score);
}
function renderAgencyRanking(items) {
  const maximum = Math.max(...items.map((item) => Number(item.contract_value)), 1);
  element("#agency-ranking").innerHTML = items.length ? items.map((item, index) => `<div class="rank-row">
    <span class="rank-number">${String(index + 1).padStart(2, "0")}</span><div><strong title="${html(item.agency)}">${html(clipped(item.agency, 42))}</strong>
    <div class="mini-track"><i style="width:${Math.max(3, Number(item.contract_value) / maximum * 100)}%"></i></div></div><b>${html(money(item.contract_value, true))}</b></div>`).join("") : `<div class="inline-empty">Sem órgãos no período.</div>`;
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
