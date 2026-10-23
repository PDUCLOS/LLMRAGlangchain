"""Garde-fou SQL : aucune requête non strictement en lecture seule ne passe.

Le modèle peut proposer une requête ; c'est ce module qui décide si elle est
exécutable. Les règles sont volontairement strictes (liste blanche de tables,
mot-clés interdits, une seule instruction) et le compte applicatif utilisé
en base est lui-même en lecture seule : deux verrous indépendants.

On ne compte pas sur le LLM pour la sécurité : le contrôle est déterministe.
"""

from __future__ import annotations

import re

FORBIDDEN_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "merge",
    "drop",
    "alter",
    "truncate",
    "create",
    "exec",
    "execute",
    "grant",
    "revoke",
    "deny",
    "backup",
    "restore",
    "dbcc",
    "openrowset",
    "opendatasource",
    "xp_cmdshell",
    "sp_executesql",
    "bcp",
    "shutdown",
    "use",
    "into",
}

ALLOWED_START = {"select", "with"}

_TOKEN_RE = re.compile(r"[a-z_][a-z0-9_]*")
_TABLE_RE = re.compile(r"\b(?:from|join|update|into)\s+([a-z_][a-z0-9_]*)")
_CTE_RE = re.compile(r"(?:\bwith\b|,)\s*([a-z_][a-z0-9_]*)\s+as\s*\(", re.IGNORECASE)


class SqlGuardError(ValueError):
    """Levée lorsqu'une requête ne respecte pas les règles de sécurité."""


def validate_readonly_sql(sql: str, allowed_tables: set[str]) -> str:
    """Valide une requête et retourne la requête normalisée.

    Raises:
        SqlGuardError: si la requête n'est pas strictement en lecture seule.
    """
    if not sql or not sql.strip():
        raise SqlGuardError("Requête vide.")

    statement = sql.strip().rstrip(";").strip()

    if ";" in statement:
        raise SqlGuardError("Une seule instruction SQL est autorisée par requête.")

    lowered = statement.lower()

    first_token = next((t for t in _TOKEN_RE.findall(lowered) if t not in {"("}), "")
    if first_token not in ALLOWED_START:
        raise SqlGuardError(
            f"Requête non autorisée : elle doit commencer par SELECT ou WITH (trouvé '{first_token}')."
        )

    tokens = set(_TOKEN_RE.findall(lowered))
    forbidden = sorted(tokens & FORBIDDEN_KEYWORDS)
    if forbidden:
        raise SqlGuardError(f"Mot-clé interdit : {', '.join(forbidden)}.")

    cte_names = {name.lower() for name in _CTE_RE.findall(statement)}
    referenced = {t.lower() for t in _TABLE_RE.findall(lowered)}
    unknown = referenced - allowed_tables - cte_names
    if unknown:
        raise SqlGuardError(
            f"Table non autorisée : {', '.join(sorted(unknown))}. "
            f"Tables autorisées : {', '.join(sorted(allowed_tables))}."
        )

    return statement
