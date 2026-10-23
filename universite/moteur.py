# -*- coding: utf-8 -*-
"""
Le moteur : file de missions persistante, ouvriers, délais, nouveaux essais, reprise après arrêt, boucles.

- Chaque mission est d'un type (= une compétence de competences/). Un ouvrier la réserve dans la base
  (jamais deux ouvriers sur la même), l'exécute, puis la marque terminée ou en erreur.
- Délai : une mission qui dépasse `delai_mission_s` est arrêtée à sa prochaine étape et notée en erreur.
- Erreur passagère (réseau, fichier occupé, IA injoignable) : nouvel essai plus tard, jusqu'à `tentatives_max`.
- Arrêt du programme : au redémarrage, les missions coupées en plein travail retournent dans la file.
- Boucles : une boucle relance une mission à intervalle régulier, avec un nombre maximal d'itérations
  (budget) et une mise en pause automatique après 3 erreurs de suite.
"""

import threading
import time
import traceback

from . import competences
from .agents import DIRECTEUR, PAR_NUMERO, SOUTIENS


class DelaiDepasse(Exception):
    pass


class Annulee(Exception):
    pass


class ErreurPassagere(Exception):
    """À lever par une compétence quand un nouvel essai a des chances de marcher."""


PASSAGERES = (ErreurPassagere, OSError, TimeoutError)


class Contexte:
    """Ce qu'une compétence reçoit : la mission, et les seules actions qui laissent une trace dans la base."""

    def __init__(self, moteur, mission):
        self.moteur, self.base, self.ia = moteur, moteur.base, moteur.ia
        self.mission = mission
        self.id = mission["id"]
        self.agent = mission["agent"]
        self.params = mission["params"] if isinstance(mission["params"], dict) else {}
        self.limite = time.time() + float(moteur.reglages["delai_mission_s"])

    def verifier(self):
        if time.time() > self.limite:
            raise DelaiDepasse(f"délai de {self.moteur.reglages['delai_mission_s']} s dépassé")
        if self.moteur.arret.is_set():
            raise Annulee("programme en cours d'arrêt")

    def etape(self, role, libelle, phase=None):
        """Note une étape réellement commencée, avec la fonction de soutien qui travaille."""
        self.verifier()
        phase = phase or SOUTIENS.get(role, {}).get("phase", "analyse")
        return self.base.debut_etape(self.id, self.agent, phase, libelle, role)

    def detail(self, info):
        """Ajoute un détail (chiffres, comptes) à l'étape en cours."""
        import json
        self.base.ecrire("UPDATE etapes SET detail=? WHERE mission=? AND statut='en_cours'",
                         (json.dumps(info, ensure_ascii=False, default=str), self.id))

    def document(self, genre, titre, contenu, donnees=None, sources=None, role="", statut="brouillon"):
        d = self.base.document(self.agent, genre, titre, contenu, donnees, sources, self.id, role, statut)
        self.base.evenement("document", f"Document « {titre} » rédigé.", agent=self.agent, mission=self.id)
        return d

    def message(self, a, genre, contenu, document=None):
        return self.base.message(self.agent, a, genre, contenu, self.id, document)

    def demander(self, agent, genre, titre, params, objectif="", document=None):
        """Demande une mission à un autre agent (vérification, avis...). Le message est réellement envoyé."""
        m = self.base.nouvelle_mission(agent, genre, titre, params, objectif, priorite=4,
                                       demandeur=f"agent {self.agent}", parent=self.id,
                                       tentatives_max=self.moteur.reglages["tentatives_max"])
        self.message(agent, "demande", f"{titre} (mission {m})", document)
        return m

    def journal(self, message, niveau="info"):
        self.base.evenement("mission", message, agent=self.agent, mission=self.id, niveau=niveau)


class Moteur:
    def __init__(self, base, reglages, ia):
        self.base, self.reglages, self.ia = base, reglages, ia
        self.arret = threading.Event()
        self.fils = []
        self.demarre = None
        self.occupes = {}  # numéro d'ouvrier -> id de mission

    # ------------------------------------------------------------------ démarrage / arrêt
    def demarrer(self):
        repris = self.base.reprendre_interrompues()
        if repris:
            self.base.evenement("moteur", f"Reprise après arrêt : {len(repris)} mission(s) remise(s) dans la file.")
        self.demarre = time.time()
        n = max(1, int(self.reglages["concurrence"]))
        for i in range(n):
            f = threading.Thread(target=self._ouvrier, args=(i,), name=f"ouvrier-{i}", daemon=True)
            f.start()
            self.fils.append(f)
        f = threading.Thread(target=self._planificateur, name="boucles", daemon=True)
        f.start()
        self.fils.append(f)
        self.base.evenement("moteur", f"Moteur démarré : {n} ouvrier(s), IA {self.reglages['concurrence_ia']} à la fois.")

    def arreter(self, attente=5):
        self.arret.set()
        for f in self.fils:
            f.join(timeout=attente)

    def etat(self):
        return {"demarre": self.demarre, "ouvriers": len([f for f in self.fils if f.name.startswith("ouvrier")]),
                "occupes": dict(self.occupes), "en_marche": bool(self.fils) and not self.arret.is_set()}

    # ------------------------------------------------------------------ exécution
    def _ouvrier(self, numero):
        while not self.arret.is_set():
            try:
                mission = self.base.prendre_mission(list(competences.TYPES))
            except Exception:  # base occupée un instant : on réessaie
                mission = None
            if mission is None:
                self.arret.wait(0.5)
                continue
            self.occupes[numero] = mission["id"]
            try:
                self.executer(mission)
            finally:
                self.occupes.pop(numero, None)

    def executer(self, mission):
        """Exécute une mission déjà réservée (utilisé par les ouvriers et par les tests)."""
        ctx = Contexte(self, mission)
        comp = competences.TYPES.get(mission["type"])
        nom = PAR_NUMERO.get(mission["agent"], {}).get("nom", mission["agent"])
        self.base.evenement("mission", f"{nom} commence : {mission['titre']}", agent=mission["agent"],
                            mission=mission["id"])
        try:
            if comp is None:
                raise ValueError(f"type de mission inconnu : {mission['type']}")
            resultat = comp.executer(ctx)
            ctx.verifier()
            self.base.fin_etapes(mission["id"])
            self.base.terminer(mission["id"], resultat)
            self.base.evenement("mission", f"{nom} a terminé : {mission['titre']}", agent=mission["agent"],
                                mission=mission["id"])
            self._suite_boucle(mission, ok=True)
        except Annulee as e:
            self.base.fin_etapes(mission["id"], "interrompue")
            self.base.echouer(mission["id"], e, reessayer_dans=0)
        except Exception as e:  # noqa: BLE001 : toute erreur d'une compétence est enregistrée, jamais avalée
            self.base.fin_etapes(mission["id"], "erreur")
            frais = self.base.mission(mission["id"])
            passagere = isinstance(e, PASSAGERES) and not isinstance(e, DelaiDepasse)
            if passagere and frais["tentatives"] < frais["tentatives_max"] + 1:
                attente = 30 * frais["tentatives"]
                self.base.echouer(mission["id"], f"{type(e).__name__} : {e}", reessayer_dans=attente)
                self.base.evenement("mission", f"Erreur passagère, nouvel essai dans {attente} s : {e}",
                                    agent=mission["agent"], mission=mission["id"], niveau="alerte")
            else:
                self.base.echouer(mission["id"], f"{type(e).__name__} : {e}")
                self.base.evenement("mission", f"Échec : {mission['titre']} ({type(e).__name__} : {e})",
                                    agent=mission["agent"], mission=mission["id"], niveau="erreur")
                self.base.message(mission["agent"], DIRECTEUR, "alerte", f"Échec de la mission {mission['id']} : {e}",
                                  mission["id"])
                self._suite_boucle(mission, ok=False, erreur=traceback.format_exception_only(e)[-1].strip())

    # ------------------------------------------------------------------ boucles
    def nouvelle_boucle(self, nom, responsable, genre, objectif, params=None, intervalle_s=600, iterations_max=100):
        import json
        maintenant = time.time()
        return self.base.ecrire(
            "INSERT INTO boucles(genre, nom, responsable, objectif, params, intervalle_s, iterations_max, prochaine,"
            " cree, maj) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (genre, nom, int(responsable), objectif, json.dumps(params or {}, ensure_ascii=False),
             max(30.0, float(intervalle_s)), max(1, int(iterations_max)), maintenant, maintenant, maintenant))

    def changer_boucle(self, ident, statut):
        if statut not in ("active", "pause", "terminee"):
            raise ValueError("statut de boucle inconnu")
        return self.base.ecrire("UPDATE boucles SET statut=?, maj=?, erreurs_de_suite=0,"
                                " prochaine=MIN(prochaine, ?) WHERE id=?",
                                (statut, time.time(), time.time(), ident)) > 0

    def _planificateur(self):
        while not self.arret.is_set():
            try:
                self.tour_de_boucles()
            except Exception as e:  # noqa: BLE001
                self.base.evenement("moteur", f"Planificateur : {e}", niveau="erreur")
            self.arret.wait(2)

    def tour_de_boucles(self, maintenant=None):
        """Lance l'itération suivante des boucles actives arrivées à échéance (une seule mission à la fois)."""
        maintenant = maintenant or time.time()
        lancees = []
        for b in self.base.lire("SELECT * FROM boucles WHERE statut='active' AND prochaine<=?", (maintenant,)):
            occupee = self.base.un("SELECT id FROM missions WHERE boucle=? AND statut IN ('en_attente','en_cours')",
                                   (b["id"],))
            if occupee:
                continue
            if b["iterations"] >= b["iterations_max"]:
                self.base.ecrire("UPDATE boucles SET statut='terminee', maj=? WHERE id=?", (maintenant, b["id"]))
                self.base.evenement("boucle", f"Boucle « {b['nom']} » terminée : budget de {b['iterations_max']}"
                                              " itérations atteint.", agent=b["responsable"])
                continue
            comp = competences.TYPES.get(b["genre"])
            m = self.base.nouvelle_mission(b["responsable"], b["genre"],
                                           f"{getattr(comp, 'TITRE', b['genre'])} (boucle « {b['nom']} », "
                                           f"itération {b['iterations'] + 1})",
                                           b["params"], b["objectif"], priorite=6, demandeur="boucle",
                                           boucle=b["id"], tentatives_max=self.reglages["tentatives_max"])
            self.base.ecrire("UPDATE boucles SET iterations=iterations+1, prochaine=?, maj=? WHERE id=?",
                             (maintenant + b["intervalle_s"], maintenant, b["id"]))
            lancees.append(m)
        return lancees

    def _suite_boucle(self, mission, ok, erreur=None):
        if not mission.get("boucle"):
            return
        if ok:
            self.base.ecrire("UPDATE boucles SET erreurs_de_suite=0, derniere_erreur=NULL, maj=? WHERE id=?",
                             (time.time(), mission["boucle"]))
            return
        self.base.ecrire("UPDATE boucles SET erreurs_de_suite=erreurs_de_suite+1, derniere_erreur=?, maj=? WHERE id=?",
                         (erreur, time.time(), mission["boucle"]))
        b = self.base.un("SELECT * FROM boucles WHERE id=?", (mission["boucle"],))
        if b and b["erreurs_de_suite"] >= 3:
            self.base.ecrire("UPDATE boucles SET statut='pause' WHERE id=?", (b["id"],))
            self.base.evenement("boucle", f"Boucle « {b['nom']} » mise en pause après 3 erreurs de suite.",
                                agent=b["responsable"], niveau="alerte")
