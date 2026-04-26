"""
Ingest ESCO CSV bulk download(s) into a normalized SQLite database.

Usage:
    python src/ingest.py --langs en
    python src/ingest.py --langs en nl ar
    python src/ingest.py --mock                    # ingest the bundled mock dataset
    python src/ingest.py --src data/raw --langs en nl

The ESCO CSV format (v1.2.x) ships these files per language pack:

    occupations_<lang>.csv
    skills_<lang>.csv
    occupationSkillRelations_<lang>.csv     (no language variation, but ships per pack)
    ISCOGroups_<lang>.csv
    broaderRelationsOccPillar_<lang>.csv   (occupation hierarchy; optional)

We only depend on the four critical files. Multi-language is handled by
ingesting each language pack and storing labels in a `labels` table keyed by
(concept_uri, language).
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO / "db" / "credentials.sqlite"
DEFAULT_SRC = REPO / "data" / "raw"
MOCK_SRC = REPO / "data" / "mock"


SCHEMA = """
CREATE TABLE IF NOT EXISTS occupations (
    uri TEXT PRIMARY KEY,
    isco_code TEXT,
    code TEXT,
    description_en TEXT
);

CREATE TABLE IF NOT EXISTS skills (
    uri TEXT PRIMARY KEY,
    skill_type TEXT,
    reuse_level TEXT,
    description_en TEXT
);

CREATE TABLE IF NOT EXISTS isco_groups (
    code TEXT PRIMARY KEY,
    preferred_label_en TEXT,
    description_en TEXT
);

-- Multi-language label store: every preferredLabel + every altLabel becomes a row.
-- This is the table the lookup engine searches against.
CREATE TABLE IF NOT EXISTS labels (
    concept_uri TEXT NOT NULL,
    concept_kind TEXT NOT NULL,         -- 'occupation' | 'skill' | 'isco'
    label TEXT NOT NULL,
    label_normalized TEXT NOT NULL,     -- lowercased, punctuation-stripped
    label_kind TEXT NOT NULL,           -- 'preferred' | 'alt' | 'hidden'
    language TEXT NOT NULL,
    PRIMARY KEY (concept_uri, label, language, label_kind)
);

CREATE INDEX IF NOT EXISTS idx_labels_norm ON labels(label_normalized);
CREATE INDEX IF NOT EXISTS idx_labels_kind ON labels(concept_kind);
CREATE INDEX IF NOT EXISTS idx_labels_lang ON labels(language);

CREATE TABLE IF NOT EXISTS occupation_skills (
    occupation_uri TEXT NOT NULL,
    skill_uri TEXT NOT NULL,
    relation_type TEXT,                 -- 'essential' | 'optional'
    skill_type TEXT,                    -- 'knowledge' | 'skill'
    PRIMARY KEY (occupation_uri, skill_uri)
);

CREATE INDEX IF NOT EXISTS idx_occskill_occ ON occupation_skills(occupation_uri);
CREATE INDEX IF NOT EXISTS idx_occskill_skill ON occupation_skills(skill_uri);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


# ---------- helpers ----------

def normalize(text: str) -> str:
    """Lowercase + strip non-alphanumeric (keep unicode letters).

    Keeps Arabic, Cyrillic, etc. characters intact — only strips ASCII
    punctuation. Spaces collapsed.
    """
    if not text:
        return ""
    out = []
    for ch in text:
        if ch.isalnum() or ch.isspace():
            out.append(ch.lower())
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def split_alt_labels(raw: str) -> list[str]:
    """ESCO altLabels are newline-separated within a CSV cell."""
    if not raw:
        return []
    return [s.strip() for s in raw.replace("\r", "").split("\n") if s.strip()]


def open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


# ---------- per-file loaders ----------

def _read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f)


def load_occupations(conn, csv_path: Path, lang: str) -> int:
    n = 0
    for row in _read_csv(csv_path):
        uri = row.get("conceptUri") or ""
        if not uri:
            continue
        isco = (row.get("iscoGroup") or "").strip()
        code = (row.get("code") or "").strip()
        desc = row.get("description") or ""
        # upsert occupation row (description only stored once, in EN by convention)
        conn.execute(
            "INSERT INTO occupations(uri, isco_code, code, description_en) VALUES (?,?,?,?) "
            "ON CONFLICT(uri) DO UPDATE SET "
            "  isco_code = COALESCE(NULLIF(excluded.isco_code,''), occupations.isco_code), "
            "  code = COALESCE(NULLIF(excluded.code,''), occupations.code), "
            "  description_en = CASE WHEN ?='en' THEN excluded.description_en ELSE occupations.description_en END",
            (uri, isco, code, desc, lang),
        )
        # labels
        pref = (row.get("preferredLabel") or "").strip()
        if pref:
            _insert_label(conn, uri, "occupation", pref, "preferred", lang)
        for alt in split_alt_labels(row.get("altLabels", "")):
            _insert_label(conn, uri, "occupation", alt, "alt", lang)
        for hid in split_alt_labels(row.get("hiddenLabels", "")):
            _insert_label(conn, uri, "occupation", hid, "hidden", lang)
        n += 1
    return n


def load_skills(conn, csv_path: Path, lang: str) -> int:
    n = 0
    for row in _read_csv(csv_path):
        uri = row.get("conceptUri") or ""
        if not uri:
            continue
        skill_type = (row.get("skillType") or "").strip()
        reuse_level = (row.get("reuseLevel") or "").strip()
        desc = row.get("description") or ""
        conn.execute(
            "INSERT INTO skills(uri, skill_type, reuse_level, description_en) VALUES (?,?,?,?) "
            "ON CONFLICT(uri) DO UPDATE SET "
            "  skill_type = COALESCE(NULLIF(excluded.skill_type,''), skills.skill_type), "
            "  reuse_level = COALESCE(NULLIF(excluded.reuse_level,''), skills.reuse_level), "
            "  description_en = CASE WHEN ?='en' THEN excluded.description_en ELSE skills.description_en END",
            (uri, skill_type, reuse_level, desc, lang),
        )
        pref = (row.get("preferredLabel") or "").strip()
        if pref:
            _insert_label(conn, uri, "skill", pref, "preferred", lang)
        for alt in split_alt_labels(row.get("altLabels", "")):
            _insert_label(conn, uri, "skill", alt, "alt", lang)
        for hid in split_alt_labels(row.get("hiddenLabels", "")):
            _insert_label(conn, uri, "skill", hid, "hidden", lang)
        n += 1
    return n


def load_occupation_skills(conn, csv_path: Path) -> int:
    n = 0
    for row in _read_csv(csv_path):
        occ = row.get("occupationUri") or ""
        sk = row.get("skillUri") or ""
        if not occ or not sk:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO occupation_skills(occupation_uri, skill_uri, relation_type, skill_type) "
            "VALUES (?,?,?,?)",
            (occ, sk, row.get("relationType", ""), row.get("skillType", "")),
        )
        n += 1
    return n


def load_isco(conn, csv_path: Path, lang: str) -> int:
    n = 0
    for row in _read_csv(csv_path):
        code = (row.get("code") or "").strip()
        if not code:
            continue
        pref = (row.get("preferredLabel") or "").strip()
        desc = row.get("description") or ""
        conn.execute(
            "INSERT INTO isco_groups(code, preferred_label_en, description_en) VALUES (?,?,?) "
            "ON CONFLICT(code) DO UPDATE SET "
            "  preferred_label_en = CASE WHEN ?='en' THEN excluded.preferred_label_en ELSE isco_groups.preferred_label_en END, "
            "  description_en = CASE WHEN ?='en' THEN excluded.description_en ELSE isco_groups.description_en END",
            (code, pref, desc, lang, lang),
        )
        # ISCO labels are also queryable
        if pref:
            _insert_label(
                conn,
                row.get("conceptUri") or f"isco:{code}",
                "isco",
                pref,
                "preferred",
                lang,
            )
        n += 1
    return n


def _insert_label(conn, uri: str, kind: str, label: str, label_kind: str, lang: str):
    conn.execute(
        "INSERT OR IGNORE INTO labels(concept_uri, concept_kind, label, label_normalized, label_kind, language) "
        "VALUES (?,?,?,?,?,?)",
        (uri, kind, label, normalize(label), label_kind, lang),
    )


# ---------- driver ----------

def ingest_language_pack(conn, src_dir: Path, lang: str, mock: bool = False) -> dict:
    """Ingest one language pack from src_dir/<lang>/ (or directly from src_dir for mock)."""
    base = src_dir if mock else src_dir / lang
    suffix = lang
    files = {
        "occupations": base / f"occupations_{suffix}.csv",
        "skills": base / f"skills_{suffix}.csv",
        "occ_skills": base / f"occupationSkillRelations_{suffix}.csv",
        "isco": base / f"ISCOGroups_{suffix}.csv",
    }
    if not files["occupations"].exists():
        raise FileNotFoundError(
            f"Required file not found: {files['occupations']}\n"
            f"Did you unzip the {lang} ESCO language pack into {base}/ ?"
        )

    counts = {}
    counts["occupations"] = load_occupations(conn, files["occupations"], lang)
    if files["isco"].exists():
        counts["isco"] = load_isco(conn, files["isco"], lang)
    else:
        # ISCO group labels only need to be loaded once (EN). Skip silently otherwise.
        counts["isco"] = 0
    if files["skills"].exists():
        counts["skills"] = load_skills(conn, files["skills"], lang)
    if files["occ_skills"].exists():
        # occupation-skill relations don't vary by language; only load on first pass
        already = conn.execute("SELECT COUNT(*) FROM occupation_skills").fetchone()[0]
        if already == 0:
            counts["occ_skills"] = load_occupation_skills(conn, files["occ_skills"])
        else:
            counts["occ_skills"] = 0
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ingest ESCO CSVs into SQLite")
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC,
                        help=f"Root folder containing per-language subfolders (default {DEFAULT_SRC})")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help=f"SQLite output path (default {DEFAULT_DB})")
    parser.add_argument("--langs", nargs="+", default=["en"],
                        help="Language codes to ingest, e.g. --langs en nl ar")
    parser.add_argument("--mock", action="store_true",
                        help="Ingest the bundled tiny mock dataset (data/mock/) for testing.")
    args = parser.parse_args(argv)

    if args.mock:
        src = MOCK_SRC
        # Mock dataset has all langs flat in one folder
        print(f"[mock] using bundled dataset at {src}")
    else:
        src = args.src

    # Fresh build
    if args.db.exists():
        args.db.unlink()
    conn = open_db(args.db)
    try:
        total = {}
        for lang in args.langs:
            print(f"[{lang}] ingesting…")
            counts = ingest_language_pack(conn, src, lang, mock=args.mock)
            for k, v in counts.items():
                total[k] = total.get(k, 0) + v
            print(f"[{lang}] done: {counts}")
        conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES ('languages', ?)",
            (",".join(args.langs),),
        )
        conn.commit()

        # Summary
        n_occ = conn.execute("SELECT COUNT(*) FROM occupations").fetchone()[0]
        n_lab = conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]
        n_skill = conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
        n_link = conn.execute("SELECT COUNT(*) FROM occupation_skills").fetchone()[0]
        print()
        print(f"  Occupations:        {n_occ}")
        print(f"  Skills:             {n_skill}")
        print(f"  Labels (all langs): {n_lab}")
        print(f"  Occupation→skill:   {n_link}")
        print(f"  DB:                 {args.db}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
