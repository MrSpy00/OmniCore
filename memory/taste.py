"""OmniCore Taste Engine — Kullanıcı tercihlerini öğrenen ve uygulayan akıllı sistem.

Kullanıcı:
- Geçmişte ne istediğini, nasıl istediğini
- Hangi dili kullandığını, hangi tarzda cevap beklediğini
- Hangi tool'ları tercih ettiğini, hangilerini beğendiğini
- Provider/model tercihlerini
- Davranış kalıplarını

Bu bilgiler SQLite'a kaydedilir ve her istekte system prompt'a enjekte edilir.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from config.logging import get_logger

logger = get_logger(__name__)

# Tüm kategoriler
CATEGORIES = {
    "language": "Kullanıcının tercih ettiği dil ve karakter desteği",
    "response_style": "Cevap formatı ve uzunluk tercihleri",
    "ui_preferences": "Arayüz görünümü ve etkileşim tercihleri",
    "tool_preferences": "Sık kullanılan ve tercih edilen araçlar",
    "provider_preferences": "LLM provider ve model tercihleri",
    "behavior": "Otonom davranış tercihleri (onay, izin, otomatik işlem)",
    "content": "İçerik tercihleri (konular, format, ton)",
    "corrections": "Kullanıcı düzeltmeleri ve geri bildirimleri",
}


class TasteEngine:
    """Kullanıcı tercihlerini öğrenen, saklayan ve uygulayan motor."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            db_path = Path("./data/omnicore.db")
        self._db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Taste tablosunu oluştur."""
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS taste (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                source TEXT DEFAULT 'auto',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(category, key)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS taste_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                taste_id INTEGER,
                feedback_type TEXT NOT NULL,
                context TEXT,
                created_at REAL NOT NULL,
                FOREIGN KEY (taste_id) REFERENCES taste(id)
            )
        """)
        conn.commit()
        conn.close()

    def learn(self, category: str, key: str, value: str, confidence: float = 0.6, source: str = "auto") -> None:
        """Yeni bir tercih öğren veya mevcut olanı güncelle."""
        now = time.time()
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute("""
                INSERT INTO taste (category, key, value, confidence, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(category, key) DO UPDATE SET
                    value = excluded.value,
                    confidence = MAX(confidence, excluded.confidence),
                    source = excluded.source,
                    updated_at = excluded.updated_at
            """, (category, key, value, confidence, source, now, now))
            conn.commit()
            logger.info("taste.learned", category=category, key=key, value=value, confidence=confidence)
        finally:
            conn.close()

    def get(self, category: str, key: str) -> str | None:
        """Belirli bir tercihi al."""
        conn = sqlite3.connect(str(self._db_path))
        try:
            row = conn.execute(
                "SELECT value FROM taste WHERE category = ? AND key = ?",
                (category, key)
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def get_all(self, category: str | None = None) -> list[dict[str, Any]]:
        """Tüm veya kategorili tercihleri al."""
        conn = sqlite3.connect(str(self._db_path))
        try:
            if category:
                rows = conn.execute(
                    "SELECT category, key, value, confidence, source FROM taste WHERE category = ? ORDER BY confidence DESC",
                    (category,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT category, key, value, confidence, source FROM taste ORDER BY category, confidence DESC"
                ).fetchall()
            return [
                {"category": r[0], "key": r[1], "value": r[2], "confidence": r[3], "source": r[4]}
                for r in rows
            ]
        finally:
            conn.close()

    def feedback(self, category: str, key: str, feedback_type: str, context: str = "") -> None:
        """Kullanıcı geri bildirimi kaydet ve güven skorunu güncelle."""
        conn = sqlite3.connect(str(self._db_path))
        try:
            row = conn.execute(
                "SELECT id, confidence FROM taste WHERE category = ? AND key = ?",
                (category, key)
            ).fetchone()

            if row:
                taste_id, current_conf = row
                # Olumlu geri bildirim: güven artır
                if feedback_type in ("positive", "thumbs_up", "correct"):
                    new_conf = min(1.0, current_conf + 0.15)
                # Olumsuz: güven azalt
                elif feedback_type in ("negative", "thumbs_down", "wrong"):
                    new_conf = max(0.0, current_conf - 0.2)
                else:
                    new_conf = current_conf

                conn.execute(
                    "UPDATE taste SET confidence = ?, updated_at = ? WHERE id = ?",
                    (new_conf, time.time(), taste_id)
                )

                conn.execute(
                    "INSERT INTO taste_feedback (taste_id, feedback_type, context, created_at) VALUES (?, ?, ?, ?)",
                    (taste_id, feedback_type, context, time.time())
                )
                conn.commit()
                logger.info("taste.feedback", category=category, key=key, type=feedback_type, new_confidence=new_conf)
        finally:
            conn.close()

    def forget(self, category: str | None = None, key: str | None = None) -> int:
        """Tercih(leri) sil."""
        conn = sqlite3.connect(str(self._db_path))
        try:
            if category and key:
                result = conn.execute("DELETE FROM taste WHERE category = ? AND key = ?", (category, key))
            elif category:
                result = conn.execute("DELETE FROM taste WHERE category = ?", (category,))
            else:
                result = conn.execute("DELETE FROM taste")
            conn.commit()
            deleted = result.rowcount
            logger.info("taste.forget", category=category, key=key, deleted=deleted)
            return deleted
        finally:
            conn.close()

    def format_for_system_prompt(self) -> str:
        """Tüm yüksek güvenli tercihleri system prompt'a eklenecek formatta döndür."""
        prefs = self.get_all()
        if not prefs:
            return ""

        groups: dict[str, list[str]] = {}
        for p in prefs:
            if p["confidence"] < 0.4:
                continue
            cat = p["category"]
            if cat not in groups:
                groups[cat] = []
            groups[cat].append(f"  {p['key']}: {p['value']}")

        if not groups:
            return ""

        lines = ["\n## KULLANICI TERCİHLERİ (öğrenilmiş)"]
        for cat, items in groups.items():
            cat_name = CATEGORIES.get(cat, cat)
            lines.append(f"\n### {cat_name}")
            lines.extend(items)

        return "\n".join(lines)

    def auto_learn_from_interaction(self, user_message: str, assistant_response: str, tools_used: list[str] | None = None) -> None:
        """Otomatik öğrenme: kullanıcı mesajından tercih çıkar."""
        msg_lower = user_message.lower()

        # Dil tespiti
        turkish_chars = set("çğıöşüâîûêÇĞİÖŞÜ")
        if any(c in user_message for c in turkish_chars) or any(w in msg_lower for w in ["merhaba", "selam", "nasıl", "edebilirim"]):
            self.learn("language", "primary", "turkish", confidence=0.7, source="auto")
        elif any(w in msg_lower for w in ["hello", "hi", "how", "what", "can you"]):
            self.learn("language", "primary", "english", confidence=0.7, source="auto")

        # Uzunluk tercihi
        if any(w in msg_lower for w in ["kısa", "kısaca", "özet", "brief", "short", "summary"]):
            self.learn("response_style", "length", "concise", confidence=0.6, source="auto")
        elif any(w in msg_lower for w in ["detaylı", "ayrıntılı", "uzun", "detailed", "comprehensive", "thorough"]):
            self.learn("response_style", "length", "detailed", confidence=0.6, source="auto")

        # Tool tercihleri
        if tools_used:
            for tool in tools_used:
                current = self.get("tool_preferences", tool) or "0"
                count = int(current) + 1
                self.learn("tool_preferences", tool, str(count), confidence=min(0.9, 0.3 + count * 0.05), source="auto")

        # Behavior: onay tercihi
        if any(w in msg_lower for w in ["onay", "izin", "sorma", "otomatik", "don't ask", "auto approve"]):
            self.learn("behavior", "approval", "auto", confidence=0.7, source="auto")
        elif any(w in msg_lower for w in ["sor", "onayla", "confirm", "ask me"]):
            self.learn("behavior", "approval", "ask", confidence=0.7, source="auto")

        # Content tercihleri
        if any(w in msg_lower for w in ["youtube", "video", "izle"]):
            self.learn("content", "media_preference", "youtube", confidence=0.5, source="auto")
        if any(w in msg_lower for w in ["github", "repo", "kod", "code"]):
            self.learn("content", "dev_preference", "github", confidence=0.5, source="auto")


# Singleton
_taste_engine: TasteEngine | None = None


def get_taste_engine() -> TasteEngine:
    """TasteEngine singleton'ini al veya oluştur."""
    global _taste_engine
    if _taste_engine is None:
        _taste_engine = TasteEngine()
    return _taste_engine
