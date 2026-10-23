// Bureau immersif : le plan vient de /api/scene (zones et postes en mètres), l'état de /api/etat (via app.js).
// Vue isométrique en SVG. Rien ne bouge sans une mission réellement en cours ; un poste « en construction »
// reste vide ; les liens ne sont que de vrais messages entre agents. Le hall en cercle reste disponible.
"use strict";

const ISO = { c: Math.cos(Math.PI / 6), s: 0.5, k: 21, ox: 636, oy: 120 };
let plan = null, mode = "bureau";
const postePos = {};

function iso(x, y, z = 0) {
  return [ISO.ox + (x - y) * ISO.c * ISO.k, ISO.oy + (x + y) * ISO.s * ISO.k - z * ISO.k];
}
const pts = (liste) => liste.map((p) => iso(...p).map((v) => v.toFixed(1)).join(",")).join(" ");

function boite(g, x, y, z, l, p, h, cls) {
  const b = el("g", { class: `boite ${cls}` }, g);
  el("polygon", { class: "dessus", points: pts([[x, y, z + h], [x + l, y, z + h], [x + l, y + p, z + h], [x, y + p, z + h]]) }, b);
  el("polygon", { class: "face-y", points: pts([[x, y + p, z], [x + l, y + p, z], [x + l, y + p, z + h], [x, y + p, z + h]]) }, b);
  el("polygon", { class: "face-x", points: pts([[x + l, y, z], [x + l, y + p, z], [x + l, y + p, z + h], [x + l, y, z + h]]) }, b);
  return b;
}

// Mobilier fixe (décor, aucune activité) : il dit seulement à quoi sert la pièce.
function decor(z) {
  const o = [];
  const ajoute = (x, y, l, p, h, cls) => o.push({ prof: x + l / 2 + y + p / 2, f: (g) => boite(g, x, y, 0, l, p, h, cls) });
  if (z.cle === "reunion") {
    ajoute(z.x + 2.5, z.y + 3, 5, 2, 0.75, "meuble table-reunion");
    for (let i = 0; i < 4; i++) { ajoute(z.x + 2.9 + i * 1.2, z.y + 2.1, 0.6, 0.6, 0.45, "siege"); ajoute(z.x + 2.9 + i * 1.2, z.y + 5.3, 0.6, 0.6, 0.45, "siege"); }
  } else if (z.cle === "bibliotheque") {
    for (let i = 0; i < 4; i++) ajoute(z.x + 0.8 + i * 3.8, z.y + 0.6, 3, 0.6, 2.2, "meuble etagere");
    ajoute(z.x + 10.5, z.y + 8.5, 4, 2, 0.75, "meuble");
  } else if (z.cle === "labo") {
    ajoute(z.x + 1, z.y + 0.5, 4, 0.15, 1.9, "tableau-blanc");
    ajoute(z.x + 6.5, z.y + 1.5, 2.5, 1.2, 0.75, "meuble");
  } else if (z.cle === "donnees") {
    for (let i = 0; i < 3; i++) ajoute(z.x + 1 + i * 1.6, z.y + 0.8, 1, 1.2, 2.1, "baie");
  }
  return o;
}

function construirePlateau() {
  const g = $("#plateau");
  g.textContent = "";
  const S = plan.sol;
  el("polygon", { class: "sol-plateau", points: pts([[0, 0], [S.l, 0], [S.l, S.p], [0, S.p]]) }, g);
  const zones = el("g", { class: "zones" }, g);
  for (const z of plan.zones) {
    const zg = el("g", { class: `zone zone-${z.cle}`, "data-zone": z.cle }, zones);
    el("polygon", { class: "sol-zone", points: pts([[z.x, z.y], [z.x + z.l, z.y], [z.x + z.l, z.y + z.p], [z.x, z.y + z.p]]) }, zg);
    el("polygon", { class: "plinthe", points: pts([[z.x, z.y + z.p, 0], [z.x + z.l, z.y + z.p, 0], [z.x + z.l, z.y + z.p, -0.25], [z.x, z.y + z.p, -0.25]]) }, zg);
    el("polygon", { class: "plinthe cote", points: pts([[z.x + z.l, z.y, 0], [z.x + z.l, z.y + z.p, 0], [z.x + z.l, z.y + z.p, -0.25], [z.x + z.l, z.y, -0.25]]) }, zg);
    el("title", {}, zg).textContent = `${z.nom} — ${z.montre} (source : ${z.source})`;
  }
  // objets triés par profondeur (du fond vers l'avant)
  const objets = plan.zones.flatMap(decor);
  for (const p of plan.postes) {
    postePos[p.agent] = p;
    objets.push({ prof: p.x + p.y, f: (gg) => dessinerPoste(gg, p) });
  }
  objets.sort((a, b) => a.prof - b.prof);
  const obj = el("g", { class: "objets" }, g);
  objets.forEach((o) => o.f(obj));
  el("g", { id: "plateau-liens" }, g);
  const noms = el("g", { class: "noms-zones" }, g);
  for (const z of plan.zones) {
    const [x, y] = iso(z.x + z.l, z.y + z.p, -0.25);
    el("text", { class: "nom-zone", x, y: y + 16 }, noms).textContent = z.nom;
  }
  const etiq = el("g", { id: "plateau-etiquettes" }, g);
  for (const p of plan.postes) dessinerEtiquette(etiq, p);
  const ecrans = el("g", { id: "plateau-ecrans" }, g);
  for (const p of plan.postes) dessinerEcran(ecrans, p);
}

// Écran au-dessus de chaque poste (visible quand on s'approche) : le dernier document RÉEL de l'agent
// et, s'il a lu des bougies, la courbe des clôtures de ces mêmes bougies (fermées à l'instant analysé).
const GENRES = { analyse: "Analyse", verification: "Vérification", synthese: "Synthèse", replay: "Replay",
  donnees: "Données", risque: "Risque", macro: "Calendrier", discours: "Discours", reaction: "Réactions",
  precedents: "Précédents", bibliotheque: "Bibliothèque" };
const courbes = {};

function dessinerEcran(g, p) {
  const [x, y] = iso(p.x, p.y, 2.6);
  const e = el("g", { class: "ecran-flottant", "data-n": p.agent, transform: `translate(${(x - 48).toFixed(1)} ${(y - 76).toFixed(1)})` }, g);
  el("rect", { class: "cadre", width: 96, height: 58, rx: 4 }, e);
  el("text", { class: "l1", x: 5, y: 10 }, e);
  el("text", { class: "l2", x: 5, y: 19.5 }, e);
  el("text", { class: "l3", x: 5, y: 28.5 }, e);
  el("polyline", { class: "courbe", points: "" }, e);
  el("text", { class: "l4", x: 5, y: 54 }, e);
  e.addEventListener("click", () => ouvrirAgent(p.agent));
}

const couper = (t, n) => (t.length > n ? `${t.slice(0, n - 1)}…` : t);

async function chargerCourbe(n, doc) {
  courbes[doc.id] = { attente: true };
  try {
    const esp = await api(`/api/agent/${n}/espace`);
    const gr = esp.dernier_document && esp.dernier_document.id === doc.id ? esp.graphique : null;
    if (!gr) { courbes[doc.id] = { aucune: true }; return; }
    const r = await api(`/api/bougies?jeu=${gr.jeu}&unite=${gr.unite}&instant=${gr.instant}&n=48`);
    courbes[doc.id] = { unite: r.unite, clotures: r.bougies.map((b) => b[4]) };
  } catch { delete courbes[doc.id]; }
}

function majEcran(a) {
  const e = document.querySelector(`.ecran-flottant[data-n="${a.n}"]`);
  if (!e) return;
  const d = a.dernier_document, t = (c) => e.querySelector(c);
  e.classList.remove("verifie", "a_verifier", "rejete", "brouillon", "vide");
  e.classList.toggle("vide", !d && a.statut !== "construction");
  if (a.statut === "construction") {
    t(".l1").textContent = "En construction"; t(".l2").textContent = "aucune donnée, aucune activité"; t(".l3").textContent = "";
  } else if (!d) {
    t(".l1").textContent = "Aucun document"; t(".l2").textContent = "pour l'instant"; t(".l3").textContent = "";
  } else {
    e.classList.add(d.statut);
    t(".l1").textContent = `${GENRES[d.genre] || d.genre} · ${STATUTS[d.statut] || d.statut}`;
    t(".l2").textContent = couper(d.titre, 23);
    t(".l3").textContent = heure(d.cree);
  }
  const c = d && courbes[d.id];
  if (d && !c && a.statut !== "construction") chargerCourbe(a.n, d);
  const ligne = t(".courbe");
  if (c && c.clotures && c.clotures.length > 1) {
    const min = Math.min(...c.clotures), max = Math.max(...c.clotures), k = (max - min) || 1;
    ligne.setAttribute("points", c.clotures.map((v, i) => `${(5 + (i * 86) / (c.clotures.length - 1)).toFixed(1)},${(45 - ((v - min) * 12) / k).toFixed(1)}`).join(" "));
    t(".l4").textContent = `${c.unite} · ${c.clotures.length} bougies`;
  } else { ligne.setAttribute("points", ""); t(".l4").textContent = ""; }
}

function dessinerPoste(g, p) {
  const dir = p.agent === 14, l = dir ? 3.2 : p.l, pr = dir ? 1.6 : p.p;
  const x = p.x - l / 2, y = p.y - pr / 2;
  const b = el("g", { class: `poste ${dir ? "directeur" : ""}`, "data-n": p.agent, tabindex: 0, role: "button",
    "aria-label": `${p.nom} (agent ${p.agent})` }, g);
  boite(b, x, y, 0, l, pr, 0.75, "bureau-table");
  // écran au fond du bureau, tourné vers nous
  const ex = p.x - 0.55, ey = y + 0.15;
  el("polygon", { class: "ecran-poste", points: pts([[ex, ey, 0.8], [ex + 1.1, ey, 0.8], [ex + 1.1, ey, 1.45], [ex, ey, 1.45]]) }, b);
  // siège et agent devant le bureau
  boite(b, p.x - 0.3, y + pr + 0.35, 0, 0.6, 0.6, 0.45, "siege");
  const agent = el("g", { class: "personne" }, b);
  const [cx, cy] = iso(p.x, y + pr + 0.65, 0.95), [hx, hy] = iso(p.x, y + pr + 0.65, 1.55);
  el("ellipse", { class: "corps", cx, cy, rx: 9, ry: 13 }, agent);
  el("circle", { class: "tete", cx: hx, cy: hy, r: 7.5 }, agent);
  el("circle", { class: "halo-poste", cx: hx, cy: hy, r: 12 }, agent);
  postePos[p.agent].tete = [hx, hy];
  const t = el("title", {}, b);
  t.textContent = p.nom;
  b.addEventListener("click", () => ouvrirAgent(p.agent));
  b.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); ouvrirAgent(p.agent); } });
}

function dessinerEtiquette(g, p) {
  const [x, y] = iso(p.x, p.y, 2.6);
  const e = el("g", { class: "etiquette-poste", "data-n": p.agent, transform: `translate(${x.toFixed(1)} ${y.toFixed(1)})` }, g);
  el("rect", { class: "fond", x: -40, y: -13, width: 80, height: 22, rx: 11 }, e);
  el("circle", { class: "point", cx: -28, cy: -2, r: 4.5 }, e);
  el("text", { class: "court", x: 4, y: -2 }, e).textContent = `${p.agent} · ${p.court}`;
  el("text", { class: "sous", x: 0, y: 22 }, e);
}

function majPlateau(etatCourant, choix) {
  if (!plan || !etatCourant) return;
  for (const a of etatCourant.agents) {
    const classes = ["disponible", "travail", "attente", "erreur", "construction"];
    for (const sel of [`.poste[data-n="${a.n}"]`, `.etiquette-poste[data-n="${a.n}"]`]) {
      const n = document.querySelector(sel);
      if (!n) continue;
      n.classList.remove(...classes);
      n.classList.add(a.statut);
      n.classList.toggle("choisi", choix === a.n);
    }
    const et = document.querySelector(`.etiquette-poste[data-n="${a.n}"] .sous`);
    let sous = a.statut === "disponible" ? "" : STATUTS[a.statut];
    if (a.mission) sous = `${PHASES[a.mission.phase] || a.mission.phase} — ${ROLES[a.mission.role] || "…"}`;
    else if (a.file) sous = `file d'attente (${a.file})`;
    if (et) et.textContent = sous;
    const t = document.querySelector(`.poste[data-n="${a.n}"] > title`);
    if (t) t.textContent = `${a.nom} — ${a.mission ? a.mission.etape : STATUTS[a.statut]} · ${a.documents} document(s)`;
    majEcran(a);
  }
  const g = $("#plateau-liens");
  g.textContent = "";
  for (const l of etatCourant.liens) {
    const a = postePos[l.de] && postePos[l.de].tete, b = postePos[l.a] && postePos[l.a].tete;
    if (!a || !b || l.de === l.a) continue;
    const mx = (a[0] + b[0]) / 2, my = Math.min(a[1], b[1]) - 60;
    const p = el("path", { class: `lien ${esc(l.genre)}`, d: `M${a[0]},${a[1]} Q${mx},${my} ${b[0]},${b[1]}`, "marker-end": "url(#fleche)" }, g);
    el("title", {}, p).textContent = `${l.n} message(s) « ${l.genre} » de l'agent ${l.de} à l'agent ${l.a}, le dernier à ${heure(l.ts)}`;
  }
}

// Vue d'ensemble : le plateau entier (proportions de l'écran 1600 x 1000 gardées)
function cadreEnsemble() {
  if (!plan) return null;
  const S = plan.sol, coins = [iso(0, 0, 3), iso(S.l, 0), iso(S.l, S.p), iso(0, S.p)];
  const xs = coins.map((c) => c[0]), ys = coins.map((c) => c[1]);
  const x0 = Math.min(...xs) - 20, x1 = Math.max(...xs) + 20, y0 = Math.min(...ys) - 20, y1 = Math.max(...ys) + 30;
  const w = Math.max(x1 - x0, ((y1 - y0) * 1600) / 1000);
  return { x: (x0 + x1 - w) / 2, y: (y0 + y1) / 2 - (w * 1000) / 3200, w, h: (w * 1000) / 1600 };
}

function cadreDirecteur() {
  const p = postePos[14];
  if (!p) return null;
  const [x, y] = iso(p.x, p.y, 1);
  return { x: x - 350, y: y - 218, w: 700, h: 437.5 };
}

function choisirMode(m) {
  mode = m === "hall" ? "hall" : "bureau";
  $("#monde").style.display = mode === "hall" ? "" : "none";
  $("#plateau").style.display = mode === "bureau" ? "" : "none";
  const b = $("#b-mode");
  if (b) { b.textContent = mode === "bureau" ? "◯" : "▦"; b.setAttribute("aria-label", mode === "bureau" ? "Voir l'ancien hall" : "Voir le bureau"); b.title = b.getAttribute("aria-label"); }
  $("#hall").setAttribute("aria-label", mode === "bureau" ? "Le bureau de l'université : zones et postes des 14 agents" : "Le grand hall de l'université : les 14 agents à leur bureau");
  try { localStorage.setItem("universite-vue", mode); } catch { /* stockage indisponible : sans conséquence */ }
}

async function demarrerPlateau() {
  let voulu = new URLSearchParams(location.search).get("vue");
  if (!voulu) { try { voulu = localStorage.getItem("universite-vue"); } catch { voulu = null; } }
  choisirMode(voulu || "bureau");
  $("#b-mode").addEventListener("click", () => { choisirMode(mode === "bureau" ? "hall" : "bureau"); allerA("hall"); });
  try {
    plan = await api("/api/scene");
    construirePlateau();
    if (etat) majPlateau(etat, choisi);
    if (mode === "bureau") {
      allerA("hall");
      if (window.innerWidth < 700) zoomer(1.7);     // téléphone : on part du centre, assez grand pour lire
    }
  } catch (e) {
    const t = el("text", { class: "nom-zone", x: 800, y: 500, "text-anchor": "middle" }, $("#plateau"));
    t.textContent = `Plan du bureau indisponible : ${e.message}`;
  }
}

window.addEventListener("resize", appliquerVue);
window.majPlateau = majPlateau;
window.modePlateau = () => mode;
window.cadreDirecteur = cadreDirecteur;
window.cadreEnsemble = cadreEnsemble;
demarrerPlateau();
