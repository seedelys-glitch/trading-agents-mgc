# -*- coding: utf-8 -*-
"""
Agent « Règles Topstep » : où en est le compte par rapport aux règles de la prop firm (calcul, aucune IA).

Règles du compte Topstep 50K (Trading Combine, vérifiées le 24/10/2026 sur l'aide Topstep et
proptradingvibes.com, article du 09/10/2026) — remplaçables dans config_mgc.json :
  - perte maximale du compte (Maximum Loss Limit) : 2 000 $, qui SUIT le plus haut solde de FIN DE JOURNÉE
    (plancher = plus haut solde de fin de journée - 2 000 $) et s'arrête de monter au solde de départ ;
  - objectif : 3 000 $ ;
  - consistance : le meilleur jour doit rester sous 55 % de l'objectif ; sinon l'objectif monte à
    meilleur jour / 0,55 (le compte n'échoue pas) ;
  - taille max : 5 contrats mini = 50 micros (max_contrats de la config).
La limite de perte du JOUR de Jabran (1 000 $) reste gérée par risque.py et Jarvis.

Les soldes viennent de Jabran (« /solde 50340 » sur Telegram, ou « mon solde Topstep c'est 50 340 » à Jarvis) :
fichier rapports\\salle\\compte-topstep.json = {"solde_depart": 50000, "soldes": {"AAAA-MM-JJ": solde, ...}}.
Le dernier solde noté d'un jour sert de solde de fin de journée.
"""

import json
from datetime import date, datetime
from pathlib import Path

ICI = Path(__file__).resolve().parent.parent
FICHIER = ICI.parent / "rapports" / "salle" / "compte-topstep.json"

REGLES = {
    "perte_max_compte_usd": 2000.0,
    "objectif_usd": 3000.0,
    "consistance_pct": 55.0,
    "marge_securite_mll_usd": 250.0,   # jamais un trade qui laisserait moins que ça avant la perte max du compte
}


def lire(fichier=FICHIER):
    try:
        return json.loads(Path(fichier).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def noter_solde(montant, jour=None, fichier=FICHIER, solde_depart=50_000.0):
    """Enregistre le solde du compte (le dernier noté d'un jour = solde de fin de journée)."""
    montant = float(str(montant).replace(" ", "").replace(" ", "").replace(",", "."))
    if not 1_000 <= montant <= 1_000_000:
        raise ValueError(f"Solde impossible : {montant}")
    contenu = lire(fichier) or {"solde_depart": float(solde_depart), "soldes": {}}
    contenu.setdefault("soldes", {})[(jour or date.today()).isoformat()] = round(montant, 2)
    contenu["maj"] = datetime.now().isoformat(timespec="seconds")
    Path(fichier).parent.mkdir(parents=True, exist_ok=True)
    Path(fichier).write_text(json.dumps(contenu, ensure_ascii=False, indent=1), encoding="utf-8")
    return contenu


def regles(config=None):
    r = dict(REGLES)
    for cle in REGLES:
        if config and config.get(cle) is not None:
            r[cle] = float(config[cle])
    return r


def etat(config=None, contenu=None, aujourd_hui=None, fichier=FICHIER):
    """État du compte, ou None si aucun solde n'a été noté."""
    contenu = contenu if contenu is not None else lire(fichier)
    if not contenu or not contenu.get("soldes"):
        return None
    r = regles(config)
    aujourd_hui = (aujourd_hui or date.today()).isoformat()
    depart = float(contenu.get("solde_depart") or (config or {}).get("capital_usd") or 50_000)
    jours = sorted(contenu["soldes"].items())
    solde = float(jours[-1][1])
    # fins de journée = jours terminés (avant aujourd'hui) ; le plancher ne bouge qu'en fin de journée
    fins = [(j, float(s)) for j, s in jours if j < aujourd_hui]
    pic = max([depart] + [s for _, s in fins])
    plancher = min(pic - r["perte_max_compte_usd"], depart)
    gains, precedent = [], depart
    for j, s in jours:
        gains.append((j, round(s - precedent, 2)))
        precedent = s
    meilleur = max(gains, key=lambda g: g[1]) if gains else (None, 0.0)
    objectif = max(r["objectif_usd"], meilleur[1] / (r["consistance_pct"] / 100)) if meilleur[1] > 0 else r["objectif_usd"]
    hier = fins[-1][1] if fins else depart
    gain_du_jour = round(solde - hier, 2) if jours[-1][0] == aujourd_hui else 0.0
    limite_jour_consistance = round(r["consistance_pct"] / 100 * objectif, 2)
    return {
        "solde": solde,
        "solde_depart": depart,
        "plancher_perte_max": round(plancher, 2),
        "marge_avant_perte_max": round(solde - plancher, 2),
        "plancher_bloque": plancher >= depart,
        "profit": round(solde - depart, 2),
        "objectif": round(objectif, 2),
        "reste_objectif": round(objectif - (solde - depart), 2),
        "meilleur_jour": {"jour": meilleur[0], "gain": meilleur[1]},
        "gain_du_jour": gain_du_jour,
        "consistance_max_jour": limite_jour_consistance,
        "maj": contenu.get("maj"),
        "regles": r,
    }


def vetos(e, risque_total_usd=0.0):
    """Vetos (bloquants) : un trade qui rapprocherait trop de la perte max du compte."""
    if not e:
        return []
    reste = e["marge_avant_perte_max"] - float(risque_total_usd or 0)
    if reste < e["regles"]["marge_securite_mll_usd"]:
        return [f"Topstep : il ne te reste que {e['marge_avant_perte_max']:.0f} $ avant la perte max du compte "
                f"(plancher {e['plancher_perte_max']:.0f} $) ; ce trade risquerait {float(risque_total_usd or 0):.0f} $. "
                "Pas de trade : protège le compte."]
    return []


def limites(e):
    """Avertissements (statut au mieux ATTENDRE) : consistance du jour."""
    if not e:
        return []
    res = []
    if e["gain_du_jour"] > 0 and e["gain_du_jour"] >= 0.8 * e["consistance_max_jour"]:
        res.append(f"Topstep, consistance : tu as déjà gagné {e['gain_du_jour']:.0f} $ aujourd'hui ; au-delà de "
                   f"{e['consistance_max_jour']:.0f} $ (55 % de l'objectif) l'objectif du compte remonte. Ne force pas.")
    return res


def resume(e=None, config=None):
    e = e if e is not None else etat(config)
    if not e:
        return ("Règles Topstep : je n'ai pas encore ton solde. Envoie « /solde 50340 » sur Telegram ou dis à Jarvis "
                "« mon solde Topstep c'est 50 340 » (le dernier solde du jour compte comme fin de journée).")
    lignes = [f"Topstep : solde {e['solde']:.0f} $ (profit {e['profit']:+.0f} $, objectif {e['objectif']:.0f} $, "
              f"reste {max(0, e['reste_objectif']):.0f} $).",
              f"Perte max du compte : plancher à {e['plancher_perte_max']:.0f} $"
              + (" (bloqué au solde de départ)" if e["plancher_bloque"] else " (suit ton plus haut de fin de journée)")
              + f", il te reste {e['marge_avant_perte_max']:.0f} $ de marge.",
              f"Consistance : meilleur jour {e['meilleur_jour']['gain']:+.0f} $ ; ne dépasse pas "
              f"{e['consistance_max_jour']:.0f} $ de gain sur une journée."]
    lignes += limites(e)
    return "\n".join(lignes)
