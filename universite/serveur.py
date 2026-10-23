# -*- coding: utf-8 -*-
"""
API locale de l'université + bureau virtuel (ui/). Écoute seulement sur 127.0.0.1 (le PC lui-même).

Toutes les réponses viennent de la base : le bureau n'affiche jamais une activité qui n'a pas eu lieu.
Les requêtes qui modifient quelque chose (POST) exigent l'en-tête X-Universite, qu'une page d'un autre site
ne peut pas envoyer sans autorisation : un site malveillant ouvert dans le navigateur ne peut rien lancer.
"""

import json
import logging
import mimetypes
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import agents, competences, config, donnees
from .base import Base
from .ia import IALocale
from .moteur import Moteur

UI = Path(__file__).resolve().parent / "ui"
ACTIF_S = 120          # un lien entre deux agents reste affiché 2 min après leur dernier message réel
log = logging.getLogger("universite")


class Universite:
    def __init__(self, dossier=None, demarrer_moteur=True):
        self.dossier = Path(dossier or config.DONNEES)
        self.reglages = config.charger(self.dossier)
        self.base = Base(self.dossier / "universite.sqlite")
        self.ia = IALocale(self.base, self.reglages)
        self.moteur = Moteur(self.base, self.reglages, self.ia)
        if demarrer_moteur:
            self.moteur.demarrer()

    # ------------------------------------------------------------------ lecture
    def etat(self):
        maintenant = time.time()
        connues = set(competences.TYPES)
        en_cours = {m["agent"]: m for m in self.base.lire("SELECT * FROM missions WHERE statut='en_cours'")}
        attente = {r["agent"]: r["n"] for r in self.base.lire(
            "SELECT agent, COUNT(*) AS n FROM missions WHERE statut='en_attente' GROUP BY agent")}
        erreurs = {r["agent"]: r for r in self.base.lire(
            "SELECT agent, MAX(fin) AS fin, COUNT(*) AS n FROM missions WHERE statut='erreur' AND fin>=? GROUP BY agent",
            (maintenant - 3600,))}
        derniers = {r["agent"]: r for r in self.base.lire(
            "SELECT agent, MAX(fin) AS fin FROM missions WHERE statut='terminee' GROUP BY agent")}
        docs = {r["agent"]: r["n"] for r in self.base.lire("SELECT agent, COUNT(*) AS n FROM documents GROUP BY agent")}
        liste = []
        for a in agents.AGENTS:
            fiche = agents.fiche(a, connues)
            m = en_cours.get(a["n"])
            if fiche["en_construction"]:
                statut = "construction"
            elif m:
                statut = "travail"
            elif a["n"] in erreurs and (derniers.get(a["n"], {}).get("fin") or 0) < erreurs[a["n"]]["fin"]:
                statut = "erreur"
            elif attente.get(a["n"]):
                statut = "attente"
            else:
                statut = "disponible"
            liste.append({"n": a["n"], "cle": a["cle"], "nom": a["nom"], "court": a["court"], "statut": statut,
                          "competences": fiche["competences_branchees"], "file": attente.get(a["n"], 0),
                          "documents": docs.get(a["n"], 0),
                          "mission": None if not m else {k: m[k] for k in (
                              "id", "titre", "phase", "role", "etape", "etapes_faites", "debut", "battement")}})
        liens = self.base.lire("SELECT de, a, genre, MAX(ts) AS ts, COUNT(*) AS n FROM messages WHERE ts>=?"
                               " GROUP BY de, a, genre", (maintenant - ACTIF_S,))
        return {"maintenant": maintenant, "agents": liste, "liens": liens, "moteur": self.moteur.etat(),
                "ia": {**self.ia.etat(), "appels_du_jour": self.ia.appels_du_jour(),
                       "budget": self.reglages["ia_appels_max_jour"], "active": self.reglages["ia_commentaires"]},
                "compteurs": self.base.un(
                    "SELECT (SELECT COUNT(*) FROM missions WHERE statut='en_attente') AS attente,"
                    " (SELECT COUNT(*) FROM missions WHERE statut='en_cours') AS en_cours,"
                    " (SELECT COUNT(*) FROM documents) AS documents,"
                    " (SELECT COUNT(*) FROM jeux) AS jeux,"
                    " (SELECT COUNT(*) FROM boucles WHERE statut='active') AS boucles"),
                "dernier_evenement": (self.base.un("SELECT MAX(id) AS id FROM evenements") or {}).get("id") or 0}

    def fiche_agent(self, n):
        a = agents.agent(n)
        if not a:
            return None
        f = agents.fiche(a, set(competences.TYPES))
        f["catalogue"] = [c for c in competences.catalogue() if c["agent"] == a["n"]]
        f["missions"] = self.base.lire("SELECT id, type, titre, statut, phase, role, etape, tentatives, erreur, cree,"
                                       " debut, fin, demandeur, parent, boucle FROM missions WHERE agent=?"
                                       " ORDER BY id DESC LIMIT 40", (a["n"],))
        f["etapes"] = self.base.lire("SELECT * FROM etapes WHERE agent=? ORDER BY id DESC LIMIT 60", (a["n"],))
        f["documents"] = self.base.lire("SELECT id, genre, titre, statut, verifie_par, cree, mission FROM documents"
                                        " WHERE agent=? ORDER BY id DESC LIMIT 30", (a["n"],))
        f["messages"] = self.base.lire("SELECT * FROM messages WHERE de=? OR a=? ORDER BY id DESC LIMIT 30",
                                       (a["n"], a["n"]))
        f["evenements"] = self.base.lire("SELECT * FROM evenements WHERE agent=? ORDER BY id DESC LIMIT 30", (a["n"],))
        f["boucles"] = self.base.lire("SELECT * FROM boucles WHERE responsable=? ORDER BY id DESC", (a["n"],))
        # Dernière étape de chaque fonction de soutien : ce qu'elle a réellement fait, et quand
        f["soutiens_etat"] = {r["role"]: r for r in self.base.lire(
            "SELECT role, libelle, statut, debut, fin, mission FROM etapes WHERE id IN"
            " (SELECT MAX(id) FROM etapes WHERE agent=? GROUP BY role)", (a["n"],))}
        return f

    # ------------------------------------------------------------------ actions
    def creer_mission(self, corps):
        genre = corps.get("type", "")
        comp = competences.TYPES.get(genre)
        if comp is None:
            raise ValueError(f"type de mission inconnu : {genre}")
        params = corps.get("params") or {}
        if corps.get("par_directeur") and comp.AGENT != agents.DIRECTEUR:
            return self.base.nouvelle_mission(agents.DIRECTEUR, "demande_directeur", f"Demande : {comp.TITRE}",
                                              {"type": genre, "params": params, "consigne": corps.get("consigne", "")},
                                              corps.get("consigne", ""), priorite=3,
                                              tentatives_max=self.reglages["tentatives_max"])
        return self.base.nouvelle_mission(comp.AGENT, genre, corps.get("titre") or comp.TITRE, params,
                                          corps.get("consigne", ""), priorite=int(corps.get("priorite", 5)),
                                          tentatives_max=self.reglages["tentatives_max"])

    def arreter(self):
        self.moteur.arreter()


def _json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")


def fabriquer_handler(univ):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Universite/1"

        def log_message(self, fmt, *args):
            log.debug(fmt, *args)

        def _envoyer(self, code, corps, type_="application/json; charset=utf-8"):
            if not isinstance(corps, bytes):
                corps = _json_bytes(corps)
            self.send_response(code)
            self.send_header("Content-Type", type_)
            self.send_header("Content-Length", str(len(corps)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(corps)

        def _corps(self, limite=20_000_000):
            n = int(self.headers.get("Content-Length") or 0)
            if n > limite:
                raise ValueError("envoi trop gros")
            brut = self.rfile.read(n) if n else b""
            return brut

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[-1] for k, v in parse_qs(u.query).items()}
            morceaux = [m for m in u.path.split("/") if m]
            try:
                if u.path == "/api/etat":
                    return self._envoyer(200, univ.etat())
                if u.path == "/api/agents":
                    connues = set(competences.TYPES)
                    return self._envoyer(200, {"agents": [agents.fiche(a, connues) for a in agents.AGENTS],
                                               "roles": len(agents.roles()), "catalogue": competences.catalogue()})
                if len(morceaux) == 3 and morceaux[:2] == ["api", "agent"]:
                    f = univ.fiche_agent(morceaux[2])
                    return self._envoyer(200 if f else 404, f or {"erreur": "agent inconnu"})
                if u.path == "/api/missions":
                    return self._envoyer(200, univ.base.lire("SELECT * FROM missions ORDER BY id DESC LIMIT ?",
                                                             (min(500, int(q.get("n", 100))),)))
                if len(morceaux) == 3 and morceaux[:2] == ["api", "mission"]:
                    m = univ.base.mission(int(morceaux[2]))
                    if m:
                        m["etapes"] = univ.base.lire("SELECT * FROM etapes WHERE mission=? ORDER BY id", (m["id"],))
                    return self._envoyer(200 if m else 404, m or {"erreur": "mission inconnue"})
                if u.path == "/api/documents":
                    return self._envoyer(200, univ.base.lire(
                        "SELECT id, agent, genre, titre, statut, verifie_par, cree, mission FROM documents"
                        " ORDER BY id DESC LIMIT ?", (min(500, int(q.get("n", 100))),)))
                if len(morceaux) == 3 and morceaux[:2] == ["api", "document"]:
                    d = univ.base.un("SELECT * FROM documents WHERE id=?", (int(morceaux[2]),))
                    return self._envoyer(200 if d else 404, d or {"erreur": "document inconnu"})
                if u.path == "/api/evenements":
                    return self._envoyer(200, univ.base.lire(
                        "SELECT * FROM evenements WHERE id>? ORDER BY id DESC LIMIT 200", (int(q.get("apres", 0)),)))
                if u.path == "/api/messages":
                    return self._envoyer(200, univ.base.lire("SELECT * FROM messages ORDER BY id DESC LIMIT 100"))
                if u.path == "/api/jeux":
                    return self._envoyer(200, donnees.liste_jeux(univ.base))
                if u.path == "/api/boucles":
                    return self._envoyer(200, univ.base.lire("SELECT * FROM boucles ORDER BY id DESC"))
                if u.path == "/api/reglages":
                    return self._envoyer(200, univ.reglages)
                return self._fichier(u.path)
            except (ValueError, KeyError) as e:
                return self._envoyer(400, {"erreur": str(e)})

        def _fichier(self, chemin):
            if chemin in ("", "/"):
                chemin = "/index.html"
            f = (UI / chemin.lstrip("/")).resolve()
            if UI.resolve() not in f.parents or not f.is_file():
                return self._envoyer(404, {"erreur": "introuvable"})
            type_ = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if type_.startswith("text/") or type_ in ("application/javascript",):
                type_ += "; charset=utf-8"
            return self._envoyer(200, f.read_bytes(), type_)

        def do_POST(self):
            if self.headers.get("X-Universite") != "1":
                return self._envoyer(403, {"erreur": "en-tête X-Universite manquant"})
            u = urlparse(self.path)
            morceaux = [m for m in u.path.split("/") if m]
            try:
                brut = self._corps()
                if u.path == "/api/jeux/import":
                    nom = self.headers.get("X-Nom-Jeu") or "Import"
                    from urllib.parse import unquote
                    r = donnees.importer_csv(univ.base, brut.decode("utf-8-sig", errors="replace"), unquote(nom),
                                             unite=self.headers.get("X-Unite") or None)
                    return self._envoyer(200, r)
                corps = json.loads(brut.decode("utf-8") or "{}") if brut else {}
                if u.path == "/api/missions":
                    return self._envoyer(200, {"mission": univ.creer_mission(corps)})
                if len(morceaux) == 4 and morceaux[:2] == ["api", "mission"] and morceaux[3] == "annuler":
                    return self._envoyer(200, {"annulee": univ.base.annuler(int(morceaux[2]))})
                if u.path == "/api/jeux/ninja":
                    config.salle_importable()
                    from mgc import config as cfg_salle, source_ninja
                    dossier = corps.get("dossier") or source_ninja.dossier_par_defaut(cfg_salle.charger())
                    return self._envoyer(200, donnees.importer_ninja(univ.base, dossier))
                if u.path == "/api/jeux/yahoo":
                    config.salle_importable()
                    from mgc import config as cfg_salle
                    from mgc.contrats import ContractManager
                    import datetime as dt
                    contrat = corps.get("contrat") or ContractManager(cfg_salle.charger()).etat(
                        dt.datetime.now(dt.UTC))["contrat"]
                    return self._envoyer(200, donnees.importer_yahoo(univ.base, contrat))
                if u.path == "/api/boucles":
                    b = univ.moteur.nouvelle_boucle(corps["nom"], int(corps["responsable"]), corps["type"],
                                                    corps.get("objectif", ""), corps.get("params"),
                                                    corps.get("intervalle_s", 600), corps.get("iterations_max", 100))
                    return self._envoyer(200, {"boucle": b})
                if len(morceaux) == 4 and morceaux[:2] == ["api", "boucle"]:
                    return self._envoyer(200, {"ok": univ.moteur.changer_boucle(int(morceaux[2]), morceaux[3])})
                if u.path == "/api/reglages":
                    univ.reglages.update(config.enregistrer(corps, univ.dossier))
                    return self._envoyer(200, univ.reglages)
                return self._envoyer(404, {"erreur": "introuvable"})
            except (ValueError, KeyError, TypeError) as e:
                return self._envoyer(400, {"erreur": str(e)})
            except OSError as e:
                return self._envoyer(503, {"erreur": f"{type(e).__name__} : {e}"})

    return Handler


def lancer(univ, port=None, hote="127.0.0.1"):
    serveur = ThreadingHTTPServer((hote, port if port is not None else univ.reglages["port"]), fabriquer_handler(univ))
    serveur.daemon_threads = True
    fil = threading.Thread(target=serveur.serve_forever, name="http", daemon=True)
    fil.start()
    return serveur
