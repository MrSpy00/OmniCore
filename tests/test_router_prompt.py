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

    assert (
        "CRITICAL MANDATE: YOU ARE A SYSTEM KERNEL. YOU MUST NEVER HALLUCINATE OR SIMULATE DATA."
        in prompt
    )
    assert "If the user asks what is on the desktop, YOU MUST EXECUTE os_list_dir." in prompt
    assert (
        "If the user asks you to write code, YOU MUST EXECUTE os_write_file or dev_execute_python_code."
        in prompt
    )
    assert (
        "NEVER write the code block in the chat response. IF YOU DO NOT USE A TOOL, YOU FAIL."
        in prompt
    )
