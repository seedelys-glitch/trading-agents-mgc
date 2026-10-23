# -*- coding: utf-8 -*-
"""
Trades RÉELS : lecture seule du journal de Jarvis (Documents\\Jarvis\\journal\\trades.jsonl).

Jarvis y note les trades dits à la voix et ceux importés de Tradovate / NinjaTrader. L'analyste n'y écrit jamais.
Sert à la perte du jour (moteur de risque) et aux chiffres réels de /stats.
"""

import datetime as dt
import json
import os
import re
from pathlib import Path

FICHIER = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents" / "Jarvis" / "journal" / "trades.jsonl"
NEGATIFS = ("perte", "perdu", "perds", "moins", "stop", "negatif", "négatif", "rouge", "loss")


def lire(fichier=FICHIER):
    """Lignes du journal ; None si le fichier n'existe pas (journal jamais rempli)."""
    try:
        texte = Path(fichier).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    lignes = []
    for ligne in texte.splitlines():
        try:
            lignes.append(json.loads(ligne))
        except ValueError:
            continue  # ligne abîmée : ignorée, comme le fait Jarvis
    return lignes


def pnl(ligne):
    """P&L en dollars : champ « pnl », sinon le texte « résultat » (« -80 dollars », « perte de 80 »...)."""
    v = ligne.get("pnl")
    if v not in (None, ""):
        try:
            return float(str(v).replace(",", "."))
        except ValueError:
            pass
    t = str(ligne.get("resultat", "")).lower()
    if any(m in t for m in ("break even", "breakeven", "break-even", "neutre")):
        return 0.0
    m = re.search(r"\d+(?:[.,]\d+)?", t)
    if not m:
        return None
    n = float(m.group().replace(",", "."))
    return -n if re.search(r"-\s*\d", t) or any(w in t for w in NEGATIFS) else n


def perte_du_jour(jour=None, fichier=FICHIER):
    """(perte du jour en $ positive ou 0, message). Seuls les trades fermés et notés dans Jarvis comptent."""
    jour = jour or dt.date.today()
    lignes = lire(fichier)
    if lignes is None:
        return 0.0, "Journal de Jarvis encore vide : le risque suppose une journée à zéro."
    du_jour = [r for r in lignes if r.get("date") == jour.strftime("%d/%m/%Y") and r.get("heure_sortie")]
    total = sum(p for p in (pnl(r) for r in du_jour) if p is not None)
    perte = round(max(0.0, -total), 2)
    return perte, (f"Journal de Jarvis : {len(du_jour)} trade(s) fermé(s) aujourd'hui, résultat {total:+.0f} $ "
                   "(seuls les trades notés ou importés comptent).")


def resume(fichier=FICHIER):
    """Chiffres des trades réels pour /stats."""
    lignes = lire(fichier)
    fermes = [r for r in lignes or [] if r.get("heure_sortie")]
    valeurs = [p for p in (pnl(r) for r in fermes) if p is not None]
    if not valeurs:
        return "Trades réels (journal de Jarvis) : aucun trade fermé noté."
    gagnants = sum(v > 0 for v in valeurs)
    return (f"Trades réels (journal de Jarvis) : {len(valeurs)} trade(s), {gagnants} gagnant(s), "
            f"total {sum(valeurs):+.0f} $.")
