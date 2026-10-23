# -*- coding: utf-8 -*-
"""
Agent 10 — discours de la Réserve fédérale : lit le flux officiel et public des discours (federalreserve.gov, gratuit),
garde le texte de chaque nouveau discours dans la bibliothèque (pour l'historien, agent 11), puis compte les
expressions d'un LEXIQUE FIXÉ À L'AVANCE (côté « faucon » = plutôt contre l'or, côté « colombe » = plutôt pour l'or)
et cite les phrases exactes. C'est une lecture simple et transparente, pas une interprétation : c'est écrit.
"""

import datetime as dt
import email.utils
import html.parser
import re
import urllib.request
import xml.etree.ElementTree as ET

from .. import bibliotheque

TYPE = "discours_fed"
AGENT = 10
TITRE = "Discours de la Fed : ton (lexique fixé) et citations"
PARAMS = {"nombre": "nombre maximal de nouveaux discours à lire (5 par défaut)"}
FLUX = "https://www.federalreserve.gov/feeds/speeches.xml"
FAUCON = ("inflation remains elevated", "inflation is too high", "further tightening", "additional tightening",
          "higher for longer", "upside risks to inflation", "not yet confident", "restrictive for longer",
          "premature to cut", "raise the policy rate", "rate increase")
COLOMBE = ("rate cuts", "cut rates", "lower the policy rate", "reduce the policy rate", "less restrictive",
           "downside risks to employment", "labor market has cooled", "inflation has eased", "progress on inflation",
           "easing of policy")
SEUIL = 2            # écart minimal pour pencher d'un côté


def _lire(url, delai=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (universite MGC, lecture seule)"})
    with urllib.request.urlopen(req, timeout=delai) as r:
        return r.read().decode("utf-8", errors="replace")


def telecharger_flux():
    """[{titre, lien, date (secondes UTC)}] du flux officiel. Remplacé dans les tests."""
    racine = ET.fromstring(_lire(FLUX))
    res = []
    for item in racine.iter("item"):
        lien = (item.findtext("link") or "").strip()
        if not lien.startswith("https://www.federalreserve.gov/"):
            continue
        try:
            date = email.utils.parsedate_to_datetime(item.findtext("pubDate") or "").timestamp()
        except (TypeError, ValueError):
            continue
        res.append({"titre": (item.findtext("title") or "").strip()[:200], "lien": lien, "date": date})
    return res


class _Texte(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.morceaux, self.profondeur, self.ignore = [], 0, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.ignore += 1
        if self.profondeur:
            self.profondeur += tag == "div"
        elif tag == "div" and dict(attrs).get("id") == "article":
            self.profondeur = 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.ignore = max(0, self.ignore - 1)
        if self.profondeur and tag == "div":
            self.profondeur -= 1
        if tag in ("p", "div", "br", "li", "h2", "h3"):
            self.morceaux.append("\n")

    def handle_data(self, data):
        if self.profondeur and not self.ignore:
            self.morceaux.append(data)


def telecharger_texte(lien):
    """Texte du discours (bloc « article » de la page officielle). Remplacé dans les tests."""
    p = _Texte()
    p.feed(_lire(lien))
    return re.sub(r"\n\s*\n+", "\n\n", "".join(p.morceaux)).strip()


def phrases(texte):
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+", texte.replace("\n", " ")) if p.strip()]


def _motif(expression):
    """Expression entière (pas « rate increases » pour « rate increase »), mots séparés par tout ce qui n'est pas une lettre."""
    return re.compile(r"(?<![a-z])" + r"[^a-z]+".join(map(re.escape, expression.split())) + r"(?![a-z])")


def compter(texte):
    """Occurrences de chaque expression (minuscules) et phrases exactes qui les contiennent."""
    bas = texte.lower()
    res = {}
    for cote, lexique in (("faucon", FAUCON), ("colombe", COLOMBE)):
        res[cote] = {e: n for e in lexique if (n := len(_motif(e).findall(bas)))}
    res["citations"] = [p for p in phrases(texte) if any(_motif(e).search(p.lower()) for e in FAUCON + COLOMBE)][:6]
    return res


def penchant(faucon, colombe):
    ecart = faucon - colombe
    return "faucon" if ecart >= SEUIL else "colombe" if ecart <= -SEUIL else "neutre ou partagé"


def executer(ctx):
    nombre = max(1, min(20, int(ctx.params.get("nombre") or 5)))
    ctx.etape("documentaliste", "Lit le flux officiel des discours de la Fed")
    try:
        flux = telecharger_flux()
    except Exception as e:
        raise OSError(f"flux de la Fed indisponible ({type(e).__name__})") from e
    deja = {r["origine"] for r in ctx.base.lire("SELECT DISTINCT origine FROM extraits WHERE origine LIKE 'fed:%'")}
    nouveaux = [d for d in sorted(flux, key=lambda d: d["date"]) if "fed:" + d["lien"] not in deja][-nombre:]
    ctx.detail({"dans_le_flux": len(flux), "nouveaux": len(nouveaux)})
    docs = []
    for d in nouveaux:
        ctx.verifier()
        ctx.etape("chercheur", f"Lit « {d['titre'][:70]} »")
        try:
            texte = telecharger_texte(d["lien"])
        except Exception as e:
            ctx.journal(f"Discours illisible ({type(e).__name__}) : {d['lien']}")
            continue
        if len(texte) < 500:
            ctx.journal(f"Texte trop court, ignoré : {d['lien']}")
            continue
        quand = dt.datetime.fromtimestamp(d["date"], dt.UTC).strftime("%d/%m/%Y")
        bibliotheque.indexer_texte(ctx.base, "fed:" + d["lien"], f"{quand} — {d['titre']}", texte)
        c = compter(texte)
        nf, nc = sum(c["faucon"].values()), sum(c["colombe"].values())
        ctx.etape("professeur", "Rédige la fiche du discours")
        lignes = [f"{d['titre']} — {quand}.", f"Source officielle : {d['lien']}", "",
                  f"Lexique fixé à l'avance : {nf} expression(s) « faucon », {nc} « colombe » → penche : {penchant(nf, nc)}."]
        lignes += [f"   faucon : « {e} » × {n}" for e, n in c["faucon"].items()]
        lignes += [f"   colombe : « {e} » × {n}" for e, n in c["colombe"].items()]
        lignes += ["", "Citations exactes :"] + [f"   « {p} »" for p in c["citations"]] if c["citations"] else []
        lignes += ["", "Limite : simple comptage d'expressions anglaises, sans lecture du contexte (une négation n'est pas "
                   "comprise). En général un ton « faucon » pèse sur l'or, « colombe » le soutient : à confirmer par les "
                   "réactions mesurées (agent 12)."]
        ctx.etape("connaissances", "Range le discours et demande son recompte", "verification")
        doc = ctx.document("discours", f"Discours Fed — {d['titre'][:80]}", "\n".join(lignes),
                           donnees={"lien": d["lien"], "date": d["date"], "comptes": c, "faucon": nf, "colombe": nc,
                                    "penchant": penchant(nf, nc)},
                           sources=[{"url": d["lien"], "origine": "fed:" + d["lien"]}], role="professeur", statut="a_verifier")
        ctx.demander(9, "verification_discours", f"Recompter le discours (document {doc})", {"document": doc},
                     "Recompter les expressions et retrouver les citations dans le texte gardé.", document=doc)
        docs.append(doc)
    if not docs:
        ctx.etape("professeur", "Aucun nouveau discours à lire")
    return {"documents": docs, "nouveaux": len(nouveaux)}
