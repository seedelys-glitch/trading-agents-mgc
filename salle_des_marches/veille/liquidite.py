"""Agent Liquidité de la veille : prévient quand le prix va chercher la liquidité (24/10/2026).

Jabran : « le marché connaît déjà la news et prépare le setup en allant chercher la liquidité (plus hauts / plus
bas des sessions Asie et Londres) avant de partir dans son vrai mouvement ». Toutes les 2 minutes, la veille
calcule ces niveaux (calculs.liquidite_sessions, le même calcul que le desk) et écrit un événement quand l'un
d'eux vient d'être BALAYÉ (mèche au-delà puis retour), entre 8h et 20h30 heure de Paris, en semaine.

Aucun ordre : un événement « liquidite » est seulement annoncé par Jarvis.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import time
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import requests

from .bougies import UA

try:  # lancé par « python -m salle_des_marches.veille »
    from .. import calculs
except ImportError:  # tests : salle_des_marches est dans sys.path
    import calculs

log = logging.getLogger("veille")
PARIS = ZoneInfo("Europe/Paris")
CHECK_S = 120
HEURES = (8 * 60, 20 * 60 + 30)   # annonces entre 8h et 20h30 (Paris), du lundi au vendredi


def yahoo_df(interval: str, rng: str):
    """Bougies GC=F (repli MGC=F) au format du desk : colonnes o, h, l, c, v ; index UTC."""
    import pandas as pd

    for sym in ("GC=F", "MGC=F"):
        try:
            r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                             params={"interval": interval, "range": rng}, headers=UA, timeout=20)
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            lignes = [(t, o, h, l, c, v or 0) for t, o, h, l, c, v in
                      zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"], q.get("volume") or [0] * len(q["open"]))
                      if None not in (o, h, l, c)]
            if len(lignes) > 20:
                index = pd.to_datetime([x[0] for x in lignes], unit="s", utc=True)
                return pd.DataFrame([x[1:] for x in lignes], index=index, columns=["o", "h", "l", "c", "v"])
        except Exception as e:
            log.debug("Liquidité : bougies %s %s indisponibles (%s)", sym, interval, e)
    return None


class Liquidite:
    def __init__(self, dossier: Path, emettre: Callable[[dict], None] | None = None,
                 charger: Callable[[str, str], object] = yahoo_df):
        self.emettre = emettre or (lambda e: None)
        self.charger = charger
        self.fichier = Path(dossier) / "liquidite-etat.json"
        self.lock = threading.Lock()
        self.dernier: dict = {}
        self.erreur = ""
        self.envoyes = self._lire()

    def _lire(self) -> list[str]:
        try:
            return list(json.loads(self.fichier.read_text(encoding="utf-8")).get("envoyes", []))[-200:]
        except (OSError, ValueError):
            return []

    def _sauver(self) -> None:
        try:
            self.fichier.write_text(json.dumps({"envoyes": self.envoyes[-200:]}), encoding="utf-8")
        except OSError:
            pass

    def calculer(self) -> dict:
        m5 = self.charger("5m", "5d")
        d1 = self.charger("1d", "1mo")
        if m5 is None or len(m5) < 20:
            return {"disponible": False, "raison": "bougies 5 min indisponibles"}
        return calculs.liquidite_sessions({"M5": m5, "D1": d1 if d1 is not None else m5.iloc[:0]}, None)

    def check(self, now: float | None = None) -> None:
        now = now or time.time()
        liq = self.calculer()
        self.dernier = liq
        if not liq.get("disponible"):
            return
        paris = dt.datetime.fromtimestamp(now, PARIS)
        if paris.weekday() >= 5 or not HEURES[0] <= paris.hour * 60 + paris.minute <= HEURES[1]:
            return
        aujourdhui = paris.strftime("%d/%m")
        for p in liq["niveaux"]:
            if p.get("etat") != "balayée" or not str(p.get("quand") or "").startswith(aujourdhui):
                continue
            cle = f"liq-{paris.date().isoformat()}-{p['nom']}-{p['prix']}"
            with self.lock:
                if cle in self.envoyes:
                    continue
                self.envoyes.append(cle)
                self._sauver()
            heure = p["quand"].split(" ")[1]
            cote = "au-dessus" if p["cote"] == "haut" else "en dessous"
            texte = (f"Liquidité prise : le {p['nom']} ({p['prix']:.1f}) a été balayé à {heure}, mèche {cote} "
                     "puis retour. Selon ta méthode, le vrai mouvement peut partir : regarde la cascade.")
            log.info("%s", texte)
            try:
                self.emettre({"cle": cle, "source": "liquidite", "type": "prise", "texte": texte, "niveau": p})
            except Exception as e:
                log.warning("Liquidité : événement non écrit (%s)", e)

    def resume(self) -> dict:
        liq = self.dernier or {}
        return {"actif": True, "erreur": self.erreur,
                "intacte_dessus": liq.get("liquidite_intacte_au_dessus"),
                "intacte_dessous": liq.get("liquidite_intacte_en_dessous"),
                "derniere_prise": liq.get("derniere_liquidite_prise")}
