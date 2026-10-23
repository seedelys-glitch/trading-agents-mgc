# -*- coding: utf-8 -*-
"""
Conversation avec le directeur (agent 14) : c'est par lui que Jarvis parle à toute l'université.

Jabran parle à Jarvis (voix, appli, écran du PC, Telegram) ; Jarvis transmet la phrase ici (POST /api/directeur).
Le directeur :
  - donne l'état réel (qui travaille, qui attend, erreurs), ou celui d'un agent précis ;
  - lance sa synthèse (et la lit si elle est prête en quelques secondes) ;
  - confie une mission à l'agent qui sait la faire (par demande_directeur, comme le bouton « Demander au directeur ») ;
  - dit où en est la dernière mission demandée, les derniers résultats, les alertes ;
  - répond aux autres questions avec l'IA locale, en ne s'appuyant QUE sur les faits de la base : une réponse qui
    contient un chiffre absent de ces faits est refusée (on renvoie alors les faits eux-mêmes).
Recherche et simulation seulement : aucun ordre, aucun broker, aucune prévision.
"""

import re
import time
import unicodedata

from . import agents, competences, donnees

MAX_TEXTE = 800
NOMBRE = re.compile(r"(?<![\w.])-?\d+(?:[.,]\d+)?")

CONSIGNE = (
    "Tu es le directeur (agent 14) de l'Université MGC, un bureau de recherche et de simulation sur le Micro Gold. "
    "Jabran te parle à travers Jarvis, souvent à l'oral : réponds en français simple, en 3 phrases au plus, sans "
    "markdown. Tu n'utilises QUE les faits donnés ci-dessous. Si l'information n'y est pas, dis-le franchement et "
    "propose la mission qui permettrait de la trouver. Distingue ce qui est vérifié de ce qui ne l'est pas. "
    "Aucun conseil d'achat ou de vente, aucune prévision de prix, aucun ordre : l'université ne trade pas.")

# Sujet d'une mission -> type de mission (l'ordre compte : « réaction aux annonces » avant « annonces »)
SUJETS = [
    (r"analyse complete|toutes les analyses|tous les techniciens|analyse technique", "analyses"),
    (r"precedent", "precedents"),
    (r"reaction", "reaction_annonces"),
    (r"replay|backtest|teste[rz]? (?:la |ma )?strategie", "replay_strategie_v1"),
    (r"controle|qualite des donnees|verifie les donnees", "controle_donnees"),
    (r"smc|ict|order ?blocks?|bos|choch", "analyse_smc"),
    (r"fibo|fibonacci", "analyse_fibo"),
    (r"ichimoku", "analyse_ichimoku"),
    (r"vwap|ema", "analyse_vwap_ema"),
    (r"flux|order ?flow|delta|profil de volume", "analyse_flux"),
    (r"discours|fed|powell", "discours_fed"),
    (r"calendrier|annonces?|agenda", "calendrier_macro"),
    (r"extrai\w* (?:les )?regles|regles de (?:la |ma )?strategie", "extraction_regles"),
    (r"range\w*|indexe\w*|bibliotheque", "indexation_bibliotheque"),
    (r"import\w*|tradingview", "import_tradingview"),
    (r"risque", "evaluation_risque"),
]
ANALYSES = ["analyse_smc", "analyse_fibo", "analyse_ichimoku", "analyse_vwap_ema", "analyse_flux"]
VERBE = (r"(?<![a-z])(?:lance|lancer|relance|demande|demander|fais|faire|refais|confie|analyse|analyser|teste|tester|"
         r"verifie|verifier|controle|controler|mesure|mesurer|cherche|chercher|retrouve|retrouver|extrais|extraire|"
         r"range|ranger|importe|importer|lis|lire|calcule|calculer|prepare|preparer|veux|voudrais|aimerais|faudrait|"
         r"peux|pourrais)\b")
SYNTHESE = r"(?<![a-z])(?:synthese|bilan|resume|fais (?:moi )?le point|fait le point)"
SUIVI = r"(?<![a-z])(?:ou en est|ou en sont|elle en est|ca donne quoi|c'est fini|c'est pret|termine)\w*.{0,30}(?:mission|demande|analyse|replay|synthese)"
ALERTES = r"(?<![a-z])(?:alertes?|vetos?|rejet\w*|problemes?|erreurs?|pannes?)\b"
ETAT = (r"(?<![a-z])(?:etat|ou en (?:est|sont|es)|qui travaille|ca avance|avancement|statut|status|quoi de neuf|"
        r"tu fais quoi|vous faites quoi|en ce moment)")
RESULTATS = r"(?<![a-z])(?:resultats?|documents?|rapports?|conclusions?|trouve quoi|appris)"
MERCI = r"^\W*(?:merci|ok merci|c'est tout|c'est bon)\b"


def plat(texte):
    t = unicodedata.normalize("NFD", (texte or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


def _court(texte, n=220):
    texte = " ".join(str(texte or "").split())
    return texte if len(texte) <= n else texte[: n - 1].rstrip() + "…"


def _nom(n):
    a = agents.agent(n) if n else None
    return a["nom"] if a else "?"


STATUTS = {"travail": "au travail", "attente": "en file d'attente", "erreur": "en erreur", "disponible": "disponible",
           "construction": "en construction"}
STATUTS_DOC = {"verifie": "vérifié", "rejete": "rejeté", "a_verifier": "à vérifier", "brouillon": "brouillon"}
STATUTS_MISSION = {"en_attente": "en attente", "en_cours": "en cours", "terminee": "terminée", "erreur": "en erreur",
                   "annulee": "annulée"}


class DirecteurChat:
    def __init__(self, univ):
        self.univ = univ
        self.base = univ.base

    # ------------------------------------------------------------------ historique
    def historique(self, n=40):
        return list(reversed(self.base.lire("SELECT * FROM conversation ORDER BY id DESC LIMIT ?", (int(n),))))

    def _noter(self, de, texte, origine, mission=None, intention=None):
        self.base.ecrire("INSERT INTO conversation(ts, de, texte, origine, mission, intention) VALUES (?,?,?,?,?,?)",
                         (time.time(), de, str(texte)[:4000], origine, mission, intention))

    # ------------------------------------------------------------------ point d'entrée
    def repondre(self, texte, origine="jarvis"):
        texte = " ".join(str(texte or "").split())[:MAX_TEXTE]
        if not texte:
            return {"reponse": "", "intention": None, "mission": None, "messages": self.historique()}
        origine = re.sub(r"[^a-z]", "", str(origine).lower())[:20] or "jarvis"
        self._noter("jabran", texte, origine)
        intention, reponse, mission = self._traiter(texte)
        self._noter("directeur", reponse, origine, mission, intention)
        self.base.evenement("directeur", f"Jabran ({origine}) : {_court(texte, 160)}", agent=agents.DIRECTEUR)
        return {"reponse": reponse, "intention": intention, "mission": mission, "messages": self.historique()}

    def _traiter(self, texte):
        t = plat(texte)
        if re.search(MERCI, t) and len(t.split()) <= 5:
            return "merci", "Avec plaisir. L'équipe continue, je te tiens au courant.", None
        if re.search(SUIVI, t):
            return "suivi", self.suivi(), None
        if re.search(SYNTHESE, t) and not re.search(r"(?<![a-z])derniere synthese", t):
            return "synthese", *self.synthese()
        sujet = next((typ for motif, typ in SUJETS if re.search(rf"(?<![a-z])(?:{motif})", t)), None)
        if sujet and re.search(VERBE, t):
            return "mission", *self.mission(sujet, texte)
        if re.search(r"(?<![a-z])derniere synthese", t):
            return "synthese", self.derniere_synthese() or "Aucune synthèse n'a encore été faite. Dis « fais la synthèse ».", None
        if re.search(ALERTES, t):
            return "alertes", self.alertes(), None
        n = self._agent_nomme(t)
        if n and n != agents.DIRECTEUR and (re.search(ETAT, t) or len(t.split()) <= 6):
            return "agent", self.etat_agent(n), None
        if re.search(ETAT, t):
            return "etat", self.etat(), None
        if re.search(RESULTATS, t):
            return "resultats", self.resultats(), None
        return "question", self.question(texte), None

    # ------------------------------------------------------------------ réponses factuelles
    def etat(self):
        e = self.univ.etat()
        ags = e["agents"]
        parts = []
        for statut in ("travail", "attente", "erreur"):
            noms = [a["nom"] for a in ags if a["statut"] == statut]
            if noms:
                parts.append(f"{STATUTS[statut]} : {', '.join(noms)}")
        prets = sum(1 for a in ags if a["statut"] != "construction")
        c = e.get("compteurs") or {}
        txt = f"{prets} agents sur {len(ags)} sont prêts. "
        txt += ("; ".join(parts) + ". ") if parts else "Personne ne travaille en ce moment. "
        txt += f"La base contient {c.get('documents', 0)} documents"
        txt += f" et {c.get('boucles', 0)} boucle(s) active(s)." if c.get("boucles") else "."
        construction = [a["nom"] for a in ags if a["statut"] == "construction"]
        if construction:
            txt += f" En construction : {', '.join(construction)}."
        return txt

    def etat_agent(self, n):
        e = self.univ.espace_agent(n)
        txt = f"{e['agent']['nom']} est {STATUTS.get(e['statut'], e['statut'])}."
        if e["mission_en_cours"]:
            txt += f" Il travaille sur : {e['mission_en_cours'].get('titre', '')}."
        if e["file"]:
            txt += f" {e['file']} mission(s) l'attendent."
        d = e["dernier_document"]
        if d:
            txt += f" Son dernier document : « {d['titre']} », {STATUTS_DOC.get(d['statut'], d['statut'])}."
        elif not e["agent"]["en_construction"]:
            txt += " Il n'a encore produit aucun document."
        return txt

    def alertes(self, heures=24):
        lim = time.time() - heures * 3600
        al = self.base.lire("SELECT * FROM messages WHERE a=? AND genre='alerte' AND ts>=? ORDER BY id DESC LIMIT 5",
                            (agents.DIRECTEUR, lim))
        erreurs = self.base.lire("SELECT id, agent, titre, erreur FROM missions WHERE statut='erreur' AND fin>=?"
                                 " ORDER BY id DESC LIMIT 3", (lim,))
        if not al and not erreurs:
            return "Aucune alerte ni mission en erreur depuis 24 heures."
        lignes = [f"{len(al)} alerte(s) depuis 24 heures." if al else "Aucune alerte depuis 24 heures."]
        lignes += [f"De {_nom(m['de'])} : {_court(m['contenu'], 180)}" for m in al[:3]]
        lignes += [f"Mission n° {m['id']} ({_nom(m['agent'])}) en erreur : {_court(m['erreur'], 140)}" for m in erreurs]
        return " ".join(lignes)

    def resultats(self, n=5):
        docs = self.base.lire("SELECT id, agent, genre, titre, statut FROM documents WHERE genre NOT IN ('verification')"
                              " ORDER BY id DESC LIMIT ?", (n,))
        if not docs:
            return "Aucun résultat pour l'instant : la base ne contient encore aucun document. Demande-moi une analyse ou un replay."
        return "Derniers résultats : " + " ; ".join(
            f"n° {d['id']} {d['titre']} par {_nom(d['agent'])} ({STATUTS_DOC.get(d['statut'], d['statut'])})" for d in docs) + "."

    def derniere_synthese(self):
        """La dernière synthèse, racontée en quelques phrases (chiffres repris tels quels du document)."""
        s = self.base.un("SELECT id, contenu, cree FROM documents WHERE genre='synthese' ORDER BY id DESC LIMIT 1")
        if not s:
            return None
        age = int((time.time() - s["cree"]) // 60)
        quand = f"il y a {age} min" if age < 120 else f"il y a {age // 60} h"
        lignes = [x.strip(" -") for x in s["contenu"].splitlines() if x.strip()]
        actifs, erreurs, autres = [], [], []
        for x in lignes:
            m = re.match(r"(.+?) : (\d+) terminée\(s\), (\d+) en cours, (\d+) en attente, (\d+) en erreur\.$", x)
            if m:
                if int(m.group(2)):
                    actifs.append(f"{m.group(1)} {m.group(2)}")
                if int(m.group(5)):
                    erreurs.append(f"{m.group(1)} ({m.group(5)})")
            elif x.startswith(("Travaux vérifiés", "Aucun document")):
                autres.append(x)
        txt = f"Synthèse n° {s['id']} ({quand}). "
        txt += ("Missions terminées : " + ", ".join(actifs) + ". ") if actifs else "Aucune mission sur la période. "
        if erreurs:
            txt += "En erreur : " + ", ".join(erreurs) + ". "
        return (txt + " ".join(autres)).strip()

    def suivi(self):
        m = self.base.un("SELECT mission FROM conversation WHERE mission IS NOT NULL ORDER BY id DESC LIMIT 1")
        if not m:
            return "Tu ne m'as encore confié aucune mission d'ici. Dis par exemple « lance une analyse Fibonacci »."
        mission = self.base.mission(m["mission"])
        if not mission:
            return "Je ne retrouve plus cette mission."
        enfants = self.base.lire("SELECT * FROM missions WHERE parent=? ORDER BY id", (mission["id"],))
        cible = enfants[-1] if enfants else mission
        txt = f"Mission n° {cible['id']} ({cible['titre']}, {_nom(cible['agent'])}) : {STATUTS_MISSION.get(cible['statut'], cible['statut'])}."
        if cible["statut"] == "erreur":
            txt += f" Raison : {_court(cible.get('erreur'), 200)}"
        if mission["statut"] == "erreur" and cible is mission:
            return txt
        doc = self.base.un("SELECT id, titre, statut, contenu FROM documents WHERE mission=? AND genre!='verification'"
                           " ORDER BY id DESC LIMIT 1", (cible["id"],))
        if doc:
            txt += (f" Document n° {doc['id']} « {doc['titre']} », {STATUTS_DOC.get(doc['statut'], doc['statut'])} : "
                    f"{_court(doc['contenu'], 400)}")
        return txt

    # ------------------------------------------------------------------ actions
    def synthese(self, attente_s=8.0):
        m = self.base.nouvelle_mission(agents.DIRECTEUR, "synthese_directeur", "Synthèse du directeur",
                                       {"heures": 24}, "Demandée par Jabran via Jarvis.", priorite=3,
                                       tentatives_max=self.univ.reglages["tentatives_max"])
        fin = time.time() + attente_s
        while time.time() < fin and self.univ.moteur.etat()["en_marche"]:
            if (self.base.mission(m) or {}).get("statut") in ("terminee", "erreur"):
                break
            time.sleep(0.3)
        if (self.base.mission(m) or {}).get("statut") == "terminee":
            return self.derniere_synthese(), m
        return f"Je lance ma synthèse des dernières 24 heures (mission n° {m}). Redemande « où en est la synthèse » dans un instant.", m

    def _jeu(self):
        """Le jeu de bougies le plus récent qui contient vraiment des bougies (jamais inventé)."""
        for j in donnees.liste_jeux(self.base):
            if j["unites"]:
                return j
        return None

    def mission(self, sujet, texte):
        if sujet == "evaluation_risque":
            return ("Pour évaluer le risque d'une idée, il me faut le sens, l'entrée, le stop et les objectifs : "
                    "remplis-les dans l'université (bouton « Demander au directeur »)."), None
        types = ANALYSES if sujet == "analyses" else [sujet]
        params = {}
        if any("jeu" in competences.TYPES[t].PARAMS for t in types):
            j = self._jeu()
            if not j:
                return ("Je ne peux pas : l'université n'a encore aucune bougie. Importe des données d'abord "
                        "(bouton « Données » de l'université, Yahoo ou export TradingView)."), None
            params["jeu"] = j["id"]
        if sujet == "precedents":
            params["question"] = re.sub(r"^.*?precedents?\s*(?:de|du|des|sur|pour)?\s*", "", plat(texte))[:200] or plat(texte)
        ids = []
        for t in types:
            ids.append(self.univ.creer_mission({"type": t, "params": {k: v for k, v in params.items()
                                                                      if k in competences.TYPES[t].PARAMS},
                                                "par_directeur": True, "consigne": texte}))
        noms = sorted({_nom(competences.TYPES[t].AGENT) for t in types})
        jeu = f" sur le jeu « {self._jeu()['nom']} »" if "jeu" in params else ""
        if len(ids) == 1:
            return (f"C'est noté : je confie « {competences.TYPES[types[0]].TITRE} » à {noms[0]}{jeu} (demande n° {ids[0]}). "
                    "Demande-moi « où en est la mission » pour le résultat."), ids[0]
        return (f"C'est noté : je lance {len(ids)} analyses{jeu} ({', '.join(noms)}). "
                "Demande-moi « où en est la mission » ou « les derniers résultats »."), ids[-1]

    # ------------------------------------------------------------------ question libre (IA locale, faits seulement)
    def faits(self):
        lignes = ["État : " + self.etat()]
        docs = self.base.lire("SELECT id, agent, genre, titre, statut FROM documents ORDER BY id DESC LIMIT 8")
        lignes.append("Derniers documents : " + ("; ".join(
            f"n° {d['id']} {d['titre']} ({_nom(d['agent'])}, {STATUTS_DOC.get(d['statut'], d['statut'])})" for d in docs)
            if docs else "aucun"))
        s = self.derniere_synthese()
        if s:
            lignes.append(s)
        lignes.append("Alertes : " + self.alertes())
        jeux = [j for j in donnees.liste_jeux(self.base) if j["unites"]]
        lignes.append("Données : " + ("; ".join(f"jeu « {j['nom']} » ({j['source']})" for j in jeux[:4]) if jeux
                                      else "aucune bougie importée"))
        lignes.append("Compétences branchées : " + ", ".join(sorted({_nom(c["agent"]) for c in competences.catalogue()
                                                                    if not c["interne"]})))
        return "\n".join(lignes)

    def question(self, texte):
        faits = self.faits()
        histo = self.historique(7)[:-1]
        conversation = "\n".join(f"{'Jabran' if m['de'] == 'jabran' else 'Directeur'} : {_court(m['texte'], 200)}"
                                 for m in histo)
        rep = self.univ.ia.completer(CONSIGNE, f"=== Faits (base de l'université) ===\n{faits}\n\n"
                                               f"=== Conversation ===\n{conversation or '(début)'}\n\n"
                                               f"Question de Jabran : {texte}", agent=agents.DIRECTEUR, role="directeur")
        if rep:
            rep = " ".join(re.sub(r"[*#_`>]+", "", rep).split())
            autorises = {n.replace(",", ".") for n in NOMBRE.findall(faits + " " + texte)}
            if not [n for n in NOMBRE.findall(rep) if n.replace(",", ".") not in autorises]:
                return rep
            self.base.evenement("ia", "Réponse du directeur refusée : chiffres absents des faits.", agent=agents.DIRECTEUR,
                                niveau="alerte")
        return ("Je réponds seulement avec ce qui existe dans l'université. " + self.etat()
                + " Tu peux me demander une analyse, un replay, la synthèse, les alertes ou les derniers résultats.")

    @staticmethod
    def _agent_nomme(t):
        for a in agents.AGENTS:
            noms = {plat(a["nom"]), plat(a["court"]), plat(a["cle"])} | {x.strip() for x in re.split(r"[/&]", plat(a["nom"]))}
            if any(len(x) >= 4 and re.search(rf"(?<![a-z]){re.escape(x)}(?![a-z])", t) for x in noms):
                return a["n"]
        m = re.search(r"(?<![a-z])agent (?:n[o°]? ?)?(\d{1,2})\b", t)
        if m and agents.agent(int(m.group(1))):
            return int(m.group(1))
        return None
