# Regression results

Generated from `docs/data/cities.json` (2026-11-14T12:17:19+00:00).

> **These results use the synthetic preview data and mean nothing.**
> Run `atlas build` with real inputs, then `atlas analyze` again.

### Rent

`np.log(rent_monthly) ~ np.log(students_total) + intl_share + east`

| term | coef. | robust s.e. | p |
|---|---:|---:|---:|
| Intercept | 5.787 | 0.807 | 0.000 |
| np.log(students_total) | 0.055 | 0.072 | 0.447 |
| intl_share | -0.367 | 0.651 | 0.573 |
| east | -0.127 | 0.094 | 0.177 |

N = 63, R² = 0.047

### Job density

`np.log(jobs_per_1000) ~ np.log(students_total) + intl_share + np.log(rent_monthly) + east`

| term | coef. | robust s.e. | p |
|---|---:|---:|---:|
| Intercept | 4.079 | 1.657 | 0.014 |
| np.log(students_total) | -0.123 | 0.091 | 0.177 |
| intl_share | 0.908 | 1.012 | 0.369 |
| np.log(rent_monthly) | -0.150 | 0.236 | 0.527 |
| east | 0.345 | 0.132 | 0.009 |

N = 63, R² = 0.120
