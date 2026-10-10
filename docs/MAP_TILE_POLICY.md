# Background map repair and demonstration limits

Reviewed 10 October 2026 against commit
`254a50c2db459e40ec11291431e6b8c0bd9a8c67` on
`feature/karnataka-data-foundation`. Antigravity's resize, mobile navigation,
legend and admin form fixes are present and retained.

## Confirmed cause and limits of reproduction

The Vite HTML response sets `Referrer-Policy: same-origin`. Before the repair,
Leaflet's cross-origin requests to
`https://tile.openstreetmap.org/{z}/{x}/{y}.png` carried **no Referer**.
This violates the official [OSMF tile usage policy](https://operations.osmfoundation.org/policies/tiles/)
sections 3.1 and 3.4, which require an accurate web-page referrer. It is a
concrete application defect and a plausible policy-blocking cause.

The user's reported 403 was **not reproduced** in this environment. Independent
installed Google Chrome 154.0.8037.57 returned 99 HTTP 200 tile responses in the
before audit despite the missing referrer. Therefore the exact server-side
reason for the reported block, including a possible prior network restriction,
remains unverified. An IDE browser's success does not disprove an external
browser or network failure.

## Repair and provider decision

All existing Leaflet maps share `src/mapBasemap.js`. The provider remains
standard OpenStreetMap, with visible **© OpenStreetMap contributors** attribution
and a link to its copyright page. Each tile image has
`referrerPolicy: 'origin'`, sending the genuine app origin only. The after audit
observed `Referer: http://127.0.0.1:14180/`. Paths, queries, credentials and admin
routes are not included. The global `same-origin` privacy header and the backend
session/CSRF protections are unchanged.

Ordinary viewport requests use browser HTTP caching. There is no tile proxy,
User-Agent substitution, address rotation, prefetch, offline download,
cache bypass or automatic host switching. Idle tile updates and a small normal
viewport buffer limit unnecessary requests. The first tile error removes only
the basemap and stops further requests from that layer; reviewed polygons,
markers, coordinate selection and their independent source attribution remain.
The notice makes missing background coverage explicit.

A bounded alternative-provider review did not establish a suitable new provider
without another permission/configuration step. [CARTO's official basemap FAQ](https://docs.carto.com/faqs/carto-basemaps)
requires an API key for raster tiles; no key was registered or service accepted.
[OSM France's usage conditions](https://www.openstreetmap.fr/usage/)
exclude private/login/intranet use, making an automatic switch across the admin
workflow unsuitable. Other reviewed community documentation was inaccessible or
insufficient to confirm applicability. No undocumented replacement was used.
OSMF provides a best-effort service without availability guarantees; this repair
cannot lift a separately imposed provider/network block. Public or larger-scale
hosting needs its own service-capacity and terms review.

## Explicit background-disabled mode

The default `VITE_MAP_BASEMAP=osm` needs no credential. In the ignored
`frontend/.env.local`, `VITE_MAP_BASEMAP=none` requests no background tiles.
Restart Vite, or rebuild a production frontend, after changing it. Unknown values
also fail closed. Local overlays remain available. This is not an offline tile
cache or an alternative map service. Never put private secrets in frontend Vite
variables.

## Independent browser evidence

The existing running loopback application and real PostgreSQL directory were
inspected through installed Google Chrome in an automated headless session with
a separate browser context, independently of the IDE browser. The user's exact
external Chrome profile/network was not reproduced.
All five routes (`/`, `/weather`, `/flood-map`, `/shelters`, `/admin`) were reviewed
at **1366×768, 1920×1080 and 390×844**. The after audit recorded **75 HTTP 200
tile responses**, successfully decoded visible map images, zero page exceptions
and no horizontal overflow in 15 views. Requests carried the real origin
referrer; no provider response was substituted in this audit.

Separate live workflows selected **Kundapur and Mangaluru** through the existing
directory. Each returned HTTP 200 real Open-Meteo weather with seven dates and
HTTP 200 inference from `rainfall_logistic_v1`, with no calibrated probability.
In-app page navigation retained weather state without duplicate requests.
Udupi displayed the original 56 historical cells; Kolar's no-public-evidence
state and the separate unavailable hazard layer remained explicit. The real
operational shelter directory remained empty.

Controlled browser outage screenshots and automated tile/HTTP fixtures are
labelled separately; they are not evidence of live provider availability.
Automated tile-policy checks use an isolated image fixture, while the independent
Chrome audit above establishes actual external tile loading.

Local, ignored receipts and screenshots:

- `data/recovery/ui_map_repair_v1/before/` and `after/`: five routes, three sizes.
- `after/report.json`: actual tile statuses/referrers and rendering dimensions.
- `live-workflows.json`: actual selected-location weather/model results.
- `after/controlled-weather-outage.png` and `controlled-shelter-outage.png`:
  explicitly simulated error-state review.

No backend, database schema, geographic evidence or model artifact changed.
Historical flooding is not live flooding; modelled heavy rainfall is not flood
probability, shelter approval or an automated warning.
