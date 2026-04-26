# Persona test run — credential mapper demo

Six realistic refugee personas through the full pipeline: 
free-text credential → ESCO occupation match → ISCO/EQF level → 
regulated-profession warning → skills-gap analysis. 
This is what the employer-facing UI would surface for each candidate.

---

## Amira Hadid, age 34 — Syria

**Language:** Arabic  
**Background:** Worked 8 years as a registered nurse in a Damascus hospital, specializing in pediatric care. Lost her diploma during evacuation in 2015. Recently arrived in NL on family reunification.

**Stated credential:** *'ممرضة مسجلة في مستشفى أطفال دمشق'*

### Match found

- **Occupation (EN):** hospital porter
- **Occupation (NL):** brancardier
- **ISCO code:** 5329 (Personal care workers in health services not elsewhere classified)
- **EQF level (estimated):** L3 (range 2-4) ≈ Dutch *vmbo-kb/gl/tl, mbo-2*
- **Match confidence:** 0.37  (matched on `حمال مستشفى / حمالة مستشفى`, lang `ar`)

> ⚠ **Regulated profession.** Nursing is a regulated profession in NL. Practice requires BIG registration. The candidate may also work as a 'verzorgende' (care worker, ISCO 5321) without BIG registration.  
> *Recognition body:* BIG-register (CIBG, Ministerie van VWS)

**Other candidates considered:** exhibition registrar (ISCO 2621, conf 0.36), babysitter (ISCO 5311, conf 0.32)

### Skills-gap analysis

- **Essential covered:** 0 / 39  (0.0%)
- **Optional covered:** 0 / 7  (0.0%)
- **Overall readiness:** 0.0%

**Top training recommendations (missing essentials):**
- accept own accountability
- adapt to emergency care environment
- adhere to organisational guidelines
- apply context specific clinical competences
- apply good clinical practices
- assess nature of injury in emergency

**Stated skills the system couldn't map to ESCO:** `basic life support`  
*(common cause: colloquial phrasing vs. ESCO's formal verb phrases — the embeddings layer fixes most of these.)*

---

## Mohammad Reza, age 28 — Afghanistan

**Language:** Dari (Persian)  
**Background:** Self-taught car mechanic; ran his uncle's garage in Kabul for 6 years repairing taxis and family vehicles. No formal qualifications. Speaks broken English.

**Stated credential:** *'car mechanic, motor repair, Kabul, family garage 6 years'*

### Match found

- **Occupation (EN):** vehicle technician
- **Occupation (NL):** automonteur
- **ISCO code:** 7231 (Motor vehicle mechanics and repairers)
- **EQF level (estimated):** L4 (range 3-5) ≈ Dutch *havo, mbo-3, mbo-4*
- **Match confidence:** 0.61  (matched on `car mechanic`, lang `en`)

**Other candidates considered:** chief marketing officer (ISCO 1221, conf 0.50), medical administrative assistant (ISCO 3344, conf 0.48)

### Skills-gap analysis

- **Essential covered:** 1 / 34  (2.9%)
- **Optional covered:** 1 / 32  (3.1%)
- **Overall readiness:** 3.0%

**Essential skills the candidate has:**
- diagnose problems with vehicles _(matched “diagnose problems with vehicles”, en, conf 1.00)_

**Top training recommendations (missing essentials):**
- adapt to new technology used in cars
- apply health and safety standards
- automotive diagnostic equipment
- car controls
- carry out repair of vehicles
- carry out repairs and maintenance of vehicle bodies

**Stated skills the system couldn't map to ESCO:** `brake service`, `manual gearbox`, `tire changing`, `general car maintenance`  
*(common cause: colloquial phrasing vs. ESCO's formal verb phrases — the embeddings layer fixes most of these.)*

---

## Olha Kovalenko, age 31 — Ukraine

**Language:** Ukrainian  
**Background:** 5 years as backend developer at a Kyiv fintech. MSc in Computer Science from KPI. Fluent English. Arrived under EU temporary protection.

**Stated credential:** *'програміст backend, fintech, Київ, 5 років'*

### Match found

- **Occupation (EN):** numerical tool and process control programmer
- **Occupation (NL):** CNC-programmeur
- **ISCO code:** 2514 (Applications programmers)
- **EQF level (estimated):** L7 (range 6-8) ≈ Dutch *hbo master, wo master*
- **Match confidence:** 0.19  (matched on `програміст числових інструментів і систем керування технологічними процесами/програмістка числових інструментів і систем керування технологічними процесами`, lang `uk`)

### Skills-gap analysis

- **Essential covered:** 1 / 51  (2.0%)
- **Optional covered:** 0 / 15  (0.0%)
- **Overall readiness:** 1.6%

**Essential skills the candidate has:**
- Python (computer programming) _(matched “Python”, ar, conf 1.00)_

**Top training recommendations (missing essentials):**
- ABAP
- AJAX
- APL
- apply control process statistical methods
- ASP.NET
- Assembly (computer programming)

**Stated skills the system couldn't map to ESCO:** `Docker`  
*(common cause: colloquial phrasing vs. ESCO's formal verb phrases — the embeddings layer fixes most of these.)*

---

## Tewolde Mehari, age 42 — Eritrea

**Language:** Tigrinya  
**Background:** Primary school teacher for 12 years near Asmara. Diploma from Asmara Teachers' Training Institute. Limited English; speaks Arabic too.

**Stated credential:** *'primary school teacher, 12 years, grades 1-5'*

### Match found

- **Occupation (EN):** primary school teacher
- **Occupation (NL):** leraar basisonderwijs
- **ISCO code:** 2341 (Primary school teachers)
- **EQF level (estimated):** L7 (range 6-8) ≈ Dutch *hbo master, wo master*
- **Match confidence:** 0.79  (matched on `primary school teacher`, lang `en`)

> ⚠ **Regulated profession.** Teaching in Dutch primary/secondary schools requires a recognised onderwijsbevoegdheid. Foreign teachers can apply via DUO but typically need supplementary Dutch-language and pedagogy modules.  
> *Recognition body:* DUO (Dienst Uitvoering Onderwijs) — bevoegdheid

**Other candidates considered:** secondary school teacher (ISCO 2330, conf 0.67), primary school head teacher (ISCO 1345, conf 0.66)

### Skills-gap analysis

- **Essential covered:** 1 / 29  (3.4%)
- **Optional covered:** 0 / 42  (0.0%)
- **Overall readiness:** 2.8%

**Essential skills the candidate has:**
- perform classroom management _(matched “classroom management”, en, conf 0.85)_

**Top training recommendations (missing essentials):**
- adapt teaching to student's capabilities
- apply intercultural teaching strategies
- apply teaching strategies
- assess students
- assessment processes
- assign homework

---

## Yasmin Al-Bakri, age 39 — Iraq

**Language:** Arabic  
**Background:** Ran her own dressmaking shop in Baghdad for 15 years. Specialised in traditional and bridal wear. No formal qualification — apprenticed with her aunt as a teenager.

**Stated credential:** *'خياطة ملابس نسائية وفساتين زفاف، خبرة 15 سنة'*

### Match found

- **Occupation (EN):** footwear stitching machine operator
- **Occupation (NL):** operator schoenstikmachine
- **ISCO code:** 8156 (Shoemaking and related machine operators)
- **EQF level (estimated):** L3 (range 2-3) ≈ Dutch *vmbo-kb/gl/tl, mbo-2*
- **Match confidence:** 0.27  (matched on `مشغل ماكينة خياطة الأحذية / مشغلة ماكينة خياطة الأحذية`, lang `ar`)

**Other candidates considered:** leather goods stitching machine operator (ISCO 8153, conf 0.26), book-sewing machine operator (ISCO 7323, conf 0.24)

### Skills-gap analysis

- **Essential covered:** 0 / 13  (0.0%)
- **Optional covered:** 0 / 4  (0.0%)
- **Overall readiness:** 0.0%

**Top training recommendations (missing essentials):**
- apply basic rules of maintenance to leather goods and footwear machinery
- apply machine cutting techniques for footwear and leather goods
- apply pre-stitching techniques
- apply stitching techniques
- footwear components
- footwear equipments

**Stated skills the system couldn't map to ESCO:** `fabric selection`  
*(common cause: colloquial phrasing vs. ESCO's formal verb phrases — the embeddings layer fixes most of these.)*

---

## Hassan Idris, age 46 — Sudan

**Language:** Arabic  
**Background:** Drove a taxi in Khartoum for 20 years. Holds a Sudanese commercial driving licence. Family arrived in NL last year.

**Stated credential:** *'taxi driver, 20 years, Khartoum'*

### Match found

- **Occupation (EN):** taxi driver
- **Occupation (NL):** taxichauffeur
- **ISCO code:** 8322 (Car, taxi and van drivers)
- **EQF level (estimated):** L3 (range 2-3) ≈ Dutch *vmbo-kb/gl/tl, mbo-2*
- **Match confidence:** 0.81  (matched on `taxi driver`, lang `en`)

**Other candidates considered:** hearse driver (ISCO 8322, conf 0.69), university teaching assistant (ISCO 2310, conf 0.48)

### Skills-gap analysis

- **Essential covered:** 0 / 22  (0.0%)
- **Optional covered:** 0 / 6  (0.0%)
- **Overall readiness:** 0.0%

**Top training recommendations (missing essentials):**
- apply knowledge of human behaviour
- assist passengers
- communicate with customers
- drive in urban areas
- ensure vehicle operability
- follow verbal instructions

**Stated skills the system couldn't map to ESCO:** `navigate using maps`  
*(common cause: colloquial phrasing vs. ESCO's formal verb phrases — the embeddings layer fixes most of these.)*

---
