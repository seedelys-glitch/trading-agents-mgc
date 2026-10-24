"""La veille : fait tourner les agents de surveillance et garde leurs événements dans un journal.

Journal : rapports\\salle\\veille-evenements.jsonl (une ligne JSON par événement, numérotée).
Rien ici ne passe, ne prépare ni ne transmet d'ordre.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path

from . import actus
from .bougies import plain
from .cascade import CHECK_S, Cascade
from .ia import IALocale
from .journal_setups import SetupJournal
from .liquidite import CHECK_S as CHECK_LIQ_S, Liquidite
from .strategie_1h import CHECK_S as CHECK_STRAT_S, Strategie1H

log = logging.getLogger("veille")

RACINE = Path(__file__).resolve().parent.parent.parent
DOSSIER = RACINE / "rapports" / "salle"
GARDES = 500  # événements gardés dans le journal


class Veille:
    def __init__(self, dossier: Path = DOSSIER):
        self.dossier = Path(dossier)
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.fichier = self.dossier / "veille-evenements.jsonl"
        self.lock = threading.Lock()
        self.evenements: list[dict] = self._lire()
        self.cascade = Cascade(self.dossier, emettre=self.ajouter)
        self.strategie = Strategie1H(self.dossier, emettre=self.ajouter)
        self.ia = IALocale()
        self.setups = SetupJournal(self.ia)            # journal des setups du dossier bot trad
        self.liquidite = Liquidite(self.dossier, emettre=self.ajouter)   # Asie / Londres / veille balayées
        self.depart = time.time()

    # ------------------------------------------------------------------ journal
    def _lire(self) -> list[dict]:
        out = []
        try:
            for ligne in self.fichier.read_text(encoding="utf-8").splitlines():
                try:
                    e = json.loads(ligne)
                    if isinstance(e, dict) and isinstance(e.get("id"), int):
                        out.append(e)
                except ValueError:
                    continue
        except OSError:
            pass
        return out[-GARDES:]

    def ajouter(self, evt: dict) -> dict:
        with self.lock:
            dernier = self.evenements[-1]["id"] if self.evenements else 0
            e = dict(evt, id=dernier + 1, t=time.time())
            self.evenements.append(e)
            reecrire = len(self.evenements) > GARDES
            self.evenements = self.evenements[-GARDES:]
            try:
                if reecrire:
                    self.fichier.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n"
                                                    for x in self.evenements), encoding="utf-8")
                else:
                    with self.fichier.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(e, ensure_ascii=False) + "\n")
            except OSError as err:
                log.warning("Veille : journal non écrit (%s)", err)
        return e

    def depuis(self, n: int) -> list[dict]:
        with self.lock:
            return [e for e in self.evenements if e["id"] > n]

    def dernier_id(self) -> int:
        with self.lock:
            return self.evenements[-1]["id"] if self.evenements else 0

    # ------------------------------------------------------------------ état et commandes
    def etat(self) -> dict:
        return {"agents": {"cascade": self.cascade.resume(), "strategie": self.strategie.resume(),
                           "liquidite": self.liquidite.resume()},
                "dernier_id": self.dernier_id(),
                "depuis": self.depart}

    def commande(self, texte: str) -> str | None:
        """Phrase de Jabran relayée par Jarvis. None = la veille ne connaît pas cette phrase."""
        t = plain(texte or "")
        if self.cascade.wants(t):
            if re.search(r"(?<![a-z])(coupe|desactive|arrete|stop|remets|active|reactive|relance|rallume|remet)", t):
                return self.cascade.handle(t)
            if not self.cascade.etat.get("maj"):
                return "La cascade démarre, je n'ai pas encore fini mon premier tour. Redemande dans une minute."
            return self.cascade.etat_phrase()
        if self.strategie.wants(t):
            return self.strategie.handle(t)
        return None

    # ------------------------------------------------------------------ demandes de Jarvis (photo, actu)
    def noter_setup(self, image: bytes, extra: str = "", resultat: str = "", quand: str = "",
                    source: str = "") -> str:
        if not image:
            return "Je n'ai pas reçu d'image du setup."
        return self.setups.add(image, extra, resultat, quand, source=source)

    def stats_setups(self) -> str:
        return self.setups.stats()

    def analyser_actu(self, texte: str, source: str) -> dict:
        return actus.analyse(self.ia, texte, source)

    # ------------------------------------------------------------------ boucle
    def boucle(self) -> None:
        prochaine_strat = prochaine_liq = 0.0
        while True:
            try:
                self.cascade.check()
                self.cascade.erreur = ""
            except Exception as e:
                self.cascade.erreur = repr(e)[:200]
                log.warning("Cascade : %s", e)
            if time.time() >= prochaine_strat:
                prochaine_strat = time.time() + CHECK_STRAT_S
                try:
                    self.strategie.check()
                    self.strategie.erreur = ""
                except Exception as e:
                    self.strategie.erreur = repr(e)[:200]
                    log.warning("Stratégie : %s", e)
            if time.time() >= prochaine_liq:
                prochaine_liq = time.time() + CHECK_LIQ_S
                try:
                    self.liquidite.check()
                    self.liquidite.erreur = ""
                except Exception as e:
                    self.liquidite.erreur = repr(e)[:200]
                    log.warning("Liquidité : %s", e)
            time.sleep(CHECK_S)

    def demarrer(self) -> None:
        threading.Thread(target=self.boucle, daemon=True, name="veille-cascade").start()
