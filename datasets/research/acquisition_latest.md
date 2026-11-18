# Phase 3 acquisition experiment `p3-20261118T031243Z`

- commit `bafdc90304f3d315c681d62fcd701c81cd26068e`
- generator `nace-gen-3.0`
- tasks per seed: 24, seeds [11, 23, 37]
- hardware: 2 cores, torch 2.15.0+cu132
- production memory unchanged: **True**

## Hidden-test pass rate by arm

| arm | tasks | hidden pass | rate | 95% CI | dev pass | test-fitted | mean candidates | mean s |
|---|---|---|---|---|---|---|---|---|
| A | 66 | 0 | 0.000 | [0.000, 0.000] | 0 | 0 | 0.0 | 0.52 |
| B | 66 | 33 | 0.500 | [0.379, 0.621] | 33 | 0 | 0.0 | 0.04 |
| C | 66 | 40 | 0.606 | [0.485, 0.727] | 46 | 6 | 180.4 | 0.13 |
| D | 66 | 40 | 0.606 | [0.485, 0.727] | 46 | 6 | 155.4 | 0.12 |
| E | 66 | 40 | 0.606 | [0.485, 0.727] | 46 | 3 | 116.5 | 0.1 |
| F1 | 66 | 36 | 0.545 | [0.424, 0.667] | 42 | 6 | 29.8 | 0.09 |
| F2 | 66 | 28 | 0.424 | [0.303, 0.545] | 32 | 4 | 162.2 | 0.09 |
| F3 | 66 | 31 | 0.470 | [0.348, 0.591] | 37 | 6 | 180.0 | 0.1 |

## Verdicts by arm

- **A**: {'exception': 66}
- **B**: {'no_result': 33, 'pass': 33}
- **C**: {'exception': 23, 'pass': 40, 'wrong_value': 3}
- **D**: {'exception': 23, 'pass': 40, 'wrong_value': 3}
- **E**: {'exception': 23, 'pass': 40, 'wrong_value': 3}
- **F1**: {'no_result': 24, 'pass': 36, 'exception': 3, 'wrong_value': 3}
- **F2**: {'no_result': 34, 'pass': 28, 'exception': 3, 'wrong_value': 1}
- **F3**: {'no_result': 29, 'pass': 31, 'exception': 3, 'wrong_value': 3}

## Notes

Every arm is scored by the independent evaluator on hidden inputs generated from a
private salt. `dev pass` counts tasks whose program satisfied the visible dev tests;
`test-fitted` counts tasks that passed dev and failed hidden — the honest measure of
how much of the apparent success is overfitting to the visible examples.
