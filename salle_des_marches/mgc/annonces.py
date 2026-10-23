# -*- coding: utf-8 -*-
"""
Annonces économiques USD : classement et fenêtres de blocage.

Règles (décisions de Jabran du 17/10/2026, prop firm Topstep) :
  - jour de réunion du FOMC (décision de taux, communiqué, conférence de presse) : journée bloquée.
    C'est une règle PERSONNELLE de Jabran : Topstep ne l'impose pas ;
  - discours du président de la Fed : blocage 30 min avant et 30 min après ;
  - autre annonce USD à fort impact : blocage 90 min avant et 30 min après.
Un simple discours (« Fed Chair X Speaks ») ne fait PAS un jour de FOMC.
"""

import datetime as dt

from .calendrier_cme import PARIS

MOTS_REUNION = ("FOMC Statement", "Federal Funds Rate", "FOMC Press Conference", "FOMC Economic Projections")


def classer(titre, impact=""):
    """« reunion_fomc », « discours_fed », « forte » ou « autre »."""
    t = (titre or "").lower()
    if any(m.lower() in t for m in MOTS_REUNION):
        return "reunion_fomc"
    if ("fed chair" in t or "fed chairman" in t) and "speaks" in t:
        return "discours_fed"
    if str(impact).lower() in ("high", "fort"):
        return "forte"
    return "autre"


def blocages(instant, annonces, config):
    """Motifs de blocage à l'instant donné. annonces : [{« quand » : datetime avec fuseau, « titre », « impact »}]."""
    motifs = []
    aujourd_hui = instant.astimezone(PARIS).date()
    for a in annonces:
        quand, genre = a["quand"], classer(a.get("titre"), a.get("impact"))
        if isinstance(quand, str):  # format ISO (données passées en JSON)
            quand = dt.datetime.fromisoformat(quand)
        heure = quand.astimezone(PARIS).strftime("%Hh%M")
        if genre == "reunion_fomc" and quand.astimezone(PARIS).date() == aujourd_hui:
            motifs.append(f"Jour de réunion du FOMC ({a['titre']} à {heure}) : règle personnelle, journée bloquée.")
            continue
        if genre == "discours_fed":
            avant, apres = config["discours_fed_avant_min"], config["discours_fed_apres_min"]
        elif genre in ("forte", "reunion_fomc"):
            avant, apres = config["annonce_avant_min"], config["annonce_apres_min"]
        else:
            continue
        if quand - dt.timedelta(minutes=avant) <= instant <= quand + dt.timedelta(minutes=apres):
            motifs.append(f"Annonce USD ({a['titre']} à {heure}) : blocage de {avant} min avant à {apres} min après.")
    return list(dict.fromkeys(motifs))
