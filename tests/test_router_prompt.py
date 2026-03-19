from __future__ import annotations

from typing import Any, cast

from core.router import CognitiveRouter


def test_system_prompt_includes_hallucination_lockdown():
    router = CognitiveRouter.__new__(CognitiveRouter)
    router._registry = cast(
        Any,
        type(
            "Registry",
            (),
            {
                "list_tools": lambda self: [
                    {"name": "os_list_dir", "description": "list dir", "destructive": "False"}
                ]
            },
        )(),
    )

    prompt = router._build_system_prompt("memory")

    assert "KRİTİK ZORUNLULUK: SEN OMNICORE ADINDA" in prompt
    assert "ASLA İNGİLİZCE KONUŞMA" in prompt
    assert "KOTA HATASI (429)" in prompt
    assert "(FOREGROUND)" in prompt
