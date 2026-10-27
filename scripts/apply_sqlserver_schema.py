#!/usr/bin/env python
"""Applique le schéma SQL Server (schéma de tables, vues, rôles).

Utilisé par la CI pour confronter `sql/00_schema.sql` au moteur cible, et
par l'installation locale sur le poste x86-64 (LG Gram).

    python scripts/apply_sqlserver_schema.py --url "mssql+pyodbc://sa:Mdp@localhost:1433/erp_ai?..."

Options :
    --url           URL SQLAlchemy de la base cible (ou variable DATABASE_URL)
    --admin-url     URL vers la base `master` (par défaut : même serveur)
    --database      nom de la base à créer si absente
    --schema-file   fichier de schéma (défaut : sql/00_schema.sql)
    --roles-file    fichier de rôles à appliquer après le schéma
    --app-password / --readonly-password / --ingest-password
                    mots de passe injectés dans les variables $(...) du
                    fichier de rôles
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parents[1]
GO_SPLIT_RE = re.compile(r"(?im)^\s*GO\s*$")


def split_batches(sql_text: str) -> list[str]:
    """Découpe un script SQL Server en lots (séparateur `GO`)."""
    return [batch.strip() for batch in GO_SPLIT_RE.split(sql_text) if batch.strip()]


def admin_url_for(url: str) -> str:
    """Remplace la base de l'URL par `master` (pour créer la base).

    L'hôte, le port et les paramètres de connexion sont conservés.
    """
    if "@" not in url:
        return url
    prefix, rest = url.split("@", 1)
    if "/" not in rest:
        return url
    host, path = rest.split("/", 1)
    db, _, query = path.partition("?")
    suffix = f"?{query}" if query else ""
    return f"{prefix}@{host}/master{suffix}"


def substitute_variables(sql_text: str, variables: dict[str, str]) -> str:
    """Remplace les variables `$(Nom)` du script sqlcmd."""
    for name, value in variables.items():
        sql_text = sql_text.replace(f"$({name})", value)
    return sql_text


def apply_file(engine: sa.Engine, path: Path, variables: dict[str, str] | None = None) -> int:
    """Applique un fichier SQL et renvoie le nombre de lots exécutés."""
    text = path.read_text(encoding="utf-8")
    if variables:
        text = substitute_variables(text, variables)
    batches = split_batches(text)
    with engine.begin() as conn:
        for index, batch in enumerate(batches, start=1):
            try:
                conn.exec_driver_sql(batch)
            except Exception as exc:
                raise SystemExit(
                    f"Échec du lot {index}/{len(batches)} de {path.name} :\n{batch[:400]}\n\n{exc}"
                ) from exc
    return len(batches)


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée."""
    parser = argparse.ArgumentParser(description="Applique le schéma SQL Server du projet.")
    parser.add_argument("--url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--admin-url", default=None)
    parser.add_argument("--database", default="erp_ai")
    parser.add_argument("--schema-file", default=str(REPO_ROOT / "sql" / "00_schema.sql"))
    parser.add_argument("--roles-file", default=None)
    parser.add_argument(
        "--skip-schema-if-exists",
        action="store_true",
        help="n'applique pas le schéma (qui recrée les tables) si dbo.client existe déjà",
    )
    parser.add_argument("--app-password", default=os.environ.get("ERP_APP_PASSWORD", ""))
    parser.add_argument("--readonly-password", default=os.environ.get("ERP_READONLY_PASSWORD", ""))
    parser.add_argument("--ingest-password", default=os.environ.get("ERP_INGEST_PASSWORD", ""))
    args = parser.parse_args(argv)

    if not args.url.startswith("mssql"):
        print(
            "URL SQL Server attendue (mssql+pyodbc://...). "
            f"Reçue : {args.url!r}",
            file=sys.stderr,
        )
        return 2

    admin_url = args.admin_url or admin_url_for(args.url)
    print(f"==> Création de la base {args.database} si absente")
    admin_engine = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            sa.text("SELECT CASE WHEN DB_ID(:db) IS NULL THEN 0 ELSE 1 END"), {"db": args.database}
        ).scalar_one()
        if not exists:
            conn.exec_driver_sql(f"CREATE DATABASE [{args.database}]")
            print(f"    base créée : {args.database}")
        else:
            print(f"    base déjà présente : {args.database}")

    engine = sa.create_engine(args.url, isolation_level="AUTOCOMMIT")
    schema_path = Path(args.schema_file)
    with engine.connect() as conn:
        deja = conn.execute(sa.text("SELECT OBJECT_ID('dbo.client', 'U')")).scalar() is not None
    if args.skip_schema_if_exists and deja:
        print(f"==> {schema_path.name} ignoré : base déjà initialisée (données conservées)")
    else:
        nb = apply_file(engine, schema_path)
        print(f"==> {schema_path.name} appliqué ({nb} lot(s))")

    if args.roles_file:
        roles_path = Path(args.roles_file)
        variables = {
            "AppPassword": args.app_password or "Tmp_App_2026!",
            "ReadOnlyPassword": args.readonly_password or "Tmp_ReadOnly_2026!",
            "IngestPassword": args.ingest_password or "Tmp_Ingest_2026!",
        }
        missing = [k for k, v in variables.items() if not v]
        if missing:
            print(f"[avertissement] mots de passe non fournis : {', '.join(missing)}")
        nb_roles = apply_file(engine, roles_path, variables)
        print(f"==> {roles_path.name} appliqué ({nb_roles} lot(s))")

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
