"""
Skills-gap analysis.

Given an ESCO occupation URI (typically the top match from `lookup.py`) and a
list of free-text skills the candidate claims to have, compute:

  - which essential skills of the occupation are *covered* by the candidate
  - which essential skills are *missing*
  - same breakdown for *optional* skills
  - which of the candidate's stated skills couldn't be mapped to ESCO at all
  - coverage percentages
  - a prioritised list of training recommendations (the missing essentials)

Each candidate skill is fuzzy-matched against ESCO's full skills label set
(all ingested languages, preferredLabel + altLabels). A skill is considered
"covered" if the candidate's text matches its label with a confidence ≥
the threshold (default 0.6).

This is the backbone of:
  - "you're 80% there, missing X and Y" feedback in the CV builder
  - bridge-training recommendations
  - employer-facing readiness summary
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
import sqlite3

try:
    from src.lookup import _score_label, _normalize, _tokens
except ImportError:
    from lookup import _score_label, _normalize, _tokens  # type: ignore


# Confidence threshold above which a candidate's stated skill is considered to
# match a given ESCO skill. Tuned to be conservative: better to flag a skill as
# "missing" and prompt the user to confirm than to over-credit them.
DEFAULT_MATCH_THRESHOLD = 0.6


# ---------- data shapes ----------

@dataclass
class CoveredSkill:
    skill_uri: str
    label_en: str
    relation: str               # 'essential' | 'optional'
    skill_type: str             # 'knowledge' | 'skill'
    matched_candidate_text: str
    matched_label: str
    matched_language: str
    confidence: float


@dataclass
class MissingSkill:
    skill_uri: str
    label_en: str
    description_en: str
    relation: str
    skill_type: str


@dataclass
class SkillsGap:
    occupation_uri: str
    threshold: float

    covered_essential: list[CoveredSkill] = field(default_factory=list)
    missing_essential: list[MissingSkill] = field(default_factory=list)
    covered_optional: list[CoveredSkill] = field(default_factory=list)
    missing_optional: list[MissingSkill] = field(default_factory=list)
    unrecognized_candidate_skills: list[str] = field(default_factory=list)

    @property
    def coverage_pct_essential(self) -> float:
        total = len(self.covered_essential) + len(self.missing_essential)
        return round(100 * len(self.covered_essential) / total, 1) if total else 0.0

    @property
    def coverage_pct_optional(self) -> float:
        total = len(self.covered_optional) + len(self.missing_optional)
        return round(100 * len(self.covered_optional) / total, 1) if total else 0.0

    @property
    def overall_readiness_pct(self) -> float:
        """Weighted blend: essentials count more than optionals."""
        ess_total = len(self.covered_essential) + len(self.missing_essential)
        opt_total = len(self.covered_optional) + len(self.missing_optional)
        if not ess_total and not opt_total:
            return 0.0
        ess_w, opt_w = 0.8, 0.2
        ess_score = (len(self.covered_essential) / ess_total) if ess_total else 0
        opt_score = (len(self.covered_optional) / opt_total) if opt_total else 0
        # If there are no essentials, fall back to optionals only
        if not ess_total:
            return round(100 * opt_score, 1)
        if not opt_total:
            return round(100 * ess_score, 1)
        return round(100 * (ess_w * ess_score + opt_w * opt_score), 1)

    def top_recommendations(self, n: int = 5) -> list[MissingSkill]:
        """The N highest-priority missing essentials (training plan input)."""
        return self.missing_essential[:n]

    def to_dict(self) -> dict:
        d = {k: v for k, v in asdict(self).items()}
        d["coverage_pct_essential"] = self.coverage_pct_essential
        d["coverage_pct_optional"] = self.coverage_pct_optional
        d["overall_readiness_pct"] = self.overall_readiness_pct
        return d


# ---------- candidate-skill parsing ----------

def parse_candidate_skills(raw: str | list[str]) -> list[str]:
    """Accept either a list of skill strings or a single delimited string.

    Splits on commas, semicolons, pipes, and newlines so the user can paste
    in whatever format they have.
    """
    if isinstance(raw, list):
        return [s.strip() for s in raw if s and s.strip()]
    if not raw:
        return []
    out = []
    for part in raw.replace("\n", ",").replace(";", ",").replace("|", ",").split(","):
        s = part.strip()
        if s:
            out.append(s)
    return out


# ---------- main analysis ----------

class SkillsGapAnalyzer:
    """Standalone analyzer that reuses the existing SQLite DB."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    # ---- helpers ----

    def _occupation_skills(self, occupation_uri: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT s.uri AS skill_uri,
                      s.description_en AS description_en,
                      os.relation_type AS relation,
                      os.skill_type AS skill_type,
                      (SELECT label FROM labels
                         WHERE concept_uri = s.uri
                           AND label_kind = 'preferred'
                           AND language = 'en') AS label_en
               FROM occupation_skills os
               JOIN skills s ON s.uri = os.skill_uri
               WHERE os.occupation_uri = ?""",
            (occupation_uri,),
        ).fetchall()

    def _all_skill_labels(self, languages: list[str] | None = None) -> list[sqlite3.Row]:
        sql = ("SELECT concept_uri, label, label_normalized, label_kind, language "
               "FROM labels WHERE concept_kind='skill'")
        params: list = []
        if languages:
            placeholders = ",".join("?" * len(languages))
            sql += f" AND language IN ({placeholders})"
            params.extend(languages)
        return self.conn.execute(sql, params).fetchall()

    def _best_match_for_candidate_skill(self, candidate_text: str,
                                        skill_labels: list[sqlite3.Row]
                                        ) -> tuple[str, str, str, float] | None:
        """Return (skill_uri, matched_label, matched_language, confidence) for
        the best ESCO skill match of one candidate-stated skill, or None."""
        in_norm = _normalize(candidate_text)
        in_tokens = _tokens(candidate_text)
        if not in_norm:
            return None

        # Pre-filter to skill labels worth scoring (token overlap or compound match)
        in_compound = in_norm.replace(" ", "")
        cands = []
        for r in skill_labels:
            ln = r["label_normalized"]
            label_tokens = {t for t in ln.split() if len(t) > 1}
            if in_tokens & label_tokens:
                cands.append(r)
                continue
            if in_compound and len(in_compound) >= 4:
                lab_compound = ln.replace(" ", "")
                if lab_compound and (lab_compound in in_compound or in_compound in lab_compound):
                    cands.append(r)
        if not cands:
            cands = skill_labels  # fall back to scoring everything for very short inputs

        # Aggregate per skill_uri (max over its labels)
        best_per_skill: dict[str, tuple[float, str, str]] = {}
        for r in cands:
            ls = _score_label(in_norm, in_tokens, r["label_normalized"], r["label_kind"])
            if ls is None or ls.score <= 0.0:
                continue
            uri = r["concept_uri"]
            cur = best_per_skill.get(uri)
            if cur is None or ls.score > cur[0]:
                best_per_skill[uri] = (ls.score, r["label"], r["language"])

        if not best_per_skill:
            return None
        uri, (score, label, lang) = max(best_per_skill.items(), key=lambda kv: kv[1][0])
        return uri, label, lang, round(score, 3)

    # ---- public API ----

    def analyze(self, occupation_uri: str, candidate_skills: str | list[str],
                threshold: float = DEFAULT_MATCH_THRESHOLD,
                languages: list[str] | None = None) -> SkillsGap:
        """Compute the skills gap for one candidate vs. one occupation."""
        skills_for_occ = self._occupation_skills(occupation_uri)
        if not skills_for_occ:
            return SkillsGap(occupation_uri=occupation_uri, threshold=threshold)

        # Required-skills index
        required: dict[str, sqlite3.Row] = {r["skill_uri"]: r for r in skills_for_occ}

        # Map each candidate-stated skill to the best ESCO skill match
        skill_labels = self._all_skill_labels(languages)
        candidate_list = parse_candidate_skills(candidate_skills)

        # candidate_uri -> (candidate_text, label, lang, confidence)
        # If multiple candidate texts map to the same ESCO skill, keep the best.
        candidate_to_uri: dict[str, tuple[str, str, str, float]] = {}
        unrecognized: list[str] = []
        for txt in candidate_list:
            best = self._best_match_for_candidate_skill(txt, skill_labels)
            if best is None or best[3] < threshold:
                unrecognized.append(txt)
                continue
            uri, lbl, lang, conf = best
            cur = candidate_to_uri.get(uri)
            if cur is None or conf > cur[3]:
                candidate_to_uri[uri] = (txt, lbl, lang, conf)

        # Walk the required list and bucket
        gap = SkillsGap(occupation_uri=occupation_uri, threshold=threshold,
                        unrecognized_candidate_skills=unrecognized)
        for uri, req in required.items():
            label_en = req["label_en"] or ""
            relation = (req["relation"] or "essential").lower()
            skill_type = (req["skill_type"] or "skill").lower()
            description_en = req["description_en"] or ""
            match = candidate_to_uri.get(uri)
            if match is not None:
                txt, lbl, lang, conf = match
                covered = CoveredSkill(
                    skill_uri=uri, label_en=label_en, relation=relation,
                    skill_type=skill_type,
                    matched_candidate_text=txt,
                    matched_label=lbl, matched_language=lang,
                    confidence=conf,
                )
                if relation == "essential":
                    gap.covered_essential.append(covered)
                else:
                    gap.covered_optional.append(covered)
            else:
                missing = MissingSkill(
                    skill_uri=uri, label_en=label_en,
                    description_en=description_en,
                    relation=relation, skill_type=skill_type,
                )
                if relation == "essential":
                    gap.missing_essential.append(missing)
                else:
                    gap.missing_optional.append(missing)

        # Stable, sensible ordering for missing lists (alphabetical by label)
        gap.missing_essential.sort(key=lambda m: m.label_en.lower())
        gap.missing_optional.sort(key=lambda m: m.label_en.lower())
        gap.covered_essential.sort(key=lambda c: -c.confidence)
        gap.covered_optional.sort(key=lambda c: -c.confidence)
        return gap


# Convenience entry point
def analyze(db_path: Path | str, occupation_uri: str,
            candidate_skills: str | list[str], **kwargs) -> SkillsGap:
    conn = sqlite3.connect(str(db_path))
    try:
        return SkillsGapAnalyzer(conn).analyze(occupation_uri, candidate_skills, **kwargs)
    finally:
        conn.close()
