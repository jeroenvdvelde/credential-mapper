"""
End-to-end demo: realistic refugee personas → full credential-mapper pipeline.

Each persona is a small struct of:
  - background story (country, situation, language)
  - free-text job/credential as they would type it into the platform
  - free-text skills they would list

For each persona we run:
  1. Occupation lookup (which ESCO occupation matches their credential?)
  2. Skills-gap analysis on the top match (what do they have / what's missing?)
  3. Regulated-profession check (do they need NL-specific recognition?)

Output is a markdown report (docs/personas_report.md) showing exactly what
the employer-facing UI would display for each candidate. Useful for:
  - sanity-checking the system on representative inputs
  - sales/demo conversations with NGO partners or employers
  - regression testing as the matching algorithms evolve

Usage:
    cd credential-mapper
    python examples/personas.py                      # uses db/credentials.sqlite
    python examples/personas.py --db /tmp/credentials.sqlite
    python examples/personas.py --json               # full JSON instead of report
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.lookup import CredentialMapper, DEFAULT_DB
from src.skills_gap import SkillsGapAnalyzer


@dataclass
class Persona:
    name: str
    age: int
    country_of_origin: str
    primary_language: str
    lang_code: str | None              # ESCO language code if available
    background: str                    # short narrative
    credential_text: str               # how they'd describe their job/edu
    stated_skills: list[str]           # how they'd list their skills


PERSONAS: list[Persona] = [
    Persona(
        name="Amira Hadid",
        age=34,
        country_of_origin="Syria",
        primary_language="Arabic",
        lang_code="ar",
        background=("Worked 8 years as a registered nurse in a Damascus hospital, "
                    "specializing in pediatric care. Lost her diploma during evacuation "
                    "in 2015. Recently arrived in NL on family reunification."),
        credential_text="ممرضة مسجلة في مستشفى أطفال دمشق",
        stated_skills=[
            "patient assessment",
            "administer medication",
            "neonatal care",
            "wound care",
            "communicate with patients' families",
            "basic life support",
        ],
    ),
    Persona(
        name="Mohammad Reza",
        age=28,
        country_of_origin="Afghanistan",
        primary_language="Dari (Persian)",
        lang_code=None,                 # Dari isn't in our ingested set; we use Arabic-script free text
        background=("Self-taught car mechanic; ran his uncle's garage in Kabul for 6 "
                    "years repairing taxis and family vehicles. No formal qualifications. "
                    "Speaks broken English."),
        credential_text="car mechanic, motor repair, Kabul, family garage 6 years",
        stated_skills=[
            "engine repair",
            "brake service",
            "manual gearbox",
            "tire changing",
            "general car maintenance",
            "diagnose problems with vehicles",
        ],
    ),
    Persona(
        name="Olha Kovalenko",
        age=31,
        country_of_origin="Ukraine",
        primary_language="Ukrainian",
        lang_code="uk",
        background=("5 years as backend developer at a Kyiv fintech. MSc in Computer "
                    "Science from KPI. Fluent English. Arrived under EU temporary protection."),
        credential_text="програміст backend, fintech, Київ, 5 років",
        stated_skills=[
            "Python",
            "git",
            "PostgreSQL",
            "REST API design",
            "Docker",
            "agile project management",
        ],
    ),
    Persona(
        name="Tewolde Mehari",
        age=42,
        country_of_origin="Eritrea",
        primary_language="Tigrinya",
        lang_code=None,                 # Tigrinya isn't in ESCO; use English description
        background=("Primary school teacher for 12 years near Asmara. Diploma from "
                    "Asmara Teachers' Training Institute. Limited English; speaks Arabic too."),
        credential_text="primary school teacher, 12 years, grades 1-5",
        stated_skills=[
            "lesson planning",
            "classroom management",
            "teach mathematics",
            "teach reading",
            "communicate with parents",
        ],
    ),
    Persona(
        name="Yasmin Al-Bakri",
        age=39,
        country_of_origin="Iraq",
        primary_language="Arabic",
        lang_code="ar",
        background=("Ran her own dressmaking shop in Baghdad for 15 years. Specialised "
                    "in traditional and bridal wear. No formal qualification — apprenticed "
                    "with her aunt as a teenager."),
        credential_text="خياطة ملابس نسائية وفساتين زفاف، خبرة 15 سنة",
        stated_skills=[
            "sewing",
            "pattern making",
            "embroidery",
            "alterations",
            "fabric selection",
            "customer service",
        ],
    ),
    Persona(
        name="Hassan Idris",
        age=46,
        country_of_origin="Sudan",
        primary_language="Arabic",
        lang_code="ar",
        background=("Drove a taxi in Khartoum for 20 years. Holds a Sudanese commercial "
                    "driving licence. Family arrived in NL last year."),
        credential_text="taxi driver, 20 years, Khartoum",
        stated_skills=[
            "driving licence B",
            "navigate using maps",
            "customer service",
            "manage cash transactions",
            "vehicle inspection",
        ],
    ),
]


def render_persona(cm: CredentialMapper, ana: SkillsGapAnalyzer, p: Persona) -> dict:
    """Run the full pipeline for one persona; return a structured result."""
    result = cm.lookup(p.credential_text, top_k=3, input_lang=p.lang_code)
    top = result.matches[0] if result.matches else None
    gap = None
    if top is not None:
        gap = ana.analyze(top.esco_uri, p.stated_skills, threshold=0.6)
    return {
        "persona": p.__dict__,
        "top_match": top.to_dict() if top else None,
        "alternatives": [m.to_dict() for m in result.matches[1:]] if result.matches else [],
        "skills_gap": gap.to_dict() if gap else None,
    }


def render_markdown(rows: list[dict]) -> str:
    out = ["# Persona test run — credential mapper demo", ""]
    out.append("Six realistic refugee personas through the full pipeline: ")
    out.append("free-text credential → ESCO occupation match → ISCO/EQF level → ")
    out.append("regulated-profession warning → skills-gap analysis. ")
    out.append("This is what the employer-facing UI would surface for each candidate.")
    out.append("")
    out.append("---")
    out.append("")
    for r in rows:
        p = r["persona"]
        out.append(f"## {p['name']}, age {p['age']} — {p['country_of_origin']}")
        out.append("")
        out.append(f"**Language:** {p['primary_language']}  ")
        out.append(f"**Background:** {p['background']}")
        out.append("")
        out.append(f"**Stated credential:** *{p['credential_text']!r}*")
        out.append("")
        if r["top_match"] is None:
            out.append("**Match:** no candidates found.")
            out.append("")
            continue
        m = r["top_match"]
        out.append("### Match found")
        out.append("")
        out.append(f"- **Occupation (EN):** {m['preferred_labels'].get('en', '-')}")
        if m['preferred_labels'].get('nl'):
            out.append(f"- **Occupation (NL):** {m['preferred_labels'].get('nl', '-')}")
        out.append(f"- **ISCO code:** {m['isco_code']} ({m['isco_label_en']})")
        if m['eqf']:
            out.append(f"- **EQF level (estimated):** L{m['eqf']['most_likely']} "
                       f"(range {m['eqf']['range_low']}-{m['eqf']['range_high']}) "
                       f"≈ Dutch *{m['eqf']['nl_label_most_likely']}*")
        out.append(f"- **Match confidence:** {m['confidence']:.2f}  "
                   f"(matched on `{m['matched_label']}`, lang `{m['matched_language']}`)")
        if m['regulated_warning']:
            out.append("")
            out.append("> ⚠ **Regulated profession.** "
                       f"{m['regulated_warning']['warning']}  ")
            out.append(f"> *Recognition body:* {m['regulated_warning']['authority']}")
        out.append("")
        # alternatives
        if r["alternatives"]:
            out.append("**Other candidates considered:** "
                       + ", ".join(
                           f"{a['preferred_labels'].get('en', '?')} "
                           f"(ISCO {a['isco_code']}, conf {a['confidence']:.2f})"
                           for a in r["alternatives"]
                       ))
            out.append("")
        # skills gap
        gap = r["skills_gap"]
        if gap:
            out.append("### Skills-gap analysis")
            out.append("")
            out.append(f"- **Essential covered:** "
                       f"{len(gap['covered_essential'])} / "
                       f"{len(gap['covered_essential']) + len(gap['missing_essential'])}  "
                       f"({gap['coverage_pct_essential']}%)")
            out.append(f"- **Optional covered:** "
                       f"{len(gap['covered_optional'])} / "
                       f"{len(gap['covered_optional']) + len(gap['missing_optional'])}  "
                       f"({gap['coverage_pct_optional']}%)")
            out.append(f"- **Overall readiness:** {gap['overall_readiness_pct']}%")
            if gap["covered_essential"]:
                out.append("")
                out.append("**Essential skills the candidate has:**")
                for c in gap["covered_essential"][:6]:
                    out.append(f"- {c['label_en']} _(matched “{c['matched_candidate_text']}”, "
                               f"{c['matched_language']}, conf {c['confidence']:.2f})_")
            missing_top = gap["missing_essential"][:6]
            if missing_top:
                out.append("")
                out.append("**Top training recommendations (missing essentials):**")
                for m_ in missing_top:
                    out.append(f"- {m_['label_en']}")
            if gap["unrecognized_candidate_skills"]:
                out.append("")
                out.append("**Stated skills the system couldn't map to ESCO:** "
                           + ", ".join(f"`{s}`" for s in gap["unrecognized_candidate_skills"])
                           + "  ")
                out.append("*(common cause: colloquial phrasing vs. ESCO's formal verb phrases — "
                           "the embeddings layer fixes most of these.)*")
        out.append("")
        out.append("---")
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path,
                   default=Path(os.environ.get("CREDENTIAL_DB", str(DEFAULT_DB))))
    p.add_argument("--json", action="store_true",
                   help="Emit JSON instead of writing the markdown report.")
    p.add_argument("--out", type=Path, default=ROOT / "docs" / "personas_report.md",
                   help="Where to write the markdown report.")
    args = p.parse_args(argv)

    cm = CredentialMapper(args.db)
    ana = SkillsGapAnalyzer(cm.conn)
    rows = []
    for persona in PERSONAS:
        print(f"  → {persona.name}…")
        rows.append(render_persona(cm, ana, persona))
    cm.close()

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    else:
        report = render_markdown(rows)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"\nReport written: {args.out}")
        print(f"({len(rows)} personas processed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
