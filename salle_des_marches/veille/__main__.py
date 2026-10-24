"""Serveur de la veille du desk : http://127.0.0.1:8791 (local seulement, un seul à la fois).

  GET  /api/veille                état des agents de veille
  GET  /api/evenements?depuis=N   événements après le numéro N
  POST /api/veille/commande       {"texte": "état de la cascade" | "coupe la cascade" | ...} -> {"reponse"}
"""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .service import DOSSIER, Veille

PORT = int(os.environ.get("VEILLE_PORT", "8791"))
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
                return self.envoyer(200, dict(veille.etat(), service="veille"))
            if u.path == "/api/evenements":
                try:
                    n = int((parse_qs(u.query).get("depuis") or ["0"])[0])
                except ValueError:
                    n = 0
                return self.envoyer(200, {"evenements": veille.depuis(n), "dernier_id": veille.dernier_id()})
            self.envoyer(404, {"erreur": "inconnu"})

        def do_POST(self):
            if urlparse(self.path).path != "/api/veille/commande":
                return self.envoyer(404, {"erreur": "inconnu"})
            # une page web d'un autre site ne doit pas pouvoir couper la veille
            if self.headers.get("Origin"):
                return self.envoyer(403, {"erreur": "origine refusée"})
            try:
                n = min(int(self.headers.get("Content-Length") or 0), 10000)
                data = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                return self.envoyer(400, {"erreur": "json"})
            rep = veille.commande(str(data.get("texte") or ""))
            self.envoyer(200, {"reponse": rep, "connu": rep is not None})

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
