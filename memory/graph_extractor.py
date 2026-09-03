"""Graf Varlık-İlişki Çıkarma Motoru — LLM gerektirmez, deterministik regex desenleri.

Sohbet metinlerinden varlık-ilişki üçlülerini (Subject-Predicate-Object) çıkarır
ve GraphMemory'ye otomatik olarak ekler.
"""

from __future__ import annotations

import re

# ─── Türkçe ve İngilizce İlişki Desenleri ────────────────────────────────────────

_RELATION_PATTERNS_EN: list[tuple[str, str]] = [
    (r"\b(\w+)\s+uses?\s+(\w+)", "uses"),
    (r"\b(\w+)\s+is\s+(?:a|an)\s+(\w+)", "is_a"),
    (r"\b(\w+)\s+has\s+(\w+)", "has"),
    (r"\b(\w+)\s+works?\s+with\s+(\w+)", "works_with"),
    (r"\b(\w+)\s+integrates?\s+with\s+(\w+)", "integrates_with"),
    (r"\b(\w+)\s+supports?\s+(\w+)", "supports"),
    (r"\b(\w+)\s+requires?\s+(\w+)", "requires"),
    (r"\b(\w+)\s+depends?\s+on\s+(\w+)", "depends_on"),
    (r"\b(\w+)\s+implements?\s+(\w+)", "implements"),
    (r"\b(\w+)\s+extends?\s+(\w+)", "extends"),
    (r"\b(\w+)\s+contains?\s+(\w+)", "contains"),
]

_RELATION_PATTERNS_TR: list[tuple[str, str]] = [
    (r"\b(\w+)\s+kullan[ıi](?:yor|r)", "kullanıyor"),
    (r"\b(\w+)\s+bir\s+(\w+)\s+dir", "is_a"),
    (r"\b(\w+)\s+sahip\s+(?:dir|oldingi)", "has"),
    (r"\b(\w+)\s+ile\s+(\w+)\s+çalış[ıi](?:yor|r)", "works_with"),
    (r"\b(\w+)\s+entegre\s+(?:dir|olduğu)", "integrates_with"),
    (r"\b(\w+)\s+destekl[ıi](?:yor|r)", "supports"),
    (r"\b(\w+)\s+ihtiyaç\s+(?:duyar|duymaktadır)", "requires"),
    (r"\b(\w+)\s+bağıml[ıi](?:dır|olduğu)", "depends_on"),
]

# ─── Önemli Varlık Tanımlayıcıları ──────────────────────────────────────────────

_TECH_TERMS = re.compile(
    r"\b(?:Python|JavaScript|TypeScript|Java|C\+\+|Rust|Go|Ruby|PHP|Swift|Kotlin|"
    r"Docker|Kubernetes|Redis|PostgreSQL|MySQL|MongoDB|SQLite|ChromaDB|Neo4j|"
    r"FastAPI|Django|Flask|Express|React|Vue|Angular|Next\.js|"
    r"Playwright|Selenium|Puppeteer|"
    r"Gemini|GPT|Claude|Llama|Mistral|DeepSeek|Groq|Ollama|"
    r"OpenAI|Anthropic|Google|Meta|Microsoft|GitHub|GitLab|"
    r"Windows|Linux|macOS|Ubuntu|Docker|AWS|Azure|GCP|"
    r"LangChain|LangGraph|CrewAI|AutoGen|"
    r"OmniCore|CognitiveRouter|GraphMemory|ChromaDB)\b",
    re.IGNORECASE,
)

_FILE_PATH = re.compile(r"[A-Za-z]:\\[\w\\.]+|~/[\w/\\.]+|\./[\w/\\.]+")

_URL_PATTERN = re.compile(r"https?://[\w./\-?&=%#@]+")


def _is_technical_term(text: str) -> bool:
    """Metnin teknik bir terim olup olmadığını kontrol eder."""
    return bool(_TECH_TERMS.match(text.strip()))


def _extract_technical_entities(text: str) -> set[str]:
    """Metinden teknik terimleri çıkarır."""
    return set(_TECH_TERMS.findall(text))


def _extract_paths_and_urls(text: str) -> list[dict[str, str]]:
    """Metinden dosya yollarını ve URL'leri çıkarır."""
    results = []
    for match in _FILE_PATH.finditer(text):
        results.append({"type": "file_path", "value": match.group()})
    for match in _URL_PATTERN.finditer(text):
        results.append({"type": "url", "value": match.group()})
    return results


def extract_entities_and_relations(text: str) -> list[dict[str, str]]:
    """Regex desenleri ile varlık-ilişki üçlülerini çıkarır.

    Returns:
        [{subject, predicate, object}] formatında üçlü listesi.
    """
    triples: list[dict[str, str]] = []
    seen = set()

    for pattern, predicate in _RELATION_PATTERNS_EN:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            subj = match.group(1)
            obj = match.group(2)
            key = (subj.lower(), predicate, obj.lower())
            if key not in seen:
                seen.add(key)
                triples.append({"subject": subj, "predicate": predicate, "object": obj})

    for pattern, predicate in _RELATION_PATTERNS_TR:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            subj = match.group(1)
            obj = match.group(2)
            key = (subj.lower(), predicate, obj.lower())
            if key not in seen:
                seen.add(key)
                triples.append({"subject": subj, "predicate": predicate, "object": obj})

    tech_entities = _extract_technical_entities(text)
    for entity in tech_entities:
        key = (entity.lower(), "mentioned_in", "conversation")
        if key not in seen:
            seen.add(key)
            triples.append({
                "subject": entity,
                "predicate": "mentioned_in",
                "object": "conversation",
            })

    return triples


def extract_from_conversation(user_msg: str, assistant_reply: str) -> list[dict[str, str]]:
    """Sohbet çiftinden (kullanıcı + asistan yanıtı) üçlüleri çıkarır."""
    combined = f"{user_msg}\n{assistant_reply}"
    return extract_entities_and_relations(combined)
