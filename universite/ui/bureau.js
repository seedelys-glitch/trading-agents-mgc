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
    const t = el("text", { class: "nom-zone", x, y: y + 16, tabindex: 0, role: "button", "data-zone": z.cle }, noms);
    t.textContent = z.nom;
    t.addEventListener("click", () => ouvrirZone(z.cle));
    t.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); ouvrirZone(z.cle); } });
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
  e.addEventListener("click", () => voirAgent(p.agent));
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
  b.addEventListener("click", () => voirAgent(p.agent));
  b.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); voirAgent(p.agent); } });
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
  if (window.maj3d) window.maj3d(etatCourant, choix);
  if (!plan || !etatCourant) return;
  if (zoneChoisie && !$("#panneau").hidden && !choix) majZone(false).catch(() => {});
  document.querySelectorAll(".zone").forEach((z) => z.classList.toggle("choisie", z.dataset.zone === zoneChoisie));
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
  if (window.basculer3d) window.basculer3d(mode);
  if (!CAMERA) try { localStorage.setItem("universite-vue", mode); } catch { /* stockage indisponible : sans conséquence */ }
}

async function demarrerPlateau() {
  let voulu = CAMERA ? "bureau" : new URLSearchParams(location.search).get("vue");
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

// ------------------------------------------------------------------ espace de travail d'un agent (panneau)
const graphiques = {};

function texteSource(s, jeux) {
  if (s.jeu !== undefined && s.unite) {
    const j = jeux[s.jeu];
    return `${j ? `Jeu « ${esc(j.nom)} » (${esc(j.source)})` : `Jeu n° ${esc(s.jeu)}`} · ${esc(s.unite)}` +
      (s.n ? ` · ${s.n} bougies` : "") + (s.debut ? ` · du ${heure(s.debut)} au ${heure(s.fin)}` : "");
  }
  if (s.document !== undefined) return `<a data-doc="${+s.document}">Document n° ${+s.document}</a>`;
  if (s.url) return `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.url)}</a>`;
  if (s.fichier) return `Fichier : ${esc(s.fichier)}`;
  if (s.extrait !== undefined) return `Extrait n° ${+s.extrait} (${esc(s.origine || "")})`;
  if (s.source) return `${esc(s.source)}${s.telecharge ? ` · téléchargé le ${heure(s.telecharge)}` : ""}`;
  if (s.jeu !== undefined) return jeux[s.jeu] ? `Jeu « ${esc(jeux[s.jeu].nom)} »` : `Jeu n° ${esc(s.jeu)}`;
  return esc(s.texte || JSON.stringify(s));
}

function rendreEspace(esp) {
  const d = esp.dernier_document, ag = esp.agent;
  const enCours = esp.mission_en_cours;
  return `
    ${enCours ? `<div class="bloc"><h3>Au travail en ce moment</h3>${esc(enCours.titre)}<br><span class="doux">${esc(ROLES[enCours.role] || "")} : ${esc(enCours.etape)}</span></div>` : ""}
    ${esp.file ? `<div class="bloc"><h3>File d'attente</h3>${esp.file} mission(s) attendent leur tour.</div>` : ""}
    <div class="bloc"><h3>Sur son bureau</h3>${d ? `${etiquette(d.statut)} <a data-doc="${d.id}">${esc(d.titre)}</a>
      <br><small class="doux">n° ${d.id} · ${esc(GENRES[d.genre] || d.genre)} · ${heure(d.cree)}${d.verifie_par ? ` · contrôlé par l'agent ${d.verifie_par}` : ""}</small>
      <pre class="doc apercu">${esc(couper(d.contenu, 700))}</pre>`
      : ag.en_construction ? `<span class="doux">Poste en construction : ${esc(esp.agent.mission)} Aucune donnée, aucune activité simulée.</span>`
      : '<span class="doux">Aucun document pour l\'instant.</span>'}</div>
    ${esp.graphique ? `<div class="bloc"><h3>Les bougies qu'il a lues</h3><div data-graphique class="graphique"><span class="doux">Chargement des bougies…</span></div></div>` : ""}
    <div class="bloc"><h3>Sources citées</h3>${esp.sources.length ? `<ul class="liste">${esp.sources.map((s) =>
      `<li>${texteSource(s, esp.jeux)}<br><small class="doux">citée dans le document n° ${s.cite_dans}</small></li>`).join("")}</ul>`
      : '<span class="doux">Aucune source pour l\'instant.</span>'}</div>
    <div class="bloc"><h3>Confier une tâche</h3>${esp.taches.length ? esp.taches.map((t) =>
      `<button data-lancer="${esc(t.type)}">${esc(t.titre)}</button>`).join(" ")
      : `<span class="doux">${ag.en_construction ? "Rien à confier tant que le poste est en construction." : "Cet agent travaille seulement à la demande des autres agents."}</span>`}</div>
    <div class="bloc"><h3>Dernières missions</h3>${esp.missions.length ? `<ul class="liste">${esp.missions.slice(0, 6).map((m) =>
      `<li>${etiquette(m.statut)} <a data-mission="${m.id}">${esc(m.titre)}</a><br><small class="doux">n° ${m.id} · ${heure(m.cree)} · demandée par ${esc(m.demandeur)}</small></li>`).join("")}</ul>`
      : '<span class="doux">Aucune mission.</span>'}</div>
    <div class="bloc"><h3>Échanges avec les autres agents</h3>${esp.echanges.length ? `<ul class="liste">${esp.echanges.slice(0, 6).map((m) =>
      `<li>${m.de === ag.n ? `→ agent ${m.a}` : `← agent ${m.de}`} (${esc(m.genre)}) : ${esc(couper(m.contenu, 160))}<br><small class="doux">${heure(m.ts)}</small></li>`).join("")}</ul>`
      : '<span class="doux">Aucun échange.</span>'}</div>`;
}

function svgBougies(r, jeu) {
  const b = r.bougies;
  if (!b.length) return '<span class="doux">Ces bougies ne sont plus dans la base.</span>';
  const W = 480, H = 190, g = 34, bas = 22;
  const hauts = b.map((x) => x[2]), basP = b.map((x) => x[3]);
  const max = Math.max(...hauts), min = Math.min(...basP), k = (max - min) || 1, pas = (W - g) / b.length;
  const y = (v) => (4 + ((max - v) * (H - bas - 8)) / k).toFixed(1);
  const corps = b.map((x, i) => {
    const cx = (i + 0.5) * pas, hausse = x[4] >= x[1];
    const haut = Math.max(x[1], x[4]), basC = Math.min(x[1], x[4]);
    return `<line x1="${cx.toFixed(1)}" x2="${cx.toFixed(1)}" y1="${y(x[2])}" y2="${y(x[3])}" class="meche"/>` +
      `<rect x="${(cx - pas * 0.35).toFixed(1)}" width="${Math.max(1, pas * 0.7).toFixed(1)}" y="${y(haut)}" height="${Math.max(1, y(basC) - y(haut)).toFixed(1)}" class="${hausse ? "hausse" : "baisse"}"/>`;
  }).join("");
  const fin = b[b.length - 1][0];
  return `<svg viewBox="0 0 ${W} ${H}" class="bougies" role="img" aria-label="${b.length} bougies ${esc(r.unite)} fermées avant l'instant analysé">
      ${corps}
      <line x1="${W - g + 2}" x2="${W - g + 2}" y1="0" y2="${H - bas}" class="instant"/>
      <text x="${W - 2}" y="${(+y(max) + 8).toFixed(1)}" class="prix">${max.toFixed(1)}</text>
      <text x="${W - 2}" y="${y(min)}" class="prix">${min.toFixed(1)}</text>
      <text x="2" y="${H - 6}" class="date">${heure(b[0][0])}</text>
      <text x="${W - g - 2}" y="${H - 6}" class="date fin">${heure(fin)}</text>
    </svg>
    <small class="doux">${esc(r.unite)} · ${b.length} bougies fermées du jeu « ${esc(jeu ? jeu.nom : r.jeu.nom)} » (${esc(r.jeu.source)}${r.jeu.temps_reel ? "" : ", différées ou historiques"})${r.reconstruite_depuis ? `, reconstruites depuis ${esc(r.reconstruite_depuis)}` : ""} ; trait vertical = instant analysé (${heure(r.instant)}), rien après.</small>`;
}

async function apresEspace(zone, esp) {
  const place = zone.querySelector("[data-graphique]");
  if (!place || !esp.graphique) return;
  const gr = esp.graphique, cle = `${gr.jeu}|${gr.unite}|${gr.instant}`;
  if (!graphiques[cle]) {
    try { graphiques[cle] = await api(`/api/bougies?jeu=${gr.jeu}&unite=${gr.unite}&instant=${gr.instant}&n=80`); }
    catch (e) { place.innerHTML = `<span class="doux">Bougies indisponibles : ${esc(e.message)}</span>`; return; }
  }
  const actuel = zone.querySelector("[data-graphique]");
  if (actuel) actuel.innerHTML = svgBougies(graphiques[cle], esp.jeux[gr.jeu]);
}

// ------------------------------------------------------------------ zones (bibliothèque, réunion, labo, données...)
// Le hall capture le pointeur pour le déplacement : une zone s'ouvre donc au relâché, si on n'a pas glissé.
let zoneChoisie = null, departClic = null;
$("#hall").addEventListener("pointerdown", (e) => {
  const z = mode === "bureau" && !e.target.closest(".poste") ? e.target.closest(".zone") : null;
  departClic = z ? { x: e.clientX, y: e.clientY, cle: z.dataset.zone } : null;
});
$("#hall").addEventListener("pointerup", (e) => {
  const d = departClic;
  departClic = null;
  if (d && Math.hypot(e.clientX - d.x, e.clientY - d.y) < 6) ouvrirZone(d.cle);
});

function voirAgent(n) { zoneChoisie = null; ouvrirAgent(n); }

async function ouvrirZone(cle) {
  zoneChoisie = cle; choisi = null;
  $("#panneau").hidden = false;
  await majZone(true);
  majHall();
}

const ligneAgent = (a) => `<li>${etiquette(a.statut)} <a data-agent="${a.n}">${a.n}. ${esc(a.nom)}</a>
  ${a.mission ? `<br><small class="doux">${esc(a.mission.etape)}</small>` : ""}
  ${a.dernier_document ? `<br><small class="doux">Dernier document : ${esc(a.dernier_document.titre)} (${esc(STATUTS[a.dernier_document.statut] || a.dernier_document.statut)})</small>` : ""}</li>`;
const ligneDoc = (d) => `<li>${etiquette(d.statut)} <a data-doc="${d.id}">${esc(d.titre)}</a><br><small class="doux">n° ${d.id} · agent ${d.agent} · ${heure(d.cree)}</small></li>`;
const liste = (titre, items, rendu, vide) => `<div class="bloc"><h3>${titre}</h3>${items && items.length
  ? `<ul class="liste">${items.map(rendu).join("")}</ul>` : `<span class="doux">${vide}</span>`}</div>`;
const STATUTS_REGLE = { proposee: "proposées", validee: "validées", rejetee: "rejetées", remplacee: "remplacées" };

function rendreZone(r) {
  const z = r.zone;
  let h = `<h2>${esc(z.nom)}</h2><p class="doux">${esc(z.montre)}.<br><small>Source : ${esc(z.source)}.</small></p>`;
  if (r.agents.length) h += liste("Qui travaille ici", r.agents, ligneAgent, "");
  if (z.cle === "directeur") {
    const c = r.compteurs;
    h += `<div class="bloc"><h3>File de travail</h3>${c.en_cours} mission(s) en cours, ${c.attente} en attente · ${c.documents} document(s) · ${c.boucles} boucle(s) active(s)
      <p class="ligne"><button data-lancer="synthese_directeur">Demander une synthèse</button></p></div>`;
    const ds = r.derniere_synthese;
    if (ds) h += `<div class="bloc"><h3>Dernière synthèse</h3>${etiquette(ds.statut)} <a data-doc="${ds.id}">${esc(ds.titre)}</a> <small class="doux">${heure(ds.cree)}</small><pre class="doc apercu">${esc(couper(ds.contenu, 900))}</pre></div>`;
    h += liste("Synthèses", r.syntheses, ligneDoc, "Aucune synthèse pour l'instant.");
    h += liste("Demandes reçues", r.demandes, (m) => `<li>${etiquette(m.statut)} <a data-mission="${m.id}">${esc(m.titre)}</a><br><small class="doux">n° ${m.id} · ${heure(m.cree)}${m.erreur ? ` · ${esc(m.erreur)}` : ""}</small></li>`, "Aucune demande.");
    h += liste("Alertes reçues", r.alertes, (m) => `<li>← agent ${m.de} : ${esc(m.contenu)}<br><small class="doux">${heure(m.ts)}</small></li>`, "Aucune alerte.");
  } else if (z.cle === "reunion") {
    h += `<div class="bloc"><h3>Ces dernières 24 h</h3>${r.messages_24h} message(s) échangé(s) entre agents.</div>`;
    h += liste("Derniers échanges", r.messages, (m) => `<li><a data-agent="${m.de}">agent ${m.de}</a> → <a data-agent="${m.a}">agent ${m.a}</a> · ${esc(m.genre)}
      ${m.document ? ` · <a data-doc="${m.document}">document ${m.document}</a>` : ""}<br>${esc(m.contenu)}<br><small class="doux">${heure(m.ts)}</small></li>`,
      "Aucun échange pour l'instant : les agents ne se parlent que pendant une vraie mission.");
  } else if (z.cle === "bibliotheque") {
    const nb = Object.entries(r.regles);
    h += `<div class="bloc"><h3>Règles</h3>${nb.length ? nb.map(([k, n]) => `${n} ${STATUTS_REGLE[k] || k}`).join(" · ") : "Aucune règle lue pour l'instant."}
      <p class="ligne"><button data-fenetre="bibliotheque">Ouvrir la bibliothèque</button></p></div>`;
    h += liste("Dernières règles", r.regles_recentes, (x) => `<li>${etiquette(x.statut === "validee" ? "verifie" : x.statut === "proposee" ? "a_verifier" : x.statut === "rejetee" ? "rejete" : "brouillon")} ${esc(x.titre)}<br><small class="doux">${esc(x.theme)} · version ${x.version} · ${heure(x.cree)}</small></li>`, "Aucune règle.");
    h += liste("Extraits gardés", r.extraits, (x) => `<li>${esc(x.genre === "fed" ? "Discours de la Fed" : x.genre)} : ${x.n} extrait(s) de ${x.origines} texte(s)</li>`, "Aucun extrait gardé.");
    h += liste("Derniers contrôles de l'agent 9", r.verifications, ligneDoc, "Aucun contrôle pour l'instant.");
  } else if (z.cle === "macro") {
    h += liste("Annonces des 48 prochaines heures", r.annonces, (x) => `<li><b>${heure(x.quand)}</b> · ${esc(x.pays)} · ${esc(x.titre)}${x.impact ? ` <span class="doux">(${esc(x.impact)})</span>` : ""}<br><small class="doux">${esc(x.source)}</small></li>`,
      r.annonces_gardees ? "Aucune annonce gardée dans les 48 h." : "Calendrier pas encore téléchargé (agent 5).");
    h += `<p class="doux">${r.annonces_gardees} annonce(s) gardée(s) au total.</p>`;
  } else if (z.cle === "donnees") {
    h += `<div class="bloc"><h3>Jeux de bougies</h3>${r.jeux.length ? `<ul class="liste">${r.jeux.map((j) => `<li><b>${esc(j.nom)}</b> · ${esc(j.source)}${j.temps_reel ? "" : " <span class=\"doux\">(différé ou historique)</span>"}<br><small class="doux">${Object.entries(j.unites).map(([u, x]) => `${u} : ${x.n} bougies, du ${heure(x.debut)} au ${heure(x.fin)}`).join("<br>") || "vide"}</small></li>`).join("")}</ul>`
      : '<span class="doux">Aucun jeu de bougies.</span>'}<p class="ligne"><button data-fenetre="donnees">Importer ou contrôler des données</button></p></div>`;
    h += liste("Derniers fichiers TradingView lus", r.fichiers, (f) => `<li>${esc(f.chemin)}<br><small class="doux">${esc(f.unite)} · ${f.lignes} lignes, ${f.ajoutees} ajoutées · jeu ${f.jeu} · ${heure(f.importe_le)}</small></li>`, "Aucun fichier importé.");
  } else if (z.cle === "labo") {
    h += `<div class="bloc"><h3>Lancer</h3><button data-lancer="replay_strategie_v1">Rejouer la stratégie V1</button> <button data-lancer="controle_donnees">Contrôler un jeu</button></div>`;
  }
  if (r.documents) h += liste("Derniers documents de la zone", r.documents, ligneDoc, "Aucun document pour l'instant.");
  return h;
}

async function majZone(premier) {
  if (!zoneChoisie) return;
  const r = await api(`/api/zone/${zoneChoisie}`);
  if (!zoneChoisie || $("#panneau").hidden) return;
  const defil = $("#panneau").scrollTop;
  $("#panneau-contenu").innerHTML = rendreZone(r);
  if (!premier) $("#panneau").scrollTop = defil;
}

$("#panneau").addEventListener("click", (e) => {
  const t = e.target;
  if (t.dataset.agent) voirAgent(+t.dataset.agent);
  else if (t.dataset.fenetre === "bibliotheque") fenetreBibliotheque();
  else if (t.dataset.fenetre === "donnees") fenetreDonnees();
});
$("#fermer-panneau").addEventListener("click", () => { zoneChoisie = null; });

window.GENRES_DOC = GENRES;
window.STATUTS_DOC = STATUTS;
window.etatCourant = () => etat;
window.rendreEspace = rendreEspace;
window.apresEspace = apresEspace;
window.addEventListener("resize", appliquerVue);
window.majPlateau = majPlateau;
window.modePlateau = () => mode;
window.cadreDirecteur = cadreDirecteur;
window.cadreEnsemble = cadreEnsemble;
demarrerPlateau();
