# Phase 3.10 — Controlled Multi-Chunk Historical Extraction

## 1. Objective

This document reports the empirical results of **Phase 3.10**, which validated the Phase 3.9 historical meteorological extraction engine across a deliberately selected set of five real Open-Meteo ERA5 reanalysis chunks covering Karnataka.

The purpose of this phase was to test:
- Multiple historical years (1979, 1980, 1988, 1994)
- Multiple spatial batches (Batch 1, Batch 2, Batch 3)
- Leap-year vs. non-leap-year hourly length handling (8,784 vs. 8,760 hours)
- Manifest state transitions and atomic persistence
- Checkpoint/resume and cached-chunk idempotency
- Strict physical and structural validation
- Raw-data provenance and SHA-256 integrity
- Actual network request latencies and compressed payload sizes

> [!IMPORTANT]
> **Operational Status & Scope Boundary:**
> The extraction engine was validated across five controlled real ERA5 chunks spanning multiple years, spatial batches, and leap/non-leap years. These results support controlled expansion but do not establish behavior of the complete 858-chunk extraction.
> No database records were modified, no migrations created, no ML models trained, and no historical data inserted into PostgreSQL.

---

## 2. Controlled Chunk Selection

Exactly five chunks were evaluated:

| Label | Chunk ID | Year | Batch | Leap Year? | Selection Rationale |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **A** | `era5_1994_batch_001` | 1994 | 1 | No | Already extracted in Phase 3.9; used to verify existing cache/idempotency. |
| **B** | `era5_1994_batch_002` | 1994 | 2 | No | New spatial batch in the same historical year; tests batch coordinate progression. |
| **C** | `era5_1988_batch_001` | 1988 | 1 | **Yes** | Mid-period monsoon year and leap year; verifies 8,784-hour leap year validation. |
| **D** | `era5_1980_batch_002` | 1980 | 2 | **Yes** | Early-period leap year in spatial batch 2; tests multi-dimensional variation. |
| **E** | `era5_1979_batch_003` | 1979 | 3 | No | Earliest tested decade and third spatial batch; tests boundary grid cells. |

---

## 3. Empirical Extraction & Performance Audit

### Summary Table

| Chunk | Year | Batch | Expected Records | Actual Records | HTTP Status | Latency | Uncompressed | Compressed | Validation | State |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **A** | 1994 | 1 | 87,600 | 87,600 | Cached (200) | 0.0s (2.83s in 3.9) | 3,339,997 B | 539,849 B | **PASS** | `SUCCEEDED` |
| **B** | 1994 | 2 | 87,600 | 87,600 | 200 OK | 11.22s | 3,333,839 B | 537,472 B | **PASS** | `SUCCEEDED` |
| **C** | 1988 | 1 | 87,840 | 87,840 | 200 OK | 7.41s | 3,347,795 B | 540,936 B | **PASS** | `SUCCEEDED` |
| **D** | 1980 | 2 | 87,840 | 87,840 | 200 OK | 5.08s | 3,343,221 B | 541,379 B | **PASS** | `SUCCEEDED` |
| **E** | 1979 | 3 | 87,600 | 87,600 | 200 OK | 3.10s | 3,333,629 B | 533,341 B | **PASS** | `SUCCEEDED` |

### Aggregate Metrics

- **Successful Network Requests:** 4 (Chunks B, C, D, E)
- **Cached Evaluations:** 5 (Chunk A in initial run; Chunks B, C, D, E in subsequent idempotency test)
- **Failures:** 0
- **Retries Observed:** 0
- **Validation Failures:** 0
- **Total Hourly Records:** **438,480 records** across all 5 chunks
- **Downloaded Compressed Bytes (New Chunks B–E):** 2,153,128 bytes (~2.15 MB)
- **Total Compressed Bytes on Disk (All 5 Chunks):** 2,692,977 bytes (~2.69 MB)
- **Downloaded Uncompressed Bytes (New Chunks B–E):** 13,358,484 bytes (~13.36 MB)
- **Total Uncompressed Bytes (All 5 Chunks):** 16,698,481 bytes (~16.70 MB)
- **Average Network Latency:** 6.705 seconds (range: 3.104s to 11.223s)
- **Maximum Network Latency:** 11.223 seconds (Chunk B)
- **Minimum Network Latency:** 3.104 seconds (Chunk E)

---

## 4. Cache & Idempotency Behavior

### Initial Cache Verification (Chunk A)
Re-running the extraction command for `era5_1994_batch_001`:
```text
Extraction Summary:
  Total Processed: 1
  Succeeded:       0
  Skipped (Cached):1
  Failed:          0
```
Chunk A was detected on disk, its compressed SHA-256 matched the manifest, and the network request was skipped.

### Post-Extraction Cache Verification (Chunks B, C, D, E)
After extracting Chunks B, C, D, and E, the identical CLI commands were re-executed for each chunk. All four were skipped without issuing any HTTP requests:
- `era5_1994_batch_002`: `Skipped (Cached): 1`
- `era5_1988_batch_001`: `Skipped (Cached): 1`
- `era5_1980_batch_002`: `Skipped (Cached): 1`
- `era5_1979_batch_003`: `Skipped (Cached): 1`

---

## 5. Leap-Year Handling

- **Non-Leap Years (1979, 1994):** Exactly 8,760 hourly records per location ($365\text{ days} \times 24\text{ hours} = 8,760$). Validated start at `YYYY-01-01T00:00` and end at `YYYY-12-31T23:00`.
- **Leap Years (1980, 1988):** Exactly 8,784 hourly records per location ($366\text{ days} \times 24\text{ hours} = 8,784$). Validated continuous hourly progression across February 29 with zero gaps or timestamp shifting.
- The validator dynamically selected expected hour counts using Python's `calendar.isleap(year)` without hardcoded overrides.

---

## 6. Validation & Physical Consistency

Across all 438,480 hourly records in the five chunks:
1. **Coordinate Tolerance:** All 10 locations in each chunk snapped to within $\pm 0.0001^\circ$ of requested grid centers.
2. **Timestamp Progression:** Strictly monotonic $+1\text{h}$ intervals throughout all 8,760 or 8,784 hours.
3. **Duplicates / Gaps:** 0 duplicate timestamps, 0 missing timestamps.
4. **Null Rates:** 0 null values across all 4 variables (`precipitation`, `temperature_2m`, `relative_humidity_2m`, `surface_pressure`).
5. **Physical Bounds:**
   - Precipitation: $\ge 0.0\text{ mm}$ (0 negative values).
   - Relative Humidity: $0.0\% \le \text{RH} \le 100.0\%$ (0 out-of-bounds values).
   - Numeric Finiteness: 0 `NaN`, 0 `Inf`, 0 non-numeric strings.

---

## 7. Raw File Integrity & Provenance

Every raw `.json.gz` payload was audited on disk:

| Chunk ID | Raw File Path | Compressed SHA-256 | Uncompressed SHA-256 |
| :--- | :--- | :--- | :--- |
| `era5_1994_batch_001` | `data/raw/era5_historical/year=1994/batch_001.json.gz` | `e41266e8792188bc806e94df4c4423c2fa89acbabee351897077bca3399ad4be` | `b6aaa5d92b6572a3b22ee14e0292df056f1a6348192d2da6a55a36a0927de4f9` |
| `era5_1994_batch_002` | `data/raw/era5_historical/year=1994/batch_002.json.gz` | `bd1900e62961a507cb6bde54789cb9fe200a1875925a69534136c0d9485ddb34` | `cc2dd2b61906af2a7823662c7158566b0fc636ca510eecd42bdf73d581005223` |
| `era5_1988_batch_001` | `data/raw/era5_historical/year=1988/batch_001.json.gz` | `6721121a84a57107dc71ea234e652a5c4af7f0ef2b4408844ea50ac7727419c5` | `6dbf65d7d89f7ccc437eff1fec51d565cb9e205c4a0ff1fa26baa721bd72b411` |
| `era5_1980_batch_002` | `data/raw/era5_historical/year=1980/batch_002.json.gz` | `47ebcc58de3287e91100927773e5a526f1333bd637b7ee51c0655454bd0fe5c2` | `7c5454144482aa599d9ca2f686c0e6fcb95b93b86108c93dab2e9cf5ceb681ac` |
| `era5_1979_batch_003` | `data/raw/era5_historical/year=1979/batch_003.json.gz` | `b003cc0e1fd028ec655df0630cc6efeb5dc750876d8ff3535d11e2a94f12e3c4` | `34b6cdb5c12a6e028a6ed738a049efd527d6c44daa0db73ef36eb64704ff96b6` |

All 13 programmatic integrity checks passed:
- File existence confirmed.
- Compressed file SHA-256 matches manifest.
- Decompression succeeds without errors.
- Uncompressed payload SHA-256 matches manifest.
- JSON structure conforms to expected schema.
- Companion `.meta.json` records complete request URL, timestamps, and parameters.

---

## 8. Retry and Failure Observations

- **Observation:** No provider throttling or retry event was observed during this controlled run; retry behavior remains covered by automated tests but has not been empirically exercised against a live failure.
- All four network requests returned HTTP 200 on their first attempt.

---

## 9. Database Safety Verification

Database table row counts were audited before and after the controlled extractions:

| Table | Baseline Count | Post-Test Count | Change |
| :--- | :---: | :---: | :---: |
| `weather_observations` | 397 | 397 | **0 (Unchanged)** |
| `rainfall_observations` | 397 | 397 | **0 (Unchanged)** |
| `districts` | 31 | 31 | **0 (Unchanged)** |
| `taluks` | 240 | 240 | **0 (Unchanged)** |

Zero database mutations occurred.

---

## 10. Git Safety Verification

- `git check-ignore data/raw/era5_historical/` confirmed that raw data files under `data/raw/` are ignored.
- `git status --short` confirmed no raw data files, compressed files, or local manifest files are staged or tracked.

---

## 11. Limitations & Unresolved Issues

Operational limitations remain intentionally untested at full scale. The 858-chunk extraction has not been executed, so provider throttling behavior, long-running failure recovery, and production-scale throughput remain to be monitored during controlled expansion.
