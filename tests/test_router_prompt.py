from __future__ import annotations

from core.router import CognitiveRouter


def test_system_prompt_includes_hallucination_lockdown():
    router = CognitiveRouter.__new__(CognitiveRouter)
    router._registry = type(
        "Registry",
        (),
        {
            "list_tools": lambda self: [
                {"name": "os_list_dir", "description": "list dir", "destructive": "False"}
            ]
        },
    )()

    prompt = router._build_system_prompt("memory")

    # V18: System prompt is now fully in Turkish.
    assert "SEN BİR SİSTEM ÇEKİRDEĞİSİN" in prompt
    assert "ASLA HALÜSİNASYON YAPMA" in prompt
    assert "os_list_dir ÇALIŞTIRMALISIN" in prompt
    assert "HER ZAMAN TÜRKÇE YANIT VER" in prompt
    assert "KURAL 11:" in prompt
    assert "ARAÇ KULLANMAZSAN BAŞARISIZ OLURSUN" in prompt
