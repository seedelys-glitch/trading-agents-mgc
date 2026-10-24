"""IA locale de la veille (LM Studio sur le PC, 127.0.0.1:1234, API compatible OpenAI). Aucune clé, rien en ligne.

Utilise le modèle DÉJÀ chargé (une seule IA tient dans la carte graphique : on n'en charge jamais une autre).
complete() : texte ; see() : image (graphique) + texte, si le modèle chargé lit les images (Gemma 4 : oui).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request

log = logging.getLogger("veille")

URL = os.environ.get("VEILLE_IA_URL", "http://127.0.0.1:1234")


class IALocale:
    def __init__(self, url: str = URL):
        self.url = url.rstrip("/")
        self.vision_error = ""
        self._sem = threading.BoundedSemaphore(1)   # un appel à la fois depuis la veille
        self._modele: tuple[float, str | None] = (0.0, None)

    def _json(self, chemin: str, corps: dict | None = None, delai: float = 5.0) -> dict:
        data = json.dumps(corps).encode("utf-8") if corps is not None else None
        req = urllib.request.Request(self.url + chemin, data=data,
                                     headers={"Content-Type": "application/json"} if data else {})
        with urllib.request.urlopen(req, timeout=delai) as r:
            return json.loads(r.read().decode("utf-8") or "{}")

    def modele(self) -> str | None:
        """Le modèle chargé dans LM Studio (mis en cache 60 s) ; None si LM Studio ne répond pas ou rien n'est chargé."""
        t, m = self._modele
        if time.time() - t < 60:
            return m
        m = None
        try:
            donnees = self._json("/api/v0/models", delai=3).get("data", [])
            charges = [x.get("id") for x in donnees if x.get("state") == "loaded" and x.get("type") != "embeddings"]
            m = next((x for x in charges if "gemma" in (x or "").lower()), charges[0] if charges else None)
        except (OSError, ValueError, urllib.error.URLError):
            try:  # LM Studio sans l'API v0 : même choix que Jarvis (Gemma d'abord)
                ids = [x.get("id") for x in self._json("/v1/models", delai=3).get("data", [])
                       if "embed" not in (x.get("id") or "")]
                m = next((x for x in ids if "gemma" in x.lower()), ids[0] if ids else None)
            except (OSError, ValueError, urllib.error.URLError):
                m = None
        self._modele = (time.time(), m)
        return m

    def _appel(self, messages: list[dict], max_tokens: int, delai: float) -> str | None:
        modele = self.modele()
        if not modele:
            self.vision_error = "LM Studio ne répond pas ou aucun modèle n'est chargé."
            return None
        with self._sem:
            try:
                r = self._json("/v1/chat/completions", {"model": modele, "messages": messages, "temperature": 0.3,
                                                        "max_tokens": max_tokens, "stream": False}, delai=delai)
                out = r["choices"][0]["message"].get("content") or ""
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300].lower()
                self.vision_error = ("Le modèle chargé dans LM Studio ne sait pas lire les images."
                                     if any(w in detail for w in ("image", "vision", "multimodal", "mmproj"))
                                     else "LM Studio a refusé la demande.")
                log.warning("IA locale : %s %s", e.code, detail[:120])
                return None
            except (OSError, ValueError, KeyError, IndexError, urllib.error.URLError) as e:
                self.vision_error = "LM Studio n'a pas répondu à temps."
                log.warning("IA locale : %s", e)
                return None
        out = re.sub(r"<think>.*?</think>", "", out, flags=re.S)
        return re.sub(r"[*#`]+", "", out).strip() or None

    def complete(self, prompt: str, max_tokens: int = 700) -> str | None:
        self.vision_error = ""
        return self._appel([{"role": "user", "content": prompt + " /no_think"}], max_tokens, 120)

    def see(self, image: bytes, prompt: str, mime: str = "image/png", max_tokens: int = 700) -> str | None:
        self.vision_error = ""
        url = f"data:{mime};base64," + base64.b64encode(image).decode("ascii")
        return self._appel([{"role": "user", "content": [{"type": "text", "text": prompt + " /no_think"},
                                                         {"type": "image_url", "image_url": {"url": url}}]}],
                           max_tokens, 240)


def mime_of(image: bytes) -> str:
    if image[:2] == b"\xff\xd8":
        return "image/jpeg"
    if image[:4] == b"RIFF" and image[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"
