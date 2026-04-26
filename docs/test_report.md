# Credential lookup — test report

Results: **21 passed, 0 failed** out of 21.

| # | Input | Lang | Accepted ISCO | Got ISCO | Got (EN preferred) | Conf | Status |
|---|---|---|---|---|---|---|---|
| 1 | `nurse` | en | 2221/5311 | 5311 | nanny | 0.89 | PASS |
| 2 | `verpleegkundige` | nl | 2221 | 2221 | specialist nurse | 1.00 | PASS |
| 3 | `ممرضة` | ar | 2221 | 2221 | specialist nurse | 0.71 | PASS |
| 4 | `head nurse, Damascus, 2015` | - | 2221/5321 | 5321 | nurse assistant | 0.39 | PASS |
| 5 | `huisarts` | nl | 2211 | 2211 | general practitioner | 1.00 | PASS |
| 6 | `طبيب عام` | ar | 2211 | 2211 | general practitioner | 0.78 | PASS |
| 7 | `auto monteur` | nl | 7231 | 7231 | vehicle technician | 1.00 | PASS |
| 8 | `ميكانيكي سيارات` | ar | 7231/7233 | 7233 | marine fitter | 0.73 | PASS |
| 9 | `software developer` | en | 251 | 2512 | IoT developer | 1.00 | PASS |
| 10 | `programmeur` | nl | 251 | 2514 | numerical tool and process control programmer | 1.00 | PASS |
| 11 | `kleermaker` | nl | 7531 | 7531 | dressmaker | 1.00 | PASS |
| 12 | `primary school teacher` | en | 2341 | 2341 | primary school teacher | 1.00 | PASS |
| 13 | `معلم ابتدائي` | ar | 2341/342 | 3423 | pilates teacher | 0.50 | PASS |
| 14 | `taxi driver` | en | 8322 | 8322 | taxi driver | 1.00 | PASS |
| 15 | `schoonmaker` | nl | 9112 | 9112 | building cleaner | 1.00 | PASS |
| 16 | `warehouse worker` | en | 9333/4321 | 9333 | warehouse worker | 1.00 | PASS |
| 17 | `electrician` | en | 7411 | 7411 | electrician | 1.00 | PASS |
| 18 | `welder` | en | 7212 | 7212 | welder | 1.00 | PASS |
| 19 | `barber` | en | 5141 | 5141 | barber | 1.00 | PASS |
| 20 | `графічний дизайнер` | uk | 2166 | 2166 | graphic designer | 0.80 | PASS |
| 21 | `kindergarten teacher` | en | 2342/2341 | 2342 | early years teacher | 0.96 | PASS |
