# -*- coding: utf-8 -*-
"""
Réglages de l'analyste MGC.

Valeurs par défaut ci-dessous, remplaçables dans salle_des_marches\\config_mgc.json (facultatif,
mêmes noms). La limite de perte du jour est lue en lecture seule dans les règles de Jarvis
(Documents\\Jarvis\\prop-firm.txt) si elle n'est pas donnée ici.
"""

import hashlib
import json
import os
from pathlib import Path

ICI = Path(__file__).resolve().parent.parent
FICHIER_CONFIG = ICI / "config_mgc.json"
REGLES_JARVIS = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents" / "Jarvis" / "prop-firm.txt"

DEFAUTS = {
    "prop_firm": "Topstep",
    "capital_usd": 50_000,
    "risque_pct": 0.25,                 # décision de Jabran du 23/10 pour Topstep : 0,25 % = 125 $ par trade (avant : 1 %)
    "limite_perte_jour_usd": None,      # None = lue dans prop-firm.txt de Jarvis (repli : 1000)
    "frais_aller_retour_usd": 1.50,     # ESTIMATION par contrat (commission + frais CME) : à confirmer sur un relevé
    "glissement_ticks_par_cote": 1,     # hypothèse : 1 tick à l'entrée + 1 tick à la sortie
    "ratio_min": 1.5,                   # rendement / risque minimal (net, sur le TP1)
    "max_contrats": 50,                 # plafond de sécurité ; à aligner sur la taille max du compte Topstep
    "fenetre_paris": ["15:30", "20:00"],  # décision de Jabran du 17/10
    "rollover_jours_restriction": 5,    # jours ouvrés avant la bascule pendant lesquels rien n'est exploitable
    "bascule_jours_avant_avis": 2,      # bascule de liquidité estimée N jours ouvrés avant le premier jour d'avis
    "mois_cotes": "GJMQVZ",             # mois cotés (fiche CME + contrats vus chez Yahoo le 17/10/2026)
    "ecart_sources_points": 2.0,        # écart maximal toléré entre deux sources de prix
    "annonce_avant_min": 90,            # annonce USD forte : blocage avant...
    "annonce_apres_min": 30,            # ... et après
    "discours_fed_avant_min": 30,       # discours du président de la Fed (décision du 17/10)
    "discours_fed_apres_min": 30,
    # --- données (étape 2)
    "dossier_ninja": None,              # None = Documents\TradingAgents\donnees_ninja (fichiers de l'indicateur)
    "battement_max_s": 120,             # NinjaTrader : dernier signe de vie au plus vieux, marché ouvert
    "fraicheur_marge_min": 2,           # une bougie fermée peut arriver jusqu'à 2 min en retard
    "trou_max_min": 15,                 # plus long trou toléré en séance ouverte (sinon données invalides)
    "bougies_controlees": 500,          # nombre de dernières bougies vérifiées (trous, doublons, prix)
}


FICHIER_PAUSE = ICI.parent / "rapports" / "salle" / "pause.demande"  # créé par /pause, supprimé par /resume


def pause_active(fichier=FICHIER_PAUSE):
    return Path(fichier).exists()


def limite_jarvis(fichier=REGLES_JARVIS):
    """LIMITE_PERTE_JOUR de prop-firm.txt (lecture seule), ou None si absente."""
    try:
        for ligne in Path(fichier).read_text(encoding="utf-8").splitlines():
            cle, sep, valeur = ligne.partition("=")
            if sep and cle.strip().upper() == "LIMITE_PERTE_JOUR" and valeur.strip():
                return float(valeur.strip().replace(",", "."))
    except (OSError, ValueError):
        pass
    return None


def charger(fichier=FICHIER_CONFIG, regles=REGLES_JARVIS):
    """Réglages complets : défauts, puis config_mgc.json, puis limite du jour de Jarvis."""
    config = dict(DEFAUTS)
    try:
        perso = json.loads(Path(fichier).read_text(encoding="utf-8"))
        config.update({k: v for k, v in perso.items() if k in DEFAUTS})
    except FileNotFoundError:
        pass
    if config["limite_perte_jour_usd"] is None:
        config["limite_perte_jour_usd"] = limite_jarvis(regles) or 1000.0
    return config


def empreinte(config):
    """Identifiant court de la version des réglages (gardé avec chaque analyse)."""
    texte = json.dumps(config, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:12]
