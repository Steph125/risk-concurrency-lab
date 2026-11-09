/* Risk Concurrency Lab — interface.
   Une page par option du menu, avec sa propre adresse (/calcul, /cours…).
   Aucune dépendance : fetch() vers l'API FastAPI et DOM construit à la main.
   Les textes venant de l'API passent toujours par textContent, jamais par innerHTML. */
"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

/* --- Formats et vocabulaire ------------------------------------------------------- */

const nf = {
  int: new Intl.NumberFormat("fr-FR"),
  dec2: new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  dec1: new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }),
  eur: new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }),
};
// Espace insécable ( ) avant les unités : « 0,77 s » ou « 99 % » ne se coupent jamais.
const fmtSeconds = (s) => `${nf.dec2.format(s)} s`;
const fmtGain = (v) => `×${nf.dec2.format(v)}`;
const fmtTimes = (v) => `${nf.dec1.format(v)} fois`;
const fmtPercent = (level) => `${nf.dec1.format(level * 100)} %`;
const fmtMs = (s) => (s < 1 ? `${nf.int.format(Math.round(s * 1000))} ms` : fmtSeconds(s));

// Noms affichés : des termes opérationnels plutôt que techniques.
const METHODS = { sequential: "En série", threads: "Multi-tâches", processes: "Multi-moteurs", asyncio: "En alternance" };
const OPERATIONS = { cpu: "Calcul du risque", io: "Récupération des cours" };
const ACTIVITY = {
  fetch_quote: "Récupération d'un cours",
  afetch_quote: "Récupération d'un cours (en alternance)",
};
const method = (name) => METHODS[name] || name;

// Une mesure varie d'environ 15 % d'un essai à l'autre : en dessous, c'est une égalité.
const NOISE = 1.15;

/** Méthode à recommander : la plus rapide si elle bat nettement la série, sinon la série.
    En mode standard, le multi-tâches ne peut pas accélérer un calcul : un gain mesuré serait du bruit. */
function recommended(kind, block, env) {
  const r = block.results;
  let names = Object.keys(r).filter((n) => n !== "sequential");
  if (kind === "cpu" && env?.gil_enabled !== false) names = names.filter((n) => n !== "threads");
  const best = names.reduce((a, b) => (a !== null && r[a].seconds <= r[b].seconds ? a : b), null);
  return best && r[best].speedup >= NOISE ? best : "sequential";
}

/** Crée un élément. Les enfants de type chaîne deviennent des nœuds texte. */
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function icon(paths) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "ico");
  svg.setAttribute("aria-hidden", "true");
  for (const d of paths) {
    const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
    p.setAttribute("d", d);
    svg.append(p);
  }
  return svg;
}
const ICON_STAR = ["M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"];

/* --- Stockage local (facultatif : la page marche sans) ------------------------------ */

const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch (e) { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* navigation privée, etc. */ }
  },
};

/* --- Navigation entre les pages ------------------------------------------------------ */

const ROUTES = {
  "/": "accueil", "/calcul": "calcul", "/cours": "cours", "/historique": "historique",
  "/references": "references", "/activite": "activite", "/aide": "aide",
};
const PAGE_LOADERS = {
  historique: () => renderHistory(),
  references: () => loadReference(),
  activite: () => loadActivity(),
};

function showPage(path, { focus = true } = {}) {
  const clean = path.replace(/\/+$/, "") || "/";
  const name = ROUTES[clean] || "introuvable";
  for (const page of $$(".page")) page.hidden = page.dataset.page !== name;
  for (const link of $$(".nav a")) {
    if (link.dataset.nav === name) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  const page = $(`.page[data-page="${name}"]`);
  document.title = `${page.dataset.title} · Risk Concurrency Lab`;
  closeMenu();
  window.scrollTo(0, 0);
  if (focus) page.querySelector("h1")?.focus({ preventScroll: true });
  PAGE_LOADERS[name]?.();
}

function setupRouter() {
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-link]");
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (link.origin !== location.origin) return;
    event.preventDefault();
    if (link.pathname !== location.pathname) history.pushState({}, "", link.pathname);
    showPage(link.pathname);
  });
  window.addEventListener("popstate", () => showPage(location.pathname));
  showPage(location.pathname, { focus: false });
}

/* --- Menu sur téléphone ---------------------------------------------------------------- */

// Sur téléphone, le menu ouvert couvre tout l'écran ; la page dessous ne défile plus.
function setMenu(open) {
  $("#sidebar").classList.toggle("is-open", open);
  document.documentElement.classList.toggle("menu-open", open);
  $("#menu-btn").setAttribute("aria-expanded", String(open));
  $("#menu-btn .label").textContent = open ? "Fermer" : "Menu";
}
const closeMenu = () => setMenu(false);

function setupMenu() {
  $("#menu-btn").addEventListener("click", () => setMenu(!$("#sidebar").classList.contains("is-open")));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });
  // Passage en grand écran avec le menu ouvert : on le referme pour ne pas bloquer le défilement.
  matchMedia("(min-width: 861px)").addEventListener("change", (e) => { if (e.matches) closeMenu(); });
}

/* --- Mode jour / nuit ------------------------------------------------------------------- */

function isDark() {
  const theme = document.documentElement.dataset.theme;
  return theme ? theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
}

function setupTheme() {
  const label = $("#theme-label");
  const sync = () => { label.textContent = isDark() ? "Mode jour" : "Mode nuit"; };
  $("#theme-toggle").addEventListener("click", () => {
    document.documentElement.dataset.theme = isDark() ? "light" : "dark";
    try { localStorage.setItem("rcl-theme", document.documentElement.dataset.theme); } catch (e) { /* ignoré */ }
    sync();
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", sync);
  sync();
}

/* --- Appels à l'API ----------------------------------------------------------------------- */

async function getJSON(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  let data = null;
  try { data = await response.json(); } catch (e) { /* réponse vide */ }
  if (!response.ok) {
    if (response.status === 422) throw new Error("Un des réglages est hors des limites autorisées.");
    throw new Error(`Le serveur a répondu avec une erreur (${response.status}).`);
  }
  return data;
}

/* --- Serveur ---------------------------------------------------------------------------------- */

const serverMode = (env) => (env.gil_enabled ? "Mode standard" : "Mode sans verrou");
const serverLine = (env) => `${env.cpu_count ?? "?"} cœurs · ${env.platform.split("-")[0]} · Python ${env.python}`;

async function loadServer() {
  try {
    const env = await getJSON("/api/env");
    $("#server-line").textContent = serverLine(env);
    $("#server-mode").textContent = env.gil_enabled
      ? "Mode standard : un calcul à la fois par moteur"
      : "Mode sans verrou : calcul parallèle possible";
  } catch (e) {
    $("#server-line").textContent = "Serveur injoignable";
  }
}

/* --- Réglages et estimations ------------------------------------------------------------------ */

function formatOutput(input) {
  const format = $(`output[for="${input.id}"]`)?.dataset.format;
  const value = Number(input.value);
  if (format === "int") return nf.int.format(value);
  if (format === "seconds") return fmtSeconds(value);
  return String(value);
}

function updateEstimates() {
  const cpu = new FormData($("#cpu-form"));
  const paths = Number(cpu.get("paths")), chunks = Number(cpu.get("chunks")), workers = Number(cpu.get("workers"));
  const parallel = Math.min(chunks, workers), repeat = Number(cpu.get("repeat"));
  let text = `${nf.int.format(paths * chunks)} scénarios par méthode${repeat > 1 ? `, mesurés ${repeat} fois` : ""}, jusqu'à ${parallel} tâche${parallel > 1 ? "s" : ""} en même temps.`;
  if (workers > chunks) text += ` ${workers - chunks} tâche${workers - chunks > 1 ? "s" : ""} n'aura rien à faire : ajoutez des lots.`;
  $("#cpu-estimate").textContent = text;

  const io = new FormData($("#io-form"));
  const symbols = Number(io.get("symbols")), ioWorkers = Number(io.get("workers")), latency = Number(io.get("latency"));
  const waves = Math.ceil(symbols / ioWorkers);
  $("#io-estimate").textContent =
    `En série : environ ${fmtSeconds(symbols * latency)}. ` +
    `En parallèle : environ ${fmtSeconds(waves * latency)}${io.get("flaky") ? ", plus les relances" : ""}.`;
}

function setupFields() {
  for (const input of $$(".params input, .params select")) {
    const output = $(`output[for="${input.id}"]`);
    const sync = () => {
      if (output) output.textContent = formatOutput(input);
      if (input.type === "range") {  // partie remplie du curseur, dessinée en CSS
        const pct = ((input.value - input.min) / (input.max - input.min)) * 100;
        input.style.setProperty("--fill", `${pct}%`);
      }
      updateEstimates();
    };
    input.addEventListener("input", sync);
    input.addEventListener("change", sync);
    sync();
  }
}

/* --- Infobulle ----------------------------------------------------------------------------------- */

let tooltipNode = null;

function showTooltip(rows, anchor, event) {
  tooltipNode.replaceChildren(...rows);
  tooltipNode.hidden = false;
  const box = tooltipNode.getBoundingClientRect();
  let x, y;
  if (event && event.clientX) { x = event.clientX + 14; y = event.clientY + 14; }
  else { const r = anchor.getBoundingClientRect(); x = r.left + 16; y = r.bottom + 6; }
  tooltipNode.style.left = `${Math.max(8, Math.min(x, innerWidth - box.width - 8))}px`;
  tooltipNode.style.top = `${Math.max(8, Math.min(y, innerHeight - box.height - 8))}px`;
}
const hideTooltip = () => { tooltipNode.hidden = true; };

function attachTooltip(target, buildRows) {
  target.addEventListener("pointermove", (e) => showTooltip(buildRows(), target, e));
  target.addEventListener("pointerleave", hideTooltip);
  target.addEventListener("focus", () => showTooltip(buildRows(), target));
  target.addEventListener("blur", hideTooltip);
}

/* --- Lecture des résultats en langage opérationnel --------------------------------------------------- */

function readCpu(data) {
  const r = data.results, p = data.params || {}, env = data.environment || {};
  const notes = [];
  const parallel = Math.min(p.chunks ?? 1, p.workers ?? 1);
  if (parallel === 1) {
    notes.push("Avec un seul lot ou une seule tâche, aucune méthode ne peut aller plus vite : elles font toutes le même travail l'une après l'autre.");
  } else {
    const t = r.threads.speedup, m = r.processes ? r.processes.speedup : null;
    if (env.gil_enabled !== false) {
      notes.push(t < NOISE
        ? `Le multi-tâches ne fait pas gagner de temps (${fmtGain(t)}) : en mode standard, un moteur ne calcule qu'une chose à la fois.`
        : `Le multi-tâches semble gagner (${fmtGain(t)}), ce qui est impossible en mode standard : c'est une variation de la machine. Augmentez le nombre d'essais.`);
    } else {
      notes.push(t >= NOISE
        ? `En mode sans verrou, le multi-tâches accélère vraiment le calcul : ${fmtTimes(t)} plus vite.`
        : "Même en mode sans verrou, le multi-tâches ne gagne rien ici : il y a trop peu de travail par lot.");
    }
    if (m === null) {
      notes.push("Le multi-moteurs n'a pas pu être mesuré : cet hébergement ne permet pas de lancer plusieurs moteurs. Lancez l'application sur un PC ou un serveur classique pour le comparer.");
    } else {
      notes.push(m >= NOISE
        ? `Le multi-moteurs va ${fmtTimes(m)} plus vite : chaque moteur calcule sur son propre cœur.`
        : `Le multi-moteurs est plus lent ici (${fmtGain(m)}) : démarrer les moteurs coûte plus que le calcul lui-même. Augmentez le nombre de scénarios.`);
    }
    const cores = env.cpu_count || 1;
    notes.push(`Gain maximum possible avec ces réglages : ×${Math.min(parallel, cores)} (${p.chunks} lots, ${p.workers} tâches, ${cores} cœurs).`);
  }
  const values = new Set(Object.values(r).map((v) => v.var_eur));
  if (values.size === 1) notes.push(`Toutes les méthodes trouvent la même perte maximale (${nf.eur.format([...values][0])}) : seule la durée change.`);
  return notes;
}

function readIo(data) {
  const r = data.results, p = data.params;
  const notes = [];
  const overlap = Math.min(p.workers, p.symbols);
  const failed = r.sequential.failed_attempts;
  notes.push(`En série, chaque demande attend la précédente : environ ${p.symbols} × ${fmtSeconds(p.latency)} = ${fmtSeconds(p.symbols * p.latency)}${failed ? ", plus le temps des relances" : ""}.`);
  if (overlap === 1) {
    notes.push("Avec une seule demande à la fois, les attentes ne se chevauchent pas : aucun gain possible.");
  } else {
    notes.push(`Le multi-tâches (${fmtTimes(r.threads.speedup)} plus vite) et l'alternance (${fmtTimes(r.asyncio.speedup)}) font attendre jusqu'à ${overlap} demandes en même temps. L'alternance y arrive avec un seul moteur.`);
  }
  if (failed) {
    notes.push(failed > 1
      ? `${failed} demandes ont échoué une première fois puis ont été relancées automatiquement : tous les cours sont récupérés.`
      : "1 demande a échoué une première fois puis a été relancée automatiquement : tous les cours sont récupérés.");
  }
  return notes;
}

function recommendation(kind, data, rec) {
  if (rec === "sequential") {
    return kind === "cpu"
      ? "Restez en série : avec ces réglages, aucune méthode ne fait nettement mieux (écart de moins de 15 %). Augmentez le nombre de scénarios pour voir la différence."
      : "Restez en série : avec ces réglages, aucune méthode ne fait nettement mieux. Augmentez le nombre de demandes simultanées pour gagner du temps.";
  }
  const what = kind === "cpu" ? "un calcul intensif" : "récupérer des données";
  return `Pour ${what}, utilisez la méthode ${method(rec)} : ${fmtTimes(data.results[rec].speedup)} plus rapide qu'en série.`;
}

/* --- Rendu d'un résultat ----------------------------------------------------------------------------- */

function extraLine(kind, value) {
  if (kind === "cpu") return value.var_eur !== undefined ? `Perte maximale : ${nf.eur.format(value.var_eur)}` : "";
  const parts = [];
  if (value.quotes !== undefined) parts.push(`${value.quotes} cours récupérés`);
  if (value.failed_attempts) parts.push(`${value.failed_attempts} relance${value.failed_attempts > 1 ? "s" : ""}`);
  return parts.join(" · ");
}

function barChart(kind, block, rec) {
  const entries = Object.entries(block.results);
  const max = Math.max(...entries.map(([, v]) => v.seconds)) || 1;
  const chart = el("div", { class: "bars", role: "list", "aria-label": "Durée par méthode" });
  for (const [name, value] of entries) {
    const best = name === rec;
    const gainText = name === "sequential" ? "Méthode de référence" : `${fmtGain(value.speedup)} par rapport à la série`;
    const row = el("div", {
      class: "bar-row", role: "listitem", tabindex: "0",
      "aria-label": `${method(name)} : ${fmtSeconds(value.seconds)}, ${gainText}${best ? ", méthode recommandée" : ""}`,
    },
      el("span", { class: "bar-label", text: method(name) }),
      el("span", { class: "bar-track" },
        el("span", { class: `bar${best ? " is-best" : ""}`, style: `width:${(value.seconds / max) * 100}%` })),
      el("span", { class: `bar-value${best ? " is-best" : ""}` }, fmtSeconds(value.seconds),
        el("span", { class: "x", text: fmtGain(value.speedup) })),
    );
    attachTooltip(row, () => [
      el("div", { class: "tt-value", text: fmtSeconds(value.seconds) }),
      el("div", { class: "tt-name" }, el("span", { class: `tt-key${best ? " is-best" : ""}` }), method(name), best ? " · recommandée" : ""),
      el("div", { class: "tt-extra", text: gainText }),
      extraLine(kind, value) ? el("div", { class: "tt-extra", text: extraLine(kind, value) }) : null,
    ]);
    chart.append(row);
  }
  return [chart, el("div", { class: "legend" },
    el("span", {}, el("i", { class: "best" }), "Méthode recommandée"),
    el("span", {}, el("i"), "Les autres méthodes"))];
}

function valuesTable(kind, block) {
  const head = kind === "cpu" ? ["Méthode", "Durée", "Gain", "Perte maximale"] : ["Méthode", "Durée", "Gain", "Cours", "Relances"];
  const rows = Object.entries(block.results).map(([name, v]) => el("tr", {},
    el("th", { scope: "row", text: method(name) }),
    el("td", { class: "num", "data-label": head[1], text: fmtSeconds(v.seconds) }),
    el("td", { class: "num", "data-label": head[2], text: fmtGain(v.speedup) }),
    kind === "cpu"
      ? el("td", { class: "num", "data-label": head[3], text: v.var_eur !== undefined ? nf.eur.format(v.var_eur) : "—" })
      : [el("td", { class: "num", "data-label": head[3], text: v.quotes ?? "—" }),
         el("td", { class: "num", "data-label": head[4], text: v.failed_attempts ?? "—" })],
  ));
  return el("div", { class: "table-scroll" }, el("table", { class: "data compact stack" },
    el("thead", {}, el("tr", {}, head.map((h, i) => el("th", { scope: "col", class: i ? "num" : null, text: h })))),
    el("tbody", {}, rows)));
}

function statTile(label, value, note, highlight = false) {
  return el("div", { class: `stat${highlight ? " highlight" : ""}` },
    el("div", { class: "stat-label", text: label }),
    el("div", { class: "stat-value", text: value }),
    note ? el("div", { class: "stat-note", text: note }) : null);
}

function statTiles(kind, data, rec) {
  const seq = data.results.sequential;
  const tiles = [statTile("Méthode recommandée", method(rec),
    rec === "sequential" ? "aucune ne gagne plus de 15 %" : `${fmtGain(data.results[rec].speedup)} par rapport à la série`, true)];
  if (kind === "cpu") {
    tiles.push(statTile(`Perte maximale à ${fmtPercent(data.params.level)}`, nf.eur.format(seq.var_eur), "sur une journée"));
    tiles.push(statTile("Durée en série", fmtSeconds(seq.seconds)));
  } else {
    tiles.push(statTile("Cours récupérés", `${seq.quotes} / ${data.params.symbols}`, "par méthode"));
    tiles.push(statTile("Relances automatiques", String(seq.failed_attempts), data.params.flaky ? "incidents simulés" : "incidents désactivés"));
  }
  return el("div", { class: "stats" }, tiles);
}

function renderLive(kind, data) {
  const notes = kind === "cpu" ? readCpu(data) : readIo(data);
  const rec = recommended(kind, data, data.environment);
  return [
    el("p", { class: "result-task", text: describeParams(kind, data.params) }),
    statTiles(kind, data, rec),
    el("div", { class: "reco", role: "note" }, icon(ICON_STAR),
      el("div", {}, el("strong", { text: "Recommandation" }), recommendation(kind, data, rec))),
    Object.keys(data.unavailable || {}).length
      ? el("div", { class: "alert info", role: "note",
          text: `Non mesuré sur ce serveur : ${Object.keys(data.unavailable).map(method).join(", ")}. L'hébergement ne permet pas de lancer plusieurs moteurs.` })
      : null,
    el("p", { class: "chart-caption", text: "Durée par méthode (plus court = mieux)" }),
    ...barChart(kind, data, rec),
    el("p", { class: "notes-title", text: "À retenir" }),
    el("ul", { class: "notes" }, notes.map((n) => el("li", { text: n }))),
    el("details", { class: "more" }, el("summary", { text: "Voir le tableau des valeurs" }), valuesTable(kind, data)),
    el("div", { class: "result-actions" },
      el("a", { class: "btn outline", href: "/historique", "data-link": "" }, "Voir l'historique")),
  ];
}

/* --- Lancement d'une mesure ------------------------------------------------------------------------------ */

function formQuery(form) {
  const params = new URLSearchParams();
  for (const input of form.querySelectorAll("input, select")) {
    params.set(input.name, input.type === "checkbox" ? String(input.checked) : input.value);
  }
  return params.toString();
}

async function runMeasure(kind) {
  const form = $(`#${kind}-form`), box = $(`#${kind}-result`);
  const button = form.querySelector("button[type=submit]");
  const label = button.querySelector(".label");
  const idle = label.textContent;
  const started = performance.now();
  const timer = setInterval(() => {
    label.textContent = `En cours… ${nf.dec1.format((performance.now() - started) / 1000)} s`;
  }, 100);
  button.disabled = true;
  button.classList.add("is-running");
  box.classList.add("is-stale");
  try {
    const data = await getJSON(`/api/benchmark/${kind}?${formQuery(form)}`);
    box.replaceChildren(...renderLive(kind, data));
    addToHistory(kind, data);
    // Sur téléphone, le résultat est sous le formulaire : on l'amène à l'écran.
    if (matchMedia("(max-width: 980px)").matches) box.closest(".result-card").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    box.replaceChildren(el("div", { class: "alert error", role: "alert", text: `La mesure n'a pas abouti. ${error.message}` }));
  } finally {
    clearInterval(timer);
    label.textContent = idle;
    button.disabled = false;
    button.classList.remove("is-running");
    box.classList.remove("is-stale");
  }
}

function setupForms() {
  for (const kind of ["cpu", "io"]) {
    $(`#${kind}-form`).addEventListener("submit", (e) => { e.preventDefault(); runMeasure(kind); });
  }
}

/* --- Historique ------------------------------------------------------------------------------------------- */

const HISTORY_KEY = "rcl-history";
const HISTORY_MAX = 30;

function describeParams(kind, p) {
  if (!p) return "";
  if (kind === "cpu") {
    return `${p.chunks} lot${p.chunks > 1 ? "s" : ""} de ${nf.int.format(p.paths)} scénarios, ${p.workers} tâche${p.workers > 1 ? "s" : ""} simultanée${p.workers > 1 ? "s" : ""}, confiance ${fmtPercent(p.level)}${p.repeat > 1 ? `, ${p.repeat} essais` : ""}`;
  }
  return `${p.symbols} cours, ${p.workers} demande${p.workers > 1 ? "s" : ""} simultanée${p.workers > 1 ? "s" : ""}, réponse en ${fmtSeconds(p.latency)}${p.flaky ? ", avec incidents" : ""}`;
}

function addToHistory(kind, data) {
  const entries = store.get(HISTORY_KEY, []);
  entries.unshift({ time: new Date().toISOString(), kind, params: data.params, environment: data.environment,
    fastest: data.fastest, results: data.results });
  store.set(HISTORY_KEY, entries.slice(0, HISTORY_MAX));
}

function renderHistory() {
  const entries = store.get(HISTORY_KEY, []);
  $("#history-body").replaceChildren(...entries.map((e) => {
    const date = new Date(e.time);
    const rec = recommended(e.kind, e, e.environment);
    // data-label : intitulé affiché devant chaque valeur quand le tableau devient une fiche (téléphone).
    return el("tr", {},
      el("td", { class: "num", "data-label": "Date", text: `${date.toLocaleDateString("fr-FR")} ${date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}` }),
      el("td", { "data-label": "Opération", text: OPERATIONS[e.kind] || e.kind }),
      el("td", { class: "params-cell", "data-label": "Réglages", text: describeParams(e.kind, e.params) }),
      el("td", { class: "num", "data-label": "Durée en série", text: fmtSeconds(e.results.sequential.seconds) }),
      el("td", { "data-label": "Recommandée", text: method(rec) }),
      el("td", { class: "num", "data-label": "Gain", text: fmtGain(e.results[rec].speedup) }));
  }));
  const empty = entries.length === 0;
  $("#history-empty").hidden = !empty;
  $("#history-body").closest(".table-scroll").hidden = empty;
  for (const id of ["#export-csv", "#export-json", "#clear-history"]) $(id).disabled = empty;
}

function download(filename, type, content) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = el("a", { href: url, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function exportCSV() {
  const rows = [["date", "operation", "reglages", "methode", "duree_s", "gain", "serveur", "mode"]];
  for (const e of store.get(HISTORY_KEY, [])) {
    for (const [name, v] of Object.entries(e.results)) {
      rows.push([new Date(e.time).toLocaleString("fr-FR"), OPERATIONS[e.kind] || e.kind, describeParams(e.kind, e.params),
        method(name), nf.dec2.format(v.seconds), nf.dec2.format(v.speedup),
        e.environment ? serverLine(e.environment) : "", e.environment ? serverMode(e.environment) : ""]);
    }
  }
  const csv = rows.map((r) => r.map((c) => `"${String(c).replaceAll('"', '""')}"`).join(";")).join("\r\n");
  download("mesures-risk-concurrency-lab.csv", "text/csv;charset=utf-8", "﻿" + csv);  // BOM : accents corrects dans Excel
}

function setupHistory() {
  $("#export-csv").addEventListener("click", exportCSV);
  $("#export-json").addEventListener("click", () =>
    download("sauvegarde-risk-concurrency-lab.json", "application/json", JSON.stringify(store.get(HISTORY_KEY, []), null, 2)));
  $("#clear-history").addEventListener("click", () => {
    if (confirm("Effacer tout l'historique de ce navigateur ?")) { store.set(HISTORY_KEY, []); renderHistory(); }
  });
}

/* --- Résultats de référence ----------------------------------------------------------------------------------- */

let referenceData = null;
let referenceRendered = false;
const fetchReference = async () => (referenceData ??= await getJSON("/api/reference"));

/** Bandeau d'accueil : mini-graphique des gains d'un vrai résultat de référence. */
async function loadHeroPreview() {
  try {
    const report = (await fetchReference()).find((r) => r.cpu_bound);
    if (!report) return;
    const block = report.cpu_bound, env = report.environment;
    const rec = recommended("cpu", block, env);
    const maxGain = Math.max(...Object.values(block.results).map((v) => v.speedup)) || 1;
    const bars = el("div", { class: "preview-bars", role: "list", "aria-label": "Gain par méthode" });
    for (const [name, v] of Object.entries(block.results)) {
      const best = name === rec;
      bars.append(el("span", { class: "pl", text: method(name) }),
        el("span", { class: "pt" }, el("span", { class: `pb${best ? " is-best" : ""}`, style: `width:${(v.speedup / maxGain) * 100}%` })),
        el("span", { class: `pv${best ? " is-best" : ""}`, text: fmtGain(v.speedup) }));
    }
    $("#hero-aside").replaceChildren(
      el("p", { class: "eyebrow on-dark", text: "Résultat de référence" }),
      el("p", { class: "preview-title", text: OPERATIONS.cpu }),
      el("p", { class: "preview-sub", text: `Serveur ${env.platform.split("-")[0]}, ${env.cpu_count} cœurs · gain par rapport à la série` }),
      bars,
      el("div", { class: "preview-foot" },
        el("span", { text: rec === "sequential" ? "Méthode recommandée : En série" : `Méthode recommandée : ${method(rec)}` }),
        el("a", { href: "/references", "data-link": "" }, "Tous les résultats")));
  } catch (e) { /* aperçu facultatif : le bandeau reste lisible sans lui */ }
}

async function loadReference() {
  if (referenceRendered) return;
  const list = $("#reference-list");
  try {
    const reports = await fetchReference();
    referenceRendered = true;
    if (!reports.length) {
      list.replaceChildren(el("p", { class: "muted", text: "Aucun résultat de référence n'a encore été enregistré." }));
      return;
    }
    list.replaceChildren(...reports.map((r) => {
      const env = r.environment;
      const card = el("article", { class: "card ref-card" },
        el("p", { class: "eyebrow", text: serverMode(env) }),
        el("h2", { text: `Serveur ${env.platform.split("-")[0]}, ${env.cpu_count} cœurs` }),
        el("p", { class: "ref-sub", text: env.gil_enabled
          ? "Version habituelle de Python : un calcul à la fois par moteur."
          : "Version spéciale de Python : le multi-tâches peut calculer en parallèle." }));
      for (const [kind, key] of [["cpu", "cpu_bound"], ["io", "io_bound"]]) {
        const block = r[key];
        if (!block) continue;
        const rec = recommended(kind, block, env);
        card.append(el("div", { class: "ref-block" },
          el("h3", { text: OPERATIONS[kind] }),
          el("p", { class: "result-task", text: rec === "sequential"
            ? "Méthode recommandée : En série (aucune ne gagne plus de 15 %)"
            : `Méthode recommandée : ${method(rec)} (${fmtGain(block.results[rec].speedup)})` }),
          ...barChart(kind, block, rec),
          el("details", { class: "more" }, el("summary", { text: "Voir le tableau des valeurs" }), valuesTable(kind, block))));
      }
      return card;
    }));
  } catch (e) {
    list.replaceChildren(el("div", { class: "alert error", text: `Impossible de charger les résultats. ${e.message}` }));
  }
}

/* --- Suivi de l'activité --------------------------------------------------------------------------------------- */

async function loadActivity() {
  try {
    const state = await getJSON("/api/decorators");
    const all = state.timings.reduce((acc, t) => ({ n: acc.n + t.count, total: acc.total + t.mean_s * t.count }), { n: 0, total: 0 });
    $("#activity-stats").replaceChildren(
      statTile("Demandes de cours", nf.int.format(state.fetch_quote_calls), "en série et multi-tâches"),
      statTile("Relances automatiques", nf.int.format(state.retries), "après un incident", state.retries > 0),
      statTile("Temps de réponse moyen", all.n ? fmtMs(all.total / all.n) : "—", "toutes méthodes confondues"));
    const body = $("#activity-body");
    if (!state.timings.length) {
      body.replaceChildren(el("tr", {}, el("td", { colspan: "4" },
        "Aucune activité pour l'instant. ", el("a", { href: "/cours", "data-link": "" }, "Lancez une récupération de cours"), ".")));
      return;
    }
    body.replaceChildren(...state.timings.map((t) => el("tr", {},
      el("th", { scope: "row", text: ACTIVITY[t.function] || t.function }),
      el("td", { class: "num", "data-label": "Exécutions", text: nf.int.format(t.count) }),
      el("td", { class: "num", "data-label": "Temps moyen", text: fmtMs(t.mean_s) }),
      el("td", { class: "num", "data-label": "Temps maximum", text: fmtMs(t.max_s) }))));
  } catch (e) {
    $("#activity-stats").replaceChildren(el("div", { class: "alert error", text: `Impossible de lire l'activité. ${e.message}` }));
  }
}

/* --- Démarrage ----------------------------------------------------------------------------------------------- */

document.addEventListener("DOMContentLoaded", () => {
  tooltipNode = $("#tooltip");
  setupMenu();
  setupTheme();
  setupFields();
  setupForms();
  setupHistory();
  $("#refresh-activity").addEventListener("click", loadActivity);
  setupRouter();
  loadServer();
  loadHeroPreview();
});
