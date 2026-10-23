# -*- coding: utf-8 -*-
"""
Agent 13 — adaptateur TradingView (gratuit, sans API ni abonnement de plus) : importe les fichiers CSV que Jabran
exporte depuis TradingView (menu du graphique « Exporter les données du graphique ») et dépose dans le dossier
`Documents\\TradingAgents\\donnees_tradingview`. Les exports du dossier Téléchargements dont le nom ressemble à un
export MGC / GC de TradingView sont aussi lus (lecture seule, rien n'est déplacé ni effacé).

Un fichier n'est importé qu'une fois (empreinte). Toutes les unités d'un même symbole vont dans le même jeu,
« TradingView <symbole> » ; une bougie déjà présente n'est jamais remplacée. Puis contrôle qualité du jeu.
"""

import hashlib
import os
import re
import time
from pathlib import Path

from .. import donnees

TYPE = "import_tradingview"
AGENT = 13
TITRE = "Importer les exports CSV de TradingView (dossier)"
PARAMS = {"dossier": "dossier à lire (vide = donnees_tradingview + exports MGC des Téléchargements)"}
NOM_EXPORT = re.compile(r"^(?:[A-Z_]+_)?(M?GC[A-Z0-9]*!?)\s*,\s*(\w+?)(?:_[0-9a-z]+)?(?: \(\d+\))?\.csv$", re.I)
UNITES_TV = {"1": "M1", "3": "M3", "5": "M5", "15": "M15", "60": "H1", "1D": "D1", "D": "D1"}
TAILLE_MAX = 50 * 1024 * 1024


def dossiers_par_defaut():
    maison = Path(os.environ.get("USERPROFILE", str(Path.home())))
    return [(Path(__file__).resolve().parents[2] / "donnees_tradingview", False), (maison / "Downloads", True)]


def a_lire(dossier, filtrer):
    """Fichiers CSV du dossier ; dans Téléchargements, seulement les noms d'export TradingView MGC / GC."""
    if not dossier.is_dir():
        return []
    return sorted(f for f in dossier.iterdir()
                  if f.is_file() and f.suffix.lower() == ".csv" and (not filtrer or NOM_EXPORT.match(f.name)))


def lire_nom(nom):
    """« COMEX_MINI_DL_MGC1!, 5_ab12c.csv » -> ("MGC1!", "M5"). (None, None) si le nom ne le dit pas."""
    m = NOM_EXPORT.match(nom)
    if not m:
        return None, None
    return m.group(1).upper(), UNITES_TV.get(m.group(2).upper())


def importer_fichier(base, chemin):
    brut = Path(chemin).read_bytes()
    if len(brut) > TAILLE_MAX:
        raise donnees.ErreurDonnees("fichier trop gros (plus de 50 Mo)")
    empreinte = hashlib.sha256(brut).hexdigest()
    if base.un("SELECT empreinte FROM fichiers_importes WHERE empreinte=?", (empreinte,)):
        return None
    lignes, rapport = donnees.lire_csv(brut.decode("utf-8-sig", errors="replace"))
    if not lignes:
        raise donnees.ErreurDonnees("aucune bougie valide")
    symbole, unite = lire_nom(Path(chemin).name)
    unite = unite or donnees.deviner_unite(lignes)
    symbole = symbole or "MGC"
    nom = f"TradingView {symbole}"
    jeu = base.un("SELECT id FROM jeux WHERE nom=? AND source='TradingView (dossier)'", (nom,))
    jeu = jeu["id"] if jeu else donnees.creer_jeu(
        base, nom, "TradingView (dossier)", symbole, temps_reel=False,
        note="Exports CSV réels de TradingView déposés par Jabran ; heures = début de bougie.")
    ajoutees = donnees.ajouter_bougies(base, jeu, unite, lignes)
    base.ecrire("INSERT INTO fichiers_importes(empreinte, chemin, jeu, unite, lignes, ajoutees, importe_le)"
                " VALUES (?,?,?,?,?,?,?)", (empreinte, str(chemin), jeu, unite, len(lignes), ajoutees, time.time()))
    return {"fichier": Path(chemin).name, "jeu": jeu, "unite": unite, "lignes": len(lignes), "ajoutees": ajoutees,
            "abimees": rapport["abimees"], "incoherentes": rapport["incoherentes"], "debut": lignes[0][0], "fin": lignes[-1][0]}


def executer(ctx):
    dossiers = [(Path(ctx.params["dossier"]), False)] if ctx.params.get("dossier") else dossiers_par_defaut()
    ctx.etape("documentaliste", "Cherche les nouveaux exports TradingView")
    fichiers = [f for d, filtrer in dossiers for f in a_lire(d, filtrer)]
    ctx.detail({"fichiers": len(fichiers), "dossiers": [str(d) for d, _ in dossiers]})
    ctx.etape("chercheur", f"Importe {len(fichiers)} fichier(s) déjà vus ou nouveaux (un fichier n'entre qu'une fois)")
    faits, erreurs = [], []
    for f in fichiers:
        ctx.verifier()
        try:
            r = importer_fichier(ctx.base, f)
        except (OSError, donnees.ErreurDonnees) as e:
            erreurs.append(f"{f.name} : {e}")
            continue
        if r:
            faits.append(r)
    ctx.etape("professeur", "Rédige le compte rendu d'import")
    lignes = [f"Dossiers lus : {', '.join(str(d) for d, _ in dossiers)}.",
              f"{len(fichiers)} fichier(s) CSV trouvés, {len(faits)} nouveau(x) importé(s)."]
    lignes += [f"   {r['fichier']} → jeu {r['jeu']}, {r['unite']} : {r['ajoutees']} bougie(s) ajoutée(s) sur {r['lignes']}"
               f" ({r['abimees']} abîmée(s), {r['incoherentes']} incohérente(s) ignorées)" for r in faits]
    lignes += [f"   Refusé : {e}" for e in erreurs]
    lignes += ["", "Données réelles exportées de TradingView (historiques, pas temps réel). Aucune bougie inventée ni corrigée."]
    ctx.etape("connaissances", "Classe le compte rendu et lance le contrôle qualité des jeux touchés", "verification")
    doc = ctx.document("donnees", f"Import TradingView — {len(faits)} fichier(s)", "\n".join(lignes),
                       donnees={"importes": faits, "erreurs": erreurs},
                       sources=[{"fichier": r["fichier"], "jeu": r["jeu"]} for r in faits], role="professeur",
                       statut="brouillon")
    for jeu in sorted({r["jeu"] for r in faits}):
        ctx.demander(13, "controle_donnees", f"Contrôler le jeu {jeu} après import TradingView", {"jeu": jeu},
                     "Trous, doublons, période couverte.")
    return {"document": doc, "importes": len(faits), "erreurs": erreurs}
