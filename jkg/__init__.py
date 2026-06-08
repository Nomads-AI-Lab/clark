"""
JKG 7.0 — Unified Memory Fabric.
Four-layer AI memory: Profile + Factual + Episodic + Procedural.
Single SQLite database. CLARK retrieval (Value Iteration + A*).
Dynamic session-start context injection. Sync bridges.
"""

__version__ = "7.0.0"
__all__ = ["HybridMemory"]


def __getattr__(name):
    if name == "HybridMemory":
        from .memory import HybridMemory
        return HybridMemory
    raise AttributeError(f"module 'jkg' has no attribute {name!r}")
