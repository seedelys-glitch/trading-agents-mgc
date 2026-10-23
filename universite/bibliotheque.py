# -*- coding: utf-8 -*-
"""
Bibliothèque de connaissances : règles proposées par les agents, validées (ou rejetées) par Jabran, avec versions.

- Extraction : les règles sont LUES dans des fichiers de Jabran (STRATEGIE.md...) : chaque point de liste devient
  une règle proposée, avec sa source exacte (fichier, section, ligne). Rien n'est reformulé ni inventé.
- Versions : si le texte d'une règle change dans le fichier, une nouvelle version est proposée ; l'ancienne reste
  valable jusqu'à ce que Jabran valide la nouvelle (elle passe alors « remplacée »). Rien n'est effacé.
- Recherche : par mots (toujours disponible) et, si LM Studio a un modèle d'embeddings, par le sens.
"""

import hashlib
import json
import math
import re
import time
import unicodedata
import urllib.request
from pathlib import Path

STATUTS = ("proposee", "validee", "rejetee", "remplacee")
TAILLE_EXTRAIT = 900


def _simple(texte):
    t = unicodedata.normalize("NFKD", texte.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _cle(theme, rang):
    return re.sub(r"[^a-z0-9]+", "-", _simple(theme)).strip("-")[:50] + f"-{rang}"


def lire_regles(texte, fichier):
    """Markdown -> règles [{cle, theme, titre, texte, source}]. Un point de liste de premier niveau = une règle,
    ses sous-points (indentés ou numérotés) en font partie."""
    regles, theme, rang, courante = [], "Général", 0, None
    for numero, ligne in enumerate(texte.splitlines(), 1):
        if ligne.startswith("#"):
            theme, rang, courante = ligne.lstrip("#").strip() or "Général", 0, None
            continue
        if re.match(r"^[-*] \S", ligne):
            rang += 1
            contenu = ligne[2:].strip()
            courante = {"cle": _cle(theme, rang), "theme": theme, "titre": contenu[:90], "lignes": [contenu],
                        "source": {"fichier": str(fichier), "section": theme, "ligne": numero}}
            regles.append(courante)
        elif courante is not None and ligne.strip() and (ligne[:1].isspace() or re.match(r"^\d+\. ", ligne)):
            courante["lignes"].append(ligne.strip())
        elif not ligne.strip():
            continue
        else:
            courante = None
    for r in regles:
        r["texte"] = "\n".join(r.pop("lignes"))
    return regles


def derniere(base, cle):
    return base.un("SELECT * FROM regles WHERE cle=? ORDER BY version DESC LIMIT 1", (cle,))


def proposer(base, regle, agent):
    """Ajoute la règle si elle est nouvelle ou si son texte a changé. Renvoie 'nouvelle', 'version' ou None."""
    avant = derniere(base, regle["cle"])
    if avant and avant["texte"] == regle["texte"]:
        return None
    base.ecrire("INSERT INTO regles(cle, version, titre, texte, theme, source, propose_par, precedente, cree)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (regle["cle"], (avant["version"] + 1) if avant else 1, regle["titre"], regle["texte"], regle["theme"],
                 json.dumps(regle["source"], ensure_ascii=False), agent, avant["id"] if avant else None, time.time()))
    return "version" if avant else "nouvelle"


def decider(base, ident, decision, note=""):
    """Décision de Jabran sur une règle proposée : 'validee' ou 'rejetee'."""
    if decision not in ("validee", "rejetee"):
        raise ValueError("décision inconnue")
    r = base.un("SELECT * FROM regles WHERE id=?", (ident,))
    if not r:
        raise ValueError("règle introuvable")
    if r["statut"] != "proposee":
        raise ValueError(f"cette règle est déjà « {r['statut']} »")
    with base._ecriture:
        base.ecrire("UPDATE regles SET statut=?, decide_par='jabran', decision_le=?, note=? WHERE id=?",
                    (decision, time.time(), str(note)[:500], ident))
        if decision == "validee":
            base.ecrire("UPDATE regles SET statut='remplacee' WHERE cle=? AND id<>? AND statut='validee'",
                        (r["cle"], ident))
    base.evenement("bibliotheque", f"Règle « {r['titre'][:60]} » (v{r['version']}) : {decision} par Jabran.")
    return base.un("SELECT * FROM regles WHERE id=?", (ident,))


def modifier(base, ident, texte):
    """Jabran corrige le texte : une nouvelle version est proposée (l'ancienne est gardée)."""
    r = base.un("SELECT * FROM regles WHERE id=?", (ident,))
    if not r:
        raise ValueError("règle introuvable")
    texte = str(texte).strip()
    if not texte:
        raise ValueError("texte vide")
    source = dict(r["source"])
    source["modifiee_par"] = "jabran"
    regle = {"cle": r["cle"], "theme": r["theme"], "titre": texte.splitlines()[0][:90], "texte": texte, "source": source}
    proposer(base, regle, None)
    return derniere(base, r["cle"])


# ---------------------------------------------------------------- extraits et recherche
def decouper(texte, taille=TAILLE_EXTRAIT):
    """Paragraphes regroupés en extraits d'environ `taille` caractères (sans couper un paragraphe)."""
    morceaux, courant = [], ""
    for p in re.split(r"\n\s*\n", texte):
        if courant and len(courant) + len(p) > taille:
            morceaux.append(courant.strip())
            courant = ""
        courant += p + "\n\n"
    if courant.strip():
        morceaux.append(courant.strip())
    return morceaux


def indexer_texte(base, origine, titre, texte):
    """Remplace les extraits d'une origine si son contenu a changé. Renvoie le nombre d'extraits écrits."""
    empreinte = hashlib.sha256(texte.encode("utf-8")).hexdigest()
    deja = base.un("SELECT empreinte FROM extraits WHERE origine=? LIMIT 1", (origine,))
    if deja and deja["empreinte"] == empreinte:
        return 0
    morceaux = decouper(texte)
    with base._ecriture:
        base.ecrire("DELETE FROM extraits WHERE origine=?", (origine,))
        for i, m in enumerate(morceaux):
            base.ecrire("INSERT INTO extraits(origine, titre, position, texte, empreinte, cree) VALUES (?,?,?,?,?,?)",
                        (origine, titre, i, m, empreinte, time.time()))
    return len(morceaux)


def embeddings(url, modele, textes, delai=60):
    """Vecteurs par LM Studio (/v1/embeddings). Lève OSError si le service ou le modèle manque."""
    corps = json.dumps({"model": modele, "input": textes}).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + "/embeddings", data=corps, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=delai) as r:
        donnees = json.loads(r.read().decode("utf-8"))
    try:
        return [d["embedding"] for d in sorted(donnees["data"], key=lambda d: d["index"])]
    except (KeyError, TypeError) as e:
        raise OSError(f"réponse d'embeddings inattendue : {e}") from e


def vectoriser(base, url, modele, lot=16):
    """Ajoute un vecteur aux extraits qui n'en ont pas. Renvoie le nombre traité."""
    faits = 0
    while True:
        a_faire = base.lire("SELECT id, texte FROM extraits WHERE vecteur IS NULL OR modele<>? LIMIT ?", (modele, lot))
        if not a_faire:
            return faits
        vecteurs = embeddings(url, modele, [x["texte"] for x in a_faire])
        for x, v in zip(a_faire, vecteurs, strict=True):
            base.ecrire("UPDATE extraits SET vecteur=?, modele=? WHERE id=?", (json.dumps(v), modele, x["id"]))
        faits += len(a_faire)


def _mots(texte):
    return [m for m in re.findall(r"[a-z0-9]+", _simple(texte)) if len(m) > 2]


def rechercher(base, question, n=8, vecteur_question=None):
    """Recherche par mots (score type BM25), complétée par le sens si un vecteur de question est fourni."""
    extraits = base.lire("SELECT id, origine, titre, position, texte, vecteur FROM extraits")
    regles = base.lire("SELECT id, titre, texte, statut, version, theme FROM regles WHERE statut IN ('validee','proposee')")
    documents = [("extrait", e) for e in extraits] + [("regle", r) for r in regles]
    if not documents:
        return []
    q = _mots(question)
    sacs = [_mots(d["texte"]) for _, d in documents]
    moyenne = sum(map(len, sacs)) / len(sacs) or 1
    freq = {m: sum(m in s for s in sacs) for m in set(q)}
    resultats = []
    for (genre, d), sac in zip(documents, sacs, strict=True):
        score = 0.0
        for m in q:
            tf = sac.count(m)
            if tf:
                idf = math.log(1 + (len(sacs) - freq[m] + 0.5) / (freq[m] + 0.5))
                score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * len(sac) / moyenne))
        sens = None
        if vecteur_question and genre == "extrait" and d.get("vecteur"):
            v = json.loads(d["vecteur"])
            na, nb = math.sqrt(sum(x * x for x in v)), math.sqrt(sum(x * x for x in vecteur_question))
            if na and nb:
                sens = sum(a * b for a, b in zip(v, vecteur_question, strict=False)) / (na * nb)
                score += 3 * max(0.0, sens)
        if score > 0:
            resultats.append({"genre": genre, "id": d["id"], "titre": d["titre"], "texte": d["texte"][:600],
                              "origine": d.get("origine"), "statut": d.get("statut"), "score": round(score, 3),
                              "sens": None if sens is None else round(sens, 3)})
    resultats.sort(key=lambda r: -r["score"])
    return resultats[:n]


def fichiers_par_defaut():
    """Fichiers de référence de Jabran (lecture seule) ; ceux qui n'existent pas sont ignorés."""
    import os
    maison = Path(os.environ.get("USERPROFILE", str(Path.home())))
    return [maison / "Desktop" / "bot trad" / "STRATEGIE.md"]
