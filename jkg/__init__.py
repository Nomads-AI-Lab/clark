"""JKG 3.0 — HYBRID Memory: Graph + Embeddings. One DB, zero conflicts."""
from .memory import HybridMemory, main_cli

__version__ = "3.0.0"
__all__ = ["HybridMemory", "main_cli"]
