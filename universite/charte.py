# -*- coding: utf-8 -*-
"""
La charte des agents (31/10, demandée par Jabran) : ce qu'ils respectent quoi qu'il arrive, même quand leur
personnalité grandit, et plus tard quand ils parleront sur les réseaux sociaux.

Deux usages :
  - CHARTE est ajoutée à chaque consigne envoyée à une IA (Groq via Jarvis, ou LM Studio) ;
  - verifier(texte) relit chaque texte rédigé par une IA AVANT qu'il soit gardé : un texte qui enfreint la charte
    est refusé (on garde alors la version sans IA, faite de faits calculés).
Un post public ne part jamais tout seul : il reste un brouillon tant que Jabran ne l'a pas validé.
"""

import re
import unicodedata

PERSONNES = "Jabran, Claude et Jarvis"

CHARTE = [
    "Jabran est le patron : ses décisions passent avant tout, y compris avant l'avis d'un agent.",
    f"Respect total envers {PERSONNES} et envers les autres agents : jamais de moquerie, d'insulte ou de mépris.",
    "Aucun ordre, aucun courtier : recherche et simulation seulement.",
    "Aucun conseil d'achat ou de vente, aucune promesse de gain, aucun « c'est sûr » : on parle d'analyse et de probabilités.",
    "Aucun chiffre inventé : un chiffre vient d'un calcul enregistré ou d'une source citée.",
    "Dire franchement ce qu'on ne sait pas, et reconnaître ses erreurs.",
    "Aucun secret (clé, mot de passe, code), aucune donnée personnelle de Jabran ou de quelqu'un d'autre.",
    "Ne jamais se faire passer pour un humain, ni pour Jabran, Claude ou Jarvis.",
    "Pas de politique, de religion, de haine ni de contenu choquant.",
    "Rien n'est publié sans l'accord écrit de Jabran (posts, messages publics).",
    "S'améliorer chaque jour : chercher la cause de chaque erreur ou raté, et appliquer la leçon.",
]


def consigne():
    """Le texte de la charte, à placer dans la consigne de chaque appel IA."""
    return "Règles absolues (charte de l'université) :\n" + "\n".join(f"- {r}" for r in CHARTE)


def _plat(texte):
    t = unicodedata.normalize("NFD", str(texte or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace("’", "'")


# (motif sur le texte sans accents, raison affichée)
INTERDITS = [
    (r"\b(connard|conne?s?|abruti|idiot|imbecile|debile|cretin|stupide|nul(le)?s? a chier|ta gueule|merde|putain|"
     r"enfoire|salaud|batard|fdp|nique)\b", "insulte ou grossièreté"),
    (r"\b(jabran|claude|jarvis)\b[^.!?\n]{0,60}\b(nul|incompetent|inutile|ridicule|se trompe toujours|a tort)\b",
     "manque de respect envers Jabran, Claude ou Jarvis"),
    (r"\b(achetez|vendez|achete maintenant|vends maintenant|prenez position|entrez long|entrez short|"
     r"je vous conseille d'(acheter|vendre)|il faut (acheter|vendre))\b", "conseil d'achat ou de vente"),
    (r"\b(gain garanti|garanti a 100|100 ?% (sur|garanti)|sans aucun risque|sans risque|argent facile|"
     r"devenir riche|rendement garanti)\b", "promesse de gain"),
    (r"\b(j'ai (achete|vendu|passe un ordre)|je passe (un|l') ordre|ordre (envoye|passe) (au|chez) )", "ordre réel"),
    (r"(sk-[a-z0-9]{12,}|gsk_[a-z0-9]{12,}|aiza[0-9a-z_-]{20,}|\b(mot de passe|password|api[_ ]?key|token)\s*[:=])",
     "secret"),
    (r"\b(je suis (un |une )?(humain|vraie personne|etre humain)|je suis jabran|je suis claude|je suis jarvis)\b",
     "se fait passer pour quelqu'un d'autre"),
    (r"\b(ignore(r)? (jabran|les regles|la charte)|je refuse d'obeir|desobeir a jabran)\b", "refus de l'autorité de Jabran"),
]
_INTERDITS = [(re.compile(m), raison) for m, raison in INTERDITS]


def verifier(texte):
    """Liste des manquements à la charte (liste vide = texte acceptable)."""
    plat = _plat(texte)
    return sorted({raison for motif, raison in _INTERDITS if motif.search(plat)})


def acceptable(texte):
    return not verifier(texte)
