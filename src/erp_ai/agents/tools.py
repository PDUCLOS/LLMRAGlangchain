"""Outils métier du copilote ERP.

Deux familles d'outils :

  * des requêtes de gestion déterministes (`ErpTools`) : impayés, chiffre
    d'affaires, recouvrement, top clients. Elles ne dépendent d'aucun LLM, donc
    les chiffres sont fiables et reproductibles ;
  * un agent Text-to-SQL (`SqlAgent`) qui traduit une question en SQL. La
    requête produite passe systématiquement par le garde-fou de lecture seule
    avant exécution.

Le calcul des retards est fait en Python et non en SQL : la même logique
fonctionne sur SQL Server et sur SQLite, sans dialecte spécifique.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from erp_ai.agents.safe_sql import SqlGuardError, validate_readonly_sql
from erp_ai.config import Settings, get_settings
from erp_ai.db import models
from erp_ai.providers.llm import ChatLLM


@dataclass
class SqlResult:
    """Résultat d'une exécution SQL encadrée."""

    sql: str
    rows: list[dict[str, Any]]
    rowcount: int
    meta: dict[str, Any] = field(default_factory=dict)


def _as_date(value: Any) -> date | None:
    """Normalise une date ERP (datetime, date ou texte ISO selon le dialecte)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def avec_anciennete(
    rows: list[dict[str, Any]], today: date, min_jours: int = 0
) -> list[dict[str, Any]]:
    """Ajoute `jours_retard` aux factures et écarte celles sous le seuil."""
    out: list[dict[str, Any]] = []
    for row in rows:
        echeance = _as_date(row["date_echeance"])
        jours = (today - echeance).days if echeance else 0
        if jours < min_jours:
            continue
        enrichie = {**row, "jours_retard": jours}
        for montant in ("montant_ttc", "montant_ht"):
            if montant in row:
                enrichie[montant] = float(row[montant] or 0)
        enrichie["date_echeance"] = echeance.isoformat() if echeance else None
        if "date_emission" in row:
            emission = _as_date(row["date_emission"])
            enrichie["date_emission"] = emission.isoformat() if emission else None
        out.append(enrichie)
    return out


class ErpTools:
    """Requêtes de gestion sur le référentiel ERP."""

    def __init__(self, engine: Engine, settings: Settings | None = None) -> None:
        self.engine = engine
        self.settings = settings or get_settings()

    # -- Impayés ---------------------------------------------------------
    def impayes(
        self,
        client_id: int | None = None,
        min_jours: int = 0,
        aujourdhui: date | None = None,
    ) -> list[dict[str, Any]]:
        """Factures non soldées, avec l'ancienneté du retard."""
        today = aujourdhui or date.today()
        stmt = (
            sa.select(
                models.facture.c.numero,
                models.facture.c.montant_ttc,
                models.facture.c.montant_ht,
                models.facture.c.date_emission,
                models.facture.c.date_echeance,
                models.facture.c.statut,
                models.client.c.id.label("client_id"),
                models.client.c.code.label("client_code"),
                models.client.c.raison_sociale,
            )
            .select_from(
                models.facture.join(models.client, models.facture.c.client_id == models.client.c.id)
            )
            .where(models.facture.c.statut != "PAYE")
            .order_by(models.facture.c.date_echeance)
        )
        if client_id is not None:
            stmt = stmt.where(models.facture.c.client_id == client_id)

        with self.engine.connect() as conn:
            rows = [dict(row) for row in conn.execute(stmt).mappings().all()]

        return avec_anciennete(rows, today, min_jours)

    def synthese_impayes(
        self,
        client_id: int | None = None,
        min_jours: int = 0,
        aujourdhui: date | None = None,
    ) -> dict[str, Any]:
        """Synthèse : total, nombre, par tranche d'ancienneté, par client."""
        lignes = self.impayes(client_id=client_id, min_jours=min_jours, aujourdhui=aujourdhui)
        tranches = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
        par_client: dict[str, float] = {}
        for ligne in lignes:
            jours = ligne["jours_retard"]
            montant = ligne["montant_ttc"]
            if jours <= 30:
                tranches["0-30"] += montant
            elif jours <= 60:
                tranches["31-60"] += montant
            elif jours <= 90:
                tranches["61-90"] += montant
            else:
                tranches["90+"] += montant
            par_client[ligne["raison_sociale"]] = (
                par_client.get(ligne["raison_sociale"], 0.0) + montant
            )

        return {
            "nb_factures": len(lignes),
            "total_ttc": round(sum(ligne["montant_ttc"] for ligne in lignes), 2),
            "par_tranche": {k: round(v, 2) for k, v in tranches.items()},
            "par_client": {
                k: round(v, 2) for k, v in sorted(par_client.items(), key=lambda i: -i[1])
            },
            "seuil_jours": min_jours,
        }

    # -- Ventes ----------------------------------------------------------
    def chiffre_affaires(self, annee: int) -> dict[str, Any]:
        """Chiffre d'affaires facturé (HT) par client sur l'année."""
        debut = datetime(annee, 1, 1)
        fin = datetime(annee + 1, 1, 1)
        stmt = (
            sa.select(
                models.client.c.raison_sociale,
                sa.func.sum(models.facture.c.montant_ht).label("ca_ht"),
                sa.func.count(models.facture.c.id).label("nb_factures"),
            )
            .select_from(
                models.facture.join(models.client, models.facture.c.client_id == models.client.c.id)
            )
            .where(models.facture.c.date_emission >= debut, models.facture.c.date_emission < fin)
            .group_by(models.client.c.raison_sociale)
            .order_by(sa.desc("ca_ht"))
        )
        with self.engine.connect() as conn:
            rows = [
                {
                    "raison_sociale": row["raison_sociale"],
                    "ca_ht": round(float(row["ca_ht"] or 0), 2),
                    "nb_factures": int(row["nb_factures"] or 0),
                }
                for row in conn.execute(stmt).mappings().all()
            ]
        return {
            "annee": annee,
            "total_ht": round(sum(r["ca_ht"] for r in rows), 2),
            "par_client": rows,
        }

    def top_clients(self, annee: int, limit: int = 5) -> list[dict[str, Any]]:
        """Top clients de l'année (encours autorisé inclus)."""
        stmt = (
            sa.select(
                models.client.c.code,
                models.client.c.raison_sociale,
                models.client.c.encours_autorise,
                sa.func.sum(models.facture.c.montant_ht).label("ca_ht"),
            )
            .select_from(
                models.facture.join(models.client, models.facture.c.client_id == models.client.c.id)
            )
            .where(
                models.facture.c.date_emission >= datetime(annee, 1, 1),
                models.facture.c.date_emission < datetime(annee + 1, 1, 1),
            )
            .group_by(models.client.c.id)
            .order_by(sa.desc("ca_ht"))
            .limit(limit)
        )
        with self.engine.connect() as conn:
            return [
                {
                    "code": row["code"],
                    "raison_sociale": row["raison_sociale"],
                    "ca_ht": round(float(row["ca_ht"] or 0), 2),
                    "encours_autorise": float(row["encours_autorise"] or 0),
                }
                for row in conn.execute(stmt).mappings().all()
            ]

    # -- Lecture SQL encadrée -------------------------------------------
    def run_readonly_sql(self, sql: str) -> SqlResult:
        """Exécute une requête après validation par le garde-fou."""
        statement = validate_readonly_sql(sql, self.settings.allowed_tables)
        with self.engine.connect() as conn:
            rows = [dict(row) for row in conn.execute(sa.text(statement)).mappings().all()]
        return SqlResult(sql=statement, rows=rows, rowcount=len(rows))


class SqlAgent:
    """Traduit une question métier en SQL en lecture seule.

    Deux modes :
      * `local`  — intention détectée par mots-clés, gabarit SQL figé ;
      * `azure`  — le LLM propose la requête, le garde-fou la valide.

    Dans les deux cas, l'exécution passe par `ErpTools.run_readonly_sql`.
    """

    INTENTS: list[tuple[str, tuple[str, ...]]] = [
        ("impayes", ("impay", "retard", "récup", "recouvr", "encours", "du")),
        ("ca", ("chiffre d'affaires", "chiffre affaires", "ca ", "ventes", "facturé")),
        ("top_clients", ("top client", "meilleur client", "principaux client")),
    ]

    TEMPLATES: dict[str, str] = {
        "impayes": (
            "SELECT f.numero, c.raison_sociale AS client, f.montant_ttc, f.date_emission, "
            "f.date_echeance, f.statut "
            "FROM facture f JOIN client c ON c.id = f.client_id "
            "WHERE f.statut <> 'PAYE' ORDER BY f.date_echeance"
        ),
        "ca": (
            "SELECT c.raison_sociale, SUM(f.montant_ht) AS ca_ht, COUNT(*) AS nb_factures "
            "FROM facture f JOIN client c ON c.id = f.client_id "
            "GROUP BY c.raison_sociale ORDER BY ca_ht DESC"
        ),
        "top_clients": (
            "SELECT c.code, c.raison_sociale, SUM(f.montant_ht) AS ca_ht "
            "FROM facture f JOIN client c ON c.id = f.client_id "
            "GROUP BY c.id ORDER BY ca_ht DESC"
        ),
    }

    # « au-delà de 60 jours », « plus de 90 jours », « supérieur à 30 j »...
    SEUIL_RETARD = re.compile(
        r"(?:au[- ]del[àa]\s+de|plus\s+de|sup[ée]rieure?s?\s+[àa]|>=?)\s*(\d+)\s*j(?:ours?)?\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        engine: Engine,
        llm: ChatLLM | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.engine = engine
        self.llm = llm
        self.settings = settings or get_settings()
        self.tools = ErpTools(engine, self.settings)

    def detect_intent(self, question: str) -> str | None:
        """Associe la question à une intention connue (mode local)."""
        lowered = question.lower()
        for intent, keywords in self.INTENTS:
            if any(keyword in lowered for keyword in keywords):
                return intent
        return None

    @classmethod
    def extract_min_jours(cls, question: str) -> int:
        """Seuil de retard exprimé dans la question (0 s'il n'y en a pas)."""
        match = cls.SEUIL_RETARD.search(question)
        return int(match.group(1)) if match else 0

    def _llm_sql(self) -> bool:
        return self.llm is not None and self.settings.llm_provider.lower() == "azure"

    def build_sql(self, question: str) -> str:
        """Produit la requête SQL correspondant à la question."""
        if self._llm_sql():
            from erp_ai.rag.prompts import SQL_SYSTEM_PROMPT, build_sql_prompt

            schema_hint = (
                "client(id, code, raison_sociale, secteur, encours_autorise) ; "
                "facture(id, numero, client_id, date_emission, date_echeance, montant_ht, "
                "montant_ttc, statut) ; ligne_facture(facture_id, article_id, quantite, "
                "prix_unitaire_ht, montant_ht) ; reglement(facture_id, date_reglement, montant, mode)"
            )
            prompt = build_sql_prompt(question, schema_hint)
            sql = self.llm.complete(SQL_SYSTEM_PROMPT, prompt)
            return sql.strip().strip("`").removeprefix("sql").strip()

        intent = self.detect_intent(question)
        if intent is None:
            raise SqlGuardError(
                "Aucune intention connue pour cette question en mode local "
                "(activez le provider Azure pour une traduction libre)."
            )
        return self.TEMPLATES[intent]

    def run(self, question: str, aujourdhui: date | None = None) -> SqlResult:
        """Construit, valide et exécute la requête.

        En mode local, l'intention `impayes` est servie par `ErpTools.impayes` :
        le retard est calculé en Python et le seuil de la question appliqué,
        plutôt qu'un gabarit SQL qui renverrait toutes les factures non soldées.
        """
        if not self._llm_sql() and self.detect_intent(question) == "impayes":
            return self.run_impayes(question, aujourdhui)
        return self.tools.run_readonly_sql(self.build_sql(question))

    def run_impayes(self, question: str, aujourdhui: date | None = None) -> SqlResult:
        """Factures non soldées au-delà du seuil de la question, avec ancienneté.

        La lecture passe par le gabarit SQL validé (lecture seule) ; le retard
        est calculé en Python, comme dans `ErpTools.impayes`.
        """
        today = aujourdhui or date.today()
        min_jours = self.extract_min_jours(question)
        brut = self.tools.run_readonly_sql(self.TEMPLATES["impayes"])
        rows = avec_anciennete(brut.rows, today, min_jours)
        return SqlResult(
            sql=brut.sql,
            rows=rows,
            rowcount=len(rows),
            meta={
                "min_jours": min_jours,
                "aujourdhui": today.isoformat(),
                "total_ttc": round(sum(r["montant_ttc"] for r in rows), 2),
            },
        )
