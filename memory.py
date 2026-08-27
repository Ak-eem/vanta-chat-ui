"""
Vanta Memory System — Hybrid SQLite + markdown profile.
stdlib only. Python 3.10+.

Design:
- SQLite ledger (WAL mode) with FTS5 full-text search
- memory.md human-readable profile
- Audit trail for every extraction/update/consolidation
- Post-turn extraction via regex + explicit patterns
- Periodic consolidation (merge duplicates, never delete)
"""

import json
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


DEFAULT_DB = Path.home() / ".vanta" / "vanta_memory.db"

# ── Schema ───────────────────────────────────────────────────────────────────
INIT_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS memory_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL CHECK(kind IN ('fact','preference','skill','event','task')),
    content     TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'turn',
    confidence  REAL NOT NULL DEFAULT 1.0 CHECK(confidence BETWEEN 0.0 AND 1.0),
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    consolidated INTEGER NOT NULL DEFAULT 0 CHECK(consolidated IN (0,1))
);

CREATE TABLE IF NOT EXISTS memory_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_audit (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    action     TEXT NOT NULL CHECK(action IN ('extract','update','consolidate','review')),
    entry_id   INTEGER,
    detail     TEXT,
    created_at REAL NOT NULL
);

-- FTS5 virtual table + triggers for sync
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(content, content_rowid=rowid);

CREATE TRIGGER IF NOT EXISTS memory_entries_ai AFTER INSERT ON memory_entries BEGIN
    INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS memory_entries_ad AFTER DELETE ON memory_entries BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, content) VALUES ('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS memory_entries_au AFTER UPDATE ON memory_entries BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, content) VALUES ('delete', old.id, old.content);
    INSERT INTO memory_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE INDEX IF NOT EXISTS idx_kind ON memory_entries(kind);
CREATE INDEX IF NOT EXISTS idx_created ON memory_entries(created_at);
CREATE INDEX IF NOT EXISTS idx_consolidated ON memory_entries(consolidated);
"""

# ── Extraction patterns ──────────────────────────────────────────────────────
_EXTRACT_PATTERNS = [
    # Explicit identity
    (r"\bmy name is\s+(.+?)(?:[.!?]|$)", "fact", 1.0),
    (r"\bi am\s+(.+?)(?:[.!?]|$)", "fact", 0.9),
    (r"\bi'm\s+(.+?)(?:[.!?]|$)", "fact", 0.9),
    # Preferences
    (r"\bi (?:like|love|enjoy|prefer)\s+(.+?)(?:[.!?]|$)", "preference", 0.85),
    (r"\bi (?:don't like|hate|dislike|prefer not to)\s+(.+?)(?:[.!?]|$)", "preference", 0.85),
    (r"\bi always\s+(.+?)(?:[.!?]|$)", "preference", 0.8),
    (r"\bi never\s+(.+?)(?:[.!?]|$)", "preference", 0.8),
    # Skills / knowledge
    (r"\bi (?:know|can|know how to)\s+(.+?)(?:[.!?]|$)", "skill", 0.75),
    (r"\bi work as\s+a[n]?\s+(.+?)(?:[.!?]|$)", "skill", 0.9),
    (r"\bi'm a[n]?\s+(.+?)(?:[.!?]|$)", "skill", 0.9),
    # Tasks / goals
    (r"\bi need to\s+(.+?)(?:[.!?]|$)", "task", 0.7),
    (r"\bi want to\s+(.+?)(?:[.!?]|$)", "task", 0.7),
    (r"\bi'm trying to\s+(.+?)(?:[.!?]|$)", "task", 0.7),
    # Events
    (r"\bi (?:just|recently)\s+(.+?)(?:[.!?]|$)", "event", 0.6),
]


# ── DB lifecycle ─────────────────────────────────────────────────────────────
def init_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Initialise the memory database. Creates tables, indexes, FTS5, WAL."""
    path = db_path or DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), check_same_thread=False)
    con.executescript(INIT_SQL)
    con.commit()
    return con


def _get_con(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Lazy singleton per path (not thread-safe across paths, fine for single-process)."""
    path = db_path or DEFAULT_DB
    cache_key = f"_con_{path}"
    if cache_key not in _get_con.__dict__:
        _get_con.__dict__[cache_key] = init_db(path)
    return _get_con.__dict__[cache_key]


# ── Core CRUD ────────────────────────────────────────────────────────────────
def add_memory(
    kind: str,
    content: str,
    source: str = "turn",
    confidence: float = 1.0,
    db_path: Optional[Path] = None,
) -> int:
    """Insert a single memory entry. Returns the row id."""
    con = _get_con(db_path)
    now = time.time()
    cur = con.execute(
        """INSERT INTO memory_entries(kind, content, source, confidence, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (kind, content.strip(), source, confidence, now, now),
    )
    entry_id = cur.lastrowid
    con.execute(
        "INSERT INTO memory_audit(action, entry_id, detail, created_at) VALUES (?, ?, ?, ?)",
        ("extract", entry_id, f"kind={kind} conf={confidence}", now),
    )
    con.commit()
    return entry_id


def _is_duplicate(content: str, kind: str, db_path: Optional[Path] = None) -> bool:
    """Check for near-duplicate (same kind + case-insensitive content match)."""
    con = _get_con(db_path)
    row = con.execute(
        "SELECT 1 FROM memory_entries WHERE kind = ? AND lower(content) = lower(?) LIMIT 1",
        (kind, content.strip()),
    ).fetchone()
    return row is not None


def extract_memories(text: str, source: str = "turn", db_path: Optional[Path] = None) -> list[int]:
    """Run regex extraction over text, insert new memories, return inserted ids.
    Skips duplicates."""
    inserted: list[int] = []
    for pattern, kind, confidence in _EXTRACT_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            raw = match.group(1).strip()
            if len(raw) < 3:
                continue
            if _is_duplicate(raw, kind, db_path):
                continue
            inserted.append(add_memory(kind, raw, source, confidence, db_path))
    return inserted


def search_memories(query: str, top_k: int = 5, db_path: Optional[Path] = None) -> list[dict]:
    """FTS5 MATCH first, fallback to LIKE. Returns list of entry dicts."""
    con = _get_con(db_path)
    results: list[dict] = []

    # Try FTS5
    try:
        rows = con.execute(
            """SELECT e.id, e.kind, e.content, e.source, e.confidence, e.created_at
               FROM memory_fts f
               JOIN memory_entries e ON f.rowid = e.id
               WHERE memory_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (query, top_k),
        ).fetchall()
        for row in rows:
            results.append({
                "id": row[0], "kind": row[1], "content": row[2],
                "source": row[3], "confidence": row[4], "created_at": row[5],
            })
    except sqlite3.OperationalError:
        # FTS5 not available or query malformed — fall through
        pass

    if not results:
        # LIKE fallback
        like_q = f"%{query}%"
        rows = con.execute(
            """SELECT id, kind, content, source, confidence, created_at
               FROM memory_entries
               WHERE content LIKE ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (like_q, top_k),
        ).fetchall()
        for row in rows:
            results.append({
                "id": row[0], "kind": row[1], "content": row[2],
                "source": row[3], "confidence": row[4], "created_at": row[5],
            })

    return results


# ── Profile assembly ─────────────────────────────────────────────────────────
def get_profile(db_path: Optional[Path] = None) -> str:
    """Assemble a compact profile string from top-confidence facts/preferences."""
    con = _get_con(db_path)
    lines: list[str] = []
    for kind in ("fact", "preference", "skill"):
        rows = con.execute(
            """SELECT content FROM memory_entries
               WHERE kind = ? AND consolidated = 0
               ORDER BY confidence DESC, created_at DESC
               LIMIT 3""",
            (kind,),
        ).fetchall()
        if rows:
            lines.append(f"{kind.capitalize()}s:")
            for r in rows:
                lines.append(f"  - {r[0]}")
    return "\n".join(lines) if lines else ""


def write_memory_md(path: Optional[Path] = None, db_path: Optional[Path] = None) -> Path:
    """Write/update the human-readable memory.md profile."""
    target = path or (Path.home() / ".vanta" / "memory.md")
    target.parent.mkdir(parents=True, exist_ok=True)

    con = _get_con(db_path)
    lines = ["# Vanta Memory Profile\n", f"_Updated: {datetime.now().isoformat()}_\n"]

    for kind in ("fact", "preference", "skill", "event", "task"):
        rows = con.execute(
            """SELECT content, confidence, created_at
               FROM memory_entries
               WHERE kind = ?
               ORDER BY confidence DESC, created_at DESC""",
            (kind,),
        ).fetchall()
        if not rows:
            continue
        lines.append(f"\n## {kind.capitalize()}s\n")
        for content, conf, ts in rows:
            dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            lines.append(f"- [{dt}] {content}  (conf: {conf:.2f})")

    target.write_text("\n".join(lines), encoding="utf-8")
    return target


# ── Consolidation ────────────────────────────────────────────────────────────
def consolidate(threshold_days: int = 30, db_path: Optional[Path] = None) -> Path:
    """Merge duplicate/similar entries, mark old as consolidated, write report.
    NEVER deletes anything."""
    con = _get_con(db_path)
    cutoff = time.time() - (threshold_days * 86400)

    # Find potential duplicates: same kind + similar content (simple substring check)
    rows = con.execute(
        """SELECT id, kind, content, confidence, created_at
           FROM memory_entries
           WHERE consolidated = 0 AND created_at < ?
           ORDER BY kind, created_at DESC""",
        (cutoff,),
    ).fetchall()

    merged_count = 0
    reports: list[str] = []
    seen: set[int] = set()

    for i, (id_a, kind_a, content_a, conf_a, ts_a) in enumerate(rows):
        if id_a in seen:
            continue
        duplicates: list[tuple[int, str, float]] = []
        for j in range(i + 1, len(rows)):
            id_b, kind_b, content_b, conf_b, ts_b = rows[j]
            if id_b in seen:
                continue
            if kind_a != kind_b:
                continue
            # Simple similarity: one contains the other or high word overlap
            a_words = set(content_a.lower().split())
            b_words = set(content_b.lower().split())
            if not a_words or not b_words:
                continue
            overlap = len(a_words & b_words) / max(len(a_words), len(b_words))
            if overlap >= 0.7 or content_a.lower() in content_b.lower() or content_b.lower() in content_a.lower():
                duplicates.append((id_b, content_b, conf_b))
                seen.add(id_b)

        if duplicates:
            seen.add(id_a)
            # Merge: keep the newest/highest-confidence content, mark rest consolidated
            best_content = content_a
            best_conf = conf_a
            for _id_b, content_b, conf_b in duplicates:
                if conf_b > best_conf:
                    best_conf = conf_b
                    best_content = content_b

            # Insert merged entry
            now = time.time()
            cur = con.execute(
                """INSERT INTO memory_entries(kind, content, source, confidence, created_at, updated_at, consolidated)
                   VALUES (?, ?, ?, ?, ?, ?, 0)""",
                (kind_a, best_content, "consolidation", best_conf, now, now),
            )
            new_id = cur.lastrowid

            # Mark originals consolidated
            for dup_id, _, _ in [(id_a, "", 0)] + duplicates:
                con.execute(
                    "UPDATE memory_entries SET consolidated = 1 WHERE id = ?",
                    (dup_id,),
                )
                con.execute(
                    "INSERT INTO memory_audit(action, entry_id, detail, created_at) VALUES (?, ?, ?, ?)",
                    ("consolidate", dup_id, f"merged into {new_id}", now),
                )

            merged_count += 1
            reports.append(
                f"Merged {len(duplicates)+1} '{kind_a}' entries into #{new_id}: '{best_content}'"
            )

    con.commit()

    # Write report
    report_path = Path.home() / ".vanta" / "memory_consolidation_report.md"
    report_lines = [
        f"# Memory Consolidation Report\n",
        f"_Run: {datetime.now().isoformat()}_\n",
        f"Threshold: {threshold_days} days\n",
        f"Merged groups: {merged_count}\n",
    ]
    if reports:
        report_lines.append("\n## Actions\n")
        for r in reports:
            report_lines.append(f"- {r}")
    else:
        report_lines.append("\nNo duplicates found.\n")

    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    # Update meta
    con.execute(
        "INSERT OR REPLACE INTO memory_meta(key, value) VALUES (?, ?)",
        ("last_consolidation", str(time.time())),
    )
    con.commit()

    return report_path


# ── Conversation summarisation ───────────────────────────────────────────────
def summarize_conversation(turns: list[dict], db_path: Optional[Path] = None) -> str:
    """Extract a concise summary from a list of turn dicts {'role': ..., 'content': ...}.
    Returns the summary text (caller decides whether to store it)."""
    if not turns:
        return ""
    # Simple extractive summary: pick key user statements and assistant decisions
    user_turns = [t["content"] for t in turns if t.get("role") == "user"]
    if not user_turns:
        return ""
    # Store as a task/event hybrid
    summary = "Conversation covered: " + "; ".join(user_turns[-3:])
    add_memory("event", summary, "conversation_summary", 0.5, db_path)
    return summary


# ── Post-turn hook ───────────────────────────────────────────────────────────
def process_turn(
    user_text: str,
    assistant_text: str = "",
    db_path: Optional[Path] = None,
) -> list[int]:
    """Post-turn hook: extract memories from both sides, update memory.md
    only if new entries were added. Returns inserted ids."""
    combined = f"{user_text}\n{assistant_text}"
    inserted = extract_memories(combined, source="turn", db_path=db_path)
    if inserted:
        write_memory_md(db_path=db_path)
    return inserted


# ── Stats ────────────────────────────────────────────────────────────────────
def stats(db_path: Optional[Path] = None) -> dict:
    con = _get_con(db_path)
    counts = {}
    for row in con.execute("SELECT kind, COUNT(*) FROM memory_entries GROUP BY kind"):
        counts[row[0]] = row[1]
    total = sum(counts.values())
    last_extract = con.execute(
        "SELECT MAX(created_at) FROM memory_audit WHERE action = 'extract'"
    ).fetchone()[0]
    return {
        "total_entries": total,
        "by_kind": counts,
        "last_extraction": datetime.fromtimestamp(last_extract).isoformat() if last_extract else None,
    }


# ── Self-test ────────────────────────────────────────────────────────────────
def _self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test_memory.db"
        md = Path(tmp) / "memory.md"

        print("=== init_db ===")
        init_db(db)
        print("OK")

        print("\n=== add_memory ===")
        id1 = add_memory("fact", "My name is Akeem", "test", 1.0, db)
        id2 = add_memory("preference", "I like dark themes", "test", 0.9, db)
        print(f"Inserted ids: {id1}, {id2}")

        print("\n=== extract_memories (regex) ===")
        text = "I am a software engineer. I prefer TypeScript over Python. I like minimal UIs."
        ids = extract_memories(text, "test", db)
        print(f"Extracted ids: {ids}")

        print("\n=== search_memories ===")
        results = search_memories("dark", 5, db)
        for r in results:
            print(f"  [{r['kind']}] {r['content']} (conf={r['confidence']})")

        print("\n=== get_profile ===")
        profile = get_profile(db)
        print(profile)

        print("\n=== write_memory_md ===")
        path = write_memory_md(md, db)
        print(path.read_text()[:500])

        print("\n=== stats ===")
        print(stats(db))

        print("\n=== consolidate ===")
        # Add a near-duplicate to trigger merging
        add_memory("preference", "I like dark themes and minimal UIs", "test", 0.85, db)
        report = consolidate(threshold_days=0, db_path=db)
        print(report.read_text()[:500])

        print("\n=== process_turn ===")
        ids = process_turn("I am learning Rust", "That's great, Rust is excellent for systems programming.", db)
        print(f"Inserted from turn: {ids}")

        print("\n=== All tests passed ===")


if __name__ == "__main__":
    _self_test()
