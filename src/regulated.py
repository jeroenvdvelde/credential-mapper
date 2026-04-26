"""
Registry of regulated professions in the Netherlands (and broadly the EU).

When a candidate's credential maps to one of these, we MUST emit a warning:
the candidate cannot legally practise without going through formal credential
recognition (BIG-register, advocaten-tableau, architectenregister, etc.).

This list is intentionally conservative — better to flag too often than to
mislead an employer into thinking they can hire someone for a regulated role.

Sources:
- Dutch govt overview of regulated professions:
    https://www.rijksoverheid.nl/onderwerpen/erkenning-van-buitenlandse-diplomas
- EU Regulated Professions Database:
    https://ec.europa.eu/growth/tools-databases/regprof/
- BIG register (healthcare):
    https://www.bigregister.nl/
"""

from dataclasses import dataclass


@dataclass
class RegulatedProfession:
    name: str
    isco_codes: list[str]              # ISCO-08 codes (4 digits or 3-digit prefix)
    keywords: list[str]                # case-insensitive substring matches
    authority: str                     # NL recognition body
    warning: str                       # message to emit to employer + candidate


_REGISTRY: list[RegulatedProfession] = [
    RegulatedProfession(
        name="Medical doctor",
        isco_codes=["2211", "2212"],
        keywords=["doctor", "physician", "arts", "huisarts", "specialist arts", "geneeskunde",
                  "طبيب", "лікар", "врач", "tabib", "doktor"],
        authority="BIG-register (CIBG, Ministerie van VWS)",
        warning="Medical doctors are a regulated profession in NL. Practice requires BIG registration after credential evaluation by CIBG. Indicative mapping only.",
    ),
    RegulatedProfession(
        name="Nurse",
        isco_codes=["2221", "3221"],
        keywords=["nurse", "verpleegkundige", "verpleger", "ممرضة", "ممرض",
                  "медсестра", "медбрат", "медичн", "hemşire", "nurs"],
        authority="BIG-register (CIBG, Ministerie van VWS)",
        warning="Nursing is a regulated profession in NL. Practice requires BIG registration. The candidate may also work as a 'verzorgende' (care worker, ISCO 5321) without BIG registration.",
    ),
    RegulatedProfession(
        name="Midwife",
        isco_codes=["2222", "3222"],
        keywords=["midwife", "verloskundige", "قابلة", "акушер"],
        authority="BIG-register",
        warning="Midwifery is a regulated profession in NL — BIG registration required.",
    ),
    RegulatedProfession(
        name="Pharmacist",
        isco_codes=["2262"],
        keywords=["pharmacist", "apotheker", "صيدلاني", "фармацевт"],
        authority="BIG-register",
        warning="Pharmacy is a regulated profession — BIG registration required.",
    ),
    RegulatedProfession(
        name="Dentist",
        isco_codes=["2261"],
        keywords=["dentist", "tandarts", "طبيب أسنان", "стоматолог"],
        authority="BIG-register",
        warning="Dentistry is a regulated profession — BIG registration required.",
    ),
    RegulatedProfession(
        name="Physiotherapist",
        isco_codes=["2264"],
        keywords=["physiotherapist", "fysiotherapeut", "physical therapist"],
        authority="BIG-register",
        warning="Physiotherapy is a regulated profession — BIG registration required.",
    ),
    RegulatedProfession(
        name="Psychologist (clinical)",
        isco_codes=["2634"],
        keywords=["clinical psychologist", "klinisch psycholoog", "gz-psycholoog"],
        authority="BIG-register",
        warning="Clinical psychology is regulated under BIG. The title 'psycholoog' is unprotected but practice in healthcare requires registration.",
    ),
    RegulatedProfession(
        name="Lawyer / Advocate",
        isco_codes=["2611"],
        keywords=["lawyer", "advocate", "advocaat", "محامي", "адвокат", "юрист"],
        authority="Nederlandse Orde van Advocaten",
        warning="Practising as 'advocaat' in NL requires admission to the bar (tableau) after Dutch law training. The candidate may work as a juridisch medewerker without admission.",
    ),
    RegulatedProfession(
        name="Notary",
        isco_codes=["2619"],
        keywords=["notary", "notaris"],
        authority="Koninklijke Notariële Beroepsorganisatie (KNB)",
        warning="Civil-law notaries in NL are appointed by the Crown after specific training — not directly transferable from foreign credentials.",
    ),
    RegulatedProfession(
        name="Architect",
        isco_codes=["2161"],
        keywords=["architect"],
        authority="Architectenregister (Bureau Architectenregister)",
        warning="The title 'architect' is protected in NL. Use without registration is prohibited. Recognition path via Bureau Architectenregister.",
    ),
    RegulatedProfession(
        name="Teacher (primary/secondary)",
        isco_codes=["2330", "2341", "2342", "2320"],
        keywords=["teacher", "leraar", "leerkracht", "docent",
                  "معلم", "معلمة", "учитель", "вчитель", "öğretmen"],
        authority="DUO (Dienst Uitvoering Onderwijs) — bevoegdheid",
        warning="Teaching in Dutch primary/secondary schools requires a recognised onderwijsbevoegdheid. Foreign teachers can apply via DUO but typically need supplementary Dutch-language and pedagogy modules.",
    ),
    RegulatedProfession(
        name="Accountant (registered)",
        isco_codes=["2411"],
        keywords=["registeraccountant", "ra accountant", "accountant-administratieconsulent", "aa accountant"],
        authority="NBA (Koninklijke Nederlandse Beroepsorganisatie van Accountants)",
        warning="The titles RA and AA are protected. Bookkeeping (boekhouder) is unregulated.",
    ),
    RegulatedProfession(
        name="Veterinarian",
        isco_codes=["2250"],
        keywords=["veterinarian", "vet ", "dierenarts", "بيطري"],
        authority="CIBG (Beroep in de Individuele Gezondheidszorg — diergeneeskunde)",
        warning="Veterinary practice is regulated — registration required.",
    ),
    RegulatedProfession(
        name="Electrician (regulated installations)",
        isco_codes=["7411", "7412"],
        keywords=["electrician", "elektricien", "elektromonteur"],
        authority="InstallQ / Sterkin / KvINL (depending on installation type)",
        warning="The job 'electrician' itself is not protected, but installing certain low/medium voltage and gas-related equipment in NL requires recognised certifications. Foreign credentials need recognition.",
    ),
    RegulatedProfession(
        name="Gas / heating installer",
        isco_codes=["7126", "7127"],
        keywords=["gas installer", "cv monteur", "loodgieter gas", "heating engineer"],
        authority="InstallQ (CO-vrij certificering verplicht sinds 2023)",
        warning="Installing gas-fired equipment in NL requires CO-vrij certification (Wet kwaliteitsborging) since 2023.",
    ),
]


def find_regulated_match(text: str, isco_code: str | None) -> RegulatedProfession | None:
    """Return the regulated-profession entry whose keywords or ISCO code match.

    Tries ISCO code first (more reliable), falls back to keyword substring match.
    """
    text_lc = (text or "").lower()
    if isco_code:
        isco_str = str(isco_code).strip()
        for entry in _REGISTRY:
            for code in entry.isco_codes:
                if isco_str == code or isco_str.startswith(code):
                    return entry
    for entry in _REGISTRY:
        for kw in entry.keywords:
            if kw.lower() in text_lc:
                return entry
    return None


def all_regulated() -> list[RegulatedProfession]:
    """Return the full registry. Useful for tests / docs / employer UI."""
    return list(_REGISTRY)
