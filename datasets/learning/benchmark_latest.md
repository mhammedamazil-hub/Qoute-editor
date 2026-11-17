# Sealed learning benchmark

Generated 2026-11-15T17:06:24Z · 17 tasks · sealed: True

## Headline

| metric | value |
|---|---|
| final success | 15/17 (88.2%) |
| first-attempt success | 15/17 (88.2%) |
| confirmed in sandbox | 15/17 |
| replay passed (fresh process) | 0/0 |
| generalisation passed | 0/0 |
| mean attempts | 1.24 |
| mean seconds/task | 0.19 |
| peak RSS | 47.5 MB |
| search tokens | 5831 |

## By category

| category | n | final | first |
|---|---|---|---|
| data | 4 | 4/4 (100%) | 4/4 (100%) |
| debugging | 2 | 2/2 (100%) | 2/2 (100%) |
| file | 2 | 2/2 (100%) | 2/2 (100%) |
| math | 4 | 4/4 (100%) | 4/4 (100%) |
| python | 5 | 3/5 (60%) | 3/5 (60%) |

## Per task

| task | category | mode | first | final | attempts | s | tokens | replay | variant |
|---|---|---|---|---|---|---|---|---|---|
| sum_evens | python | acquisition | ✓ | ✓ | 1 | 0.09 | 36 | — | — |
| double_all | python | acquisition | ✓ | ✓ | 1 | 0.07 | 84 | — | — |
| range_span | math | acquisition | ✓ | ✓ | 1 | 0.07 | 24 | — | — |
| count_positive | math | acquisition | ✓ | ✓ | 1 | 0.09 | 32 | — | — |
| abs_all | python | acquisition | ✓ | ✓ | 1 | 0.09 | 80 | — | — |
| product | math | acquisition | ✓ | ✓ | 1 | 0.07 | 20 | — | — |
| evens_sorted | data | acquisition | ✓ | ✓ | 1 | 0.12 | 673 | — | — |
| unique_upper | data | acquisition | ✓ | ✓ | 1 | 0.11 | 573 | — | — |
| median | math | acquisition | ✓ | ✓ | 1 | 0.07 | 44 | — | — |
| word_lengths | data | acquisition | ✓ | ✓ | 1 | 0.08 | 112 | — | — |
| run_length_encode | python | acquisition | ✗ | ✗ | 3 | 1.13 | 1907 | — | — |
| caesar | python | acquisition | ✗ | ✗ | 3 | 0.88 | 1907 | — | — |
| count_lines | file | acquisition | ✓ | ✓ | 1 | 0.02 | 4 | — | — |
| sum_column | file | acquisition | ✓ | ✓ | 1 | 0.04 | 103 | — | — |
| write_report | data | acquisition | ✓ | ✓ | 1 | 0.08 | 120 | — | — |
| fix_off_by_one | debugging | acquisition | ✓ | ✓ | 1 | 0.07 | 52 | — | — |
| fix_mutation | debugging | acquisition | ✓ | ✓ | 1 | 0.09 | 60 | — | — |

## Failures (reported, not hidden)

- **run_length_encode** (python, hard): exhausted 1907 candidates up to depth 2
- **caesar** (python, hard): exhausted 1907 candidates up to depth 2
