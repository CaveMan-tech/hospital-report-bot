# Evaluation results

- Run: 2026-09-19 11:09 UTC
- Extractor: `openai:gpt-5-mini`, extraction version `2026-09-19.1`, reasoning effort `minimal`
- Stories: 36 hand-written (English and Pidgin; Nigeria and Kenya packs)

## Headline: missed emergencies = 0 (target: 0)

An emergency counts as caught if the rules put it on the severe branch or at the danger
check. It is missed only if it would be treated as not severe without asking.

| Check | Passed | Of |
|---|---|---|
| ack_clean | 1 | 1 |
| asked | 1 | 1 |
| category | 31 | 31 |
| clinical_complaint | 2 | 2 |
| emergency_caught | 12 | 12 |
| handoff | 2 | 2 |
| hospital | 5 | 5 |
| language | 31 | 31 |
| no_false_alarm | 18 | 18 |
| nonsense | 3 | 3 |
| not_nonsense | 31 | 31 |
| patient_group | 9 | 9 |
| reporter_role | 1 | 1 |
| subtype | 13 | 13 |
| summary_redacted | 1 | 1 |

| Story | Category | Decision | Result |
|---|---|---|---|
| emg-01 | emergency_refused | severe | PASS |
| emg-02 | emergency_refused | severe | PASS |
| emg-03 | neglect | severe | PASS |
| emg-04 | detention | severe | PASS |
| emg-05 | detention | severe | PASS |
| emg-06 | emergency_refused | severe | PASS |
| emg-07 | neglect | severe | PASS |
| emg-08 | emergency_refused | severe | PASS |
| emg-09 | neglect | severe | PASS |
| past-01 | abuse | not_severe | PASS |
| past-02 | abuse | not_severe | PASS |
| past-03 | neglect | not_severe | PASS |
| past-04 | emergency_refused | not_severe | PASS |
| past-05 | detention | not_severe | PASS |
| past-06 | abuse | not_severe | PASS |
| past-07 | neglect | not_severe | PASS |
| amb-01 | other | ask | PASS |
| amb-02 | neglect | ask | PASS |
| amb-03 | neglect | ask | PASS |
| amb-04 | emergency_refused | ask | PASS |
| clin-01 | other | not_severe | PASS |
| clin-02 | other | ask | PASS |
| oos-01 | other | ask | PASS |
| oos-02 | other | ask | PASS |
| oos-03 | other | not_severe | PASS |
| inj-01 | other | ask | PASS |
| inj-02 | abuse | not_severe | PASS |
| hand-01 | abuse | not_severe | PASS |
| hand-02 | other | ask | PASS |
| priv-01 | abuse | not_severe | PASS |
| ke-emg-01 | emergency_refused | severe | PASS |
| ke-emg-02 | detention | severe | PASS |
| ke-emg-03 | detention | severe | PASS |
| ke-past-01 | abuse | not_severe | PASS |
| ke-past-02 | neglect | not_severe | PASS |
| ke-lang-01 | abuse | not_severe | PASS |
