"""Serveur de la veille du desk : http://127.0.0.1:8791 (local seulement, un seul à la fois).

  GET  /api/veille                état des agents de veille
  GET  /api/evenements?depuis=N   événements après le numéro N
  POST /api/veille/commande       {"texte": "état de la cascade" | "coupe la cascade" | ...} -> {"reponse"}
  POST /api/setups/noter          {"image": base64, "extra", "resultat", "quand", "source"} -> {"reponse"}
  GET  /api/setups/stats          points communs du journal des setups -> {"reponse"}
  POST /api/actus/analyser        {"texte", "source"} -> {"impact", "sens", "resume", "traduction"}
  POST /api/veille/arret          arrête la veille (Jarvis la relance avec le nouveau code après une mise à jour)
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .service import DOSSIER, Veille

PORT = int(os.environ.get("VEILLE_PORT", "8791"))
VERSION = "2026-10-24d"   # Jarvis compare : si elle change, il arrête l'ancienne veille et lance la nouvelle
log = logging.getLogger("veille")


def fabrique(veille: Veille):
    class Gestion(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def envoyer(self, code: int, data) -> None:
            corps = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/api/veille":
                return self.envoyer(200, dict(veille.etat(), service="veille", version=VERSION))
            if u.path == "/api/evenements":
                try:
                    n = int((parse_qs(u.query).get("depuis") or ["0"])[0])
                except ValueError:
                    n = 0
                return self.envoyer(200, {"evenements": veille.depuis(n), "dernier_id": veille.dernier_id()})
            if u.path == "/api/setups/stats":
                return self.envoyer(200, {"reponse": veille.stats_setups()})
            self.envoyer(404, {"erreur": "inconnu"})

        def do_POST(self):
            chemin = urlparse(self.path).path
            limites = {"/api/veille/commande": 10_000, "/api/actus/analyser": 100_000,
                       "/api/setups/noter": 30_000_000, "/api/veille/arret": 1_000}
            if chemin not in limites:
                return self.envoyer(404, {"erreur": "inconnu"})
            # une page web d'un autre site ne doit pas pouvoir piloter la veille
            if self.headers.get("Origin"):
                return self.envoyer(403, {"erreur": "origine refusée"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > limites[chemin]:
                    return self.envoyer(413, {"erreur": "trop gros"})
                data = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                return self.envoyer(400, {"erreur": "json"})
            if chemin == "/api/veille/arret":
                log.info("Veille : arrêt demandé (mise à jour).")
                self.envoyer(200, {"reponse": "arrêt"})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return None
            if chemin == "/api/veille/commande":
                rep = veille.commande(str(data.get("texte") or ""))
                return self.envoyer(200, {"reponse": rep, "connu": rep is not None})
            if chemin == "/api/actus/analyser":
                return self.envoyer(200, veille.analyser_actu(str(data.get("texte") or ""),
                                                              str(data.get("source") or "")))
            try:
                image = base64.b64decode(str(data.get("image") or ""), validate=True)
            except (binascii.Error, ValueError):
                return self.envoyer(400, {"erreur": "image"})
            rep = veille.noter_setup(image, str(data.get("extra") or ""), str(data.get("resultat") or ""),
                                     str(data.get("quand") or ""), str(data.get("source") or ""))
            self.envoyer(200, {"reponse": rep})

    return Gestion


class ServeurExclusif(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows : pas de 2e veille sur le même port
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main() -> int:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(DOSSIER / "veille.log"), level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        serveur = ServeurExclusif(("127.0.0.1", PORT), fabrique(veille := Veille()))
    except OSError:
        log.info("Veille : le port %s est déjà pris (une veille tourne déjà).", PORT)
        return 3
    veille.demarrer()
    log.info("Veille du desk en marche sur http://127.0.0.1:%s", PORT)
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    serveur.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
