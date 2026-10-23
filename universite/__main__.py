# -*- coding: utf-8 -*-
"""Lance l'université : python -m universite  (depuis Documents\\TradingAgents). Ctrl+C pour arrêter."""

import argparse
import logging
import sys
import time
import webbrowser

from . import config
from .serveur import Universite, lancer


def main():
    p = argparse.ArgumentParser(description="Université MGC (recherche et simulation seulement, aucun ordre)")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--sans-navigateur", action="store_true")
    args = p.parse_args()
    config.DONNEES.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=config.DONNEES / "universite.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    config.salle_importable()
    try:
        from mgc.journal_json import FiltreSecrets
        for h in logging.getLogger().handlers:
            h.addFilter(FiltreSecrets())
    except ImportError:
        pass
    port = args.port or config.charger()["port"]
    try:
        univ = Universite(demarrer_moteur=False)
        serveur = lancer(univ, port)
    except OSError:
        # Déjà lancée (port occupé) : on ouvre simplement la page de celle qui tourne
        logging.info("Université déjà en marche sur le port %s", port)
        if not args.sans_navigateur:
            webbrowser.open(f"http://127.0.0.1:{port}/")
        return
    univ.moteur.demarrer()
    adresse = f"http://127.0.0.1:{serveur.server_address[1]}/"
    logging.info("Université démarrée sur %s", adresse)
    if sys.stdout:  # pythonw n'a pas de console
        print(f"Université MGC : {adresse}  (Ctrl+C pour arrêter)")
    if not args.sans_navigateur:
        webbrowser.open(adresse)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        serveur.shutdown()
        univ.arreter()


if __name__ == "__main__":
    main()
