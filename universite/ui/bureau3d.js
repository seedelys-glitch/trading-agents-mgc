// Bureau 3D (WebGL, three.js en copie locale) : même plan que la vue 2,5D (/api/scene), même état réel (/api/etat).
// Ambiance « grande salle de marché au soleil couchant » : la lumière du soir entre vraiment par les fenêtres des
// murs (ombres portées), lustres, lampes de banquier, marbre ciré, bois verni, tapis de velours.
// Mais rien ne bouge sans une mission réellement en cours, un poste « en construction » reste vide et éteint, les
// arcs lumineux sont de vrais messages entre agents et l'horloge donne l'heure réelle.
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
let image = 0;

let plan, L, P, renderer, scene, camera, controls, composer, labels, conteneur, pret = false, actif = false;
const postes = {}, cliquables = [], tetes = {};
let liens3d = [], dernierLiens = "", t0 = performance.now(), poussiere = null, horloge = null;

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
    const motif = (x, y, s) => {
      c.save(); c.translate(x, y); c.scale(s, s);
      c.strokeStyle = "rgba(190,160,95,.16)"; c.fillStyle = "rgba(190,160,95,.07)"; c.lineWidth = 2;
      for (let k = 0; k < 4; k++) {
        c.rotate(Math.PI / 2); c.beginPath(); c.moveTo(0, 0);
        c.bezierCurveTo(18, -20, 34, -6, 30, 22); c.bezierCurveTo(22, 8, 10, 6, 0, 0); c.fill(); c.stroke();
      }
      c.beginPath(); c.arc(0, 0, 5, 0, 7); c.fill(); c.restore();
    };
    motif(w / 2, h / 2, 1.6); motif(0, 0, 1.6); motif(w, 0, 1.6); motif(0, h, 1.6); motif(w, h, 1.6);
  }, true);
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
  // lustres de cristal au-dessus de chaque pièce
  const anneau = new THREE.TorusGeometry(1, 0.045, 10, 48), petit = new THREE.TorusGeometry(0.55, 0.035, 8, 32);
  const bougie = new THREE.SphereGeometry(0.075, 10, 8), pampille = new THREE.OctahedronGeometry(0.06, 0);
  for (const z of plan.zones) {
    const c = P3(z.x + z.l / 2, z.y + z.p / 2, 6.4), fort = z.cle === "directeur";
    const l = new THREE.PointLight(0xffc27a, fort ? 34 : 22, 18, 1.8); l.position.copy(c).add(new THREE.Vector3(0, -0.3, 0)); scene.add(l);
    const g = new THREE.Group(); g.position.copy(c);
    for (const [geo, y, r] of [[anneau, 0, 1], [petit, 0.55, 0.55]]) {
      const a = new THREE.Mesh(geo, M.or); a.rotation.x = Math.PI / 2; a.position.y = y; g.add(a);
      const n = r > 0.7 ? 12 : 8;
      for (let k = 0; k < n; k++) {
        const ang = (k / n) * Math.PI * 2;
        const b = new THREE.Mesh(bougie, M.ampoule); b.position.set(Math.cos(ang) * r, y + 0.16, Math.sin(ang) * r); g.add(b);
        const p = new THREE.Mesh(pampille, M.cristal); p.scale.set(1, 2.2, 1); p.position.set(Math.cos(ang + 0.2) * r, y - 0.2, Math.sin(ang + 0.2) * r); g.add(p);
      }
    }
    const tige = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, MUR + 1 - c.y, 6), M.or); tige.position.y = (MUR + 1 - c.y) / 2; g.add(tige);
    const coupe = new THREE.Mesh(new THREE.SphereGeometry(0.28, 16, 10, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2), M.or); coupe.position.y = -0.1; g.add(coupe);
    scene.add(g);
    flaque(c.x, 0.03, c.z, fort ? 13 : 11, 0xffb060, 0.1);
  }
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
  const t = new THREE.Mesh(new THREE.BoxGeometry(z.l - 0.5, 0.025, z.p - 0.5), m);
  t.position.copy(P3(z.x + z.l / 2, z.y + z.p / 2, 0.013)); t.receiveShadow = true;
  t.userData = { zone: z.cle };
  scene.add(t); cliquables.push(t);
  const d = document.createElement("div");
  d.className = "nom-zone3d"; d.textContent = z.nom; d.tabIndex = 0;
  d.addEventListener("click", () => window.ouvrirZone(z.cle));
  const o = new CSS2DObject(d); o.position.copy(P3(z.x + z.l / 2, z.y + z.p - 0.2, 0.05)); o.center.set(0.5, -0.4);
  scene.add(o);
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

function bibliothequeMeuble(cx, cz, angle, largeur, graine) {
  const g = new THREE.Group(); g.position.set(cx, 0, cz); g.rotation.y = angle;
  const H = 3.2, etages = 6;
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
    for (let k = 0; k < 4; k++) bibliothequeMeuble(P3(z.x + 2.2 + k * 3.9, 0).x, P3(0, z.y + 0.55).z, 0, 3.4, 11 + k);
    // échelle de bibliothèque
    const e = new THREE.Group(); e.position.copy(P3(z.x + 6.1, z.y + 1.05)); e.rotation.x = -0.25;
    for (const s of [-0.25, 0.25]) e.add(boite(0.05, 3.3, 0.06, M.bois, s, 1.6, 0));
    for (let k = 0; k < 9; k++) e.add(boite(0.5, 0.035, 0.05, M.laiton, 0, 0.3 + k * 0.35, 0));
    scene.add(e);
    // table de lecture, lampes de banquier, fauteuils club
    const t = P3(z.x + 11.8, z.y + 9.3);
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
    const tb = P3(z.x + 3, z.y + 0.7);
    const tableau = new THREE.Group(); tableau.position.copy(tb);
    tableau.add(boite(4.2, 2.1, 0.03, phy({ color: 0xdfe8f0, roughness: 0.05, transparent: true, opacity: 0.25, clearcoat: 1 }), 0, 1.75, 0, false));
    for (const s of [-2.15, 2.15]) tableau.add(cyl(0.03, 0.03, 2.9, M.chrome, s, 1.45, 0, 10));
    tableau.add(boite(4.2, 0.03, 0.08, M.chrome, 0, 0.7, 0.04));
    scene.add(tableau);
    plante(z.x + 0.7, z.y + 7.4, 1.2);
  } else if (z.cle === "donnees") {
    const face = std({ map: T.led, emissive: 0xffffff, emissiveMap: T.led, emissiveIntensity: 1.2, roughness: 0.25 });
    for (let k = 0; k < 3; k++) {
      const b = P3(z.x + 1.3 + k * 1.7, z.y + 1.3);
      const baie = new THREE.Mesh(new RoundedBoxGeometry(1.05, 2.3, 1.2, 2, 0.03), M.noir); baie.position.set(b.x, 1.15, b.z); ombre(baie); scene.add(baie);
      const vitre = new THREE.Mesh(new THREE.PlaneGeometry(0.9, 2.1), face); vitre.position.set(b.x, 1.15, b.z + 0.61); scene.add(vitre);
      const h = new THREE.Mesh(new THREE.PlaneGeometry(2, 1.6), M.halo(0x3d7bd6, 0.18)); h.rotation.x = -Math.PI / 2; h.position.set(b.x, 0.03, b.z + 1.3); scene.add(h);
    }
    const froid = new THREE.PointLight(0x4d86ff, 10, 7, 2); froid.position.copy(P3(z.x + z.l / 2, z.y + 3, 2.4)); scene.add(froid);
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
    bibliothequeMeuble(c.x, c.z - z.p / 2 + 1.25, 0, 4.2, 99);
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
    for (const dx of [-0.6, 0.6]) fauteuil(c.x + dx, c.z + 1.0, Math.PI, 0.3, M.cuirNoir);
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
  horloge = { c, tex, minute: -1 };
  dessinerHorloge();
}
function dessinerHorloge() {
  if (!horloge) return;
  const d = new Date(), m = d.getHours() * 60 + d.getMinutes();
  if (m === horloge.minute) return;
  horloge.minute = m;
  const x = horloge.c.getContext("2d"), w = 256, r = 120;
  x.fillStyle = "#f3ead2"; x.fillRect(0, 0, w, w);
  x.translate(w / 2, w / 2);
  x.fillStyle = "#2a2118"; x.font = "600 30px Georgia, serif"; x.textAlign = "center"; x.textBaseline = "middle";
  ["XII", "III", "VI", "IX"].forEach((t, k) => { const a = k * Math.PI / 2; x.fillText(t, Math.sin(a) * (r - 30), -Math.cos(a) * (r - 30)); });
  for (let k = 0; k < 60; k++) { const a = k * Math.PI / 30, l = k % 5 ? 6 : 14; x.fillRect(Math.sin(a) * (r - 6) - 1, -Math.cos(a) * (r - 6) - 1, 2, 2); if (!(k % 5)) { x.beginPath(); x.moveTo(Math.sin(a) * (r - 4), -Math.cos(a) * (r - 4)); x.lineTo(Math.sin(a) * (r - 4 - l), -Math.cos(a) * (r - 4 - l)); x.lineWidth = 3; x.strokeStyle = "#2a2118"; x.stroke(); } }
  const aiguille = (a, l, e) => { x.beginPath(); x.moveTo(0, 0); x.lineTo(Math.sin(a) * l, -Math.cos(a) * l); x.lineWidth = e; x.lineCap = "round"; x.strokeStyle = "#1a140e"; x.stroke(); };
  aiguille(((d.getHours() % 12) + d.getMinutes() / 60) * Math.PI / 6, r * 0.5, 7);
  aiguille(d.getMinutes() * Math.PI / 30, r * 0.78, 4);
  x.beginPath(); x.arc(0, 0, 7, 0, 7); x.fillStyle = "#b8892f"; x.fill();
  x.setTransform(1, 0, 0, 1, 0, 0);
  horloge.tex.needsUpdate = true;
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
  const tag = new CSS2DObject(d); tag.position.copy(P3(p.x, p.y, y0 + 2.3)); scene.add(tag);
  for (const o of [g, agent]) o.traverse((m) => { if (m.isMesh) { m.userData.agent = p.agent; cliquables.push(m); } });
  postes[p.agent] = { g, agent, corps: pers.haut, bras: pers.bras, anneau, vitre, e, tag: d, cle: "", statut: "", y0, travail: false };
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
    const col = new THREE.Color(couleur[l.genre] || 0xd4a64a);
    const m = new THREE.MeshBasicMaterial({ color: col.clone().multiplyScalar(1.6), toneMapped: false, transparent: true, opacity: 0.7 });
    const mesh = new THREE.Mesh(new THREE.TubeGeometry(courbe, 64, 0.022, 6, false), m);
    const point = new THREE.Mesh(new THREE.SphereGeometry(0.09, 12, 8), new THREE.MeshBasicMaterial({ color: col.clone().multiplyScalar(3), toneMapped: false }));
    scene.add(mesh, point);
    liens3d.push({ mesh, point, courbe });
  }
}

// ------------------------------------------------------------------ caméra, clics, rendu
const VUES = { ensemble: telephone ? [new THREE.Vector3(16, 26, 30), new THREE.Vector3(0, 0, 1)] : [new THREE.Vector3(22, 21, 30), new THREE.Vector3(-2, 0, -2)] };
let vol = null;
function allerVers(pos, cible, duree = 900) {
  vol = { de: camera.position.clone(), deC: controls.target.clone(), a: pos, aC: cible, t: performance.now(), duree };
}
function vue3d(nom) {
  if (!actif) return false;
  if (nom === "directeur") {
    const c = tetes[14];
    allerVers(new THREE.Vector3(c.x + 5, 5, c.z + 7), new THREE.Vector3(c.x, 1, c.z - 0.5));
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

// étalonnage final : vignette et léger grain (cinéma)
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
  if (camera3d && (image++ & 1)) return;
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
  if (grain) grain.uniforms.temps.value = s % 10;
  if (image % 120 === 0) dessinerHorloge();
  if (!camera3d) image++;
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
  renderer.setPixelRatio(camera3d ? 1 : Math.min(window.devicePixelRatio, telephone ? 1.75 : 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
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
  if (camera3d) {   // la caméra tourne seule ; si on la prend en main, elle reprend sa ronde 20 s après
    let reprise = null;
    Object.assign(controls, { autoRotate: true, autoRotateSpeed: 0.35 });
    controls.addEventListener("start", () => { controls.autoRotate = false; clearTimeout(reprise); });
    controls.addEventListener("end", () => { reprise = setTimeout(() => { controls.autoRotate = true; }, 20000); });
  }
  // rendu : anticrénelage (MSAA), halo lumineux, étalonnage
  const cible = new THREE.WebGLRenderTarget(16, 16, { type: THREE.HalfFloatType, samples: LEGER ? 2 : 4 });
  composer = new EffectComposer(renderer, cible);
  composer.addPass(new RenderPass(scene, camera));
  composer.addPass(new UnrealBloomPass(new THREE.Vector2(512, 512), 0.36, 0.5, 0.9));
  composer.addPass(new OutputPass());
  grain = new ShaderPass(ETALONNAGE); composer.addPass(grain);
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
