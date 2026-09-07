"""Unit tests for GraphMemory and Graph Extractor."""

from __future__ import annotations

import pytest

from memory.graph_extractor import (
    _extract_paths_and_urls,
    _extract_technical_entities,
    _is_technical_term,
    extract_entities_and_relations,
    extract_from_conversation,
)
from memory.graph_memory import GraphMemory


class TestGraphExtractor:
    """Test regex entity and relation extraction patterns."""

    def test_technical_terms(self):
        assert _is_technical_term("Python") is True
        assert _is_technical_term("ChromaDB") is True
        assert _is_technical_term("random_banana") is False

        entities = _extract_technical_entities("We are building OmniCore using FastAPI and Docker.")
        assert "OmniCore" in entities
        assert "FastAPI" in entities
        assert "Docker" in entities

    def test_extract_paths_and_urls(self):
        sample = "Check config at C:\\OmniCore\\settings.json and visit https://github.com/test/repo"
        extracted = _extract_paths_and_urls(sample)
        types = [x["type"] for x in extracted]
        assert "file_path" in types
        assert "url" in types

    def test_relation_patterns_english(self):
        text = "OmniCore uses ChromaDB. FastAPI works with Python."
        triples = extract_entities_and_relations(text)
        assert any(t["predicate"] == "uses" for t in triples)
        assert any(t["predicate"] == "works_with" for t in triples)

    def test_relation_patterns_turkish(self):
        text = "OmniCore ChromaDB kullanıyor. Robot insan ile çalışır."
        triples = extract_entities_and_relations(text)
        assert any(t["predicate"] == "kullanıyor" for t in triples)
        assert any(t["predicate"] == "works_with" for t in triples)

    def test_extract_from_conversation(self):
        triples = extract_from_conversation(
            user_msg="OmniCore supports SQLite.",
            assistant_reply="Yes, OmniCore integrates with SQLite seamlessly.",
        )
        assert len(triples) >= 1
        assert any(t["subject"] == "OmniCore" for t in triples)


class TestGraphMemory:
    """Test GraphMemory SQLite storage, querying, prompt formatting, and export."""

    @pytest.fixture()
    async def graph_db(self, tmp_path):
        db_path = tmp_path / "test_graph.db"
        gm = GraphMemory(db_path=db_path)
        await gm.initialize()
        yield gm
        await gm.close()

    @pytest.mark.asyncio
    async def test_add_and_query_relations(self, graph_db):
        await graph_db.add_relation("OmniCore", "uses", "ChromaDB", 0.95)
        await graph_db.add_relation("OmniCore", "built_with", "Python", 1.0)

        rels = await graph_db.query_relations("OmniCore")
        assert len(rels) == 2
        predicates = [r["predicate"] for r in rels]
        assert "uses" in predicates
        assert "built_with" in predicates

        # Reverse lookup by object
        rev_rels = await graph_db.query_relations("ChromaDB")
        assert len(rev_rels) == 1
        assert rev_rels[0]["subject"] == "OmniCore"

    @pytest.mark.asyncio
    async def test_format_graph_for_prompt(self, graph_db):
        await graph_db.add_relation("OmniCore", "accelerates", "Workflows", 1.0)
        formatted = await graph_db.format_graph_for_prompt("How OmniCore accelerates things")
        assert "KNOWLEDGE GRAPH RELATIONS" in formatted
        assert "(OmniCore) --[accelerates]--> (Workflows)" in formatted

    @pytest.mark.asyncio
    async def test_format_graph_for_prompt_no_match(self, graph_db):
        formatted = await graph_db.format_graph_for_prompt("unrelated query")
        assert formatted == ""

    @pytest.mark.asyncio
    async def test_export_graph_data(self, graph_db):
        await graph_db.add_relation("User", "owns", "Computer", 1.0)
        data = await graph_db.export_graph_data(limit=50)

        assert data["count"] == 1
        node_ids = [n["id"] for n in data["nodes"]]
        assert "User" in node_ids
        assert "Computer" in node_ids
        assert data["edges"][0]["source"] == "User"
        assert data["edges"][0]["target"] == "Computer"

    @pytest.mark.asyncio
    async def test_extract_and_store_from_text(self, graph_db):
        text = "OmniCore supports SQLite and uses Redis."
        stored_count = await graph_db.extract_and_store_from_text(text)
        assert stored_count >= 2

        rels = await graph_db.query_relations("OmniCore")
        assert len(rels) >= 2
