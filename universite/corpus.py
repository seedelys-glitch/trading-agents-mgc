# -*- coding: utf-8 -*-
"""
Le corpus Groq (31/10, demande de Jabran) : chaque fois que Groq (gratuit, en ligne, via Jarvis) répond à l'université,
la question et la réponse sont gardées, avec le verdict de l'université (texte accepté, refusé par la charte, réponse
de quiz juste ou fausse). Plus tard, les IA locales (LM Studio) pourront s'appuyer sur ces exemples (exemples à
montrer avant une question, ou ré-entraînement si un jour la machine le permet).

Rangement : rapports\\universite\\corpus_groq\\<numéro>-<agent>\\<AAAA-MM>.jsonl, une ligne JSON par échange
(format « messages » : system / user / assistant, le format attendu par les outils d'entraînement).
Les secrets sont masqués avant l'écriture (même règle que le Scribe). Rien n'est jamais envoyé ailleurs.
"""

import datetime as dt
import json
import threading
import time
from pathlib import Path

from .agents import agent as fiche_agent

_verrou = threading.Lock()
LISEZ_MOI = ("Corpus Groq de l'université MGC : une ligne JSON par question posée à Groq et sa réponse, avec le verdict "
             "de l'université (accepte, refuse, juste, faux). Un dossier par agent, un fichier par mois.\n"
             "Sert plus tard aux IA locales (exemples à suivre). Les secrets sont masqués. Ne pas modifier à la main.\n")


def dossier(base):
    return Path(base.fichier).parent / "corpus_groq"


def _dossier_agent(base, agent):
    a = fiche_agent(agent) if agent else None
    nom = f"{a['n']:02d}-{a['cle']}" if a else "00-divers"
    return dossier(base) / nom


def noter(base, agent, genre, consigne, entree, sortie, modele, verdict, mission=None):
    """Ajoute un échange au corpus. Ne lève jamais d'erreur (le corpus ne doit pas casser une mission)."""
    try:
        from .memoire import masquer

        ligne = {"ts": time.time(), "date": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "agent": agent,
                 "genre": genre, "modele": modele, "verdict": verdict, "mission": mission,
                 "messages": [{"role": "system", "content": masquer(consigne)},
                              {"role": "user", "content": masquer(entree)},
                              {"role": "assistant", "content": masquer(sortie)}]}
        d = _dossier_agent(base, agent)
        with _verrou:
            d.mkdir(parents=True, exist_ok=True)
            racine = dossier(base) / "LISEZ-MOI.txt"
            if not racine.exists():
                racine.write_text(LISEZ_MOI, encoding="utf-8")
            with open(d / f"{dt.date.today():%Y-%m}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        return True
    except Exception:  # noqa: BLE001
        return False


def exemples(base, agent, genre=None, verdicts=("accepte", "juste"), n=3):
    """Les derniers bons exemples d'un agent (pour les montrer à une IA locale avant une question)."""
    d = _dossier_agent(base, agent)
    res = []
    for fichier in sorted(d.glob("*.jsonl"), reverse=True):
        for texte in reversed(fichier.read_text(encoding="utf-8").splitlines()):
            try:
                ligne = json.loads(texte)
            except ValueError:
                continue
            if ligne.get("verdict") in verdicts and (genre is None or ligne.get("genre") == genre):
                res.append(ligne)
                if len(res) >= n:
                    return res
    return res


def resume(base):
    """Combien d'échanges par agent (pour la fiche et l'API)."""
    compte = {}
    for f in dossier(base).glob("*/*.jsonl"):
        compte[f.parent.name] = compte.get(f.parent.name, 0) + sum(1 for _ in f.open(encoding="utf-8"))
    return compte
