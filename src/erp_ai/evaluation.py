"""Évaluation de la qualité de la recherche (gold set).

Le gold set est un jeu de questions métier avec :
  * les documents attendus en source ;
  * des mots-clés qui doivent apparaître dans la réponse.

On mesure deux choses : le taux de succès de la recherche (le bon document
est-il remonté ?) et le taux de couverture des mots-clés dans la réponse.
Ces deux taux sont des seuils bloquants en CI : un changement de prompt, de
découpage ou d'embedding qui dégrade le résultat est détecté avant livraison.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from erp_ai.config import PROJECT_ROOT

GOLD_SET_PATH = PROJECT_ROOT / "eval" / "gold_set.json"


def load_gold_set(path: Path | None = None) -> list[dict[str, Any]]:
    """Charge le gold set (vide si absent)."""
    target = path or GOLD_SET_PATH
    if not target.exists():
        return []
    data = json.loads(target.read_text(encoding="utf-8"))
    return data.get("questions", [])


def run_evaluation(path: Path | None = None) -> dict[str, Any]:
    """Exécute l'évaluation et renvoie le rapport."""
    from erp_ai.service import CopilotService

    questions = load_gold_set(path)
    if not questions:
        return {"erreur": "gold set introuvable ou vide", "questions": 0}

    service = CopilotService()
    top_k = service.settings.top_k

    details: list[dict[str, Any]] = []
    succes_recherche = 0
    succes_reponse = 0

    for item in questions:
        question = item["question"]
        attendus = [t.lower() for t in item.get("documents_attendus", [])]
        mots_cles = [m.lower() for m in item.get("mots_cles", [])]

        retrieved = service.retriever.search(question, top_k=top_k)
        titres = [r.titre.lower() for r in retrieved]
        docs_trouves = any(any(att in t for t in titres) for att in attendus)
        succes_recherche += int(docs_trouves)

        resultat = service.ask(question=question, role="daf", top_k=top_k)
        reponse = (resultat["answer"] or "").lower()
        manquants = [m for m in mots_cles if m not in reponse]
        succes_reponse += int(not manquants)

        details.append(
            {
                "question": question,
                "doc_attendu": item.get("documents_attendus", []),
                "doc_trouve": docs_trouves,
                "sources": [r.source_ref for r in retrieved],
                "mots_cles_manquants": manquants,
                "statut": resultat["statut"],
                "latence_ms": resultat["usage"]["latence_ms"],
            }
        )

    total = len(questions)
    return {
        "questions": total,
        "taux_recherche": round(succes_recherche / total, 3),
        "taux_reponse": round(succes_reponse / total, 3),
        "details": details,
    }
