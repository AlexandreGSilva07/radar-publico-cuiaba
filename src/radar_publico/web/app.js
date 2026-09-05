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

function navigate(viewName) {
  const target = titles[viewName] ? viewName : "overview";
  document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${target}`));
  document.querySelectorAll(".nav-link[data-view]").forEach((link) => link.classList.toggle("active", link.dataset.view === target));
  document.querySelector("#page-context").textContent = titles[target].toUpperCase();
  document.querySelector("#sidebar").classList.remove("open");
  document.querySelector("#menu-button").setAttribute("aria-expanded", "false");
}

window.addEventListener("hashchange", () => navigate(location.hash.slice(1)));
document.querySelector("#menu-button").addEventListener("click", (event) => {
  const sidebar = document.querySelector("#sidebar");
  const open = sidebar.classList.toggle("open");
  event.currentTarget.setAttribute("aria-expanded", String(open));
});
document.querySelectorAll("[data-go]").forEach((link) => link.addEventListener("click", () => navigate(link.dataset.go)));
navigate(location.hash.slice(1));
