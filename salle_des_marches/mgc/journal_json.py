# -*- coding: utf-8 -*-
"""
Journal structuré (une ligne JSON par événement) dans rapports\\salle\\evenements.jsonl, secrets masqués.

Le même masquage s'applique à serveur.log (FiltreSecrets) : une clé API ou un token Telegram ne doit jamais
finir écrit en clair dans un fichier, même dans un message d'erreur.
"""

import datetime as dt
import json
import logging
import re
from pathlib import Path

FICHIER = Path(__file__).resolve().parent.parent.parent / "rapports" / "salle" / "evenements.jsonl"

MOTIFS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),                    # Google / Gemini
    re.compile(r"gsk_[0-9A-Za-z]{20,}"),                       # Groq
    re.compile(r"sk-[0-9A-Za-z_\-]{16,}"),                     # DeepSeek, OpenAI...
    re.compile(r"\b\d{6,12}:[0-9A-Za-z_\-]{30,}\b"),           # token de bot Telegram
    re.compile(r"(?i)bearer\s+[0-9A-Za-z._\-]{10,}"),
    re.compile(r"(?i)\b(api[_-]?key|token|password|mot[_ ]de[_ ]passe|secret)\b(\s*[=:]\s*)\S+"),
]


def masquer(texte):
    if not isinstance(texte, str):
        return texte
    for motif in MOTIFS[:-1]:
        texte = motif.sub("[masqué]", texte)
    return MOTIFS[-1].sub(lambda m: f"{m.group(1)}{m.group(2)}[masqué]", texte)


def _nettoyer(valeur):
    if isinstance(valeur, dict):
        return {k: _nettoyer(v) for k, v in valeur.items()}
    if isinstance(valeur, (list, tuple)):
        return [_nettoyer(v) for v in valeur]
    return masquer(valeur)


def ecrire(genre, message, niveau="info", fichier=FICHIER, **champs):
    ligne = {"quand": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "niveau": niveau, "genre": genre,
             "message": message, **champs}
    Path(fichier).parent.mkdir(parents=True, exist_ok=True)
    with open(fichier, "a", encoding="utf-8") as f:
        f.write(json.dumps(_nettoyer(ligne), ensure_ascii=False, default=str) + "\n")


class FiltreSecrets(logging.Filter):
    """À poser sur un gestionnaire de logs : masque les secrets du message final."""

    def filter(self, record):
        record.msg = masquer(record.getMessage())
        record.args = ()
        return True
