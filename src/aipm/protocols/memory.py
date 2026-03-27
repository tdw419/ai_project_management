"""
Long-term Memory & Knowledge Retention

SemanticMemoryCore with VectorStore for persistent learning
across recursive iterations using semantic embeddings.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from enum import Enum
import json
import math
import hashlib
from collections import defaultdict


class MemoryType(Enum):
    INSIGHT = "insight"
    PATTERN = "pattern"
    FAILURE = "failure"
    SUCCESS = "success"
    RULE = "rule"
    CONTEXT = "context"


@dataclass
class Embedding:
    """A semantic embedding vector."""
    vector: list[float]
    dimensions: int
    model: str = "simple"  # In production: "text-embedding-3-small"

    def to_dict(self) -> dict:
        return {
            "vector": self.vector[:10] + ["..."],  # Truncate for storage
            "dimensions": self.dimensions,
            "model": self.model,
            "vector_hash": hashlib.md5(str(self.vector).encode()).hexdigest()[:8],
        }

    @classmethod
    def from_vector(cls, vec: list[float], model: str = "simple") -> "Embedding":
        return cls(vector=vec, dimensions=len(vec), model=model)


@dataclass
class MemoryEntry:
    """A single memory entry in the vector store."""
    id: str
    content: str
    memory_type: MemoryType
    embedding: Embedding
    created_at: datetime
    iteration: int
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    importance_score: float = 0.5
    decay_rate: float = 0.1  # How fast importance decays

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "embedding": self.embedding.to_dict(),
            "created_at": self.created_at.isoformat(),
            "iteration": self.iteration,
            "tags": self.tags,
            "metadata": self.metadata,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "importance_score": self.importance_score,
            "decay_rate": self.decay_rate,
        }


@dataclass
class SearchResult:
    """Result of a similarity search."""
    entry: MemoryEntry
    similarity: float
    rank: int

    def to_dict(self) -> dict:
        return {
            "id": self.entry.id,
            "content": self.entry.content[:100] + "...",
            "similarity": self.similarity,
            "rank": self.rank,
            "memory_type": self.entry.memory_type.value,
        }


class SimpleEmbedder:
    """
    Simple embedding generator without external dependencies.

    In production, this would use:
    - OpenAI text-embedding-3-small
    - Anthropic's embeddings
    - Local sentence-transformers

    This implementation uses a hash-based approach for demonstration.
    """

    def __init__(self, dimensions: int = 128):
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        """
        Generate embedding for text.

        Uses a simple approach:
        1. Normalize and tokenize text
        2. Generate deterministic hash-based vectors
        3. Normalize to unit length
        """
        # Tokenize
        words = text.lower().split()
        if not words:
            return [0.0] * self.dimensions

        # Initialize vector
        vec = [0.0] * self.dimensions

        # Hash each word and accumulate
        for i, word in enumerate(words):
            word_hash = int(hashlib.md5(word.encode()).hexdigest(), 16)

            # Spread across dimensions
            for d in range(self.dimensions):
                # Deterministic but varied per word and dimension
                seed = (word_hash + d * 31 + i * 17) % (2**31)
                vec[d] += math.sin(seed) * (1.0 / (i + 1))

        # Normalize to unit length
        magnitude = math.sqrt(sum(v * v for v in vec))
        if magnitude > 0:
            vec = [v / magnitude for v in vec]

        return vec

    def similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = math.sqrt(sum(a * a for a in vec1))
        mag2 = math.sqrt(sum(b * b for b in vec2))

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)


class VectorStore:
    """
    Vector store for semantic memory.

    Schema:
    - entries: Dict[id, MemoryEntry]
    - type_index: Dict[MemoryType, List[id]]
    - tag_index: Dict[tag, List[id]]
    - iteration_index: Dict[iteration, List[id]]

    Supports:
    - Similarity search
    - Filtered search by type/tags
    - Temporal search by iteration
    - Importance-based retrieval
    """

    def __init__(self, state_dir: Path, dimensions: int = 128):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.dimensions = dimensions

        self.embedder = SimpleEmbedder(dimensions)
        self.entries: dict[str, MemoryEntry] = {}

        # Indexes for efficient retrieval
        self.type_index: dict[MemoryType, list[str]] = defaultdict(list)
        self.tag_index: dict[str, list[str]] = defaultdict(list)
        self.iteration_index: dict[int, list[str]] = defaultdict(list)

        self._load()

    def _load(self):
        """Load persisted store."""
        store_file = self.state_dir / "vector_store.json"
        if store_file.exists():
            with open(store_file) as f:
                data = json.load(f)

            for entry_data in data.get("entries", []):
                entry = MemoryEntry(
                    id=entry_data["id"],
                    content=entry_data["content"],
                    memory_type=MemoryType(entry_data["memory_type"]),
                    embedding=Embedding(
                        vector=[],  # Re-compute on demand
                        dimensions=self.dimensions,
                    ),
                    created_at=datetime.fromisoformat(entry_data["created_at"]),
                    iteration=entry_data["iteration"],
                    tags=entry_data.get("tags", []),
                    metadata=entry_data.get("metadata", {}),
                    access_count=entry_data.get("access_count", 0),
                    importance_score=entry_data.get("importance_score", 0.5),
                    decay_rate=entry_data.get("decay_rate", 0.1),
                )

                self.entries[entry.id] = entry
                self._index_entry(entry)

    def _save(self):
        """Persist store."""
        store_file = self.state_dir / "vector_store.json"

        # Store without full vectors (re-compute on load)
        entries_data = []
        for entry in self.entries.values():
            data = entry.to_dict()
            del data["embedding"]["vector"]  # Don't store full vector
            entries_data.append(data)

        with open(store_file, "w") as f:
            json.dump({
                "entries": entries_data,
                "stats": {
                    "total_entries": len(self.entries),
                    "dimensions": self.dimensions,
                    "updated_at": datetime.now().isoformat(),
                }
            }, f, indent=2)

    def _index_entry(self, entry: MemoryEntry):
        """Add entry to indexes."""
        self.type_index[entry.memory_type].append(entry.id)

        for tag in entry.tags:
            self.tag_index[tag].append(entry.id)

        self.iteration_index[entry.iteration].append(entry.id)

    def store(self, content: str, memory_type: MemoryType,
              iteration: int, tags: list[str] = None,
              metadata: dict = None, importance: float = 0.5) -> MemoryEntry:
        """
        Store a new memory entry.

        Args:
            content: The content to remember
            memory_type: Type of memory
            iteration: Current iteration number
            tags: Optional tags for retrieval
            metadata: Optional metadata
            importance: Initial importance score

        Returns:
            The created MemoryEntry
        """
        # Generate ID
        timestamp = datetime.now()
        id_hash = hashlib.md5(f"{content}{timestamp}".encode()).hexdigest()[:8]
        entry_id = f"MEM-{timestamp.strftime('%Y%m%d%H%M%S')}-{id_hash}"

        # Generate embedding
        embedding = self.embedder.embed(content)
        emb_obj = Embedding.from_vector(embedding)

        # Create entry
        entry = MemoryEntry(
            id=entry_id,
            content=content,
            memory_type=memory_type,
            embedding=emb_obj,
            created_at=timestamp,
            iteration=iteration,
            tags=tags or [],
            metadata=metadata or {},
            importance_score=importance,
        )

        # Store and index
        self.entries[entry_id] = entry
        self._index_entry(entry)
        self._save()

        return entry

    def search(self, query: str, k: int = 10,
               memory_types: list[MemoryType] = None,
               tags: list[str] = None,
               min_importance: float = 0.0) -> list[SearchResult]:
        """
        Search for similar memories.

        Args:
            query: Query text
            k: Number of results
            memory_types: Filter by memory types
            tags: Filter by tags (any match)
            min_importance: Minimum importance threshold

        Returns:
            List of SearchResult ranked by similarity
        """
        # Generate query embedding
        query_embedding = self.embedder.embed(query)

        # Get candidate IDs
        candidates = set(self.entries.keys())

        # Filter by memory type
        if memory_types:
            type_ids = set()
            for mt in memory_types:
                type_ids.update(self.type_index.get(mt, []))
            candidates &= type_ids

        # Filter by tags
        if tags:
            tag_ids = set()
            for tag in tags:
                tag_ids.update(self.tag_index.get(tag, []))
            candidates &= tag_ids

        # Calculate similarities
        results = []
        for entry_id in candidates:
            entry = self.entries[entry_id]

            # Filter by importance
            if entry.importance_score < min_importance:
                continue

            # Re-compute embedding for comparison
            entry_embedding = self.embedder.embed(entry.content)
            similarity = self.embedder.similarity(query_embedding, entry_embedding)

            results.append(SearchResult(
                entry=entry,
                similarity=similarity,
                rank=0,  # Set after sorting
            ))

        # Sort by similarity
        results.sort(key=lambda r: r.similarity, reverse=True)

        # Set ranks and update access
        for i, result in enumerate(results[:k]):
            result.rank = i + 1
            result.entry.access_count += 1
            result.entry.last_accessed = datetime.now()

        self._save()

        return results[:k]

    def get_by_id(self, entry_id: str) -> Optional[MemoryEntry]:
        """Retrieve entry by ID."""
        entry = self.entries.get(entry_id)
        if entry:
            entry.access_count += 1
            entry.last_accessed = datetime.now()
            self._save()
        return entry

    def get_by_iteration(self, iteration: int) -> list[MemoryEntry]:
        """Get all memories from a specific iteration."""
        ids = self.iteration_index.get(iteration, [])
        return [self.entries[id] for id in ids if id in self.entries]

    def get_recent(self, n: int = 10, memory_type: MemoryType = None) -> list[MemoryEntry]:
        """Get n most recent memories."""
        entries = list(self.entries.values())

        if memory_type:
            entries = [e for e in entries if e.memory_type == memory_type]

        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries[:n]

    def get_important(self, n: int = 10) -> list[MemoryEntry]:
        """Get n most important memories."""
        entries = list(self.entries.values())
        entries.sort(key=lambda e: e.importance_score, reverse=True)
        return entries[:n]

    def apply_decay(self):
        """Apply importance decay to all entries."""
        now = datetime.now()

        for entry in self.entries.values():
            age_hours = (now - entry.created_at).total_seconds() / 3600
            decay = math.exp(-entry.decay_rate * age_hours / 24)  # Decay per day
            entry.importance_score *= decay

        self._save()

    def get_statistics(self) -> dict:
        """Get store statistics."""
        type_counts = defaultdict(int)
        for entry in self.entries.values():
            type_counts[entry.memory_type.value] += 1

        avg_importance = (
            sum(e.importance_score for e in self.entries.values()) / len(self.entries)
            if self.entries else 0.0
        )

        return {
            "total_entries": len(self.entries),
            "by_type": dict(type_counts),
            "by_tag": {k: len(v) for k, v in self.tag_index.items()},
            "iteration_range": (
                min(self.iteration_index.keys()),
                max(self.iteration_index.keys())
            ) if self.iteration_index else (0, 0),
            "avg_importance": avg_importance,
            "dimensions": self.dimensions,
        }


class SemanticMemoryCore:
    """
    High-level memory management for persistent learning.

    Integrates with:
    - InsightsDatabase (stores insights as memories)
    - MetaPromptEngine (retrieves relevant learnings)
    - RewardFunction (uses memory for action valuation)
    """

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.vector_store = VectorStore(state_dir / "vectors")

        # Working memory (short-term, high-importance)
        self.working_memory: dict[str, Any] = {}

        # Memory consolidation threshold
        self.consolidation_threshold = 3  # Access count to consolidate

    def remember(self, content: str, memory_type: MemoryType,
                 iteration: int, tags: list[str] = None,
                 metadata: dict = None, importance: float = 0.5) -> MemoryEntry:
        """
        Store a new memory.

        Args:
            content: What to remember
            memory_type: Type of memory
            iteration: Current iteration
            tags: Retrieval tags
            metadata: Additional data
            importance: How important (0-1)

        Returns:
            The created memory entry
        """
        return self.vector_store.store(
            content=content,
            memory_type=memory_type,
            iteration=iteration,
            tags=tags or [],
            metadata=metadata,
            importance=importance,
        )

    def recall(self, query: str, k: int = 5,
               memory_types: list[MemoryType] = None) -> list[SearchResult]:
        """
        Recall relevant memories.

        Args:
            query: What to recall
            k: Number of memories
            memory_types: Filter by types

        Returns:
            Ranked search results
        """
        return self.vector_store.search(
            query=query,
            k=k,
            memory_types=memory_types,
        )

    def recall_failures(self, context: str, k: int = 5) -> list[SearchResult]:
        """Recall relevant failure patterns."""
        return self.recall(
            query=context,
            k=k,
            memory_types=[MemoryType.FAILURE],
        )

    def recall_successes(self, context: str, k: int = 5) -> list[SearchResult]:
        """Recall relevant success patterns."""
        return self.recall(
            query=context,
            k=k,
            memory_types=[MemoryType.SUCCESS],
        )

    def recall_rules(self, context: str, k: int = 5) -> list[SearchResult]:
        """Recall relevant learned rules."""
        return self.recall(
            query=context,
            k=k,
            memory_types=[MemoryType.RULE],
        )

    def set_working(self, key: str, value: Any):
        """Set working memory (short-term, high-priority)."""
        self.working_memory[key] = {
            "value": value,
            "set_at": datetime.now().isoformat(),
        }

    def get_working(self, key: str) -> Optional[Any]:
        """Get from working memory."""
        data = self.working_memory.get(key)
        return data["value"] if data else None

    def consolidate(self):
        """
        Consolidate frequently accessed memories.

        Memories accessed >= consolidation_threshold get boosted importance.
        """
        for entry in self.vector_store.entries.values():
            if entry.access_count >= self.consolidation_threshold:
                entry.importance_score = min(1.0, entry.importance_score * 1.2)
                entry.decay_rate *= 0.8  # Decay slower

        self.vector_store._save()

    def forget_weak(self, threshold: float = 0.1):
        """
        Forget memories below importance threshold.

        Args:
            threshold: Minimum importance to keep
        """
        to_forget = [
            id for id, entry in self.vector_store.entries.items()
            if entry.importance_score < threshold
        ]

        for entry_id in to_forget:
            entry = self.vector_store.entries[entry_id]

            # Remove from indexes
            if entry_id in self.vector_store.type_index[entry.memory_type]:
                self.vector_store.type_index[entry.memory_type].remove(entry_id)

            for tag in entry.tags:
                if entry_id in self.vector_store.tag_index[tag]:
                    self.vector_store.tag_index[tag].remove(entry_id)

            if entry_id in self.vector_store.iteration_index[entry.iteration]:
                self.vector_store.iteration_index[entry.iteration].remove(entry_id)

            del self.vector_store.entries[entry_id]

        self.vector_store._save()

        return len(to_forget)

    def get_context_for_iteration(self, iteration: int,
                                    include_similar: str = None) -> dict:
        """
        Get full context for an iteration.

        Args:
            iteration: Target iteration
            include_similar: Optional query for similar memories

        Returns:
            Dict with iteration memories and similar ones
        """
        context = {
            "iteration": iteration,
            "iteration_memories": [
                {"content": m.content, "type": m.memory_type.value}
                for m in self.vector_store.get_by_iteration(iteration)
            ],
        }

        if include_similar:
            similar = self.recall(include_similar, k=5)
            context["similar_memories"] = [r.to_dict() for r in similar]

        return context

    def get_statistics(self) -> dict:
        """Get memory statistics."""
        return {
            "vector_store": self.vector_store.get_statistics(),
            "working_memory_size": len(self.working_memory),
        }


# === USAGE EXAMPLE ===

if __name__ == "__main__":
    from pathlib import Path

    state_dir = Path(".ouroboros/memory")
    state_dir.mkdir(parents=True, exist_ok=True)

    memory = SemanticMemoryCore(state_dir)

    print("=" * 60)
    print("SEMANTIC MEMORY CORE TEST")
    print("=" * 60)

    # Store some memories
    print("\nStoring memories...")

    memory.remember(
        content="Mocking database in tests is fragile - prefer test containers",
        memory_type=MemoryType.INSIGHT,
        iteration=1,
        tags=["testing", "reliability"],
        importance=0.7,
    )

    memory.remember(
        content="Safety validation must check protected files before modification",
        memory_type=MemoryType.RULE,
        iteration=2,
        tags=["safety", "validation"],
        importance=0.9,
    )

    memory.remember(
        content="Failed to parse LLM response - added ASCII box character filtering",
        memory_type=MemoryType.FAILURE,
        iteration=3,
        tags=["parsing", "llm"],
        importance=0.6,
    )

    memory.remember(
        content="Generator/Critic architecture improved convergence by 40%",
        memory_type=MemoryType.SUCCESS,
        iteration=4,
        tags=["architecture", "convergence"],
        importance=0.8,
    )

    memory.remember(
        content="Subprocess isolation provides safe code execution",
        memory_type=MemoryType.PATTERN,
        iteration=5,
        tags=["safety", "execution"],
        importance=0.7,
    )

    # Test recall
    print("\nRecall: 'safety validation'")
    results = memory.recall("safety validation", k=3)
    for r in results:
        print(f"  [{r.similarity:.2f}] {r.entry.content[:60]}...")

    print("\nRecall: 'test improvements'")
    results = memory.recall("test improvements", k=3)
    for r in results:
        print(f"  [{r.similarity:.2f}] {r.entry.content[:60]}...")

    print("\nRecall failures: 'parsing'")
    results = memory.recall_failures("parsing", k=3)
    for r in results:
        print(f"  [{r.similarity:.2f}] {r.entry.content[:60]}...")

    # Statistics
    print("\n" + "=" * 60)
    print("STATISTICS")
    print(json.dumps(memory.get_statistics(), indent=2))
