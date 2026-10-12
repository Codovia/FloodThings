# Unsent CWC station-history and semantics request

**Prepared for manual delivery only. Messages sent: zero.** No account has been
created and no institutional permission is represented as already granted.

To: Chief Engineer, Krishna & Godavari Basin Organisation, Central Water
Commission, Krishna Godavari Bhavan, H.No.11-4-648, A.C.Guards,
Hyderabad–500004. This role/address is from Annex I of the retained November2018
[Hydro-Meteorological Data Dissemination Policy](https://www.cwc.gov.in/sites/default/files/hddp2018_0.pdf),
PDF7. Reconfirm current routing through CWC before dispatch; the old policy's
telephone numbers and named officers are not presented as current contacts.

Subject: Unclassified Krishna-basin station data, field dictionary and
correction/QC records for a bounded research forecasting experiment.

Please confirm the currently applicable unclassified-data request procedure.
The published2018 policy §§6.1–6.3, PDF5, describes registered India-WRIS access,
and requests to the concerned Chief Engineer for unclassified records unavailable
there, with producer acknowledgement and without a secrecy undertaking. The
portal-linked2026 policy was previously identified as Final Draft; this request
does not assume its adoption or transfer rights.

FloodPulse proposes an independently evaluated **six-hour measured-stage
forecast**, initially at Huvinhedgi/Huvinahedgi `CW1KRU000339` on Krishna and
Sadalga/Sadalgi `CW1KRU000083` on Dudhganga. Stage prediction is distinct from
official danger-level exceedance and from mapped inundation. Gokak Falls
`CW1KRU000212` is deferred pending dated cross-section/reach clarification.

The raw files below are **already retained; a second full transfer is unnecessary**:

| Resource | Retained file | Required clarification |
|---|---|---|
| `7778f459-0e82-4681-9638-5e494c36fd42` | `rwl_manual_hr_cwc_007_1991_2020.csv` | Exact level reference, schedule, measurement/time and record QC |
| `f95150ea-c8fc-4740-8815-d9c34c9d53a3` | `river_discharge_manual_daily_cwc_ka_2001_2025.csv` | Session/aggregate meaning, time and observed/computed/revised flags |

Please provide the following for the **2013-06-01 to2020-05-31** common proposed
experiment window, and the metadata history needed to interpret it:

1. An authoritative source-station-to-CWC-code crosswalk, dated gauge/cross-section
   coordinates, river/catchment identity and relocation/correction records.
   Please explain differing published coordinates, including Sadalga2025/2026.
   If field divisions hold the records, please refer this request: the retained
   2025 SOP lists UKD Pune for Sadalga and LKD Hyderabad for Huvinhedigi.
2. The exact meaning and timezone of `Data Acquisition Time`, including whether
   time denotes observation, measurement-session start/end or an aggregate
   boundary. Specify cadence by season/site/year, session duration, missing-value
   codes, daylight/date conventions and intervals. A webpage-update IST clock
   does not resolve observation semantics.
3. Level-field units and datum: gauge reading versus MSL/RL elevation,
   benchmark/zero-gauge history, shifts, instrument changes and explicit relation
   to `RL_of_zeroGauge`/`MeanSeaLevel`. No numeric offset will be assumed.
4. Observed/computed/rating-curve/revised/discarded flags, validation and
   revision history, original record IDs, instrument/method uncertainty, and
   approved corrections for duplicate/conflicting timestamps. The aggregate
   Phase12F register identifies conflicts without silently choosing values.
   If the existing export omits these fields, supply a **station-filtered
   QC-augmented replacement or correction table**, not another basin-wide archive.
5. Original measurement release/availability records or an authoritative,
   historically applicable latency protocol for inputs. Distinguish final
   revised truth from what a forecaster could actually see at an issue time.
   If historical latency cannot be recovered, identify an authorized prospective
   read-only measurement feed and its issue/availability documentation.
6. Official warning/danger stage levels, effective dates and station/datum
   crosswalk for the requested years. The2025 SOP alone does not establish
   historical applicability. If discharge thresholds are offered, identify their
   independent flood rationale and dated high-flow rating-curve uncertainty;
   no statistical percentile will be called an official threshold.
7. Dated upstream basin delineation and rain-gauge associations with reuse
   permission, relevant upstream/reservoir release records and their issue-time
   availability. Basin information may extend outside Karnataka.
8. Rights for local research, attributed aggregate results, any proposed detailed
   measurement redistribution and source-forecast public display. Clarify
   NWDP Other(Open), CWC website copyright and third-party government geometry.

A source dictionary may resolve some blockers without transferring new values.
Receipt does not automatically authorize training: independent review must still
approve measurement quality, feature availability, sample adequacy and held-out
chronological/event evaluation. No operational warning or statewide prediction
claim is proposed in this request.

For unclassified records still unavailable, §6.4 describes an RTI route. Use the
current official CWC CPIO directory and procedure; do not reuse stale personal
contact details or apply classified-data AnnexIII/IV forms to Krishna by default.

Separate unsent forecast-access requests are specified in
[source_access_review.json](source_access_review.json): CWC FloodWatch documented
feed and display permission; IMD authorized FFG access; KSNDMC read-only alerts
and rights; account-owner verification of EWDS terms and a bounded native GloFAS
request. None has been dispatched by this phase.
