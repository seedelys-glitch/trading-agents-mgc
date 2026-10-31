# -*- coding: utf-8 -*-
"""
IA locale (LM Studio, API compatible OpenAI sur le PC). Aucune clé dans l'université.

Rédaction (31/10) : pour les textes longs (réunion du soir, cours du mentor, personnalités), l'université demande
d'abord à Jarvis (POST http://127.0.0.1:8765/api/rediger, sur le PC seulement) qui utilise Groq avec SA clé :
la clé ne quitte jamais Jarvis. Si Jarvis ne répond pas, LM Studio rédige. Chaque texte passe par la charte
(charte.py) : un texte qui l'enfreint est refusé et la version sans IA, faite de faits calculés, est gardée.

L'IA n'est utilisée que pour RÉDIGER un commentaire pédagogique à partir de faits déjà calculés.
Elle ne fournit jamais un chiffre : un commentaire qui contient un nombre absent des faits est refusé.
Chaque appel est noté dans la table ia_appels (durée, statut), avec un budget par jour et un nombre
d'appels simultanés limité (pour ne pas saturer la carte graphique).
"""

import json
import re
import threading
import time
import urllib.error
import urllib.request

NOMBRE = re.compile(r"(?<![\w.])-?\d+(?:[.,]\d+)?")


class IALocale:
    def __init__(self, base, reglages):
        self.base = base
        self.reglages = reglages
        self._sem = threading.BoundedSemaphore(max(1, int(reglages.get("concurrence_ia", 1))))
        self._etat = {"joignable": None, "modeles": [], "verifie": 0}

    def _url(self, chemin):
        return self.reglages["ia_url"].rstrip("/") + chemin

    def etat(self, cache_s=30):
        """LM Studio répond-il, et quels modèles sont chargés ? (mis en cache 30 s)"""
        if time.time() - self._etat["verifie"] < cache_s:
            return dict(self._etat)
        try:
            with urllib.request.urlopen(self._url("/models"), timeout=3) as r:
                modeles = [m.get("id") for m in json.loads(r.read().decode("utf-8")).get("data", [])]
            self._etat = {"joignable": True, "modeles": modeles, "verifie": time.time()}
        except (OSError, ValueError):
            self._etat = {"joignable": False, "modeles": [], "verifie": time.time()}
        return dict(self._etat)

    def appels_du_jour(self):
        debut = time.time() - (time.time() % 86400)
        return self.base.un("SELECT COUNT(*) AS n FROM ia_appels WHERE ts>=?", (debut,))["n"]

    def disponible(self):
        r = self.reglages
        return bool(r.get("ia_commentaires")) and self.appels_du_jour() < int(r.get("ia_appels_max_jour", 0)) \
            and self.etat()["joignable"]

    def completer(self, consigne, texte, mission=None, agent=None, role="", max_tokens=400, delai=None):
        """Un appel de chat. Renvoie le texte, ou None (pas joignable, budget atteint, erreur).
        delai : secondes d'attente au plus pour cet appel (par défaut ia_delai_s)."""
        if not self.disponible():
            return None
        modele = self.reglages.get("ia_modele") or (self.etat()["modeles"] or [""])[0]
        corps = json.dumps({"model": modele, "temperature": 0.2, "max_tokens": int(max_tokens),
                            "messages": [{"role": "system", "content": consigne},
                                         {"role": "user", "content": texte}]}).encode("utf-8")
        debut = time.time()
        with self._sem:
            try:
                req = urllib.request.Request(self._url("/chat/completions"), data=corps,
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=float(delai or self.reglages.get("ia_delai_s", 90))) as r:
                    reponse = json.loads(r.read().decode("utf-8"))
                contenu = reponse["choices"][0]["message"]["content"]
                contenu = re.sub(r"<think>.*?</think>", "", contenu, flags=re.S).strip()
                self._noter(mission, agent, role, modele, debut, "ok")
                return contenu
            except (OSError, ValueError, KeyError, IndexError, urllib.error.URLError) as e:
                self._noter(mission, agent, role, modele, debut, "erreur", str(e)[:300])
                return None

    def _noter(self, mission, agent, role, modele, debut, statut, erreur=None):
        self.base.ecrire("INSERT INTO ia_appels(ts, mission, agent, role, modele, duree_s, statut, erreur)"
                         " VALUES (?,?,?,?,?,?,?,?)",
                         (time.time(), mission, agent, role, modele, round(time.time() - debut, 2), statut, erreur))

    def commenter(self, faits, mission=None, agent=None, role="professeur"):
        """Commentaire pédagogique sur des faits calculés. Refusé s'il contient un chiffre absent des faits."""
        consigne = ("Tu es professeur de trading sur le Micro Gold (MGC). Explique en français simple, en 4 phrases "
                    "au plus, ce que veulent dire les faits ci-dessous pour un trader. N'écris AUCUN chiffre, aucun "
                    "prix, aucun pourcentage. Ne donne aucun conseil d'achat ou de vente. Ne fais aucune prévision.")
        texte = self.completer(consigne, faits, mission, agent, role)
        if not texte:
            return None
        autorises = {n.replace(",", ".") for n in NOMBRE.findall(faits)}
        etrangers = [n for n in NOMBRE.findall(texte) if n.replace(",", ".") not in autorises]
        if etrangers:
            self.base.evenement("ia", f"Commentaire IA refusé : chiffres non vérifiés ({', '.join(etrangers[:5])}).",
                                agent=agent, mission=mission, niveau="alerte")
            return None
        return texte

    # ------------------------------------------------------------------ rédaction (Groq via Jarvis, sinon LM Studio)
    def _par_jarvis(self, consigne, texte, max_tokens):
        url = self.reglages.get("redaction_url") or ""
        if not url or self.reglages.get("ia_redaction", "groq") != "groq":
            return None
        corps = json.dumps({"consigne": consigne, "texte": texte, "max_tokens": int(max_tokens)}).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=corps, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=float(self.reglages.get("ia_delai_s", 90))) as r:
                reponse = json.loads(r.read().decode("utf-8"))
            return (reponse.get("texte") or "").strip() or None, reponse.get("ia") or "Groq (via Jarvis)"
        except (OSError, ValueError, urllib.error.URLError):
            return None

    def rediger(self, consigne, faits, mission=None, agent=None, role="professeur", max_tokens=900,
                chiffres_libres=False):
        """Texte rédigé à partir de faits. Renvoie {"texte", "ia"} ou None (pas d'IA, budget, charte, chiffre étranger).
        Les chiffres du texte doivent venir des faits, sauf chiffres_libres (cours tiré de sources citées)."""
        from . import charte

        r = self.reglages
        if not r.get("ia_commentaires") or self.appels_du_jour() >= int(r.get("ia_appels_max_jour", 0)):
            return None
        consigne = consigne + "\n\n" + charte.consigne()
        debut = time.time()
        res = self._par_jarvis(consigne, faits, max_tokens)
        if res:
            texte, ia = res
            self._noter(mission, agent, role, ia, debut, "ok")
        else:
            texte, ia = self.completer(consigne, faits, mission, agent, role, max_tokens), "LM Studio"
        if not texte:
            return None
        manques = charte.verifier(texte)
        if manques:
            self.base.evenement("ia", f"Texte IA refusé (charte : {', '.join(manques)}).", agent=agent, mission=mission,
                                niveau="alerte")
            return None
        if not chiffres_libres:
            autorises = {n.replace(",", ".") for n in NOMBRE.findall(faits)}
            etrangers = [n for n in NOMBRE.findall(texte) if n.replace(",", ".") not in autorises]
            if etrangers:
                self.base.evenement("ia", f"Texte IA refusé : chiffres non vérifiés ({', '.join(etrangers[:5])}).",
                                    agent=agent, mission=mission, niveau="alerte")
                return None
        return {"texte": texte, "ia": ia}
