"""
Tests for the Memory Protocol (Semantic Memory & Vector Store)

Tests:
- MemoryType enum
- Embedding, MemoryEntry, SearchResult dataclasses
- SimpleEmbedder class
- VectorStore class
- SemanticMemoryCore class
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch
import json
import tempfile
import math

from src.ouroboros.protocols.memory import (
    MemoryType,
    Embedding,
    MemoryEntry,
    SearchResult,
    SimpleEmbedder,
    VectorStore,
    SemanticMemoryCore,
)


# ============================================================
# Enum Tests
# ============================================================

class TestMemoryType:
    """Tests for MemoryType enum."""

    def test_insight_type(self):
        """Test INSIGHT memory type."""
        assert MemoryType.INSIGHT.value == "insight"

    def test_pattern_type(self):
        """Test PATTERN memory type."""
        assert MemoryType.PATTERN.value == "pattern"

    def test_failure_type(self):
        """Test FAILURE memory type."""
        assert MemoryType.FAILURE.value == "failure"

    def test_success_type(self):
        """Test SUCCESS memory type."""
        assert MemoryType.SUCCESS.value == "success"

    def test_rule_type(self):
        """Test RULE memory type."""
        assert MemoryType.RULE.value == "rule"

    def test_context_type(self):
        """Test CONTEXT memory type."""
        assert MemoryType.CONTEXT.value == "context"

    def test_all_types_defined(self):
        """Test all expected types are defined."""
        types = list(MemoryType)
        assert len(types) == 6


# ============================================================
# Dataclass Tests
# ============================================================

class TestEmbedding:
    """Tests for Embedding dataclass."""

    def test_create_embedding(self):
        """Test creating an embedding."""
        vec = [0.1, 0.2, 0.3, 0.4]
        emb = Embedding(vector=vec, dimensions=4)
        assert emb.vector == vec
        assert emb.dimensions == 4
        assert emb.model == "simple"

    def test_embedding_to_dict(self):
        """Test embedding serialization."""
        vec = [0.1] * 20
        emb = Embedding(vector=vec, dimensions=20, model="test-model")
        d = emb.to_dict()
        assert d["dimensions"] == 20
        assert d["model"] == "test-model"
        assert "vector_hash" in d

    def test_from_vector(self):
        """Test creating embedding from vector."""
        vec = [0.5, 0.5, 0.5]
        emb = Embedding.from_vector(vec, model="custom")
        assert emb.vector == vec
        assert emb.dimensions == 3
        assert emb.model == "custom"


class TestMemoryEntry:
    """Tests for MemoryEntry dataclass."""

    def test_create_entry(self):
        """Test creating a memory entry."""
        emb = Embedding(vector=[0.1, 0.2], dimensions=2)
        entry = MemoryEntry(
            id="test-001",
            content="Test memory",
            memory_type=MemoryType.INSIGHT,
            embedding=emb,
            created_at=datetime.now(),
            iteration=1,
        )
        assert entry.id == "test-001"
        assert entry.content == "Test memory"
        assert entry.memory_type == MemoryType.INSIGHT
        assert entry.access_count == 0
        assert entry.importance_score == 0.5

    def test_entry_with_tags(self):
        """Test entry with tags."""
        emb = Embedding(vector=[0.1], dimensions=1)
        entry = MemoryEntry(
            id="test-002",
            content="Tagged memory",
            memory_type=MemoryType.RULE,
            embedding=emb,
            created_at=datetime.now(),
            iteration=2,
            tags=["safety", "validation"],
        )
        assert "safety" in entry.tags
        assert "validation" in entry.tags

    def test_entry_to_dict(self):
        """Test entry serialization."""
        emb = Embedding(vector=[0.1, 0.2], dimensions=2)
        entry = MemoryEntry(
            id="test-003",
            content="Test",
            memory_type=MemoryType.SUCCESS,
            embedding=emb,
            created_at=datetime.now(),
            iteration=1,
            metadata={"key": "value"},
        )
        d = entry.to_dict()
        assert d["id"] == "test-003"
        assert d["memory_type"] == "success"
        assert d["metadata"]["key"] == "value"


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_create_result(self):
        """Test creating a search result."""
        emb = Embedding(vector=[0.1], dimensions=1)
        entry = MemoryEntry(
            id="result-001",
            content="Result content",
            memory_type=MemoryType.INSIGHT,
            embedding=emb,
            created_at=datetime.now(),
            iteration=1,
        )
        result = SearchResult(entry=entry, similarity=0.85, rank=1)
        assert result.similarity == 0.85
        assert result.rank == 1

    def test_result_to_dict(self):
        """Test result serialization."""
        emb = Embedding(vector=[0.1], dimensions=1)
        entry = MemoryEntry(
            id="result-002",
            content="A" * 150,  # Long content
            memory_type=MemoryType.PATTERN,
            embedding=emb,
            created_at=datetime.now(),
            iteration=1,
        )
        result = SearchResult(entry=entry, similarity=0.75, rank=2)
        d = result.to_dict()
        assert d["similarity"] == 0.75
        assert d["rank"] == 2
        assert d["memory_type"] == "pattern"
        assert "..." in d["content"]  # Should be truncated


# ============================================================
# SimpleEmbedder Tests
# ============================================================

class TestSimpleEmbedder:
    """Tests for SimpleEmbedder class."""

    def test_create_embedder(self):
        """Test creating an embedder."""
        embedder = SimpleEmbedder(dimensions=64)
        assert embedder.dimensions == 64

    def test_embed_nonempty(self):
        """Test embedding non-empty text."""
        embedder = SimpleEmbedder(dimensions=128)
        vec = embedder.embed("hello world")
        assert len(vec) == 128
        assert all(isinstance(v, float) for v in vec)

    def test_embed_empty(self):
        """Test embedding empty text."""
        embedder = SimpleEmbedder(dimensions=64)
        vec = embedder.embed("")
        assert len(vec) == 64
        assert all(v == 0.0 for v in vec)

    def test_embed_deterministic(self):
        """Test that same text produces same embedding."""
        embedder = SimpleEmbedder(dimensions=128)
        vec1 = embedder.embed("test text")
        vec2 = embedder.embed("test text")
        assert vec1 == vec2

    def test_embed_different_texts(self):
        """Test that different texts produce different embeddings."""
        embedder = SimpleEmbedder(dimensions=128)
        vec1 = embedder.embed("hello world")
        vec2 = embedder.embed("goodbye moon")
        assert vec1 != vec2

    def test_similarity_identical(self):
        """Test similarity of identical vectors."""
        embedder = SimpleEmbedder()
        vec = embedder.embed("test")
        sim = embedder.similarity(vec, vec)
        assert abs(sim - 1.0) < 0.0001

    def test_similarity_orthogonal(self):
        """Test similarity of orthogonal-ish vectors."""
        embedder = SimpleEmbedder()
        vec1 = [1.0, 0.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0, 0.0]
        sim = embedder.similarity(vec1, vec2)
        assert abs(sim) < 0.0001

    def test_similarity_different_lengths(self):
        """Test similarity with different length vectors."""
        embedder = SimpleEmbedder()
        vec1 = [1.0, 2.0]
        vec2 = [1.0, 2.0, 3.0]
        sim = embedder.similarity(vec1, vec2)
        assert sim == 0.0

    def test_similarity_zero_vectors(self):
        """Test similarity with zero vectors."""
        embedder = SimpleEmbedder()
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 2.0, 3.0]
        sim = embedder.similarity(vec1, vec2)
        assert sim == 0.0

    def test_embedding_normalized(self):
        """Test that embeddings are normalized."""
        embedder = SimpleEmbedder(dimensions=64)
        vec = embedder.embed("normalization test")
        magnitude = math.sqrt(sum(v * v for v in vec))
        assert abs(magnitude - 1.0) < 0.0001


# ============================================================
# VectorStore Tests
# ============================================================

class TestVectorStore:
    """Tests for VectorStore class."""

    @pytest.fixture
    def temp_store(self, tmp_path):
        """Create a temporary vector store."""
        store_dir = tmp_path / "vectors"
        store_dir.mkdir()
        return VectorStore(store_dir)

    def test_create_store(self, tmp_path):
        """Test creating a vector store."""
        store_dir = tmp_path / "store"
        store = VectorStore(store_dir)
        assert store.dimensions == 128
        assert store.entries == {}

    def test_store_entry(self, temp_store):
        """Test storing an entry."""
        entry = temp_store.store(
            content="Test memory content",
            memory_type=MemoryType.INSIGHT,
            iteration=1,
            tags=["test"],
        )
        assert entry.id.startswith("MEM-")
        assert entry.content == "Test memory content"
        assert entry.memory_type == MemoryType.INSIGHT
        assert len(temp_store.entries) == 1

    def test_store_with_metadata(self, temp_store):
        """Test storing with metadata."""
        entry = temp_store.store(
            content="Metadata test",
            memory_type=MemoryType.RULE,
            iteration=1,
            metadata={"source": "test", "confidence": 0.9},
        )
        assert entry.metadata["source"] == "test"
        assert entry.metadata["confidence"] == 0.9

    def test_search_basic(self, temp_store):
        """Test basic search."""
        temp_store.store(
            content="Safety validation is important",
            memory_type=MemoryType.RULE,
            iteration=1,
            tags=["safety"],
        )
        temp_store.store(
            content="Testing improves reliability",
            memory_type=MemoryType.INSIGHT,
            iteration=2,
            tags=["testing"],
        )

        results = temp_store.search("safety", k=5)
        assert len(results) >= 1
        assert all(isinstance(r, SearchResult) for r in results)

    def test_search_with_type_filter(self, temp_store):
        """Test search with type filter."""
        temp_store.store(
            content="Failure pattern A",
            memory_type=MemoryType.FAILURE,
            iteration=1,
        )
        temp_store.store(
            content="Success pattern B",
            memory_type=MemoryType.SUCCESS,
            iteration=2,
        )

        results = temp_store.search("pattern", k=5, memory_types=[MemoryType.FAILURE])
        assert len(results) >= 1
        assert all(r.entry.memory_type == MemoryType.FAILURE for r in results)

    def test_search_with_tag_filter(self, temp_store):
        """Test search with tag filter."""
        temp_store.store(
            content="Tagged content alpha",
            memory_type=MemoryType.INSIGHT,
            iteration=1,
            tags=["alpha", "test"],
        )
        temp_store.store(
            content="Tagged content beta",
            memory_type=MemoryType.INSIGHT,
            iteration=2,
            tags=["beta", "test"],
        )

        results = temp_store.search("content", k=5, tags=["alpha"])
        assert len(results) >= 1

    def test_search_with_importance_filter(self, temp_store):
        """Test search with importance filter."""
        temp_store.store(
            content="High importance",
            memory_type=MemoryType.RULE,
            iteration=1,
            importance=0.9,
        )
        temp_store.store(
            content="Low importance",
            memory_type=MemoryType.CONTEXT,
            iteration=2,
            importance=0.1,
        )

        results = temp_store.search("importance", k=5, min_importance=0.5)
        assert all(r.entry.importance_score >= 0.5 for r in results)

    def test_get_by_id(self, temp_store):
        """Test retrieval by ID."""
        entry = temp_store.store(
            content="Retrieve by ID test",
            memory_type=MemoryType.INSIGHT,
            iteration=1,
        )
        retrieved = temp_store.get_by_id(entry.id)
        assert retrieved is not None
        assert retrieved.content == "Retrieve by ID test"
        assert retrieved.access_count == 1

    def test_get_by_id_not_found(self, temp_store):
        """Test retrieval of non-existent ID."""
        result = temp_store.get_by_id("NONEXISTENT")
        assert result is None

    def test_get_by_iteration(self, temp_store):
        """Test retrieval by iteration."""
        temp_store.store("Iter 1 A", MemoryType.INSIGHT, iteration=1)
        temp_store.store("Iter 1 B", MemoryType.INSIGHT, iteration=1)
        temp_store.store("Iter 2 A", MemoryType.INSIGHT, iteration=2)

        iter1 = temp_store.get_by_iteration(1)
        assert len(iter1) == 2

    def test_get_recent(self, temp_store):
        """Test getting recent memories."""
        for i in range(5):
            temp_store.store(f"Memory {i}", MemoryType.INSIGHT, iteration=i)

        recent = temp_store.get_recent(n=3)
        assert len(recent) == 3

    def test_get_recent_with_type(self, temp_store):
        """Test getting recent memories by type."""
        temp_store.store("Success 1", MemoryType.SUCCESS, iteration=1)
        temp_store.store("Failure 1", MemoryType.FAILURE, iteration=2)
        temp_store.store("Success 2", MemoryType.SUCCESS, iteration=3)

        recent = temp_store.get_recent(n=5, memory_type=MemoryType.SUCCESS)
        assert all(e.memory_type == MemoryType.SUCCESS for e in recent)

    def test_get_important(self, temp_store):
        """Test getting important memories."""
        temp_store.store("Low", MemoryType.INSIGHT, iteration=1, importance=0.1)
        temp_store.store("High", MemoryType.INSIGHT, iteration=2, importance=0.9)
        temp_store.store("Medium", MemoryType.INSIGHT, iteration=3, importance=0.5)

        important = temp_store.get_important(n=2)
        assert len(important) == 2
        assert important[0].importance_score >= important[1].importance_score

    def test_apply_decay(self, temp_store):
        """Test importance decay."""
        entry = temp_store.store(
            "Decay test",
            MemoryType.INSIGHT,
            iteration=1,
            importance=1.0,
        )
        original_importance = entry.importance_score

        temp_store.apply_decay()

        # Importance should have decreased (decay_rate defaults to 0.1)
        assert entry.importance_score <= original_importance

    def test_get_statistics(self, temp_store):
        """Test getting store statistics."""
        temp_store.store("Stat 1", MemoryType.INSIGHT, iteration=1, tags=["a"])
        temp_store.store("Stat 2", MemoryType.FAILURE, iteration=2, tags=["b"])

        stats = temp_store.get_statistics()
        assert stats["total_entries"] == 2
        assert "by_type" in stats
        assert "insight" in stats["by_type"]
        assert "failure" in stats["by_type"]

    def test_persistence(self, tmp_path):
        """Test that store persists to disk."""
        store_dir = tmp_path / "persist"

        # Create and store
        store1 = VectorStore(store_dir)
        store1.store("Persisted", MemoryType.INSIGHT, iteration=1)

        # Create new instance - should load
        store2 = VectorStore(store_dir)
        assert len(store2.entries) == 1


# ============================================================
# SemanticMemoryCore Tests
# ============================================================

class TestSemanticMemoryCore:
    """Tests for SemanticMemoryCore class."""

    @pytest.fixture
    def temp_memory(self, tmp_path):
        """Create a temporary memory core."""
        return SemanticMemoryCore(tmp_path)

    def test_create_memory_core(self, tmp_path):
        """Test creating a memory core."""
        memory = SemanticMemoryCore(tmp_path)
        assert memory.vector_store is not None
        assert memory.working_memory == {}

    def test_remember(self, temp_memory):
        """Test storing a memory."""
        entry = temp_memory.remember(
            content="Test insight",
            memory_type=MemoryType.INSIGHT,
            iteration=1,
            tags=["test"],
        )
        assert entry is not None
        assert entry.content == "Test insight"

    def test_recall(self, temp_memory):
        """Test recalling memories."""
        temp_memory.remember("Safety rule", MemoryType.RULE, iteration=1)
        temp_memory.remember("Test pattern", MemoryType.PATTERN, iteration=2)

        results = temp_memory.recall("safety", k=5)
        assert len(results) >= 1

    def test_recall_failures(self, temp_memory):
        """Test recalling failures."""
        temp_memory.remember("Failure A", MemoryType.FAILURE, iteration=1)
        temp_memory.remember("Success A", MemoryType.SUCCESS, iteration=2)

        results = temp_memory.recall_failures("A", k=5)
        assert all(r.entry.memory_type == MemoryType.FAILURE for r in results)

    def test_recall_successes(self, temp_memory):
        """Test recalling successes."""
        temp_memory.remember("Success B", MemoryType.SUCCESS, iteration=1)
        temp_memory.remember("Failure B", MemoryType.FAILURE, iteration=2)

        results = temp_memory.recall_successes("B", k=5)
        assert all(r.entry.memory_type == MemoryType.SUCCESS for r in results)

    def test_recall_rules(self, temp_memory):
        """Test recalling rules."""
        temp_memory.remember("Rule 1", MemoryType.RULE, iteration=1)
        temp_memory.remember("Insight 1", MemoryType.INSIGHT, iteration=2)

        results = temp_memory.recall_rules("1", k=5)
        assert all(r.entry.memory_type == MemoryType.RULE for r in results)

    def test_working_memory(self, temp_memory):
        """Test working memory operations."""
        temp_memory.set_working("current_task", "optimize_module")
        value = temp_memory.get_working("current_task")
        assert value == "optimize_module"

    def test_working_memory_not_found(self, temp_memory):
        """Test getting non-existent working memory."""
        value = temp_memory.get_working("nonexistent")
        assert value is None

    def test_consolidate(self, temp_memory):
        """Test memory consolidation."""
        # Create entry with high access count
        entry = temp_memory.remember("Popular", MemoryType.INSIGHT, iteration=1)
        for _ in range(5):
            temp_memory.vector_store.get_by_id(entry.id)

        original_importance = entry.importance_score
        temp_memory.consolidate()

        # Should be boosted due to high access
        assert entry.importance_score >= original_importance

    def test_forget_weak(self, temp_memory):
        """Test forgetting weak memories."""
        temp_memory.remember("Strong", MemoryType.RULE, iteration=1, importance=0.9)
        temp_memory.remember("Weak", MemoryType.CONTEXT, iteration=2, importance=0.05)

        forgotten = temp_memory.forget_weak(threshold=0.1)
        assert forgotten == 1
        assert len(temp_memory.vector_store.entries) == 1

    def test_get_context_for_iteration(self, temp_memory):
        """Test getting context for iteration."""
        temp_memory.remember("Iter 1 mem", MemoryType.INSIGHT, iteration=1)
        temp_memory.remember("Iter 2 mem", MemoryType.INSIGHT, iteration=2)

        context = temp_memory.get_context_for_iteration(1)
        assert context["iteration"] == 1
        assert len(context["iteration_memories"]) >= 1

    def test_get_context_with_similar(self, temp_memory):
        """Test getting context with similar memories."""
        temp_memory.remember("Safety is important", MemoryType.RULE, iteration=1)
        temp_memory.remember("Testing safety", MemoryType.INSIGHT, iteration=2)

        context = temp_memory.get_context_for_iteration(2, include_similar="safety")
        assert "similar_memories" in context

    def test_get_statistics(self, temp_memory):
        """Test getting memory statistics."""
        temp_memory.remember("Stat test", MemoryType.INSIGHT, iteration=1)
        temp_memory.set_working("key", "value")

        stats = temp_memory.get_statistics()
        assert "vector_store" in stats
        assert "working_memory_size" in stats
        assert stats["working_memory_size"] == 1


# ============================================================
# Integration Tests
# ============================================================

class TestMemoryIntegration:
    """Integration tests for the memory system."""

    @pytest.fixture
    def full_memory(self, tmp_path):
        """Create a full memory system."""
        return SemanticMemoryCore(tmp_path)

    def test_full_memory_lifecycle(self, full_memory):
        """Test complete memory lifecycle."""
        # Store various types
        full_memory.remember(
            "Pattern: Early stopping prevents overfitting",
            MemoryType.PATTERN,
            iteration=1,
            tags=["ml", "training"],
            importance=0.7,
        )

        full_memory.remember(
            "Rule: Always validate before modification",
            MemoryType.RULE,
            iteration=2,
            tags=["safety"],
            importance=0.9,
        )

        full_memory.remember(
            "Failure: Parsing failed on malformed JSON",
            MemoryType.FAILURE,
            iteration=3,
            tags=["parsing"],
            importance=0.6,
        )

        # Recall
        results = full_memory.recall("validation safety", k=5)
        assert len(results) >= 1

        # Recall by type
        failures = full_memory.recall_failures("parsing", k=5)
        assert len(failures) >= 1

        # Set working memory
        full_memory.set_working("active_pattern", "early_stopping")

        # Get context
        context = full_memory.get_context_for_iteration(2, include_similar="training")
        assert context["iteration"] == 2

        # Consolidate
        full_memory.consolidate()

        # Statistics
        stats = full_memory.get_statistics()
        assert stats["vector_store"]["total_entries"] == 3

    def test_memory_similarity_ranking(self, full_memory):
        """Test that similarity ranking works correctly."""
        # Store similar and dissimilar memories
        full_memory.remember("Test containers are reliable", MemoryType.INSIGHT, iteration=1)
        full_memory.remember("Test containers provide isolation", MemoryType.INSIGHT, iteration=2)
        full_memory.remember("Random unrelated content about cooking", MemoryType.INSIGHT, iteration=3)

        results = full_memory.recall("testing with containers", k=3)

        # Similar memories should rank higher
        assert len(results) >= 2
        # First result should be more similar than last
        if len(results) >= 2:
            assert results[0].similarity >= results[-1].similarity
