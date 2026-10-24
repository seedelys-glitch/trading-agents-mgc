// Bureau virtuel de l'université : tout ce qui s'affiche vient de l'API (/api/...), relue toutes les 2 secondes.
// Aucune animation sans une mission réellement en cours ; aucun lien sans un vrai message entre deux agents.
"use strict";

const NS = "http://www.w3.org/2000/svg";
const ROLES = { documentaliste: "Documentaliste", chercheur: "Chercheur", professeur: "Professeur",
  connaissances: "Gestionnaire des connaissances" };
const PHASES = { recherche: "recherche", analyse: "analyse", redaction: "rédaction", verification: "vérification",
  attente: "attente", reunion: "réunion" };
const STATUTS = { disponible: "disponible", travail: "au travail", attente: "file d'attente", erreur: "erreur",
  construction: "en construction", en_attente: "en attente", en_cours: "en cours", terminee: "terminée",
  annulee: "annulée", a_verifier: "à vérifier", verifie: "vérifié", rejete: "rejeté", brouillon: "brouillon",
  active: "active", pause: "en pause" };

// ?camera=1 : la « caméra » que Jarvis montre (écran du PC, appli) : seulement le bureau 3D, qui tourne lentement.
const CAMERA = new URLSearchParams(location.search).get("camera") === "1";
if (CAMERA) document.documentElement.classList.add("camera");

let etat = null, choisi = null, ongletChoisi = "mission", vue = { x: 0, y: 0, w: 1600, h: 1000 }, catalogue = [];
const pos = {};

// ------------------------------------------------------------------ outils
const $ = (s) => document.querySelector(s);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const heure = (ts) => ts ? new Date(ts * 1000).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
const duree = (s) => s < 60 ? `${Math.round(s)} s` : s < 3600 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`;
const etiquette = (s) => `<span class="etiquette ${esc(s)}">${esc(STATUTS[s] || s)}</span>`;

async function api(chemin, options = {}) {
  // adresses relatives : la même page marche en direct (127.0.0.1:8780/) et à travers Jarvis (/universite/…)
  const r = await fetch(chemin.replace(/^\//, ""), { ...options, headers: { "X-Universite": "1", ...(options.headers || {}) } });
  const corps = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(corps.erreur || `erreur ${r.status}`);
  return corps;
}
const poster = (chemin, donnees) => api(chemin, { method: "POST", body: JSON.stringify(donnees || {}),
  headers: { "Content-Type": "application/json" } });

function el(nom, attrs = {}, parent) {
  const e = document.createElementNS(NS, nom);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}

// ------------------------------------------------------------------ le hall
function placer(agents) {
  const autres = agents.filter((a) => a.n !== 14);
  // à intervalles égaux le long de l'ellipse (et non d'angle) : les bureaux des côtés ne se chevauchent plus
  const N = 720, rx = 610, ry = 370, cumul = [0];
  const pt = (k) => { const t = -Math.PI / 2 + (k * 2 * Math.PI) / N; return [800 + rx * Math.cos(t), 500 + ry * Math.sin(t)]; };
  for (let k = 1; k <= N; k++) { const [x0, y0] = pt(k - 1), [x1, y1] = pt(k); cumul.push(cumul[k - 1] + Math.hypot(x1 - x0, y1 - y0)); }
  autres.forEach((a, i) => {
    const cible = (i * cumul[N]) / autres.length;
    let k = 0; while (cumul[k] < cible) k++;
    const [x, y] = pt(k);
    pos[a.n] = { x, y };
  });
  pos[14] = { x: 800, y: 480 };
}

function dessinerBureaux(agents) {
  const g = $("#bureaux");
  g.textContent = "";
  for (const a of agents) {
    const p = pos[a.n], dir = a.n === 14, k = dir ? 1.35 : 1;
    const b = el("g", { class: `bureau ${dir ? "directeur" : ""}`, transform: `translate(${p.x} ${p.y}) scale(${k})`,
      tabindex: 0, role: "button", "data-n": a.n }, g);
    el("rect", { class: "table", x: -62, y: 12, width: 124, height: 34, rx: 6 }, b);
    el("rect", { class: "ecran", x: -22, y: 0, width: 44, height: 22, rx: 3 }, b);
    el("circle", { class: "halo", r: 30, cy: -26 }, b);
    el("circle", { class: "avatar", r: 30, cy: -26 }, b);
    el("text", { class: "initiales", y: -26 }, b).textContent = a.court;
    el("circle", { r: 10, cx: 26, cy: -50, fill: "#0b0b0d", stroke: "#4a3d24" }, b);
    el("text", { class: "num", x: 26, y: -50 }, b).textContent = a.n;
    Object.keys(ROLES).forEach((r, i) => {
      const s = el("circle", { class: "soutien", "data-role": r, r: 6, cx: -27 + i * 18, cy: 60 }, b);
      el("title", {}, s).textContent = ROLES[r];
    });
    el("text", { class: "nom", y: 86 }, b).textContent = a.nom;
    el("text", { class: "sous", y: 104 }, b);
    const t = el("title", {}, b);
    t.textContent = a.nom;
    b.addEventListener("click", () => ouvrirAgent(a.n));
    b.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); ouvrirAgent(a.n); } });
  }
}

function majHall() {
  for (const a of etat.agents) {
    const b = document.querySelector(`.bureau[data-n="${a.n}"]`);
    if (!b) continue;
    b.classList.remove("disponible", "travail", "attente", "erreur", "construction");
    b.classList.add(a.statut);
    b.classList.toggle("choisi", choisi === a.n);
    let sous = STATUTS[a.statut];
    if (a.mission) sous = `${PHASES[a.mission.phase] || a.mission.phase} — ${ROLES[a.mission.role] || "…"}`;
    else if (a.file) sous += ` (${a.file})`;
    b.querySelector(".sous").textContent = sous;
    b.querySelector(":scope > title").textContent = `${a.nom} — ${a.mission ? a.mission.etape : STATUTS[a.statut]}`;
    b.querySelectorAll(".soutien").forEach((s) => s.classList.toggle("actif", !!a.mission && a.mission.role === s.dataset.role));
  }
  if (window.majPlateau) window.majPlateau(etat, choisi);
  const g = $("#liens");
  g.textContent = "";
  for (const l of etat.liens) {
    const a = pos[l.de], b = pos[l.a];
    if (!a || !b || l.de === l.a) continue;
    const mx = (a.x + b.x) / 2 + (b.y - a.y) * 0.15, my = (a.y + b.y) / 2 - (b.x - a.x) * 0.15;
    const p = el("path", { class: `lien ${esc(l.genre)}`, d: `M${a.x},${a.y - 26} Q${mx},${my} ${b.x},${b.y - 26}`,
      "marker-end": "url(#fleche)" }, g);
    el("title", {}, p).textContent = `${l.n} message(s) « ${l.genre} » de l'agent ${l.de} à l'agent ${l.a}, le dernier à ${heure(l.ts)}`;
  }
}

function majVoyants() {
  const m = etat.moteur, ia = etat.ia, c = etat.compteurs;
  const v = [
    [m.en_marche ? "ok" : "ko", `Moteur : <b>${m.en_marche ? `${m.ouvriers} ouvrier(s)` : "arrêté"}</b>`],
    [ia.joignable ? "ok" : "attention", `IA locale : <b>${ia.joignable ? (ia.active ? "LM Studio prêt" : "désactivée") : "LM Studio absent"}</b>` +
      (ia.joignable ? ` · ${ia.appels_du_jour}/${ia.budget} appels` : "")],
    [c.jeux ? "ok" : "attention", `Données : <b>${c.jeux} jeu(x)</b>`],
    ["", `File : <b>${c.en_cours} en cours, ${c.attente} en attente</b>`],
    ["", `Documents : <b>${c.documents}</b>`],
    ["", `Boucles actives : <b>${c.boucles}</b>`],
  ];
  $("#voyants").innerHTML = v.map(([cl, t]) => `<span class="voyant ${cl}">${t}</span>`).join("");
}

let dernierJournal = 0;
async function majJournal() {
  if (etat.dernier_evenement === dernierJournal) return;
  const ev = await api(`/api/evenements?apres=0`);
  dernierJournal = etat.dernier_evenement;
  const e = ev[0];
  $("#journal").innerHTML = e ? `<b>${heure(e.ts)}</b> · <span class="${esc(e.niveau)}">${esc(e.message)}</span>` : "Aucun événement pour l'instant.";
}

async function rafraichir() {
  try {
    etat = await api("/api/etat");
    if (!$("#bureaux").childNodes.length) { placer(etat.agents); dessinerBureaux(etat.agents); }
    majHall(); majVoyants(); await majJournal();
    if (CAMERA) majCamera();
    if (choisi && !$("#panneau").hidden) await majPanneau(false);
  } catch (e) {
    $("#voyants").innerHTML = `<span class="voyant ko">Université injoignable : <b>${esc(e.message)}</b></span>`;
  }
}

// Bandeau de la caméra : uniquement des compteurs réels de /api/etat
function majCamera() {
  let b = $("#cam-bandeau");
  if (!b) { b = document.createElement("div"); b.id = "cam-bandeau"; document.body.appendChild(b); }
  const n = (s) => etat.agents.filter((a) => a.statut === s).length;
  const parts = [[n("travail"), "au travail"], [n("attente"), "en attente"], [n("erreur"), "en erreur"]].filter((x) => x[0]);
  b.innerHTML = `<i class="rec"></i><b>Université MGC</b><span>${parts.length ? parts.map((x) => `${x[0]} ${x[1]}`).join(" · ") : "aucun agent au travail"}</span>`;
}

// ------------------------------------------------------------------ zoom et déplacement
function appliquerVue() {
  $("#hall").setAttribute("viewBox", `${vue.x} ${vue.y} ${vue.w} ${vue.h}`);
  const r = $("#hall").getBoundingClientRect(), echelle = Math.min(r.width / vue.w, r.height / vue.h);
  $("#hall").classList.toggle("proche", echelle >= 1.2);     // assez près pour lire les écrans des postes
}
function zoomer(f, cx = vue.x + vue.w / 2, cy = vue.y + vue.h / 2) {
  if (window.zoom3d && window.zoom3d(f)) return;
  const w = Math.min(2400, Math.max(300, vue.w / f)), h = (w * 1000) / 1600;
  vue = { x: cx - ((cx - vue.x) * w) / vue.w, y: cy - ((cy - vue.y) * h) / vue.h, w, h };
  appliquerVue();
}
function allerA(nom) {
  if (window.vue3d && window.vue3d(nom)) return;
  const enBureau = window.modePlateau && window.modePlateau() === "bureau";
  const plateau = enBureau ? (nom === "directeur" ? window.cadreDirecteur() : window.cadreEnsemble()) : null;
  vue = plateau || (nom === "directeur" ? { x: 450, y: 260, w: 700, h: 437.5 } : { x: 0, y: 0, w: 1600, h: 1000 });
  appliquerVue();
}
function pointSvg(e) {
  const r = $("#hall").getBoundingClientRect(), s = Math.max(vue.w / r.width, vue.h / r.height);
  return { x: vue.x + (e.clientX - r.left - (r.width - vue.w / s) / 2) * s, y: vue.y + (e.clientY - r.top - (r.height - vue.h / s) / 2) * s, s };
}
function brancherZoom() {
  const svg = $("#hall");
  svg.addEventListener("wheel", (e) => { e.preventDefault(); const p = pointSvg(e); zoomer(e.deltaY < 0 ? 1.15 : 0.87, p.x, p.y); }, { passive: false });
  let depart = null;
  svg.addEventListener("pointerdown", (e) => { if (e.target.closest(".bureau, .poste")) return; depart = { e, v: { ...vue }, s: pointSvg(e).s }; svg.classList.add("glisse"); svg.setPointerCapture(e.pointerId); });
  svg.addEventListener("pointermove", (e) => { if (!depart) return; vue.x = depart.v.x - (e.clientX - depart.e.clientX) * depart.s; vue.y = depart.v.y - (e.clientY - depart.e.clientY) * depart.s; appliquerVue(); });
  const fin = () => { depart = null; svg.classList.remove("glisse"); };
  svg.addEventListener("pointerup", fin); svg.addEventListener("pointercancel", fin);
  document.querySelectorAll(".zoom [data-zoom]").forEach((b) => b.addEventListener("click", () => zoomer(+b.dataset.zoom)));
  document.querySelectorAll(".zoom [data-vue]").forEach((b) => b.addEventListener("click", () => allerA(b.dataset.vue)));
}

// ------------------------------------------------------------------ panneau d'un agent
async function ouvrirAgent(n) {
  choisi = n; ongletChoisi = window.rendreEspace ? "espace" : "mission";
  $("#panneau").hidden = false;
  await majPanneau(true);
  majHall();
}

async function majPanneau(premier) {
  const [f, esp] = await Promise.all([api(`/api/agent/${choisi}`),
    window.rendreEspace ? api(`/api/agent/${choisi}/espace`) : null]);
  const a = etat.agents.find((x) => x.n === choisi);
  const onglets = { ...(esp ? { espace: "Son espace" } : {}), mission: "Mission", taches: `Tâches (${f.missions.length})`, documents: `Documents (${f.documents.length})`,
    soutiens: "Soutiens", historique: "Historique" };
  const contenu = {
    espace: () => window.rendreEspace(esp),
    mission: () => `
      <div class="bloc"><h3>Mission</h3>${esc(f.mission)}</div>
      ${a.mission ? `<div class="bloc"><h3>En ce moment</h3>${esc(a.mission.titre)}<br><span class="doux">Étape : ${esc(a.mission.etape)} — depuis ${duree(etat.maintenant - a.mission.battement)}</span></div>` : ""}
      <div class="bloc"><h3>Ce qu'il sait réellement faire</h3>${f.catalogue.length ? f.catalogue.map((c) =>
        `${esc(c.titre)} ${c.interne ? '<span class="doux">(sur demande d\'un autre agent)</span>' : `<button class="lienbouton" data-lancer="${esc(c.type)}">lancer</button>`}`).join("<br>")
        : '<span class="doux">Rien pour l\'instant : cet agent est en construction. Aucune activité n\'est simulée.</span>'}</div>
      <div class="bloc"><h3>Outils autorisés</h3>${f.outils.map(esc).join(" · ")}</div>
      <div class="bloc"><h3>Critères de qualité</h3>${f.qualite.map(esc).join("<br>")}</div>
      <div class="bloc"><h3>Escalade</h3>${esc(f.escalade)}</div>
      <div class="bloc"><h3>Règles communes</h3>${f.regles.map(esc).join("<br>")}</div>`,
    taches: () => f.missions.length ? `<ul class="liste">${f.missions.map((m) => `<li>${etiquette(m.statut)} <b>${esc(m.titre)}</b>
        <br><small>n° ${m.id} · demandée par ${esc(m.demandeur)} le ${heure(m.cree)}${m.tentatives > 1 ? ` · ${m.tentatives} essais` : ""}
        ${m.erreur ? `<br>${esc(m.erreur)}` : ""}</small>
        ${m.statut === "en_attente" ? ` <button class="lienbouton" data-annuler="${m.id}">annuler</button>` : ""}
        <button class="lienbouton" data-mission="${m.id}">détail</button></li>`).join("")}</ul>` : '<p class="doux">Aucune mission.</p>',
    documents: () => f.documents.length ? `<ul class="liste">${f.documents.map((d) => `<li>${etiquette(d.statut)} <a data-doc="${d.id}">${esc(d.titre)}</a>
        <br><small>n° ${d.id} · ${esc(d.genre)} · ${heure(d.cree)}${d.verifie_par ? ` · vérifié par l'agent ${d.verifie_par}` : ""}</small></li>`).join("")}</ul>`
      : '<p class="doux">Aucun document.</p>',
    soutiens: () => `<div class="soutiens">${f.soutiens.map((s) => {
        const e = f.soutiens_etat[s.role];
        return `<div class="bloc"><h3>${esc(s.nom)}</h3><span class="doux">${esc(s.mission)}</span><br>
          ${e ? `${etiquette(e.statut === "en_cours" ? "en_cours" : e.statut === "faite" ? "terminee" : e.statut)} ${esc(e.libelle)}<br><small class="doux">${heure(e.debut)} · mission ${e.mission}</small>`
            : '<small class="doux">N\'a encore jamais travaillé.</small>'}</div>`;
      }).join("")}</div>`,
    historique: () => `<ul class="liste">${f.etapes.map((e) => `<li>${etiquette(e.statut === "faite" ? "terminee" : e.statut)} ${esc(ROLES[e.role] || e.role)} : ${esc(e.libelle)}
        <br><small>${heure(e.debut)}${e.fin ? ` · ${duree(e.fin - e.debut)}` : ""} · mission ${e.mission}</small></li>`).join("")
      }${f.messages.map((m) => `<li>✉ ${m.de === f.n ? `vers l'agent ${m.a}` : `de l'agent ${m.de}`} (${esc(m.genre)}) : ${esc(m.contenu)}<br><small>${heure(m.ts)}</small></li>`).join("")}</ul>
      ${!f.etapes.length && !f.messages.length ? '<p class="doux">Rien encore.</p>' : ""}`,
  };
  const zone = $("#panneau-contenu");
  const defil = $("#panneau").scrollTop;
  zone.innerHTML = `<h2>${f.n}. ${esc(f.nom)}</h2>${etiquette(a.statut)}
    ${f.competences_branchees.length ? "" : '<span class="doux"> aucune compétence branchée</span>'}
    <div class="onglets">${Object.entries(onglets).map(([k, t]) => `<button data-onglet="${k}" class="${k === ongletChoisi ? "actif" : ""}">${t}</button>`).join("")}</div>
    <div>${contenu[ongletChoisi]()}</div>`;
  if (ongletChoisi === "espace") window.apresEspace(zone, esp);
  if (!premier) $("#panneau").scrollTop = defil;
}

$("#panneau").addEventListener("click", async (e) => {
  const t = e.target;
  if (t.dataset.onglet) { ongletChoisi = t.dataset.onglet; await majPanneau(true); }
  else if (t.dataset.doc) voirDocument(+t.dataset.doc);
  else if (t.dataset.mission) voirMission(+t.dataset.mission);
  else if (t.dataset.annuler) { await poster(`/api/mission/${t.dataset.annuler}/annuler`); await rafraichir(); }
  else if (t.dataset.lancer) formulaireDemande(t.dataset.lancer, false);
});
$("#fermer-panneau").addEventListener("click", () => { $("#panneau").hidden = true; choisi = null; majHall(); });

// ------------------------------------------------------------------ fenêtres
function modale(titre, html) {
  $("#modale-titre").textContent = titre;
  $("#modale-corps").innerHTML = html;
  if (!$("#modale").open) $("#modale").showModal();
  return $("#modale-corps");
}
const avis = (corps, texte, ok) => corps.insertAdjacentHTML("afterbegin", `<div class="message ${ok ? "ok" : "ko"}">${esc(texte)}</div>`);

async function voirDocument(id) {
  const d = await api(`/api/document/${id}`);
  const sources = (d.sources || []).map((s) => s.unite ? `jeu ${s.jeu}, ${s.n} bougies ${s.unite}${s.reconstruite_depuis ? ` (reconstruites depuis ${s.reconstruite_depuis})` : ""}`
    : s.document ? `document ${s.document}` : s.jeu ? `jeu ${s.jeu}` : JSON.stringify(s));
  modale(d.titre, `${etiquette(d.statut)} <span class="doux">n° ${d.id} · agent ${d.agent} · ${heure(d.cree)}${d.verifie_par ? ` · vérifié par l'agent ${d.verifie_par}` : ""}</span>
    <pre class="doc">${esc(d.contenu)}</pre>${sources.length ? `<p class="doux">Sources : ${sources.map(esc).join(" ; ")}</p>` : ""}`);
}

async function voirMission(id) {
  const m = await api(`/api/mission/${id}`);
  modale(m.titre, `${etiquette(m.statut)} <span class="doux">n° ${m.id} · agent ${m.agent} · ${m.tentatives} essai(s)</span>
    ${m.erreur ? `<div class="message ko">${esc(m.erreur)}</div>` : ""}
    <ul class="liste">${m.etapes.map((e) => `<li>${etiquette(e.statut === "faite" ? "terminee" : e.statut)} ${esc(ROLES[e.role] || e.role)} : ${esc(e.libelle)}
      <br><small>${heure(e.debut)}${e.fin ? ` · ${duree(e.fin - e.debut)}` : ""}${e.detail ? ` · ${esc(JSON.stringify(e.detail))}` : ""}</small></li>`).join("")}</ul>
    ${m.resultat && m.resultat.document ? `<button data-doc-m="${m.resultat.document}">Voir le document produit</button>` : ""}`);
  const b = document.querySelector("[data-doc-m]");
  if (b) b.addEventListener("click", () => voirDocument(+b.dataset.docM));
}

function champJeu(jeux) {
  return jeux.length ? `<select name="jeu">${jeux.map((j) => `<option value="${j.id}">${esc(j.nom)} — ${esc(j.source)} (${Object.entries(j.unites).map(([u, x]) => `${x.n} ${u}`).join(", ") || "vide"})</option>`).join("")}</select>`
    : '<span class="doux">Aucun jeu de bougies : importez d\'abord des données (bouton « Données »).</span>';
}

const COMMUNS = ["jeu", "instant"];
async function formulaireDemande(typeChoisi, parDirecteur = true) {
  const [jeux] = await Promise.all([api("/api/jeux")]);
  const types = catalogue.filter((c) => !c.interne && c.agent !== 14 || c.type === "synthese_directeur");
  const corps = modale(parDirecteur ? "Demander au directeur" : "Lancer une mission", `
    <div class="champ"><label>Ce que vous demandez</label><select name="type">${types.map((c) =>
      `<option value="${esc(c.type)}" ${c.type === typeChoisi ? "selected" : ""}>${esc(c.titre)} — agent ${c.agent}</option>`).join("")}</select></div>
    <div class="champ" data-pour="jeu"><label>Jeu de bougies</label>${champJeu(jeux)}</div>
    <div class="champ" data-pour="instant"><label>Instant analysé (vide = maintenant ; une date passée = replay sans regarder la suite)</label><input type="datetime-local" name="instant"></div>
    <div data-autres></div>
    <div class="champ"><label>Consigne (facultatif)</label><input name="consigne" maxlength="300" placeholder="ex. regarde la séance de Londres"></div>
    <label class="ligne"><input type="checkbox" name="directeur" ${parDirecteur ? "checked" : ""}> passer par le directeur (il confie la mission au bon agent)</label>
    <p class="ligne" style="margin-top:14px"><button class="principal" data-envoyer>Envoyer</button></p>`);
  const maj = () => {
    const t = corps.querySelector("[name=type]").value;
    const besoin = (catalogue.find((c) => c.type === t) || {}).params || {};
    corps.querySelectorAll("[data-pour]").forEach((d) => { d.hidden = !(d.dataset.pour in besoin); });
    corps.querySelector("[data-autres]").innerHTML = Object.entries(besoin).filter(([k]) => !COMMUNS.includes(k)).map(([k, aide]) =>
      `<div class="champ"><label>${esc(aide)}</label>${k === "sens" ? '<select data-param="sens"><option value="achat">achat</option><option value="vente">vente</option></select>'
        : `<input data-param="${esc(k)}" inputmode="decimal" maxlength="200">`}</div>`).join("");
  };
  corps.querySelector("[name=type]").addEventListener("change", maj); maj();
  corps.querySelector("[data-envoyer]").addEventListener("click", async () => {
    const t = corps.querySelector("[name=type]").value, besoin = (catalogue.find((c) => c.type === t) || {}).params || {};
    const params = {};
    const jeu = corps.querySelector("[name=jeu]");
    if ("jeu" in besoin) { if (!jeu) return avis(corps, "Il faut d'abord un jeu de bougies.", false); params.jeu = +jeu.value; }
    const inst = corps.querySelector("[name=instant]").value;
    if ("instant" in besoin && inst) params.instant = new Date(inst).getTime() / 1000;
    corps.querySelectorAll("[data-param]").forEach((c) => {
      const v = c.value.trim().replace(",", ".");
      if (v !== "") params[c.dataset.param] = c.tagName === "SELECT" || isNaN(+v) ? v : +v;
    });
    try {
      const r = await poster("/api/missions", { type: t, params, consigne: corps.querySelector("[name=consigne]").value,
        par_directeur: corps.querySelector("[name=directeur]").checked });
      avis(corps, `Mission n° ${r.mission} enregistrée. Suivez-la dans le hall.`, true);
      rafraichir();
    } catch (e) { avis(corps, e.message, false); }
  });
}

async function fenetreDonnees() {
  const jeux = await api("/api/jeux");
  const corps = modale("Données de marché", `
    <p class="doux">Seules des données réelles entrent ici. Les données temps réel viennent de NinjaTrader ; Yahoo est différé.</p>
    <div class="bloc"><h3>Importer un fichier CSV (export TradingView ou NinjaTrader)</h3>
      <div class="ligne"><input type="file" name="fichier" accept=".csv,text/csv"><input name="nom" placeholder="nom du jeu" maxlength="80"></div>
      <p class="ligne"><button data-csv>Importer le fichier</button></p></div>
    <div class="ligne"><button data-tv>Lire le dossier TradingView</button><button data-ninja>Importer depuis NinjaTrader</button><button data-yahoo>Importer Yahoo (différé)</button></div>
    <p class="doux">Dossier TradingView : déposez vos exports (graphique → « Exporter les données du graphique ») dans Documents\TradingAgents\donnees_tradingview ; les exports MGC du dossier Téléchargements sont lus aussi.</p>
    <h3 style="margin-top:16px">Jeux enregistrés</h3>
    ${jeux.length ? `<ul class="liste">${jeux.map((j) => `<li><b>${esc(j.nom)}</b> ${j.temps_reel ? etiquette("temps réel") : '<span class="etiquette">différé / historique</span>'}
      <br><small>${esc(j.source)} · ${Object.entries(j.unites).map(([u, x]) => `${u} : ${x.n} bougies (${heure(x.debut)} → ${heure(x.fin)})`).join(" · ") || "vide"}</small>
      <br><button class="lienbouton" data-controle="${j.id}">faire contrôler par le chercheur quantitatif</button></li>`).join("")}</ul>` : '<p class="doux">Aucun jeu pour l\'instant.</p>'}`);
  const action = async (fn) => { try { const r = await fn(); avis(corps, r, true); rafraichir(); } catch (e) { avis(corps, e.message, false); } };
  corps.querySelector("[data-csv]").addEventListener("click", () => action(async () => {
    const f = corps.querySelector("[name=fichier]").files[0];
    if (!f) throw new Error("Choisissez d'abord un fichier.");
    const r = await api("/api/jeux/import", { method: "POST", body: await f.text(),
      headers: { "X-Nom-Jeu": encodeURIComponent(corps.querySelector("[name=nom]").value || f.name) } });
    return `${r.ajoutees} bougies ${r.unite} importées (${r.abimees} abîmées et ${r.incoherentes} incohérentes ignorées).`;
  }));
  corps.querySelector("[data-ninja]").addEventListener("click", () => action(async () => {
    const r = await poster("/api/jeux/ninja");
    return `NinjaTrader : ${Object.entries(r.unites).map(([u, x]) => `${x.ajoutees} nouvelles bougies ${u}`).join(", ")}.`;
  }));
  corps.querySelector("[data-tv]").addEventListener("click", () => action(async () => {
    const r = await poster("/api/missions", { type: "import_tradingview", params: {} });
    return `Mission n° ${r.mission} confiée au chercheur quantitatif : il lit le dossier.`;
  }));
  corps.querySelector("[data-yahoo]").addEventListener("click", () => action(async () => {
    const r = await poster("/api/jeux/yahoo");
    return `Yahoo : ${r.ajoutees} bougies importées (différées).`;
  }));
  corps.querySelectorAll("[data-controle]").forEach((b) => b.addEventListener("click", () => action(async () => {
    const r = await poster("/api/missions", { type: "controle_donnees", params: { jeu: +b.dataset.controle } });
    return `Mission n° ${r.mission} confiée au chercheur quantitatif.`;
  })));
}

async function fenetreBoucles() {
  const [boucles, jeux] = await Promise.all([api("/api/boucles"), api("/api/jeux")]);
  const types = catalogue.filter((c) => !c.interne && c.agent !== 14);
  const corps = modale("Boucles de travail", `
    <p class="doux">Une boucle relance une mission à intervalle régulier, avec un nombre maximal d'itérations. Elle se met en pause seule après 3 erreurs de suite.</p>
    ${boucles.length ? `<ul class="liste">${boucles.map((b) => `<li>${etiquette(b.statut)} <b>${esc(b.nom)}</b> — agent ${b.responsable}
      <br><small>${b.iterations}/${b.iterations_max} itérations · toutes les ${duree(b.intervalle_s)} · prochaine ${heure(b.prochaine)}${b.derniere_erreur ? ` · dernière erreur : ${esc(b.derniere_erreur)}` : ""}</small>
      <br>${b.statut === "active" ? `<button class="lienbouton" data-b="${b.id}" data-s="pause">mettre en pause</button>` : b.statut === "pause" ? `<button class="lienbouton" data-b="${b.id}" data-s="active">reprendre</button>` : ""}
      ${b.statut !== "terminee" ? ` <button class="lienbouton" data-b="${b.id}" data-s="terminee">arrêter</button>` : ""}</li>`).join("")}</ul>` : '<p class="doux">Aucune boucle.</p>'}
    <div class="bloc"><h3>Nouvelle boucle</h3>
      <div class="champ"><label>Mission répétée</label><select name="type">${types.map((c) => `<option value="${esc(c.type)}" data-agent="${c.agent}">${esc(c.titre)}</option>`).join("")}</select></div>
      <div class="champ"><label>Jeu de bougies</label>${champJeu(jeux)}</div>
      <div class="ligne"><label>toutes les <input name="minutes" type="number" min="1" value="15" style="width:80px"> min</label>
        <label>au plus <input name="max" type="number" min="1" value="40" style="width:80px"> fois</label></div>
      <p class="ligne"><button class="principal" data-creer>Créer la boucle</button></p></div>`);
  corps.querySelectorAll("[data-b]").forEach((b) => b.addEventListener("click", async () => {
    await poster(`/api/boucle/${b.dataset.b}/${b.dataset.s}`); fenetreBoucles(); rafraichir();
  }));
  corps.querySelector("[data-creer]").addEventListener("click", async () => {
    const sel = corps.querySelector("[name=type]"), jeu = corps.querySelector("[name=jeu]");
    if (!jeu) return avis(corps, "Il faut d'abord un jeu de bougies.", false);
    try {
      await poster("/api/boucles", { nom: sel.selectedOptions[0].textContent, type: sel.value, responsable: +sel.selectedOptions[0].dataset.agent,
        objectif: "Boucle créée depuis le bureau", params: { jeu: +jeu.value }, intervalle_s: 60 * +corps.querySelector("[name=minutes]").value,
        iterations_max: +corps.querySelector("[name=max]").value });
      fenetreBoucles(); rafraichir();
    } catch (e) { avis(corps, e.message, false); }
  });
}

async function fenetreDocuments() {
  const docs = await api("/api/documents");
  const corps = modale("Documents produits", docs.length ? `<ul class="liste">${docs.map((d) => `<li>${etiquette(d.statut)} <a data-doc="${d.id}">${esc(d.titre)}</a>
    <br><small>n° ${d.id} · agent ${d.agent} · ${esc(d.genre)} · ${heure(d.cree)}</small></li>`).join("")}</ul>` : '<p class="doux">Aucun document pour l\'instant.</p>');
  corps.querySelectorAll("[data-doc]").forEach((a) => a.addEventListener("click", () => voirDocument(+a.dataset.doc)));
}

async function fenetreReglages() {
  const r = await api("/api/reglages");
  const champs = [["concurrence", "Missions en même temps", "number"], ["concurrence_ia", "Appels IA en même temps", "number"],
    ["delai_mission_s", "Délai maximal d'une mission (s)", "number"], ["tentatives_max", "Nouveaux essais après une erreur passagère", "number"],
    ["ia_appels_max_jour", "Budget d'appels IA par jour", "number"], ["ia_modele", "Modèle LM Studio (vide = celui qui est chargé)", "text"],
    ["ia_embeddings", "Modèle d'embeddings LM Studio pour la recherche par le sens (vide = recherche par mots)", "text"]];
  const corps = modale("Réglages", `${champs.map(([k, t, ty]) => `<div class="champ"><label>${t}</label><input name="${k}" type="${ty}" value="${esc(r[k])}"></div>`).join("")}
    <label class="ligne"><input type="checkbox" name="ia_commentaires" ${r.ia_commentaires ? "checked" : ""}> commentaires pédagogiques par l'IA locale (sans aucun chiffre)</label>
    <p class="doux">Le nombre de missions en même temps s'applique au prochain démarrage de l'université.</p>
    <p><button class="principal" data-ok>Enregistrer</button></p>`);
  corps.querySelector("[data-ok]").addEventListener("click", async () => {
    const m = Object.fromEntries(champs.map(([k]) => [k, corps.querySelector(`[name=${k}]`).value]));
    m.ia_commentaires = corps.querySelector("[name=ia_commentaires]").checked;
    try { await poster("/api/reglages", m); avis(corps, "Réglages enregistrés.", true); } catch (e) { avis(corps, e.message, false); }
  });
}

async function fenetreBibliotheque(recherche = "") {
  const regles = await api("/api/regles");
  const proposees = regles.filter((r) => r.statut === "proposee"), validees = regles.filter((r) => r.statut === "validee");
  const autres = regles.filter((r) => r.statut === "rejetee" || r.statut === "remplacee");
  const source = (r) => r.source && r.source.fichier ? `${esc(r.source.fichier)}, « ${esc(r.source.section)} », ligne ${r.source.ligne}${r.source.modifiee_par ? " (corrigée par toi)" : ""}` : "";
  const carte = (r, actions) => `<li>${etiquette(r.statut)} <b>${esc(r.theme)}</b> <span class="doux">v${r.version}</span>
    <pre class="doc" style="margin:6px 0">${esc(r.texte)}</pre><small class="doux">Source : ${source(r)}</small>
    ${actions ? `<div class="ligne" style="margin-top:6px"><button data-r="${r.id}" data-a="valider">Valider</button>
      <button data-r="${r.id}" data-a="corriger">Corriger</button><button data-r="${r.id}" data-a="rejeter">Rejeter</button></div>` : ""}</li>`;
  const corps = modale("Bibliothèque de connaissances", `
    <div class="ligne"><input name="q" placeholder="Chercher dans la bibliothèque (ex. stop FVG)" value="${esc(recherche)}" style="flex:1">
      <button data-chercher>Chercher</button></div>
    <div data-resultats></div>
    <div class="ligne" style="margin:12px 0"><button data-mission="extraction_regles">Lire STRATEGIE.md et proposer les règles</button>
      <button data-mission="indexation_bibliotheque">Ranger les documents vérifiés</button></div>
    <h3>À valider (${proposees.length})</h3>
    ${proposees.length ? `<ul class="liste">${proposees.map((r) => carte(r, true)).join("")}</ul>` : '<p class="doux">Rien à valider.</p>'}
    <h3>Règles validées (${validees.length})</h3>
    ${validees.length ? `<ul class="liste">${validees.map((r) => carte(r, false)).join("")}</ul>` : '<p class="doux">Aucune règle validée pour l\'instant.</p>'}
    ${autres.length ? `<details><summary>Historique : versions remplacées et règles rejetées (${autres.length})</summary><ul class="liste">${autres.map((r) => carte(r, false)).join("")}</ul></details>` : ""}`);
  const chercher = async () => {
    const q = corps.querySelector("[name=q]").value, zone = corps.querySelector("[data-resultats]");
    if (!q.trim()) { zone.innerHTML = ""; return; }
    const r = await api(`/api/recherche?q=${encodeURIComponent(q)}`);
    zone.innerHTML = `<p class="doux">${r.resultats.length} résultat(s) — recherche ${r.sens ? "par mots et par le sens" : "par mots"}</p>
      <ul class="liste">${r.resultats.map((x) => `<li><b>${esc(x.titre)}</b> ${x.statut ? etiquette(x.statut) : `<span class="doux">${esc(x.origine)}</span>`}<br><small>${esc(x.texte)}</small></li>`).join("")}</ul>`;
  };
  corps.querySelector("[data-chercher]").addEventListener("click", chercher);
  corps.querySelector("[name=q]").addEventListener("keydown", (e) => { if (e.key === "Enter") chercher(); });
  if (recherche) chercher();
  corps.querySelectorAll("[data-mission]").forEach((b) => b.addEventListener("click", async () => {
    try { const r = await poster("/api/missions", { type: b.dataset.mission, params: {} }); avis(corps, `Mission n° ${r.mission} confiée au secrétaire-auditeur. Rouvrez la bibliothèque dans un instant.`, true); rafraichir(); }
    catch (e) { avis(corps, e.message, false); }
  }));
  corps.querySelectorAll("[data-r]").forEach((b) => b.addEventListener("click", async () => {
    const li = b.closest("li");
    if (b.dataset.a === "corriger") {
      const texte = li.querySelector("pre").textContent;
      li.insertAdjacentHTML("beforeend", `<div class="champ" style="margin-top:8px"><textarea rows="5">${esc(texte)}</textarea>
        <button data-enregistrer>Proposer cette version</button></div>`);
      li.querySelector("[data-enregistrer]").addEventListener("click", async () => {
        try { await poster(`/api/regle/${b.dataset.r}/modifier`, { texte: li.querySelector("textarea").value }); fenetreBibliotheque(); }
        catch (e) { avis(corps, e.message, false); }
      });
      return;
    }
    try { await poster(`/api/regle/${b.dataset.r}/${b.dataset.a}`); fenetreBibliotheque(corps.querySelector("[name=q]").value); }
    catch (e) { avis(corps, e.message, false); }
  }));
}

// ------------------------------------------------------------------ mémoire (Scribe n° 15, Archiviste n° 16)
async function fenetreMemoire(recherche = "", dossier = "") {
  const idx = await api("/api/memoire/index");
  const corps = modale("Mémoire de l'université", `
    <p class="doux">Le Scribe note tout en blocs (agents, directeur, desk de Jarvis, sessions Claude, règles, état du projet)
      et les range par sujet ; l'Archiviste les retrouve. ${idx.total} bloc(s)${idx.dernier_passage ? `, dernier passage ${heure(idx.dernier_passage)}` : ", aucun passage pour l'instant"}.
      Copie lisible : <code>${esc(idx.dossier_fichiers)}</code></p>
    <div class="ligne">${idx.dossiers.map((d) => `<button data-dossier="${esc(d.dossier)}" class="${d.dossier === dossier ? "principal" : ""}">${esc(d.dossier)} (${d.blocs})</button>`).join("")}
      ${dossier ? '<button data-dossier="">Tous</button>' : ""}</div>
    <div class="ligne" style="margin-top:8px"><input name="q" placeholder="Chercher (ex. break-even, bouton micro, replay compte B)" value="${esc(recherche)}" style="flex:1">
      <button data-chercher>Chercher</button></div>
    <div data-resultats></div>
    <div class="ligne" style="margin:12px 0"><button data-noter>Faire noter maintenant</button>
      <button data-archiviste>Demander une réponse écrite à l'Archiviste</button></div>
    <details><summary>Sessions récentes (${idx.sessions.length})</summary><ul class="liste">${idx.sessions.map((s) => `<li><b>${esc(s.session)}</b>
      <span class="doux">${esc(s.dossier)} · ${s.blocs} bloc(s) · ${heure(s.debut)} → ${heure(s.fin)}</span></li>`).join("")}</ul></details>`);
  const zone = corps.querySelector("[data-resultats]");
  const chercher = async () => {
    const q = corps.querySelector("[name=q]").value;
    const r = await api(`/api/memoire?n=30&q=${encodeURIComponent(q)}${dossier ? `&dossier=${encodeURIComponent(dossier)}` : ""}`);
    zone.innerHTML = `<p class="doux">${r.resultats.length} bloc(s)${q.trim() ? "" : " (les plus récents)"}</p><ul class="liste">${r.resultats.map((b) => `<li>
      <a data-bloc="${b.id}"><b>${esc(b.titre)}</b></a><br><small class="doux">n° ${b.id} · ${esc(b.dossier)} · ${esc(b.session)} · ${heure(b.debut)}</small>
      <br><small>${esc(b.extrait || "")}</small></li>`).join("")}</ul>`;
    zone.querySelectorAll("[data-bloc]").forEach((a) => a.addEventListener("click", async () => {
      const b = await api(`/api/memoire/bloc/${a.dataset.bloc}`);
      const li = a.closest("li");
      if (!li.querySelector("pre")) li.insertAdjacentHTML("beforeend", `<pre class="doc" style="margin:6px 0">${esc(b.texte)}</pre>`);
    }));
  };
  corps.querySelector("[data-chercher]").addEventListener("click", chercher);
  corps.querySelector("[name=q]").addEventListener("keydown", (e) => { if (e.key === "Enter") chercher(); });
  corps.querySelectorAll("[data-dossier]").forEach((b) => b.addEventListener("click", () => fenetreMemoire(corps.querySelector("[name=q]").value, b.dataset.dossier)));
  corps.querySelector("[data-noter]").addEventListener("click", async () => {
    try { const r = await poster("/api/missions", { type: "ecriture_memoire", params: {} }); avis(corps, `Mission n° ${r.mission} confiée au Scribe. Rouvrez la mémoire dans un instant.`, true); rafraichir(); }
    catch (e) { avis(corps, e.message, false); }
  });
  corps.querySelector("[data-archiviste]").addEventListener("click", async () => {
    const q = corps.querySelector("[name=q]").value.trim();
    if (!q) { avis(corps, "Écrivez d'abord ce que vous cherchez.", false); return; }
    try { const r = await poster("/api/missions", { type: "recherche_memoire", params: { question: q, dossier } }); avis(corps, `Mission n° ${r.mission} confiée à l'Archiviste : sa réponse arrivera dans « Documents », contrôlée par l'agent 9.`, true); rafraichir(); }
    catch (e) { avis(corps, e.message, false); }
  });
  chercher();
}

// ------------------------------------------------------------------ démarrage
$("#b-demander").addEventListener("click", () => formulaireDemande("analyse_vwap_ema", true));
$("#b-donnees").addEventListener("click", fenetreDonnees);
$("#b-boucles").addEventListener("click", fenetreBoucles);
$("#b-documents").addEventListener("click", fenetreDocuments);
$("#b-reglages").addEventListener("click", fenetreReglages);
$("#b-bibliotheque").addEventListener("click", () => fenetreBibliotheque());
$("#b-memoire").addEventListener("click", () => fenetreMemoire());
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#modale").open) { $("#panneau").hidden = true; choisi = null; } });

(async () => {
  brancherZoom();
  try { catalogue = (await api("/api/agents")).catalogue; } catch (e) { /* affiché par rafraichir */ }
  await rafraichir();
  setInterval(rafraichir, 2000);
})();
