from clark import HybridMemory


def test_stats_initializes_empty_database(tmp_path):
    memory = HybridMemory(db_path=str(tmp_path / "memory.db"))

    stats = memory.stats()

    assert stats["entities"] == 0
    assert stats["facts"] == 0
    assert stats["relations"] == 0
    assert stats["episodes"] == 0
    assert stats["has_embeddings"] is True


def test_index_and_search_skill_round_trip(tmp_path):
    memory = HybridMemory(db_path=str(tmp_path / "skills.db"))

    stored = memory.index_skill(
        "code-review",
        description="Reviews pull requests for security and correctness",
        triggers=["review", "pull request", "security"],
        category="engineering",
    )
    results = memory.search_skills("security review")

    assert stored["status"] == "ok"
    assert stored["action"] == "created"
    assert len(results) == 1
    assert results[0]["name"] == "code-review"
    assert "security" in results[0]["triggers"]


def test_profile_get_returns_directly_persisted_profile_rows(tmp_path):
    memory = HybridMemory(db_path=str(tmp_path / "profile.db"))
    memory.conn.execute(
        """
        INSERT INTO memory_profile(key, value, category, confidence, source)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("communication_style", "concise and direct", "preference", 0.95, "test"),
    )
    memory.conn.commit()

    profile = memory.get_profile("preference")

    assert len(profile) == 1
    assert profile[0]["key"] == "communication_style"
    assert profile[0]["value"] == "concise and direct"

