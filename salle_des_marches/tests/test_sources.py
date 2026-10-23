# -*- coding: utf-8 -*-
import datetime as dt
import json

import pytest
from fabrique import bougies, ecrire_csv, format_yahoo, journalier

from mgc import calendrier_cme as cal
from mgc import source_ninja as ninja
from mgc import sources

INSTANT = dt.datetime(2026, 10, 20, 16, 0, tzinfo=cal.PARIS)  # mardi, séance ouverte
PERIODES = {"M1": 1, "M3": 3, "M5": 5, "M15": 15, "H1": 60}


def faux_yahoo(decalage=0.0, demandes=None):
    def chargeur(ticker, periode, intervalle):
        if demandes is not None:
            demandes.append(ticker)
        if intervalle == "1d":
            return format_yahoo(journalier(INSTANT, 300), quotidien=True)
        minutes = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}[intervalle]
        return format_yahoo(bougies(INSTANT, 400, minutes, prix=4200.0 + decalage))
    return chargeur


def ecrire_ninja(dossier, contrat="MGC 12-26", age_s=5, etat="temps_reel", erreur="", jours=30):
    for nom, p in PERIODES.items():
        ecrire_csv(dossier / f"MGC_{nom}.csv", bougies(INSTANT, 400, p))
    ecrire_csv(dossier / "MGC_D1.csv", journalier(INSTANT, jours), quotidien=True)
    heure = (INSTANT - dt.timedelta(seconds=age_s)).astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    (dossier / "battement.json").write_text(json.dumps(
        {"contrat": contrat, "dernier_prix": 4200.5, "heure_utc": heure, "etat": etat, "erreur": erreur}), encoding="utf-8")


@pytest.fixture
def cfg_ninja(config, tmp_path):
    config["dossier_ninja"] = str(tmp_path)
    return config


# ------------------------------------------------------------------ lecteur NinjaTrader

def test_noms_de_contrat_ninjatrader():
    assert ninja.code_depuis_ninja("MGC 12-26") == "MGCZ26"
    assert ninja.code_depuis_ninja("MGC 02-27") == "MGCG27"
    assert ninja.code_depuis_ninja("MGC") is None
    assert ninja.code_depuis_ninja("MGC 13-26") is None


def test_ligne_coupee_et_ligne_abimee_ignorees(tmp_path):
    f = tmp_path / "MGC_M5.csv"
    f.write_text("debut_utc,o,h,l,c,v\n2026-10-20T13:00:00Z,4200.0,4201.0,4199.0,4200.5,10\n"
                 "pas,une,bougie,valable,du,tout\n2026-10-20T13:05:00Z,4200.5,4201", encoding="utf-8")
    df = ninja.lire_bougies(f)
    assert len(df) == 1
    assert str(df.index.tz) == "UTC"
    assert ninja.lire_bougies(tmp_path / "absent.csv").empty


def test_battement(tmp_path, config):
    assert ninja.en_direct(ninja.lire_battement(tmp_path), INSTANT, config)[0] is False
    ecrire_ninja(tmp_path, age_s=5)
    b = ninja.lire_battement(tmp_path)
    assert b["code"] == "MGCZ26"
    assert ninja.en_direct(b, INSTANT, config) == (True, "")
    ecrire_ninja(tmp_path, age_s=600)
    assert ninja.en_direct(ninja.lire_battement(tmp_path), INSTANT, config)[0] is False
    ecrire_ninja(tmp_path, etat="chargement")
    assert ninja.en_direct(ninja.lire_battement(tmp_path), INSTANT, config)[0] is False
    ecrire_ninja(tmp_path, erreur="Le graphique doit être en 1 minute.")
    ok, motif = ninja.en_direct(ninja.lire_battement(tmp_path), INSTANT, config)
    assert ok is False and "1 minute" in motif


def test_prix_yahoo_arrondis_au_centime():
    brut = format_yahoo(bougies(INSTANT, 3, 5))
    brut["Close"] = 4181.10009765625  # précision réduite de Yahoo, vue le 17/10/2026
    assert (sources.depuis_yahoo(brut)["c"] == 4181.1).all()
    assert sources.depuis_yahoo(None).empty


# ------------------------------------------------------------------ choix de la source

def test_sans_ninjatrader_yahoo_differe_sur_le_vrai_contrat(cfg_ninja):
    demandes = []
    r = sources.charger_mgc(INSTANT, cfg_ninja, chargeur_yahoo=faux_yahoo(demandes=demandes))
    assert r["source"] == "yahoo"
    assert r["contrat"] == "MGCZ26"
    assert set(demandes) == {"MGCZ26.CMX"}
    assert r["statut"] == "differee"
    assert r["temps_reel"] is False
    assert {"D1", "H12", "H4", "H1", "M15", "M5", "M3", "M1"} <= set(r["bougies"])
    assert not r["bougies"]["M3"].empty


def test_ninjatrader_en_direct(cfg_ninja, tmp_path):
    ecrire_ninja(tmp_path)
    r = sources.charger_mgc(INSTANT, cfg_ninja, chargeur_yahoo=faux_yahoo())
    assert r["source"] == "ninjatrader"
    assert r["statut"] == "temps_reel", r["motifs"]
    assert r["temps_reel"] is True
    assert r["dernier_prix"] == 4200.5
    assert any("complété par Yahoo" in m for m in r["motifs"])  # D1 trop court (30 jours)


def test_ninjatrader_sur_le_mauvais_contrat(cfg_ninja, tmp_path):
    ecrire_ninja(tmp_path, contrat="MGC 02-27")
    r = sources.charger_mgc(INSTANT, cfg_ninja, chargeur_yahoo=faux_yahoo())
    assert r["source"] == "yahoo"
    assert any("MGCG27" in m for m in r["motifs"])


def test_ninjatrader_coupe_repli_yahoo(cfg_ninja, tmp_path):
    ecrire_ninja(tmp_path, age_s=900)
    r = sources.charger_mgc(INSTANT, cfg_ninja, chargeur_yahoo=faux_yahoo())
    assert r["source"] == "yahoo"
    assert r["statut"] == "differee"
    assert any("NinjaTrader" in m for m in r["motifs"])


def test_desaccord_entre_sources_bloque(cfg_ninja, tmp_path):
    ecrire_ninja(tmp_path, jours=300)
    r = sources.charger_mgc(INSTANT, cfg_ninja, chargeur_yahoo=faux_yahoo(decalage=3.0))
    assert r["source"] == "ninjatrader"
    assert r["statut"] == "invalide"
    assert any("Écart de 3.0 points" in m for m in r["motifs"])
