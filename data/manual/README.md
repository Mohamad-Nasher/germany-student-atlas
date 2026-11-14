# Hand-maintained inputs

Three small CSV files hold the figures that have no stable public API. Each ships
with only a header row; a file with no data rows makes that layer show as
"missing" on the map instead of being guessed. City names must match
`config/cities.csv` exactly; sector keys must match `config/sectors.csv`.

## rents.csv

| column | meaning |
|---|---|
| `city` | city name as in `config/cities.csv` |
| `wg_room_eur` | monthly rent for a room in a shared flat, EUR (preferred) |
| `rent_eur_m2` | net cold rent in EUR per m², used only when `wg_room_eur` is empty |
| `period` | what the figure refers to, e.g. `WS 2026/27` or `2022-05-15` |
| `source` | where you took it from |

Where to get it:
- **Shared-flat room rents by university city**: the Moses Mendelssohn Institut and
  WG-Gesucht.de publish average asking rents for about 90 university cities each
  semester (press releases at moses-mendelssohn-institut.de and wg-gesucht.de/presse).
- **Net cold rent per m² by municipality**: Zensus 2022, regional table
  "Gebäude und Wohnungen" at zensus2022.de. These are rents under existing
  contracts on 15 May 2022, so they sit well below today's asking rents.

Do not mix the two within one comparison if you can avoid it: one is asking
rents for rooms, the other contract rents for whole dwellings.

## students.csv

| column | meaning |
|---|---|
| `city` | city name as in `config/cities.csv` |
| `students_total` | all enrolled students at universities in the city |
| `students_international` | students with a foreign nationality |
| `semester` | e.g. `WS 2025/26` |
| `source` | where you took it from |

Where to get it: Destatis, "Statistik der Studierenden" (GENESIS table 21311,
students by university and nationality); sum the universities located in each
city. State statistical offices publish the same per university, often earlier.

## sector_official.csv (optional)

| column | meaning |
|---|---|
| `sector` | key from `config/sectors.csv` |
| `shortage_score` | 0–3 score from the federal agency's shortage analysis |
| `employment_change_pct` | year-on-year change in employment, if you have it |
| `source` | where you took it from |

Where to get it: Bundesagentur für Arbeit, "Fachkräfteengpassanalyse"
(statistik.arbeitsagentur.de → Interaktive Statistiken → Fachkräftebedarf). A
score of 2.0 or more is the agency's own threshold for a shortage occupation.
