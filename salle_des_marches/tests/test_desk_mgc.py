# -*- coding: utf-8 -*-
"""Le desk en analyste MGC : régime, configuration du programme, statuts, vetos, calendrier (sans IA)."""

import copy
import datetime as dt

import pytest

import bureau
import calculs
from mgc import calendrier_cme as cal
from mgc import regime, setup


def fibo(sens="haussière"):
    """Impulsion haussière de 4100 à 4200 (ou baissière de 4200 à 4100), FVG sur le 0.705 seulement."""
    if sens == "haussière":
        depart, fin, fvg = 4100.0, 4200.0, [4127.0, 4132.0]
    else:
        depart, fin, fvg = 4200.0, 4100.0, [4168.0, 4173.0]
    niveaux = {f"{x:g}": round(fin + x * (depart - fin), 1) for x in calculs.NIVEAUX_FIBO}
    zones = [{"niveau": f"{x:g}", "prix": niveaux[f"{x:g}"], "fvg_dessus": x == 0.705, "fvg": fvg if x == 0.705 else None}
             for x in calculs.ZONES_ENTREE]
    return {"disponible": True, "impulsion": sens, "niveaux": niveaux, "zones_entree": zones, "retracement_actuel": 0.6}


def faits(sens="haussière", prix=4140.0, temps_reel=True):
    return {"marche": {"prix": prix, "ticker": "MGCZ26"}, "fibo": fibo(sens), "donnees": {"temps_reel": temps_reel},
            "regime": {"regime": "GOLD_BULL", "confiance": "haute"}}


def desk(haussiers, baissiers):
    cles = [s["cle"] for s in bureau.SPECIALISTES]
    biais = ["haussier"] * haussiers + ["baissier"] * baissiers
    biais += ["neutre"] * (len(cles) - len(biais))
    avis = {c: {"biais": b, "confiance": 4, "argument": f"argument {c}"} for c, b in zip(cles, biais, strict=True)}
    return avis, copy.deepcopy(avis)


def decision_chef():
    return {"decision": "long", "blocages": [], "prix_non_verifies": [], "votes": {}, "raison": "ok"}


# ------------------------------------------------------------------ configuration calculée par le programme

def test_setup_achat():
    s, motif = setup.construire(fibo(), "achat", 4140.0)
    assert motif == ""
    assert (s["niveau"], s["entree"], s["stop"]) == ("0.705", 4129.5, 4126.0)  # bas du FVG - 20 % de sa hauteur
    assert (s["tp1"], s["tp2"], s["tp3"], s["tp4"]) == (4200.0, 4227.2, 4327.2, 4461.8)


def test_setup_stop_sans_place_sous_le_fvg():
    """FVG au-dessus du niveau d'entrée : stop à 20 % de l'écart jusqu'au niveau Fibo suivant."""
    f = fibo()
    for z in f["zones_entree"]:
        if z["niveau"] == "0.705":
            z["fvg"] = [4130.5, 4131.0]
    s, _ = setup.construire(f, "achat", 4140.0)
    assert s["stop"] == 4127.8 and s["stop"] < s["entree"]  # 4129.5 - 0.2 x (4129.5 - 4121.4), arrondi vers le bas


def test_setup_vente():
    s, _ = setup.construire(fibo("baissière"), "vente", 4160.0)
    assert (s["entree"], s["stop"], s["tp1"]) == (4170.5, 4174.0, 4100.0)  # haut du FVG + 20 % de sa hauteur
    assert (s["tp2"], s["tp3"], s["tp4"]) == (4072.8, 3972.8, 3838.2)


def test_setup_refuse():
    assert setup.construire(fibo(), "vente", 4140.0)[0] is None              # impulsion dans le mauvais sens
    sans_fvg = fibo()
    for z in sans_fvg["zones_entree"]:
        z["fvg_dessus"] = False
    assert "FVG" in setup.construire(sans_fvg, "achat", 4140.0)[1]
    invalide = dict(fibo(), retracement_actuel=1.2)
    assert setup.construire(invalide, "achat", 4140.0)[0] is None
    assert setup.construire({"disponible": False, "raison": "rien"}, "achat", 4140.0) == (None, "rien")


def test_jamais_d_entree_sur_le_0_5():
    f = fibo()
    for z in f["zones_entree"]:
        z["fvg_dessus"] = True
        z["fvg"] = [z["prix"] - 1, z["prix"] + 1]
    for prix in (4140.0, 4150.0, 4160.0):
        assert setup.construire(f, "achat", prix)[0]["niveau"] != "0.5"


# ------------------------------------------------------------------ statuts

def test_achat_envisageable(config):
    avis, debat = desk(5, 1)
    d = bureau.finaliser_mgc(decision_chef(), avis, debat, faits(), [], config)
    assert d["statut"] == "ACHAT ENVISAGEABLE"
    assert d["decision"] == "long"
    assert d["risque"]["contrats"] == 12          # 3,5 points : 38,50 $ net par contrat, budget 500 $
    assert d["risque"]["ratio_net_tp1"] == 18.22
    assert d["sl"] == "4126.0" and d["tp4"] == "4461.8"
    assert d["biais"]["accord"] == "5/6"


def test_donnees_differees_au_mieux_attendre(config):
    avis, debat = desk(6, 0)
    d = bureau.finaliser_mgc(decision_chef(), avis, debat, faits(temps_reel=False), ["Données différées."], config)
    assert d["statut"] == "ATTENDRE"
    assert d["decision"] == "pas de trade"
    assert d["setup"]["entree"] == 4129.5          # niveaux à surveiller
    assert any("différés" in i for i in d["incertitudes"])


def test_desk_divise_aucune_opportunite(config):
    avis, debat = desk(3, 3)
    chef = dict(decision_chef(), blocages=["Desk divisé : il faut au moins 4 spécialistes sur 6 dans le même sens."])
    d = bureau.finaliser_mgc(chef, avis, debat, faits(), [], config)
    assert d["statut"] == "AUCUNE OPPORTUNITÉ"
    assert d["setup"] is None


def test_veto_du_risque(config):
    avis, debat = desk(5, 0)
    d = bureau.finaliser_mgc(decision_chef(), avis, debat, faits(), [], config, perte_du_jour_usd=1000)
    assert d["statut"] == "AUCUNE OPPORTUNITÉ"
    assert any("Limite de perte" in v for v in d["vetos"])


def test_prix_inventes_par_le_chef(config):
    avis, debat = desk(5, 0)
    chef = dict(decision_chef(), prix_non_verifies=[4133.3])
    d = bureau.finaliser_mgc(chef, avis, debat, faits(), [], config)
    assert d["statut"] == "ATTENDRE"
    assert any("4133.3" in i for i in d["vetos_informatifs"])


def test_vente_dans_le_bon_sens(config):
    avis, debat = desk(0, 5)
    d = bureau.finaliser_mgc(decision_chef(), avis, debat, faits("baissière", 4160.0), [], config)
    assert d["statut"] == "VENTE ENVISAGEABLE"
    assert d["decision"] == "short"


def test_blocage_sans_ia():
    d = bureau.bloquer(faits(), ["Pause d'urgence active."], ["Hors fenêtre."])
    assert d["statut"] == "ANALYSE BLOQUÉE"
    assert d["decision"] == "pas de trade"
    assert d["blocages"] == ["Pause d'urgence active.", "Hors fenêtre."]


def test_debat_seulement_en_cas_de_vrai_desaccord():
    assert bureau.desaccord_reel(desk(5, 1)[0]) is True
    assert bureau.desaccord_reel(desk(4, 0)[0]) is False   # haussiers + neutres : pas de débat
    assert bureau.desaccord_reel(desk(0, 6)[0]) is False


def test_les_statuts_sont_analytiques():
    assert set(bureau.STATUTS) == {"ACHAT ENVISAGEABLE", "VENTE ENVISAGEABLE", "ATTENDRE", "AUCUNE OPPORTUNITÉ",
                                   "ANALYSE BLOQUÉE"}


# ------------------------------------------------------------------ régime

def macro(dollar, taux):
    return {"dollar_DXY": {"variation_5_jours_pct": dollar}, "taux_10_ans_US": {"variation_5_jours_pct": taux}}


@pytest.mark.parametrize("prix, pente, dollar, taux, attendu, confiance", [
    ("au-dessus", "montante", -1.0, -3.0, "GOLD_BULL", "haute"),
    ("au-dessus", "montante", 1.0, 0.0, "HAVEN_TEST", "moyenne"),
    ("en dessous", "descendante", 1.0, 3.0, "HEADWIND", "haute"),
    ("en dessous", "montante", 0.1, 0.5, "GOLDILOCKS", "faible"),
])
def test_regimes(prix, pente, dollar, taux, attendu, confiance):
    r = regime.detecter({"macro": macro(dollar, taux), "tendance": {"ema200_D1": {"prix": prix, "pente": pente}}})
    assert (r["regime"], r["confiance"]) == (attendu, confiance)
    assert r["justification"] and r["horodatage"]


def test_regime_inconnu_si_donnees_manquantes():
    assert regime.detecter({"macro": macro(None, 1.0), "tendance": {"ema200_D1": {"prix": "au-dessus"}}})["regime"] == "UNKNOWN"
    assert regime.detecter({})["regime"] == "UNKNOWN"


# ------------------------------------------------------------------ calendrier (le faux FOMC du 16/10/2026)

def flux(*evenements):
    return lambda: [{"country": "USD", "title": t, "impact": i, "date": d} for t, i, d in evenements]


def test_discours_du_president_n_est_pas_un_jour_de_fomc(config):
    source = flux(("Fed Chairman Warsh Speaks", "High", "2026-10-15T23:30:00-04:00"),
                  ("FOMC Member Hammack Speaks", "Low", "2026-10-15T16:30:00-04:00"))
    c = calculs.calendrier(dt.datetime(2026, 10, 16, 10, 0, tzinfo=cal.PARIS), config, source)
    assert c["fomc_aujourdhui"] is False
    assert c["blocages"] == []
    assert len(c["liste"]) == 1  # le discours d'un simple membre (impact faible) est ignoré
    pendant = calculs.calendrier(dt.datetime(2026, 10, 16, 5, 45, tzinfo=cal.PARIS), config, source)
    assert pendant["blocages"] and pendant["fomc_aujourdhui"] is False


def test_jour_de_reunion_du_fomc(config):
    source = flux(("FOMC Statement", "High", "2026-10-28T14:00:00-04:00"))
    c = calculs.calendrier(dt.datetime(2026, 10, 28, 10, 0, tzinfo=cal.PARIS), config, source)
    assert c["fomc_aujourdhui"] is True
    assert any(b.startswith("Jour de réunion") for b in c["blocages"])
    assert "Topstep" in c["regle_prop_firm"]


def test_calendrier_indisponible(config):
    def panne():
        raise OSError("pas d'internet")
    assert calculs.calendrier(dt.datetime(2026, 10, 20, 10, 0, tzinfo=cal.PARIS), config, panne)["disponible"] is False


def test_vetos_niveau1(config):
    from mgc import vetos
    from mgc.contrats import ContractManager

    instant = dt.datetime(2026, 10, 20, 16, 0, tzinfo=cal.PARIS)
    etat = ContractManager(config).etat(instant)
    n = vetos.niveau1(instant, config, etat, [], False, "temps_reel")
    assert n == {"bloquants": [], "informatifs": []}
    n = vetos.niveau1(instant, config, etat, [], False, "differee")
    assert n["bloquants"] == [] and len(n["informatifs"]) == 1
    assert vetos.niveau1(instant, config, etat, [], True, "temps_reel")["bloquants"]
    assert vetos.niveau1(instant, config, etat, [], False, "perimee", ["vieux"])["bloquants"]
    assert vetos.niveau1(instant, config, etat, [], False, "temps_reel", calendrier_ok=False)["bloquants"]
    soir = dt.datetime(2026, 10, 20, 22, 0, tzinfo=cal.PARIS)
    assert any("fenêtre" in m for m in vetos.niveau1(soir, config, etat, [], False, "temps_reel")["informatifs"])
