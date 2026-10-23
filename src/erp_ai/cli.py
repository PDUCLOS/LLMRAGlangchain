"""CLI du copilote ERP.

    python -m erp_ai.cli init-db
    python -m erp_ai.cli ingest
    python -m erp_ai.cli ask "Quelles sont les règles de relance client ?"
    python -m erp_ai.cli sql "Quelles factures sont en retard ?"
    python -m erp_ai.cli eval
    python -m erp_ai.cli serve
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from erp_ai.config import get_settings


def _cmd_init_db(args: argparse.Namespace) -> int:
    from erp_ai.db.bootstrap import init_db
    from erp_ai.db.engine import create_engine_for

    settings = get_settings()
    engine = create_engine_for(settings)
    result = init_db(engine)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("skipped"):
        print("Base déjà initialisée (aucune recharge).")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    from erp_ai.service import CopilotService

    service = CopilotService()
    result = service.ingest(force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_ask(args: argparse.Namespace) -> int:
    from erp_ai.service import CopilotService

    service = CopilotService()
    result = service.ask(
        question=args.question,
        client_id=args.client_id,
        role=args.role,
        top_k=args.top_k,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0

    print("=" * 78)
    print(result["answer"])
    print("=" * 78)
    if result["sources"]:
        print("Sources :")
        for src in result["sources"]:
            section = f" § {src['section']}" if src.get("section") else ""
            score = f" (score {src['score']})" if src.get("score") is not None else ""
            print(f"  [{src['ref']}] {src['document']}{section}{score}")
    if result.get("sql"):
        print(f"\nSQL exécuté (lecture seule) :\n  {result['sql']['sql']}")
    usage = result["usage"]
    print(
        f"\nusage : {usage['provider']}/{usage['model']} — "
        f"{usage['tokens_in']} in / {usage['tokens_out']} out — "
        f"{usage['cout_eur']:.6f} EUR — {usage['latence_ms']} ms"
    )
    return 0


def _cmd_sql(args: argparse.Namespace) -> int:
    from erp_ai.service import CopilotService

    service = CopilotService()
    result = service.run_sql(args.question)
    print(result["sql"])
    print(f"\n{result['rowcount']} ligne(s)")
    for row in result["rows"][:20]:
        print("  " + " | ".join(f"{k}={v}" for k, v in row.items()))
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    from erp_ai.evaluation import run_evaluation

    report = run_evaluation()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["taux_recherche"] >= args.seuil else 1


def _cmd_usage(args: argparse.Namespace) -> int:
    from erp_ai.service import CopilotService

    service = CopilotService()
    rows = service.usage(days=args.days)
    if not rows:
        print("Aucune consommation enregistrée.")
        return 0
    for row in rows:
        print(
            f"{row['jour']} | {row['provider']}/{row['modele']} | "
            f"{row['nb_appels']} appels | {row['tokens_in']}+{row['tokens_out']} tokens | "
            f"{row['cout_eur']:.6f} EUR | {row['latence_moy_ms']} ms"
        )
    return 0


def _cmd_health(args: argparse.Namespace) -> int:
    from erp_ai.service import CopilotService

    print(json.dumps(CopilotService().health(), ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "erp_ai.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=get_settings().log_level.lower(),
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construit le parseur d'arguments."""
    parser = argparse.ArgumentParser(
        prog="erp-ai", description="Copilote IA & automatisation ERP (Sage / EBP)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-db", help="créer le schéma et charger le jeu de démo")
    p_init.set_defaults(func=_cmd_init_db)

    p_ing = sub.add_parser("ingest", help="indexer les documents dans la base vectorielle")
    p_ing.add_argument("--force", action="store_true", help="reconstruire même si déjà indexé")
    p_ing.set_defaults(func=_cmd_ingest)

    p_ask = sub.add_parser("ask", help="poser une question au copilote")
    p_ask.add_argument("question")
    p_ask.add_argument("--client-id", type=int, default=None)
    p_ask.add_argument("--role", default="daf", choices=["daf", "controleur", "commercial", "admin"])
    p_ask.add_argument("--top-k", type=int, default=None)
    p_ask.add_argument("--json", action="store_true")
    p_ask.set_defaults(func=_cmd_ask)

    p_sql = sub.add_parser("sql", help="traduire une question en SQL encadré et l'exécuter")
    p_sql.add_argument("question")
    p_sql.set_defaults(func=_cmd_sql)

    p_eval = sub.add_parser("eval", help="évaluer la recherche sur le gold set")
    p_eval.add_argument("--seuil", type=float, default=0.8, help="taux de succès minimal")
    p_eval.set_defaults(func=_cmd_eval)

    p_usage = sub.add_parser("usage", help="consommation tokens / coût / latence")
    p_usage.add_argument("--days", type=int, default=30)
    p_usage.set_defaults(func=_cmd_usage)

    p_health = sub.add_parser("health", help="état de l'application")
    p_health.set_defaults(func=_cmd_health)

    p_serve = sub.add_parser("serve", help="démarrer l'API")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=_cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée de la CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Any = getattr(args, "func")
    return int(handler(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
