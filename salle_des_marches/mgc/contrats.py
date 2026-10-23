# -*- coding: utf-8 -*-
"""
Gestion des échéances MGC : contrat actif, contrat suivant, bascule de liquidité, restriction de rollover.

Dates (calendrier CME, voir calendrier_cme.py) :
  - dernier jour de négociation : 3e dernier jour ouvré du mois d'échéance ;
  - premier jour d'avis de livraison : dernier jour ouvré du mois précédent ;
  - bascule de liquidité estimée : N jours ouvrés avant le premier jour d'avis (réglage
    « bascule_jours_avant_avis »). Si les volumes réels sont fournis, ils priment.
"""

import datetime as dt

from . import calendrier_cme as cal
from .instrument import CODES_MOIS, code_contrat


class ContractManager:
    def __init__(self, config):
        self.config = config
        self.mois = sorted(CODES_MOIS[c] for c in config["mois_cotes"])

    # ------------------------------------------------------------------ dates d'un contrat
    @staticmethod
    def dernier_jour_negociation(annee, mois):
        return cal.dernier_jour_ouvre_du_mois(annee, mois, rang=3)

    @staticmethod
    def premier_jour_avis(annee, mois):
        precedent = (annee, mois - 1) if mois > 1 else (annee - 1, 12)
        return cal.dernier_jour_ouvre_du_mois(*precedent)

    def date_bascule(self, annee, mois):
        return cal.decaler_jours_ouvres(self.premier_jour_avis(annee, mois), -self.config["bascule_jours_avant_avis"])

    # ------------------------------------------------------------------ liste des échéances
    def echeances(self, depuis, nombre=4):
        """Les `nombre` prochaines échéances cotées encore négociables à la date `depuis`."""
        res, annee, mois = [], depuis.year, depuis.month
        while len(res) < nombre:
            if mois in self.mois and self.dernier_jour_negociation(annee, mois) >= depuis:
                res.append((annee, mois))
            annee, mois = (annee, mois + 1) if mois < 12 else (annee + 1, 1)
        return res

    # ------------------------------------------------------------------ état du jour
    def etat(self, jour, volumes=None):
        """Contrat actif et suivant pour la date `jour` (date de négociation).

        volumes : facultatif, {« MGCZ26 » : volume, ...}. Si le suivant traite déjà plus que l'actif,
        la bascule de liquidité est constatée et le suivant devient l'actif.
        """
        if isinstance(jour, dt.datetime):
            jour = cal.jour_de_negociation(jour)
        liste = self.echeances(jour, nombre=4)
        rang = next(i for i, (a, m) in enumerate(liste) if jour < self.date_bascule(a, m))
        actif, suivant = liste[rang], liste[rang + 1]
        motif = "bascule estimée d'après le calendrier"
        if volumes:
            v_actif, v_suivant = volumes.get(code_contrat(*actif), 0), volumes.get(code_contrat(*suivant), 0)
            if v_suivant > v_actif:
                actif, suivant = suivant, liste[rang + 2]
                motif = "bascule de liquidité constatée (le contrat suivant traite plus de volume)"
        bascule = self.date_bascule(*actif)
        avant_bascule = cal.jours_ouvres_entre(jour, bascule)
        limite = self.config["rollover_jours_restriction"]
        restriction = avant_bascule <= limite
        return {
            "contrat": code_contrat(*actif),
            "suivant": code_contrat(*suivant),
            "dernier_jour_negociation": self.dernier_jour_negociation(*actif).isoformat(),
            "jours_ouvres_avant_fin": cal.jours_ouvres_entre(jour, self.dernier_jour_negociation(*actif)),
            "bascule_estimee": bascule.isoformat(),
            "jours_ouvres_avant_bascule": avant_bascule,
            "choix": motif,
            "restriction_rollover": restriction,
            "motif_restriction": (f"Rollover proche : bascule vers {code_contrat(*suivant)} dans {avant_bascule} jour(s) "
                                  f"ouvré(s) (restriction à {limite} jours). Analyse informative seulement.")
            if restriction else "",
        }
