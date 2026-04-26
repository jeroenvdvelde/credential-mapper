"""
REST API for the credential mapper.

Run locally:
    pip install fastapi uvicorn
    uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

Deploy in production behind a reverse proxy (nginx, Traefik, Cloudflare).
The DB file is opened read-only at startup; refresh data by re-running
`python src/ingest.py` and restarting the API.

Endpoints
---------
GET  /health
GET  /meta                          → languages ingested, occupation/skill counts
POST /lookup                        → free-text → ESCO occupation candidates
POST /skills-gap                    → occupation_uri + candidate skills → gap
POST /credential                    → combined: lookup + (optional) gap in one call
GET  /occupation/{uri:path}         → full occupation record (labels, skills, EQF, regulated)
GET  /skill/{uri:path}              → full skill record

All endpoints accept and return JSON. CORS is enabled for browser-based UIs.

Authentication is intentionally NOT included here — wire your own
(API key, JWT, mTLS, IP allowlist) at the reverse-proxy or middleware
layer. Adding it as middleware is ~10 lines of FastAPI.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import asynccontextmanager
from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
except ImportError as e:
    raise SystemExit(
        "FastAPI not installed.\n"
        "Install:  pip install fastapi uvicorn pydantic\n"
        f"Original error: {e}"
    )

from .lookup import CredentialMapper, DEFAULT_DB
from .skills_gap import SkillsGapAnalyzer, DEFAULT_MATCH_THRESHOLD


# -------------------- DB lifecycle --------------------

DB_PATH = Path(os.environ.get("CREDENTIAL_DB", str(DEFAULT_DB)))

# SQLite connections are not thread-safe by default. We give each request its
# own connection via a thread-local; the DB file is opened read-only.
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Database not found at {DB_PATH}. "
                   f"Run `python src/ingest.py --langs en nl ar` first.",
        )
    conn = getattr(_local, "conn", None)
    if conn is None:
        # Open read-only so the API can never corrupt the DB
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True,
                                check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return conn


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm: open a connection and verify the DB is loadable.
    _get_conn()
    yield
    # Per-thread connections are closed when threads die.


# -------------------- request / response models --------------------

class LookupRequest(BaseModel):
    text: str = Field(..., description="Free-text credential or job title.")
    input_lang: str | None = Field(None, description="Hint of input language (en/nl/ar/uk/...).")
    top_k: int = Field(5, ge=1, le=25)
    restrict_languages: list[str] | None = Field(
        None, description="Only consider labels in these languages.")


class SkillsGapRequest(BaseModel):
    occupation_uri: str = Field(..., description="ESCO occupation URI (from a /lookup match).")
    candidate_skills: list[str] = Field(..., min_length=1,
                                        description="The candidate's stated skills.")
    threshold: float = Field(DEFAULT_MATCH_THRESHOLD, ge=0.0, le=1.0)
    restrict_languages: list[str] | None = None


class CredentialRequest(BaseModel):
    """Combined endpoint: lookup + optional gap analysis in one call."""
    text: str
    input_lang: str | None = None
    top_k: int = Field(3, ge=1, le=25)
    restrict_languages: list[str] | None = None
    candidate_skills: list[str] | None = Field(
        None, description="If provided, run gap analysis against the top match.")
    skills_threshold: float = Field(DEFAULT_MATCH_THRESHOLD, ge=0.0, le=1.0)


# -------------------- app --------------------

app = FastAPI(
    title="Credential Mapper API",
    description=("Maps free-text refugee credentials to ESCO occupations, "
                 "ISCO codes, EQF levels, and Dutch NLQF equivalents. "
                 "Includes regulated-profession warnings and skills-gap analysis."),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # restrict to your platform's domain in prod
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# -------------------- endpoints --------------------

@app.get("/health")
def health():
    """Liveness probe. Returns 200 if the DB is reachable."""
    try:
        conn = _get_conn()
        n = conn.execute("SELECT COUNT(*) FROM occupations").fetchone()[0]
        return {"ok": True, "occupations": n, "db": str(DB_PATH)}
    except Exception as e:
        raise HTTPException(503, f"DB unhealthy: {e}")


@app.get("/meta")
def meta():
    """Summary of the loaded dataset."""
    conn = _get_conn()
    out = {
        "occupations": conn.execute("SELECT COUNT(*) FROM occupations").fetchone()[0],
        "skills": conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0],
        "labels": conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0],
        "isco_groups": conn.execute("SELECT COUNT(*) FROM isco_groups").fetchone()[0],
        "occupation_skills": conn.execute("SELECT COUNT(*) FROM occupation_skills").fetchone()[0],
    }
    langs = conn.execute("SELECT DISTINCT language FROM labels ORDER BY language").fetchall()
    out["languages"] = [r["language"] for r in langs]
    row = conn.execute("SELECT value FROM meta WHERE key='languages'").fetchone()
    if row:
        out["last_ingest_languages"] = row["value"]
    return out


@app.post("/lookup")
def lookup(req: LookupRequest):
    """Map free text to the most likely ESCO occupations."""
    conn = _get_conn()
    cm = CredentialMapper.__new__(CredentialMapper)   # bypass __init__ (it opens its own conn)
    cm.db_path = DB_PATH
    cm.conn = conn
    result = cm.lookup(
        req.text,
        top_k=req.top_k,
        input_lang=req.input_lang,
        restrict_languages=req.restrict_languages,
    )
    return result.to_dict()


@app.post("/skills-gap")
def skills_gap(req: SkillsGapRequest):
    """Compute the skills gap between a candidate and an ESCO occupation."""
    conn = _get_conn()
    ana = SkillsGapAnalyzer(conn)
    gap = ana.analyze(
        req.occupation_uri,
        req.candidate_skills,
        threshold=req.threshold,
        languages=req.restrict_languages,
    )
    if not gap.covered_essential and not gap.missing_essential and \
       not gap.covered_optional and not gap.missing_optional:
        raise HTTPException(
            404,
            f"Occupation URI not found or has no associated skills: {req.occupation_uri}",
        )
    return gap.to_dict()


@app.post("/credential")
def credential(req: CredentialRequest):
    """Combined endpoint — single call from the platform's CV builder.

    Returns the top match(es) plus, if `candidate_skills` is provided,
    a skills-gap analysis against the top match. This is the endpoint
    the front-end will use most.
    """
    conn = _get_conn()
    cm = CredentialMapper.__new__(CredentialMapper)
    cm.db_path = DB_PATH
    cm.conn = conn
    result = cm.lookup(
        req.text,
        top_k=req.top_k,
        input_lang=req.input_lang,
        restrict_languages=req.restrict_languages,
    )
    out = {"lookup": result.to_dict(), "skills_gap": None}
    if req.candidate_skills and result.matches:
        ana = SkillsGapAnalyzer(conn)
        gap = ana.analyze(
            result.matches[0].esco_uri,
            req.candidate_skills,
            threshold=req.skills_threshold,
            languages=req.restrict_languages,
        )
        out["skills_gap"] = gap.to_dict()
    return out


@app.get("/occupation/{uri:path}")
def occupation(uri: str,
               langs: list[str] | None = Query(None,
                   description="Limit returned labels to these languages.")):
    """Full record for one ESCO occupation."""
    conn = _get_conn()
    occ = conn.execute(
        "SELECT uri, isco_code, code, description_en FROM occupations WHERE uri=?",
        (uri,),
    ).fetchone()
    if not occ:
        raise HTTPException(404, f"Occupation not found: {uri}")

    lang_filter = ""
    params: list = [uri]
    if langs:
        lang_filter = f" AND language IN ({','.join('?'*len(langs))})"
        params.extend(langs)

    label_rows = conn.execute(
        f"SELECT label, label_kind, language FROM labels WHERE concept_uri=?{lang_filter}",
        params,
    ).fetchall()
    labels: dict[str, dict[str, list[str]]] = {}
    for r in label_rows:
        labels.setdefault(r["language"], {}).setdefault(r["label_kind"], []).append(r["label"])

    skills = conn.execute(
        """SELECT s.uri, os.relation_type, os.skill_type,
                  (SELECT label FROM labels WHERE concept_uri=s.uri
                     AND label_kind='preferred' AND language='en') AS label_en
           FROM occupation_skills os
           JOIN skills s ON s.uri = os.skill_uri
           WHERE os.occupation_uri=?
           ORDER BY os.relation_type, label_en""",
        (uri,),
    ).fetchall()

    isco_label = ""
    if occ["isco_code"]:
        row = conn.execute(
            "SELECT preferred_label_en FROM isco_groups WHERE code=?", (occ["isco_code"],)
        ).fetchone()
        if row:
            isco_label = row["preferred_label_en"] or ""

    return {
        "uri": occ["uri"],
        "isco_code": occ["isco_code"],
        "isco_label_en": isco_label,
        "code": occ["code"],
        "description_en": occ["description_en"],
        "labels_by_language": labels,
        "skills": [
            {"uri": s["uri"], "label_en": s["label_en"],
             "relation": s["relation_type"], "type": s["skill_type"]}
            for s in skills
        ],
    }


@app.get("/skill/{uri:path}")
def skill(uri: str,
          langs: list[str] | None = Query(None)):
    """Full record for one ESCO skill."""
    conn = _get_conn()
    sk = conn.execute(
        "SELECT uri, skill_type, reuse_level, description_en FROM skills WHERE uri=?",
        (uri,),
    ).fetchone()
    if not sk:
        raise HTTPException(404, f"Skill not found: {uri}")

    lang_filter = ""
    params: list = [uri]
    if langs:
        lang_filter = f" AND language IN ({','.join('?'*len(langs))})"
        params.extend(langs)

    label_rows = conn.execute(
        f"SELECT label, label_kind, language FROM labels WHERE concept_uri=?{lang_filter}",
        params,
    ).fetchall()
    labels: dict[str, dict[str, list[str]]] = {}
    for r in label_rows:
        labels.setdefault(r["language"], {}).setdefault(r["label_kind"], []).append(r["label"])

    return {
        "uri": sk["uri"],
        "skill_type": sk["skill_type"],
        "reuse_level": sk["reuse_level"],
        "description_en": sk["description_en"],
        "labels_by_language": labels,
    }
