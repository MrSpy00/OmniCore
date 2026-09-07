"""Unit tests for ASTSafetyFilter and DynamicCodeSynthesizer."""

from __future__ import annotations

import pytest

from core.code_synth import ASTSafetyFilter, DynamicCodeSynthesizer


def test_ast_safety_filter_safe_code():
    filter_instance = ASTSafetyFilter()
    safe_code = """
x = [1, 2, 3, 4, 5]
y = [i * 2 for i in x]
result = sum(y)
"""
    is_safe, violations = filter_instance.analyze(safe_code)
    assert is_safe is True
    assert len(violations) == 0


def test_ast_safety_filter_blocks_dangerous_imports():
    filter_instance = ASTSafetyFilter()

    for dangerous in ["import os", "import subprocess", "import sys", "from shutil import rmtree"]:
        is_safe, violations = filter_instance.analyze(dangerous)
        assert is_safe is False
        assert len(violations) > 0


def test_ast_safety_filter_blocks_eval_exec():
    filter_instance = ASTSafetyFilter()

    is_safe, violations = filter_instance.analyze("eval('1 + 1')")
    assert is_safe is False

    is_safe, violations = filter_instance.analyze("exec('x = 1')")
    assert is_safe is False


def test_ast_safety_filter_blocks_dunder_attacks():
    filter_instance = ASTSafetyFilter()

    is_safe, violations = filter_instance.analyze("x = ().__class__.__bases__[0].__subclasses__()")
    assert is_safe is False
    assert len(violations) > 0


def test_ast_safety_filter_syntax_error():
    filter_instance = ASTSafetyFilter()
    is_safe, violations = filter_instance.analyze("def broken(:")
    assert is_safe is False
    assert any("Sözdizimi" in v for v in violations)


def test_ast_safety_filter_code_too_large():
    filter_instance = ASTSafetyFilter()
    huge_code = "x = 1\n" * 2500
    is_safe, violations = filter_instance.analyze(huge_code)
    assert is_safe is False
    assert any("çok büyük" in v for v in violations)


def test_ast_safety_filter_dunder_literal():
    filter_instance = ASTSafetyFilter()
    is_safe, violations = filter_instance.analyze('attr = "__subclasses__"')
    assert is_safe is False
    assert any("dunder" in v.lower() for v in violations)


@pytest.mark.asyncio
async def test_code_extraction_helpers():
    from unittest.mock import AsyncMock, MagicMock

    from langchain_core.messages import AIMessage

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="```python\nresult = 42\n```"))
    synthesizer = DynamicCodeSynthesizer(llm=mock_llm)
    code = await synthesizer._generate_code("do something", {})
    assert code.strip() == "result = 42"


@pytest.mark.asyncio
async def test_dynamic_code_synthesizer_sandboxed_execution():
    synthesizer = DynamicCodeSynthesizer(llm=None)

    # Directly test sandboxed execution with safe code
    safe_code = "result = {'computed': 10 * 42}"
    exec_result = synthesizer._execute_sandboxed(safe_code, {})
    assert exec_result == {"computed": 420}


@pytest.mark.asyncio
async def test_dynamic_code_synthesizer_no_llm_handling():
    synthesizer = DynamicCodeSynthesizer(llm=None)
    res = await synthesizer.synthesize_and_execute("compute Fibonacci numbers")
    assert res["success"] is False
    assert "Kod üretilemedi" in res["error"]


@pytest.mark.asyncio
async def test_dynamic_code_synthesizer_mocked_llm_flow():
    from unittest.mock import AsyncMock, MagicMock

    from langchain_core.messages import AIMessage

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="```python\nresult = {'sum': sum([1, 2, 3])}\n```"))

    synthesizer = DynamicCodeSynthesizer(llm=mock_llm)
    res = await synthesizer.synthesize_and_execute("calculate sum of 1, 2, 3")
    assert res["success"] is True
    assert res["result"] == {"sum": 6}


@pytest.mark.asyncio
async def test_dynamic_code_synthesizer_unsafe_generation_blocked():
    from unittest.mock import AsyncMock, MagicMock

    from langchain_core.messages import AIMessage

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=AIMessage(content="```python\nimport os\nos.system('dir')\nresult = 0\n```")
    )

    synthesizer = DynamicCodeSynthesizer(llm=mock_llm)
    res = await synthesizer.synthesize_and_execute("list directory unsafely")
    assert res["success"] is False
    assert "güvenlik" in res["error"].lower()
