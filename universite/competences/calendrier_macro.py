# -*- coding: utf-8 -*-
"""
Agent 5 — calendrier économique USD : télécharge le flux public de la semaine (Forex Factory, gratuit, sans clé),
GARDE chaque annonce dans la base (l'historique se construit ainsi au fil des semaines, pour l'agent 12), puis
dit ce qui arrive dans les 48 h et ce qui bloque maintenant selon les règles de Jabran (mgc/annonces.py) :
jour de FOMC bloqué, discours du président de la Fed 30 min avant / après, annonce forte 90 min avant / 30 après.
Les heures sont celles de la source, converties en heure de Paris. Rien n'est deviné quand la source ne répond pas.
"""

import datetime as dt
import time
from zoneinfo import ZoneInfo

from .. import config

TYPE = "calendrier_macro"
AGENT = 5
TITRE = "Calendrier des annonces USD (48 h) et blocages"
PARAMS = {}
SOURCE = "Forex Factory (flux public de la semaine)"
PARIS = ZoneInfo("Europe/Paris")
maintenant = time.time          # remplacé dans les tests


def telecharger():
    """Remplacé dans les tests. Sur le PC : le même flux que la Salle des marchés (calculs.telecharger_calendrier)."""
    config.salle_importable()
    import calculs

    return calculs.telecharger_calendrier()


def enregistrer(base, evenements, source=SOURCE):
    """Annonces USD -> table annonces (une ligne par annonce ; prévision / précédent mis à jour). Renvoie (nouvelles, total)."""
    config.salle_importable()
    from mgc import annonces

    nouvelles = total = 0
    recu = time.time()
    for e in evenements:
        if e.get("country") != "USD" or not e.get("title"):
            continue
        try:
            quand = dt.datetime.fromisoformat(str(e["date"])).timestamp()
        except (KeyError, ValueError):
            continue
        total += 1
        titre = str(e["title"])[:200]
        avant = base.un("SELECT id FROM annonces WHERE quand=? AND titre=? AND pays='USD'", (quand, titre))
        if avant:
            base.ecrire("UPDATE annonces SET impact=?, genre=?, prevision=?, precedent=?, maj=? WHERE id=?",
                        (str(e.get("impact", "")), annonces.classer(titre, e.get("impact")), str(e.get("forecast", "")),
                         str(e.get("previous", "")), recu, avant["id"]))
            continue
        base.ecrire("INSERT INTO annonces(quand, titre, pays, impact, genre, prevision, precedent, source, recu_le, maj)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (quand, titre, "USD", str(e.get("impact", "")), annonces.classer(titre, e.get("impact")),
                     str(e.get("forecast", "")), str(e.get("previous", "")), source, recu, recu))
        nouvelles += 1
    return nouvelles, total


def heure(ts):
    return dt.datetime.fromtimestamp(ts, PARIS).strftime("%a %d/%m %Hh%M")


def reglages_annonces():
    config.salle_importable()
    from mgc import config as cfg

    try:
        r = cfg.charger()
    except (OSError, ValueError):
        r = dict(cfg.DEFAUTS)
    return {k: r[k] for k in ("annonce_avant_min", "annonce_apres_min", "discours_fed_avant_min", "discours_fed_apres_min")}


def executer(ctx):
    config.salle_importable()
    from mgc import annonces

    instant = maintenant()
    ctx.etape("documentaliste", f"Télécharge le calendrier de la semaine ({SOURCE})")
    try:
        evenements = telecharger()
    except Exception as e:          # réseau, format : on le dit, on n'invente rien
        raise OSError(f"calendrier indisponible ({type(e).__name__})") from e
    ctx.etape("connaissances", "Range les annonces USD dans l'historique de l'université")
    nouvelles, total = enregistrer(ctx.base, evenements)
    ctx.detail({"annonces_usd": total, "nouvelles": nouvelles})
    ctx.etape("chercheur", "Repère les annonces des 48 h et les blocages de maintenant")
    proches = ctx.base.lire("SELECT * FROM annonces WHERE quand BETWEEN ? AND ? AND (genre<>'autre' OR impact='Medium')"
                            " ORDER BY quand", (instant - 2 * 3600, instant + 48 * 3600))
    reg = reglages_annonces()
    liste = [{"quand": dt.datetime.fromtimestamp(a["quand"], dt.UTC), "titre": a["titre"], "impact": a["impact"]}
             for a in ctx.base.lire("SELECT * FROM annonces WHERE quand BETWEEN ? AND ?", (instant - 86400, instant + 86400))]
    blocages = annonces.blocages(dt.datetime.fromtimestamp(instant, dt.UTC), liste, reg)
    ctx.etape("professeur", "Rédige le point macro")
    noms = {"reunion_fomc": "FOMC", "discours_fed": "discours du président de la Fed", "forte": "fort", "autre": "moyen"}
    lignes = [f"Source : {SOURCE}, téléchargée à {heure(instant)} (heure de Paris). {total} annonce(s) USD cette "
              f"semaine, dont {nouvelles} nouvelle(s) dans l'historique.", "",
              "Maintenant : " + ("; ".join(blocages) if blocages else "aucun blocage lié aux annonces."), "",
              "Prochaines 48 h :" if proches else "Aucune annonce USD forte ou moyenne dans les 48 h."]
    lignes += [f"   {heure(a['quand'])} — {a['titre']} ({noms[a['genre']]})"
               + (f" ; prévision {a['prevision']}, précédent {a['precedent']}" if a["prevision"] or a["precedent"] else "")
               for a in proches]
    lignes += ["", "Règles appliquées (Jabran, 17/10) : jour de FOMC bloqué ; discours du président de la Fed "
               f"{reg['discours_fed_avant_min']} min avant / {reg['discours_fed_apres_min']} après ; annonce forte "
               f"{reg['annonce_avant_min']} min avant / {reg['annonce_apres_min']} après.",
               "Limite : la source ne donne pas le chiffre publié ; les heures peuvent bouger, revérifier le jour même."]
    doc = ctx.document("macro", f"Point macro — {heure(instant)}", "\n".join(lignes),
                       donnees={"instant": instant, "reglages": reg, "blocages": blocages,
                                "annonces": [a["id"] for a in proches], "total": total, "nouvelles": nouvelles},
                       sources=[{"source": SOURCE, "telecharge": instant}], role="professeur", statut="a_verifier")
    verif = ctx.demander(9, "verification_calendrier", f"Contrôler le point macro (document {doc})", {"document": doc},
                         "Refaire les blocages à partir de l'historique.", document=doc)
    if blocages:
        ctx.message(8, "alerte", "Blocage annonces : " + "; ".join(blocages)[:300], doc)
    return {"document": doc, "verification": verif, "blocages": blocages, "a_venir": len(proches)}
