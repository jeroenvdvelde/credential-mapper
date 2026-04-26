# Credential Mapper

Maps free-text credentials and job descriptions from anywhere in the world to
their closest equivalent in the European framework (ESCO occupation, ISCO code,
estimated EQF level, and related skills).

Built as the credential-equivalence add-on for the refugee employment platform.

## What it does

Input (any language, free text):

```
"head nurse, Damascus, 2015, Aleppo University BSc Nursing"
```

Output:

```
{
  "match": {
    "esco_uri": "http://data.europa.eu/esco/occupation/03b1c5ec-6f6e-4e35-bf4e-c693dab28d40",
    "preferred_label_en": "specialist nurse",
    "preferred_label_nl": "gespecialiseerd verpleegkundige",
    "isco_code": "2221",
    "isco_group": "Nursing professionals",
    "eqf_level_estimate": 6,
    "confidence": 0.82
  },
  "alternatives": [ ... 4 more candidates ... ],
  "skills": ["administer medication", "patient assessment", ...],
  "regulated_profession": true,
  "regulated_warning": "Nursing is a regulated profession in NL. Formal recognition via BIG-register required to practise. This mapping is INDICATIVE only."
}
```

## Why this is hard, and how we handle it

1.  **Many candidates speak no English.** ESCO is published in 28 languages.
    We ingest every language pack the user supplies, so a Syrian candidate
    writing "ممرضة" matches the Arabic label for "nurse" directly without
    requiring upstream translation.
2.  **Free-text input is messy.** Candidates write things like "I worked
    fixing motorbikes for my uncle's shop". We use fuzzy + token matching
    against the full set of `preferredLabel` *and* `altLabels` for every
    occupation — altLabels alone is ~30k synonyms.
3.  **Regulated professions have legal implications.** A bad mapping that
    suggests someone can practise medicine creates real liability. We tag
    a curated set of regulated occupation codes and emit warnings.

## Data: what to download and where

Download the official ESCO v1.2.1 (or later) CSV bundle from:

  https://esco.ec.europa.eu/en/use-esco/download

Pick **CSV format** and at minimum the **English** language pack. For broader
coverage download as many languages as you want — at least Arabic, Ukrainian,
Russian, Farsi/Dari, Tigrinya (if available), Somali (if available), French,
Spanish, Turkish, and Dutch are high-value for the refugee use case.

Unzip each language pack into `data/raw/<lang>/` so the layout is:

```
data/raw/
  en/
    occupations_en.csv
    skills_en.csv
    occupationSkillRelations_en.csv
    ISCOGroups_en.csv
    broaderRelationsOccPillar_en.csv
    ... etc
  nl/
    occupations_nl.csv
    ...
  ar/
    occupations_ar.csv
    ...
```

Licence: ESCO is published under the European Union Public Licence (EUPL),
free to use including commercially. Attribution required.

## Quick start

```bash
# 1. (Once) drop ESCO CSVs into data/raw/<lang>/ as above

# 2. Build the SQLite database from the CSVs
python src/ingest.py --langs en nl ar

# 3. Look something up
python src/cli.py "nurse, Syria, 2015"
python src/cli.py "ممرضة" --input-lang ar
python src/cli.py "auto monteur, Eritrea"

# 4. Skills-gap analysis on the top match
python src/cli.py "vehicle technician" \
    --skills "engine repair, brake repair, OBD diagnostics, tire rotation"

# 5. Run the test suite
python -m unittest discover tests

# 6. Start the REST API (after `pip install fastapi uvicorn`)
uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload
```

## REST API

Once `uvicorn src.api:app` is running, the platform front-end can hit:

```bash
# Health
curl http://localhost:8000/health

# Dataset summary
curl http://localhost:8000/meta

# Free text → ESCO occupation candidates
curl -X POST http://localhost:8000/lookup \
     -H 'Content-Type: application/json' \
     -d '{"text":"head nurse, Damascus, 2015","top_k":5}'

# Combined: lookup + skills-gap in one call (the most useful endpoint
# for the platform's CV builder)
curl -X POST http://localhost:8000/credential \
     -H 'Content-Type: application/json' \
     -d '{
           "text": "automonteur",
           "input_lang": "nl",
           "candidate_skills": [
             "engine repair", "brake repair", "OBD diagnostics", "tire rotation"
           ]
         }'

# Skills-gap against an explicit occupation URI
curl -X POST http://localhost:8000/skills-gap \
     -H 'Content-Type: application/json' \
     -d '{
           "occupation_uri": "http://data.europa.eu/esco/occupation/<uri>",
           "candidate_skills": ["..."],
           "threshold": 0.6
         }'

# Full record for one occupation (multi-language labels + skills + EQF info)
curl 'http://localhost:8000/occupation/http%3A%2F%2Fdata.europa.eu%2Fesco%2Foccupation%2F<uri>'
```

Auto-generated OpenAPI docs are at `http://localhost:8000/docs`.

**Production notes**

- The DB is opened **read-only** by the API; the API can never corrupt it.
- To refresh data, re-run `python src/ingest.py --langs ...` and restart uvicorn.
- Auth is intentionally not in the API itself — wire your own (API key middleware,
  JWT, mTLS, or upstream allow-listing). Adding it as a FastAPI middleware is ~10 lines.
- Override the DB path with `CREDENTIAL_DB=/path/to/credentials.sqlite`.
- CORS is wide open by default — restrict `allow_origins` in `src/api.py` for prod.

## Project structure

```
credential-mapper/
├── README.md
├── requirements.txt
├── data/
│   ├── raw/                  # YOU drop ESCO CSVs here
│   └── mock/                 # tiny built-in dataset for tests + offline demo
├── db/
│   └── credentials.sqlite    # generated by ingest.py
├── src/
│   ├── ingest.py             # CSV → SQLite
│   ├── lookup.py             # core occupation-matching engine
│   ├── skills_gap.py         # candidate skills vs. occupation requirements
│   ├── regulated.py          # regulated-profession registry + warnings
│   ├── eqf.py                # EQF-level estimator from ISCO codes
│   ├── cli.py                # command-line interface
│   └── api.py                # FastAPI REST wrapper
└── tests/
    ├── test_examples.py      # realistic refugee credential test cases
    └── test_skills_gap.py    # skills-gap analyzer tests
```

## Roadmap (next add-ons after this works)

1.  **Skills-gap calculator** — given the matched ESCO occupation, compare
    candidate's stated skills to the full skill set required and emit a
    targeted training-needs list.
2.  **Nuffic / NL-specific layer** — overlay Nuffic diploma equivalences on
    top of ESCO occupations to produce an MBO/HBO/WO level estimate that
    Dutch employers actually understand.
3.  **Document-recovery helper** — guided flows for retrieving/reconstructing
    diplomas the candidate no longer has.
4.  **Confidence calibration** — tune the score so we know when to say
    "high confidence" vs "needs human review".

## Licence

Code: MIT. Data: ESCO is EUPL — see https://esco.ec.europa.eu/en/about-esco/licence
