// Bureau 3D (WebGL, three.js en copie locale) : même plan que la vue 2,5D (/api/scene), même état réel (/api/etat).
// Ambiance « grand hall au soleil couchant » : la lumière du soir entre par les hautes fenêtres (ombres portées) ;
// chaque équipe a son bureau fermé (murs pleins, ouverture sans porte, parquet, plafond à caissons, lustre).
// Vue d'ensemble en « maison de poupée » : les murs tournés vers la caméra s'abaissent ; on peut entrer dans
// chaque pièce. Les écrans muraux montrent de vraies données (bougies fermées, échanges réels, heure réelle).
// Mais rien ne bouge sans une mission réellement en cours, un poste « en construction » reste vide et éteint, les
// arcs lumineux sont de vrais messages entre agents et les horloges donnent l'heure réelle.
// Sans WebGL, la vue 2,5D en SVG prend le relais (bureau.js).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";

const COULEURS = { disponible: 0x4cc38a, travail: 0x5aa7ff, attente: 0xf0a03c, erreur: 0xe05252, construction: 0x55534f };
// tapis de chaque pièce : fond, motif
const TAPIS = { directeur: ["#3b0d12", "#c9a24f"], analyse: ["#0c1a33", "#b8954a"], macro: ["#24102c", "#c49a52"],
  reunion: ["#10261c", "#c3a058"], bibliotheque: ["#3a1d0e", "#d0aa5c"], labo: ["#0b2427", "#a9b8b0"],
  risque: ["#2e0c10", "#c49452"], donnees: ["#0e1828", "#8fa8c8"] };
const MUR = 11, MEZZ = 4.4, FEN_BAS = 5.2, FEN_HAUT = 8.6, FEN_L = 2.6;
const SOLEIL = new THREE.Vector3(0.42, -0.58, 0.7).normalize();   // le soir entre par le fond et la gauche
const telephone = window.innerWidth < 700;
// mode caméra (Jarvis) : la vue tourne lentement toute seule, 30 images par seconde suffisent
const camera3d = document.documentElement.classList.contains("camera");
const LEGER = telephone || camera3d;   // téléphone et petite caméra : ombres plus petites, moins d.anticrénelage
// écran tactile (téléphone, tablette) : un doigt fait glisser le plan, deux doigts zooment, boutons de déplacement en bas
const tactile = matchMedia("(pointer: coarse)").matches;
if (tactile) document.documentElement.classList.add("tactile");
const camLente = camera3d && !tactile;   // la petite caméra de l'écran Jarvis : 30 images/s ; au doigt : fluide
let image = 0;

let plan, L, P, renderer, scene, camera, controls, composer, labels, conteneur, pret = false, actif = false;
const postes = {}, cliquables = [], tetes = {}, sols = [];
let liens3d = [], dernierLiens = "", t0 = performance.now(), poussiere = null, feu = null, grand = null, tableauEchanges = null;
const horloges = [];

// ------------------------------------------------------------------ outils
const P3 = (x, y, z = 0) => new THREE.Vector3(x - L / 2, z, y - P / 2);
function hasard(graine) { let a = graine >>> 0; return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function toile(w, h, dessin, repete = false) {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  dessin(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  if (repete) t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}
const std = (o) => new THREE.MeshStandardMaterial(o);
const phy = (o) => new THREE.MeshPhysicalMaterial(o);
function ombre(m, porte = true) { m.castShadow = porte; m.receiveShadow = true; return m; }
function boite(l, h, p, m, x, y, z, porte = true) {
  const b = new THREE.Mesh(new THREE.BoxGeometry(l, h, p), m); b.position.set(x, y, z);
  return ombre(b, porte);
}
function arrondi(l, h, p, r, m, x, y, z, porte = true) {
  const b = new THREE.Mesh(new RoundedBoxGeometry(l, h, p, 3, Math.min(r, l / 2, h / 2, p / 2)), m); b.position.set(x, y, z);
  return ombre(b, porte);
}
function cyl(rh, rb, h, m, x, y, z, seg = 20) {
  const c = new THREE.Mesh(new THREE.CylinderGeometry(rh, rb, h, seg), m); c.position.set(x, y, z);
  return ombre(c);
}
// segment arrondi (bras, jambes) entre deux points
function membre(a, b, r, m) {
  const d = b.clone().sub(a), long = d.length();
  const s = new THREE.Mesh(new THREE.CapsuleGeometry(r, Math.max(0.001, long), 6, 12), m);
  s.position.copy(a).addScaledVector(d, 0.5);
  s.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
  return ombre(s);
}

// ------------------------------------------------------------------ textures dessinées par le code
let M, T;
// motif damassé (feuilles en croix)
function damas(c, x, y, s, trait, plein) {
  c.save(); c.translate(x, y); c.scale(s, s);
  c.strokeStyle = trait; c.fillStyle = plein; c.lineWidth = 2;
  for (let k = 0; k < 4; k++) {
    c.rotate(Math.PI / 2); c.beginPath(); c.moveTo(0, 0);
    c.bezierCurveTo(18, -20, 34, -6, 30, 22); c.bezierCurveTo(22, 8, 10, 6, 0, 0); c.fill(); c.stroke();
  }
  c.beginPath(); c.arc(0, 0, 5, 0, 7); c.fill(); c.restore();
}
// panneau de boiserie en relief (lumière en haut à gauche) avec un filet doré
function panneau(c, x, y, w, h) {
  c.lineWidth = 4;
  c.strokeStyle = "rgba(255,222,170,.16)"; c.beginPath(); c.moveTo(x, y + h); c.lineTo(x, y); c.lineTo(x + w, y); c.stroke();
  c.strokeStyle = "rgba(0,0,0,.5)"; c.beginPath(); c.moveTo(x + w, y); c.lineTo(x + w, y + h); c.lineTo(x, y + h); c.stroke();
  c.strokeStyle = "rgba(205,165,85,.32)"; c.lineWidth = 1.5; c.strokeRect(x + 10, y + 10, w - 20, h - 20);
}
// murs intérieurs : tissu de la couleur de l'équipe au-dessus d'un lambris de noyer (texture de 1,6 m sur 3,4 m)
const TEINTES_MURS = { analyse: ["#14223a", "rgba(205,170,100,.2)"], macro: ["#11301f", "rgba(205,175,105,.18)"],
  reunion: ["#3c1517", "rgba(220,175,115,.17)"], bibliotheque: ["#1d2a22", "rgba(205,175,105,.16)"], labo: ["#cfc8bb", "rgba(120,105,85,.16)"],
  risque: ["#311015", "rgba(215,165,105,.18)"], donnees: ["#0e1626", "rgba(120,160,220,.16)"] };
function texMur(cle) {
  return toile(512, 1024, (c, w, h) => {
    const Y = (m) => h - (m / 3.4) * h, bois = c.createPattern(T.bois.image, "repeat"), haut = Y(0.95);
    if (cle === "directeur") {   // boiserie de noyer du sol au plafond
      c.fillStyle = bois; c.fillRect(0, 0, w, h);
      for (const x of [0, w / 2]) panneau(c, x + 22, Y(3.05), w / 2 - 44, Y(1.15) - Y(3.05));
    } else {
      const [fond, motif] = TEINTES_MURS[cle] || ["#1a1a1a", "rgba(255,255,255,.08)"];
      c.fillStyle = fond; c.fillRect(0, 0, w, haut);
      for (let j = 0; j * 128 - 64 < haut + 64; j++) for (let x = -64; x <= w + 64; x += 128) damas(c, x + (j % 2 ? 64 : 0), j * 128 - 64, 0.9, motif, motif.replace(/[\d.]+\)$/, "0.07)"));
      const g = c.createLinearGradient(0, 0, 0, haut); g.addColorStop(0, "rgba(0,0,0,.28)"); g.addColorStop(1, "rgba(0,0,0,0)");
      c.fillStyle = g; c.fillRect(0, 0, w, haut);
    }
    c.fillStyle = bois; c.fillRect(0, haut, w, h - haut);
    for (const x of [0, w / 2]) panneau(c, x + 18, Y(0.85), w / 2 - 36, Y(0.22) - Y(0.85));
  }, true);
}
function textures() {
  T = {};
  // marbre noir veiné de blanc, dalles de 2 m avec joints dorés
  T.marbre = toile(1024, 1024, (c, w, h) => {
    const r = hasard(7);
    for (let i = 0; i < 2; i++) for (let j = 0; j < 2; j++) {
      const g = c.createLinearGradient(i * w / 2, j * h / 2, (i + 1) * w / 2, (j + 1) * h / 2);
      const base = (i + j) % 2 ? ["#0c0d10", "#15161b"] : ["#121318", "#0a0a0d"];
      g.addColorStop(0, base[0]); g.addColorStop(1, base[1]); c.fillStyle = g; c.fillRect(i * w / 2, j * h / 2, w / 2, h / 2);
    }
    for (let k = 0; k < 70; k++) {
      const fort = r() < 0.18;
      c.strokeStyle = `rgba(225,228,236,${fort ? 0.28 + r() * 0.2 : 0.04 + r() * 0.08})`;
      c.lineWidth = fort ? 1.2 + r() * 1.6 : 0.6 + r();
      c.shadowColor = "rgba(230,232,240,.35)"; c.shadowBlur = fort ? 6 : 2;
      c.beginPath(); let x = r() * w, y = r() * h; c.moveTo(x, y);
      for (let s = 0; s < 5; s++) {
        const x2 = x + (r() - 0.25) * 260, y2 = y + (r() - 0.5) * 200;
        c.quadraticCurveTo(x + (r() - 0.5) * 160, y + (r() - 0.5) * 160, x2, y2); x = x2; y = y2;
      }
      c.stroke();
    }
    c.shadowBlur = 0;
    c.strokeStyle = "rgba(201,162,79,.9)"; c.lineWidth = 3;
    c.strokeRect(1.5, 1.5, w - 3, h - 3); c.beginPath(); c.moveTo(w / 2, 0); c.lineTo(w / 2, h); c.moveTo(0, h / 2); c.lineTo(w, h / 2); c.stroke();
  }, true);
  // noyer verni
  T.bois = toile(512, 512, (c, w, h) => {
    const r = hasard(3);
    const g = c.createLinearGradient(0, 0, w, 0); g.addColorStop(0, "#3a2010"); g.addColorStop(0.5, "#4b2a14"); g.addColorStop(1, "#38200f");
    c.fillStyle = g; c.fillRect(0, 0, w, h);
    for (let k = 0; k < 160; k++) {
      c.strokeStyle = `rgba(${20 + r() * 30},${10 + r() * 14},${4 + r() * 6},${0.15 + r() * 0.35})`; c.lineWidth = 0.6 + r() * 2.2;
      c.beginPath(); let y = r() * h; c.moveTo(0, y);
      for (let x = 0; x <= w; x += 32) { y += (r() - 0.5) * 6; c.lineTo(x, y); }
      c.stroke();
    }
    for (let k = 0; k < 6; k++) {   // nœuds
      const x = r() * w, y = r() * h;
      for (let a = 1; a < 6; a++) { c.strokeStyle = `rgba(25,12,5,${0.25 - a * 0.03})`; c.beginPath(); c.ellipse(x, y, 4 + a * 7, 2 + a * 2.5, 0, 0, 7); c.stroke(); }
    }
  }, true);
  // tissu damassé des murs (bleu nuit, motif à peine doré)
  T.damas = toile(256, 256, (c, w, h) => {
    c.fillStyle = "#0e1622"; c.fillRect(0, 0, w, h);
    const motif = (x, y, s) => damas(c, x, y, s, "rgba(190,160,95,.16)", "rgba(190,160,95,.07)");
    motif(w / 2, h / 2, 1.6); motif(0, 0, 1.6); motif(w, 0, 1.6); motif(0, h, 1.6); motif(w, h, 1.6);
  }, true);
  // extérieur des bureaux : boiserie de noyer à panneaux
  T.boiserie = toile(512, 1024, (c, w, h) => {
    const Y = (m) => h - (m / 3.4) * h;
    c.fillStyle = c.createPattern(T.bois.image, "repeat"); c.fillRect(0, 0, w, h);
    c.fillStyle = "rgba(0,0,0,.18)"; c.fillRect(0, 0, w, h);
    for (const x of [0, w / 2]) { panneau(c, x + 20, Y(0.95), w / 2 - 40, Y(0.25) - Y(0.95)); panneau(c, x + 20, Y(3.0), w / 2 - 40, Y(1.1) - Y(3.0)); }
  }, true);
  // parquet de chêne fumé en point de Hongrie (motif de 1,6 m)
  T.parquet = toile(512, 512, (c, w, h) => {
    const r = hasard(13), cw = 128, d = h / 12, tons = [];
    for (let k = 0; k < 48; k++) tons.push(`hsl(${22 + r() * 9},${42 + r() * 16}%,${15 + r() * 9}%)`);
    for (let col = 0; col < w / cw; col++) {
      const x0 = col * cw, f = col % 2 ? (x) => cw - (x - x0) : (x) => x - x0;
      for (let k = -4; k < 16; k++) {
        const y0 = k * d;
        c.beginPath(); c.moveTo(x0, y0 + f(x0)); c.lineTo(x0 + cw, y0 + f(x0 + cw)); c.lineTo(x0 + cw, y0 + f(x0 + cw) + d); c.lineTo(x0, y0 + f(x0) + d); c.closePath();
        c.fillStyle = tons[(((k % 12) + 12) % 12) + col * 12]; c.fill();
        c.strokeStyle = "rgba(10,5,2,.6)"; c.lineWidth = 1.5; c.stroke();
      }
    }
    for (let k = 0; k < 1400; k++) { c.fillStyle = `rgba(${r() < 0.5 ? "0,0,0" : "255,215,160"},${0.03 + r() * 0.05})`; c.fillRect(r() * w, r() * h, 1 + r() * 3, 1); }
  }, true);
  // plafonds à caissons (2 m) : plâtre clair et filets dorés, noyer chez le directeur
  const caissons = (c, w, h, fond, creux, filet) => {
    c.fillStyle = fond; c.fillRect(0, 0, w, h);
    const t = w / 2;
    for (let i = 0; i < 2; i++) for (let j = 0; j < 2; j++) {
      const x = i * t + 22, y = j * t + 22, s = t - 44;
      const g = c.createLinearGradient(x, y, x + s, y + s); g.addColorStop(0, creux[0]); g.addColorStop(1, creux[1]);
      c.fillStyle = g; c.fillRect(x, y, s, s);
      c.strokeStyle = filet; c.lineWidth = 3; c.strokeRect(x + 10, y + 10, s - 20, s - 20);
      c.beginPath(); c.arc(x + s / 2, y + s / 2, 16, 0, 7); c.fillStyle = filet; c.fill();
    }
  };
  T.plafond = toile(512, 512, (c, w, h) => caissons(c, w, h, "#d9cdb5", ["#b5a68a", "#cdbfa4"], "rgba(196,154,72,.85)"), true);
  T.plafondNoyer = toile(512, 512, (c, w, h) => caissons(c, w, h, c.createPattern(T.bois.image, "repeat"), ["#24140a", "#3a2111"], "rgba(214,170,85,.9)"), true);
  // tapis des allées : bordeaux, filets et losanges dorés (2 m de long)
  T.couloir = toile(512, 128, (c, w, h) => {
    c.fillStyle = "#4a1117"; c.fillRect(0, 0, w, h);
    const r = hasard(17); for (let k = 0; k < 1500; k++) { c.fillStyle = `rgba(255,255,255,${r() * 0.025})`; c.fillRect(r() * w, r() * h, 2, 2); }
    c.fillStyle = "#c9a24f"; for (const [y, e] of [[10, 4], [18, 2], [h - 20, 2], [h - 14, 4]]) c.fillRect(0, y, w, e);
    c.globalAlpha = 0.55; for (let x = 16; x < w; x += 32) { c.beginPath(); c.moveTo(x, h / 2 - 9); c.lineTo(x + 9, h / 2); c.lineTo(x, h / 2 + 9); c.lineTo(x - 9, h / 2); c.fill(); }
    c.globalAlpha = 1;
  }, true);
  // tableaux (décor, peints par le code)
  const huile = (c, w, h, graine) => { const r = hasard(graine); for (let k = 0; k < 2500; k++) { c.fillStyle = `rgba(${r() < 0.5 ? "0,0,0" : "255,240,210"},${r() * 0.05})`; c.fillRect(r() * w, r() * h, 2 + r() * 4, 1 + r() * 2); } };
  T.tableaux = [
    toile(320, 200, (c, w, h) => {   // marine au couchant
      let g = c.createLinearGradient(0, 0, 0, h * 0.6); g.addColorStop(0, "#1e2b52"); g.addColorStop(0.6, "#c4663e"); g.addColorStop(1, "#f2b46a"); c.fillStyle = g; c.fillRect(0, 0, w, h * 0.6);
      c.fillStyle = "#ffd89a"; c.beginPath(); c.arc(w * 0.62, h * 0.56, 18, 0, 7); c.fill();
      g = c.createLinearGradient(0, h * 0.6, 0, h); g.addColorStop(0, "#5a3a3a"); g.addColorStop(1, "#141826"); c.fillStyle = g; c.fillRect(0, h * 0.6, w, h * 0.4);
      for (let k = 0; k < 40; k++) { c.fillStyle = `rgba(255,200,130,${0.4 - k * 0.009})`; c.fillRect(w * 0.62 - 20 + Math.sin(k) * 8, h * 0.62 + k * 2, 40 - k * 0.6, 1.5); }
      huile(c, w, h, 1);
    }),
    toile(320, 200, (c, w, h) => {   // montagnes au crépuscule
      const g = c.createLinearGradient(0, 0, 0, h); g.addColorStop(0, "#2a2448"); g.addColorStop(0.55, "#d48a6a"); g.addColorStop(1, "#f0c79a"); c.fillStyle = g; c.fillRect(0, 0, w, h);
      const r = hasard(31);
      for (const [col, base] of [["#4a3a52", 0.5], ["#2e2638", 0.62], ["#1a1622", 0.78]]) {
        c.fillStyle = col; c.beginPath(); c.moveTo(0, h); c.lineTo(0, h * base);
        for (let x = 0; x <= w; x += 16) c.lineTo(x, h * base - r() * h * 0.18);
        c.lineTo(w, h); c.fill();
      }
      huile(c, w, h, 2);
    }),
    toile(320, 200, (c, w, h) => {   // campagne d'automne
      const g = c.createLinearGradient(0, 0, 0, h); g.addColorStop(0, "#8fa7b8"); g.addColorStop(0.45, "#e6d3a8"); g.addColorStop(0.46, "#8a6a2a"); g.addColorStop(1, "#4a3216"); c.fillStyle = g; c.fillRect(0, 0, w, h);
      const r = hasard(41); for (let k = 0; k < 60; k++) { c.fillStyle = ["#8a3a14", "#b8661e", "#5a4a1a", "#3a4a22"][Math.floor(r() * 4)]; c.beginPath(); c.arc(r() * w, h * 0.42 + r() * 20, 6 + r() * 14, 0, 7); c.fill(); }
      huile(c, w, h, 3);
    }),
    toile(320, 200, (c, w, h) => {   // abstrait, or et nuit
      c.fillStyle = "#121018"; c.fillRect(0, 0, w, h);
      for (let k = 0; k < 7; k++) { c.strokeStyle = `rgba(214,170,85,${0.25 + k * 0.08})`; c.lineWidth = 2 + k; c.beginPath(); c.arc(w * 0.3, h * 1.1, 60 + k * 26, -1.2, -0.2); c.stroke(); }
      c.fillStyle = "rgba(170,40,40,.7)"; c.fillRect(w * 0.68, h * 0.18, 46, 46);
      huile(c, w, h, 4);
    }),
  ];
  T.flamme = toile(64, 128, (c, w, h) => {
    const g = c.createRadialGradient(w / 2, h * 0.82, 2, w / 2, h * 0.7, h * 0.6);
    g.addColorStop(0, "rgba(255,240,180,1)"); g.addColorStop(0.3, "rgba(255,150,40,.9)"); g.addColorStop(0.7, "rgba(200,50,10,.35)"); g.addColorStop(1, "rgba(0,0,0,0)");
    c.fillStyle = g; c.beginPath(); c.moveTo(w / 2, 4); c.bezierCurveTo(w, h * 0.5, w * 0.9, h, w / 2, h); c.bezierCurveTo(w * 0.1, h, 0, h * 0.5, w / 2, 4); c.fill();
  });
  // ciel du soir vu par les fenêtres
  T.ciel = toile(256, 512, (c, w, h) => {
    const g = c.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, "#2a3a6e"); g.addColorStop(0.38, "#c56f52"); g.addColorStop(0.62, "#f6a95e"); g.addColorStop(0.8, "#ffd9a0"); g.addColorStop(1, "#ffe9c2");
    c.fillStyle = g; c.fillRect(0, 0, w, h);
    const r = hasard(5);
    for (let k = 0; k < 14; k++) { c.fillStyle = `rgba(255,${170 + r() * 60},${120 + r() * 60},${0.08 + r() * 0.1})`; c.beginPath(); c.ellipse(r() * w, 120 + r() * 200, 40 + r() * 70, 4 + r() * 6, 0, 0, 7); c.fill(); }
  });
  // tranche des livres (bandes dorées)
  T.livre = toile(64, 256, (c, w, h) => {
    c.fillStyle = "#d8d0c0"; c.fillRect(0, 0, w, h);
    c.fillStyle = "#fff4cc"; for (const y of [18, 28, 200, 214]) c.fillRect(0, y, w, 5);
    c.fillStyle = "#b9ab8c"; c.fillRect(10, 80, w - 20, 60);
  });
  T.feuille = toile(128, 256, (c, w, h) => {
    const g = c.createLinearGradient(0, 0, w, 0); g.addColorStop(0, "#1f4a26"); g.addColorStop(0.5, "#3f7a3c"); g.addColorStop(1, "#1d4322");
    c.fillStyle = g; c.beginPath(); c.moveTo(w / 2, 4); c.bezierCurveTo(w + 10, h * 0.3, w * 0.8, h * 0.85, w / 2, h - 4);
    c.bezierCurveTo(w * 0.2, h * 0.85, -10, h * 0.3, w / 2, 4); c.fill();
    c.strokeStyle = "rgba(160,200,120,.5)"; c.lineWidth = 2; c.beginPath(); c.moveTo(w / 2, 8); c.lineTo(w / 2, h - 8); c.stroke();
  });
  T.doux = toile(128, 128, (c, w, h) => {
    const g = c.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
    g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(0.4, "rgba(255,255,255,.35)"); g.addColorStop(1, "rgba(255,255,255,0)");
    c.fillStyle = g; c.fillRect(0, 0, w, h);
  });
  T.clavier = toile(256, 80, (c, w, h) => {
    c.fillStyle = "#16171b"; c.fillRect(0, 0, w, h);
    c.fillStyle = "#2a2c33";
    for (let y = 0; y < 5; y++) for (let x = 0; x < 15; x++) c.fillRect(6 + x * 16.5, 6 + y * 14.5, 13, 11);
  });
  T.led = toile(128, 256, (c, w, h) => {
    c.fillStyle = "#07090f"; c.fillRect(0, 0, w, h);
    const r = hasard(9);
    for (let y = 6; y < h; y += 12) {
      c.fillStyle = "#121a2a"; c.fillRect(6, y, w - 12, 9);
      c.fillStyle = r() < 0.7 ? "#3d8bff" : "#40d890"; c.fillRect(w - 22, y + 3, 4, 3);
      c.fillStyle = "#1e2c44"; c.fillRect(12, y + 3, 40, 2);
    }
  });
  T.globe = toile(512, 256, (c, w, h) => {
    c.fillStyle = "#c9b78e"; c.fillRect(0, 0, w, h);
    c.strokeStyle = "rgba(90,60,25,.45)"; c.lineWidth = 1.2;
    for (let x = 0; x <= w; x += w / 12) { c.beginPath(); c.moveTo(x, 0); c.lineTo(x, h); c.stroke(); }
    for (let y = 0; y <= h; y += h / 6) { c.beginPath(); c.moveTo(0, y); c.lineTo(w, y); c.stroke(); }
    const g = c.createLinearGradient(0, 0, 0, h); g.addColorStop(0, "rgba(80,50,20,.35)"); g.addColorStop(0.5, "rgba(0,0,0,0)"); g.addColorStop(1, "rgba(80,50,20,.35)");
    c.fillStyle = g; c.fillRect(0, 0, w, h);
  });
}

function materiaux() {
  textures();
  M = {
    sol: phy({ map: T.marbre, roughness: 0.5, metalness: 0, specularIntensity: 0.5, clearcoat: 0.35, clearcoatRoughness: 0.35 }),
    damas: std({ map: T.damas, roughness: 0.9 }),
    pierre: std({ color: 0x2a2620, roughness: 0.55 }),
    pierreClaire: std({ color: 0x8c8274, roughness: 0.5 }),
    or: std({ color: 0xd8ac55, metalness: 1, roughness: 0.25 }),
    laiton: std({ color: 0xc89b4a, metalness: 1, roughness: 0.35 }),
    bois: phy({ map: T.bois, roughness: 0.4, clearcoat: 0.7, clearcoatRoughness: 0.12 }),
    boisMat: std({ map: T.bois, color: 0xb59a86, roughness: 0.6 }),
    cuir: phy({ color: 0x3a1c12, roughness: 0.45, sheen: 0.4, sheenColor: 0x6a3a22, clearcoat: 0.3, clearcoatRoughness: 0.4 }),
    cuirNoir: phy({ color: 0x141214, roughness: 0.42, clearcoat: 0.35, clearcoatRoughness: 0.35 }),
    sousMain: std({ color: 0x173326, roughness: 0.7 }),
    metal: std({ color: 0x23252b, metalness: 0.85, roughness: 0.32 }),
    chrome: std({ color: 0xd6d8de, metalness: 1, roughness: 0.12 }),
    noir: std({ color: 0x0b0c0f, roughness: 0.35, metalness: 0.3 }),
    papier: std({ color: 0xeee8da, roughness: 0.9 }),
    porcelaine: std({ color: 0xf2efe8, roughness: 0.25 }),
    verre: phy({ color: 0xcfe3ff, roughness: 0.03, metalness: 0, transparent: true, opacity: 0.22, clearcoat: 1 }),
    verreVert: phy({ color: 0x1d6b3e, roughness: 0.15, transparent: true, opacity: 0.92, emissive: 0x0a3a1c, emissiveIntensity: 0.6, side: THREE.DoubleSide }),
    clavier: std({ map: T.clavier, roughness: 0.6 }),
    feuille: std({ map: T.feuille, alphaTest: 0.5, side: THREE.DoubleSide, roughness: 0.7 }),
    pot: std({ color: 0x2b2420, roughness: 0.5, metalness: 0.2 }),
    terre: std({ color: 0x1c140e, roughness: 1 }),
    chemise: std({ color: 0xece9e2, roughness: 0.7 }),
    pantalon: std({ color: 0x15171c, roughness: 0.75 }),
    chaussure: phy({ color: 0x120c08, roughness: 0.3, clearcoat: 0.8 }),
    velours: phy({ color: 0x4a0d14, roughness: 0.85, sheen: 1, sheenRoughness: 0.4, sheenColor: 0xa83a44, side: THREE.DoubleSide }),
    ciel: new THREE.MeshBasicMaterial({ map: T.ciel, toneMapped: false, color: new THREE.Color(1.25, 1.15, 1.05) }),
    ampoule: new THREE.MeshBasicMaterial({ color: new THREE.Color(3, 2.3, 1.4), toneMapped: false }),
    cristal: std({ color: 0xffffff, metalness: 1, roughness: 0.02 }),
    parquet: std({ map: T.parquet, roughness: 0.5 }),
    plafond: std({ map: T.plafond, roughness: 0.85 }),
    plafondNoyer: std({ map: T.plafondNoyer, roughness: 0.6 }),
    boiserie: std({ map: T.boiserie, roughness: 0.55 }),
    couloir: std({ map: T.couloir, roughness: 0.95 }),
    capot: std({ color: 0x2b1a0f, roughness: 0.45, metalness: 0.1 }),
    marbreBlanc: phy({ color: 0xe9e3d6, roughness: 0.22, clearcoat: 0.5, clearcoatRoughness: 0.2 }),
    abatJour: std({ color: 0xf1dfbd, emissive: 0xffc070, emissiveIntensity: 0.85, roughness: 0.8, side: THREE.DoubleSide }),
    flamme: new THREE.MeshBasicMaterial({ map: T.flamme, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false,
      color: new THREE.Color(2.2, 1.6, 1.1), side: THREE.DoubleSide }),
    halo: (couleur, force = 1) => new THREE.MeshBasicMaterial({ map: T.doux, color: new THREE.Color(couleur).multiplyScalar(force), transparent: true,
      blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }),
  };
}

// lumière douce posée sur une surface (flaque de lumière d'une lampe, d'un lustre) : décor fixe
function flaque(x, y, z, taille, couleur, force) {
  const f = new THREE.Mesh(new THREE.PlaneGeometry(taille, taille), M.halo(couleur, force));
  f.rotation.x = -Math.PI / 2; f.position.set(x, y, z); f.renderOrder = 2; scene.add(f);
  return f;
}

// ------------------------------------------------------------------ la salle : murs percés de fenêtres, mezzanine
function fenetreForme(cx) {
  const s = new THREE.Path();
  s.moveTo(cx - FEN_L / 2, FEN_BAS); s.lineTo(cx + FEN_L / 2, FEN_BAS); s.lineTo(cx + FEN_L / 2, FEN_HAUT);
  s.absarc(cx, FEN_HAUT, FEN_L / 2, 0, Math.PI, false); s.lineTo(cx - FEN_L / 2, FEN_BAS);
  return s;
}
function verriere(cx) {
  const f = new THREE.Shape();
  f.moveTo(cx - FEN_L / 2, FEN_BAS); f.lineTo(cx + FEN_L / 2, FEN_BAS); f.lineTo(cx + FEN_L / 2, FEN_HAUT);
  f.absarc(cx, FEN_HAUT, FEN_L / 2, 0, Math.PI, false); f.lineTo(cx - FEN_L / 2, FEN_BAS);
  const g = new THREE.ShapeGeometry(f, 24);
  // UV 0..1 sur la fenêtre (la texture du ciel occupe toute l'arche)
  const pos = g.attributes.position, uv = g.attributes.uv;
  for (let i = 0; i < pos.count; i++) uv.setXY(i, (pos.getX(i) - cx + FEN_L / 2) / FEN_L, (pos.getY(i) - FEN_BAS) / (FEN_HAUT + FEN_L / 2 - FEN_BAS));
  return g;
}
// mur percé : u = position le long du mur, centres des fenêtres
// copie position / rotation / échelle (propriétés en lecture seule dans three.js) et le reste tel quel
function poser(o, props) {
  for (const k in props) { if (o[k] && o[k].copy) o[k].copy(props[k]); else o[k] = props[k]; }
  return o;
}

function mur(longueur, centres) {
  const s = new THREE.Shape();
  s.moveTo(-longueur / 2, 0); s.lineTo(longueur / 2, 0); s.lineTo(longueur / 2, MUR); s.lineTo(-longueur / 2, MUR); s.lineTo(-longueur / 2, 0);
  for (const c of centres) s.holes.push(fenetreForme(c));
  const g = new THREE.ExtrudeGeometry(s, { depth: 0.7, bevelEnabled: false, curveSegments: 16 });
  const m = new THREE.Mesh(g, M.damas); m.castShadow = true; m.receiveShadow = true;
  M.damas.map.repeat.set(0.4, 0.4);
  const groupe = new THREE.Group(); groupe.add(m);
  for (const c of centres) {
    const v = new THREE.Mesh(verriere(c), M.ciel); v.position.z = 0.15; groupe.add(v);
    // meneaux et traverses
    for (const dx of [-FEN_L / 6, FEN_L / 6]) groupe.add(boite(0.06, FEN_HAUT - FEN_BAS + FEN_L / 2 - 0.15, 0.08, M.noir, c + dx, (FEN_BAS + FEN_HAUT + FEN_L / 2) / 2 - 0.05, 0.2, true));
    for (const y of [FEN_BAS + 1.15, FEN_BAS + 2.3]) groupe.add(boite(FEN_L, 0.06, 0.08, M.noir, c, y, 0.2, true));
    groupe.add(boite(FEN_L + 0.5, 0.14, 0.5, M.pierreClaire, c, FEN_BAS - 0.07, 0.8));                     // appui
    const cle = arrondi(0.34, 0.5, 0.18, 0.04, M.or, c, FEN_HAUT + FEN_L / 2 + 0.12, 0.75); groupe.add(cle);  // clé de voûte
    for (const s2 of [-1, 1]) {   // rideaux de velours
      const geo = new THREE.PlaneGeometry(0.9, 5.6, 16, 1), p = geo.attributes.position;
      for (let i = 0; i < p.count; i++) p.setZ(i, Math.sin(p.getX(i) * 14) * 0.07);
      geo.computeVertexNormals();
      const r = new THREE.Mesh(geo, M.velours); r.position.set(c + s2 * (FEN_L / 2 + 0.5), FEN_BAS + 2.6, 0.85); r.castShadow = true; groupe.add(r);
      groupe.add(cyl(0.05, 0.05, 0.7, M.or, c + s2 * (FEN_L / 2 + 0.5), FEN_BAS + 1.6, 0.92, 8));
    }
  }
  return groupe;
}

// rayons du soleil couchant : volume lumineux qui part de la fenêtre dans la vraie direction du soleil
function rayons(coins, couleur) {
  const long = 16, geo = new THREE.BufferGeometry(), pos = [], f = [], idx = [];
  const loin = coins.map((c) => c.clone().addScaledVector(SOLEIL, long));
  const tous = [...coins, ...loin];
  for (const v of tous) pos.push(v.x, v.y, v.z);
  f.push(0, 0, 0, 0, 1, 1, 1, 1);
  for (let k = 0; k < 4; k++) { const a = k, b = (k + 1) % 4; idx.push(a, b, b + 4, a, b + 4, a + 4); }
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute("f", new THREE.Float32BufferAttribute(f, 1));
  geo.setIndex(idx);
  const m = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, toneMapped: false,
    uniforms: { couleur: { value: new THREE.Color(couleur) }, force: { value: LEGER ? 0.09 : 0.075 }, soleil: { value: SOLEIL } },
    vertexShader: "attribute float f; varying float vf; varying vec3 vp; void main(){ vf=f; vp=position; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }",
    // vus dans l'axe du soleil, les rayons s'empilent : on les efface pour éviter une tache blanche
    fragmentShader: "uniform vec3 couleur; uniform float force; uniform vec3 soleil; varying float vf; varying vec3 vp;" +
      "void main(){ float axe = abs(dot(normalize(cameraPosition - vp), soleil)); float a = pow(1.0-vf, 1.6) * smoothstep(0.0, 0.08, vf) * force * smoothstep(0.0, 1.2, vp.y) * (1.0 - smoothstep(0.55, 0.9, axe)); gl_FragColor = vec4(couleur*a, a); }",
  });
  const r = new THREE.Mesh(geo, m); r.renderOrder = 3; r.frustumCulled = false;
  scene.add(r);
}

function salle() {
  const S = plan.sol, mx = -L / 2 - 4, mz = -P / 2 - 4, lx = S.l + 8, lz = S.p + 8;
  const sol = new THREE.Mesh(new THREE.PlaneGeometry(lx + 30, lz + 30), M.sol);
  M.sol.map.repeat.set((lx + 30) / 4, (lz + 30) / 4);
  sol.rotation.x = -Math.PI / 2; sol.position.set(4, 0, 4); sol.receiveShadow = true; scene.add(sol);
  // mur du fond : fenêtres entre les colonnes
  const fondC = [], gaucheC = [];
  for (let x = mx; x + 3 < L / 2 + 4; x += 6) fondC.push(x + 3);
  for (let z = mz; z + 3 < P / 2 + 4; z += 6) gaucheC.push(z + 3);
  const fond = mur(lx, fondC); fond.position.set(0, 0, mz - 0.7); scene.add(fond);
  // mur de gauche : même mur tourné (u = -z)
  const gauche = mur(lz, gaucheC.map((z) => -z)); gauche.rotation.y = Math.PI / 2; gauche.position.set(mx - 0.7, 0, 0);
  scene.add(gauche);
  // rayons du soir (vraie direction du soleil, même que la lumière qui projette les ombres)
  for (const c of fondC) {
    const h = FEN_HAUT + 0.3;
    rayons([new THREE.Vector3(c - FEN_L / 2, FEN_BAS, mz), new THREE.Vector3(c + FEN_L / 2, FEN_BAS, mz),
      new THREE.Vector3(c + FEN_L / 2, h, mz), new THREE.Vector3(c - FEN_L / 2, h, mz)], 0xffb873);
  }
  for (const c of gaucheC) {
    const h = FEN_HAUT + 0.3;
    rayons([new THREE.Vector3(mx, FEN_BAS, c - FEN_L / 2), new THREE.Vector3(mx, FEN_BAS, c + FEN_L / 2),
      new THREE.Vector3(mx, h, c + FEN_L / 2), new THREE.Vector3(mx, h, c - FEN_L / 2)], 0xffa860);
  }
  // colonnes (fût cannelé, base et chapiteau dorés) devant les murs
  const fut = new THREE.CylinderGeometry(0.4, 0.46, MUR - 0.9, 24);
  const posC = [];
  for (let x = mx; x <= L / 2 + 4.01; x += 6) posC.push([x, mz + 0.45]);
  for (let z = mz + 6; z <= P / 2 + 4.01; z += 6) posC.push([mx + 0.45, z]);
  for (const [x, z] of posC) {
    scene.add(ombre(poser(new THREE.Mesh(fut, M.pierreClaire), { position: new THREE.Vector3(x, (MUR - 0.9) / 2 + 0.45, z) })));
    scene.add(arrondi(1.05, 0.45, 1.05, 0.05, M.pierre, x, 0.22, z));
    scene.add(arrondi(1.15, 0.4, 1.15, 0.05, M.or, x, MUR - 0.25, z));
  }
  // corniche dorée
  scene.add(boite(lx + 0.6, 0.3, 1, M.or, 0, MUR + 0.1, mz + 0.2, false));
  scene.add(boite(1, 0.3, lz + 0.6, M.or, mx + 0.2, MUR + 0.1, 0, false));
  // lambris de noyer sous la mezzanine, avec appliques
  const lam = 2.6;
  scene.add(boite(lx, lam, 0.12, M.boisMat, 0, lam / 2, mz + 0.08, false));
  scene.add(boite(0.12, lam, lz, M.boisMat, mx + 0.08, lam / 2, 0, false));
  scene.add(boite(lx, 0.06, 0.16, M.or, 0, lam, mz + 0.1, false));
  scene.add(boite(0.16, 0.06, lz, M.or, mx + 0.1, lam, 0, false));
  for (let x = mx + 1; x < L / 2 + 4; x += 2) scene.add(boite(1.6, 1.7, 0.05, M.bois, x + 0.0, 1.2, mz + 0.17, false));
  for (let z = mz + 1; z < P / 2 + 4; z += 2) scene.add(boite(0.05, 1.7, 1.6, M.bois, mx + 0.17, 1.2, z, false));
  for (let x = mx + 3; x < L / 2 + 4; x += 6) {
    scene.add(poser(new THREE.Mesh(new THREE.SphereGeometry(0.09, 12, 8), M.ampoule), { position: new THREE.Vector3(x, 3.3, mz + 0.35) }));
    const h = new THREE.Mesh(new THREE.PlaneGeometry(1.6, 1.6), M.halo(0xffb066, 0.55)); h.position.set(x, 3.3, mz + 0.16); scene.add(h);
  }
  // mezzanine : dalle, bandeau de noyer, balustrade de laiton, spots dessous
  scene.add(boite(lx, 0.35, 2.6, M.pierre, 0, MEZZ, mz + 1.4));
  scene.add(boite(2.6, 0.35, lz, M.pierre, mx + 1.4, MEZZ, 0));
  scene.add(boite(lx, 0.45, 0.08, M.bois, 0, MEZZ - 0.05, mz + 2.72, false));
  scene.add(boite(0.08, 0.45, lz, M.bois, mx + 2.72, MEZZ - 0.05, 0, false));
  scene.add(boite(lx, 0.07, 0.1, M.or, 0, MEZZ + 0.21, mz + 2.75, false));
  scene.add(boite(0.1, 0.07, lz, M.or, mx + 2.75, MEZZ + 0.21, 0, false));
  scene.add(arrondi(lx, 0.09, 0.14, 0.03, M.bois, 0, MEZZ + 1.15, mz + 2.62, false));
  scene.add(arrondi(0.14, 0.09, lz, 0.03, M.bois, mx + 2.62, MEZZ + 1.15, 0, false));
  const balustre = new THREE.CylinderGeometry(0.03, 0.045, 0.9, 10);
  const nb = Math.round(lx / 0.35) + Math.round(lz / 0.35) + 4;
  const bal = new THREE.InstancedMesh(balustre, M.laiton, nb), m4 = new THREE.Matrix4(); let i = 0;
  for (let x = mx; x < L / 2 + 4 && i < nb; x += 0.35) bal.setMatrixAt(i++, m4.makeTranslation(x, MEZZ + 0.65, mz + 2.62));
  for (let z = mz; z < P / 2 + 4 && i < nb; z += 0.35) bal.setMatrixAt(i++, m4.makeTranslation(mx + 2.62, MEZZ + 0.65, z));
  bal.count = i; bal.castShadow = true; scene.add(bal);
  for (let x = mx + 1.5; x < L / 2 + 4; x += 3) scene.add(poser(new THREE.Mesh(new THREE.CircleGeometry(0.07, 12), M.ampoule), { position: new THREE.Vector3(x, MEZZ - 0.18, mz + 2.2), rotation: new THREE.Euler(Math.PI / 2, 0, 0) }));
  for (let z = mz + 1.5; z < P / 2 + 4; z += 3) scene.add(poser(new THREE.Mesh(new THREE.CircleGeometry(0.07, 12), M.ampoule), { position: new THREE.Vector3(mx + 2.2, MEZZ - 0.18, z), rotation: new THREE.Euler(Math.PI / 2, 0, 0) }));
  // bordure dorée du hall
  for (const [l, p, x, z] of [[S.l + 1, 0.1, 0, -P / 2 - 0.5], [S.l + 1, 0.1, 0, P / 2 + 0.5], [0.1, S.p + 1, -L / 2 - 0.5, 0], [0.1, S.p + 1, L / 2 + 0.5, 0]]) {
    const b = new THREE.Mesh(new THREE.PlaneGeometry(l, p), M.or); b.rotation.x = -Math.PI / 2; b.position.set(x, 0.004, z); scene.add(b);
  }
  // poussière dans la lumière (décor, ne représente aucune activité)
  if (!camera3d) {
    const n = telephone ? 260 : 650, g = new THREE.BufferGeometry(), p = [], r = hasard(21);
    for (let k = 0; k < n; k++) {
      const depart = fondC[Math.floor(r() * fondC.length)];
      const o = new THREE.Vector3(depart + (r() - 0.5) * FEN_L, FEN_BAS + r() * 3.5, mz).addScaledVector(SOLEIL, 1 + r() * 9);
      p.push(o.x, o.y, o.z);
    }
    g.setAttribute("position", new THREE.Float32BufferAttribute(p, 3));
    poussiere = new THREE.Points(g, new THREE.PointsMaterial({ map: T.doux, size: 0.06, color: 0xffd6a0, transparent: true, opacity: 0.55,
      blending: THREE.AdditiveBlending, depthWrite: false }));
    poussiere.userData.base = Float32Array.from(p);
    scene.add(poussiere);
  }
}

function environnement() {
  // reflets : une pièce sombre et chaude avec des fenêtres lumineuses (pour le marbre ciré, le laiton, le cuir)
  const env = new THREE.Scene();
  env.add(new THREE.Mesh(new THREE.BoxGeometry(40, 14, 40), new THREE.MeshBasicMaterial({ color: 0x150e09, side: THREE.BackSide })));
  const chaud = new THREE.MeshBasicMaterial({ color: new THREE.Color(6, 3.6, 1.8) });
  for (let k = -2; k <= 2; k++) { const f = new THREE.Mesh(new THREE.PlaneGeometry(3, 6), chaud); f.position.set(k * 7, 2, -19.5); env.add(f); }
  for (let k = -2; k <= 2; k++) { const f = new THREE.Mesh(new THREE.PlaneGeometry(3, 6), chaud); f.position.set(-19.5, 2, k * 7); f.rotation.y = Math.PI / 2; env.add(f); }
  const lustre = new THREE.MeshBasicMaterial({ color: new THREE.Color(4, 3, 2) });
  for (const [x, z] of [[-8, -8], [8, -6], [0, 6], [10, 10]]) { const s = new THREE.Mesh(new THREE.SphereGeometry(0.8, 12, 8), lustre); s.position.set(x, 5.5, z); env.add(s); }
  const pm = new THREE.PMREMGenerator(renderer);
  scene.environment = pm.fromScene(env, 0.03).texture;
  scene.environmentIntensity = 0.55;
}

// lustre de cristal (deux couronnes de bougies, pampilles), tige jusqu'au plafond
let geoLustre = null;
function lustre(pos, ech, tige) {
  if (!geoLustre) geoLustre = { anneau: new THREE.TorusGeometry(1, 0.045, 10, 48), petit: new THREE.TorusGeometry(0.55, 0.035, 8, 32),
    bougie: new THREE.SphereGeometry(0.075, 10, 8), pampille: new THREE.OctahedronGeometry(0.06, 0),
    coupe: new THREE.SphereGeometry(0.28, 16, 10, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2) };
  const G = geoLustre, g = new THREE.Group(); g.position.copy(pos); g.scale.setScalar(ech);
  for (const [geo, y, r] of [[G.anneau, 0, 1], [G.petit, 0.55, 0.55]]) {
    const a = new THREE.Mesh(geo, M.or); a.rotation.x = Math.PI / 2; a.position.y = y; g.add(a);
    const n = r > 0.7 ? 12 : 8;
    for (let k = 0; k < n; k++) {
      const ang = (k / n) * Math.PI * 2;
      const b = new THREE.Mesh(G.bougie, M.ampoule); b.position.set(Math.cos(ang) * r, y + 0.16, Math.sin(ang) * r); g.add(b);
      const p = new THREE.Mesh(G.pampille, M.cristal); p.scale.set(1, 2.2, 1); p.position.set(Math.cos(ang + 0.2) * r, y - 0.2, Math.sin(ang + 0.2) * r); g.add(p);
    }
  }
  const t = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, tige / ech, 6), M.or); t.position.y = tige / ech / 2; g.add(t);
  const c = new THREE.Mesh(G.coupe, M.or); c.position.y = -0.1; g.add(c);
  scene.add(g);
  return g;
}

function lumieres() {
  scene.add(new THREE.HemisphereLight(0x6a78a8, 0x2a1a0e, 0.35));
  // soleil du soir : entre par les fenêtres (les murs portent ombre), long reflets dorés au sol
  const soleil = new THREE.DirectionalLight(0xffa868, 3.2);
  soleil.position.copy(SOLEIL).multiplyScalar(-60); soleil.target.position.set(0, 0, 0);
  soleil.castShadow = true;
  soleil.shadow.mapSize.set(LEGER ? 1024 : 4096, LEGER ? 1024 : 4096);
  Object.assign(soleil.shadow.camera, { left: -42, right: 42, top: 34, bottom: -34, near: 10, far: 130 });
  soleil.shadow.bias = -0.0004; soleil.shadow.normalBias = 0.04; soleil.shadow.radius = 3;
  scene.add(soleil, soleil.target);
  // lustres du grand hall, au-dessus des allées (deux grands éclairent, les autres décorent)
  for (const [x, y, fort] of [[9, 15, true], [39, 15, true], [18, 15, false], [30, 15, false], [24, 10, false], [24, 20, false]]) {
    const pos = P3(x, y, fort ? 7 : 7.6);
    lustre(pos, fort ? 1 : 0.6, MUR + 1 - pos.y);
    if (!fort) continue;
    const l = new THREE.PointLight(0xffc27a, 26, 22, 1.8); l.position.copy(pos).add(new THREE.Vector3(0, -0.3, 0)); scene.add(l);
    flaque(pos.x, 0.03, pos.z, 9, 0xffb060, 0.07);
  }
}

// ------------------------------------------------------------------ bureaux fermés : murs pleins, ouverture sans porte
// Vue d'ensemble en « maison de poupée » : les murs dont la face extérieure regarde la caméra s'abaissent à 1 m
// (plan de coupe par orientation), les autres restent debout. À hauteur d'homme tous les murs sont debout, et le
// plafond à caissons de la pièce où l'on se trouve apparaît.
const EP = 0.16, PORTE_H = 2.55, COUPE_BAS = 1.0, PLEIN = 3.6;
const COTES = ["x0", "x1", "y0", "y1"];
const NORMALES = { x0: new THREE.Vector3(-1, 0, 0), x1: new THREE.Vector3(1, 0, 0), y0: new THREE.Vector3(0, 0, -1), y1: new THREE.Vector3(0, 0, 1) };
const coupes = {}, matsCoupe = new Map(), murs3d = [], pieces = {};
for (const c of COTES) coupes[c] = { plan: new THREE.Plane(new THREE.Vector3(0, -1, 0), PLEIN), h: PLEIN, caps: [] };
const COURTS = { directeur: "Directeur", analyse: "Analyse", macro: "Macro", reunion: "Réunion", bibliotheque: "Bibliothèque",
  labo: "Labo quant", risque: "Risques", donnees: "Données" };

// matériau coupé avec les murs de ce côté (une copie par côté, partagée)
function mc(m, cote) {
  if (Array.isArray(m)) return m.map((x) => mc(x, cote));
  const k = m.uuid + cote;
  if (!matsCoupe.has(k)) { const r = m.clone(); r.clippingPlanes = [coupes[cote].plan]; r.clipShadows = true; matsCoupe.set(k, r); }
  return matsCoupe.get(k);
}
function couper(o, cote) { o.traverse((m) => { if (m.isMesh) m.material = mc(m.material, cote); }); return o; }
// une face d'un mur : où elle est (plan) et vers où elle regarde
function face(z, cote, dedans) {
  const e = dedans ? EP : 0;
  if (cote === "x0") return { vertical: true, pos: z.x + e, dir: dedans ? 1 : -1 };
  if (cote === "x1") return { vertical: true, pos: z.x + z.l - e, dir: dedans ? -1 : 1 };
  if (cote === "y0") return { vertical: false, pos: z.y + e, dir: dedans ? 1 : -1 };
  return { vertical: false, pos: z.y + z.p - e, dir: dedans ? -1 : 1 };
}
// moulure contre un mur : de s0 à s1 le long du mur, de y0 à y1 en hauteur
function contre(z, cote, dedans, s0, s1, y0, y1, saillie, mat) {
  const f = face(z, cote, dedans), c = f.pos + f.dir * saillie / 2;
  const geo = f.vertical ? new THREE.BoxGeometry(saillie, y1 - y0, s1 - s0) : new THREE.BoxGeometry(s1 - s0, y1 - y0, saillie);
  const b = new THREE.Mesh(geo, mc(mat, cote));
  b.position.copy(f.vertical ? P3(c, (s0 + s1) / 2, (y0 + y1) / 2) : P3((s0 + s1) / 2, c, (y0 + y1) / 2));
  scene.add(ombre(b, false));
  return b;
}
// groupe accroché à un mur : son +z regarde la pièce (ou l'allée)
function surMur(z, cote, dedans, s, h) {
  const f = face(z, cote, dedans), g = new THREE.Group();
  g.position.copy(f.vertical ? P3(f.pos, s, h) : P3(s, f.pos, h));
  g.rotation.y = f.vertical ? (f.dir > 0 ? Math.PI / 2 : -Math.PI / 2) : (f.dir > 0 ? 0 : Math.PI);
  g.userData.cote = cote;
  return g;
}
function poserMur(g) { couper(g, g.userData.cote); scene.add(g); return g; }
// coordonnées de texture prises dans le monde (motifs continus d'un pan à l'autre)
function uvMonde(geo, pas, hauteur) {
  const p = geo.attributes.position, n = geo.attributes.normal, uv = geo.attributes.uv;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), y = p.getY(i), z = p.getZ(i);
    if (Math.abs(n.getY(i)) > 0.5) uv.setXY(i, x / pas, z / pas);
    else if (Math.abs(n.getX(i)) > 0.5) uv.setXY(i, z / pas, y / hauteur);
    else uv.setXY(i, x / pas, y / hauteur);
  }
}
// un pan de mur plein (de a à b le long du côté, de y0 à y1 en hauteur) + son couvercle quand il est coupé
function pan(z, cote, a, b, y0, y1, mInt) {
  const vertical = cote[0] === "x", milieu = face(z, cote, true).pos - face(z, cote, true).dir * EP / 2;
  const geo = vertical ? new THREE.BoxGeometry(EP, y1 - y0, b - a) : new THREE.BoxGeometry(b - a, y1 - y0, EP);
  const c = vertical ? P3(milieu, (a + b) / 2, (y0 + y1) / 2) : P3((a + b) / 2, milieu, (y0 + y1) / 2);
  geo.translate(c.x, c.y, c.z); uvMonde(geo, 1.6, z.h);
  const ext = M.boiserie, bout = M.bois;
  const mats = vertical ? (cote === "x0" ? [mInt, ext, bout, bout, bout, bout] : [ext, mInt, bout, bout, bout, bout])
    : (cote === "y0" ? [bout, bout, bout, bout, mInt, ext] : [bout, bout, bout, bout, ext, mInt]);
  const m = new THREE.Mesh(geo, mc(mats, cote)); ombre(m); m.userData.mur = cote; scene.add(m); murs3d.push(m);
  const cap = new THREE.Mesh(vertical ? new THREE.BoxGeometry(EP + 0.04, 0.035, b - a) : new THREE.BoxGeometry(b - a, 0.035, EP + 0.04), M.capot);
  cap.position.set(c.x, 0, c.z); cap.visible = false; cap.userData = { bas: y0, haut: y1 }; cap.receiveShadow = true;
  scene.add(cap); coupes[cote].caps.push(cap);
}
function murs(z, piece) {
  const o = z.porte, H = z.h;
  for (const cote of COTES) {
    const vertical = cote[0] === "x";
    const s0 = vertical ? z.y + EP : z.x, s1 = vertical ? z.y + z.p - EP : z.x + z.l;
    const i0 = vertical ? s0 : z.x + EP, i1 = vertical ? s1 : z.x + z.l - EP;
    const porte = o && o.cote === cote ? [o.centre - o.l / 2, o.centre + o.l / 2] : null;
    const morceaux = (a, b) => (porte ? [[a, porte[0] - 0.14], [porte[1] + 0.14, b]] : [[a, b]]);
    if (porte) { pan(z, cote, s0, porte[0], 0, H, piece.mur); pan(z, cote, porte[1], s1, 0, H, piece.mur); pan(z, cote, porte[0], porte[1], PORTE_H, H, piece.mur); }
    else pan(z, cote, s0, s1, 0, H, piece.mur);
    // intérieur : plinthe, cimaise, corniche à filet doré ; extérieur : plinthe et corniche
    for (const [a, b] of morceaux(i0, i1)) { contre(z, cote, true, a, b, 0, 0.14, 0.03, M.bois); contre(z, cote, true, a, b, 0.93, 0.99, 0.035, M.bois); }
    contre(z, cote, true, i0, i1, H - 0.2, H, 0.09, M.bois);
    contre(z, cote, true, i0, i1, H - 0.25, H - 0.2, 0.06, M.or);
    const e0 = vertical ? z.y : z.x - 0.03, e1 = vertical ? z.y + z.p : z.x + z.l + 0.03;
    for (const [a, b] of morceaux(e0, e1)) contre(z, cote, false, a, b, 0, 0.16, 0.03, M.bois);
    contre(z, cote, false, e0, e1, H - 0.14, H, 0.06, M.bois);
    contre(z, cote, false, e0, e1, H - 0.18, H - 0.14, 0.05, M.or);
    if (porte) encadrement(z, cote, o, piece);
  }
}
// ouverture sans porte : chambranle de noyer, filet doré, seuil de marbre, lanterne d'état, plaque au nom de la pièce
function encadrement(z, cote, o, piece) {
  const a = o.centre - o.l / 2, b = o.centre + o.l / 2;
  for (const dedans of [true, false]) {
    contre(z, cote, dedans, a - 0.14, a, 0, PORTE_H + 0.14, 0.05, M.bois);
    contre(z, cote, dedans, b, b + 0.14, 0, PORTE_H + 0.14, 0.05, M.bois);
    contre(z, cote, dedans, a - 0.14, b + 0.14, PORTE_H, PORTE_H + 0.14, 0.05, M.bois);
    contre(z, cote, dedans, a - 0.04, b + 0.04, PORTE_H + 0.15, PORTE_H + 0.18, 0.06, M.or);
    // lanterne : sa couleur est l'état réel des agents de la pièce (bleu = au travail)
    const g = surMur(z, cote, dedans, o.centre, PORTE_H + 0.42);
    g.add(arrondi(0.2, 0.04, 0.14, 0.01, M.laiton, 0, -0.1, 0.07));
    g.add(cyl(0.008, 0.008, 0.12, M.laiton, 0, -0.02, 0.02, 6));
    const verre = new THREE.Mesh(new THREE.SphereGeometry(0.065, 16, 10), piece.lampe); verre.position.set(0, -0.02, 0.09); g.add(verre);
    const halo = new THREE.Mesh(new THREE.PlaneGeometry(0.9, 0.9), M.halo(0xffd9a0, 0.25)); halo.position.set(0, -0.02, 0.005); g.add(halo);
    poserMur(g);
    piece.lampes.add(verre.material); piece.halos.add(halo.material);
  }
  const f = face(z, cote, false), mil = f.pos - f.dir * EP / 2;
  const seuil = new THREE.Mesh(f.vertical ? new THREE.BoxGeometry(EP + 0.08, 0.012, o.l) : new THREE.BoxGeometry(o.l, 0.012, EP + 0.08), M.pierreClaire);
  seuil.position.copy(f.vertical ? P3(mil, o.centre, 0.006) : P3(o.centre, mil, 0.006)); seuil.receiveShadow = true; scene.add(seuil);
  const ext = surMur(z, cote, false, b + 0.8, 1.55);
  const tex = toile(512, 144, (cx, w, h) => {
    const g = cx.createLinearGradient(0, 0, 0, h); g.addColorStop(0, "#e2c27a"); g.addColorStop(0.5, "#b88d3e"); g.addColorStop(1, "#8a6526");
    cx.fillStyle = g; cx.fillRect(0, 0, w, h); cx.strokeStyle = "#5a3f14"; cx.lineWidth = 4; cx.strokeRect(10, 10, w - 20, h - 20);
    cx.fillStyle = "#3a2608"; cx.font = "600 36px Georgia, serif"; cx.textAlign = "center"; cx.textBaseline = "middle";
    cx.fillText(z.nom.toUpperCase(), w / 2, h / 2 + 2, w - 50);
  });
  ext.add(poser(new THREE.Mesh(new THREE.PlaneGeometry(0.95, 0.27), std({ map: tex, metalness: 0.6, roughness: 0.35 })), { position: new THREE.Vector3(0, 0, 0.012) }));
  poserMur(ext);
}
function tableauMur(z, cote, s, h, larg, haut, n) {
  const g = surMur(z, cote, true, s, h), e = 0.07;
  for (const [l, hh, x, y] of [[larg + 2 * e, e, 0, (haut + e) / 2], [larg + 2 * e, e, 0, -(haut + e) / 2], [e, haut, (larg + e) / 2, 0], [e, haut, -(larg + e) / 2, 0]]) g.add(boite(l, hh, 0.06, M.or, x, y, 0.03, false));
  g.add(poser(new THREE.Mesh(new THREE.PlaneGeometry(larg, haut), std({ map: T.tableaux[n % T.tableaux.length], roughness: 0.75 })), { position: new THREE.Vector3(0, 0, 0.012) }));
  const barre = cyl(0.012, 0.012, larg * 0.6, M.laiton, 0, haut / 2 + 0.12, 0.12, 8); barre.rotation.z = Math.PI / 2; g.add(barre);
  g.add(poser(new THREE.Mesh(new THREE.PlaneGeometry(larg * 1.3, haut * 1.1), M.halo(0xffd8a0, 0.2)), { position: new THREE.Vector3(0, haut * 0.15, 0.02) }));
  return poserMur(g);
}
function applique(z, cote, s, h) {
  const g = surMur(z, cote, true, s, h);
  g.add(arrondi(0.09, 0.18, 0.03, 0.01, M.laiton, 0, 0, 0.015));
  const bras = cyl(0.01, 0.01, 0.16, M.laiton, 0, 0.02, 0.09, 6); bras.rotation.x = Math.PI / 2; g.add(bras);
  g.add(poser(new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.085, 0.13, 18, 1, true), M.abatJour), { position: new THREE.Vector3(0, 0.12, 0.17) }));
  g.add(poser(new THREE.Mesh(new THREE.PlaneGeometry(1.2, 1.2), M.halo(0xffb870, 0.3)), { position: new THREE.Vector3(0, 0.12, 0.004) }));
  return poserMur(g);
}
// écran mural : contenu réel dessiné à part (bougies fermées, échanges entre agents)
function ecranMural(z, cote, s, h, larg, haut) {
  const g = surMur(z, cote, true, s, h);
  g.add(arrondi(larg + 0.08, haut + 0.08, 0.06, 0.015, M.noir, 0, 0, 0.03));
  const e = ecranTexture(1024, Math.round(1024 * haut / larg));
  g.add(poser(new THREE.Mesh(new THREE.PlaneGeometry(larg, haut), new THREE.MeshBasicMaterial({ map: e.t, toneMapped: false, color: 0xdadada })), { position: new THREE.Vector3(0, 0, 0.062) }));
  g.add(poser(new THREE.Mesh(new THREE.PlaneGeometry(larg * 1.5, haut * 1.7), M.halo(0x5a8ad0, 0.1)), { position: new THREE.Vector3(0, 0, 0.005) }));
  poserMur(g);
  const c = e.c.getContext("2d"); c.fillStyle = "#070c16"; c.fillRect(0, 0, e.c.width, e.c.height); e.t.needsUpdate = true;
  return e;
}
// horloge murale à l'heure réelle d'une place financière
function horlogeMurale(z, cote, s, h, ville, tz) {
  const g = surMur(z, cote, true, s, h);
  const c = document.createElement("canvas"); c.width = c.height = 256;
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
  g.add(poser(new THREE.Mesh(new THREE.CircleGeometry(0.3, 48), new THREE.MeshBasicMaterial({ map: tex, color: 0xcfc6b0 })), { position: new THREE.Vector3(0, 0, 0.035) }));
  g.add(poser(new THREE.Mesh(new THREE.TorusGeometry(0.31, 0.025, 10, 48), M.laiton), { position: new THREE.Vector3(0, 0, 0.035) }));
  g.add(cyl(0.3, 0.3, 0.03, M.boisMat, 0, 0, 0.015, 32)); g.children[g.children.length - 1].rotation.x = Math.PI / 2;
  const nom = toile(256, 54, (x, w, hh) => {
    x.fillStyle = "#b88d3e"; x.fillRect(0, 0, w, hh); x.fillStyle = "#2a1a06"; x.font = "700 26px Georgia, serif";
    x.textAlign = "center"; x.textBaseline = "middle"; x.fillText(ville, w / 2, hh / 2 + 1);
  });
  g.add(poser(new THREE.Mesh(new THREE.PlaneGeometry(0.62, 0.13), std({ map: nom, metalness: 0.6, roughness: 0.35 })), { position: new THREE.Vector3(0, -0.45, 0.015) }));
  poserMur(g);
  horloges.push({ c, tex, tz, minute: -1 });
}
function cheminee(z, cote, s) {
  const g = surMur(z, cote, true, s, 0);
  for (const x of [-0.86, 0.86]) g.add(boite(0.38, 1.15, 0.36, M.marbreBlanc, x, 0.575, 0.18));
  g.add(boite(2.1, 0.32, 0.36, M.marbreBlanc, 0, 0.99, 0.18));
  g.add(boite(2.3, 0.07, 0.48, M.marbreBlanc, 0, 1.19, 0.22));
  g.add(boite(1.34, 0.84, 0.04, M.noir, 0, 0.42, 0.02, false));
  g.add(boite(2.3, 0.05, 0.62, M.marbreBlanc, 0, 0.025, 0.33));
  for (const [x, y, a] of [[-0.12, 0.12, 0.25], [0.12, 0.12, -0.2], [0, 0.22, 0.05]]) { const b = cyl(0.06, 0.06, 0.8, M.boisMat, x, y, 0.2, 10); b.rotation.set(0, a, Math.PI / 2); g.add(b); }
  const flammes = [];
  for (const x of [-0.22, 0.02, 0.24]) { const f = new THREE.Mesh(new THREE.PlaneGeometry(0.34, 0.6), M.flamme); f.position.set(x, 0.5, 0.2); g.add(f); flammes.push(f); }
  const lum = new THREE.PointLight(0xff8a3a, 2.5, 6, 2); lum.position.set(0, 0.55, 0.6); g.add(lum);
  poserMur(g);
  feu = { flammes, lum };
}

// habillage de chaque pièce : tableaux et appliques, écrans muraux, horloges du monde, cheminée
const TABLEAUX = { analyse: [["x0", 7, 0], ["x1", 7, 1]], macro: [["x0", 7, 2], ["x1", 7, 3]], reunion: [["x0", 5, 1], ["x1", 5, 0]],
  directeur: [["x1", 13.4, 3]], bibliotheque: [["x0", 23, 2], ["x1", 23, 0]], labo: [["x1", 25, 3]], risque: [["x1", 23.5, 1]] };
function habillage(z) {
  for (const [cote, s, n] of TABLEAUX[z.cle] || []) {
    tableauMur(z, cote, s, 1.95, 1.5, 0.95, n);
    applique(z, cote, s - 1.3, 2.05); applique(z, cote, s + 1.3, 2.05);
  }
  if (z.cle === "analyse") grand = ecranMural(z, "y0", z.x + z.l / 2, 2.05, 4.4, 2.1);
  if (z.cle === "reunion") tableauEchanges = ecranMural(z, "y0", z.x + z.l / 2, 1.95, 3.2, 1.7);
  if (z.cle === "macro") {
    [["PARIS", "Europe/Paris"], ["LONDRES", "Europe/London"], ["NEW YORK", "America/New_York"], ["TOKYO", "Asia/Tokyo"]]
      .forEach(([v, tz], k) => horlogeMurale(z, "y0", z.x + 3.5 + k * 3, 2.4, v, tz));
  }
  if (z.cle === "directeur") {
    cheminee(z, "x0", z.y + 4.6);
    tableauMur(z, "x0", z.y + 4.6, 2.25, 1.3, 0.8, 1);
  }
}

// une pièce : parquet, murs, plafond (vu seulement de l'intérieur), lustres, habillage
function piece(z) {
  const p = { z, mur: std({ map: texMur(z.cle), roughness: 0.85 }), lampe: new THREE.MeshBasicMaterial({ color: 0xffd9a0, toneMapped: false }), lampes: new Set(), halos: new Set() };
  pieces[z.cle] = p;
  const c = P3(z.x + z.l / 2, z.y + z.p / 2), li = z.l - 2 * EP, pi = z.p - 2 * EP;
  const dalle = (mat, h, dessous, pas) => {
    const g = new THREE.PlaneGeometry(li, pi), pos = g.attributes.position, uv = g.attributes.uv;
    for (let i = 0; i < pos.count; i++) uv.setXY(i, (pos.getX(i) + c.x) / pas, (pos.getY(i) - c.z) / pas);
    const m = new THREE.Mesh(g, mat); m.rotation.x = dessous ? Math.PI / 2 : -Math.PI / 2; m.position.set(c.x, h, c.z);
    return m;
  };
  const sol = dalle(M.parquet, 0.004, false, 1.6); sol.receiveShadow = true; scene.add(sol);
  sol.userData = { zone: z.cle, sol: true }; sols.push(sol);   // toucher le sol : entrer, ou avancer jusque-là
  murs(z, p);
  p.plafond = dalle(z.cle === "directeur" ? M.plafondNoyer : M.plafond, z.h - 0.002, true, 2);
  p.plafond.visible = false; ombre(p.plafond); scene.add(p.plafond);
  const n = z.l > 12 ? 2 : 1;
  for (let k = 0; k < n; k++) {
    const pos = P3(z.x + z.l * (k + 0.5) / n, z.y + z.p / 2, z.h - 0.75);
    lustre(pos, 0.5, 0.75);
    const l = new THREE.PointLight(0xffc98a, z.cle === "directeur" ? 10 : 8, 11, 1.6); l.position.copy(pos).add(new THREE.Vector3(0, -0.15, 0)); scene.add(l);
  }
  habillage(z);
}

// tapis des allées entre les bureaux
function allees() {
  const chemin = (x0, y0, x1, y1, larg) => {
    const long = Math.hypot(x1 - x0, y1 - y0), g = new THREE.PlaneGeometry(long, larg), uv = g.attributes.uv;
    for (let i = 0; i < uv.count; i++) uv.setX(i, uv.getX(i) * long / 2);
    const m = new THREE.Mesh(g, M.couloir); m.rotation.x = -Math.PI / 2; if (x0 === x1) m.rotation.z = Math.PI / 2;
    m.position.copy(P3((x0 + x1) / 2, (y0 + y1) / 2, 0.006)); m.receiveShadow = true; scene.add(m);
  };
  chemin(0.3, 15, 18.9, 15, 2.2); chemin(29.1, 15, 47.7, 15, 2.2);
  for (const x of [18, 30]) { chemin(x, 0.4, x, 13.9, 1.2); chemin(x, 16.1, x, 29.6, 1.2); }
  for (const y of [10, 20]) chemin(18.6, y, 29.4, y, 1.2);
}

// ------------------------------------------------------------------ pièces : tapis de velours (cliquables) + mobilier
function tapis(z) {
  const [fond, motif] = TAPIS[z.cle] || ["#111", "#aa8"];
  const tex = toile(1024, Math.round(1024 * z.p / z.l), (c, w, h) => {
    c.fillStyle = fond; c.fillRect(0, 0, w, h);
    const r = hasard(z.cle.length * 31);
    for (let k = 0; k < 3000; k++) { c.fillStyle = `rgba(255,255,255,${r() * 0.03})`; c.fillRect(r() * w, r() * h, 2, 2); }
    // bordure à motifs
    c.strokeStyle = motif; c.lineWidth = 10; c.strokeRect(22, 22, w - 44, h - 44);
    c.lineWidth = 3; c.strokeRect(48, 48, w - 96, h - 96);
    c.fillStyle = motif; c.globalAlpha = 0.55;
    const pas = 34;
    for (let x = 60; x < w - 60; x += pas) for (const y of [35, h - 35]) { c.beginPath(); c.moveTo(x, y - 7); c.lineTo(x + 7, y); c.lineTo(x, y + 7); c.lineTo(x - 7, y); c.fill(); }
    for (let y = 60; y < h - 60; y += pas) for (const x of [35, w - 35]) { c.beginPath(); c.moveTo(x, y - 7); c.lineTo(x + 7, y); c.lineTo(x, y + 7); c.lineTo(x - 7, y); c.fill(); }
    // médaillon central
    c.globalAlpha = 0.35; c.lineWidth = 3;
    const cx = w / 2, cy = h / 2, R = Math.min(w, h) * 0.22;
    for (let k = 0; k < 16; k++) { c.save(); c.translate(cx, cy); c.rotate(k * Math.PI / 8); c.beginPath(); c.ellipse(R * 0.55, 0, R * 0.5, R * 0.14, 0, 0, 7); c.stroke(); c.restore(); }
    c.beginPath(); c.arc(cx, cy, R, 0, 7); c.stroke(); c.beginPath(); c.arc(cx, cy, R * 0.25, 0, 7); c.fill();
    c.globalAlpha = 1;
  });
  const m = phy({ map: tex, roughness: 0.95, sheen: 1, sheenRoughness: 0.5, sheenColor: new THREE.Color(motif).multiplyScalar(0.35), emissive: 0x000000 });
  const t = new THREE.Mesh(new THREE.BoxGeometry(z.l - 2, 0.025, z.p - 2), m);
  t.position.copy(P3(z.x + z.l / 2, z.y + z.p / 2, 0.013)); t.receiveShadow = true;
  t.userData = { zone: z.cle };
  scene.add(t); cliquables.push(t);
  const d = document.createElement("div");
  d.className = "nom-zone3d"; d.textContent = z.nom; d.tabIndex = 0;
  d.addEventListener("click", () => allerPiece(z.cle));
  const o = new CSS2DObject(d); o.position.copy(P3(z.x + z.l / 2, z.y + z.p - 0.2, 0.05)); o.center.set(0.5, -0.4);
  scene.add(o);
  if (pieces[z.cle]) pieces[z.cle].nomObj = o;
}

function plante(x, y, grande = 1) {
  const g = new THREE.Group(); g.position.copy(P3(x, y));
  g.add(cyl(0.34, 0.26, 0.62, M.pot, 0, 0.31, 0, 24));
  g.add(cyl(0.36, 0.36, 0.05, M.or, 0, 0.62, 0, 24));
  g.add(cyl(0.31, 0.31, 0.02, M.terre, 0, 0.6, 0, 16));
  g.add(cyl(0.03, 0.045, 1.4 * grande, M.boisMat, 0, 0.6 + 0.7 * grande, 0, 6));
  const r = hasard(Math.round(x * 13 + y * 7)), feuille = new THREE.PlaneGeometry(0.28, 0.5);
  for (let k = 0; k < 34; k++) {
    const f = new THREE.Mesh(feuille, M.feuille), h = 0.9 + r() * 1.3 * grande, a = r() * Math.PI * 2;
    f.position.set(Math.cos(a) * (0.12 + r() * 0.3), h, Math.sin(a) * (0.12 + r() * 0.3));
    f.rotation.set(-0.6 - r() * 0.6, a, (r() - 0.5) * 0.6); f.castShadow = true; g.add(f);
  }
  scene.add(g);
}

function fauteuil(x, z, angle, y0 = 0, m = M.cuir) {
  const g = new THREE.Group(); g.position.set(x, y0, z); g.rotation.y = angle;
  g.add(arrondi(0.58, 0.12, 0.56, 0.05, m, 0, 0.49, 0));
  g.add(arrondi(0.58, 0.72, 0.12, 0.05, m, 0, 0.9, -0.27));
  for (const s of [-1, 1]) {
    g.add(arrondi(0.07, 0.05, 0.42, 0.02, M.cuirNoir, s * 0.32, 0.72, -0.02));
    g.add(cyl(0.015, 0.015, 0.2, M.chrome, s * 0.32, 0.6, -0.05, 6));
  }
  g.add(cyl(0.035, 0.035, 0.38, M.chrome, 0, 0.27, 0, 10));
  for (let k = 0; k < 5; k++) {
    const a = k * Math.PI * 2 / 5, b = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.03, 0.32), M.chrome);
    b.position.set(Math.sin(a) * 0.16, 0.06, Math.cos(a) * 0.16); b.rotation.y = a; g.add(b);
    g.add(cyl(0.025, 0.025, 0.04, M.noir, Math.sin(a) * 0.31, 0.025, Math.cos(a) * 0.31, 8));
  }
  scene.add(g);
  return g;
}

function bibliothequeMeuble(cx, cz, angle, largeur, graine, H = 2.9) {
  const g = new THREE.Group(); g.position.set(cx, 0, cz); g.rotation.y = angle;
  const etages = 6;
  g.add(boite(largeur, H, 0.08, M.boisMat, 0, H / 2, -0.22));
  for (const s of [-1, 1]) g.add(boite(0.08, H, 0.5, M.bois, s * largeur / 2, H / 2, 0));
  g.add(arrondi(largeur + 0.3, 0.16, 0.62, 0.03, M.bois, 0, H + 0.05, 0.02));
  g.add(boite(largeur + 0.3, 0.04, 0.05, M.or, 0, H - 0.05, 0.3, false));
  for (let e = 0; e <= etages; e++) g.add(boite(largeur, 0.04, 0.46, M.bois, 0, 0.1 + e * (H - 0.3) / etages, 0));
  const n = Math.floor(largeur / 0.085) * etages, livres = new THREE.InstancedMesh(new THREE.BoxGeometry(0.075, 1, 0.3), std({ map: T.livre, roughness: 0.65 }), n);
  const r = hasard(graine), m4 = new THREE.Matrix4(), col = new THREE.Color(), q = new THREE.Quaternion(); let i = 0;
  const teintes = [0x6a1c16, 0x1f4a33, 0x1c2c55, 0x7a5a1e, 0x47203c, 0x2d2a26, 0x8a3a1a];
  for (let e = 0; e < etages; e++) {
    let x = -largeur / 2 + 0.08;
    while (x < largeur / 2 - 0.1 && i < n) {
      const hgt = 0.3 + r() * 0.13, pench = r() < 0.06 ? 0.25 : 0;
      q.setFromEuler(new THREE.Euler(0, 0, pench));
      m4.compose(new THREE.Vector3(x, 0.12 + e * (H - 0.3) / etages + hgt / 2, 0.02), q, new THREE.Vector3(0.8 + r() * 0.6, hgt, 1));
      livres.setMatrixAt(i, m4); livres.setColorAt(i++, col.setHex(teintes[Math.floor(r() * teintes.length)]));
      x += 0.075 + r() * 0.03 + (r() < 0.05 ? 0.25 : 0);
    }
  }
  livres.count = i; livres.castShadow = true; livres.receiveShadow = true; g.add(livres);
  scene.add(g);
  return g;
}

function lampeBanquier(g, x, y, z) {
  g.add(cyl(0.11, 0.13, 0.03, M.laiton, x, y + 0.015, z, 24));
  g.add(cyl(0.012, 0.012, 0.32, M.laiton, x, y + 0.18, z, 8));
  const abat = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.36, 24, 1, true, 0, Math.PI), M.verreVert);
  abat.rotation.z = Math.PI / 2; abat.position.set(x, y + 0.36, z); abat.castShadow = true; g.add(abat);
  const ampoule = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.28, 10), M.ampoule); ampoule.rotation.z = Math.PI / 2; ampoule.position.set(x, y + 0.33, z); g.add(ampoule);
  const f = new THREE.Mesh(new THREE.PlaneGeometry(1.3, 1.3), M.halo(0xffc47a, 0.5)); f.rotation.x = -Math.PI / 2; f.position.set(x, y + 0.006, z + 0.12); g.add(f);
}

function decor(z) {
  const c = P3(z.x + z.l / 2, z.y + z.p / 2);
  if (z.cle === "bibliotheque") {
    // rayonnages contre le mur de l'entrée, de part et d'autre de l'ouverture
    const yb = z.y + EP + 0.27;
    for (const [dx, k] of [[1.95, 0], [5.1, 1], [10.9, 2], [14.05, 3]]) bibliothequeMeuble(P3(z.x + dx, 0).x, P3(0, yb).z, 0, 3.05, 11 + k);
    // échelle de bibliothèque
    const e = new THREE.Group(); e.position.copy(P3(z.x + 3.5, yb + 0.6)); e.rotation.x = -0.22;
    for (const s of [-0.25, 0.25]) e.add(boite(0.05, 3.0, 0.06, M.bois, s, 1.45, 0));
    for (let k = 0; k < 8; k++) e.add(boite(0.5, 0.035, 0.05, M.laiton, 0, 0.3 + k * 0.35, 0));
    scene.add(e);
    // table de lecture, lampes de banquier, fauteuils club
    const t = P3(z.x + 3.8, z.y + 9.4);
    const table = new THREE.Group(); table.position.copy(t);
    table.add(arrondi(3.6, 0.08, 1.5, 0.03, M.bois, 0, 0.78, 0));
    for (const sx of [-1.6, 1.6]) for (const sz of [-0.6, 0.6]) table.add(cyl(0.05, 0.04, 0.74, M.bois, sx, 0.37, sz, 10));
    lampeBanquier(table, -0.8, 0.82, -0.3); lampeBanquier(table, 0.8, 0.82, -0.3);
    table.add(boite(0.3, 0.04, 0.22, M.papier, 0.2, 0.84, 0.25));
    scene.add(table);
    for (const dx of [-1, 1]) fauteuil(t.x + dx * 0.9, t.z + 1.25, Math.PI);
  } else if (z.cle === "reunion") {
    const t = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 0.09, 64), M.bois);
    t.scale.set(2.7, 1, 1.05); t.position.set(c.x, 0.78, c.z); ombre(t); scene.add(t);
    const bord = new THREE.Mesh(new THREE.TorusGeometry(1, 0.025, 6, 96), M.or); bord.scale.set(2.7, 1.05, 1); bord.rotation.x = Math.PI / 2; bord.position.set(c.x, 0.82, c.z); scene.add(bord);
    for (const dx of [-1.2, 1.2]) scene.add(cyl(0.18, 0.4, 0.74, M.bois, c.x + dx, 0.37, c.z, 24));
    for (let k = 0; k < 10; k++) {
      const a = (k / 10) * Math.PI * 2, x = c.x + Math.cos(a) * 3.35, zz = c.z + Math.sin(a) * 1.6;
      fauteuil(x, zz, Math.atan2(c.x - x, c.z - zz));
      const bloc = boite(0.21, 0.015, 0.29, M.papier, c.x + Math.cos(a) * 2.35, 0.83, c.z + Math.sin(a) * 1.0, false);
      bloc.rotation.y = -a; scene.add(bloc);
    }
    for (const dx of [-0.7, 0.7]) {
      scene.add(cyl(0.07, 0.09, 0.28, M.verre, c.x + dx, 0.97, c.z, 16));
      scene.add(cyl(0.04, 0.04, 0.09, M.verre, c.x + dx + 0.18, 0.87, c.z + 0.1, 12));
    }
  } else if (z.cle === "labo") {
    const tableau = new THREE.Group(); tableau.position.copy(P3(z.x + EP + 0.3, z.y + z.p / 2)); tableau.rotation.y = Math.PI / 2;
    tableau.add(boite(4.2, 2.1, 0.03, phy({ color: 0xdfe8f0, roughness: 0.05, transparent: true, opacity: 0.25, clearcoat: 1 }), 0, 1.75, 0, false));
    for (const s of [-2.15, 2.15]) tableau.add(cyl(0.03, 0.03, 2.9, M.chrome, s, 1.45, 0, 10));
    tableau.add(boite(4.2, 0.03, 0.08, M.chrome, 0, 0.7, 0.04));
    scene.add(tableau);
    plante(z.x + z.l - 0.8, z.y + z.p - 0.8, 1.2);
  } else if (z.cle === "donnees") {
    const face = std({ map: T.led, emissive: 0xffffff, emissiveMap: T.led, emissiveIntensity: 1.2, roughness: 0.25 });
    for (let k = 0; k < 3; k++) {   // baies de serveurs le long du mur du fond, face à la pièce
      const g = new THREE.Group(); g.position.copy(P3(z.x + z.l - EP - 0.65, z.y + 3.6 + k * 2.6)); g.rotation.y = -Math.PI / 2;
      g.add(ombre(poser(new THREE.Mesh(new RoundedBoxGeometry(1.05, 2.3, 1.2, 2, 0.03), M.noir), { position: new THREE.Vector3(0, 1.15, 0) })));
      g.add(poser(new THREE.Mesh(new THREE.PlaneGeometry(0.9, 2.1), face), { position: new THREE.Vector3(0, 1.15, 0.61) }));
      const h = new THREE.Mesh(new THREE.PlaneGeometry(2, 1.6), M.halo(0x3d7bd6, 0.18)); h.rotation.x = -Math.PI / 2; h.position.set(0, 0.03, 1.3); g.add(h);
      scene.add(g);
    }
    const froid = new THREE.PointLight(0x4d86ff, 8, 7, 2); froid.position.copy(P3(z.x + z.l / 2, z.y + z.p / 2, 2.4)); scene.add(froid);
  } else if (z.cle === "risque") {
    const b = P3(z.x + z.l - 1.2, z.y + 1.1);
    scene.add(arrondi(1.2, 1.9, 0.95, 0.05, std({ color: 0x2a2e33, metalness: 0.9, roughness: 0.3 }), b.x, 0.95, b.z));
    const roue = new THREE.Mesh(new THREE.TorusGeometry(0.2, 0.03, 10, 32), M.laiton); roue.position.set(b.x, 1.15, b.z + 0.49); scene.add(roue);
    for (let k = 0; k < 4; k++) { const r = boite(0.02, 0.4, 0.02, M.laiton, b.x, 1.15, b.z + 0.5, false); r.rotation.z = k * Math.PI / 4; scene.add(r); }
    pendule(P3(z.x + 0.9, z.y + 1));
  } else if (z.cle === "directeur") {
    // estrade de marbre bordée d'or, médaillon MGC, salon, globe, bibliothèque
    scene.add(arrondi(z.l - 1.6, 0.3, z.p - 1.6, 0.04, phy({ color: 0x1a1612, roughness: 0.45, specularIntensity: 0.5, clearcoat: 0.4, clearcoatRoughness: 0.3 }), c.x, 0.15, c.z));
    scene.add(boite(z.l - 1.5, 0.035, 0.06, M.or, c.x, 0.31, c.z + (z.p - 1.6) / 2));
    scene.add(boite(z.l - 1.5, 0.035, 0.06, M.or, c.x, 0.31, c.z - (z.p - 1.6) / 2));
    scene.add(boite(0.06, 0.035, z.p - 1.5, M.or, c.x + (z.l - 1.6) / 2, 0.31, c.z));
    scene.add(boite(0.06, 0.035, z.p - 1.5, M.or, c.x - (z.l - 1.6) / 2, 0.31, c.z));
    const embleme = toile(512, 512, (cx, w, h) => {
      cx.clearRect(0, 0, w, h); cx.strokeStyle = "#e0b862"; cx.fillStyle = "#e0b862"; cx.lineWidth = 10;
      cx.beginPath(); cx.arc(w / 2, h / 2, w / 2 - 12, 0, 7); cx.stroke(); cx.lineWidth = 3; cx.beginPath(); cx.arc(w / 2, h / 2, w / 2 - 34, 0, 7); cx.stroke();
      cx.font = "700 150px Georgia, serif"; cx.textAlign = "center"; cx.textBaseline = "middle"; cx.fillText("MGC", w / 2, h / 2 + 8);
    });
    const med = new THREE.Mesh(new THREE.PlaneGeometry(1.6, 1.6), std({ map: embleme, transparent: true, metalness: 1, roughness: 0.25, color: 0xffffff }));
    med.rotation.x = -Math.PI / 2; med.position.set(c.x, 0.305, c.z + 2.6); scene.add(med);
    bibliothequeMeuble(c.x, c.z - z.p / 2 + EP + 0.27, 0, 4.2, 99, 2.8);
    // globe terrestre ancien
    const gl = P3(z.x + 1.6, z.y + 2.2, 0.3);
    scene.add(cyl(0.05, 0.25, 0.08, M.bois, gl.x, gl.y + 0.04, gl.z, 16), cyl(0.03, 0.03, 0.7, M.bois, gl.x, gl.y + 0.4, gl.z, 8));
    const globe = new THREE.Mesh(new THREE.SphereGeometry(0.32, 32, 20), std({ map: T.globe, roughness: 0.45 })); globe.position.set(gl.x, gl.y + 1.05, gl.z); globe.rotation.z = 0.41; ombre(globe); scene.add(globe);
    const meridien = new THREE.Mesh(new THREE.TorusGeometry(0.36, 0.012, 6, 48), M.laiton); meridien.position.copy(globe.position); scene.add(meridien);
    // canapé Chesterfield et table basse
    const ca = P3(z.x + 8.3, z.y + 2.4, 0.3);
    const canape = new THREE.Group(); canape.position.copy(ca); canape.rotation.y = -Math.PI / 2;
    canape.add(arrondi(2, 0.4, 0.85, 0.12, M.cuir, 0, 0.32, 0));
    canape.add(arrondi(2, 0.55, 0.22, 0.1, M.cuir, 0, 0.72, -0.35));
    for (const s of [-1, 1]) canape.add(arrondi(0.24, 0.6, 0.85, 0.1, M.cuir, s * 1.05, 0.5, 0));
    scene.add(canape);
    scene.add(arrondi(0.6, 0.06, 1.1, 0.02, M.bois, ca.x - 1.0, ca.y + 0.42, ca.z));
    scene.add(boite(0.5, 0.36, 1.0, M.boisMat, ca.x - 1.0, ca.y + 0.2, ca.z));
    for (const dx of [-0.7, 0.7]) fauteuil(c.x + dx, c.z - 1.35, 0, 0.3, M.cuirNoir);   // invités, en face du directeur
  }
}

// pendule de parquet : elle donne l'heure réelle
function pendule(p) {
  const g = new THREE.Group(); g.position.copy(p);
  g.add(arrondi(0.62, 2.3, 0.4, 0.04, M.bois, 0, 1.15, 0));
  g.add(arrondi(0.72, 0.18, 0.48, 0.04, M.bois, 0, 2.35, 0));
  g.add(boite(0.4, 0.9, 0.02, M.verre, 0, 0.95, 0.21, false));
  g.add(cyl(0.012, 0.012, 0.55, M.laiton, 0, 1.0, 0.18, 6));
  g.add(cyl(0.09, 0.09, 0.02, M.laiton, 0, 0.72, 0.19, 20)); g.children[g.children.length - 1].rotation.x = Math.PI / 2;
  const c = document.createElement("canvas"); c.width = c.height = 256;
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
  const cadran = new THREE.Mesh(new THREE.CircleGeometry(0.24, 40), new THREE.MeshBasicMaterial({ map: tex, color: 0xd8cfb8 }));
  cadran.position.set(0, 1.95, 0.205); g.add(cadran);
  const cercle = new THREE.Mesh(new THREE.TorusGeometry(0.245, 0.018, 8, 40), M.laiton); cercle.position.copy(cadran.position); g.add(cercle);
  g.rotation.y = Math.PI / 4;
  scene.add(g);
  horloges.push({ c, tex, tz: null, minute: -1 });
}
function heureDe(tz) {
  if (!tz) { const d = new Date(); return [d.getHours(), d.getMinutes()]; }
  const p = new Intl.DateTimeFormat("fr-FR", { timeZone: tz, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date());
  return [+p.find((x) => x.type === "hour").value, +p.find((x) => x.type === "minute").value];
}
function dessinerHorloges() {
  for (const o of horloges) {
    const [hh, mm] = heureDe(o.tz), m = hh * 60 + mm;
    if (m === o.minute) continue;
    o.minute = m;
    const x = o.c.getContext("2d"), w = 256, r = 120;
    x.setTransform(1, 0, 0, 1, 0, 0);
    x.fillStyle = "#f3ead2"; x.fillRect(0, 0, w, w);
    x.translate(w / 2, w / 2);
    x.fillStyle = "#2a2118"; x.font = "600 30px Georgia, serif"; x.textAlign = "center"; x.textBaseline = "middle";
    ["XII", "III", "VI", "IX"].forEach((t, k) => { const a = k * Math.PI / 2; x.fillText(t, Math.sin(a) * (r - 30), -Math.cos(a) * (r - 30)); });
    for (let k = 0; k < 60; k++) { const a = k * Math.PI / 30, l = k % 5 ? 6 : 14; x.fillRect(Math.sin(a) * (r - 6) - 1, -Math.cos(a) * (r - 6) - 1, 2, 2); if (!(k % 5)) { x.beginPath(); x.moveTo(Math.sin(a) * (r - 4), -Math.cos(a) * (r - 4)); x.lineTo(Math.sin(a) * (r - 4 - l), -Math.cos(a) * (r - 4 - l)); x.lineWidth = 3; x.strokeStyle = "#2a2118"; x.stroke(); } }
    const aiguille = (a, l, e) => { x.beginPath(); x.moveTo(0, 0); x.lineTo(Math.sin(a) * l, -Math.cos(a) * l); x.lineWidth = e; x.lineCap = "round"; x.strokeStyle = "#1a140e"; x.stroke(); };
    aiguille(((hh % 12) + mm / 60) * Math.PI / 6, r * 0.5, 7);
    aiguille(mm * Math.PI / 30, r * 0.78, 4);
    x.beginPath(); x.arc(0, 0, 7, 0, 7); x.fillStyle = "#b8892f"; x.fill();
    x.setTransform(1, 0, 0, 1, 0, 0);
    o.tex.needsUpdate = true;
  }
}

// ------------------------------------------------------------------ un poste : bureau de direction, écrans (contenu réel), agent
function ecranTexture(w = 512, h = 288) {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  return { c, t };
}
// 2e écran : la fiche réelle de l'agent (numéro, nom, rôle), dessinée une fois
function ficheAgent(p) {
  return toile(512, 288, (c, w, h) => {
    const g = c.createLinearGradient(0, 0, 0, h); g.addColorStop(0, "#0b1426"); g.addColorStop(1, "#060a14"); c.fillStyle = g; c.fillRect(0, 0, w, h);
    c.strokeStyle = "rgba(212,166,74,.6)"; c.lineWidth = 2; c.strokeRect(10, 10, w - 20, h - 20);
    c.fillStyle = "#d4a64a"; c.font = "700 64px Georgia, serif"; c.fillText(String(p.agent), 28, 92);
    c.fillStyle = "#ece6d6"; c.font = "600 28px system-ui"; c.fillText(p.court, 28 + (p.agent > 9 ? 80 : 46), 88);
    c.fillStyle = "#9fb0c8"; c.font = "22px system-ui";
    const mots = String(p.nom).split(" "); let ligne = "", yy = 148;
    for (const mot of mots) { if (c.measureText(ligne + mot).width > w - 60) { c.fillText(ligne, 28, yy); ligne = ""; yy += 30; } ligne += mot + " "; }
    c.fillText(ligne, 28, yy);
    c.fillStyle = "rgba(212,166,74,.8)"; c.font = "600 18px system-ui"; c.fillText("UNIVERSITÉ MGC", 28, h - 30);
  });
}

const VESTES = [0x1b2438, 0x2a2d33, 0x3a1f26, 0x23302a, 0x3b3226, 0x1e1e24, 0x2b3346];
const PEAUX = [0xe2c4a6, 0xc69a74, 0x9a6a46, 0x6e4a32, 0xd8b28c, 0xb4835e];
const CHEVEUX = [0x1a1410, 0x2c1e14, 0x4a3220, 0x0e0e10, 0x6a5a48, 0x8a6a3c];
function personnage(n) {
  const r = hasard(n * 977);
  const veste = std({ color: VESTES[Math.floor(r() * VESTES.length)], roughness: 0.72 });
  const peau = std({ color: PEAUX[Math.floor(r() * PEAUX.length)], roughness: 0.55 });
  const cheveux = std({ color: CHEVEUX[Math.floor(r() * CHEVEUX.length)], roughness: 0.6 });
  const cravate = std({ color: [0x6a1a1a, 0x1a2a5a, 0x8a6a1a, 0x2a4a2a][Math.floor(r() * 4)], roughness: 0.5 });
  const g = new THREE.Group(), V = (x, y, z) => new THREE.Vector3(x, y, z);
  // jambes assises
  for (const s of [-1, 1]) {
    g.add(membre(V(s * 0.11, 0.57, 0.02), V(s * 0.12, 0.56, -0.36), 0.075, M.pantalon));
    g.add(membre(V(s * 0.12, 0.54, -0.4), V(s * 0.12, 0.1, -0.44), 0.06, M.pantalon));
    g.add(arrondi(0.11, 0.08, 0.27, 0.035, M.chaussure, s * 0.12, 0.04, -0.5));
  }
  // haut du corps (bouge seulement quand l'agent travaille vraiment)
  const haut = new THREE.Group(); g.add(haut);
  const profil = [[0.001, 0.52], [0.16, 0.54], [0.17, 0.62], [0.165, 0.75], [0.19, 0.92], [0.22, 1.02], [0.2, 1.08], [0.09, 1.12], [0.001, 1.13]].map(([x, y]) => new THREE.Vector2(x, y));
  const tronc = new THREE.Mesh(new THREE.LatheGeometry(profil, 28), veste); tronc.scale.z = 0.68; tronc.rotation.x = -0.06; ombre(tronc); haut.add(tronc);
  const plastron = new THREE.Mesh(new THREE.CircleGeometry(0.075, 3), M.chemise); plastron.position.set(0, 1.05, -0.122); plastron.rotation.set(Math.PI, 0, Math.PI / 2 * 0); haut.add(plastron);
  const cr = boite(0.035, 0.2, 0.01, cravate, 0, 0.98, -0.125, false); haut.add(cr);
  haut.add(cyl(0.065, 0.07, 0.06, M.chemise, 0, 1.13, 0, 16));
  haut.add(cyl(0.05, 0.055, 0.1, peau, 0, 1.19, 0, 12));
  const tete = new THREE.Mesh(new THREE.SphereGeometry(0.115, 28, 20), peau); tete.scale.set(0.9, 1.12, 1); tete.position.set(0, 1.35, -0.01); ombre(tete); haut.add(tete);
  for (const s of [-1, 1]) haut.add(poser(new THREE.Mesh(new THREE.SphereGeometry(0.025, 8, 6), peau), { position: V(s * 0.1, 1.35, 0) }));
  const coupe = new THREE.Mesh(new THREE.SphereGeometry(0.122, 28, 14, 0, Math.PI * 2, 0, Math.PI * (0.45 + r() * 0.12)), cheveux);
  coupe.scale.set(0.93, 1.1, 1.04); coupe.position.set(0, 1.365, 0.012); coupe.rotation.x = 0.35; ombre(coupe); haut.add(coupe);
  const bras = [];
  for (const s of [-1, 1]) {
    const epaule = V(s * 0.21, 1.04, 0), coude = V(s * 0.25, 0.83, -0.13), main = V(s * 0.13, 0.84, -0.44);
    haut.add(membre(epaule, coude, 0.06, veste));
    const pivot = new THREE.Group(); pivot.position.copy(coude); haut.add(pivot);
    pivot.add(membre(V(0, 0, 0), main.clone().sub(coude), 0.05, veste));
    const poignet = main.clone().sub(coude);
    pivot.add(poser(new THREE.Mesh(new THREE.SphereGeometry(0.045, 12, 8), peau), { position: poignet.clone().add(V(0, -0.005, -0.03)), scale: new THREE.Vector3(1, 0.6, 1.3) }));
    pivot.userData.base = 0; bras.push(pivot);
  }
  return { g, haut, bras };
}

function poste(p) {
  const dir = p.agent === 14, l = dir ? 3.2 : 2.2, pr = dir ? 1.3 : 1.05, y0 = dir ? 0.3 : 0;
  const g = new THREE.Group(); g.position.copy(P3(p.x, p.y, y0)); g.userData = { agent: p.agent };
  // bureau en noyer verni : plateau, caissons à tiroirs (poignées de laiton), panneau de fond, sous-main de cuir
  g.add(arrondi(l, 0.06, pr, 0.025, M.bois, 0, 0.76, 0));
  g.add(boite(l - 0.04, 0.012, 0.03, M.or, 0, 0.73, pr / 2 - 0.01, false));
  for (const s of [-1, 1]) {
    g.add(arrondi(0.5, 0.72, pr - 0.08, 0.02, M.bois, s * (l / 2 - 0.29), 0.37, 0));
    for (let k = 0; k < 3; k++) {
      g.add(boite(0.44, 0.005, 0.005, M.noir, s * (l / 2 - 0.29), 0.2 + k * 0.22, pr / 2 - 0.035, false));
      g.add(boite(0.12, 0.018, 0.02, M.laiton, s * (l / 2 - 0.29), 0.3 + k * 0.22 - 0.1 + 0.1, pr / 2 - 0.02, false));
    }
  }
  g.add(boite(l - 1.1, 0.5, 0.04, M.boisMat, 0, 0.45, -pr / 2 + 0.06));
  g.add(arrondi(dir ? 1.1 : 0.8, 0.008, 0.48, 0.004, M.sousMain, 0, 0.794, 0.12, false));
  // écrans : le principal montre le dernier document réel de l'agent (ou sa mission en cours)
  const e = ecranTexture(), larg = dir ? 0.78 : 0.62, haut = larg * 0.5625;
  const ecran = (x, angle, map) => {
    const m = new THREE.Group(); m.position.set(x, 0, -pr / 2 + 0.28); m.rotation.y = angle;
    m.add(arrondi(larg + 0.03, haut + 0.03, 0.025, 0.008, M.noir, 0, 1.16, 0));
    const v = new THREE.Mesh(new THREE.PlaneGeometry(larg, haut), new THREE.MeshBasicMaterial({ map, toneMapped: false }));
    v.position.set(0, 1.16, 0.0135); m.add(v);
    m.add(cyl(0.018, 0.022, 0.32, M.chrome, 0, 0.94, -0.03, 10));
    m.add(arrondi(0.22, 0.012, 0.16, 0.005, M.chrome, 0, 0.8, -0.03));
    g.add(m);
    return v;
  };
  const vitre = ecran(dir ? 0 : -larg / 2 - 0.02, dir ? 0 : 0.12, e.t);
  if (dir) { ecran(-larg - 0.08, 0.32, ficheAgent(p)); ecran(larg + 0.08, -0.32, ficheAgent(p)); }
  else ecran(larg / 2 + 0.02, -0.12, ficheAgent(p));
  const lueur = new THREE.Mesh(new THREE.PlaneGeometry(1.4, 0.9), M.halo(0x6aa0ff, 0.12)); lueur.rotation.x = -Math.PI / 2; lueur.position.set(0, 0.795, -0.05); g.add(lueur);
  // clavier, souris, papiers, tasse
  const clav = new THREE.Mesh(new RoundedBoxGeometry(0.44, 0.018, 0.14, 2, 0.006), [M.noir, M.noir, M.clavier, M.noir, M.noir, M.noir]);
  clav.position.set(0, 0.805, 0.1); ombre(clav, false); g.add(clav);
  const souris = new THREE.Mesh(new THREE.CapsuleGeometry(0.025, 0.04, 4, 10), M.noir); souris.rotation.x = Math.PI / 2; souris.scale.y = 0.6; souris.position.set(0.32, 0.805, 0.12); g.add(souris);
  const rr = hasard(p.agent * 41);
  for (let k = 0; k < 2; k++) { const f = boite(0.21, 0.004, 0.29, M.papier, -l / 2 + 0.45 + k * 0.03, 0.795 + k * 0.004, 0.15 + k * 0.02, false); f.rotation.y = (rr() - 0.5) * 0.5; g.add(f); }
  const tasse = cyl(0.04, 0.035, 0.09, M.porcelaine, l / 2 - 0.5, 0.835, 0.2, 18); g.add(tasse);
  const anse = new THREE.Mesh(new THREE.TorusGeometry(0.025, 0.007, 6, 12), M.porcelaine); anse.position.set(l / 2 - 0.45, 0.84, 0.2); g.add(anse);
  lampeBanquier(g, l / 2 - 0.35, 0.79, -pr / 2 + 0.3);
  scene.add(g);
  // fauteuil + agent devant le bureau, tourné vers les écrans
  const assise = P3(p.x, p.y + pr / 2 + 0.5, y0);
  fauteuil(assise.x, assise.z, Math.PI, y0, dir ? M.cuir : (p.agent % 2 ? M.cuirNoir : M.cuir));
  const pers = personnage(p.agent), agent = pers.g; agent.position.copy(assise); scene.add(agent);
  // anneau lumineux au sol : la couleur de son état réel
  const anneau = new THREE.Group();
  anneau.add(new THREE.Mesh(new THREE.RingGeometry(0.62, 0.68, 64), new THREE.MeshBasicMaterial({ color: COULEURS.disponible, toneMapped: false, transparent: true, opacity: 0.95 })));
  anneau.add(new THREE.Mesh(new THREE.PlaneGeometry(1.9, 1.9), M.halo(0xffffff, 0.22)));
  anneau.children.forEach((m) => { m.rotation.x = -Math.PI / 2; });
  anneau.position.copy(assise).add(new THREE.Vector3(0, 0.035, 0)); scene.add(anneau);
  tetes[p.agent] = assise.clone().add(new THREE.Vector3(0, 1.5, 0));
  // étiquette (texte net, toujours lisible)
  const d = document.createElement("div");
  d.className = "tag3d"; d.innerHTML = `<i></i><b>${p.agent} · ${p.court}</b><small></small>`;
  d.addEventListener("click", () => window.voirAgent(p.agent));
  const tag = new CSS2DObject(d); tag.position.copy(P3(p.x, p.y, y0 + 2.2)); scene.add(tag);
  for (const o of [g, agent]) o.traverse((m) => { if (m.isMesh) { m.userData.agent = p.agent; cliquables.push(m); } });
  postes[p.agent] = { g, agent, corps: pers.haut, bras: pers.bras, anneau, vitre, e, tag: d, tagObj: tag, zone: p.zone, cle: "", statut: "", y0, travail: false };
}

function dessinerEcran(ps, a) {
  const d = a.dernier_document, m = a.mission;
  const cle = JSON.stringify([a.statut, m && m.etape, d && d.id, d && d.statut]);
  if (cle === ps.cle) return;
  ps.cle = cle;
  const c = ps.e.c.getContext("2d"), w = ps.e.c.width, h = ps.e.c.height;
  const fond = { travail: ["#123a6a", "#0a1f3c"], erreur: ["#4a1414", "#240808"], attente: ["#3c2a0c", "#1e1406"], construction: ["#030304", "#020203"] }[a.statut] || ["#0e1a30", "#070d18"];
  const g = c.createLinearGradient(0, 0, 0, h); g.addColorStop(0, fond[0]); g.addColorStop(1, fond[1]); c.fillStyle = g; c.fillRect(0, 0, w, h);
  if (a.statut === "construction") {
    c.fillStyle = "#3a3936"; c.font = "600 30px system-ui"; c.fillText("En construction", 24, 70);
    c.font = "22px system-ui"; c.fillText("aucune donnée, aucune activité", 24, 110);
  } else {
    const coul = { verifie: "#4cc38a", a_verifier: "#f0a03c", rejete: "#e05252" };
    c.fillStyle = "rgba(255,255,255,.06)"; c.fillRect(0, 0, w, 46);
    c.fillStyle = "#d4a64a"; c.font = "700 26px system-ui";
    c.fillText(m ? "Au travail" : d ? `${(window.GENRES_DOC || {})[d.genre] || d.genre}` : "Aucun document", 20, 32);
    c.font = "24px system-ui"; c.fillStyle = "#ece6d8";
    const texte = m ? m.etape : d ? d.titre : "pour l'instant";
    const mots = String(texte).split(" "); let ligne = "", yy = 92;
    for (const mot of mots) {
      if (c.measureText(ligne + mot).width > w - 40) { c.fillText(ligne, 20, yy); ligne = ""; yy += 32; if (yy > 200) break; }
      ligne += mot + " ";
    }
    if (yy <= 200) c.fillText(ligne, 20, yy);
    if (d && !m) {
      c.fillStyle = coul[d.statut] || "#9d9a92"; c.font = "600 24px system-ui";
      c.fillText(`● ${(window.STATUTS_DOC || {})[d.statut] || d.statut}`, 20, h - 26);
    }
  }
  ps.e.t.needsUpdate = true;
}

// ------------------------------------------------------------------ état réel -> scène
function maj3d(etat, choix) {
  if (!pret || !etat) return;
  for (const a of etat.agents) {
    const ps = postes[a.n];
    if (!ps) continue;
    ps.statut = a.statut; ps.travail = a.statut === "travail";
    ps.anneau.children[0].material.color.setHex(COULEURS[a.statut] || COULEURS.disponible);
    ps.anneau.children[1].material.color.setHex(COULEURS[a.statut] || COULEURS.disponible).multiplyScalar(0.22);
    ps.agent.visible = a.statut !== "construction";
    ps.tag.className = `tag3d ${a.statut}${choix === a.n ? " choisi" : ""}`;
    let sous = "";
    if (a.mission) sous = `${PHASES[a.mission.phase] || a.mission.phase} — ${ROLES[a.mission.role] || "…"}`;
    else if (a.statut !== "disponible") sous = a.file ? `file d'attente (${a.file})` : STATUTS[a.statut];
    ps.tag.querySelector("small").textContent = sous;
    ps.tag.title = `${a.nom} — ${a.mission ? a.mission.etape : STATUTS[a.statut]} · ${a.documents} document(s)`;
    dessinerEcran(ps, a);
    if (!ps.travail) { ps.corps.position.y = 0; ps.bras.forEach((b) => { b.rotation.x = 0; }); }
  }
  // lanterne de chaque pièce : l'état le plus important de ses agents (erreur, au travail, file d'attente, disponible)
  const ordre = ["erreur", "travail", "attente", "disponible"], etats = {};
  for (const ps of Object.values(postes)) {
    if (!ordre.includes(ps.statut)) continue;
    const a = etats[ps.zone];
    if (!a || ordre.indexOf(ps.statut) < ordre.indexOf(a)) etats[ps.zone] = ps.statut;
  }
  etatsPieces = etats; majBarre();
  for (const [k, p] of Object.entries(pieces)) {
    const st = etats[k], col = new THREE.Color(st ? COULEURS[st] : 0xffd9a0);
    for (const m of p.lampes) m.color.copy(col).multiplyScalar(st ? 2.4 : 1.3);
    for (const m of p.halos) m.color.copy(col).multiplyScalar(0.3);
  }
  const cle = JSON.stringify(etat.liens.map((l) => [l.de, l.a, l.genre]));
  if (cle !== dernierLiens) { dernierLiens = cle; liens(etat.liens); majEchanges(); }
}

// grand écran de la salle d'analyse : les vraies bougies H1 FERMÉES du jeu le plus récent (jamais inventées)
async function majGraphique() {
  if (!grand) return;
  try {
    const jeux = await (await fetch("api/jeux")).json();
    const fin = (j) => Math.max(0, ...Object.values(j.unites || {}).map((u) => u.fin || 0));
    const jeu = jeux.filter((j) => fin(j) > 0).sort((a, b) => fin(b) - fin(a))[0];
    dessinerGraphique(grand, jeu ? await (await fetch(`api/bougies?jeu=${jeu.id}&unite=H1&n=60`)).json() : null);
  } catch { /* université injoignable : l'écran garde sa dernière image */ }
}
function dessinerGraphique(e, r) {
  const c = e.c.getContext("2d"), w = e.c.width, h = e.c.height, b = r && r.bougies ? r.bougies : [];
  const g = c.createLinearGradient(0, 0, 0, h); g.addColorStop(0, "#0b1626"); g.addColorStop(1, "#05090f"); c.fillStyle = g; c.fillRect(0, 0, w, h);
  c.textAlign = "left"; c.textBaseline = "alphabetic";
  c.fillStyle = "#d4a64a"; c.font = "700 30px system-ui";
  if (!b.length) {
    c.fillText("Graphique du gold", 30, 56);
    c.fillStyle = "#9fb0c8"; c.font = "24px system-ui"; c.fillText("Aucune bougie disponible : importe un jeu dans la Salle des données.", 30, 104);
    e.t.needsUpdate = true;
    return;
  }
  c.fillText(`${r.jeu.symbole} · ${r.unite} · ${b.length} bougies fermées`, 30, 50);
  c.fillStyle = "#9fb0c8"; c.font = "20px system-ui";
  c.fillText(`${r.jeu.nom} — source : ${r.jeu.source}${r.jeu.temps_reel ? "" : " (différé ou historique)"}`, 30, 82);
  const x0 = 30, x1 = w - 120, y0 = 112, y1 = h - 54;
  const bas = Math.min(...b.map((k) => k[3])), haut = Math.max(...b.map((k) => k[2]));
  const Y = (v) => y1 - ((v - bas) / (haut - bas || 1)) * (y1 - y0);
  c.strokeStyle = "rgba(255,255,255,.07)"; c.lineWidth = 1; c.fillStyle = "#7f8ea6"; c.font = "18px system-ui";
  for (let k = 0; k <= 4; k++) { const v = bas + ((haut - bas) * k) / 4, y = Y(v); c.beginPath(); c.moveTo(x0, y); c.lineTo(x1, y); c.stroke(); c.fillText(v.toFixed(1), x1 + 12, y + 6); }
  const pas = (x1 - x0) / b.length;
  b.forEach(([, o, hh, l, cl], i) => {
    const x = x0 + pas * (i + 0.5), col = cl >= o ? "#3fbf86" : "#e0525a";
    c.strokeStyle = col; c.fillStyle = col; c.lineWidth = 1.5;
    c.beginPath(); c.moveTo(x, Y(hh)); c.lineTo(x, Y(l)); c.stroke();
    const ya = Y(Math.max(o, cl)), yb = Y(Math.min(o, cl)); c.fillRect(x - pas * 0.32, ya, pas * 0.64, Math.max(1.5, yb - ya));
  });
  const der = b[b.length - 1], d = new Date(der[0] * 1000);
  c.fillStyle = "#ece6d8"; c.font = "600 20px system-ui";
  c.fillText(`Dernière bougie fermée : ${d.toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })} · clôture ${der[4].toFixed(1)}`, 30, h - 18);
  e.t.needsUpdate = true;
}
// écran de la salle de réunion : les vrais échanges entre agents
async function majEchanges() {
  if (!tableauEchanges) return;
  try { dessinerEchanges(tableauEchanges, await (await fetch("api/zone/reunion")).json()); } catch { /* idem */ }
}
function dessinerEchanges(e, r) {
  const c = e.c.getContext("2d"), w = e.c.width, h = e.c.height;
  const g = c.createLinearGradient(0, 0, 0, h); g.addColorStop(0, "#14100a"); g.addColorStop(1, "#080604"); c.fillStyle = g; c.fillRect(0, 0, w, h);
  c.textAlign = "left"; c.textBaseline = "alphabetic";
  c.fillStyle = "#d4a64a"; c.font = "700 32px Georgia, serif"; c.fillText("Échanges entre agents", 30, 56);
  c.fillStyle = "#9fb0c8"; c.font = "22px system-ui"; c.fillText(`${r.messages_24h || 0} message(s) ces dernières 24 h`, 30, 92);
  const liste = (r.messages || []).slice(0, 6);
  if (!liste.length) { c.fillStyle = "#ece6d8"; c.font = "24px system-ui"; c.fillText("Aucun échange : les agents ne se parlent que pendant une vraie mission.", 30, 150, w - 60); }
  liste.forEach((m, i) => {
    const y = 146 + i * 64;
    c.fillStyle = m.genre === "alerte" ? "#e05252" : m.genre === "reponse" ? "#4cc38a" : "#d4a64a"; c.font = "600 22px system-ui";
    c.fillText(`Agent ${m.de} → agent ${m.a} · ${m.genre}`, 30, y);
    c.fillStyle = "#cfc8b8"; c.font = "20px system-ui";
    const t = String(m.contenu || "").replace(/\s+/g, " ");
    c.fillText(t.length > 80 ? t.slice(0, 79) + "…" : t, 30, y + 28, w - 60);
  });
  e.t.needsUpdate = true;
}

function liens(liste) {
  for (const o of liens3d) { scene.remove(o.mesh, o.point); o.mesh.geometry.dispose(); }
  liens3d = [];
  const couleur = { alerte: 0xe05252, reponse: 0x4cc38a };
  for (const l of liste) {
    const a = tetes[l.de], b = tetes[l.a];
    if (!a || !b || l.de === l.a) continue;
    const milieu = a.clone().lerp(b, 0.5); milieu.y += 3 + a.distanceTo(b) * 0.15;
    const courbe = new THREE.QuadraticBezierCurve3(a, milieu, b);
    const col = new THREE.Color(couleur[l.genre] || 0xd4a64a);
    const m = new THREE.MeshBasicMaterial({ color: col.clone().multiplyScalar(1.6), toneMapped: false, transparent: true, opacity: 0.7 });
    const mesh = new THREE.Mesh(new THREE.TubeGeometry(courbe, 64, 0.022, 6, false), m);
    const point = new THREE.Mesh(new THREE.SphereGeometry(0.09, 12, 8), new THREE.MeshBasicMaterial({ color: col.clone().multiplyScalar(3), toneMapped: false }));
    scene.add(mesh, point);
    mesh.visible = point.visible = !pieceVue;
    liens3d.push({ mesh, point, courbe });
  }
}

// ------------------------------------------------------------------ caméra, clics, rendu
const VUES = { ensemble: telephone ? [new THREE.Vector3(16, 26, 30), new THREE.Vector3(0, 0, 1)] : [new THREE.Vector3(22, 21, 30), new THREE.Vector3(-2, 0, -2)] };
const FOV = telephone ? [55, 74] : [38, 62];   // vue d'ensemble, dans une pièce
// point de vue dans chaque pièce (plan : x, y, hauteur des yeux) et ce qu'on regarde
const PLACES = {
  analyse: [[12.6, 12.1, 1.75], [8, 3.5, 1.3]], macro: [[42.6, 12.1, 1.75], [38, 3.5, 1.4]],
  reunion: [[27.2, 8.3, 1.8], [23.5, 4.2, 1.0]], directeur: [[27.4, 18.3, 2.05], [23.6, 13.2, 1.35]],
  bibliotheque: [[13.8, 28.2, 1.75], [7.5, 19.5, 1.4]], labo: [[27.6, 28.3, 1.75], [22.5, 23.4, 1.2]],
  risque: [[37.9, 28.3, 1.75], [34, 20.5, 1.2]], donnees: [[42.1, 28.3, 1.75], [45.5, 21, 1.3]],
};
let vol = null, pieceActuelle = null, pieceVue = null, barre = null, nav = null, zoomPiece = 1, pince = false, etatsPieces = {};
// vol de caméra : courbe passant par deux points (au-dessus des murs quand on entre ou sort d'une pièce)
function allerVers(pos, cible, duree = 900, c1 = null, c2 = null) {
  const de = camera.position.clone();
  vol = { de, deC: controls.target.clone(), a: pos, aC: cible, c1: c1 || de.clone().lerp(pos, 1 / 3), c2: c2 || de.clone().lerp(pos, 2 / 3), t: performance.now(), duree };
}
// vue d'ensemble : on tourne autour du bâtiment (au doigt : un doigt fait glisser le plan, deux doigts zooment et tournent)
// dans une pièce : on regarde autour de soi en « attrapant » la vue ; molette ou pincement = zoom ; toucher le sol = y aller
function limites() {
  if (pieceActuelle) Object.assign(controls, { minDistance: 0.01, maxDistance: 1, minPolarAngle: 0.45, maxPolarAngle: 2.4, rotateSpeed: -0.4, enableZoom: false, enablePan: false });
  else Object.assign(controls, { minDistance: 3, maxDistance: 85, minPolarAngle: 0, maxPolarAngle: 1.38, rotateSpeed: 1, enableZoom: true, enablePan: true });
  controls.touches = { ONE: pieceActuelle || !tactile ? THREE.TOUCH.ROTATE : THREE.TOUCH.PAN, TWO: pieceActuelle ? THREE.TOUCH.DOLLY_PAN : THREE.TOUCH.DOLLY_ROTATE };
}
// arrivé dans une pièce : le point regardé passe juste devant les yeux, la vue tourne alors autour de soi
function regarder() {
  const d = controls.target.clone().sub(camera.position);
  if (d.lengthSq() < 1e-6) camera.getWorldDirection(d);
  controls.target.copy(camera.position).addScaledVector(d.normalize(), 0.05);
  controls.update();
}
function entrer(cle) {
  const p = pieces[cle];
  if (!actif || !p) return false;
  const z = p.z, [pc, cc] = PLACES[cle] || [[z.x + z.l * 0.75, z.y + z.p - 0.9, 1.75], [z.x + z.l / 2, z.y + z.p * 0.35, 1.2]];
  const depuis = pieceActuelle && pieceActuelle !== cle ? pieces[pieceActuelle].z : null;
  const c1 = depuis ? P3(depuis.x + depuis.l / 2, depuis.y + depuis.p / 2, depuis.h + 5) : null;
  const c2 = P3(z.x + z.l / 2, z.y + z.p / 2, z.h + 6);
  pieceActuelle = cle; zoomPiece = 1; limites();
  allerVers(P3(...pc), P3(...cc), depuis ? 2300 : 1800, c1, c2);
  if (camera3d) ronde = performance.now() + 25000;
  majBarre(); carton(cle);
  return true;
}
function ensemble() {
  if (!actif) return false;
  const z = pieceActuelle ? pieces[pieceActuelle].z : null;
  pieceActuelle = null; zoomPiece = 1; limites();
  allerVers(VUES.ensemble[0].clone(), VUES.ensemble[1].clone(), z ? 1800 : 900, z ? P3(z.x + z.l / 2, z.y + z.p / 2, z.h + 6) : null);
  majBarre();
  return true;
}
// l'utilisateur entre lui-même dans une pièce (toucher, barre, boutons) : la ronde de la caméra s'arrête
function visiter(cle) {
  pris();
  if (!entrer(cle)) return;
  astuce("piece", tactile ? "Glisse pour regarder autour de toi · touche le sol pour avancer · ‹ › pièce voisine"
    : "Glisse pour regarder autour de toi · clic sur le sol pour avancer · Échap pour sortir");
}
// pièce voisine (boutons ‹ ›), dans l'ordre du plan
function voisine(sens) {
  const cles = plan.zones.map((z) => z.cle), i = cles.indexOf(pieceActuelle);
  visiter(cles[(i + (i < 0 && sens < 0 ? 0 : sens) + cles.length) % cles.length]);
}
// toucher une pièce : on y entre (et sur grand écran, sa fiche s'ouvre) ; déjà dedans : on avance (voir cliquer)
function allerPiece(cle) {
  if (pieceActuelle === cle && !vol) { window.ouvrirZone(cle); return; }
  visiter(cle);
  if (!telephone && !camera3d) window.ouvrirZone(cle);
}
function vue3d(nom) {
  if (!actif) return false;
  if (pieces[nom]) return entrer(nom);
  return ensemble();
}
function zoom3d(f) {
  if (!actif) return false;
  if (pieceActuelle) { zoomPiece = THREE.MathUtils.clamp(zoomPiece / f, 0.45, 1.25); return true; }
  const v = camera.position.clone().sub(controls.target).multiplyScalar(1 / f);
  if (v.length() < controls.minDistance || v.length() > controls.maxDistance) return true;
  allerVers(controls.target.clone().add(v), controls.target.clone(), 350);
  return true;
}
// vue d'ensemble : un quart de tour (boutons ⟲ ⟳), en suivant l'arc de cercle
function tourner(sens) {
  if (!actif || pieceActuelle) return;
  const t = controls.target.clone(), o = camera.position.clone().sub(t), axe = new THREE.Vector3(0, 1, 0);
  const pt = (k) => t.clone().add(o.clone().applyAxisAngle(axe, sens * Math.PI / 4 * k));
  allerVers(pt(1), t, 700, pt(1 / 3), pt(2 / 3));
}
// dans une pièce : on avance vers le point touché (on s'arrête juste avant, le regard ne change pas)
function marcher(p) {
  const z = pieces[pieceActuelle].z, m = EP + 0.3, cl = THREE.MathUtils.clamp, de = camera.position.clone();
  const vers = new THREE.Vector3(p.x - de.x, 0, p.z - de.z), d = vers.length();
  if (d < 0.25) return;
  const a = de.clone().addScaledVector(vers.normalize(), Math.max(0, d - 0.5));
  a.x = cl(a.x, z.x + m - L / 2, z.x + z.l - m - L / 2);
  a.z = cl(a.z, z.y + m - P / 2, z.y + z.p - m - P / 2);
  allerVers(a, controls.target.clone().add(a.clone().sub(de)), cl(d * 260, 450, 1300));
}
// dans une pièce, la caméra reste entre les murs (le regard la suit)
function garderDans(cle) {
  const z = pieces[cle].z, m = EP + 0.3, cl = THREE.MathUtils.clamp, v = camera.position, avant = v.clone();
  v.x = cl(v.x, z.x + m - L / 2, z.x + z.l - m - L / 2);
  v.z = cl(v.z, z.y + m - P / 2, z.y + z.p - m - P / 2);
  v.y = cl(v.y, 0.45, z.h - 0.25);
  controls.target.add(v.clone().sub(avant));
}
// vue d'ensemble : ce qu'on regarde reste au-dessus du bâtiment (on ne le perd pas en faisant glisser)
function garderBatiment() {
  const t = controls.target, cl = THREE.MathUtils.clamp, avant = t.clone();
  t.x = cl(t.x, -L / 2, L / 2); t.z = cl(t.z, -P / 2, P / 2); t.y = cl(t.y, 0, 4);
  camera.position.add(t.clone().sub(avant));
}
// murs coupés selon l'orientation de la caméra (vue d'ensemble) ou tous debout (à hauteur d'homme)
const dirCam = new THREE.Vector3();
function majCoupes(dt) {
  camera.getWorldDirection(dirCam);
  const debout = camera.position.y < PLEIN + 0.4, k = majCoupes.pret ? Math.min(1, dt * 5) : 1;   // au chargement : tout de suite
  majCoupes.pret = true;
  for (const c of COTES) {
    const o = coupes[c], f = debout ? 0 : THREE.MathUtils.smoothstep(-NORMALES[c].dot(dirCam), 0.1, 0.3);
    const cible = PLEIN - f * (PLEIN - COUPE_BAS);
    if (o.h === cible) continue;
    o.h += (cible - o.h) * k;
    if (Math.abs(cible - o.h) < 0.003) o.h = cible;
    o.plan.constant = o.h;
    for (const cap of o.caps) {
      const vu = o.h > cap.userData.bas + 0.02 && o.h < cap.userData.haut - 0.02;
      cap.visible = vu;
      if (vu) cap.position.y = o.h + 0.0175;
    }
  }
}
// pièce où se trouve la caméra : son plafond apparaît, seules ses étiquettes restent
function majPieceVue() {
  const x = camera.position.x + L / 2, y = camera.position.z + P / 2;
  let vue = null;
  for (const p of Object.values(pieces)) {
    const z = p.z;
    if (camera.position.y < z.h && x > z.x && x < z.x + z.l && y > z.y && y < z.y + z.p) { vue = z.cle; break; }
  }
  if (vue === pieceVue) return;
  pieceVue = vue;
  for (const p of Object.values(pieces)) { p.plafond.visible = p.z.cle === vue; if (p.nomObj) p.nomObj.visible = !vue; }
  for (const ps of Object.values(postes)) ps.tagObj.visible = !vue || ps.zone === vue;
  for (const l of liens3d) l.mesh.visible = l.point.visible = !vue;   // les arcs des messages se lisent de haut
}
function majOptique(dt) {
  const fov = pieceActuelle ? FOV[1] * zoomPiece : pieceVue ? FOV[1] : FOV[0], pres = camera.position.y < 4.5 ? 0.08 : 0.3;
  let change = camera.near !== pres;
  if (Math.abs(camera.fov - fov) > 0.05) { camera.fov += (fov - camera.fov) * Math.min(1, dt * (pince ? 14 : 3)); change = true; }
  if (change) { camera.near = pres; camera.updateProjectionMatrix(); }
}
// mode caméra (Jarvis) : la ronde passe voir les pièces où un agent travaille VRAIMENT, puis revient sur l'ensemble
let ronde = 0, rondeI = 0, priseEnMain = 0;
// l'utilisateur prend la main : la ronde et la rotation lente s'arrêtent (3 min au doigt, 1 min à la souris)
function pris() {
  if (!camera3d) return;
  controls.autoRotate = false; priseEnMain = performance.now() + (tactile ? 180000 : 60000);
}
function rondeCamera(t) {
  if (vol || t < priseEnMain) return;
  if (!ronde) { ronde = t + 40000; return; }
  if (t < ronde) return;
  if (pieceActuelle) { ensemble(); controls.autoRotate = true; ronde = t + 45000; return; }
  const occupees = [...new Set(Object.values(postes).filter((ps) => ps.travail).map((ps) => ps.zone))];
  if (!occupees.length) { ronde = t + 15000; return; }
  rondeI = (rondeI + 1) % occupees.length;
  controls.autoRotate = false; entrer(occupees[rondeI]); ronde = t + 20000;
}
// barre des pièces (au-dessus de la vue) : entrer dans une pièce, revenir à l'ensemble, ouvrir la fiche
function barrePieces() {
  barre = document.createElement("div"); barre.className = "pieces3d";
  const bouton = (cle, nom) => {
    const b = document.createElement("button"); b.type = "button"; b.textContent = nom; b.dataset.piece = cle;
    b.addEventListener("click", () => { if (cle) visiter(cle); else { pris(); ensemble(); } });
    if (cle && TAPIS[cle]) b.style.setProperty("--teinte", TAPIS[cle][0]);
    barre.appendChild(b);
  };
  bouton("", "Vue d'ensemble");
  for (const z of plan.zones) bouton(z.cle, COURTS[z.cle] || z.nom);
  const info = document.createElement("button"); info.type = "button"; info.className = "info"; info.textContent = "Fiche de la pièce"; info.hidden = true;
  info.addEventListener("click", () => pieceActuelle && window.ouvrirZone(pieceActuelle));
  barre.appendChild(info);
  conteneur.appendChild(barre);
  majBarre();
}
function majBarre() {
  majNav();
  if (!barre) return;
  barre.querySelectorAll("[data-piece]").forEach((b) => {
    b.classList.toggle("actif", (b.dataset.piece || null) === pieceActuelle);
    const st = etatsPieces[b.dataset.piece];
    if (st) b.dataset.etat = st; else delete b.dataset.etat;   // point coloré : l'état réel de ses agents
  });
  barre.querySelector(".info").hidden = !pieceActuelle;
  const a = barre.querySelector(".actif");   // la pièce choisie reste visible dans la barre (téléphone)
  if (a && majBarre.vue !== pieceActuelle && barre.scrollWidth > barre.clientWidth) barre.scrollTo({ left: a.offsetLeft - (barre.clientWidth - a.offsetWidth) / 2, behavior: "smooth" });
  majBarre.vue = pieceActuelle;
}
// boutons de déplacement en bas (écran tactile) : tourner et zoomer sur l'ensemble ; pièce voisine ou sortir dans une pièce
function navigation() {
  nav = document.createElement("div"); nav.className = "nav3d";
  const bouton = (texte, titre, action, classe = "") => {
    const b = document.createElement("button"); b.type = "button"; b.textContent = texte; b.title = titre;
    b.setAttribute("aria-label", titre); if (classe) b.className = classe;
    b.addEventListener("click", () => { pris(); action(); });
    nav.appendChild(b); return b;
  };
  nav.ensemble = [bouton("⟲", "Tourner à gauche", () => tourner(-1)), bouton("−", "Dézoomer", () => zoom3d(0.8)),
    bouton("+", "Zoomer", () => zoom3d(1.25)), bouton("⟳", "Tourner à droite", () => tourner(1))];
  nav.piece = [bouton("‹", "Pièce précédente", () => voisine(-1)), bouton("⌂ Sortir", "Revenir à la vue d'ensemble", ensemble, "large"),
    bouton("›", "Pièce suivante", () => voisine(1))];
  conteneur.appendChild(nav);
  majNav();
}
function majNav() {
  if (!nav) return;
  for (const b of nav.ensemble) b.hidden = !!pieceActuelle;
  for (const b of nav.piece) b.hidden = !pieceActuelle;
}
// petite astuce en bas de l'écran (les trois premières fois seulement)
function astuce(cle, texte) {
  if (camLente) return;
  let n = 0;
  try { n = +localStorage.getItem(`astuce3d-${cle}`) || 0; localStorage.setItem(`astuce3d-${cle}`, n + 1); } catch { /* navigation privée */ }
  if (n >= 3) return;
  conteneur.querySelector(".astuce3d")?.remove();
  const d = document.createElement("div"); d.className = "astuce3d"; d.textContent = texte;
  conteneur.appendChild(d); setTimeout(() => d.remove(), 5400);
}
// carton à l'entrée d'une pièce : son nom et ses agents (vrai état)
function carton(cle) {
  const z = pieces[cle].z, ag = Object.values(postes).filter((ps) => ps.zone === cle && ps.statut && ps.statut !== "construction");
  const n = ag.filter((ps) => ps.travail).length;
  conteneur.querySelector(".carton3d")?.remove();
  const d = document.createElement("div"); d.className = "carton3d";
  const b = document.createElement("b"); b.textContent = z.nom;
  const sous = document.createElement("span");
  sous.textContent = `${ag.length} agent${ag.length > 1 ? "s" : ""}${n ? ` · ${n} au travail` : ""}`;
  d.append(b, sous); conteneur.appendChild(d); setTimeout(() => d.remove(), 3400);
}

function cliquer() {
  const el = renderer.domElement, ray = new THREE.Raycaster(), souris = new THREE.Vector2(), cibles = cliquables.concat(murs3d, sols);
  const doigts = new Map(), cl = THREE.MathUtils.clamp;
  let depart = null, survol = null, plusieurs = false, ecart0 = 0, zoom0 = 1;
  const viser = (e) => {
    const r = el.getBoundingClientRect();
    souris.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(souris, camera);
    for (const t of ray.intersectObjects(cibles, false)) {
      const u = t.object.userData;
      if (!u.mur) return { u, p: t.point };
      if (t.point.y <= coupes[u.mur].h + 0.01) return null;   // partie debout d'un mur : le clic s'arrête là
    }
    return null;
  };
  const ecart = () => { const [a, b] = [...doigts.values()]; return Math.hypot(a[0] - b[0], a[1] - b[1]) || 1; };
  el.addEventListener("pointerdown", (e) => {
    doigts.set(e.pointerId, [e.clientX, e.clientY]);
    if (doigts.size === 1) { depart = [e.clientX, e.clientY]; plusieurs = false; }
    if (doigts.size === 2) { plusieurs = true; ecart0 = ecart(); zoom0 = zoomPiece; }
    pris();
  });
  el.addEventListener("pointermove", (e) => {
    if (doigts.has(e.pointerId)) {
      doigts.set(e.pointerId, [e.clientX, e.clientY]);
      if (doigts.size === 2 && pieceActuelle && ecart0) { zoomPiece = cl(zoom0 * ecart0 / ecart(), 0.45, 1.25); pince = true; }
    }
    if (e.buttons || e.pointerType === "touch") return;
    const h = viser(e), u = h && h.u, cle = u ? (u.agent ? `a${u.agent}` : `z${u.zone}`) : null;
    el.style.cursor = cle ? "pointer" : "grab";
    if (cle === survol) return;
    survol = cle;
    for (const t of cliquables) if (t.userData.zone) t.material.emissive.setHex(u && u.zone === t.userData.zone && u.zone !== pieceActuelle ? 0x2a1d06 : 0x000000);
  });
  const lacher = (e) => {
    doigts.delete(e.pointerId);
    if (doigts.size < 2) { ecart0 = 0; pince = false; }
  };
  el.addEventListener("pointerup", (e) => {
    lacher(e);
    const tape = depart && !plusieurs && Math.hypot(e.clientX - depart[0], e.clientY - depart[1]) <= (e.pointerType === "touch" ? 10 : 6);
    if (doigts.size === 0) depart = null;
    if (!tape) return;
    const h = viser(e), u = h && h.u;
    if (u && u.agent) window.voirAgent(u.agent);
    else if (u && u.zone && u.zone === pieceActuelle) { if (!vol) marcher(h.p); }
    else if (u && u.zone) allerPiece(u.zone);
  });
  el.addEventListener("pointercancel", (e) => { lacher(e); if (doigts.size === 0) depart = null; });
  el.addEventListener("wheel", (e) => {   // dans une pièce, la molette règle le zoom de l'objectif
    if (!pieceActuelle) return;
    e.preventDefault(); pris();
    zoomPiece = cl(zoomPiece * Math.exp(e.deltaY * 0.0012), 0.45, 1.25);
  }, { passive: false });
  window.addEventListener("keydown", (e) => {
    if (!actif || (e.target.closest && e.target.closest("input, textarea, select, dialog"))) return;
    if (e.key === "Escape" && pieceActuelle) ensemble();
    else if ((e.key === "ArrowUp" || e.key === "ArrowDown") && pieceActuelle && !vol) {   // flèches : un pas en avant ou en arrière
      const d = new THREE.Vector3(); camera.getWorldDirection(d); d.y = 0;
      marcher(camera.position.clone().addScaledVector(d.normalize(), e.key === "ArrowUp" ? 1.3 : -0.8));
      e.preventDefault();
    }
  });
}

// étalonnage final : vignette et léger grain (cinéma)
// garde-fou avant le halo : sur la carte graphique du PC, un reflet trop fort (cristaux des lustres, verre) dépasse la
// limite des demi-flottants et devient « infini » ; le halo l'étalait puis le rendu de l'image en faisait du noir :
// la petite caméra de l'écran Jarvis restait noire par moments. On borne chaque pixel (et un NaN devient noir seul).
const BORNES = {
  uniforms: { tDiffuse: { value: null } },
  vertexShader: "varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }",
  fragmentShader: "uniform sampler2D tDiffuse; varying vec2 vUv;" +
    "void main(){ vec3 c = texture2D(tDiffuse, vUv).rgb; if (any(isnan(c))) c = vec3(0.0); gl_FragColor = vec4(clamp(c, 0.0, 64.0), 1.0); }",
};
const ETALONNAGE = {
  uniforms: { tDiffuse: { value: null }, temps: { value: 0 } },
  vertexShader: "varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }",
  fragmentShader: "uniform sampler2D tDiffuse; uniform float temps; varying vec2 vUv;" +
    "float h(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233)) + temps) * 43758.5453); }" +
    "void main(){ vec4 c = texture2D(tDiffuse, vUv); vec2 d = vUv - 0.5; float v = smoothstep(0.85, 0.25, length(d * vec2(1.0, 0.85)));" +
    "c.rgb *= mix(0.62, 1.0, v); c.rgb = mix(c.rgb, c.rgb * vec3(1.04, 1.0, 0.94), 0.6); c.rgb += (h(vUv * 800.0) - 0.5) * 0.018; gl_FragColor = c; }",
};
let grain = null;

function taille() {
  const r = conteneur.getBoundingClientRect();
  if (!r.width || !r.height) return;
  renderer.setSize(r.width, r.height); labels.setSize(r.width, r.height); composer.setSize(r.width, r.height);
  camera.aspect = r.width / r.height; camera.updateProjectionMatrix();
}

function boucle(t) {
  requestAnimationFrame(boucle);
  if (!actif || document.hidden) return;
  if (camLente && (image++ & 1)) return;
  const s = (t - t0) / 1000, dt = Math.min(0.25, (t - (boucle.avant || t)) / 1000);
  boucle.avant = t;
  if (vol) {
    const k = Math.min(1, (t - vol.t) / vol.duree), e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2, u = 1 - e;
    camera.position.set(0, 0, 0).addScaledVector(vol.de, u * u * u).addScaledVector(vol.c1, 3 * u * u * e)
      .addScaledVector(vol.c2, 3 * u * e * e).addScaledVector(vol.a, e * e * e);
    controls.target.lerpVectors(vol.deC, vol.aC, e); camera.lookAt(controls.target);
    if (k >= 1) { vol = null; if (pieceActuelle) regarder(); }
  } else {
    controls.update();
    if (pieceActuelle) garderDans(pieceActuelle); else garderBatiment();
  }
  majCoupes(dt); majPieceVue(); majOptique(dt);
  if (camera3d) rondeCamera(t);
  // seulement les agents réellement au travail bougent (frappe au clavier, halo qui pulse)
  for (const ps of Object.values(postes)) {
    if (ps.travail) {
      ps.corps.position.y = Math.sin(s * 3) * 0.008;
      ps.bras[0].rotation.x = Math.sin(s * 14) * 0.06; ps.bras[1].rotation.x = Math.sin(s * 14 + 2) * 0.06;
      const k = 1 + 0.12 * (0.5 + 0.5 * Math.sin(s * 4)); ps.anneau.scale.set(k, 1, k);
    } else if (ps.anneau.scale.x !== 1) ps.anneau.scale.set(1, 1, 1);
  }
  for (const l of liens3d) l.point.position.copy(l.courbe.getPoint((s * 0.45) % 1));
  if (poussiere) {
    const p = poussiere.geometry.attributes.position, b = poussiere.userData.base;
    for (let i = 0; i < p.count; i++) p.setXYZ(i, b[i * 3] + Math.sin(s * 0.13 + i) * 0.15, b[i * 3 + 1] + Math.sin(s * 0.09 + i * 1.7) * 0.2, b[i * 3 + 2] + Math.cos(s * 0.11 + i) * 0.15);
    p.needsUpdate = true;
  }
  if (feu) {   // cheminée du directeur (décor)
    feu.lum.intensity = 2.4 + Math.sin(s * 7.3) * 0.35 + Math.sin(s * 13.1) * 0.25;
    feu.flammes.forEach((f, i) => { f.scale.y = 1 + 0.16 * Math.sin(s * (6 + i * 1.7) + i); f.scale.x = 1 + 0.06 * Math.sin(s * 9 + i); });
  }
  if (grain) grain.uniforms.temps.value = s % 10;
  if (image % 120 === 0) dessinerHorloges();
  if (!camLente) image++;
  composer.render();
  labels.render(scene, camera);
}

function webglPossible() {
  try { const c = document.createElement("canvas"); return !!(window.WebGL2RenderingContext && c.getContext("webgl2")); } catch { return false; }
}

async function demarrer() {
  conteneur = document.getElementById("scene3d");
  if (!conteneur || new URLSearchParams(location.search).get("vue") === "plan" || !webglPossible()) return;
  plan = await (await fetch("api/scene")).json();
  L = plan.sol.l; P = plan.sol.p;
  renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: "high-performance" });
  renderer.setPixelRatio(camLente ? 1 : Math.min(window.devicePixelRatio, camera3d ? 1.5 : telephone ? 1.75 : 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.localClippingEnabled = true;   // murs coupés de la vue d'ensemble
  conteneur.appendChild(renderer.domElement);
  labels = new CSS2DRenderer(); labels.domElement.className = "etiquettes3d"; conteneur.appendChild(labels.domElement);
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x07060a);
  scene.fog = new THREE.FogExp2(0x0d0a09, 0.0085);
  environnement();
  camera = new THREE.PerspectiveCamera(telephone ? 55 : 38, 1, 0.3, 300);
  camera.position.copy(VUES.ensemble[0]);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.target.copy(VUES.ensemble[1]);
  Object.assign(controls, { enableDamping: true, dampingFactor: 0.08, maxPolarAngle: 1.38, minDistance: 3, maxDistance: 85, screenSpacePanning: false });
  if (camera3d) {   // la caméra tourne seule ; si on la prend en main, elle reprend sa ronde 20 s après (3 min au doigt)
    let reprise = null;
    Object.assign(controls, { autoRotate: true, autoRotateSpeed: 0.35 });
    controls.addEventListener("start", () => { pris(); clearTimeout(reprise); });
    controls.addEventListener("end", () => { reprise = setTimeout(() => { if (!pieceActuelle) controls.autoRotate = true; }, tactile ? 180000 : 20000); });
  }
  // rendu : anticrénelage (MSAA), halo lumineux, étalonnage
  const cible = new THREE.WebGLRenderTarget(16, 16, { type: THREE.HalfFloatType, samples: LEGER ? 2 : 4 });
  composer = new EffectComposer(renderer, cible);
  composer.addPass(new RenderPass(scene, camera));
  composer.addPass(new ShaderPass(BORNES));
  composer.addPass(new UnrealBloomPass(new THREE.Vector2(512, 512), 0.36, 0.5, 0.9));
  composer.addPass(new OutputPass());
  grain = new ShaderPass(ETALONNAGE); composer.addPass(grain);
  materiaux(); salle(); allees(); lumieres();
  for (const z of plan.zones) { piece(z); tapis(z); decor(z); }
  plante(0.5, 15); plante(47.5, 0.6); plante(29.6, 9.6); plante(18.4, 20.4); plante(47.5, 29.4); plante(0.5, 29.4);
  for (const p of plan.postes) poste(p);
  cliquer(); limites(); barrePieces(); navigation();
  majGraphique(); majEchanges();
  setInterval(majGraphique, 5 * 60000); setInterval(majEchanges, 60000);
  new ResizeObserver(taille).observe(conteneur);
  pret = true;
  window.maj3d = maj3d; window.vue3d = vue3d; window.zoom3d = zoom3d;
  basculer(window.modePlateau ? window.modePlateau() : "bureau");
  if (window.etatCourant) maj3d(window.etatCourant(), null);
  requestAnimationFrame(boucle);
  astuce("ensemble", tactile ? "Un doigt : faire glisser · deux doigts : zoomer et tourner · touche une pièce pour y entrer"
    : "Glisser : tourner · clic droit : se déplacer · molette : zoom · clic sur une pièce : y entrer");
}

// Le bureau en 3D remplace la vue 2,5D quand on est en mode « bureau » ; le hall en cercle reste en SVG.
function basculer(mode) {
  if (!pret) return;
  actif = mode === "bureau";
  conteneur.hidden = !actif;
  document.getElementById("plateau").style.display = actif ? "none" : (mode === "bureau" ? "" : "none");
  document.body.classList.toggle("en3d", actif);
  if (actif) taille();
}
window.basculer3d = basculer;
demarrer().catch((e) => { console.warn("Bureau 3D indisponible, vue 2,5D gardée :", e); });
