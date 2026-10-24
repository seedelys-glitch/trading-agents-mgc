"""
Analyse des actus pour le gold (déménagée de Jarvis vers la veille du desk le 24/10/2026) : Jarvis collecte
les posts de Trump et les mails importants (Gmail reste chez lui), le desk les traduit et note leur impact
sur le gold avec l'IA locale (POST /api/actus/analyser {"texte", "source"}). Sans IA : impact estimé par mots-clés.
"""

from __future__ import annotations

import json
import re

GOLD_WORDS = ("tariff", "tarif", "fed", "powell", "rate", "taux", "inflation", "dollar", "gold",
              "or ", "china", "chine", "russia", "russie", "iran", "israel", "war", "guerre",
              "sanction", "oil", "pétrole", "petrole", "debt", "dette", "treasury", "bond",
              "trade", "deal", "recession", "jobs", "emploi", "cpi", "opec", "nuclear", "missile",
              "strike", "bitcoin", "crypto", "bank", "banque", "shutdown", "default")

PROMPT = """Tu es analyste macro pour un trader de gold (XAU/USD, Micro Gold).
Analyse ce texte ({source}) et réponds UNIQUEMENT avec un objet JSON, sans rien d'autre :
{{"impact": "fort" | "moyen" | "faible",
  "sens": "haussier" | "baissier" | "neutre",
  "resume": "une phrase en français qui dit ce qui compte pour le gold",
  "traduction": "traduction française fidèle et complète du texte (résumée si très long, 120 mots max)"}}
Fort = peut faire bouger le gold dans la journée (droits de douane, Fed/taux, inflation, guerre,
sanctions, dollar, accord commercial majeur, dette US). Faible = politique intérieure, campagne,
attaques personnelles, sport, félicitations.

Texte :
\"\"\"{text}\"\"\""""


def _heuristic(text: str) -> str:
    t = text.lower()
    hits = sum(1 for w in GOLD_WORDS if w in t)
    return "fort" if hits >= 3 else "moyen" if hits >= 1 else "faible"


def analyse(ia, text: str, source: str) -> dict:
    res = None
    raw = ia.complete(PROMPT.format(source=source, text=text[:4000]))
    if raw:
        m = re.search(r"\{.*\}", raw, flags=re.S)
        if m:
            try:
                res = json.loads(m.group(0))
            except Exception:
                res = None
    if not res:
        res = {"impact": _heuristic(text), "sens": "neutre",
               "resume": "", "traduction": "(traduction indisponible : LM Studio éteint)", "secours": True}
    res["impact"] = str(res.get("impact", "faible")).lower().strip()
    if res["impact"] not in ("fort", "moyen", "faible"):
        res["impact"] = _heuristic(text)
    return res
