"""
Command-line interface for the credential mapper.

Examples:
    python src/cli.py "head nurse, Damascus, 2015"
    python src/cli.py "ميكانيكي سيارات" --input-lang ar
    python src/cli.py "auto monteur" --input-lang nl --json
    python src/cli.py "software developer" --top 3
    python src/cli.py "software developer" --db /tmp/credentials.sqlite
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from src.lookup import CredentialMapper, DEFAULT_DB
    from src.skills_gap import SkillsGapAnalyzer, DEFAULT_MATCH_THRESHOLD
except ImportError:
    from lookup import CredentialMapper, DEFAULT_DB  # type: ignore
    from skills_gap import SkillsGapAnalyzer, DEFAULT_MATCH_THRESHOLD  # type: ignore


def _format_human(result) -> str:
    lines = []
    lines.append(f"Input:        {result.input!r}")
    if result.input_lang_hint:
        lines.append(f"Input lang:   {result.input_lang_hint}")
    lines.append(f"Normalized:   {result.input_normalized!r}")
    lines.append(f"Found:        {len(result.matches)} candidate(s)")
    lines.append("")

    if not result.matches:
        lines.append("  (no matches — try a different language pack or broader text)")
        return "\n".join(lines)

    for m in result.matches:
        lines.append(f"  #{m.rank}  confidence {m.confidence:.2f}")
        # Show preferred labels in EN and one other language if present
        en = m.preferred_labels.get("en", "")
        if en:
            lines.append(f"      EN:          {en}")
        for lang, lbl in m.preferred_labels.items():
            if lang == "en":
                continue
            lines.append(f"      {lang.upper()}:          {lbl}")
        lines.append(f"      ISCO:        {m.isco_code}  ({m.isco_label_en or '-'})")
        if m.eqf:
            lines.append(
                f"      EQF (est.):  L{m.eqf['most_likely']} "
                f"(range {m.eqf['range_low']}-{m.eqf['range_high']}) "
                f"≈ {m.eqf['nl_label_most_likely']}"
            )
        lines.append(f"      Matched:     '{m.matched_label}' "
                     f"({m.matched_language}, {m.matched_label_kind})")
        if len(m.matched_languages) > 1:
            lines.append(f"      Cross-lang:  also matched in {', '.join(m.matched_languages)}")
        if m.regulated_warning:
            lines.append(f"      ⚠ REGULATED: {m.regulated_warning['name']}")
            lines.append(f"         {m.regulated_warning['warning']}")
        if m.skills:
            top_skills = [s["label_en"] for s in m.skills if s["relation"] == "essential"][:5]
            if top_skills:
                lines.append(f"      Skills:      {', '.join(top_skills)}")
        if m.description:
            short = m.description if len(m.description) <= 110 else m.description[:107] + "…"
            lines.append(f"      About:       {short}")
        lines.append("")
    return "\n".join(lines)


def _format_gap_human(gap) -> str:
    lines = []
    lines.append("")
    lines.append("  --- Skills gap ---")
    lines.append(f"  Essential covered: {len(gap.covered_essential)}/"
                 f"{len(gap.covered_essential) + len(gap.missing_essential)}  "
                 f"({gap.coverage_pct_essential}%)")
    lines.append(f"  Optional covered:  {len(gap.covered_optional)}/"
                 f"{len(gap.covered_optional) + len(gap.missing_optional)}  "
                 f"({gap.coverage_pct_optional}%)")
    lines.append(f"  Overall readiness: {gap.overall_readiness_pct}%")
    lines.append("")
    if gap.covered_essential:
        lines.append("  ✓ Essential skills you have:")
        for c in gap.covered_essential[:8]:
            lines.append(f"      - {c.label_en}  (matched '{c.matched_candidate_text}', conf {c.confidence:.2f})")
    recs = gap.top_recommendations(8)
    if recs:
        lines.append("")
        lines.append("  ✗ Essential skills to acquire (training plan):")
        for m in recs:
            lines.append(f"      - {m.label_en}")
    if gap.unrecognized_candidate_skills:
        lines.append("")
        lines.append("  ? Stated skills we couldn't map to ESCO:")
        for s in gap.unrecognized_candidate_skills:
            lines.append(f"      - {s}")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Map a free-text credential to ESCO.")
    p.add_argument("text", help="The candidate's stated job/credential text.")
    p.add_argument("--input-lang", help="Hint of input language (en/nl/ar/uk/...).")
    p.add_argument("--top", type=int, default=5, help="Top K results.")
    p.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite DB.")
    p.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable.")
    p.add_argument("--restrict-langs", nargs="+",
                   help="Only consider labels in these languages.")
    p.add_argument("--skills",
                   help="Comma- or newline-separated list of candidate's stated skills. "
                        "Triggers a skills-gap analysis against the top match.")
    p.add_argument("--gap-threshold", type=float, default=DEFAULT_MATCH_THRESHOLD,
                   help=f"Minimum confidence to credit a skill (default {DEFAULT_MATCH_THRESHOLD}).")
    args = p.parse_args(argv)

    with CredentialMapper(args.db) as cm:
        result = cm.lookup(
            args.text,
            top_k=args.top,
            input_lang=args.input_lang,
            restrict_languages=args.restrict_langs,
        )

        gap = None
        if args.skills and result.matches:
            top_uri = result.matches[0].esco_uri
            analyzer = SkillsGapAnalyzer(cm.conn)
            gap = analyzer.analyze(top_uri, args.skills,
                                   threshold=args.gap_threshold,
                                   languages=args.restrict_langs)

    if args.json:
        out = {"lookup": result.to_dict()}
        if gap is not None:
            out["skills_gap"] = gap.to_dict()
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    else:
        print(_format_human(result))
        if gap is not None:
            print(_format_gap_human(gap))
    return 0


if __name__ == "__main__":
    sys.exit(main())
