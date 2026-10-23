// Bureau 3D (WebGL, three.js en copie locale) : même plan que la vue 2,5D (/api/scene), même état réel (/api/etat).
// Lumières, ombres, reflets et halo lumineux pour l'ambiance ; mais rien ne bouge sans une mission réellement en
// cours, un poste « en construction » reste vide et éteint, les arcs lumineux sont de vrais messages entre agents.
// Sans WebGL, la vue 2,5D en SVG prend le relais (bureau.js).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

const COULEURS = { disponible: 0x4cc38a, travail: 0x5aa7ff, attente: 0xf0a03c, erreur: 0xe05252, construction: 0x55534f };
const TEINTES = { directeur: "#3a2a0e", analyse: "#0f1d33", macro: "#24112e", reunion: "#142318", bibliotheque: "#2e1a0c",
  labo: "#0c2626", risque: "#2e0f12", donnees: "#101a2e" };
const MUR = 9, MEZZ = 4.6;
const telephone = window.innerWidth < 700;

let plan, L, P, renderer, scene, camera, controls, composer, labels, conteneur, pret = false, actif = false;
const postes = {}, cliquables = [], tetes = {};
let liens3d = [], dernierLiens = "", t0 = performance.now();

// ------------------------------------------------------------------ outils
const P3 = (x, y, z = 0) => new THREE.Vector3(x - L / 2, z, y - P / 2);
function hasard(graine) { let a = graine >>> 0; return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function toile(w, h, dessin) {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  dessin(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  return t;
}
const mat = (o) => new THREE.MeshStandardMaterial(o);
function boite(l, h, p, m, x, y, z, ombre = true) {
  const b = new THREE.Mesh(new THREE.BoxGeometry(l, h, p), m);
  b.position.set(x, y, z); b.castShadow = ombre; b.receiveShadow = true;
  return b;
}

// ------------------------------------------------------------------ matériaux (textures dessinées par le code)
let M;
function materiaux() {
  const marbre = toile(512, 512, (c, w, h) => {
    const r = hasard(7);
    for (let i = 0; i < 2; i++) for (let j = 0; j < 2; j++) {
      c.fillStyle = (i + j) % 2 ? "#0b0e16" : "#151a26"; c.fillRect(i * w / 2, j * h / 2, w / 2, h / 2);
    }
    c.lineWidth = 1;
    for (let k = 0; k < 40; k++) {
      c.strokeStyle = `rgba(200,210,235,${0.03 + r() * 0.06})`;
      c.beginPath(); let x = r() * w, y = r() * h; c.moveTo(x, y);
      for (let s = 0; s < 6; s++) { x += (r() - 0.3) * 90; y += (r() - 0.5) * 60; c.lineTo(x, y); }
      c.stroke();
    }
    c.strokeStyle = "rgba(212,166,74,.55)"; c.lineWidth = 3;
    c.strokeRect(1.5, 1.5, w - 3, h - 3); c.beginPath(); c.moveTo(w / 2, 0); c.lineTo(w / 2, h); c.moveTo(0, h / 2); c.lineTo(w, h / 2); c.stroke();
  });
  marbre.wrapS = marbre.wrapT = THREE.RepeatWrapping;
  const bois = toile(256, 256, (c, w, h) => {
    const r = hasard(3);
    c.fillStyle = "#4a2c14"; c.fillRect(0, 0, w, h);
    for (let y = 0; y < h; y += 2) { c.fillStyle = `rgba(${90 + r() * 40},${52 + r() * 20},${22 + r() * 10},${0.25 + r() * 0.3})`; c.fillRect(0, y, w, 1 + r() * 2); }
  });
  const fenetre = toile(256, 512, (c, w, h) => {
    const g = c.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, "#c8d8ff"); g.addColorStop(0.55, "#5e7bc4"); g.addColorStop(1, "#1d2a52");
    c.fillStyle = g; c.beginPath(); c.moveTo(0, h); c.lineTo(0, w / 2); c.arc(w / 2, w / 2, w / 2, Math.PI, 0); c.lineTo(w, h); c.fill();
    c.strokeStyle = "#0a0d16"; c.lineWidth = 10;
    for (let x = w / 3; x < w; x += w / 3) { c.beginPath(); c.moveTo(x, 20); c.lineTo(x, h); c.stroke(); }
    for (let y = w / 2 + 40; y < h; y += 90) { c.beginPath(); c.moveTo(0, y); c.lineTo(w, y); c.stroke(); }
  });
  M = {
    sol: mat({ map: marbre, roughness: 0.34, metalness: 0.1 }),
    mur: mat({ color: 0x0d1424, roughness: 0.85 }),
    pierre: mat({ color: 0x1b2131, roughness: 0.6 }),
    or: mat({ color: 0xd4a64a, metalness: 1, roughness: 0.28 }),
    bois: mat({ map: bois, roughness: 0.45, metalness: 0.05 }),
    boisSombre: mat({ map: bois, color: 0x8a7060, roughness: 0.55 }),
    cuir: mat({ color: 0x1a1616, roughness: 0.5 }),
    metal: mat({ color: 0x2a2d35, metalness: 0.8, roughness: 0.35 }),
    ecranOff: mat({ color: 0x05070c, roughness: 0.2, metalness: 0.4 }),
    costume: mat({ color: 0x1b2438, roughness: 0.65 }),
    peau: mat({ color: 0xcbbfae, roughness: 0.55 }),
    fenetre: new THREE.MeshBasicMaterial({ map: fenetre, toneMapped: false, color: 0x9aa6c8 }),
    feuille: mat({ color: 0x2f6b3a, roughness: 0.8, flatShading: true }),
    pot: mat({ color: 0x2b2118, roughness: 0.7 }),
    gris: mat({ color: 0x3b3c40, roughness: 0.9 }),
  };
}

// ------------------------------------------------------------------ la salle
function salle() {
  const S = plan.sol;
  const sol = new THREE.Mesh(new THREE.PlaneGeometry(S.l + 8, S.p + 8), M.sol);
  sol.material.map.repeat.set((S.l + 8) / 4, (S.p + 8) / 4);
  sol.rotation.x = -Math.PI / 2; sol.receiveShadow = true; scene.add(sol);
  // murs du fond (gauche et arrière), colonnes, hautes fenêtres, mezzanine
  const mx = -L / 2 - 4, mz = -P / 2 - 4;
  scene.add(boite(S.l + 8, MUR, 0.6, M.mur, 0, MUR / 2, mz - 0.3, false));
  scene.add(boite(0.6, MUR, S.p + 8, M.mur, mx - 0.3, MUR / 2, 0, false));
  const colonne = new THREE.CylinderGeometry(0.42, 0.5, MUR, 20);
  const chapiteau = new THREE.BoxGeometry(1.2, 0.35, 1.2);
  const fen = new THREE.PlaneGeometry(2.8, 5.2);
  for (let x = -L / 2 - 4; x <= L / 2 + 4.01; x += 6) {
    const c = new THREE.Mesh(colonne, M.pierre); c.position.set(x, MUR / 2, mz + 0.5); c.castShadow = true; scene.add(c);
    const h = new THREE.Mesh(chapiteau, M.or); h.position.set(x, MUR - 0.2, mz + 0.5); scene.add(h);
    if (x + 3 < L / 2 + 4) { const f = new THREE.Mesh(fen, M.fenetre); f.position.set(x + 3, 4.6, mz + 0.02); scene.add(f); }
  }
  for (let z = -P / 2 - 4; z <= P / 2 + 4.01; z += 6) {
    const c = new THREE.Mesh(colonne, M.pierre); c.position.set(mx + 0.5, MUR / 2, z); c.castShadow = true; scene.add(c);
    const h = new THREE.Mesh(chapiteau, M.or); h.position.set(mx + 0.5, MUR - 0.2, z); scene.add(h);
    if (z + 3 < P / 2 + 4) { const f = new THREE.Mesh(fen, M.fenetre); f.rotation.y = Math.PI / 2; f.position.set(mx + 0.02, 4.6, z + 3); scene.add(f); }
  }
  // corniche dorée en haut des murs
  scene.add(boite(S.l + 8.6, 0.25, 0.9, M.or, 0, MUR + 0.12, mz + 0.1, false));
  scene.add(boite(0.9, 0.25, S.p + 8.6, M.or, mx + 0.1, MUR + 0.12, 0, false));
  // mezzanine : dalle, garde-corps doré, petites lumières dessous
  scene.add(boite(S.l + 8, 0.35, 2.4, M.pierre, 0, MEZZ, mz + 1.5));
  scene.add(boite(2.4, 0.35, S.p + 8, M.pierre, mx + 1.5, MEZZ, 0));
  scene.add(boite(S.l + 8, 0.06, 0.06, M.or, 0, MEZZ + 1.05, mz + 2.65, false));
  scene.add(boite(0.06, 0.06, S.p + 8, M.or, mx + 2.65, MEZZ + 1.05, 0, false));
  const barreau = new THREE.CylinderGeometry(0.025, 0.025, 1, 6);
  const nb = Math.round((S.l + 8) / 0.8) + Math.round((S.p + 8) / 0.8);
  const bars = new THREE.InstancedMesh(barreau, M.or, nb);
  const m4 = new THREE.Matrix4(); let i = 0;
  for (let x = -L / 2 - 4; x < L / 2 + 4 && i < nb; x += 0.8) bars.setMatrixAt(i++, m4.makeTranslation(x, MEZZ + 0.6, mz + 2.65));
  for (let z = -P / 2 - 4; z < P / 2 + 4 && i < nb; z += 0.8) bars.setMatrixAt(i++, m4.makeTranslation(mx + 2.65, MEZZ + 0.6, z));
  bars.count = i; scene.add(bars);
  const ampoule = new THREE.MeshBasicMaterial({ color: 0xffd9a0, toneMapped: false });
  const petite = new THREE.SphereGeometry(0.08, 8, 6);
  for (let x = -L / 2 - 2; x < L / 2 + 4; x += 3) { const a = new THREE.Mesh(petite, ampoule); a.position.set(x, MEZZ - 0.25, mz + 2.4); scene.add(a); }
  for (let z = -P / 2 - 2; z < P / 2 + 4; z += 3) { const a = new THREE.Mesh(petite, ampoule); a.position.set(mx + 2.4, MEZZ - 0.25, z); scene.add(a); }
  // bordure dorée du sol
  const bord = new THREE.MeshBasicMaterial({ color: 0xb8892f });
  for (const [l, p, x, z] of [[S.l + 1, 0.12, 0, -P / 2 - 0.5], [S.l + 1, 0.12, 0, P / 2 + 0.5], [0.12, S.p + 1, -L / 2 - 0.5, 0], [0.12, S.p + 1, L / 2 + 0.5, 0]]) {
    const b = new THREE.Mesh(new THREE.PlaneGeometry(l, p), bord); b.rotation.x = -Math.PI / 2; b.position.set(x, 0.005, z); scene.add(b);
  }
}

function lumieres() {
  scene.add(new THREE.HemisphereLight(0x5a6aa8, 0x120c06, 0.75));
  const lune = new THREE.DirectionalLight(0xaabfff, 1.4);
  lune.position.set(-34, 30, -26); lune.castShadow = true;
  lune.shadow.mapSize.set(telephone ? 1024 : 2048, telephone ? 1024 : 2048);
  Object.assign(lune.shadow.camera, { left: -36, right: 36, top: 30, bottom: -30, near: 5, far: 110 });
  lune.shadow.bias = -0.0005; lune.shadow.normalBias = 0.03;
  scene.add(lune);
  // lustres au-dessus de chaque pièce : lumière chaude (décor fixe)
  const anneau = new THREE.TorusGeometry(0.9, 0.06, 8, 32);
  const flamme = new THREE.MeshBasicMaterial({ color: 0xffd28a, toneMapped: false });
  const bougie = new THREE.SphereGeometry(0.07, 8, 6);
  for (const z of plan.zones) {
    const c = P3(z.x + z.l / 2, z.y + z.p / 2, 6.2);
    const l = new THREE.PointLight(0xffc77a, z.cle === "directeur" ? 55 : 32, 18, 1.6);
    l.position.copy(c); scene.add(l);
    const lustre = new THREE.Group(); lustre.position.copy(c).add(new THREE.Vector3(0, 0.4, 0));
    const a = new THREE.Mesh(anneau, M.or); a.rotation.x = Math.PI / 2; lustre.add(a);
    for (let k = 0; k < 8; k++) { const b = new THREE.Mesh(bougie, flamme); b.position.set(Math.cos(k * Math.PI / 4) * 0.9, 0.12, Math.sin(k * Math.PI / 4) * 0.9); lustre.add(b); }
    const fil = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, MUR - c.y, 4), M.or); fil.position.y = (MUR - c.y) / 2; lustre.add(fil);
    scene.add(lustre);
  }
}

// ------------------------------------------------------------------ pièces (tapis cliquables + mobilier fixe)
function tapis(z) {
  const tex = toile(512, 512, (c, w, h) => {
    c.fillStyle = TEINTES[z.cle] || "#111"; c.fillRect(0, 0, w, h);
    const r = hasard(z.cle.length * 31);
    for (let k = 0; k < 400; k++) { c.fillStyle = `rgba(255,255,255,${r() * 0.025})`; c.fillRect(r() * w, r() * h, 2, 2); }
    c.strokeStyle = "rgba(212,166,74,.85)"; c.lineWidth = 6; c.strokeRect(14, 14, w - 28, h - 28);
    c.lineWidth = 2; c.strokeRect(30, 30, w - 60, h - 60);
  });
  const m = mat({ map: tex, roughness: 0.95, emissive: 0x000000 });
  const t = new THREE.Mesh(new THREE.PlaneGeometry(z.l - 0.5, z.p - 0.5), m);
  t.rotation.x = -Math.PI / 2; t.position.copy(P3(z.x + z.l / 2, z.y + z.p / 2, 0.012)); t.receiveShadow = true;
  t.userData = { zone: z.cle };
  scene.add(t); cliquables.push(t);
  const d = document.createElement("div");
  d.className = "nom-zone3d"; d.textContent = z.nom; d.tabIndex = 0;
  d.addEventListener("click", () => window.ouvrirZone(z.cle));
  const o = new CSS2DObject(d); o.position.copy(P3(z.x + z.l / 2, z.y + z.p - 0.2, 0.05)); o.center.set(0.5, -0.4);
  scene.add(o);
}

function plante(x, y) {
  const g = new THREE.Group(); g.position.copy(P3(x, y));
  const p = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.22, 0.55, 14), M.pot); p.position.y = 0.27; p.castShadow = true; g.add(p);
  for (let k = 0; k < 3; k++) {
    const f = new THREE.Mesh(new THREE.IcosahedronGeometry(0.42 - k * 0.08, 0), M.feuille);
    f.position.set((k - 1) * 0.12, 0.85 + k * 0.32, (k % 2) * 0.1); f.castShadow = true; g.add(f);
  }
  scene.add(g);
}

function decor(z) {
  const c = P3(z.x + z.l / 2, z.y + z.p / 2);
  if (z.cle === "bibliotheque") {
    const livre = new THREE.BoxGeometry(0.09, 1, 0.3);
    const n = 4 * 5 * 26, livres = new THREE.InstancedMesh(livre, mat({ roughness: 0.7 }), n);
    const r = hasard(11), m4 = new THREE.Matrix4(), col = new THREE.Color(); let i = 0;
    const teintes = [0x5a1a14, 0x1d3a2a, 0x1c2a4a, 0x6a4a18, 0x3a1830, 0x2a2a2a];
    for (let k = 0; k < 4; k++) {
      const bx = z.x + 0.8 + k * 3.8, by = z.y + 0.7;
      const cadre = P3(bx + 1.5, by, 0);
      scene.add(boite(3.1, 2.8, 0.45, M.boisSombre, cadre.x, 1.4, cadre.z - 0.05));
      for (let s = 0; s < 5; s++) for (let b = 0; b < 26 && i < n; b++) {
        const hgt = 0.32 + r() * 0.16;
        m4.makeScale(1, hgt, 1).setPosition(cadre.x - 1.4 + b * 0.108, 0.25 + s * 0.53 + hgt / 2, cadre.z + 0.2);
        livres.setMatrixAt(i, m4); livres.setColorAt(i++, col.setHex(teintes[Math.floor(r() * teintes.length)]));
      }
    }
    livres.castShadow = true; scene.add(livres);
    const table = P3(z.x + 12.5, z.y + 9.5);
    scene.add(boite(3.6, 0.08, 1.6, M.bois, table.x, 0.78, table.z));
    scene.add(boite(3.3, 0.74, 1.3, M.boisSombre, table.x, 0.37, table.z));
    for (const dx of [-1, 1]) {
      const abat = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.2, 0.18, 12, 1, true), new THREE.MeshBasicMaterial({ color: 0x2fbf6a, side: THREE.DoubleSide, toneMapped: false }));
      abat.position.set(table.x + dx, 1.25, table.z); scene.add(abat);
    }
  } else if (z.cle === "reunion") {
    const t = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 0.08, 48), M.bois);
    t.scale.set(2.6, 1, 1); t.position.set(c.x, 0.78, c.z); t.castShadow = true; t.receiveShadow = true; scene.add(t);
    const bord = new THREE.Mesh(new THREE.TorusGeometry(1, 0.03, 6, 64), M.or); bord.scale.set(2.6, 1, 1); bord.rotation.x = Math.PI / 2; bord.position.set(c.x, 0.82, c.z); scene.add(bord);
    const pied = new THREE.Mesh(new THREE.CylinderGeometry(0.25, 0.5, 0.75, 16), M.metal); pied.position.set(c.x, 0.37, c.z); scene.add(pied);
    for (let k = 0; k < 10; k++) {
      const a = (k / 10) * Math.PI * 2, x = c.x + Math.cos(a) * 3.3, zz = c.z + Math.sin(a) * 1.5;
      fauteuil(x, zz, Math.atan2(c.x - x, c.z - zz));
    }
  } else if (z.cle === "labo") {
    const tb = P3(z.x + 3, z.y + 0.6);
    scene.add(boite(4.2, 2.2, 0.08, mat({ color: 0x8d949b, roughness: 0.75 }), tb.x, 1.9, tb.z));
    scene.add(boite(4.4, 0.08, 0.14, M.metal, tb.x, 0.78, tb.z + 0.05));
  } else if (z.cle === "donnees") {
    const led = toile(64, 256, (cx, w, h) => {
      cx.fillStyle = "#0b0f18"; cx.fillRect(0, 0, w, h);
      for (let y = 8; y < h; y += 14) { cx.fillStyle = "#16233a"; cx.fillRect(4, y, w - 8, 9); cx.fillStyle = "#3d7bd6"; cx.fillRect(w - 14, y + 3, 4, 3); }
    });
    const face = new THREE.MeshStandardMaterial({ map: led, emissive: 0xffffff, emissiveMap: led, emissiveIntensity: 0.6, roughness: 0.4 });
    for (let k = 0; k < 3; k++) {
      const b = P3(z.x + 1.5 + k * 1.6, z.y + 1.4);
      const baie = new THREE.Mesh(new THREE.BoxGeometry(1, 2.2, 1.2), [M.metal, M.metal, M.metal, M.metal, face, M.metal]);
      baie.position.set(b.x, 1.1, b.z); baie.castShadow = true; scene.add(baie);
    }
  } else if (z.cle === "risque") {
    const b = P3(z.x + z.l - 1.2, z.y + 1);
    scene.add(boite(1.2, 1.9, 0.9, M.metal, b.x, 0.95, b.z));
    const roue = new THREE.Mesh(new THREE.TorusGeometry(0.2, 0.03, 8, 24), M.or); roue.position.set(b.x, 1.1, b.z + 0.47); scene.add(roue);
  } else if (z.cle === "directeur") {
    // estrade : marbre sombre bordé d'or
    scene.add(boite(z.l - 2, 0.3, z.p - 2, M.pierre, c.x, 0.15, c.z));
    scene.add(boite(z.l - 1.9, 0.04, 0.08, M.or, c.x, 0.31, c.z + (z.p - 2) / 2));
    scene.add(boite(0.08, 0.04, z.p - 1.9, M.or, c.x + (z.l - 2) / 2, 0.31, c.z));
  }
}

function fauteuil(x, z, angle, y0 = 0) {
  const g = new THREE.Group(); g.position.set(x, y0, z); g.rotation.y = angle;
  g.add(boite(0.55, 0.1, 0.55, M.cuir, 0, 0.48, 0));
  g.add(boite(0.55, 0.6, 0.08, M.cuir, 0, 0.8, -0.27));
  const pied = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.42, 8), M.metal); pied.position.y = 0.22; g.add(pied);
  const base = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.28, 0.04, 5), M.metal); base.position.y = 0.03; g.add(base);
  scene.add(g);
  return g;
}

// ------------------------------------------------------------------ un poste : bureau, écran (contenu réel), agent
function ecranTexture() {
  const c = document.createElement("canvas"); c.width = 384; c.height = 224;
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  return { c, t };
}

function poste(p) {
  const dir = p.agent === 14, l = dir ? 3.4 : 2.2, pr = dir ? 1.5 : 1.1, y0 = dir ? 0.3 : 0;
  const g = new THREE.Group(); g.position.copy(P3(p.x, p.y, y0)); g.userData = { agent: p.agent };
  // bureau en bois, liseré doré
  g.add(boite(l, 0.07, pr, M.bois, 0, 0.76, 0));
  g.add(boite(0.07, 0.72, pr - 0.1, M.boisSombre, -l / 2 + 0.06, 0.37, 0));
  g.add(boite(0.07, 0.72, pr - 0.1, M.boisSombre, l / 2 - 0.06, 0.37, 0));
  g.add(boite(l - 0.2, 0.5, 0.05, M.boisSombre, 0, 0.47, -pr / 2 + 0.08));
  g.add(boite(l, 0.025, 0.03, M.or, 0, 0.8, pr / 2, false));
  // écran : son contenu = le dernier document réel de l'agent (ou sa mission en cours)
  const pied = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.05, 0.3, 8), M.metal); pied.position.set(0, 0.95, -pr / 2 + 0.25); g.add(pied);
  g.add(boite(dir ? 1.5 : 1.15, dir ? 0.82 : 0.68, 0.05, M.metal, 0, 1.4, -pr / 2 + 0.22));
  const e = ecranTexture();
  const vitre = new THREE.Mesh(new THREE.PlaneGeometry(dir ? 1.42 : 1.07, dir ? 0.74 : 0.6), new THREE.MeshBasicMaterial({ map: e.t, toneMapped: false }));
  vitre.position.set(0, 1.4, -pr / 2 + 0.25); g.add(vitre);
  g.add(boite(0.5, 0.02, 0.16, M.metal, 0, 0.8, 0.1, false));
  // lampe de bureau
  const lampe = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.45, 6), M.or); lampe.position.set(l / 2 - 0.3, 1.02, -pr / 2 + 0.25); g.add(lampe);
  const abat = new THREE.Mesh(new THREE.ConeGeometry(0.13, 0.14, 14, 1, true), M.or); abat.position.set(l / 2 - 0.3, 1.25, -pr / 2 + 0.25); g.add(abat);
  scene.add(g);
  // fauteuil + agent devant le bureau, tourné vers l'écran
  const assise = P3(p.x, p.y + pr / 2 + 0.55, y0);
  fauteuil(assise.x, assise.z, Math.PI, y0);
  const agent = new THREE.Group(); agent.position.copy(assise);
  const corps = new THREE.Mesh(new THREE.CapsuleGeometry(0.22, 0.42, 6, 14), M.costume); corps.position.y = 0.98; corps.castShadow = true; agent.add(corps);
  const tete = new THREE.Mesh(new THREE.SphereGeometry(0.15, 20, 14), M.peau); tete.position.y = 1.52; tete.castShadow = true; agent.add(tete);
  const bras = [];
  for (const s of [-1, 1]) {
    const b = new THREE.Mesh(new THREE.CapsuleGeometry(0.06, 0.4, 4, 8), M.costume);
    b.position.set(s * 0.25, 1.05, -0.2); b.rotation.x = -1.1; b.castShadow = true; agent.add(b); bras.push(b);
  }
  scene.add(agent);
  // anneau lumineux au sol : la couleur de son état réel
  const anneau = new THREE.Mesh(new THREE.RingGeometry(0.55, 0.7, 40), new THREE.MeshBasicMaterial({ color: COULEURS.disponible, toneMapped: false, transparent: true, opacity: 0.85 }));
  anneau.rotation.x = -Math.PI / 2; anneau.position.copy(assise).add(new THREE.Vector3(0, 0.02, 0)); scene.add(anneau);
  tetes[p.agent] = assise.clone().add(new THREE.Vector3(0, 1.55, 0));
  // étiquette (texte net, toujours lisible)
  const d = document.createElement("div");
  d.className = "tag3d"; d.innerHTML = `<i></i><b>${p.agent} · ${p.court}</b><small></small>`;
  d.addEventListener("click", () => window.voirAgent(p.agent));
  const tag = new CSS2DObject(d); tag.position.copy(P3(p.x, p.y, y0 + 2.3)); scene.add(tag);
  for (const o of [g, agent]) o.traverse((m) => { if (m.isMesh) { m.userData.agent = p.agent; cliquables.push(m); } });
  postes[p.agent] = { g, agent, corps, bras, anneau, vitre, e, tag: d, cle: "", statut: "", y0, travail: false };
}

function dessinerEcran(ps, a) {
  const d = a.dernier_document, m = a.mission;
  const cle = JSON.stringify([a.statut, m && m.etape, d && d.id, d && d.statut]);
  if (cle === ps.cle) return;
  ps.cle = cle;
  const c = ps.e.c.getContext("2d"), w = ps.e.c.width, h = ps.e.c.height;
  const fond = { travail: "#0d2a4f", erreur: "#3a0e0e", attente: "#2e2008", construction: "#020203" }[a.statut] || "#08101e";
  c.fillStyle = fond; c.fillRect(0, 0, w, h);
  if (a.statut === "construction") {
    c.fillStyle = "#3a3936"; c.font = "600 22px system-ui"; c.fillText("En construction", 18, 50);
    c.font = "17px system-ui"; c.fillText("aucune donnée, aucune activité", 18, 82);
  } else {
    const coul = { verifie: "#4cc38a", a_verifier: "#f0a03c", rejete: "#e05252" };
    c.fillStyle = "#d4a64a"; c.font = "700 21px system-ui";
    c.fillText(m ? "Au travail" : d ? `${(window.GENRES_DOC || {})[d.genre] || d.genre}` : "Aucun document", 16, 36);
    c.font = "18px system-ui"; c.fillStyle = "#e9e4d8";
    const texte = m ? m.etape : d ? d.titre : "pour l'instant";
    const mots = String(texte).split(" "); let ligne = "", yy = 72;
    for (const mot of mots) {
      if (c.measureText(ligne + mot).width > w - 32) { c.fillText(ligne, 16, yy); ligne = ""; yy += 25; if (yy > 150) break; }
      ligne += mot + " ";
    }
    if (yy <= 150) c.fillText(ligne, 16, yy);
    if (d && !m) {
      c.fillStyle = coul[d.statut] || "#9d9a92"; c.font = "600 18px system-ui";
      c.fillText(`● ${(window.STATUTS_DOC || {})[d.statut] || d.statut}`, 16, h - 22);
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
    ps.anneau.material.color.setHex(COULEURS[a.statut] || COULEURS.disponible);
    ps.agent.visible = a.statut !== "construction";
    ps.tag.className = `tag3d ${a.statut}${choix === a.n ? " choisi" : ""}`;
    let sous = "";
    if (a.mission) sous = `${PHASES[a.mission.phase] || a.mission.phase} — ${ROLES[a.mission.role] || "…"}`;
    else if (a.statut !== "disponible") sous = a.file ? `file d'attente (${a.file})` : STATUTS[a.statut];
    ps.tag.querySelector("small").textContent = sous;
    ps.tag.title = `${a.nom} — ${a.mission ? a.mission.etape : STATUTS[a.statut]} · ${a.documents} document(s)`;
    dessinerEcran(ps, a);
    if (!ps.travail) { ps.corps.position.y = 0.98; ps.bras.forEach((b) => { b.rotation.x = -1.1; }); }
  }
  const cle = JSON.stringify(etat.liens.map((l) => [l.de, l.a, l.genre]));
  if (cle !== dernierLiens) { dernierLiens = cle; liens(etat.liens); }
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
    const m = new THREE.MeshBasicMaterial({ color: couleur[l.genre] || 0xd4a64a, toneMapped: false, transparent: true, opacity: 0.75 });
    const mesh = new THREE.Mesh(new THREE.TubeGeometry(courbe, 48, 0.035, 6, false), m);
    const point = new THREE.Mesh(new THREE.SphereGeometry(0.12, 12, 8), new THREE.MeshBasicMaterial({ color: m.color, toneMapped: false }));
    scene.add(mesh, point);
    liens3d.push({ mesh, point, courbe });
  }
}

// ------------------------------------------------------------------ caméra, clics, rendu
const VUES = { ensemble: telephone ? [new THREE.Vector3(16, 26, 30), new THREE.Vector3(0, 0, 1)] : [new THREE.Vector3(22, 23, 31), new THREE.Vector3(-2, 0, -1)] };
let vol = null;
function allerVers(pos, cible, duree = 900) {
  vol = { de: camera.position.clone(), deC: controls.target.clone(), a: pos, aC: cible, t: performance.now(), duree };
}
function vue3d(nom) {
  if (!actif) return false;
  if (nom === "directeur") {
    const c = tetes[14];
    allerVers(new THREE.Vector3(c.x + 6, 6.5, c.z + 8), new THREE.Vector3(c.x, 1, c.z));
  } else allerVers(VUES.ensemble[0].clone(), VUES.ensemble[1].clone());
  return true;
}
function zoom3d(f) {
  if (!actif) return false;
  const v = camera.position.clone().sub(controls.target).multiplyScalar(1 / f);
  if (v.length() < controls.minDistance || v.length() > controls.maxDistance) return true;
  allerVers(controls.target.clone().add(v), controls.target.clone(), 350);
  return true;
}

function cliquer() {
  const ray = new THREE.Raycaster(), souris = new THREE.Vector2();
  let depart = null, survol = null;
  const viser = (e) => {
    const r = renderer.domElement.getBoundingClientRect();
    souris.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(souris, camera);
    const t = ray.intersectObjects(cliquables, false)[0];
    return t ? t.object.userData : null;
  };
  renderer.domElement.addEventListener("pointerdown", (e) => { depart = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener("pointerup", (e) => {
    if (!depart || Math.hypot(e.clientX - depart[0], e.clientY - depart[1]) > 6) { depart = null; return; }
    depart = null;
    const u = viser(e);
    if (u && u.agent) window.voirAgent(u.agent);
    else if (u && u.zone) window.ouvrirZone(u.zone);
  });
  renderer.domElement.addEventListener("pointermove", (e) => {
    if (e.buttons) return;
    const u = viser(e), cle = u ? (u.agent ? `a${u.agent}` : `z${u.zone}`) : null;
    renderer.domElement.style.cursor = cle ? "pointer" : "grab";
    if (cle === survol) return;
    survol = cle;
    for (const t of cliquables) if (t.userData.zone) t.material.emissive.setHex(u && u.zone === t.userData.zone ? 0x2a1d06 : 0x000000);
  });
}

function taille() {
  const r = conteneur.getBoundingClientRect();
  if (!r.width || !r.height) return;
  renderer.setSize(r.width, r.height); labels.setSize(r.width, r.height); composer.setSize(r.width, r.height);
  camera.aspect = r.width / r.height; camera.updateProjectionMatrix();
}

function boucle(t) {
  requestAnimationFrame(boucle);
  if (!actif || document.hidden) return;
  const s = (t - t0) / 1000;
  if (vol) {
    const k = Math.min(1, (t - vol.t) / vol.duree), e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
    camera.position.lerpVectors(vol.de, vol.a, e); controls.target.lerpVectors(vol.deC, vol.aC, e);
    if (k >= 1) vol = null;
  }
  controls.update();
  // seulement les agents réellement au travail bougent (frappe au clavier, halo qui pulse)
  for (const ps of Object.values(postes)) {
    if (ps.travail) {
      ps.corps.position.y = 0.98 + Math.sin(s * 3) * 0.012;
      ps.bras[0].rotation.x = -1.1 + Math.sin(s * 14) * 0.08; ps.bras[1].rotation.x = -1.1 + Math.sin(s * 14 + 2) * 0.08;
      const k = 1 + 0.15 * (0.5 + 0.5 * Math.sin(s * 4)); ps.anneau.scale.set(k, k, k);
    } else if (ps.anneau.scale.x !== 1) ps.anneau.scale.set(1, 1, 1);
  }
  for (const l of liens3d) l.point.position.copy(l.courbe.getPoint((s * 0.45) % 1));
  composer.render();
  labels.render(scene, camera);
}

function webglPossible() {
  try { const c = document.createElement("canvas"); return !!(window.WebGL2RenderingContext && c.getContext("webgl2")); } catch { return false; }
}

async function demarrer() {
  conteneur = document.getElementById("scene3d");
  if (!conteneur || new URLSearchParams(location.search).get("vue") === "plan" || !webglPossible()) return;
  plan = await (await fetch("/api/scene")).json();
  L = plan.sol.l; P = plan.sol.p;
  renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, telephone ? 1.75 : 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.2;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  conteneur.appendChild(renderer.domElement);
  labels = new CSS2DRenderer(); labels.domElement.className = "etiquettes3d"; conteneur.appendChild(labels.domElement);
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x04060b);
  scene.fog = new THREE.FogExp2(0x04060b, 0.011);
  const pm = new THREE.PMREMGenerator(renderer);
  scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.22;
  camera = new THREE.PerspectiveCamera(telephone ? 55 : 40, 1, 0.5, 300);
  camera.position.copy(VUES.ensemble[0]);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.target.copy(VUES.ensemble[1]);
  Object.assign(controls, { enableDamping: true, dampingFactor: 0.08, maxPolarAngle: 1.38, minDistance: 4, maxDistance: 85, screenSpacePanning: false });
  composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  composer.addPass(new UnrealBloomPass(new THREE.Vector2(512, 512), 0.5, 0.45, 0.9));
  composer.addPass(new OutputPass());
  materiaux(); salle(); lumieres();
  for (const z of plan.zones) { tapis(z); decor(z); }
  plante(0.5, 15); plante(47.5, 0.6); plante(29.6, 9.6); plante(18.4, 20.4); plante(47.5, 29.4); plante(0.5, 29.4);
  for (const p of plan.postes) poste(p);
  cliquer();
  new ResizeObserver(taille).observe(conteneur);
  pret = true;
  window.maj3d = maj3d; window.vue3d = vue3d; window.zoom3d = zoom3d;
  basculer(window.modePlateau ? window.modePlateau() : "bureau");
  if (window.etatCourant) maj3d(window.etatCourant(), null);
  requestAnimationFrame(boucle);
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
