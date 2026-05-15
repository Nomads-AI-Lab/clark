"""
JKG 7.0 — Unified Memory Fabric.
Four-layer AI memory: Profile + Factual + Episodic + Procedural.
Single SQLite database. CLARK retrieval (Value Iteration + A*).
Dynamic session-start context injection. Sync bridges.
"""
from .memory import HybridMemory

__version__ = "7.0.0"
__all__ = ["HybridMemory"]
