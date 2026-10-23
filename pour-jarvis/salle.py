"""
Salle des marchés (TradingAgents) depuis Jarvis : lance le desk des spécialistes sur le PC
et envoie le plan du chef de desk sur le téléphone (Telegram) dès qu'il est prêt.

La Salle est un programme séparé (Documents\\TradingAgents\\salle_des_marches). Jarvis ne fait que :
  1. la démarrer si elle est fermée (sans fenêtre, sans ouvrir le navigateur) ;
  2. lui demander un desk (POST /api/lancer) ;
  3. surveiller la fin (GET /api/resume/<id>) et envoyer le résumé avec notify(texte, "brief").

Aucun appel réseau n'est fait en tenant le verrou.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

import requests

log = logging.getLogger("jarvis")

DOSSIER = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents" / "TradingAgents"
PORTS = range(8790, 8800)          # la Salle prend 8790, ou le suivant libre
LIMITE_S = 35 * 60                 # la Salle s'arrête elle-même à 30 min ; on attend un peu plus
SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Mots dits ou écrits -> ticker compris par la Salle
ALIAS = {
    "gold": "XAUUSD", "or": "XAUUSD", "xau": "XAUUSD", "xauusd": "XAUUSD",
    "bitcoin": "BTC-USD", "btc": "BTC-USD",
    "nasdaq": "NQ=F", "nq": "NQ=F", "sp500": "ES=F", "es": "ES=F",
    "nvidia": "NVDA", "nvda": "NVDA", "apple": "AAPL", "lvmh": "MC.PA",
}
NOMS = {"XAUUSD": "le gold", "BTC-USD": "le bitcoin", "NQ=F": "le Nasdaq", "ES=F": "le S&P 500"}


def ticker_depuis_texte(texte: str) -> str:
    """« lance le desk sur le gold » -> XAUUSD ; « desk nvda » -> NVDA. Par défaut : le gold."""
    mots = re.findall(r"[a-z0-9.&=\-]+", (texte or "").lower().replace("s&p 500", "sp500").replace("s&p", "sp500"))
    for mot in mots:
        if mot in ALIAS:
            return ALIAS[mot]
    # un ticker écrit tel quel après « sur » (ex. « desk sur TSLA »)
    m = re.search(r"\bsur (?:le |la |l')?([a-z]{1,5}(?:\.[a-z]{1,2})?)\b", (texte or "").lower())
    if m and m.group(1) not in ("le", "la", "les", "du", "des"):
        return m.group(1).upper()
    return "XAUUSD"


class SalleDesMarches:
    def __init__(self, notify: Callable[[str, str], None], dossier: Path = DOSSIER, attente_s: float = 15):
        self.notify = notify
        self.dossier = dossier
        self.attente_s = attente_s        # intervalle entre deux coups d'œil à la Salle
        self._verrou = threading.Lock()
        self.en_cours: tuple[str, str, float] | None = None   # (identifiant, ticker, début)
        self.dernier = ""                                     # dernier résumé reçu

    # ------------------------------------------------------------------ trouver / démarrer la Salle
    def _adresse(self) -> str | None:
        for port in PORTS:
            try:
                r = requests.get(f"http://127.0.0.1:{port}/api/salle", timeout=1.5)
                if r.ok and r.json().get("salle") is True:
                    return f"http://127.0.0.1:{port}"
            except Exception:
                continue
        return None

    def _demarrer(self) -> str | None:
        pythonw = self.dossier / ".venv" / "Scripts" / "pythonw.exe"
        serveur = self.dossier / "salle_des_marches" / "serveur.py"
        if not (pythonw.is_file() and serveur.is_file()):
            log.warning("Salle des marchés : introuvable dans %s.", self.dossier)
            return None
        log.info("Salle des marchés : je la démarre (sans fenêtre).")
        try:
            subprocess.Popen([str(pythonw), str(serveur), "--sans-navigateur"], cwd=str(self.dossier),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=SANS_FENETRE)
        except Exception as e:
            log.warning("Salle des marchés : démarrage impossible (%s).", e)
            return None
        for _ in range(40):
            time.sleep(1)
            adresse = self._adresse()
            if adresse:
                return adresse
        return None

    # ------------------------------------------------------------------ commandes
    def lancer_desk(self, texte: str = "", ia: str = "auto") -> str:
        """Lance le desk et répond tout de suite ; le plan arrive sur Telegram à la fin."""
        ticker = ticker_depuis_texte(texte)
        nom = NOMS.get(ticker, ticker)
        with self._verrou:
            if self.en_cours:
                return (f"Un desk tourne déjà sur {NOMS.get(self.en_cours[1], self.en_cours[1])}. "
                        "Je t'envoie le plan sur Telegram dès qu'il est prêt.")
        adresse = self._adresse() or self._demarrer()
        if not adresse:
            return "Je n'arrive pas à ouvrir la Salle des marchés sur le PC."
        try:
            r = requests.post(f"{adresse}/api/lancer", timeout=20,
                              json={"mode": "bureau", "ticker": ticker, "moteur": ia})
            donnees = r.json()
        except Exception as e:
            log.warning("Salle des marchés : %s", e)
            return "La Salle des marchés ne répond pas."
        if r.status_code != 200:
            return donnees.get("erreur") or "La Salle des marchés a refusé de lancer le desk."
        ident = donnees["id"]
        with self._verrou:
            self.en_cours = (ident, ticker, time.time())
        threading.Thread(target=self._surveiller, args=(adresse, ident, ticker), daemon=True,
                         name="salle-desk").start()
        log.info("Salle des marchés : desk %s lancé (%s).", ticker, ident)
        return f"C'est parti, le desk analyse {nom}. Je t'envoie le plan sur Telegram dans 5 minutes environ."

    def _surveiller(self, adresse: str, ident: str, ticker: str) -> None:
        fin, texte = time.time() + LIMITE_S, ""
        while time.time() < fin:
            time.sleep(self.attente_s)
            try:
                r = requests.get(f"{adresse}/api/resume/{ident}", timeout=10)
                d = r.json()
                if d.get("fini"):
                    texte = d.get("texte") or ""
                    break
            except Exception:
                continue  # la Salle redémarre ou le PC est chargé : on réessaie
        if not texte:
            texte = f"Desk {ticker} : pas de réponse de la Salle des marchés au bout de 35 minutes."
        with self._verrou:
            self.en_cours, self.dernier = None, texte
        log.info("Salle des marchés : desk %s terminé.", ticker)
        self.notify(texte, "brief")

    def etat_phrase(self) -> str:
        """« Où en est le desk ? »"""
        with self._verrou:
            en_cours, dernier = self.en_cours, self.dernier
        if en_cours:
            minutes = int((time.time() - en_cours[2]) // 60)
            return (f"Le desk sur {NOMS.get(en_cours[1], en_cours[1])} tourne depuis "
                    f"{minutes} minute{'s' if minutes > 1 else ''}.")
        return dernier or "Aucun desk lancé depuis le démarrage de Jarvis."
