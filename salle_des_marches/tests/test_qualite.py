# -*- coding: utf-8 -*-
import datetime as dt

import pandas as pd
from fabrique import bougies

from mgc import calendrier_cme as cal
from mgc import qualite

# mardi 20/10/2026 16h à Paris = 9h à Chicago, séance ouverte
INSTANT = dt.datetime(2026, 10, 20, 16, 0, tzinfo=cal.PARIS)


def test_donnees_saines(config):
    c = qualite.controler(bougies(INSTANT, 300, 5), 5, INSTANT, config, temps_reel=True)
    assert c["statut"] == "temps_reel"
    assert c["motifs"] == []
    assert c["nb"] == 300
    assert c["age_min"] == 0


def test_source_differee(config):
    assert qualite.controler(bougies(INSTANT, 300, 5), 5, INSTANT, config, temps_reel=False)["statut"] == "differee"


def test_bougie_en_cours_retiree(config):
    df = bougies(INSTANT, 300, 5)
    c = qualite.controler(df, 5, INSTANT - dt.timedelta(minutes=2), config, temps_reel=True)
    assert c["nb"] == 299


def test_donnees_perimees(config):
    c = qualite.controler(bougies(INSTANT, 300, 5), 5, INSTANT + dt.timedelta(minutes=20), config, temps_reel=True)
    assert c["statut"] == "perimee"
    assert any("périmées" in m for m in c["motifs"])


def test_marche_ferme_n_est_pas_perime(config):
    samedi = dt.datetime(2026, 10, 17, 12, 0, tzinfo=cal.PARIS)
    vendredi_fin = dt.datetime(2026, 10, 16, 16, 0, tzinfo=cal.CHICAGO)
    c = qualite.controler(bougies(vendredi_fin, 300, 5), 5, samedi, config, temps_reel=True)
    assert c["statut"] == "temps_reel"


def test_week_end_et_pause_ne_sont_pas_des_trous(config):
    dimanche = dt.datetime(2026, 10, 18, 18, 0, tzinfo=cal.CHICAGO)  # 1 h après la réouverture
    c = qualite.controler(bougies(dimanche, 400, 5), 5, dimanche, config, temps_reel=True)
    assert c["motifs"] == []
    mardi_soir = dt.datetime(2026, 10, 20, 18, 0, tzinfo=cal.CHICAGO)  # pause 16h-17h dedans
    c = qualite.controler(bougies(mardi_soir, 400, 5), 5, mardi_soir, config, temps_reel=True)
    assert c["motifs"] == []


def test_petit_trou_signale_gros_trou_bloque(config):
    df = bougies(INSTANT, 300, 5)
    petit = df.drop(df.index[100:102])        # 10 min
    c = qualite.controler(petit, 5, INSTANT, config, temps_reel=True)
    assert c["statut"] == "temps_reel"
    assert any("manquante" in m for m in c["motifs"])
    gros = df.drop(df.index[100:106])         # 30 min > 15
    assert qualite.controler(gros, 5, INSTANT, config, temps_reel=True)["statut"] == "invalide"


def test_doublons_retires(config):
    df = bougies(INSTANT, 300, 5)
    df = pd.concat([df, df.iloc[[10, 20]]])
    c = qualite.controler(df, 5, INSTANT, config, temps_reel=True)
    assert c["doublons"] == 2
    assert c["nb"] == 300
    assert c["statut"] == "temps_reel"


def test_sans_fuseau_et_vide(config):
    df = bougies(INSTANT, 50, 5)
    df.index = df.index.tz_localize(None)
    assert qualite.controler(df, 5, INSTANT, config, temps_reel=True)["statut"] == "invalide"
    assert qualite.controler(pd.DataFrame(), 5, INSTANT, config, temps_reel=True)["statut"] == "invalide"
    assert qualite.controler(None, 5, INSTANT, config, temps_reel=True)["statut"] == "invalide"


def test_prix_impossibles_et_hors_grille(config):
    df = bougies(INSTANT, 50, 5)
    df.iloc[10, df.columns.get_loc("h")] = 4190.0  # haut sous le corps
    assert qualite.controler(df, 5, INSTANT, config, temps_reel=True)["statut"] == "invalide"
    df = bougies(INSTANT, 50, 5)
    df.iloc[10, df.columns.get_loc("c")] = 4200.05
    assert qualite.controler(df, 5, INSTANT, config, temps_reel=True)["statut"] == "invalide"


def test_contrat_different(config):
    c = qualite.controler(bougies(INSTANT, 50, 5), 5, INSTANT, config, temps_reel=True,
                          contrat="MGCG27", contrat_attendu="MGCZ26")
    assert c["statut"] == "invalide"


def test_ensemble_garde_le_pire(config):
    bon = {"statut": "temps_reel", "motifs": []}
    mauvais = {"statut": "perimee", "motifs": ["vieux"]}
    e = qualite.ensemble({"M5": bon, "H1": mauvais})
    assert e["statut"] == "perimee"
    assert e["motifs"] == ["H1 : vieux"]


def test_ecart_entre_sources(config):
    assert qualite.ecart_sources(4200.0, 4202.5, config)
    assert qualite.ecart_sources(4200.0, 4201.9, config) == ""
    assert qualite.ecart_sources(None, 4201.0, config) == ""


def test_h4_et_h12_calees_sur_l_ouverture_cme():
    fin = dt.datetime(2026, 10, 20, 16, 0, tzinfo=cal.CHICAGO)  # séance du mardi : lundi 17h -> mardi 16h
    h1 = bougies(fin, 23, 60)
    h4 = qualite.regrouper_cme(h1, 4)
    heures = [t.tz_convert(cal.CHICAGO).hour for t in h4.index]
    assert heures == [17, 21, 1, 5, 9, 13]
    assert len(h1[h1.index >= h4.index[-1]]) == 3   # dernière H4 : 13h-16h (la pause n'est pas comptée)
    h12 = qualite.regrouper_cme(h1, 12)
    assert [t.tz_convert(cal.CHICAGO).hour for t in h12.index] == [17, 5]
    assert h12["v"].sum() == h1["v"].sum()
    assert qualite.regrouper_cme(h1.iloc[:0], 4).empty
