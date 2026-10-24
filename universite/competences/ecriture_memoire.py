# -*- coding: utf-8 -*-
"""
Agent 15 — le Scribe : un passage sur tout ce qui s'est passé depuis le précédent (missions, conversations avec le
directeur et le desk de Jarvis, sessions Claude du PC, règles décidées, alertes, PROJECT_STATUS.md, notes déposées).
Chaque chose devient un bloc rangé dans le dossier de son sujet ; l'index et les fichiers Markdown sont mis à jour.
Tourne en boucle (toutes les 5 minutes) ; ne produit pas de document : ses blocs SONT son travail.
"""

from .. import memoire

TYPE = "ecriture_memoire"
AGENT = memoire.SCRIBE
TITRE = "Noter en blocs ce qui s'est passé"
PARAMS = {}


def executer(ctx):
    roles = iter(["documentaliste", "documentaliste", "chercheur", "documentaliste", "connaissances"])

    def etape(libelle):
        ctx.etape(next(roles, "connaissances"), libelle)

    comptes = memoire.ecrire_tout(ctx.base, ctx.moteur.reglages, etape)
    ctx.detail(comptes)
    return comptes
