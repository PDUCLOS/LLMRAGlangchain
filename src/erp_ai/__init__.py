"""erp-ai-copilot — Assistant IA & automatisation ERP (Sage / EBP) sur Azure.

Le package est conçu pour que le code métier ne dépende jamais du fournisseur :
la base (SQL Server en cible, SQLite en dev rapide), les embeddings, le LLM et
la base vectorielle sont derrière des interfaces interchangeables, pilotées par
les variables d'environnement (voir `erp_ai.config`).
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
