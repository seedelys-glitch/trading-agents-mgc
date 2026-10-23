# -*- coding: utf-8 -*-
"""
Backtest de la stratégie V1 sur l'historique H1 disponible, avec rapport.

  python lancer_backtest.py            (Yahoo GC=F, environ 2 ans d'historique H1)
  python lancer_backtest.py FICHIER.csv  (export NinjaTrader MGC_H1.csv, quand il existera)

Écrit rapports\\backtest\\backtest-AAAA-MM-JJ.json (tous les trades) et docs\\BACKTEST.md (synthèse).
"""

import datetime as dt
import json
import sys
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

from mgc import backtest  # noqa: E402
from mgc import config as cfg  # noqa: E402
from mgc import source_ninja, sources  # noqa: E402

SORTIE = ICI.parent / "rapports" / "backtest"
DOC = ICI.parent / "docs" / "BACKTEST.md"


def charger(fichier=None):
    if fichier:
        return source_ninja.lire_bougies(fichier), f"NinjaTrader ({Path(fichier).name})"
    return sources.depuis_yahoo(sources.yahoo_brut("GC=F", "730d", "1h")), "Yahoo GC=F (contrat continu, différé)"


def pct(x):
    return "–" if x is None else f"{x:.0%}"


def val(x, suffixe=""):
    return "–" if x is None else f"{x:g}{suffixe}"


def ligne(nom, s):
    if not s["nombre"]:
        return f"| {nom} | 0 | – | – | – | – | – | – |"
    return (f"| {nom} | {s['nombre']} | {pct(s['taux_reussite'])} | {pct(s['wilson_95'][0])}–{pct(s['wilson_95'][1])} | "
            f"{val(s['esperance_R'], ' R')} | {val(s['profit_factor'])} | {val(s['drawdown_max_R'], ' R')} | "
            f"{val(s['total_usd'], ' $')} |")


def ecrire_doc(r, source, duree):
    entete = "| | trades | réussite | Wilson 95 % | espérance | profit factor | drawdown max | total |\n|---|---|---|---|---|---|---|---|"
    lignes = [
        "# Backtest de la stratégie V1 (1H / 12H)",
        "",
        f"Généré le {dt.date.today():%d/%m/%Y} par `salle_des_marches/lancer_backtest.py` en {duree:.0f} s. "
        "**Aucune promesse de rentabilité** : c'est un rejeu prudent de règles fixées à l'avance, pas une prévision.",
        "",
        f"- Données : {source}, {r['bougies_H1']} bougies H1, du {r['periode'][0][:10]} au {r['periode'][1][:10]}.",
        f"- Découpage chronologique : première partie jusqu'au {r['coupure'][:10]} (60 %), puis hors échantillon (40 %). "
        "Aucun paramètre n'a été réglé sur ces résultats : les règles viennent de STRATEGIE.md et des réglages du 17/10.",
        f"- Signaux refusés : {r['refus']['risque']} par le moteur de risque, {r['refus']['fenetre']} hors fenêtre "
        f"15h30-20h ou séance fermée, {r['refus']['rollover']} près du rollover.",
        f"- Sorties : {', '.join(f'{k} ({v})' for k, v in r['sorties'].items()) or 'aucune'}.",
        "",
        "## Résultats (R = risque initial jusqu'au stop)",
        "",
        entete,
        ligne("Tout, brut", r["tout"]["brut"]),
        ligne("Tout, net (frais + glissement)", r["tout"]["net"]),
        ligne("Première partie, net", r["premiere_partie"]["net"]),
        ligne("Hors échantillon, net", r["hors_echantillon"]["net"]),
        "",
        f"Conclusion statistique : {r['tout']['net']['conclusion']}",
        "",
        "## Walk-forward (par trimestre, net)",
        "",
        entete,
        *[ligne(q, s) for q, s in r["walk_forward_trimestres"].items()],
        "",
        "## Par setup (net)",
        "",
        entete,
        *[ligne(k, s) for k, s in r["par_setup"].items()],
        "",
        "## Biais contrôlés et limites",
        "",
        "- Pas de regard vers le futur : à chaque bougie, seules les bougies passées sont lues ; entrée à l'ouverture "
        "suivante ; un test automatique vérifie que des bougies futures ne changent aucune décision passée.",
        "- Prudence : stop compté avant l'objectif dans une même bougie ; break-even effectif à la bougie suivante.",
        "- Pas de sélection : tous les signaux sont pris ; une impulsion ne sert qu'une fois.",
        "- **Non modélisé** : annonces (FOMC, NFP…) faute de calendrier historique ; sauts de rollover du contrat continu ; "
        "sorties partielles en fractions de contrat ; frais et glissement estimés (1,50 $ + 2 ticks par contrat).",
        "- Sortie forcée à 15h00 (Chicago), avant la limite Topstep de 15h10 (à vérifier dans tes règles Topstep).",
        "- Échantillon : en dessous de 30 trades, aucune conclusion n'est possible.",
    ]
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text("\n".join(lignes) + "\n", encoding="utf-8")


def main():
    debut = time.time()
    h1, source = charger(sys.argv[1] if len(sys.argv) > 1 else None)
    resultat = backtest.simuler(h1, cfg.charger())
    r = backtest.rapport(resultat)
    duree = time.time() - debut
    SORTIE.mkdir(parents=True, exist_ok=True)
    (SORTIE / f"backtest-{dt.date.today().isoformat()}.json").write_text(
        json.dumps({"source": source, "rapport": r, "trades": resultat["trades"]}, ensure_ascii=False, indent=1,
                   default=str), encoding="utf-8")
    ecrire_doc(r, source, duree)
    net = r["tout"]["net"]
    print(f"{r['nombre_trades']} trades en {duree:.0f} s ; net : espérance {net.get('esperance_R')} R, "
          f"total {net.get('total_usd')} $. {net['conclusion']}")


if __name__ == "__main__":
    main()
