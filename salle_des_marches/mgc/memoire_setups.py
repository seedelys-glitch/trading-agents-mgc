# -*- coding: utf-8 -*-
"""
Agent « Mémoire » : à quels setups passés de Jabran ressemble la configuration du jour ? (calcul, aucune IA)

Il lit le journal des setups du dossier « bot trad » (journal_setups.csv, tenu par la veille) et compte, parmi les
setups qui ressemblent à celui du desk, combien ont touché un objectif et combien ont fini au stop.
Ressemblance, du plus précis au plus large (le premier critère qui réunit au moins 5 setups est gardé) :
  1. même sens + même niveau de Fibo + même session (Asie, Londres, New York) ;
  2. même sens + même niveau de Fibo ;
  3. même niveau de Fibo.
Moins de 5 setups semblables : « pas assez de setups », jamais de pourcentage tiré de 2 ou 3 cas.
Avis seulement : il ne change pas le statut du desk.
"""

import datetime as dt
import re
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from veille.journal_setups import COLUMNS, JOURNAL, bot_dir, plain, session_of
except ImportError:  # lancé autrement (python -m salle_des_marches...)
    from salle_des_marches.veille.journal_setups import COLUMNS, JOURNAL, bot_dir, plain, session_of

MINIMUM = 5
GAGNANT = re.compile(r"tp|gagn|objectif")
PERDANT = re.compile(r"(?<![a-z])(stop|sl|perdu|perte)(?![a-z])")


def lire(dossier=None):
    d = Path(dossier) if dossier else bot_dir()
    if d is None or not (d / JOURNAL).is_file():
        return []
    texte = (d / JOURNAL).read_text(encoding="utf-8-sig", errors="replace")
    lignes = [ln for ln in texte.splitlines() if ln.strip()][1:]
    col = {c: i for i, c in enumerate(COLUMNS)}
    res = []
    for ln in lignes:
        r = ln.split(";")
        if len(r) < 20:
            continue
        issue = plain(r[col["Resultat"]])
        res.append({
            "sens": plain(r[col["Sens"]]).strip(),
            "niveau": r[col["Niveau entree"]].strip().split(" ")[0].replace(",", "."),
            "session": r[col["Session"]].strip(),
            "issue": "gagnant" if GAGNANT.search(issue) else "perdant" if PERDANT.search(issue) else "?",
        })
    return res


def comparer(config_trade, maintenant=None, dossier=None, setups=None):
    """Résumé des setups passés qui ressemblent à `config_trade` (sens « achat » / « vente », niveau « 0.705»...)."""
    if not config_trade:
        return None
    setups = setups if setups is not None else lire(dossier)
    if not setups:
        return {"total": 0, "texte": "Agent Mémoire : ton journal des setups est vide ou introuvable "
                                     "(dossier « bot trad »)."}
    maintenant = (maintenant or dt.datetime.now(dt.UTC)).astimezone(ZoneInfo("Europe/Paris"))
    sens = "long" if config_trade["sens"] == "achat" else "short"
    niveau = str(config_trade.get("niveau"))
    session = session_of(maintenant.date(), maintenant.hour + maintenant.minute / 60)
    criteres = [
        (f"{'achats' if sens == 'long' else 'ventes'} sur le {niveau} en session {session}",
         lambda s: s["sens"] == sens and s["niveau"] == niveau and s["session"] == session),
        (f"{'achats' if sens == 'long' else 'ventes'} sur le {niveau}", lambda s: s["sens"] == sens and s["niveau"] == niveau),
        (f"setups sur le {niveau}", lambda s: s["niveau"] == niveau),
    ]
    for nom, filtre in criteres:
        semblables = [s for s in setups if filtre(s) and s["issue"] != "?"]
        if len(semblables) >= MINIMUM:
            gagnants = sum(s["issue"] == "gagnant" for s in semblables)
            taux = round(100 * gagnants / len(semblables))
            return {"critere": nom, "total": len(semblables), "gagnants": gagnants,
                    "perdants": len(semblables) - gagnants, "taux_pct": taux,
                    "texte": f"Agent Mémoire : tes {nom} : {len(semblables)} dans ton journal, {gagnants} gagnant(s), "
                             f"{len(semblables) - gagnants} au stop ({taux} % de réussite)."}
    return {"total": 0, "texte": f"Agent Mémoire : pas assez de setups semblables dans ton journal (il en faut "
                                 f"{MINIMUM} avec un résultat noté) pour un {niveau} en {sens}."}
