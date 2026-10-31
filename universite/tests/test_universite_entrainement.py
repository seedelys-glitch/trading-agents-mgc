"""Entraînement des agents (31/10) : cours, examens « cas d'école », travaux pratiques en replay, quiz de l'IA."""

import random

import pytest
from aides_universite import executer_tout

from universite import agents, competences, config, donnees, entrainement
from universite.competences import entrainement_quotidien
from universite.serveur import Universite

LECONS = """CREATE TABLE IF NOT EXISTS lecons (id INTEGER PRIMARY KEY AUTOINCREMENT, equipe TEXT NOT NULL DEFAULT 'universite',
    agent INTEGER, type TEXT NOT NULL DEFAULT '', empreinte TEXT NOT NULL, quoi TEXT NOT NULL, cause TEXT NOT NULL,
    lecon TEXT NOT NULL, exemple TEXT NOT NULL DEFAULT '', statut TEXT NOT NULL DEFAULT 'a_appliquer',
    fois INTEGER NOT NULL DEFAULT 1, relue INTEGER NOT NULL DEFAULT 0, cree REAL NOT NULL, maj REAL NOT NULL,
    UNIQUE(equipe, empreinte))"""


def _avec_lecons(base):
    base.ecrire(LECONS)


def test_chaque_agent_a_un_cours_et_chaque_examen_existe():
    for a in agents.AGENTS:
        sujets = entrainement.programme(a["n"])
        assert sujets, f"agent {a['n']} sans cours"
        assert all(s["titre"] and s["resume"] for s in sujets)
    noms = [s["examen"] for p in entrainement.PROGRAMME.values() for s in p if s.get("examen")]
    assert set(noms) == set(entrainement.EXAMENS)
    for p in entrainement.PROGRAMME.values():
        for s in p:
            if s.get("quiz"):
                bonne, _, choix = s["quiz"]
                assert bonne in choix and len(choix) == 4


@pytest.mark.parametrize("graine", [20261031, 20261101, 7])
def test_les_vrais_calculs_reussissent_tous_les_cas_d_ecole(graine):
    for n in entrainement.PROGRAMME:
        for r in entrainement.passer_examens(n, graine):
            rates = [q for q in r["questions"] if not q["reussi"]]
            assert not rates, (n, r["examen"], rates)


def test_un_calcul_faux_est_detecte(monkeypatch):
    """L'examen n'est pas décoratif : un Fibonacci décalé ou une structure inversée sont recalés."""
    config.salle_importable()
    import calculs

    vrai_fibo = calculs.fibo

    def fibo_decale(d, a):
        r = vrai_fibo(d, a)
        r["niveaux"] = {k: v + 1.0 for k, v in r["niveaux"].items()}
        return r

    monkeypatch.setattr(calculs, "fibo", fibo_decale)
    notes = {r["examen"]: r["note"] for r in entrainement.passer_examens(2, 1)}
    assert notes["fibo_niveaux"] < entrainement.NOTE_REUSSITE

    vraie_structure = calculs.structure
    monkeypatch.setattr(calculs, "structure", lambda df, cote=3: {**vraie_structure(df, cote), "tendance": "baissier"})
    notes = {r["examen"]: r["note"] for r in entrainement.passer_examens(1, 1)}
    assert notes["smc_bos"] < 20


def test_un_calcul_qui_plante_est_une_question_ratee(monkeypatch):
    monkeypatch.setitem(entrainement.EXAMENS, "macro_heures", lambda alea: 1 / 0)
    r = [x for x in entrainement.passer_examens(5, 1) if x["examen"] == "macro_heures"][0]
    assert r["note"] == 0 and "ZeroDivisionError" in r["questions"][0]["obtenu"]


def test_mission_examen_note_le_bulletin(moteur, base):
    m = base.nouvelle_mission(2, "examen_ecole", "Examen", {"agent": 2})
    executer_tout(moteur)
    assert base.mission(m)["statut"] == "terminee"
    b = entrainement.bulletin(base, 2)
    assert b["moyenne"] == 20 and not b["rates"] and {n["sujet"] for n in b["notes"]} == {"impulsion", "zones"}
    doc = base.un("SELECT * FROM documents WHERE genre='examen'")
    assert doc["statut"] == "verifie" and "20/20" in doc["titre"]


def test_examen_rate_ecrit_une_lecon_et_previent_le_directeur(moteur, base, monkeypatch):
    _avec_lecons(base)
    monkeypatch.setitem(entrainement.EXAMENS, "fibo_zones",
                        lambda alea: [entrainement._q("Le 0.5 ne fait jamais partie des zones", True, False)])
    for _ in range(2):
        base.nouvelle_mission(2, "examen_ecole", "Examen", {"agent": 2})
        executer_tout(moteur)
    lecon = base.un("SELECT * FROM lecons")
    assert lecon["agent"] == 2 and lecon["type"] == "analyse_fibo" and lecon["fois"] == 2
    assert "0.618" in lecon["lecon"]
    alerte = base.un("SELECT * FROM messages WHERE a=? AND genre='alerte'", (agents.DIRECTEUR,))
    assert alerte and "défaut de calcul" in alerte["contenu"]
    b = entrainement.bulletin(base, 2)
    assert b["rates"] and b["lecons"]


def _jeu_h1(base, n=700, graine=3, tendance=0.0):
    alea = random.Random(graine)
    j = donnees.creer_jeu(base, "h1", "artificiel (tests)", "MGC")
    lignes, c = [], 3000.0
    for i in range(n):
        o = c
        c = round(o + tendance + alea.gauss(0, 3), 1)
        lignes.append((entrainement.DEPART + 3600 * i, o, max(o, c) + 1, min(o, c) - 1, c, 10.0))
    donnees.ajouter_bougies(base, j, "H1", lignes)
    return j


def test_travaux_pratiques_sans_look_ahead(base, monkeypatch):
    j = _jeu_h1(base)
    vus = []
    vraie = entrainement.lecture

    def espion(agent, cadres):
        vus.append(cadres["H1"].index[-1].timestamp())
        return vraie(agent, cadres)

    monkeypatch.setattr(entrainement, "lecture", espion)
    tp = entrainement.travaux_pratiques(base, j, 1, n_max=40, graine=1)
    assert len(tp["cas"]) == len(vus) > 20
    for cas, derniere in zip(tp["cas"], vus, strict=True):
        assert derniere + 3600 <= cas["instant"]          # la dernière bougie lue est fermée à l'instant
    instants = sorted(c["instant"] for c in tp["cas"])
    assert all(b - a >= entrainement.HORIZON_H * 3600 for a, b in zip(instants, instants[1:], strict=False))


def test_bilan_compare_au_hasard():
    def cas(avis, resultat, n, session="Londres"):
        return [{"avis": avis, "resultat": resultat, "session": session} for _ in range(n)]

    from universite.competences import _commun  # noqa: F401  (rend la Salle importable)
    config.salle_importable()
    from mgc import stats

    bon = entrainement.bilan_tp(cas(1, 1, 30) + cas(-1, -1, 30) + cas(1, -1, 5), stats.wilson)
    assert bon["verdict"].startswith("la lecture a aidé") and entrainement.note_tp(bon) > 14
    mauvais = entrainement.bilan_tp(cas(1, -1, 40) + cas(-1, 1, 30), stats.wilson)
    assert mauvais["verdict"].startswith("la lecture s'est trompée") and entrainement.note_tp(mauvais) < 6
    peu = entrainement.bilan_tp(cas(1, 1, 10), stats.wilson)
    assert peu["verdict"].startswith("échantillon insuffisant") and entrainement.note_tp(peu) is None
    # toujours « hausse » dans un marché qui monte : bon taux, mais pas mieux que le hasard intelligent
    suiveur = entrainement.bilan_tp(cas(1, 1, 40) + cas(1, -1, 20), stats.wilson)
    assert not suiveur["verdict"].startswith("la lecture a aidé")


def test_mission_travaux_pratiques(moteur, base):
    j = _jeu_h1(base)
    m = base.nouvelle_mission(3, "travaux_pratiques", "TP", {"agent": 3, "jeu": j, "cas": 40})
    executer_tout(moteur)
    assert base.mission(m)["statut"] == "terminee", base.mission(m)["erreur"]
    ligne = base.un("SELECT * FROM examens WHERE genre='replay' AND agent=3")
    assert ligne and ligne["detail"]["bilan"]["n"] >= 0
    doc = base.un("SELECT * FROM documents WHERE genre='travaux_pratiques'")
    assert "Wilson" in doc["contenu"] or "insuffisant" in doc["contenu"]


class FausseIA:
    def __init__(self, bonnes=True, dispo=True):
        self.bonnes, self.dispo, self.posees = bonnes, dispo, []

    def disponible(self):
        return self.dispo

    def completer(self, consigne, texte, mission=None, agent=None, role=""):
        self.posees.append(texte)
        for p in entrainement.PROGRAMME.values():
            for s in p:
                if s.get("quiz") and texte.startswith(s["quiz"][1]) and texte.endswith("/no_think"):
                    return f"Réponse : {s['quiz'][0]}" if self.bonnes else "Z ... A"
        return "?"


def test_quiz_ia(moteur, base):
    _avec_lecons(base)
    moteur.ia = FausseIA(bonnes=True)
    base.nouvelle_mission(9, "quiz_ia", "Quiz", {"agent": 3})
    executer_tout(moteur)
    assert entrainement.bulletin(base, 3)["moyenne"] == 20
    moteur.ia = FausseIA(bonnes=False)
    base.nouvelle_mission(9, "quiz_ia", "Quiz", {"agent": 1})
    executer_tout(moteur)
    b = entrainement.bulletin(base, 1)
    assert b["moyenne"] < 20 and base.un("SELECT COUNT(*) AS n FROM lecons WHERE agent=1")["n"] >= 1


def test_quiz_sans_ia_ne_note_rien(moteur, base):
    moteur.ia = FausseIA(dispo=False)
    m = base.nouvelle_mission(9, "quiz_ia", "Quiz", {"agent": 1})
    executer_tout(moteur)
    assert base.mission(m)["resultat"]["passe"] is False
    assert not base.un("SELECT * FROM examens")


def test_entrainement_quotidien_confie_les_epreuves(moteur, base):
    j = _jeu_h1(base)
    assert entrainement_quotidien.assurer_boucle(moteur) and entrainement_quotidien.assurer_boucle(moteur) is None
    m = base.nouvelle_mission(9, "entrainement_quotidien", "Entraînement", {})
    executer_tout(moteur, limite=1)
    r = base.mission(m)["resultat"]
    examens = base.lire("SELECT agent FROM missions WHERE type='examen_ecole'")
    assert {e["agent"] for e in examens} == {n for n, p in entrainement.PROGRAMME.items() if any(s.get("examen") for s in p)}
    tp = base.lire("SELECT agent, params FROM missions WHERE type='travaux_pratiques'")
    assert {t["agent"] for t in tp} == set(entrainement.LECTURES) and all(t["params"]["jeu"] == j for t in tp)
    assert r["replay"] is True and r["quiz"] == 0       # IA coupée pendant les tests


def test_competences_declarees():
    for t in ("examen_ecole", "travaux_pratiques", "quiz_ia", "entrainement_quotidien"):
        assert t in competences.TYPES


def test_fiche_agent_montre_le_bulletin(tmp_path):
    u = Universite(tmp_path, demarrer_moteur=False)
    try:
        f = u.fiche_agent(6)
        assert f["entrainement"]["programme"] and f["entrainement"]["moyenne"] is None
        assert u.base.un("SELECT * FROM boucles WHERE genre='entrainement_quotidien'")
    finally:
        u.base.fermer()


def test_directeur_comprend_trace_moi_le_fibo():
    import re

    from universite import directeur_chat as dc

    t = dc.plat("trace moi le fibo")
    assert re.search(dc.VERBE, t)


# ------------------------------------------------------------------ leçons du 1er entraînement sur le PC (31/10)
def test_lire_la_lettre_sans_se_tromper_de_mot():
    assert entrainement.lire_lettre("La réponse est D") == "D"          # avant : le A de « La » était lu
    assert entrainement.lire_lettre("D) Dire qu'il attend") == "D"
    assert entrainement.lire_lettre("<think>A ou B ?</think>\nC") == "C"
    assert entrainement.lire_lettre("Aucune idée") == "?"


def test_le_quiz_s_arrete_avant_le_delai(moteur, base):
    ia = FausseIA(bonnes=True)
    restant = iter([500, 500, 150, 150])
    r = entrainement.poser_quiz(ia, 1, temps_restant=lambda: next(restant))
    assert len(r) == 2 and all(x["reussi"] for x in r)


def test_le_replay_ne_compte_pas_dans_la_moyenne(base):
    entrainement.enregistrer(base, 6, "cas_ecole", "vwap", 20.0, {}, 1)
    entrainement.enregistrer(base, 6, "replay", "lecture", 2.5, {}, 1, reussi=True)
    b = entrainement.bulletin(base, 6)
    assert b["moyenne"] == 20 and b["valeur_lecture"] == 2.5 and not b["rates"]


def test_flux_en_replay_seulement_avec_des_bougies_5_min(base):
    j = _jeu_h1(base, n=700)
    debut = entrainement.DEPART + 3600 * 400
    m5 = [(debut + 300 * i, 3000.0, 3001.0, 2999.0, 3000.0 + (i % 2), 10.0) for i in range(12 * 290)]
    donnees.ajouter_bougies(base, j, "M5", m5)
    tp = entrainement.travaux_pratiques(base, j, 7, n_max=20, graine=1)
    assert tp["cas"] and all(c["instant"] >= debut for c in tp["cas"])
    assert sum(1 for c in tp["cas"] if c["avis"]) == len(tp["cas"])


def test_le_quiz_passe_d_abord_par_groq(base):
    from universite.ia import IALocale

    ia = IALocale(base, {"ia_commentaires": True, "ia_appels_max_jour": 100, "ia_url": "http://127.0.0.1:1/v1",
                         "ia_redaction": "groq", "redaction_url": "http://x"})
    ia.disponible = lambda: True
    ia._par_jarvis = lambda consigne, texte, max_tokens: ("La bonne réponse est D", "Groq llama")
    r = entrainement.poser_quiz(ia, 4)
    assert r and r[0]["obtenu"] == "D" and r[0]["reussi"] and r[0]["ia"] == "Groq (via Jarvis)"
    assert base.un("SELECT modele FROM ia_appels")["modele"] == "Groq llama"
    from universite import corpus

    ligne = corpus.exemples(base, 4, "quiz")[0]
    assert ligne["verdict"] == "juste" and ligne["messages"][2]["content"] == "La bonne réponse est D"
    assert corpus.resume(base) == {"04-liquidite": 1}


def test_corpus_garde_les_redactions_groq_et_masque_les_secrets(base):
    from universite import corpus
    from universite.ia import IALocale

    ia = IALocale(base, {"ia_commentaires": True, "ia_appels_max_jour": 100, "ia_url": "http://127.0.0.1:1/v1",
                         "ia_redaction": "groq", "redaction_url": "http://x"})
    ia._par_jarvis = lambda consigne, texte, max_tokens: ("Le prix est au-dessus du nuage.", "Groq llama")
    assert ia.rediger("Explique.", "Prix au-dessus du nuage. token: abcdefgh12345678", agent=3)
    ligne = corpus.exemples(base, 3)[0]
    assert ligne["verdict"] == "accepte" and "abcdefgh12345678" not in ligne["messages"][1]["content"]
    assert (corpus.dossier(base) / "LISEZ-MOI.txt").exists()
