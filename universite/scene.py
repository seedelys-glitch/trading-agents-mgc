# -*- coding: utf-8 -*-
"""
Plan du bureau immersif : les zones et les postes, décrits en DONNÉES (mètres, x vers la droite, y vers le fond,
z vers le haut). Aucun dessin ici : le moteur d'affichage du navigateur (vue isométrique aujourd'hui, un moteur
3D ou VR plus tard) lit ce plan et l'état réel de la base, sans rien changer d'autre.

Une zone dit ce qu'elle montre et d'où ça vient : elle n'affiche jamais une activité qui n'existe pas.
"""

from . import agents

SOL = {"l": 48, "p": 30}
HAUTEUR_MUR = 3.0

ZONES = [
    {"cle": "directeur", "nom": "Bureau du directeur", "x": 19, "y": 11, "l": 10, "p": 8,
     "montre": "Dernière synthèse, demandes en cours, alertes reçues",
     "source": "documents de synthèse, missions et messages de l'agent 14"},
    {"cle": "analyse", "nom": "Salle d'analyse technique", "x": 1, "y": 1, "l": 16, "p": 12,
     "montre": "Les analyses SMC, Fibonacci, Ichimoku, VWAP / EMA et flux, et leur vérification",
     "source": "documents d'analyse des agents 1, 2, 3, 6 et 7"},
    {"cle": "macro", "nom": "Pôle macro et discours", "x": 31, "y": 1, "l": 16, "p": 12,
     "montre": "Calendrier des annonces, discours de la Fed, précédents, réactions mesurées du gold",
     "source": "annonces gardées et documents des agents 5, 10, 11 et 12"},
    {"cle": "reunion", "nom": "Salle de réunion", "x": 19, "y": 1, "l": 10, "p": 8,
     "montre": "Les vraies chaînes de travail : qui a demandé quoi à qui, et la réponse",
     "source": "messages entre agents"},
    {"cle": "bibliotheque", "nom": "Bibliothèque et vérification", "x": 1, "y": 17, "l": 16, "p": 12,
     "montre": "Règles proposées et validées, extraits gardés, recherche, contrôles de l'agent 9, mémoire (Scribe et Archiviste)",
     "source": "tables des règles, des extraits et des blocs de mémoire, documents de vérification"},
    {"cle": "labo", "nom": "Labo quant", "x": 19, "y": 21, "l": 10, "p": 8,
     "montre": "Replays de la stratégie, contrôles de données",
     "source": "documents de replay et de contrôle de l'agent 13"},
    {"cle": "risque", "nom": "Contrôle des risques", "x": 31, "y": 17, "l": 8, "p": 12,
     "montre": "Évaluations de risque et vetos",
     "source": "documents de l'agent 8"},
    {"cle": "donnees", "nom": "Salle des données", "x": 41, "y": 17, "l": 6, "p": 12,
     "montre": "Jeux de bougies, période couverte, imports TradingView",
     "source": "jeux et fichiers importés"},
]

# Agents de chaque zone, dans l'ordre des postes (rangées de 3 au plus)
OCCUPANTS = {
    "directeur": [14],
    "analyse": [1, 2, 3, 6, 7, 4],
    "macro": [5, 10, 11, 12],
    "bibliotheque": [9, 15, 16],
    "labo": [13],
    "risque": [8],
}

PAR_CLE = {z["cle"]: z for z in ZONES}


def _postes():
    postes = []
    for cle, numeros in OCCUPANTS.items():
        z = PAR_CLE[cle]
        colonnes = min(3, len(numeros))
        rangees = (len(numeros) + colonnes - 1) // colonnes
        for i, n in enumerate(numeros):
            col, rang = i % colonnes, i // colonnes
            postes.append({"agent": n, "zone": cle,
                           "x": round(z["x"] + z["l"] * (col + 0.5) / colonnes, 2),
                           "y": round(z["y"] + z["p"] * (rang + 0.5) / rangees, 2),
                           "z": 0, "orientation": 180, "l": 2.2, "p": 1.2})
    return postes


POSTES = _postes()


def scene():
    """Le plan complet, avec le nom de chaque agent (pas son état : celui-ci vient de /api/etat)."""
    zones = [{**z, "z": 0, "h": HAUTEUR_MUR} for z in ZONES]
    postes = [{**p, "nom": agents.agent(p["agent"])["nom"], "court": agents.agent(p["agent"])["court"]}
              for p in POSTES]
    return {"version": 1, "unite": "m", "sol": SOL, "zones": zones, "postes": postes}


def poste(n):
    return next((p for p in POSTES if p["agent"] == int(n)), None)


def verifier(s=None):
    """Problèmes du plan (liste vide = plan cohérent) : un poste par agent, postes dans leur zone, pas de chevauchement."""
    s = s or scene()
    problemes = []
    vus = [p["agent"] for p in s["postes"]]
    attendus = [a["n"] for a in agents.AGENTS]
    if sorted(vus) != attendus:
        problemes.append(f"postes {sorted(vus)} au lieu de {attendus}")
    zones = {z["cle"]: z for z in s["zones"]}
    for z in s["zones"]:
        if z["x"] < 0 or z["y"] < 0 or z["x"] + z["l"] > s["sol"]["l"] or z["y"] + z["p"] > s["sol"]["p"]:
            problemes.append(f"zone {z['cle']} hors du sol")
    for i, a in enumerate(s["zones"]):
        for b in s["zones"][i + 1:]:
            if a["x"] < b["x"] + b["l"] and b["x"] < a["x"] + a["l"] and a["y"] < b["y"] + b["p"] and b["y"] < a["y"] + a["p"]:
                problemes.append(f"zones {a['cle']} et {b['cle']} se chevauchent")
    for p in s["postes"]:
        z = zones.get(p["zone"])
        if not z or not (z["x"] + p["l"] / 2 <= p["x"] <= z["x"] + z["l"] - p["l"] / 2
                         and z["y"] + p["p"] / 2 <= p["y"] <= z["y"] + z["p"] - p["p"] / 2):
            problemes.append(f"poste de l'agent {p['agent']} hors de sa zone")
    for i, a in enumerate(s["postes"]):
        for b in s["postes"][i + 1:]:
            if abs(a["x"] - b["x"]) < (a["l"] + b["l"]) / 2 and abs(a["y"] - b["y"]) < (a["p"] + b["p"]) / 2:
                problemes.append(f"postes {a['agent']} et {b['agent']} se chevauchent")
    return problemes
