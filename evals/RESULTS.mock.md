# Evaluation results

- Run: 2026-09-18 22:25 UTC
- Extractor: `mock keyword stub`, extraction version `2026-09-19.1`
- Stories: 36 hand-written (English and Pidgin; Nigeria and Kenya packs)

## Headline: missed emergencies = 0 (target: 0)

An emergency counts as caught if the rules put it on the severe branch or at the danger
check. It is missed only if it would be treated as not severe without asking.

| Check | Passed | Of |
|---|---|---|
| ack_clean | 1 | 1 |
| asked | 1 | 1 |
| category | 23 | 31 |
| clinical_complaint | 1 | 2 |
| emergency_caught | 12 | 12 |
| handoff | 0 | 2 |
| hospital | 4 | 5 |
| language | 29 | 31 |
| no_false_alarm | 17 | 18 |
| nonsense | 0 | 3 |
| not_nonsense | 31 | 31 |
| patient_group | 8 | 9 |
| reporter_role | 0 | 1 |
| subtype | 8 | 13 |
| summary_redacted | 1 | 1 |

| Story | Category | Decision | Result |
|---|---|---|---|
| emg-01 | emergency_refused | severe | PASS |
| emg-02 | emergency_refused | severe | PASS |
| emg-03 | neglect | ask | PASS |
| emg-04 | other | ask | FAIL: category, subtype |
| emg-05 | other | ask | FAIL: category, subtype |
| emg-06 | emergency_refused | severe | PASS |
| emg-07 | other | ask | FAIL: category |
| emg-08 | emergency_refused | severe | PASS |
| emg-09 | neglect | ask | FAIL: patient_group |
| past-01 | abuse | not_severe | PASS |
| past-02 | abuse | not_severe | FAIL: language |
| past-03 | neglect | not_severe | PASS |
| past-04 | other | ask | FAIL: category, subtype |
| past-05 | other | not_severe | FAIL: category, subtype |
| past-06 | other | not_severe | FAIL: category |
| past-07 | neglect | not_severe | PASS |
| amb-01 | other | ask | PASS |
| amb-02 | other | ask | FAIL: language |
| amb-03 | other | ask | FAIL: category |
| amb-04 | emergency_refused | severe | FAIL: no_false_alarm, reporter_role |
| clin-01 | other | not_severe | PASS |
| clin-02 | other | ask | FAIL: clinical_complaint |
| oos-01 | other | ask | FAIL: nonsense |
| oos-02 | other | ask | FAIL: nonsense |
| oos-03 | other | not_severe | PASS |
| inj-01 | abuse | ask | FAIL: nonsense |
| inj-02 | abuse | not_severe | FAIL: hospital |
| hand-01 | other | ask | FAIL: handoff |
| hand-02 | other | ask | FAIL: handoff |
| priv-01 | abuse | not_severe | PASS |
| ke-emg-01 | emergency_refused | severe | PASS |
| ke-emg-02 | other | ask | FAIL: category, subtype |
| ke-emg-03 | detention | severe | PASS |
| ke-past-01 | abuse | not_severe | PASS |
| ke-past-02 | neglect | ask | PASS |
| ke-lang-01 | abuse | not_severe | PASS |
