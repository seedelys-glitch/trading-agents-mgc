"""
Agent d'alertes en CASCADE (méthode principale de Jabran, décision du 18/10/2026) :

  Weekly -> 12H -> 48 min -> 12 min. On ne descend d'un étage que si l'étage du dessus a un setup :
    1. setup Fibo + FVG en Weekly (le prix est venu sur une zone 0.618 / 0.705 / 0.786 / 0.893 avec un FVG)
    2. alors seulement : setup dans le même sens en 12H
    3. puis en 48 min
    4. puis l'ENTRÉE en 12 min : bougie de confirmation (mèche au-delà de la zone, corps posé dessus)
  JAMAIS le 0.5. Entrées seulement de 15h30 à 20h (Paris), en semaine.

Plan de trade (Bureau\\bot trad\\STRATEGIE.md, section « Gestion des trades ») calculé sur le Fibo du 12 min :
  - stop = haut du FVG de la zone + 20 % de sa hauteur (bas - 20 % pour un achat) ;
    sans FVG : 20 % de l'écart jusqu'à la zone suivante ;
  - objectifs : 0, -0.272, -1.272, -2.618 ; stop au 0.5 quand le -0.272 est touché, au 0 quand le -1.272 l'est.

Données : Yahoo (futur gold GC=F, ~10 min de retard) : weekly, 1H -> 12H, 2 min -> 48 min et 12 min
(alignés sur l'ouverture CME, 18h New York).

Déménagée de Jarvis vers le desk le 24/10/2026 (étape 3 du plan « Jarvis connecteur ») : la veille ne fait
qu'ÉCRIRE des événements (texte + plan calculé). Elle ne passe, ne prépare ni ne transmet aucun ordre ;
Jarvis lit les événements et les annonce. Aucun appel réseau sous verrou.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Callable

import requests

from .bougies import UA, Bar, atr, fmt_price, ny_offset_s, paris, plain, structure

log = logging.getLogger("veille")

LEVELS = (0.618, 0.705, 0.786, 0.893)   # zones de la stratégie (le 0.5 n'existe pas ici)
DEEPER = {0.618: 0.705, 0.705: 0.786, 0.786: 0.893, 0.893: 1.0}
TP_RATIOS = (0.0, -0.272, -1.272, -2.618)
STOP_MARGE = 0.20                # 20 % de la hauteur du FVG au-delà de son bord
FVG_TOL_ATR = 0.1                # le FVG doit toucher le niveau (à 0,1 ATR près)
FVG_MIN_ATR = 0.15               # un FVG minuscule ne compte pas
MIN_IMPULSE_ATR = 2.5            # « belle impulsion » : au moins 2,5 ATR de l'unité de temps
BAR_DELAY_S = 12 * 60            # retard de Yahoo : une bougie est « clôturée » 12 min après sa fin
CHECK_S = 60                     # un tour par minute

# étage : (nom, durée d'une bougie en s, pivots de chaque côté, nb de bougies max depuis la touche de la zone)
ETAGES = [
    ("Weekly", 7 * 86400, 2, 8),
    ("12H", 12 * 3600, 2, 10),
    ("48 min", 48 * 60, 3, 15),
    ("12 min", 12 * 60, 3, 0),     # dernier étage : l'entrée (bougie de confirmation)
]
RECHARGE_S = {"Weekly": 6 * 3600, "12H": 30 * 60, "48 min": 5 * 60, "12 min": 2 * 60}


# ---------------------------------------------------------------------------
# Bougies
# ---------------------------------------------------------------------------
def regroupe(bars: list[Bar], secondes: int) -> list[Bar]:
    """Bougies de `secondes` alignées sur l'ouverture CME (18h New York), à partir de bougies plus petites."""
    out: list[Bar] = []
    cle = None
    for b in bars:
        k = int((b.t + ny_offset_s(b.t) - 18 * 3600) // secondes)
        if k != cle:
            out.append(Bar(b.t, b.o, b.h, b.l, b.c))
            cle = k
        else:
            x = out[-1]
            x.h, x.l, x.c = max(x.h, b.h), min(x.l, b.l), b.c
    return out


def fermees(bars: list[Bar], secondes: int, now: float) -> list[Bar]:
    return [b for b in bars if b.t + secondes + BAR_DELAY_S <= now]


# ---------------------------------------------------------------------------
# Analyse d'un étage (sans réseau : testable)
# ---------------------------------------------------------------------------
def analyse_etage(bars: list[Bar], k: int, sens: str | None = None, fraicheur: int = 0) -> dict:
    """Dernière impulsion (jambe du dernier BOS, dans `sens` si donné), zones de Fibo avec FVG,
    et si le prix est venu sur une de ces zones (= setup de l'étage)."""
    out: dict = {"ok": False, "why": "", "setup": False}
    if len(bars) < 4 * k + 10:
        out["why"] = "pas assez de bougies"
        return out
    a14 = atr(bars)
    ev = structure(bars, k)
    if not ev:
        out["why"] = "pas de cassure de structure"
        return out
    dernier = ev[-1][0]
    if sens and dernier != sens:
        out["why"] = f"la structure est encore {dernier}"
        out["dernier_bos"] = dernier
        return out
    sens = sens or dernier
    up = sens == "haussier"
    _, ib, jpiv, _niv = [e for e in ev if e[0] == sens][-1]
    seg = range(jpiv, ib + 1)
    io = min(seg, key=lambda i: bars[i].l) if up else max(seg, key=lambda i: bars[i].h)
    apres = range(ib, len(bars))
    ie = max(apres, key=lambda i: bars[i].h) if up else min(apres, key=lambda i: bars[i].l)
    origin = bars[io].l if up else bars[io].h
    extreme = bars[ie].h if up else bars[ie].l
    a = a14[ie]
    out.update(sens=sens, origin=origin, extreme=extreme, io=io, ie=ie, atr=a14[-1],
               impulse_id=f"{int(bars[io].t)}-{int(bars[ie].t)}")
    if io >= ie:
        out["why"] = "impulsion illisible"
        return out
    if abs(extreme - origin) < MIN_IMPULSE_ATR * a:
        out["why"] = f"dernière impulsion trop petite ({abs(extreme - origin) / a:.1f} ATR)"
        return out
    if any((b.c < origin) if up else (b.c > origin) for b in bars[ie:]):
        out["why"] = "l'impulsion a été effacée"
        return out
    fvgs = []
    for j in range(io + 1, ie):
        p, n = bars[j - 1], bars[j + 1]
        if up and n.l - p.h >= FVG_MIN_ATR * a:
            fvgs.append((p.h, n.l))
        elif not up and p.l - n.h >= FVG_MIN_ATR * a:
            fvgs.append((n.h, p.l))
    tol = FVG_TOL_ATR * a
    zones = []
    for L in LEVELS:
        prix = extreme + L * (origin - extreme)
        hit = [f for f in fvgs if f[0] - tol <= prix <= f[1] + tol]
        if hit:
            zones.append({"L": L, "prix": prix, "fvg": hit[0]})
    out.update(zones=zones, ok=bool(zones), tol=tol)
    if not zones:
        out["why"] = "aucun FVG sur les zones de Fibo"
        return out
    # la zone la plus profonde touchée après l'extrême (setup de l'étage)
    touche, quand = None, None
    for i in range(ie + 1, len(bars)):
        for z in zones:
            if (bars[i].l <= z["prix"] + tol) if up else (bars[i].h >= z["prix"] - tol):
                if touche is None or z["L"] > touche["L"]:
                    touche, quand = z, i
    out["touche"] = touche
    if touche is None:
        out["why"] = "le prix n'est pas encore venu sur une zone"
        return out
    if fraicheur and len(bars) - 1 - quand > fraicheur:
        out["why"] = "zone touchée il y a trop longtemps"
        return out
    out.update(setup=True, quand=bars[quand].t, why="")
    return out


def confirmation(st: dict, bar: Bar, z: dict) -> bool:
    """Bougie dont la mèche dépasse la zone et dont le corps se pose dessus."""
    a, L = st["atr"], z["prix"]
    bas_corps, haut_corps = min(bar.o, bar.c), max(bar.o, bar.c)
    if st["sens"] == "haussier":
        return bar.l < L - 0.05 * a and bas_corps >= L - 0.1 * a and bas_corps <= L + 0.35 * a
    return bar.h > L + 0.05 * a and haut_corps <= L + 0.1 * a and haut_corps >= L - 0.35 * a


def plan_trade(sens: str, origin: float, extreme: float, L: float, fvg: tuple[float, float] | None) -> dict:
    """Entrée, stop, objectifs et déplacements de stop (règles du 18/10/2026)."""
    up = sens == "haussier"
    r = lambda x: extreme + x * (origin - extreme)  # noqa: E731  prix d'un niveau de Fibo
    entree = r(L)
    if fvg:
        bas, haut = fvg
        h = haut - bas
        # bord du FVG (ou l'entrée si elle est au-delà du FVG) + 20 % de la hauteur du FVG
        stop = min(bas, entree) - STOP_MARGE * h if up else max(haut, entree) + STOP_MARGE * h
        regle = "FVG + 20 %"
    else:
        ecart = abs(r(DEEPER[L]) - entree)
        stop = entree - STOP_MARGE * ecart if up else entree + STOP_MARGE * ecart
        regle = "20 % de l'écart jusqu'à la zone suivante"
    return {
        "sens": sens, "niveau": L, "entree": entree, "stop": stop, "regle_stop": regle,
        "objectifs": [{"ratio": x, "prix": r(x)} for x in TP_RATIOS],
        "stop_au_05": {"declencheur": r(-0.272), "nouveau_stop": r(0.5)},
        "stop_au_0": {"declencheur": r(-1.272), "nouveau_stop": r(0.0)},
        "origin": origin, "extreme": extreme,
    }


def dans_fenetre(t: float) -> bool:
    d = paris(t)
    m = d.hour * 60 + d.minute
    return d.weekday() < 5 and 15 * 60 + 30 <= m < 20 * 60


# ---------------------------------------------------------------------------
class Cascade:
    def __init__(self, dossier: Path, emettre: Callable[[dict], None] | None = None):
        """dossier : où garder l'état ; emettre(evenement) reçoit chaque nouvel événement (une seule fois)."""
        self.emettre = emettre or (lambda e: None)
        self.state_file = Path(dossier) / "cascade-etat.json"
        self.lock = threading.Lock()
        self.bars: dict[str, list[Bar]] = {}
        self.bars_t: dict[str, float] = {}
        self.etat: dict = {"etage": 0, "etages": [], "maj": 0}
        self.dernier_plan: dict | None = None
        self.state = self._load()
        self.erreur = ""
        self.tours = 0

    # ------------------------------------------------------------------ état gardé
    def _load(self) -> dict:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return {"off": False, "sent": [], "checked": {}}

    def _save(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state["sent"] = self.state.get("sent", [])[-300:]
            self.state_file.write_text(json.dumps(self.state), encoding="utf-8")
        except OSError:
            pass

    def enabled(self) -> bool:
        return not self.state.get("off")

    def set_enabled(self, on: bool) -> str:
        with self.lock:
            self.state["off"] = not on
            self._save()
        return ("Cascade active : je cherche tes setups en Weekly, puis 12H, 48 min et 12 min." if on else
                "Cascade coupée. Dis « remets la cascade » pour la relancer.")

    # ------------------------------------------------------------------ données
    def _yahoo(self, interval: str, rng: str) -> list[Bar]:
        for sym in ("GC=F", "MGC=F"):
            try:
                r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                                 params={"interval": interval, "range": rng}, headers=UA, timeout=20)
                r.raise_for_status()
                res = r.json()["chart"]["result"][0]
                q = res["indicators"]["quote"][0]
                bars = [Bar(float(t), float(o), float(h), float(l), float(c)) for t, o, h, l, c in
                        zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"])
                        if None not in (o, h, l, c)]
                if len(bars) > 20:
                    return bars
            except Exception as e:
                log.debug("Cascade : bougies %s %s indisponibles (%s)", sym, interval, e)
        return []

    def _charge(self, nom: str, now: float) -> list[Bar]:
        if self.bars.get(nom) and now - self.bars_t.get(nom, 0) < RECHARGE_S[nom]:
            return self.bars[nom]
        if nom == "Weekly":
            b = self._yahoo("1wk", "5y")
        elif nom == "12H":
            b = regroupe(self._yahoo("60m", "1y"), 12 * 3600)
        elif nom == "48 min":
            b = regroupe(self._yahoo("2m", "30d"), 48 * 60)
        else:
            b = regroupe(self._yahoo("2m", "5d"), 12 * 60)
        if b:
            self.bars[nom], self.bars_t[nom] = b, now
        return self.bars.get(nom, [])

    # ------------------------------------------------------------------ un tour
    def analyse(self, now: float | None = None) -> dict:
        """Descend la cascade et renvoie l'état (sans rien envoyer)."""
        now = now or time.time()
        etages, sens = [], None
        for nom, sec, k, fraicheur in ETAGES[:3]:
            brutes = self._charge(nom, now)
            # semaine en cours : pas finie, donc pas comptée ; ailleurs, seulement les bougies clôturées
            bars = brutes[:-1] if nom == "Weekly" else fermees(brutes, sec, now)
            st = analyse_etage(bars, k, sens, fraicheur)
            st["nom"] = nom
            etages.append(st)
            if not st.get("setup"):
                break
            sens = st["sens"]
        etat = {"etages": etages, "etage": sum(1 for e in etages if e.get("setup")), "maj": now,
                "sens": sens, "entree": None}
        if etat["etage"] == 3:  # Weekly + 12H + 48 min : on cherche l'entrée en 12 min
            bars12 = fermees(self._charge("12 min", now), 12 * 60, now)
            st = analyse_etage(bars12, ETAGES[3][2], sens, 0)
            st["nom"] = "12 min"
            etages.append(st)
            if st.get("ok") and bars12 and len(bars12) - 1 > st["ie"]:
                bar = bars12[-1]
                for z in sorted(st["zones"], key=lambda z: -z["L"]):
                    if confirmation(st, bar, z):
                        plan = plan_trade(sens, st["origin"], st["extreme"], z["L"], z["fvg"])
                        plan.update(t_bougie=bar.t, cle=f"entree-{st['impulse_id']}-{z['L']}-{int(bar.t)}")
                        etat["entree"] = plan
                        break
        self.etat = etat
        return etat

    def check(self, now: float | None = None) -> None:
        now = now or time.time()
        self.tours += 1
        if not self.enabled():
            return
        etat = self.analyse(now)
        # 1) un message par nouvel étage atteint (setup trouvé)
        for i, st in enumerate(etat["etages"][:3]):
            if not st.get("setup"):
                break
            z = st["touche"]
            cle = f"etage-{st['nom']}-{st['impulse_id']}-{z['L']}"
            suite = ETAGES[i + 1][0]
            sens = "baissier" if st["sens"] == "baissier" else "haussier"
            self._envoie(cle, "etage", f"Cascade : setup {sens} en {st['nom']} sur le {z['L']} "
                                       f"({fmt_price(z['prix'])}) avec un FVG. Je surveille maintenant le {suite}.")
        # 2) l'entrée en 12 min
        plan = etat.get("entree")
        if plan and plan["cle"] not in self.state.get("sent", []):
            if not dans_fenetre(plan["t_bougie"] + 12 * 60):
                self._envoie(plan["cle"], "hors_fenetre", f"Cascade : entrée 12 min sur le {plan['niveau']}, mais "
                                                          "hors de ta fenêtre 15h30-20h : pas de trade.")
            else:
                self.dernier_plan = dict(plan, quand=now)
                cote = "vente" if plan["sens"] == "baissier" else "achat"
                self._envoie(plan["cle"], "entree", f"Cascade complète Weekly, 12H, 48 min, 12 min : entrée à la "
                                                    f"{cote} sur le {plan['niveau']} ({fmt_price(plan['entree'])}). "
                                                    f"Stop {fmt_price(plan['stop'])}.", plan)

    def _envoie(self, cle: str, genre: str, texte: str, plan: dict | None = None) -> None:
        with self.lock:
            if cle in self.state.get("sent", []):
                return
            self.state.setdefault("sent", []).append(cle)
            self._save()
        log.info("%s", texte)
        evt = {"cle": cle, "source": "cascade", "type": genre, "texte": texte}
        if plan:
            evt["plan"] = dict(plan)
        try:
            self.emettre(evt)
        except Exception as e:
            log.warning("Cascade : événement non écrit (%s)", e)

    def loop(self) -> None:
        while True:
            try:
                self.check()
                self.erreur = ""
            except Exception as e:
                self.erreur = repr(e)[:200]
                log.warning("Cascade : %s", e)
            time.sleep(CHECK_S)

    def start(self) -> None:
        threading.Thread(target=self.loop, daemon=True, name="cascade").start()

    # ------------------------------------------------------------------ texte et commandes
    def etat_phrase(self) -> str:
        etat = self.etat if self.etat.get("maj") else self.analyse()
        morceaux = []
        for st in etat["etages"]:
            if st.get("setup"):
                z = st["touche"]
                morceaux.append(f"{st['nom']} : setup {st['sens']} sur le {z['L']} à {fmt_price(z['prix'])}")
            elif st["nom"] == "12 min" and st.get("ok"):
                zs = ", ".join(f"{z['L']} à {fmt_price(z['prix'])}" for z in st["zones"])
                morceaux.append(f"12 min : zones d'entrée possibles {zs}, j'attends la bougie de confirmation")
            else:
                morceaux.append(f"{st['nom']} : pas de setup ({st.get('why') or 'rien'})")
                break
        txt = "Cascade. " + ". ".join(morceaux) + "."
        if not self.enabled():
            txt += " Les alertes de la cascade sont coupées."
        return txt

    def resume(self) -> dict:
        """Pour l'appli et le chef d'orchestre (sans réseau)."""
        out = []
        for st in self.etat.get("etages", []):
            out.append({"nom": st.get("nom"), "setup": bool(st.get("setup")), "sens": st.get("sens"),
                        "pourquoi": st.get("why", ""),
                        "zone": ({"niveau": st["touche"]["L"], "prix": round(st["touche"]["prix"], 2)}
                                 if st.get("touche") and st.get("setup") else None)})
        return {"etage": self.etat.get("etage", 0), "etages": out, "maj": self.etat.get("maj", 0),
                "actif": self.enabled(), "erreur": self.erreur}

    @staticmethod
    def wants(c: str) -> bool:
        t = plain(c)
        return bool(re.search(r"(?<![a-z])cascade", t))

    def handle(self, c: str) -> str | None:
        if not self.wants(c):
            return None
        t = plain(c)
        if re.search(r"(?<![a-z])(coupe|desactive|arrete|stop)", t):
            return self.set_enabled(False)
        if re.search(r"(?<![a-z])(remets|active|reactive|relance|rallume|remet)", t):
            return self.set_enabled(True)
        return self.etat_phrase()
