"""Jeu de données de démonstration —métier de la gestion (BTP / négoce).

Données synthétiques mais réalistes : clients, articles, factures (avec lignes
et règlements), écritures comptables, et un corpus documentaire qui sert de
corpus RAG (procédures, contrat, note interne, manuel).

Objectif : pouvoir démontrer le pipeline complet (RAG + requêtes chiffrées +
relance client) sans données clients réelles.
"""

from __future__ import annotations

from datetime import datetime

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
CLIENTS = [
    # code, raison_sociale, secteur, pays, ville, encours_autorise, actif
    ("CLI-001", "Batipont SAS", "Bâtiment / gros œuvre", "France", "Lyon", 50000, True),
    ("CLI-002", "NéoCharpentes SAS", "Bâtiment / charpente", "France", "Villeurbanne", 30000, True),
    ("CLI-003", "Proxifroid Rhône", "Négoce / froid", "France", "Vénissieux", 20000, True),
    ("CLI-004", "Atelier Meyer SARL", "Industrie", "France", "Saint-Priest", 15000, True),
    ("CLI-005", "Groupe Valdec", "Industrie", "France", "Lyon", 80000, True),
    ("CLI-006", "Matériaux Express", "Négoce / matériaux", "France", "Vénissieux", 25000, True),
    (
        "CLI-007",
        "Charpentes du Rhône",
        "Bâtiment / charpente",
        "France",
        "Vaulx-en-Velin",
        40000,
        True,
    ),
    ("CLI-008", "SODIP Distribution", "Négoce", "France", "Bron", 12000, False),
]

# ---------------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------------
ARTICLES = [
    # code, désignation, famille, unité, prix HT, TVA %, stock
    ("ART-001", "Panneau sandwich isolant 1000x2000", "Isolation", "U", 89.90, 20.0, 420),
    ("ART-002", "Poutre bois lamellé 6x20x4m", "Structure", "U", 145.00, 20.0, 85),
    ("ART-003", "Rail de sécurité galvanisé 3m", "Sécurité", "U", 22.50, 20.0, 610),
    ("ART-004", "Plaque OSB3 2500x1250", "Panneaux", "U", 38.90, 20.0, 275),
    ("ART-005", "Ciment prompt 25 kg", "Mortier", "SAC", 9.80, 10.0, 1450),
    ("ART-006", "Laine de roche 100 mm", "Isolation", "U", 12.40, 20.0, 980),
    ("ART-007", "Vis autoperceuse 6x100 boîte 1000", "Quincaillerie", "BOITE", 78.00, 20.0, 64),
    ("ART-008", "Mortier de scellement rapide 25 kg", "Mortier", "SAC", 18.60, 10.0, 720),
    ("ART-009", "Charpente industrielle Pin classe C24", "Structure", "M3", 78.40, 20.0, 310),
    ("ART-010", "Écran sous-toiture HPV 150 g", "Étanchéité", "U", 31.20, 20.0, 190),
]

# ---------------------------------------------------------------------------
# Factures : (numéro, code client, date émission, jours de délai, statut)
# Le montant est recalculé à partir des lignes (invariant de cohérence).
# ---------------------------------------------------------------------------
FACTURES = [
    ("F-2026-0001", "CLI-001", "2026-01-12", 30, "PAYE"),
    ("F-2026-0002", "CLI-002", "2026-01-19", 30, "PAYE"),
    ("F-2026-0003", "CLI-003", "2026-01-28", 30, "PAYE"),
    ("F-2026-0004", "CLI-004", "2026-02-05", 45, "PAYE"),
    ("F-2026-0005", "CLI-005", "2026-02-11", 30, "PAYE"),
    ("F-2026-0006", "CLI-001", "2026-02-24", 30, "PAYE"),
    ("F-2026-0007", "CLI-006", "2026-03-03", 30, "RETARD"),
    ("F-2026-0008", "CLI-002", "2026-03-10", 30, "PAYE"),
    ("F-2026-0009", "CLI-007", "2026-03-18", 45, "PAYE"),
    ("F-2026-0010", "CLI-003", "2026-04-02", 30, "RETARD"),
    ("F-2026-0011", "CLI-005", "2026-04-09", 30, "PARTIEL"),
    ("F-2026-0012", "CLI-004", "2026-04-21", 30, "PAYE"),
    ("F-2026-0013", "CLI-006", "2026-05-06", 30, "IMPAYE"),
    ("F-2026-0014", "CLI-001", "2026-05-14", 30, "RETARD"),
    ("F-2026-0015", "CLI-007", "2026-05-27", 45, "PAYE"),
    ("F-2026-0016", "CLI-002", "2026-06-04", 30, "PAYE"),
    ("F-2026-0017", "CLI-003", "2026-06-15", 30, "RETARD"),
    ("F-2026-0018", "CLI-005", "2026-06-24", 30, "PAYE"),
    ("F-2026-0019", "CLI-006", "2026-07-02", 30, "IMPAYE"),
    ("F-2026-0020", "CLI-001", "2026-07-13", 30, "PARTIEL"),
    ("F-2026-0021", "CLI-004", "2026-07-27", 45, "PAYE"),
    ("F-2026-0022", "CLI-007", "2026-08-05", 30, "RETARD"),
    ("F-2026-0023", "CLI-008", "2026-08-11", 30, "IMPAYE"),
    ("F-2026-0024", "CLI-002", "2026-08-24", 30, "RETARD"),
    ("F-2026-0025", "CLI-003", "2026-09-02", 30, "PAYE"),
    ("F-2026-0026", "CLI-005", "2026-09-14", 30, "PAYE"),
    ("F-2026-0027", "CLI-001", "2026-09-23", 30, "RETARD"),
    ("F-2026-0028", "CLI-006", "2026-10-02", 30, "PAYE"),
    ("F-2026-0029", "CLI-007", "2026-10-09", 30, "RETARD"),
    ("F-2026-0030", "CLI-004", "2026-10-16", 30, "PAYE"),
]

# Lignes : rotation déterministe sur les articles, cohérente par client
LIGNES_PAR_FACTURE = [
    [("ART-001", 24), ("ART-006", 40), ("ART-005", 50)],
    [("ART-002", 12), ("ART-009", 18)],
    [("ART-004", 30), ("ART-007", 4)],
    [("ART-003", 60), ("ART-010", 25)],
    [("ART-008", 35), ("ART-005", 80)],
]


def _lignes(index: int) -> list[tuple[str, float]]:
    return LIGNES_PAR_FACTURE[index % len(LIGNES_PAR_FACTURE)]


def _dt(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d")


def _add_days(date_str: str, days: int) -> datetime:
    from datetime import timedelta

    return _dt(date_str) + timedelta(days=days)


# ---------------------------------------------------------------------------
# Corpus documentaire (corpus RAG)
# ---------------------------------------------------------------------------

DOC_PROCEDURE_RELANCE = """# Procédure de relance client

Document interne PRO-REL-2026-01 — Version 3.2 — Applicable depuis le 1er janvier 2026.
Responsable : Direction Administrative et Financière.

## 1. Objet

Cette procédure décrit les règles de relance des factures clients impayées.
Elle s'applique à l'ensemble des clients de l'entreprise, à l'exception des
clients en liquidation judiciaire, pour lesquels la procédure est remplacée
par une transmission du dossier au service contentieux.

## 2. Règle des délais de paiement

Le délai de paiement applicable est de 30 jours à compter de la date
d'émission de la facture. Un délai de 45 jours est accordé aux clients dont
l'encours autorisé est supérieur à 30000 euros et qui sont facturés au moins
quatre fois par an.

La date d'échéance est calculée à partir de la date d'émission, et non du
date de règlement comptable. En cas de facture partiellement réglée, la
relance porte sur le solde restant, et non sur le montant initial.

## 3. Escalade de la relance

La relance s'exécute en trois niveaux. Le premier niveau est un rappel de
courtoisie envoyé par courriel trente jours après l'échéance. Le deuxième
niveau est une relance ferme envoyée par courriel et par courrier recommandé
avec accusé de réception soixante jours après l'échéance. Le troisième
niveau est une mise en demeure, transmise par lettre recommandée avec
accusé de réception, et qui suspend toute nouvelle livraison.

Aucun niveau ne peut être déclenché sans validation du contrôleur de gestion.
La validation est matérialisée dans l'outil de gestion par un statut
« relance validée ».

## 4. Litiges et avoirs

Lorsqu'un litige est signalé par le client, aucune relance n'est émise tant
que le service client n'a pas enregistré le dossier de litige. Un avoir
commercial peut être partiellement ou totalement émis pour neutraliser la
facture contestée ; dans ce cas, la facture est comptabilisée comme soldée
par avoir et sort du périmètre de la relance.

## 5. Montants et tolérances

Les relances inférieures à 50 euros ne sont pas émises : elles sont
regroupées dans un relevé annuel des petits soldes. Le montant de la
relance correspond au solde restant dû, majoré des pénalités de retard
contractuelles au taux de 1,5 euro par jour et par tranche de 100 euros,
dans la limite de 15 pour cent du montant initial.

## 6. Traçabilité

Chaque relance est journalisée avec la date d'émission, le niveau de
relance, le canal utilisé, le montant réclamé et l'identifiant de la
personne ayant validé l'envoi. Ce journal est conservé cinq ans et doit
rester consultable dans le module de gestion.
"""

DOC_POLITIQUE_REMISE = """# Politique commerciale et remises 2026

Document interne POL-COM-2026-01 — Version 2.0 — Applicable au 1er janvier 2026.
Responsable : Direction Commerciale.

## 1. Principes

La remise est un outil de fidélisation et non un instrument de marge. Elle
est accordée en fonction du volume annuel facturé au client, de la régularité
des paiements et de la part de portefeuille stratégique.

## 2. Barème de remises

Une remise de 2 pour cent s'applique au-delà de 50000 euros de chiffre
d'affaires annuel facturé. Une remise de 4 pour cent s'applique au-delà de
150000 euros. Une remise de 6 pour cent s'applique au-delà de 300000 euros.

La remise s'applique sur le montant hors taxes de la facture concernée. Elle
est calculée au moment de la saisie de la facture, et non en fin de période.

## 3. Conditions de paiement

L'octroi d'une remise est conditionné au respect des délais de paiement
définis par la procédure de relance client. Un client en retard de plus de
soixante jours sur l'une de ses factures perd automatiquement le bénéfice de
la remise jusqu'à régularisation de la situation.

## 4. Encours et crédit

L'encours autorisé est fixé par la direction financière lors de la création
du compte client. Par défaut, il est de 15000 euros. Il peut être porté à
50000 euros après examen du bilan et avis de la direction. Tout dépassement
d'encours bloque la livraison tant qu'une validation écrite n'a pas été
donnée par la direction financière.

## 5. Validation

Toute remise supérieure à 5 pour cent doit être validée par la direction
commerciale. Les remises inférieures ou égales à 5 pour cent relèvent du
responsable de compte. La traçabilité des validations est conservée dans
l'outil de gestion.
"""

DOC_CONTRAT_CADRE = """# Contrat-cadre de fourniture 2026

Contrat-cadre — REF CC-2026-01 — Entreprise distributrice (ci-après « le
Fournisseur ») et ses clients professionnels (ci-après « le Client »).

## 1. Objet et champ d'application

Le présent contrat-cadre définit les conditions dans lesquelles le Fournisseur
met à disposition du Client des produits de négoce et de chantier, ainsi que
les services associés de livraison, de reprise et de conseil technique.

## 2. Commande et livraison

Les commandes sont passées par le portail client ou par API REST du système
de gestion. Le délai de livraison standard est de cinq jours ouvrés à
compter de la validation de la commande. Les commandes passées avant 11
heures sont livrées le jour ouvré suivant pour les références stockées.

## 3. Prix et révision

Les prix sont ceux du catalogue en vigueur à la date de la commande. Une
révision annuelle des prix peut être appliquée au 1er janvier de chaque année
par accord écrit, plafonnée à l'indice ICGIT publication.

## 4. Paiement

Les factures sont payables à 30 jours à compter de la date d'émission, par
virement ou chèque. Les modalités dérogatoires sont décrites à l'article 5.

## 5. Conditions particulières

Pour les clients réalisant plus de 200000 euros de chiffre d'affaires
annuel, un délai de 45 jours peut être appliqué. Ce délai est un délai de
paiement contractuel et non un délai de paiement de droit commun.

## 6. Récupération et litiges

En cas de retard de paiement, le Fournisseur peut suspendre les livraisons
après mise en demeure restée sans effet pendant un délai de soixante jours.
Les pénalités de retard contractuelles sont de 1,5 euro par jour et par
tranche de 100 euros, dans la limite de 15 pour cent du montant initial.

## 7. Données personnelles

Les données personnelles échangées dans le cadre du portail client sont
traitées pour la seule gestion de la relation commerciale. Elles sont
conservées pendant la durée de la relation contractuelle et trois ans au
maximum après sa cessation, à l'exception des données comptables et
fiscales, conservées selon les obligations légales applicables.
"""

DOC_GUIDE_SAISIE = """# Guide de saisie et de clôture comptable

Document interne GSC-2026-01 — Version 1.4 — Service comptabilité.
Destiné aux utilisateurs de Sage 100 Gestion Commerciale et du module
comptabilité.

## 1. Principes de saisie

Toute saisie fait l'objet d'une facture, d'une ligne de facture et d'une
écriture comptable correspondante. Le montant de la facture est toujours
égal à la somme de ses lignes. Le montant toutes taxes comprises est obtenu
en appliquant le taux de TVA de chaque ligne.

## 2. Règle d'arrondi

Les montants sont arrondis à l'euro supérieur pour la facturation. Le
total d'une facture est calculé à partir des montants de lignes déjà
arrondis, et non à partir du total non arrondi.

## 3. Clôture mensuelle

La clôture mensuelle comporte sept étapes : lettrage des règlements,
rapprochement bancaire, contrôle des soldes clients, contrôle des stocks,
déclaration de TVA, calcul de la marge par famille, et validation par le
responsable comptable.

Le contrôle des soldes clients consiste à rapprocher le balance client
comptable du balance client de gestion. Tout écart supérieur à un euro doit
être expliqué avant validation.

## 4. Stock

Le stock est mis à jour à la livraison, à la facturation ou à la reprise,
selon la nature de l'opération. La valorisation du stock est en coût moyen
pondéré. L'écart d'inventaire supérieur à 2 pour cent de la valeur du stock
de la famille donne lieu à une analyse documentée.

## 5. Reporting

Le tableau de bord de direction est produit mensuellement à partir d'une vue
analytique dédiée. Les indicateurs suivis sont le chiffre d'affaires, la
marge brute par famille, le taux de recouvrement à 30 et 60 jours, et
l'encours client total.

## 6. Sauvegarde

La base de gestion fait l'objet d'une sauvegarde quotidienne avec
conservation de sept versions. La restauration est testée chaque trimestre.
"""

DOC_NOTE_RECOUVREMENT = """# Note interne — Recouvrement et litiges

Note interne N-2026-07 — Direction Administrative et Financière.

## Situation au troisième trimestre

Le taux de recouvrement à 30 jours s'établit à 91,4 pour cent, en baisse de
2,1 points par rapport au deuxième trimestre. Cette dégradation provient
principalement de trois clients du secteur négoce, dont les encours dépassent
le seuil de 30000 euros.

## Factures en souffrance

Six factures dépassent 90 jours de retard, pour un cumul de 48 700 euros
hors taxes. Deux de ces factures font l'objet d'un litige technique : la
prestation a été réalisée mais la réserve de 15 pour cent n'a pas été levée.

## Actions engagées

Une revue du fichier des encours a été conduite avec le contrôleur de
gestion. Trois clients en dépassement d'encours ont été passés en livraison
suspendue. Les relances de niveau 2 ont été systématisées sur l'ensemble des
factures de plus de 60 jours.

## Point de vigilance ERP

La version actuelle du module de gestion ne restitue pas la ventilation des
factures échues par tranche d'ancienneté. Cette restitution est reconstruite
à partir de la vue analytique dédiée, ce qui allonge le temps de préparation
du tableau de bord. L'évolution attendue du fournisseur permettrait de supprimer
cette étape manuelle.
"""


def documents() -> list[dict]:
    """Documents de démonstration prêts à être ingérés."""
    return [
        {
            "source": "sharepoint",
            "type_doc": "procedure",
            "titre": "Procédure de relance client",
            "client_id": None,
            "date_doc": datetime(2026, 1, 1),
            "chemin": "/sites/finance/Documents/PRO-REL-2026-01.docx",
            "version": "3.2",
            "contenu": DOC_PROCEDURE_RELANCE,
        },
        {
            "source": "sharepoint",
            "type_doc": "procedure",
            "titre": "Politique commerciale et remises 2026",
            "client_id": None,
            "date_doc": datetime(2026, 1, 1),
            "chemin": "/sites/finance/Documents/POL-COM-2026-01.docx",
            "version": "2.0",
            "contenu": DOC_POLITIQUE_REMISE,
        },
        {
            "source": "erp",
            "type_doc": "contrat",
            "titre": "Contrat-cadre de fourniture 2026",
            "client_id": None,
            "date_doc": datetime(2026, 1, 1),
            "chemin": "/sites/finance/Documents/CC-2026-01.docx",
            "version": "1.0",
            "contenu": DOC_CONTRAT_CADRE,
        },
        {
            "source": "fichier",
            "type_doc": "manuel",
            "titre": "Guide de saisie et de clôture comptable",
            "client_id": None,
            "date_doc": datetime(2026, 3, 1),
            "chemin": "/sites/compta/Documents/GSC-2026-01.pdf",
            "version": "1.4",
            "contenu": DOC_GUIDE_SAISIE,
        },
        {
            "source": "fichier",
            "type_doc": "note",
            "titre": "Note interne — Recouvrement et litiges",
            "client_id": None,
            "date_doc": datetime(2026, 10, 1),
            "chemin": "/sites/finance/Documents/N-2026-07.pdf",
            "version": "1.0",
            "contenu": DOC_NOTE_RECOUVREMENT,
        },
    ]
