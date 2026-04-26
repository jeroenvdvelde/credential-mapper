"""
EQF (European Qualifications Framework) level estimation from ISCO-08 codes.

Important caveat: EQF is a framework for *qualifications*, not occupations.
ISCO codes describe *jobs*. We can only produce an INDICATIVE estimate of the
typical EQF level expected for a given ISCO occupation, based on the official
ISCO-to-skill-level crosswalk and the European Commission's published guidance
on the relationship between ISCO skill levels and EQF.

This is suitable for "what level of qualification is the candidate roughly
operating at?" but is NOT a substitute for a formal Nuffic / ENIC-NARIC
credential evaluation.

References:
- ISCO-08 skill levels:  https://www.ilo.org/public/english/bureau/stat/isco/isco08/
- EQF self-certification reports for member states
- ESCO methodology: https://esco.ec.europa.eu/en/classification/occupation_main
"""

from dataclasses import dataclass


@dataclass
class EqfEstimate:
    """An indicative EQF level estimate with a plausible range."""
    most_likely: int          # 1-8
    range_low: int            # 1-8
    range_high: int           # 1-8
    rationale: str            # human-readable explanation
    source: str = "ISCO-08 skill level crosswalk (indicative)"


# ISCO-08 major group → typical EQF range.
# Source: ILO ISCO-08 conceptual framework (skill levels 1-4) mapped to
# EQF 1-8 using the European Commission's guidance. Conservative ranges.
_ISCO_MAJOR_TO_EQF = {
    "0": (3, 6, 5, "Armed forces — varies by rank/role; commissioned officers tend higher."),
    "1": (5, 8, 6, "Managers — typically tertiary-level qualifications or extensive experience."),
    "2": (6, 8, 7, "Professionals — typically a Bachelor's, Master's, or doctoral degree."),
    "3": (4, 6, 5, "Technicians & associate professionals — typically post-secondary or short-cycle tertiary."),
    "4": (3, 4, 4, "Clerical support — typically upper-secondary education plus on-the-job training."),
    "5": (2, 4, 3, "Services & sales — typically lower- to upper-secondary, often with vocational training."),
    "6": (2, 4, 3, "Skilled agricultural / forestry / fishery — secondary plus practical training or apprenticeship."),
    "7": (3, 5, 4, "Craft & related trades — vocational qualification or apprenticeship typical."),
    "8": (2, 3, 3, "Plant & machine operators — secondary plus operator certification."),
    "9": (1, 2, 1, "Elementary occupations — typically primary or basic literacy required."),
}


def estimate_eqf(isco_code: str | None) -> EqfEstimate | None:
    """Return an EqfEstimate for an ISCO-08 code, or None if code is unknown.

    `isco_code` can be 1-4 digits; we look at the first digit (major group).
    """
    if not isco_code:
        return None
    major = str(isco_code).strip()[:1]
    if major not in _ISCO_MAJOR_TO_EQF:
        return None
    low, high, ml, rationale = _ISCO_MAJOR_TO_EQF[major]
    return EqfEstimate(most_likely=ml, range_low=low, range_high=high, rationale=rationale)


# Rough EQF → Dutch NLQF / education level. NLQF aligns 1:1 with EQF in most
# cases but the cultural names differ, which is what Dutch employers expect.
_EQF_TO_NL = {
    1: "basisonderwijs (primary)",
    2: "vmbo-bb / praktijkonderwijs",
    3: "vmbo-kb/gl/tl, mbo-2",
    4: "havo, mbo-3, mbo-4",
    5: "associate degree, mbo-4+",
    6: "hbo bachelor, wo bachelor",
    7: "hbo master, wo master",
    8: "PhD / doctoraat",
}


def eqf_to_nl_label(eqf: int) -> str:
    """Translate an EQF level to a Dutch education-system label."""
    return _EQF_TO_NL.get(eqf, "onbekend niveau")
