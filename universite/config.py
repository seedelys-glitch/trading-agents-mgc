# -*- coding: utf-8 -*-
"""
Réglages et emplacements de l'université.

Les réglages modifiables sont dans rapports\\universite\\reglages-universite.json (créé au premier
changement, modifiable depuis le panneau « Réglages » du bureau). Aucune clé ni mot de passe ici :
l'IA utilisée est LM Studio, sur le PC.
"""

import json
import os
import sys
import threading
from pathlib import Path

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent                                  # Documents\TradingAgents
SALLE = RACINE / "salle_des_marches"
DONNEES = Path(os.environ.get("UNIVERSITE_DONNEES") or RACINE / "rapports" / "universite")

DEFAUTS = {
    "port": 8780,
    "concurrence": 2,             # missions exécutées en même temps (calculs Python)
    "concurrence_ia": 1,          # appels à l'IA locale en même temps (protège la carte graphique)
    "delai_mission_s": 300,       # au-delà, la mission est arrêtée et notée en erreur
    "tentatives_max": 2,          # nouvel essai automatique après une erreur passagère
    "ia_url": "http://127.0.0.1:1234/v1",   # LM Studio (API compatible OpenAI)
    "ia_modele": "",              # vide = le modèle déjà chargé dans LM Studio
    "ia_commentaires": True,      # commentaire pédagogique sous les rapports, si LM Studio répond
    "ia_appels_max_jour": 200,    # budget d'appels IA par jour
    "ia_delai_s": 90,
    "ia_embeddings": "",          # modèle d'embeddings LM Studio (ex. nomic-embed), vide = recherche par mots seulement
}

_verrou = threading.Lock()


def salle_importable():
    """Rend calculs.py et le paquet mgc de la Salle importables (sans rien modifier dans la Salle)."""
    chemin = str(SALLE)
    if chemin not in sys.path:
        sys.path.append(chemin)


def fichier_reglages(dossier=None):
    return Path(dossier or DONNEES) / "reglages-universite.json"


def charger(dossier=None):
    r = dict(DEFAUTS)
    try:
        lu = json.loads(fichier_reglages(dossier).read_text(encoding="utf-8"))
        r.update({k: v for k, v in lu.items() if k in DEFAUTS})
    except (OSError, ValueError):
        pass
    return r


def enregistrer(modifs, dossier=None):
    """Applique seulement les clés connues, dans des bornes raisonnables ; renvoie les réglages complets."""
    with _verrou:
        r = charger(dossier)
        for k, v in (modifs or {}).items():
            if k not in DEFAUTS or k == "port":
                continue
            attendu = type(DEFAUTS[k])
            try:
                v = (str(v).lower() in ("1", "true", "oui")) if attendu is bool else attendu(v)
            except (TypeError, ValueError):
                continue
            if k in ("concurrence", "concurrence_ia"):
                v = max(1, min(8, v))
            elif k == "delai_mission_s":
                v = max(10, min(3600, v))
            elif k == "tentatives_max":
                v = max(0, min(5, v))
            elif k == "ia_appels_max_jour":
                v = max(0, min(10_000, v))
            elif k == "ia_url" and not str(v).startswith(("http://127.0.0.1", "http://localhost")):
                continue  # l'IA de l'université reste sur le PC
            r[k] = v
        f = fichier_reglages(dossier)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(f)
        return r
