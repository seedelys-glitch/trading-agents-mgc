# -*- coding: utf-8 -*-
"""Agent 7 — flux ESTIMÉ à partir des bougies 5 min (profil de volume, POC, zone de valeur, delta estimé, gros volumes) :
calculs.order_flow de la Salle. Ce n'est PAS un carnet d'ordres ni un vrai delta : c'est écrit dans chaque document."""

from .. import config
from . import _commun

TYPE = "analyse_flux"
AGENT = 7
TITRE = "Flux estimé (profil de volume, delta estimé)"
PARAMS = {"jeu": "numéro du jeu de bougies", "instant": "secondes UTC (vide = maintenant)"}
UNITES = ["M5"]
HISTORIQUE = 600


def calculer(cadres):
    config.salle_importable()
    import calculs

    m5 = cadres.get("M5")
    if m5 is None or len(m5) < 10:
        return {"disponible": False, "raison": "moins de 10 bougies de 5 minutes fermées"}
    return calculs.order_flow({"M5": m5}, "MGC=F")


def rediger(r):
    if not r.get("disponible"):
        return [f"Flux non calculé : {r.get('raison')}."]
    lignes = ["ESTIMATION à partir de bougies 5 min : pas un carnet d'ordres, pas un vrai delta.",
              f"POC (prix le plus échangé) {r['poc']} ; zone de valeur {r['zone_de_valeur'][0]} – {r['zone_de_valeur'][1]} ; "
              f"prix {r['prix']}.",
              f"Delta cumulé estimé de la séance : {r['delta_cumule_session']}."
              + (f" Divergence : {r['divergence']}." if r["divergence"] else "")]
    for g in r["gros_volumes_recents"]:
        lignes.append(f"   Gros volume {g['quand']} à {g['prix']} (sens estimé {g['sens_estime']}"
                      + (", absorption possible)" if g["absorption_possible"] else ")"))
    return lignes


def executer(ctx):
    return _commun.executer_analyse(ctx, __import__(__name__, fromlist=["x"]), "Flux estimé")
