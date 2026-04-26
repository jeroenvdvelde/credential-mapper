"""
Credential lookup engine.

Given free-text input (any language ESCO supports), finds the closest
ESCO occupation(s), the ISCO group, an indicative EQF level, the
typical skill set, and any regulated-profession warnings.

Design notes
------------
- Labels are stored in `labels` table: every preferredLabel and altLabel
  in every language we ingested. We score the input against every label
  whose normalized form shares at least one token with the input. That
  pre-filter lets us scale to ESCO's full ~30k labels without scoring
  every row.
- Scoring blends:
    a. Exact-match bonus (normalized input == normalized label) — very strong signal.
    b. Substring bonus (one is contained in the other).
    c. Token-overlap (Jaccard) — robust to word order.
    d. Character similarity (SequenceMatcher.ratio) — catches typos and
       morphological variation.
- Per-occupation score is the max over its labels, plus a small bonus
  if labels in multiple languages all agree.
- preferredLabel matches outweigh altLabel matches.

If `rapidfuzz` is installed it's used for scoring (10-50x faster on big
datasets); otherwise we transparently fall back to stdlib `difflib`.

The lookup returns at most `top_k` candidates with confidence scores in
[0,1]. Threshold what you act on at the application layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from difflib import SequenceMatcher
from pathlib import Path
import sqlite3
from typing import Iterable

try:
    from src.eqf import estimate_eqf, eqf_to_nl_label
    from src.regulated import find_regulated_match
except ImportError:  # allow running as `python lookup.py` from src/
    from eqf import estimate_eqf, eqf_to_nl_label  # type: ignore
    from regulated import find_regulated_match  # type: ignore


# Try to use rapidfuzz for speed; fall back gracefully.
try:
    from rapidfuzz import fuzz as _rf_fuzz  # type: ignore

    def _ratio(a: str, b: str) -> float:
        return _rf_fuzz.ratio(a, b) / 100.0
except ImportError:
    def _ratio(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()


REPO = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO / "db" / "credentials.sqlite"


# ---------- normalization (must match ingest.py) ----------

def _normalize(text: str) -> str:
    if not text:
        return ""
    out = []
    for ch in text:
        if ch.isalnum() or ch.isspace():
            out.append(ch.lower())
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def _tokens(text: str) -> set[str]:
    return {t for t in _normalize(text).split() if len(t) > 1}


# ---------- scoring ----------

@dataclass
class LabelScore:
    """How well a single label matches the input."""
    label: str
    label_normalized: str
    label_kind: str          # 'preferred' | 'alt' | 'hidden'
    language: str
    score: float             # 0.0 - 1.0
    breakdown: dict


def _compute_pair_score(in_norm: str, in_tokens: set[str],
                        lab_norm: str, lab_tokens: set[str]) -> tuple[float, dict]:
    """Score a single normalized input/label pair. Pure function, no kind weighting."""
    if not lab_norm or not in_norm:
        return 0.0, {}

    # 1. exact
    exact = 1.0 if in_norm == lab_norm else 0.0

    # 2. substring (one contained in the other) — penalised by length asymmetry
    #    so a 1-word input contained in a 3-word label doesn't dominate.
    if exact:
        substring = 1.0
    elif in_norm in lab_norm or lab_norm in in_norm:
        short, long_ = (in_norm, lab_norm) if len(in_norm) <= len(lab_norm) else (lab_norm, in_norm)
        ratio = len(short) / max(1, len(long_))
        # Only really strong when the lengths are close.
        substring = 0.45 + 0.55 * ratio
    else:
        substring = 0.0

    # 3. bilateral token coverage (harmonic mean) — penalises one-sided matches
    shared = in_tokens & lab_tokens if in_tokens and lab_tokens else set()
    in_cov = len(shared) / len(in_tokens) if in_tokens else 0.0
    lab_cov = len(shared) / len(lab_tokens) if lab_tokens else 0.0
    if in_cov and lab_cov:
        token_score = 2 * in_cov * lab_cov / (in_cov + lab_cov)
    else:
        token_score = 0.0

    # 4. character similarity — robust to typos / morphological variation
    char_sim = _ratio(in_norm, lab_norm)

    # Combine. Exact > substring > blended.
    if exact:
        score = 1.0
    else:
        # Blend that rewards both token coverage and character similarity.
        blend = 0.55 * token_score + 0.45 * char_sim
        score = max(substring, blend)

    return score, {
        "exact": exact,
        "substring": round(substring, 3),
        "token_score": round(token_score, 3),
        "in_cov": round(in_cov, 3),
        "lab_cov": round(lab_cov, 3),
        "char_sim": round(char_sim, 3),
    }


def _score_label(input_norm: str, input_tokens: set[str], label_norm: str,
                 label_kind: str) -> LabelScore | None:
    if not label_norm or not input_norm:
        return None

    label_tokens = {t for t in label_norm.split() if len(t) > 1}

    # Pre-reject only when there's *no* possible signal: no shared tokens AND
    # the strings share no substring. The substring check handles compounds
    # like NL "automonteur" vs input "auto monteur" (when one is contained in
    # the other after removing spaces).
    in_compound = input_norm.replace(" ", "")
    lab_compound = label_norm.replace(" ", "")
    has_shared_token = bool(input_tokens & label_tokens) if input_tokens and label_tokens else False
    has_substring = (in_compound and lab_compound and
                     (in_compound in lab_compound or lab_compound in in_compound))
    short_mode = len(input_norm) <= 20 and len(label_norm) <= 30

    if not has_shared_token and not has_substring and not short_mode:
        return None

    # Score the original normalized forms.
    base_score, base_breakdown = _compute_pair_score(input_norm, input_tokens,
                                                    label_norm, label_tokens)

    # Compound-form scoring: only fire when the *input* contains a space.
    # This handles cases like input "auto monteur" → label "automonteur"
    # (Dutch compound word the user split). We deliberately do NOT collapse
    # spaces in the label when the input is a single token — that would
    # inflate partial matches like input "nurse" ⊂ "drynurse" (from "dry
    # nurse"), which is exactly the wrong behaviour.
    compound_score = 0.0
    compound_breakdown: dict = {}
    if " " in input_norm and in_compound:
        compound_score, compound_breakdown = _compute_pair_score(
            in_compound, {in_compound},
            lab_compound, {lab_compound} if lab_compound else set(),
        )

    if compound_score > base_score:
        score = compound_score
        breakdown = {**compound_breakdown, "via": "compound"}
    else:
        score = base_score
        breakdown = {**base_breakdown, "via": "tokens"}

    # Label-kind weighting. preferredLabel is the canonical name and should
    # outrank altLabel matches; hiddenLabel is the weakest signal.
    if label_kind == "alt":
        score *= 0.93
    elif label_kind == "hidden":
        score *= 0.83
    # preferred → no weight change (full strength)

    score = min(1.0, score)

    return LabelScore(
        label="",  # filled by caller
        label_normalized=label_norm,
        label_kind=label_kind,
        language="",
        score=score,
        breakdown=breakdown,
    )


# ---------- main lookup ----------

@dataclass
class Match:
    rank: int
    esco_uri: str
    confidence: float
    isco_code: str
    isco_label_en: str
    preferred_labels: dict          # {language: preferredLabel}
    matched_label: str
    matched_language: str
    matched_label_kind: str
    matched_score_breakdown: dict
    matched_languages: list[str]    # all langs whose labels also matched well
    eqf: dict | None
    regulated_warning: dict | None
    skills: list[dict] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LookupResult:
    input: str
    input_normalized: str
    input_lang_hint: str | None
    matches: list[Match]

    def to_dict(self) -> dict:
        return {
            "input": self.input,
            "input_normalized": self.input_normalized,
            "input_lang_hint": self.input_lang_hint,
            "matches": [m.to_dict() for m in self.matches],
        }


class CredentialMapper:
    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Database not found at {self.db_path}. "
                "Run `python src/ingest.py --mock` (offline demo) "
                "or `python src/ingest.py --langs en` (after downloading ESCO)."
            )
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        self.conn.close()

    # context manager sugar
    def __enter__(self): return self
    def __exit__(self, *a): self.close()

    # ---------- candidate pre-filtering via token index ----------

    def _candidate_labels(self, input_norm: str, input_tokens: set[str],
                          languages: Iterable[str] | None) -> list[sqlite3.Row]:
        """Return labels worth scoring against the input.

        Includes labels that:
          (a) share at least one token with the input, OR
          (b) whose compound form (no spaces) is contained in the input
              compound, or vice-versa — handles Dutch/German compounds
              (e.g. 'auto monteur' ↔ 'automonteur').
        """
        sql = (
            "SELECT concept_uri, label, label_normalized, label_kind, language "
            "FROM labels WHERE concept_kind='occupation'"
        )
        params: list = []
        if languages:
            lang_list = list(languages)
            placeholders = ",".join("?" * len(lang_list))
            sql += f" AND language IN ({placeholders})"
            params.extend(lang_list)

        rows = self.conn.execute(sql, params).fetchall()
        if not input_tokens and not input_norm:
            return rows

        in_compound = input_norm.replace(" ", "")
        out = []
        for r in rows:
            ln = r["label_normalized"]
            label_tokens = {t for t in ln.split() if len(t) > 1}
            if input_tokens & label_tokens:
                out.append(r)
                continue
            # Compound-form fallback (handles Dutch/German compounds + spacing variations)
            if in_compound and len(in_compound) >= 4:
                lab_compound = ln.replace(" ", "")
                if lab_compound and (lab_compound in in_compound or in_compound in lab_compound):
                    out.append(r)
        return out or rows

    # ---------- per-occupation aggregation ----------

    def _score_per_occupation(self, input_norm: str, input_tokens: set[str],
                              candidate_rows: Iterable[sqlite3.Row]) -> dict:
        """Aggregate label scores into per-occupation scores."""
        per_occ: dict[str, dict] = {}
        for r in candidate_rows:
            ls = _score_label(input_norm, input_tokens, r["label_normalized"], r["label_kind"])
            if ls is None or ls.score <= 0.0:
                continue
            uri = r["concept_uri"]
            entry = per_occ.setdefault(uri, {
                "best_score": 0.0,
                "best_label": "",
                "best_label_lang": "",
                "best_label_kind": "",
                "best_breakdown": {},
                "matched_langs": set(),
            })
            if ls.score > entry["best_score"]:
                entry["best_score"] = ls.score
                entry["best_label"] = r["label"]
                entry["best_label_lang"] = r["language"]
                entry["best_label_kind"] = r["label_kind"]
                entry["best_breakdown"] = ls.breakdown
            if ls.score >= 0.55:
                entry["matched_langs"].add(r["language"])
        return per_occ

    def _isco4_for(self, uri: str) -> str:
        """Cached lookup of ISCO 4-digit code for an occupation URI."""
        if not hasattr(self, "_isco4_cache"):
            self._isco4_cache: dict[str, str] = {}
        if uri not in self._isco4_cache:
            row = self.conn.execute(
                "SELECT isco_code FROM occupations WHERE uri=?", (uri,)
            ).fetchone()
            self._isco4_cache[uri] = (row["isco_code"] if row else "") or ""
        return self._isco4_cache[uri]

    def _compute_group_density(self, per_occ: dict) -> dict[str, float]:
        """Sum per-occupation best_scores aggregated by ISCO 4-digit group.

        Only counts occupations whose best label scored above a moderate
        threshold so a single weak match doesn't inflate a group.
        """
        density: dict[str, float] = {}
        for uri, e in per_occ.items():
            if e["best_score"] < 0.4:
                continue
            isco4 = self._isco4_for(uri)
            if not isco4:
                continue
            density[isco4] = density.get(isco4, 0.0) + e["best_score"]
        return density

    @staticmethod
    def _multilang_bonus(matched_langs: set[str]) -> float:
        """Small confidence bump if labels in multiple languages match."""
        if len(matched_langs) >= 3:
            return 0.05
        if len(matched_langs) == 2:
            return 0.03
        return 0.0

    # ---------- public API ----------

    def lookup(self, text: str, *, top_k: int = 5,
               input_lang: str | None = None,
               restrict_languages: list[str] | None = None) -> LookupResult:
        """Map a free-text credential to ESCO occupations.

        Args:
            text: e.g. "head nurse, Damascus, 2015" or "ميكانيكي سيارات"
            top_k: number of candidates to return
            input_lang: optional hint ('en','nl','ar',…); used to bias matches
                in that language slightly higher when scores are tied.
            restrict_languages: only consider labels in these languages.
                Default: all ingested languages.
        """
        input_norm = _normalize(text)
        input_tokens = _tokens(text)
        candidates = self._candidate_labels(input_norm, input_tokens, restrict_languages)
        per_occ = self._score_per_occupation(input_norm, input_tokens, candidates)

        # ISCO-group density bonus: short ambiguous queries like "nurse"
        # legitimately match many occupations under ISCO 2221 (Nursing
        # professionals) but only one under 5311 (Nanny, via altLabel
        # "dry nurse"). The right ISCO group is the one with high MATCH
        # DENSITY across multiple occupations, not just the single best
        # incidental match. We sum each occupation's best-score per ISCO
        # 4-digit group and use a log-scaled fraction of the leading group's
        # density as a per-occupation bonus.
        group_density = self._compute_group_density(per_occ)
        leader_density = max(group_density.values()) if group_density else 0.0

        # Apply multi-language bonus + ISCO-group density bonus + lang hint
        for uri, e in per_occ.items():
            isco4 = self._isco4_for(uri)
            density = group_density.get(isco4, 0.0)
            # density bonus capped at +0.18 — enough to flip ambiguous cases,
            # not enough to override a clear exact match in a different group.
            if leader_density > 0 and density > 0:
                density_frac = density / leader_density       # 0..1
                density_bonus = 0.18 * density_frac * min(1.0, density / 1.5)
            else:
                density_bonus = 0.0

            e["confidence"] = min(
                1.0,
                e["best_score"]
                + self._multilang_bonus(e["matched_langs"])
                + density_bonus,
            )
            e["density_bonus"] = round(density_bonus, 3)
            e["isco4"] = isco4
            # tiny bias toward input_lang
            if input_lang and e["best_label_lang"] == input_lang:
                e["confidence"] = min(1.0, e["confidence"] + 0.01)

        ranked = sorted(per_occ.items(), key=lambda kv: kv[1]["confidence"], reverse=True)[:top_k]

        matches: list[Match] = []
        for rank, (uri, e) in enumerate(ranked, start=1):
            occ = self.conn.execute(
                "SELECT isco_code, description_en FROM occupations WHERE uri=?", (uri,)
            ).fetchone()
            isco_code = occ["isco_code"] if occ else ""
            desc = occ["description_en"] if occ else ""

            # preferred labels per language
            pref_rows = self.conn.execute(
                "SELECT language, label FROM labels WHERE concept_uri=? AND label_kind='preferred'",
                (uri,),
            ).fetchall()
            preferred_labels = {r["language"]: r["label"] for r in pref_rows}

            isco_label = ""
            if isco_code:
                row = self.conn.execute(
                    "SELECT preferred_label_en FROM isco_groups WHERE code=?", (isco_code,)
                ).fetchone()
                if row:
                    isco_label = row["preferred_label_en"] or ""

            # EQF
            eqf_est = estimate_eqf(isco_code)
            eqf_dict = None
            if eqf_est:
                eqf_dict = {
                    "most_likely": eqf_est.most_likely,
                    "range_low": eqf_est.range_low,
                    "range_high": eqf_est.range_high,
                    "rationale": eqf_est.rationale,
                    "nl_label_most_likely": eqf_to_nl_label(eqf_est.most_likely),
                }

            # Regulated-profession warning
            reg = find_regulated_match(
                " ".join([text] + list(preferred_labels.values())),
                isco_code,
            )
            reg_dict = None
            if reg:
                reg_dict = {
                    "name": reg.name,
                    "authority": reg.authority,
                    "warning": reg.warning,
                }

            # Skills
            skills = []
            sk_rows = self.conn.execute(
                """SELECT s.uri, l.label, os.relation_type, os.skill_type
                   FROM occupation_skills os
                   JOIN skills s ON s.uri = os.skill_uri
                   JOIN labels l ON l.concept_uri = s.uri
                                AND l.label_kind='preferred'
                                AND l.language='en'
                   WHERE os.occupation_uri=?
                   ORDER BY os.relation_type, l.label""",
                (uri,),
            ).fetchall()
            for r in sk_rows:
                skills.append({
                    "label_en": r["label"],
                    "relation": r["relation_type"],
                    "type": r["skill_type"],
                })

            matches.append(Match(
                rank=rank,
                esco_uri=uri,
                confidence=round(e["confidence"], 3),
                isco_code=isco_code,
                isco_label_en=isco_label,
                preferred_labels=preferred_labels,
                matched_label=e["best_label"],
                matched_language=e["best_label_lang"],
                matched_label_kind=e["best_label_kind"],
                matched_score_breakdown=e["best_breakdown"],
                matched_languages=sorted(e["matched_langs"]),
                eqf=eqf_dict,
                regulated_warning=reg_dict,
                skills=skills,
                description=desc,
            ))

        return LookupResult(
            input=text,
            input_normalized=input_norm,
            input_lang_hint=input_lang,
            matches=matches,
        )


# Convenience function for ad-hoc use.
def lookup(text: str, **kwargs) -> LookupResult:
    with CredentialMapper() as cm:
        return cm.lookup(text, **kwargs)
