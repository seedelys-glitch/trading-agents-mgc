# -*- coding: utf-8 -*-
"""
Agent « Piège » : pourquoi ce trade risque d'échouer (calcul déterministe, aucune IA).

Jabran a 2 à 3 fois plus de setups perdants que gagnants, surtout à cause des pièges : avant son vrai mouvement,
le marché va chercher la liquidité (plus hauts / plus bas d'Asie, de Londres, de la veille) et touche les stops.
Ce module regarde la configuration calculée par le programme (setup.py) et liste les signaux de piège :

  - liquidité INTACTE entre l'entrée et le départ de l'impulsion (Fibo 1) : le prix risque d'aller la chercher
    à travers le stop avant de partir (le piège n° 1) ;
  - prix autour du 50 % du Fibo (zone de range / manipulation pour Jabran) ;
  - le prix vient de balayer une liquidité DANS le sens du trade (souvent un retournement contre lui) ;
  - order flow (estimé) en divergence contre le trade ;
  - stop très court par rapport à la volatilité (moins de 0,3 ATR H1 : une mèche suffit).

Bons signes (notés à part) : la liquidité côté stop a déjà été balayée (le marché a fait son plein).
Niveau : faible (0-1 point), moyen (2), fort (3 et plus). « fort » limite le statut du desk à « ATTENDRE ».
"""

POINTS_FORT = 3


def evaluer(sens, config_trade, calculs_faits):
    """sens : « achat » ou « vente ». Renvoie {niveau, points, signaux, bons_signes, a_attendre}."""
    signaux, bons, a_attendre = [], [], []
    points = 0
    if not config_trade:
        return {"niveau": "inconnu", "points": 0, "signaux": [], "bons_signes": [], "a_attendre": []}
    fibo = calculs_faits.get("fibo") or {}
    liq = calculs_faits.get("liquidite") or {}
    marche = calculs_faits.get("marche") or {}
    atr = float(marche.get("atr_H1") or 0) or None
    entree, stop = float(config_trade["entree"]), float(config_trade["stop"])
    depart = (fibo.get("niveaux") or {}).get("1")
    achat = sens == "achat"
    cote_stop = "bas" if achat else "haut"

    # 1. Liquidité intacte entre l'entrée et le départ de l'impulsion (côté stop)
    if liq.get("disponible"):
        borne = float(depart) if depart is not None else (stop - 3 * (atr or 0) if achat else stop + 3 * (atr or 0))
        bas, haut = (min(borne, entree), entree) if achat else (entree, max(borne, entree))
        cote = [p for p in liq.get("niveaux") or [] if p.get("cote") == cote_stop and bas <= float(p["prix"]) <= haut]
        intactes = [p for p in cote if p.get("etat") == "intacte"]
        balayees = [p for p in cote if p.get("etat") == "balayée"]
        if intactes:
            # la plus proche de l'entrée : juste sous l'entrée pour un achat, juste au-dessus pour une vente
            p = max(intactes, key=lambda x: x["prix"]) if achat else min(intactes, key=lambda x: x["prix"])
            points += 3
            signaux.append(f"Liquidité intacte côté stop : {p['nom']} à {p['prix']}, entre ton entrée {entree} et le "
                           f"départ de l'impulsion. Le marché risque d'aller la chercher à travers ton stop {stop}.")
            a_attendre.append(f"attendre que le {p['nom']} ({p['prix']}) soit balayé (mèche puis retour) avant d'entrer")
        if balayees and not intactes:
            p = balayees[-1]
            bons.append(f"La liquidité côté stop a déjà été prise ({p['nom']} {p['prix']}, {p.get('quand') or ''}) : "
                        "le marché a fait son plein.")
        # le prix vient de balayer une liquidité dans le sens du trade (au-dessus pour un achat)
        derniere = liq.get("derniere_liquidite_prise")
        if derniere and derniere.get("cote") == ("haut" if achat else "bas"):
            points += 1
            signaux.append(f"Le prix vient de balayer le {derniere['nom']} ({derniere['prix']}) dans le sens de ton "
                           f"trade : souvent un retournement contre {'les acheteurs' if achat else 'les vendeurs'}.")

    # 2. Prix autour du 50 % (range avant manipulation)
    r = fibo.get("retracement_actuel")
    if r is not None and 0.44 <= float(r) <= 0.56:
        points += 2
        signaux.append("Le prix est autour du 50 % du Fibo : pour toi, c'est un range avant une manipulation.")
        a_attendre.append("attendre que le prix atteigne la zone 0.618-0.893")

    # 3. Order flow en divergence contre le trade
    flux = calculs_faits.get("orderflow") or {}
    div = flux.get("divergence") or ""
    if achat and "acheteurs qui s'essoufflent" in div:
        points += 1
        signaux.append("Order flow (estimé) : les acheteurs s'essoufflent.")
    if not achat and "vendeurs qui s'essoufflent" in div:
        points += 1
        signaux.append("Order flow (estimé) : les vendeurs s'essoufflent.")

    # 4. Stop trop court pour la volatilité
    if atr and abs(entree - stop) < 0.3 * atr:
        points += 1
        signaux.append(f"Stop très court ({abs(entree - stop):.1f} points) pour la volatilité (ATR H1 {atr:.1f}) : "
                       "une simple mèche peut le toucher.")

    niveau = "fort" if points >= POINTS_FORT else "moyen" if points == 2 else "faible"
    return {"niveau": niveau, "points": points, "signaux": signaux, "bons_signes": bons, "a_attendre": a_attendre}


def veto(resultat):
    """Message d'« ATTENDRE » si le risque de piège est fort, sinon None."""
    if resultat and resultat.get("niveau") == "fort":
        suite = (" À faire : " + " ; ".join(resultat["a_attendre"]) + ".") if resultat.get("a_attendre") else ""
        return "Piège probable (agent Piège) : " + " ".join(resultat["signaux"][:2]) + suite
    return None
