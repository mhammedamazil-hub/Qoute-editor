# Sealed learning benchmark

Generated 2026-11-15T16:13:46Z · 22 tasks · sealed: True

## Headline

| metric | value |
|---|---|
| final success | 20/22 (90.9%) |
| first-attempt success | 20/22 (90.9%) |
| confirmed in sandbox | 20/22 |
| replay passed (fresh process) | 4/4 |
| generalisation passed | 3/3 |
| mean attempts | 1.18 |
| mean seconds/task | 2.32 |
| peak RSS | 65.5 MB |
| search tokens | 5923 |

## By category

| category | n | final | first |
|---|---|---|---|
| data | 4 | 4/4 (100%) | 4/4 (100%) |
| debugging | 2 | 2/2 (100%) | 2/2 (100%) |
| file | 2 | 2/2 (100%) | 2/2 (100%) |
| math | 4 | 4/4 (100%) | 4/4 (100%) |
| multistep | 1 | 1/1 (100%) | 1/1 (100%) |
| new_api | 1 | 1/1 (100%) | 1/1 (100%) |
| python | 5 | 3/5 (60%) | 3/5 (60%) |
| tool_discovery | 1 | 1/1 (100%) | 1/1 (100%) |
| visual | 1 | 1/1 (100%) | 1/1 (100%) |
| visual_inspection | 1 | 1/1 (100%) | 1/1 (100%) |

## Per task

| task | category | mode | first | final | attempts | s | tokens | replay | variant |
|---|---|---|---|---|---|---|---|---|---|
| sum_evens | python | acquisition | ✓ | ✓ | 1 | 0.15 | 36 | — | — |
| double_all | python | acquisition | ✓ | ✓ | 1 | 0.08 | 84 | — | — |
| range_span | math | acquisition | ✓ | ✓ | 1 | 0.06 | 24 | — | — |
| count_positive | math | acquisition | ✓ | ✓ | 1 | 0.07 | 32 | — | — |
| abs_all | python | acquisition | ✓ | ✓ | 1 | 0.07 | 80 | — | — |
| product | math | acquisition | ✓ | ✓ | 1 | 0.06 | 20 | — | — |
| evens_sorted | data | acquisition | ✓ | ✓ | 1 | 0.11 | 673 | — | — |
| unique_upper | data | acquisition | ✓ | ✓ | 1 | 0.11 | 573 | — | — |
| median | math | acquisition | ✓ | ✓ | 1 | 0.08 | 44 | — | — |
| word_lengths | data | acquisition | ✓ | ✓ | 1 | 0.08 | 112 | — | — |
| run_length_encode | python | acquisition | ✗ | ✗ | 3 | 0.99 | 1907 | — | — |
| caesar | python | acquisition | ✗ | ✗ | 3 | 0.84 | 1907 | — | — |
| count_lines | file | acquisition | ✓ | ✓ | 1 | 0.02 | 4 | — | — |
| sum_column | file | acquisition | ✓ | ✓ | 1 | 0.03 | 103 | — | — |
| write_report | data | acquisition | ✓ | ✓ | 1 | 0.07 | 120 | — | — |
| fix_off_by_one | debugging | acquisition | ✓ | ✓ | 1 | 0.06 | 52 | — | — |
| fix_mutation | debugging | acquisition | ✓ | ✓ | 1 | 0.06 | 60 | — | — |
| visual_headline | visual | acquisition+adaptation | ✓ | ✓ | 1 | 12.32 | 17 | ✓ | ✓ |
| tool_discovery_shape | tool_discovery | acquisition | ✓ | ✓ | 1 | 11.99 | 23 | ✓ | — |
| multistep_poster | multistep | acquisition+adaptation | ✓ | ✓ | 1 | 12.05 | 38 | ✓ | ✓ |
| api_typography | new_api | acquisition+adaptation | ✓ | ✓ | 1 | 11.77 | 14 | ✓ | ✓ |
| visual_inspection | visual_inspection | retrieval | ✓ | ✓ | 1 | 0.0 | 0 | — | — |

## Failures (reported, not hidden)

- **run_length_encode** (python, hard): exhausted 1907 candidates up to depth 2
- **caesar** (python, hard): exhausted 1907 candidates up to depth 2
