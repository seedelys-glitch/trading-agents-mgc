"""
Alertes de la stratégie 1H / 12H (déménagées de Jarvis vers la veille du desk le 24/10/2026) :
  1. bougies 1H du futur gold COMEX (Yahoo GC=F, ~10 min de retard), 12H reconstituées (séances CME) ;
  2. BIAIS : dernier BOS en 12H ET en 1H dans le même sens + EMA 200 (1H) qui va dans ce sens ;
  3. dernière IMPULSION (au moins 3 ATR) ; FIBO 0.618 / 0.705 / 0.786 / 0.893 avec un FVG dessus ; JAMAIS le 0.5 ;
  4. « zone » : le prix arrive à moins de 0,3 ATR d'un niveau valable ;
  5. « confirmation » : bougie 1H clôturée, mèche au-delà du niveau, corps posé dessus ;
  6. semaine, entrée entre 15h30 et 20h (Paris).
OBSERVE_ONLY (comme dans Jarvis depuis le 18/10 : la cascade est la méthode principale) : calcule et note dans
veille.log sans rien annoncer. Sinon : un événement par alerte (Jarvis l'annonce). Aucun ordre.
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

from .bougies import UA, Bar, atr, ema, fmt_price, paris, plain, structure, to_12h

log = logging.getLogger("veille")

LEVELS = (0.618, 0.705, 0.786, 0.893)   # zones de Fibo de la stratégie (le 0.5 n'existe pas ici)
DEEPER = {0.618: 0.705, 0.705: 0.786, 0.786: 0.893, 0.893: 1.0}  # « zone juste au-dessus » pour le stop
PIVOT_1H, PIVOT_12H = 3, 2       # un sommet/creux = plus haut/bas que les 3 (ou 2) bougies de chaque côté
MIN_IMPULSE_ATR = 3.0            # « belle impulsion » : au moins 3 ATR (1H)
NEAR_ATR = 0.3                   # « le prix arrive sur la zone » : à moins de 0,3 ATR
FVG_TOL_ATR = 0.1                # le FVG doit toucher le niveau (à 0,1 ATR près)
FVG_MIN_ATR = 0.15               # un « FVG » de quelques centimes ne compte pas : au moins 0,15 ATR
CHECK_S = 120                    # vérification toutes les 2 min (boucle de service.py)
BARS_EVERY_S = 300               # bougies relues toutes les 5 min
BAR_DELAY_S = 12 * 60            # Yahoo a ~10 min de retard : une bougie est « clôturée » 12 min après

OBSERVE_ONLY = True              # True : calcule et note dans le log, sans prévenir (phase de vérification)



def analyze(bars1h: list[Bar], now: float) -> dict:
    """Biais, impulsion, niveaux de Fibo valables (avec FVG) à partir des bougies 1H CLÔTURÉES."""
    closed = [b for b in bars1h if b.t + 3600 + BAR_DELAY_S <= now]
    out: dict = {"ok": False, "why": "", "closed": closed}
    if len(closed) < 230:
        out["why"] = "pas assez de bougies 1H"
        return out
    closes = [b.c for b in closed]
    e200 = ema(closes, 200)
    atr14 = atr(closed)
    ev1 = structure(closed, PIVOT_1H)
    h12 = to_12h(closed)
    ev12 = structure(h12, PIVOT_12H)
    t1 = ev1[-1][0] if ev1 else None
    t12 = ev12[-1][0] if ev12 else None
    slope = e200[-1] - e200[-25]
    ema_dir = "haussier" if slope > 0 else "baissier"
    pos = "au-dessus" if closes[-1] > e200[-1] else "sous"
    out.update(trend_1h=t1, trend_12h=t12, ema=e200[-1], ema_dir=ema_dir, ema_pos=pos, atr=atr14[-1],
               last=closes[-1])
    if not (t1 and t12 and t1 == t12 == ema_dir):
        out["why"] = "pas de biais clair"
        return out
    bias = t1
    up = bias == "haussier"
    # la jambe qui a fait le dernier BOS 1H dans le sens du biais
    last = [e for e in ev1 if e[0] == bias][-1]
    _, ib, jpiv, _lvl = last
    seg = range(jpiv, ib + 1)
    io = min(seg, key=lambda i: closed[i].l) if up else max(seg, key=lambda i: closed[i].h)
    after = range(ib, len(closed))
    ie = max(after, key=lambda i: closed[i].h) if up else min(after, key=lambda i: closed[i].l)
    origin = closed[io].l if up else closed[io].h
    extreme = closed[ie].h if up else closed[ie].l
    a = atr14[ie]
    out.update(bias=bias, io=io, ie=ie, origin=origin, extreme=extreme, size=abs(extreme - origin),
               atr_at=a, impulse_id=f"{int(closed[io].t)}-{int(closed[ie].t)}")
    if io >= ie:
        out["why"] = "impulsion illisible"
        return out
    if abs(extreme - origin) < MIN_IMPULSE_ATR * a:
        out["why"] = f"dernière impulsion trop petite ({abs(extreme - origin) / a:.1f} ATR)"
        return out
    # impulsion cassée (le prix est revenu au-delà de son départ) : plus de setup
    if any((b.c < origin) if up else (b.c > origin) for b in closed[ie:]):
        out["why"] = "l'impulsion a été entièrement effacée"
        return out
    # FVG de l'impulsion (dans son sens)
    fvgs = []
    for j in range(io + 1, ie):
        p, n = closed[j - 1], closed[j + 1]
        if up and n.l - p.h >= FVG_MIN_ATR * a:
            fvgs.append((p.h, n.l))
        elif not up and p.l - n.h >= FVG_MIN_ATR * a:
            fvgs.append((n.h, p.l))
    levels = []
    tol = FVG_TOL_ATR * a
    for L in LEVELS:
        price = extreme + L * (origin - extreme)
        hit = [f for f in fvgs if f[0] - tol <= price <= f[1] + tol]
        levels.append({"L": L, "price": price, "fvg": hit[0] if hit else None})
    valid = [lv for lv in levels if lv["fvg"]]
    out.update(fvgs=fvgs, levels=levels, valid=valid, ok=bool(valid),
               why="" if valid else "aucun FVG sur les zones de Fibo")
    return out


def trade_plan(st: dict, lv: dict) -> dict:
    """Stop, TP1, TP2, break-even pour une entrée sur ce niveau (règles de STRATEGIE.md)."""
    up = st["bias"] == "haussier"
    o, e = st["origin"], st["extreme"]
    deeper = e + DEEPER[lv["L"]] * (o - e)
    fvg_far = lv["fvg"][0] if up else lv["fvg"][1]
    stop = min(fvg_far, deeper) if up else max(fvg_far, deeper)
    tp1 = e
    tp2 = e - 0.618 * (o - e)
    be = lv["price"] + 0.35 * (tp1 - lv["price"])
    return {"stop": stop, "tp1": tp1, "tp2": tp2, "be": be}


def confirmation(st: dict, bar: Bar, lv: dict) -> bool:
    """Bougie 1H dont la mèche dépasse le niveau et dont le corps se pose dessus."""
    a, L = st["atr"], lv["price"]
    lo_body, hi_body = min(bar.o, bar.c), max(bar.o, bar.c)
    if st["bias"] == "haussier":
        return bar.l < L - 0.05 * a and lo_body >= L - 0.1 * a and lo_body <= L + 0.35 * a
    return bar.h > L + 0.05 * a and hi_body <= L + 0.1 * a and hi_body >= L - 0.35 * a


def in_window(t_entry: float) -> bool:
    d = paris(t_entry)
    minutes = d.hour * 60 + d.minute
    return d.weekday() < 5 and 15 * 60 + 30 <= minutes < 20 * 60  # 15h30-20h, heure de Paris


class Strategie1H:
    def __init__(self, dossier: Path, emettre: Callable[[dict], None] | None = None):
        self.emettre = emettre or (lambda e: None)
        self.state_file = Path(dossier) / "strategie-etat.json"
        self.journal = Path(dossier) / "alertes-strategie.csv"
        self.lock = threading.Lock()
        self.bars: list[Bar] = []
        self.bars_t = 0.0
        self.prix: float | None = None   # dernier prix donné par Yahoo avec les bougies
        self.last: dict = {}
        self.state = self._load()
        self._last_why = None
        self._observed: set[str] = set()
        self.erreur = ""
        self.tours = 0

    # ------------------------------------------------------------------ état gardé
    def _load(self) -> dict:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return {"off": False, "sent": [], "checked_bar": 0}

    def _save(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state["sent"] = self.state.get("sent", [])[-200:]
            self.state_file.write_text(json.dumps(self.state), encoding="utf-8")
        except OSError:
            pass

    def enabled(self) -> bool:
        return not self.state.get("off")

    def set_enabled(self, on: bool) -> str:
        with self.lock:
            self.state["off"] = not on
            self._save()
        return ("Alertes de stratégie actives : je te préviens quand le gold arrive sur une zone de Fibo avec un FVG, "
                "puis à la bougie de confirmation." if on else
                "Alertes de stratégie coupées. Dis « remets les alertes de stratégie » pour les relancer.")

    # ------------------------------------------------------------------ données
    def fetch_bars(self) -> list[Bar]:
        for sym in ("GC=F", "MGC=F"):
            try:
                r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                                 params={"interval": "60m", "range": "60d"}, headers=UA, timeout=15)
                r.raise_for_status()
                res = r.json()["chart"]["result"][0]
                q = res["indicators"]["quote"][0]
                bars = [Bar(float(t), float(o), float(h), float(l), float(c)) for t, o, h, l, c in
                        zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"])
                        if None not in (o, h, l, c)]
                if len(bars) > 100:
                    p = (res.get("meta") or {}).get("regularMarketPrice")
                    self.prix = float(p) if p else bars[-1].c
                    return bars
            except Exception as e:
                log.debug("Stratégie : bougies %s indisponibles (%s)", sym, e)
        return []

    def _bougies(self, now: float) -> None:
        if now - self.bars_t >= BARS_EVERY_S or not self.bars:
            bars = self.fetch_bars()
            if bars:
                self.bars, self.bars_t = bars, now

    # ------------------------------------------------------------------ texte
    def state_phrase(self) -> str:
        """Sans réseau : lit le dernier calcul de la boucle."""
        st = self.last
        if not st:
            if self.tours and not self.bars:
                return "Je n'arrive pas à récupérer les bougies du gold pour le moment."
            return "La stratégie 1H n'a pas encore fait son premier calcul. Redemande dans deux minutes."
        if "trend_1h" not in st:
            return "Pas assez de bougies pour lire la stratégie."
        price = self.prix or st["last"]
        out = (f"Structure : {st['trend_12h'] or 'pas de BOS'} en 12H, {st['trend_1h'] or 'pas de BOS'} en 1H, "
               f"EMA 200 {'montante' if st['ema_dir'] == 'haussier' else 'descendante'}, "
               f"prix {st['ema_pos']} à {fmt_price(st['ema'])}. ")
        if "bias" not in st:
            return out + "Pas de biais clair : pas d'alerte pour l'instant."
        out += (f"Biais {st['bias']}. Dernière impulsion de {fmt_price(st['origin'])} à {fmt_price(st['extreme'])}. ")
        if not st["ok"]:
            return out + f"Pas de zone valable : {st['why']}."
        z = ", ".join(f"{lv['L']} à {fmt_price(lv['price'])}" for lv in st["valid"])
        out += f"Zones valables avec un FVG : {z}. Le gold est à {fmt_price(price)}."
        if not self.enabled():
            out += " Les alertes sont coupées."
        return out

    def resume(self) -> dict:
        st = self.last or {}
        return {"actif": self.enabled(), "envoyees": len(self.state.get("sent", [])), "observation": OBSERVE_ONLY,
                "biais": st.get("bias"), "pourquoi": st.get("why", ""), "maj": self.bars_t, "erreur": self.erreur,
                "zones": [{"niveau": lv["L"], "prix": round(lv["price"], 2)} for lv in st.get("valid", [])]}

    # ------------------------------------------------------------------ alertes
    def _send(self, key: str, genre: str, text: str, row: list[str], plan: dict | None = None) -> None:
        if OBSERVE_ONLY:  # phase de vérification : seulement dans le log, rien n'est gardé comme « envoyé »
            if key not in self._observed:
                self._observed.add(key)
                log.info("Stratégie (observation, pas envoyé) : %s", text)
            return
        with self.lock:
            if key in self.state.get("sent", []):
                return
            self.state.setdefault("sent", []).append(key)
            self._save()
        log.info("Alerte stratégie : %s", text)
        evt = {"cle": key, "source": "strategie", "type": genre, "texte": text}
        if plan:
            evt["plan"] = dict(plan)
        try:
            self.emettre(evt)
        except Exception as e:
            log.warning("Stratégie : événement non écrit (%s)", e)
        self._log_row(row)

    def _log_row(self, row: list[str]) -> None:
        f = self.journal
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            head = b"" if f.exists() else ("\ufeff" + ";".join(
                ["Date", "Heure", "Type", "Sens", "Niveau", "Prix du niveau", "Prix", "Origine impulsion",
                 "Extreme impulsion", "FVG", "Stop", "TP1 (0)", "TP2 (-0.618)", "Biais 12H", "Biais 1H",
                 "EMA 200"]) + "\n").encode("utf-8")
            with open(f, "ab") as fh:
                fh.write(head + (";".join(x.replace(";", ",") for x in row) + "\n").encode("utf-8"))
        except OSError as e:
            log.debug("Stratégie : journal des alertes %s", e)

    def _row(self, kind: str, st: dict, lv: dict, price: float, plan: dict | None) -> list[str]:
        n = dt.datetime.now()
        c = lambda x: f"{x:.2f}".replace(".", ",")  # noqa: E731
        return [n.strftime("%d/%m/%Y"), n.strftime("%H:%M"), kind, "Long" if st["bias"] == "haussier" else "Short",
                str(lv["L"]), c(lv["price"]), c(price), c(st["origin"]), c(st["extreme"]),
                f"{c(lv['fvg'][0])}-{c(lv['fvg'][1])}", c(plan["stop"]) if plan else "?",
                c(plan["tp1"]) if plan else "?", c(plan["tp2"]) if plan else "?", st["trend_12h"],
                st["trend_1h"], f"{st['ema_pos']} ({c(st['ema'])})"]

    def check(self, now: float | None = None) -> None:
        """Un tour : bougies (toutes les 5 min), prix, zones, confirmation. Rien n'est envoyé deux fois.
        Le coupe-circuit n'est pas ici : il est chez Jarvis, qui n'annonce pas d'entrée s'il est déclenché."""
        now = now or time.time()
        if not self.enabled():
            return
        self.tours += 1
        self._bougies(now)
        if not self.bars:
            return
        st = analyze(self.bars, now)
        self.last = st
        why = st.get("why") or ("zones : " + ", ".join(f"{lv['L']}={lv['price']:.1f}" for lv in st.get("valid", [])))
        if why != self._last_why:  # dans le log seulement quand ça change
            self._last_why = why
            log.info("Stratégie : %s%s.", f"biais {st['bias']}, " if st.get("bias") else "", why)
        if not st["ok"]:
            return
        up = st["bias"] == "haussier"
        sens = "haussier" if up else "baissier"
        # 1) le prix arrive sur une zone
        if self.prix and in_window(now):
            price = self.prix
            for lv in st["valid"]:
                if abs(price - lv["price"]) <= NEAR_ATR * st["atr"]:
                    key = f"zone-{st['impulse_id']}-{lv['L']}"
                    text = (f"Alerte stratégie : le gold arrive sur le {lv['L']} à {fmt_price(lv['price'])}, "
                            f"avec un FVG dessus. Biais {sens} en 12H et en 1H. "
                            "Attends la bougie de confirmation 1H.")
                    self._send(key, "zone", text, self._row("zone", st, lv, price, None))
                    break
        # 2) bougie de confirmation (bougie 1H clôturée, après l'extrême de l'impulsion)
        closed = st["closed"]
        bar, ib = closed[-1], len(closed) - 1
        if ib > st["ie"] and bar.t > self.state.get("checked_bar", 0):
            with self.lock:
                self.state["checked_bar"] = bar.t
                self._save()
            if in_window(bar.t + 3600):  # l'entrée se fait à la bougie suivante
                for lv in st["valid"]:
                    if confirmation(st, bar, lv):
                        plan = trade_plan(st, lv)
                        key = f"conf-{st['impulse_id']}-{lv['L']}"
                        side = "à l'achat" if up else "à la vente"
                        text = (f"Alerte stratégie : bougie de confirmation 1H sur le {lv['L']} "
                                f"({fmt_price(lv['price'])}). Entrée possible à la bougie suivante, "
                                f"{side} ; la décision est à toi. "
                                f"Stop {'sous' if up else 'au-dessus de'} {fmt_price(plan['stop'])} "
                                f"(FVG et zone suivante). TP1 au 0 : {fmt_price(plan['tp1'])}. "
                                f"TP2 au -0.618 : {fmt_price(plan['tp2'])}. Break-even à {fmt_price(plan['be'])}.")
                        self._send(key, "confirmation", text, self._row("confirmation", st, lv, bar.c, plan), plan)
                        break

    # ------------------------------------------------------------------ commandes
    @staticmethod
    def wants(c: str) -> bool:
        t = plain(c)
        if not re.search(r"(?<![a-z])strateg|zones? du jour|biais du jour", t):
            return False
        return bool(re.search(r"(?<![a-z])(alertes?|etat|ou en est|zones?|biais|situation|ca donne|dit quoi|"
                              r"lecture|point)(?![a-z])", t))

    def handle(self, c: str) -> str | None:
        if not self.wants(c):
            return None
        t = plain(c)
        if re.search(r"(?<![a-z])alertes?(?![a-z])", t):
            if re.search(r"(?<![a-z])(coupe|desactive|arrete|stop|enleve|supprime|plus d)", t):
                return self.set_enabled(False)
            if re.search(r"(?<![a-z])(remets|active|reactive|relance|rallume|remet)", t):
                return self.set_enabled(True)
        if re.search(r"(?<![a-z])(etat|ou en est|zones?|biais|situation|ca donne|dit quoi|lis|lecture|point)", t):
            return self.state_phrase()
        return None
