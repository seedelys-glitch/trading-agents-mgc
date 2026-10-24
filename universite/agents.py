# -*- coding: utf-8 -*-
"""
Les agents de l'université (le directeur est le n° 14 ; la mémoire : Scribe n° 15 et Archiviste n° 16) et leurs
4 fonctions de soutien.

Ce fichier dit QUI fait QUOI. Ce qu'un agent sait réellement faire est la liste `competences` : chaque nom
renvoie à un module de competences/. Un agent sans compétence branchée est affiché « en construction » :
le bureau ne lui invente jamais d'activité.

Les fonctions de soutien ne sont pas des modèles d'IA lancés en permanence : ce sont les rôles qu'un agent
mobilise pendant les étapes d'une mission (chaque étape enregistrée dit quel rôle a travaillé).
"""

SOUTIENS = {
    "chercheur": {"nom": "Chercheur", "phase": "recherche",
                  "mission": "Rassembler les données et les sources, calculer, comparer."},
    "professeur": {"nom": "Professeur", "phase": "redaction",
                   "mission": "Expliquer simplement ce qui a été trouvé, avec ses limites."},
    "documentaliste": {"nom": "Documentaliste", "phase": "recherche",
                       "mission": "Retrouver et citer les bonnes données (source, période, nombre de bougies)."},
    "connaissances": {"nom": "Gestionnaire des connaissances", "phase": "verification",
                      "mission": "Classer le document, le relier aux autres et demander sa vérification."},
}

REGLES_COMMUNES = [
    "Recherche et simulation seulement : aucun ordre, aucun courtier.",
    "Jamais de données, de résultats ou de statistiques inventés : chaque chiffre vient d'un calcul enregistré.",
    "Toujours dire ce qui est réel, estimé ou supposé.",
    "Pas de look-ahead : à l'instant t, seules les bougies déjà fermées sont visibles.",
    "Un échantillon trop petit n'est pas une preuve : le dire.",
]

AGENTS = [
    {"n": 1, "cle": "smc", "nom": "SMC / BOS / CHoCH", "court": "SMC", "salle": "smc",
     "mission": "Lire la structure du marché : sommets et creux, cassures (BOS), changements de caractère "
                "(CHoCH), zones de liquidité et order blocks.",
     "outils": ["calculs.structure", "calculs.order_blocks", "calculs.liquidite"],
     "qualite": ["Chaque cassure citée a une bougie et une heure.", "Unité de temps toujours précisée."],
     "escalade": "Structure contradictoire entre unités de temps -> demande l'avis du directeur.",
     "competences": ["analyse_smc"]},
    {"n": 2, "cle": "fibo", "nom": "Fibonacci", "court": "Fibo", "salle": "fibo",
     "mission": "Tracer les retracements et extensions sur la bonne impulsion, selon STRATEGIE.md "
                "(zones 0.618 à 0.893, jamais le 0.5).",
     "outils": ["calculs.fibo", "calculs.fvg"],
     "qualite": ["L'impulsion choisie est datée (début, fin).", "Les niveaux viennent du calcul, pas du texte."],
     "escalade": "Impulsion ambiguë -> demande la structure à l'agent SMC.",
     "competences": ["analyse_fibo"]},
    {"n": 3, "cle": "ichimoku", "nom": "Ichimoku", "court": "Ichi", "salle": "ichimoku",
     "mission": "Lire le nuage, Tenkan/Kijun et Chikou sur plusieurs unités de temps.",
     "outils": ["calculs.ichimoku"],
     "qualite": ["Position du prix par rapport au nuage vérifiable."],
     "escalade": "Signaux opposés entre D1 et H1 -> le signaler au directeur.",
     "competences": ["analyse_ichimoku"]},
    {"n": 4, "cle": "liquidite", "nom": "Heatmap / liquidité", "court": "Heat", "salle": None,
     "mission": "Étudier la carte de liquidité (Bookmap) : murs d'ordres, absorption, zones vidées.",
     "outils": ["export Bookmap (à vérifier)"],
     "qualite": ["Ne jamais déduire un carnet d'ordres de simples bougies."],
     "escalade": "Pas de données Bookmap -> l'agent reste en attente et le dit.",
     "competences": []},
    {"n": 5, "cle": "macro", "nom": "Macro / actualités", "court": "Macro", "salle": "calendrier",
     "mission": "Suivre le calendrier économique (CPI, NFP, FOMC...) et le contexte macro du gold.",
     "outils": ["calendrier Forex Factory (flux public)", "mgc.annonces", "historique des annonces de l'université"],
     "qualite": ["Heure de chaque annonce en heure de Paris.", "Source citée."],
     "escalade": "Annonce majeure dans l'heure -> prévient le gestionnaire des risques.",
     "competences": ["calendrier_macro"]},
    {"n": 6, "cle": "vwap_ema", "nom": "VWAP & EMA 200", "court": "VWAP", "salle": "tendance",
     "mission": "Calculer le VWAP de séance (depuis 18 h New York) avec ses bandes, et l'EMA 200 sur "
                "plusieurs unités de temps ; dire où est le prix et dans quel sens va la moyenne.",
     "outils": ["calculs.ema", "VWAP de séance CME", "fenêtre de replay sans look-ahead"],
     "qualite": ["Au moins 200 bougies fermées pour une EMA 200, sinon « pas assez de données ».",
                 "VWAP seulement si la séance a du volume.",
                 "Chaque chiffre est recalculé par le secrétaire-auditeur (agent 9)."],
     "escalade": "Écart avec la vérification -> le document est rejeté et le directeur est prévenu.",
     "competences": ["analyse_vwap_ema"]},
    {"n": 7, "cle": "dom", "nom": "DOM / carnet d'ordres", "court": "DOM", "salle": "orderflow",
     "mission": "Étudier le carnet d'ordres et le flux (delta) quand une vraie source existe.",
     "outils": ["calculs.order_flow (estimation depuis les bougies)"],
     "qualite": ["Toujours écrire « estimé » quand le delta vient des bougies."],
     "escalade": "Pas de carnet réel -> le dire, ne pas extrapoler.",
     "competences": ["analyse_flux"]},
    {"n": 8, "cle": "risque", "nom": "Gestionnaire des risques", "court": "Risque", "salle": None,
     "mission": "Vérifier chaque idée contre les règles : risque par trade, perte du jour, annonces, "
                "taille de position en MGC (1 point = 10 $).",
     "outils": ["mgc.risque", "mgc.vetos", "mgc.instrument"],
     "qualite": ["Un veto est toujours expliqué."],
     "escalade": "Règle franchie -> veto immédiat, prévient le directeur.",
     "competences": ["evaluation_risque"]},
    {"n": 9, "cle": "secretaire", "nom": "Secrétaire / auditeur", "court": "Audit", "salle": None,
     "mission": "Tenir les comptes rendus et recalculer de façon indépendante les chiffres des autres "
                "agents avant qu'un document soit marqué « vérifié ».",
     "outils": ["recalcul indépendant en Python pur", "base de l'université"],
     "qualite": ["Recalcul sans réutiliser le code de l'agent vérifié.", "Écarts chiffrés et tolérance écrite."],
     "escalade": "Écart hors tolérance -> rejet + message à l'auteur et au directeur.",
     "competences": ["verification_analyse", "verification_reproductibilite", "verification_risque",
                     "verification_calendrier", "verification_reactions", "verification_discours",
                     "verification_citations", "verification_memoire",
                     "verification_replay", "extraction_regles", "indexation_bibliotheque"]},
    {"n": 10, "cle": "discours", "nom": "Analyse des discours", "court": "Disc", "salle": None,
     "mission": "Analyser le ton des discours (Fed, BCE, Trésor) : faucon, colombe, neutre, et ce qui change.",
     "outils": ["flux officiel des discours (federalreserve.gov)", "lexique fixé à l'avance", "bibliothèque"],
     "qualite": ["Citation exacte et date de chaque passage utilisé."],
     "escalade": "Texte introuvable -> ne pas résumer de mémoire.",
     "competences": ["discours_fed"]},
    {"n": 11, "cle": "historien", "nom": "Historien des déclarations", "court": "Hist", "salle": None,
     "mission": "Garder l'historique des déclarations publiques et retrouver les précédents comparables.",
     "outils": ["bibliothèque de l'université", "historique des annonces"],
     "qualite": ["Chaque précédent a sa date et sa source."],
     "escalade": "Précédent incertain -> marqué « à vérifier ».",
     "competences": ["precedents"]},
    {"n": 12, "cle": "reaction", "nom": "Vérificateur des réactions", "court": "Réac", "salle": None,
     "mission": "Mesurer comment le gold a réellement réagi après une annonce ou un discours "
                "(avec les bougies de l'époque, sans look-ahead).",
     "outils": ["historique des annonces (agent 5)", "fenêtre de replay", "jeux de bougies M1 / M5"],
     "qualite": ["Fenêtre de mesure fixée AVANT de regarder le résultat."],
     "escalade": "Moins de 20 cas -> « échantillon insuffisant ».",
     "competences": ["reaction_annonces"]},
    {"n": 13, "cle": "quant", "nom": "Chercheur quantitatif", "court": "Quant", "salle": None,
     "mission": "Préparer et contrôler les données, puis tester les règles en replay : coûts réalistes, "
                "découpage entraînement / validation / test, pas de surapprentissage.",
     "outils": ["donnees.py (import, contrôle qualité)", "mgc.backtest", "mgc.stats"],
     "qualite": ["Source, période et nombre de bougies toujours affichés.", "Trous et doublons signalés."],
     "escalade": "Données douteuses -> bloque les analyses qui en dépendent.",
     "competences": ["import_tradingview", "controle_donnees", "replay_strategie_v1"]},
    {"n": 14, "cle": "directeur", "nom": "Directeur", "court": "Dir", "salle": None,
     "mission": "Interlocuteur principal de Jabran : reçoit les demandes, les confie aux bons agents, "
                "suit l'avancement et fait la synthèse de ce qui est vérifié.",
     "outils": ["file de missions", "états réels des agents"],
     "qualite": ["La synthèse ne reprend que des documents existants, avec leur statut."],
     "escalade": "Décision qui change l'objectif -> la pose à Jabran.",
     "competences": ["synthese_directeur", "demande_directeur"]},
    {"n": 15, "cle": "scribe", "nom": "Scribe", "court": "Scribe", "salle": None,
     "mission": "Noter en blocs tout ce qui se passe : missions des agents, conversations avec le directeur et le "
                "desk de Jarvis, sessions Claude du PC, règles décidées, alertes, état du projet ; ranger chaque "
                "bloc dans le dossier de son sujet et tenir l'index.",
     "outils": ["base de l'université", "chat du desk de Jarvis", "sessions Claude Code (~\\.claude\\projects)",
                "PROJECT_STATUS.md", "index de recherche FTS5"],
     "qualite": ["Seulement du texte réellement écrit ou enregistré : rien n'est résumé ni inventé.",
                 "Secrets masqués (clés, tokens, mots de passe, lignes CLE=valeur) ; contenu des fichiers lus jamais copié.",
                 "Chaque bloc garde sa source, sa date, sa session et son dossier."],
     "escalade": "Source illisible -> le passage continue avec les autres et l'erreur est notée.",
     "competences": ["ecriture_memoire"]},
    {"n": 16, "cle": "archiviste", "nom": "Archiviste", "court": "Archives", "salle": None,
     "mission": "Retrouver dans la mémoire ce dont quelqu'un a besoin (Jabran, Jarvis, le directeur, un agent, une "
                "session Claude) et le redonner avec la date, le dossier et la source de chaque bloc.",
     "outils": ["index de recherche FTS5 (accents ignorés)", "dossiers de sujet", "API /api/memoire"],
     "qualite": ["Ne cite que des blocs existants, avec leur numéro.", "Dit franchement quand rien n'est trouvé."],
     "escalade": "Rien trouvé -> le dit, ne répond pas de mémoire.",
     "competences": ["recherche_memoire"]},
]

PAR_NUMERO = {a["n"]: a for a in AGENTS}
PAR_CLE = {a["cle"]: a for a in AGENTS}
DIRECTEUR = 14


def agent(n):
    return PAR_NUMERO.get(int(n))


def roles():
    """Les rôles de soutien (4 par agent)."""
    return [{"agent": a["n"], "role": cle, **s} for a in AGENTS for cle, s in SOUTIENS.items()]


def fiche(a, competences_connues):
    """Fiche publique d'un agent, avec ce qui est réellement branché."""
    branchees = [c for c in a["competences"] if c in competences_connues]
    return {**a, "regles": REGLES_COMMUNES, "competences_branchees": branchees,
            "soutiens": [{"role": k, **v} for k, v in SOUTIENS.items()],
            "en_construction": not branchees}
