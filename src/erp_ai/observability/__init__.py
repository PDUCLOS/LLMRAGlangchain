"""Observabilité : journalisation des appels IA et suivi du coût.

Toute requête traitée est journalisée : rôle, client, modèle, tokens, coût
euro, latence, statut. C'est la base du pilotage FinOps côté conseil
(« combien ce client me coûte-t-il ? ») et de la non-régression.
"""

from erp_ai.observability.usage import estimate_cost, log_usage, usage_summary

__all__ = ["estimate_cost", "log_usage", "usage_summary"]
