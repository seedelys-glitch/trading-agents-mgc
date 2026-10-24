# -*- coding: utf-8 -*-
"""Nouveaux agents du desk (24/10/2026) : Liquidité, Dollar & taux, Piège, vote pondéré, express, bulletin."""

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import bureau
import calculs
import commandes
from mgc import bulletin, piege

PARIS = "Europe/Paris"


# ------------------------------------------------------------------ Liquidité (Asie, Londres, veille)

def bougies_m5(speciales, debut="2026-10-21 00:00", fin="2026-10-22 17:00"):
    """Bougies 5 min (heure de Paris -> UTC) à 4200, sauf les bougies `speciales` {"AAAA-MM-JJ HH:MM": (h, l, c)}."""
    index = pd.date_range(debut, fin, freq="5min", tz=PARIS, inclusive="left")
    df = pd.DataFrame({"o": 4200.0, "h": 4201.0, "l": 4199.0, "c": 4200.0, "v": 100.0}, index=index)
    for quand, (h, l, c) in speciales.items():
        t = pd.Timestamp(quand, tz=PARIS)
        df.loc[t, ["h", "l", "c"]] = [h, l, c]
    return df.tz_convert("UTC")


def jours():
    index = pd.DatetimeIndex(["2026-10-21", "2026-10-22"]).tz_localize("UTC")
    return pd.DataFrame({"o": [4200.0, 4200.0], "h": [4230.0, 4218.0], "l": [4150.0, 4185.0], "c": [4200.0, 4212.0],
                         "v": 1000.0}, index=index)


def niveau(liq, nom):
    return next(p for p in liq["niveaux"] if p["nom"] == nom)


def test_liquidite_balayee_intacte_cassee():
    m5 = bougies_m5({
        "2026-10-22 03:00": (4210.0, 4199.0, 4205.0),   # plus haut d'Asie 4210
        "2026-10-22 05:00": (4201.0, 4188.0, 4195.0),   # plus bas d'Asie 4188
        "2026-10-22 10:00": (4215.0, 4199.0, 4212.0),   # plus haut de Londres 4215
        "2026-10-22 12:00": (4201.0, 4190.0, 4195.0),   # plus bas de Londres 4190
        "2026-10-22 16:00": (4218.0, 4205.0, 4212.0),   # mèche au-dessus de 4215 puis retour
        "2026-10-22 16:55": (4213.0, 4199.0, 4200.0),   # dernière clôture 4200 : sous 4210 et 4215
    })
    liq = calculs.liquidite_sessions({"M5": m5, "D1": jours()}, a_h1=10.0)
    assert liq["disponible"]
    assert niveau(liq, "plus haut Londres")["etat"] == "balayée"
    assert niveau(liq, "plus haut Londres")["quand"] == "22/10 16h00"
    assert niveau(liq, "plus haut Asie")["etat"] == "balayée"      # 4210 dépassé par la bougie de 10h, retour depuis
    assert niveau(liq, "plus bas Londres")["etat"] == "intacte"
    assert niveau(liq, "plus haut de la veille (D1)")["etat"] == "intacte"   # 4230 jamais atteint
    assert liq["liquidite_intacte_en_dessous"]["prix"] == 4190.0
    assert liq["liquidite_intacte_en_dessous"]["distance_atr_H1"] == 1.0
    assert liq["derniere_liquidite_prise"]["nom"] == "plus haut Londres"
    assert "_ts" not in json.dumps(liq)


def test_liquidite_cassee_et_session_en_formation():
    m5 = bougies_m5({"2026-10-22 03:00": (4210.0, 4199.0, 4205.0),
                     "2026-10-22 09:00": (4220.0, 4209.0, 4219.0),   # clôture au-dessus de 4210...
                     "2026-10-22 09:55": (4222.0, 4215.0, 4216.0)},  # ... et y reste
                    fin="2026-10-22 10:00")
    m5.iloc[-12:, m5.columns.get_loc("c")] = 4216.0
    liq = calculs.liquidite_sessions({"M5": m5, "D1": jours()}, a_h1=10.0)
    assert niveau(liq, "plus haut Asie")["etat"] == "cassée"
    assert niveau(liq, "plus haut Londres")["etat"] == "en formation"


def test_liquidite_sans_bougies():
    assert calculs.liquidite_sessions({"M5": pd.DataFrame(), "M15": pd.DataFrame()}, 10.0)["disponible"] is False


# ------------------------------------------------------------------ Dollar & taux

def serie(debut, n, depart, pas, freq="D"):
    index = pd.date_range(debut, periods=n, freq=freq, tz="UTC")
    return pd.Series([depart + i * pas for i in range(n)], index=index)


def test_macro_dollar_taux_argent():
    def faux(symbole, periode, intervalle):
        if intervalle == "1h":
            return serie("2026-10-20", 48, 100.0, 0.05, "h")
        depart = {"DX-Y.NYB": 100.0, "^TNX": 4.0, "SI=F": 50.0}[symbole]
        pas = {"DX-Y.NYB": 0.1, "^TNX": 0.01, "SI=F": -0.2}[symbole]
        return serie("2026-07-01", 60, depart, pas)

    or_ = pd.DataFrame({"c": [4000.0 + (10 if i % 2 else -10) * i for i in range(60)]},
                       index=pd.date_range("2026-07-01", periods=60, freq="D", tz="UTC"))
    m = calculs.macro("MGC=F", or_, telecharger=faux)
    assert m["dollar_DXY"]["au_dessus_moyenne_20_jours"] is True
    assert m["argent_SI"]["variation_5_jours_pct"] < 0
    assert "variation_24h_pct" in m["dollar_DXY"]
    assert "correlation_20j_or_dollar" in m
    assert m["argent_confirme_or_5j"] in (True, False)
    assert calculs.macro("NVDA")["disponible"] is False


def test_macro_tolere_une_panne():
    def panne(symbole, periode, intervalle):
        raise OSError("réseau coupé")

    m = calculs.macro("GC=F", None, telecharger=panne)
    assert m["dollar_DXY"] is None and m["argent_SI"] is None


# ------------------------------------------------------------------ Piège

def faits_piege(etat_londres="intacte", retracement=0.75):
    niveaux = {f"{x:g}": round(4200 + x * (4100 - 4200), 1) for x in calculs.NIVEAUX_FIBO}
    return {
        "marche": {"prix": 4135.0, "atr_H1": 10.0},
        "fibo": {"disponible": True, "impulsion": "haussière", "niveaux": niveaux, "retracement_actuel": retracement},
        "liquidite": {"disponible": True, "niveaux": [
            {"nom": "plus bas Londres", "cote": "bas", "prix": 4115.0, "etat": etat_londres, "quand": "22/10 12h00"},
            {"nom": "plus haut Asie", "cote": "haut", "prix": 4190.0, "etat": "intacte", "quand": None}],
            "derniere_liquidite_prise": None},
        "orderflow": {"divergence": None},
    }


SETUP = {"sens": "achat", "entree": 4129.5, "stop": 4126.0, "niveau": "0.705"}


def faits_desk():
    """Même desk que test_desk_mgc : impulsion haussière 4100 -> 4200, FVG sur le 0.705 (4127-4132)."""
    niveaux = {f"{x:g}": round(4200 + x * (4100 - 4200), 1) for x in calculs.NIVEAUX_FIBO}
    zones = [{"niveau": f"{x:g}", "prix": niveaux[f"{x:g}"], "fvg_dessus": x == 0.705,
              "fvg": [4127.0, 4132.0] if x == 0.705 else None} for x in calculs.ZONES_ENTREE]
    return {"marche": {"prix": 4140.0, "ticker": "MGCZ26"}, "donnees": {"temps_reel": True},
            "fibo": {"disponible": True, "impulsion": "haussière", "niveaux": niveaux, "zones_entree": zones,
                     "retracement_actuel": 0.6}, "regime": {"regime": "GOLD_BULL", "confiance": "haute"}}


def desk(haussiers, baissiers):
    cles = [s["cle"] for s in bureau.SPECIALISTES]
    sens = ["haussier"] * haussiers + ["baissier"] * baissiers
    sens += ["neutre"] * (len(cles) - len(sens))
    avis = {c: {"biais": b, "confiance": 4, "argument": f"argument {c}"} for c, b in zip(cles, sens, strict=True)}
    return avis, json.loads(json.dumps(avis))


def decision_chef():
    return {"decision": "long", "blocages": [], "prix_non_verifies": [], "votes": {}, "raison": "ok"}


def test_piege_liquidite_intacte_sous_l_entree():
    r = piege.evaluer("achat", SETUP, faits_piege())
    assert r["niveau"] == "fort"
    assert "plus bas Londres" in r["signaux"][0]
    message = piege.veto(r)
    assert message.startswith("Piège probable") and "4115.0" in message


def test_piege_liquidite_deja_prise_bon_signe():
    r = piege.evaluer("achat", SETUP, faits_piege("balayée"))
    assert r["niveau"] == "faible"
    assert r["bons_signes"] and piege.veto(r) is None


def test_piege_autour_du_50():
    r = piege.evaluer("achat", SETUP, faits_piege("balayée", retracement=0.5))
    assert r["niveau"] == "moyen" and "50 %" in r["signaux"][0]


def test_piege_divergence_et_stop_court():
    faits = faits_piege("balayée")
    faits["orderflow"]["divergence"] = "prix plus haut mais delta en baisse (acheteurs qui s'essoufflent)"
    r = piege.evaluer("achat", {**SETUP, "stop": 4128.0}, faits)
    assert r["points"] == 2 and r["niveau"] == "moyen"


def test_piege_limite_le_statut_a_attendre(config):
    calc = faits_desk()
    calc["marche"]["atr_H1"] = 10.0
    calc["liquidite"] = faits_piege()["liquidite"]
    avis, debat = desk(7, 0)
    d = bureau.finaliser_mgc(decision_chef(), avis, debat, calc, [], config)
    assert d["statut"] == "ATTENDRE"
    assert any(i.startswith("Piège probable") for i in d["vetos_informatifs"])


# ------------------------------------------------------------------ vote pondéré et express

def biais(*sens):
    return {f"a{i}": {"biais": s} for i, s in enumerate(sens)}


def test_majorite_comme_avant_avec_six():
    assert bureau.majorite(biais(*["haussier"] * 4, "neutre", "baissier")) == "haussier"
    assert bureau.majorite(biais(*["haussier"] * 3, "neutre", "neutre", "baissier")) is None


def test_majorite_pondere_par_le_bulletin():
    debat = biais(*["haussier"] * 5, "neutre", "neutre", "baissier")
    assert bureau.majorite(debat) is None                       # 5 sur 8 < 2/3
    poids = {"a0": 1.5, "a1": 1.5, "a2": 1.5, "a3": 1.5, "a4": 1.5, "a5": 0.5, "a6": 0.5, "a7": 0.5}
    assert bureau.majorite(debat, poids) == "haussier"          # 7,5 sur 9


def test_express_exige_les_trois():
    assert bureau.majorite(biais("haussier", "haussier", "neutre"), accord_min=bureau.ACCORD_MIN_EXPRESS) is None
    assert bureau.majorite(biais("baissier", "baissier", "baissier"), accord_min=bureau.ACCORD_MIN_EXPRESS) == "baissier"
    assert bureau.texte_accord(3, bureau.ACCORD_MIN_EXPRESS) == "au moins 3 sur 3"
    assert bureau.texte_accord(8) == "au moins 6 sur 8" and bureau.texte_accord(6) == "au moins 4 sur 6"


def test_controler_message_desk_divise():
    decision = {"decision": "long", "votes": {"haussier": 2}}
    d = bureau.controler(decision, faits_desk(), debat=biais("haussier", "haussier", "neutre"),
                         accord_min=bureau.ACCORD_MIN_EXPRESS)
    assert d["decision"] == "pas de trade"
    assert any("au moins 3 sur 3" in b for b in d["blocages"])


def test_les_votants_et_le_piege():
    cles = [s["cle"] for s in bureau.SPECIALISTES]
    assert cles == ["smc", "fibo", "ichimoku", "tendance", "orderflow", "calendrier", "liquidite", "dollar"]
    assert "piege" not in cles and bureau.PIEGE["cle"] == "piege"
    assert set(bureau.EXPRESS_VOTANTS) <= set(cles)
    assert "macro" not in next(s for s in bureau.SPECIALISTES if s["cle"] == "calendrier")["donnees"]
    assert "0,25 %" in bureau.REGLES_JABRAN


# ------------------------------------------------------------------ bulletin de notes

def ecrire_desk(dossier, ident, debut, prix, biais_par_agent, atr=10.0):
    (dossier / ident).mkdir(parents=True)
    contenu = {"id": ident, "type": "bureau", "debut": debut.timestamp(),
               "donnees": {"marche": {"prix": prix, "atr_H1": atr}},
               "specialistes": {c: {"tour1": {"biais": b}, "tour2": {"biais": b}} for c, b in biais_par_agent.items()}}
    (dossier / ident / "comparaison.json").write_text(json.dumps(contenu), encoding="utf-8")


def test_bulletin_note_quatre_heures_apres(tmp_path):
    debut = datetime(2026, 10, 21, 13, 30, tzinfo=timezone.utc)
    ecrire_desk(tmp_path, "d1", debut, 4200.0, {"fibo": "haussier", "smc": "baissier", "dollar": "neutre"})
    prix = [(debut + timedelta(hours=h), 4200.0 + 3 * h) for h in range(1, 8)]   # +12 à +4 h
    b = bulletin.noter(tmp_path, tmp_path / "bulletin.json", charger_prix=lambda d, f: prix,
                       maintenant=debut + timedelta(hours=6))
    agents = b["notes"]["d1"]["agents"]
    assert agents["fibo"]["juste"] is True and agents["smc"]["juste"] is False and agents["dollar"]["juste"] is False
    assert b["poids"] == {"fibo": 1.0, "smc": 1.0, "dollar": 1.0}       # moins de 10 notes : poids 1
    assert "Fibonacci : 1/1" in bulletin.resume(b)


def test_bulletin_ajuste_les_poids_apres_dix_notes(tmp_path):
    for i in range(12):
        debut = datetime(2026, 10, 1, 13, 0, tzinfo=timezone.utc) + timedelta(days=i)
        ecrire_desk(tmp_path, f"d{i:02d}", debut, 4200.0, {"fibo": "haussier", "smc": "baissier"})
    def prix(d, f):
        return [(datetime(2026, 10, 1, 17, 0, tzinfo=timezone.utc) + timedelta(days=i), 4210.0) for i in range(12)]
    b = bulletin.noter(tmp_path, tmp_path / "bulletin.json", charger_prix=prix,
                       maintenant=datetime(2026, 10, 20, tzinfo=timezone.utc))
    assert b["poids"]["fibo"] == 1.5 and b["poids"]["smc"] == 0.5
    assert bulletin.poids(tmp_path / "bulletin.json")["fibo"] == 1.5


def test_bulletin_marche_ferme_pas_de_note(tmp_path):
    debut = datetime(2026, 10, 23, 20, 0, tzinfo=timezone.utc)     # vendredi soir
    ecrire_desk(tmp_path, "w", debut, 4200.0, {"fibo": "haussier"})
    b = bulletin.noter(tmp_path, tmp_path / "bulletin.json", charger_prix=lambda d, f: [],
                       maintenant=debut + timedelta(days=5))
    assert b["notes"]["w"]["non_note"]
    assert b["eleves"] == {}


def test_bulletin_vide_et_commande(tmp_path, monkeypatch):
    monkeypatch.setattr(bulletin, "FICHIER", tmp_path / "rien.json")
    assert "pas encore de note" in bulletin.resume(bulletin.lire(tmp_path / "rien.json"))
    assert "Bulletin" in commandes.executer("/bulletin")
    assert "/express" in commandes.AIDE and "/liquidite" in commandes.AIDE


def test_texte_liquidite():
    liq = calculs.liquidite_sessions({"M5": bougies_m5({"2026-10-22 03:00": (4210.0, 4199.0, 4205.0)}),
                                      "D1": jours()}, 10.0)
    texte = commandes.texte_liquidite(liq)
    assert "plus haut Asie 4210.0" in texte and "Plus proche liquidité intacte" in texte


# ------------------------------------------------------------------ règles Topstep

from datetime import date  # noqa: E402

from mgc import topstep  # noqa: E402


def compte(*soldes, depart=50_000.0):
    jours = [date(2026, 10, 19 + i).isoformat() for i in range(len(soldes))]
    return {"solde_depart": depart, "soldes": dict(zip(jours, soldes, strict=True))}


def test_topstep_plancher_suit_la_fin_de_journee():
    e = topstep.etat(contenu=compte(50_600, 51_200, 51_000), aujourd_hui=date(2026, 10, 21))
    assert e["plancher_perte_max"] == 49_200          # plus haut de fin de journée 51 200 - 2 000
    assert e["marge_avant_perte_max"] == 1_800
    assert e["gain_du_jour"] == -200 and e["profit"] == 1_000
    assert e["meilleur_jour"] == {"jour": "2026-10-19", "gain": 600}


def test_topstep_plancher_bloque_au_depart_et_consistance():
    e = topstep.etat(contenu=compte(52_500, 53_100), aujourd_hui=date(2026, 10, 25))
    assert e["plancher_perte_max"] == 50_000 and e["plancher_bloque"]
    # meilleur jour 2 500 $ > 55 % de 3 000 : l'objectif monte à 2 500 / 0,55
    assert e["objectif"] == round(2500 / 0.55, 2)


def test_topstep_veto_pres_de_la_perte_max():
    e = topstep.etat(contenu=compte(48_300), aujourd_hui=date(2026, 10, 20))
    assert e["marge_avant_perte_max"] == 300
    assert topstep.vetos(e, 125.0)[0].startswith("Topstep : il ne te reste que 300 $")
    assert topstep.vetos(topstep.etat(contenu=compte(50_000), aujourd_hui=date(2026, 10, 20)), 125.0) == []
    assert topstep.vetos(None, 125.0) == []


def test_topstep_consistance_du_jour():
    e = topstep.etat(contenu=compte(50_100, 51_500), aujourd_hui=date(2026, 10, 20))
    assert e["gain_du_jour"] == 1_400
    assert "consistance" in topstep.limites(e)[0]


def test_commande_solde(tmp_path, monkeypatch):
    monkeypatch.setattr(topstep, "FICHIER", tmp_path / "compte.json")
    monkeypatch.setattr(topstep.noter_solde, "__defaults__", (None, tmp_path / "compte.json", 50_000.0))
    monkeypatch.setattr(topstep.etat, "__defaults__", (None, None, None, tmp_path / "compte.json"))
    assert "je n'ai pas encore ton solde" in commandes.executer("/topstep")
    texte = commandes.executer("/solde", "50 340")
    assert texte.startswith("Solde noté.") and "50340" in texte
    assert topstep.lire(tmp_path / "compte.json")["soldes"][date.today().isoformat()] == 50_340
    commandes.executer("/solde", "50.400")
    assert topstep.lire(tmp_path / "compte.json")["soldes"][date.today().isoformat()] == 50_400
    assert "illisible" in commandes.executer("/solde", "beaucoup")


def test_topstep_veto_dans_le_desk(config):
    avis, debat = desk(7, 0)
    e = topstep.etat(contenu=compte(48_300), aujourd_hui=date(2026, 10, 20))
    d = bureau.finaliser_mgc(decision_chef(), avis, debat, faits_desk(), [], config, compte=e)
    assert d["statut"] == "AUCUNE OPPORTUNITÉ"
    assert any(v.startswith("Topstep") for v in d["vetos"])


# ------------------------------------------------------------------ veille : liquidité prise annoncée

from veille import liquidite as vliq  # noqa: E402


def test_veille_annonce_une_liquidite_prise(tmp_path):
    m5 = bougies_m5({"2026-10-22 03:00": (4210.0, 4199.0, 4205.0),      # plus haut d'Asie 4210
                     "2026-10-22 16:00": (4214.0, 4205.0, 4206.0),      # balayé à 16h, retour dessous
                     "2026-10-22 16:55": (4207.0, 4199.0, 4200.0)})
    evenements = []
    agent = vliq.Liquidite(tmp_path, emettre=evenements.append,
                           charger=lambda intervalle, periode: m5 if intervalle == "5m" else jours())
    a_17h = datetime(2026, 10, 22, 15, 0, tzinfo=timezone.utc).timestamp()   # 17h à Paris
    agent.check(a_17h)
    prises = [e for e in evenements if e["niveau"]["nom"] == "plus haut Asie"]
    assert len(prises) == 1 and prises[0]["source"] == "liquidite"
    assert "balayé à 16h00" in prises[0]["texte"]
    agent.check(a_17h + 120)                      # pas deux fois la même annonce
    assert len([e for e in evenements if e["niveau"]["nom"] == "plus haut Asie"]) == 1
    assert vliq.Liquidite(tmp_path).envoyes == agent.envoyes   # gardé après un redémarrage


def test_veille_liquidite_silencieuse_la_nuit(tmp_path):
    m5 = bougies_m5({"2026-10-22 03:00": (4210.0, 4199.0, 4205.0), "2026-10-22 16:00": (4214.0, 4205.0, 4206.0)})
    evenements = []
    agent = vliq.Liquidite(tmp_path, emettre=evenements.append, charger=lambda i, p: m5 if i == "5m" else jours())
    agent.check(datetime(2026, 10, 22, 21, 0, tzinfo=timezone.utc).timestamp())   # 23h à Paris
    assert evenements == []
    assert agent.resume()["actif"] is True


def test_veille_liquidite_sans_donnees(tmp_path):
    agent = vliq.Liquidite(tmp_path, charger=lambda i, p: None)
    agent.check()
    assert agent.dernier["disponible"] is False


# ------------------------------------------------------------------ un desk complet avec une fausse IA

class FausseIA:
    def __init__(self):
        self.consignes = []

    def invoke(self, consigne):
        self.consignes.append(consigne)
        if "chef d'un desk" in consigne:
            texte = "DECISION: long\nZONE: 4129.5\nSL: 4126.0\nTP1: 4200\nRAISON: accord du desk."
        elif "agent Piège" in consigne:
            texte = "RISQUE: fort\nSCÉNARIO: le prix va chercher le plus bas de Londres.\nÀ ATTENDRE: un balayage du 4115."
        elif "Ton avis au premier tour" in consigne:
            texte = "BIAIS: haussier\nCONFIANCE: 4\nREPONSE: d'accord avec Fibo."
        else:
            texte = "BIAIS: haussier\nCONFIANCE: 4\nNIVEAUX: 4129.5\nINVALIDATION: 4100\nARGUMENT: zone avec FVG."

        class Reponse:
            content = texte
            usage_metadata = {}
        return Reponse()


@pytest.fixture
def fausse_ia(monkeypatch):
    import sys
    import types

    import moteur

    ia = FausseIA()
    fabrique = types.ModuleType("tradingagents.llm_clients.factory")
    fabrique.create_tier_client = lambda config, tier: types.SimpleNamespace(get_llm=lambda: ia)
    monkeypatch.setitem(sys.modules, "tradingagents.llm_clients.factory", fabrique)
    monkeypatch.setattr(moteur, "verifier_acces", lambda m: None)
    monkeypatch.setattr(moteur, "construire_config", lambda m, modele=None: {"quick_think_llm": "faux"})
    monkeypatch.setattr(bureau, "poids_agents", lambda: {})
    evenements = []
    monkeypatch.setattr(bureau, "emettre", lambda **e: evenements.append(e))
    return ia, evenements


def args_desk(express=False):
    import types

    return types.SimpleNamespace(moteur="lmstudio", modele=None, express=express)


def calculs_desk():
    c = faits_desk()
    c["marche"].update(heure_paris="22/10 16h00", atr_H1=10.0)
    c["calendrier"] = {"fomc_aujourdhui": False}
    c["liquidite"] = faits_piege("balayée")["liquidite"]
    return c


def test_desk_express_avec_fausse_ia(fausse_ia):
    ia, evenements = fausse_ia
    avis, debat, decision = bureau.debattre(args_desk(True), calculs_desk(), {"appels": 0}, economiser=True, express=True)
    assert set(avis) == {"fibo", "smc", "liquidite"}
    assert len(ia.consignes) == 5                      # 3 avis + Piège + chef, pas de débat
    assert decision["decision"] == "long" and decision["accord_min"] == 1.0
    piege_ev = next(e for e in evenements if e.get("cle") == "piege" and e.get("tour") == 1)
    assert piege_ev["risque"] == "fort" and "4115" in piege_ev["invalidation"]
    assert "Piège" in ia.consignes[-1] and "au moins 3 sur 3" in ia.consignes[-1]


def test_desk_complet_avec_fausse_ia(fausse_ia, config):
    ia, evenements = fausse_ia
    avis, debat, decision = bureau.debattre(args_desk(), calculs_desk(), {"appels": 0}, economiser=True)
    assert len(avis) == 8
    assert len(ia.consignes) == 10                     # 8 avis + Piège + chef (tous d'accord : pas de débat)
    d = bureau.finaliser_mgc(decision, avis, debat, calculs_desk(), [], config)
    assert d["statut"] == "ACHAT ENVISAGEABLE" and d["biais"]["accord"] == "8/8"
    assert d["avis_piege"]["risque"] == "fort"         # l'avis de l'IA est affiché, le statut suit le calcul


# ------------------------------------------------------------------ agent Mémoire (journal des setups)

from mgc import memoire_setups  # noqa: E402
from veille.journal_setups import COLUMNS  # noqa: E402


def ecrire_journal(dossier, lignes):
    entete = ";".join(COLUMNS)
    corps = []
    for i, (sens, niveau, session, resultat) in enumerate(lignes, 1):
        cases = ["?"] * len(COLUMNS)
        cases[0], cases[COLUMNS.index("Sens")], cases[COLUMNS.index("Niveau entree")] = str(i), sens, niveau
        cases[COLUMNS.index("Session")], cases[COLUMNS.index("Resultat")] = session, resultat
        corps.append(";".join(cases))
    (dossier / "journal_setups.csv").write_text("﻿" + entete + "\n" + "\n".join(corps) + "\n", encoding="utf-8")


def test_memoire_setups_semblables(tmp_path):
    lignes = [("Short", "0.705", "New York", "TP1")] * 2 + [("Short", "0.705", "New York", "Stop")] * 4 \
        + [("Long", "0.705", "Londres", "TP2")] * 3
    ecrire_journal(tmp_path, lignes)
    a_17h = datetime(2026, 10, 22, 15, 0, tzinfo=timezone.utc)
    r = memoire_setups.comparer({"sens": "vente", "niveau": "0.705"}, a_17h, dossier=tmp_path)
    assert r["critere"] == "ventes sur le 0.705 en session New York"
    assert (r["total"], r["gagnants"], r["perdants"], r["taux_pct"]) == (6, 2, 4, 33)
    r = memoire_setups.comparer({"sens": "achat", "niveau": "0.705"}, a_17h, dossier=tmp_path)
    assert r["critere"] == "setups sur le 0.705" and r["total"] == 9      # trop peu d'achats : critère élargi


def test_memoire_pas_assez_ou_vide(tmp_path):
    ecrire_journal(tmp_path, [("Long", "0.618", "Asie", "TP1")] * 2)
    r = memoire_setups.comparer({"sens": "achat", "niveau": "0.618"}, dossier=tmp_path)
    assert r["total"] == 0 and "pas assez" in r["texte"]
    assert "vide ou introuvable" in memoire_setups.comparer({"sens": "achat", "niveau": "0.618"},
                                                            dossier=tmp_path / "rien")["texte"]
    assert memoire_setups.comparer(None) is None
