"""Build the verified Karnataka river forecast points (GloFAS v4 via Open-Meteo).

A candidate becomes a forecast point only if BOTH checks pass:
1. Geography: OpenStreetMap has a river with the expected name within 3 km of the model cell
   (the model's 5 km grid can otherwise pick a neighbouring stream).
2. Flood history: a documented flood (dated, sourced) falls within 3 days of one of the cell's
   three largest annual peaks in the GloFAS v4 reanalysis (1997-2021, the years `consolidated_v4` covers).
Flood levels (2-, 5- and 10-year) are a Gumbel fit to the cell's own 25 annual maxima, as
GloFAS does for its own thresholds, so model bias is not compared against observed levels.

Run: python3 scripts/build_karnataka_river_points.py  (network; writes data/reference/...)
"""
import hashlib, json, math, statistics, time, urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'data/reference/karnataka_river_points_v1/points.json'
FLOOD = 'https://flood-api.open-meteo.com/v1/flood'
OVERPASS = 'https://overpass-api.de/api/interpreter'
YEARS = (1997, 2021)  # complete years of the consolidated v4 reanalysis (it starts 1997 and ends July 2022)
UA = {'User-Agent': 'FloodPulse-river-points/1.0'}

# Documented floods used for the history check (date of reported peak or highest-flood-level crossing).
EVENTS = {
    'krishna_2019': ('2019-08-08', 'Krishna and tributaries crossed highest flood levels in Karnataka, 8 Aug 2019',
                     'https://sandrp.in/2019/08/12/krishna-basin-floods-in-karnataka-the-role-of-dams/'),
    'ghataprabha_2019': ('2019-08-09', 'Ghataprabha at Gokak Falls new record level, crossed 5 Aug, peak 9 Aug 2019 (CWC data)',
                         'https://sandrp.in/2019/10/03/breaching-historic-flood-levels-many-times-over-aftermath-of-ghataprabha-floods-2019/'),
    'kabini_2018': ('2018-08-18', 'Kabini dam releases inundated Nanjangud, 18 Aug 2018',
                    'https://sandrp.in/2018/11/08/hfl-crossing-flood-events-during-india-sw-monsoon-2018/'),
    'cauvery_2018': ('2018-08-16', 'Cauvery at Chunchunkatte above highest flood level 14-18 Aug 2018 (CWC)',
                     'https://sandrp.in/2018/11/08/hfl-crossing-flood-events-during-india-sw-monsoon-2018/'),
    'netravati_2019': ('2019-08-10', 'Netravati at Bantwal 11.6 m against an 8.5 m danger level, 10 Aug 2019',
                       'https://www.deccanherald.com/india/karnataka/rain-recedes-but-situation-still-grim-in-dk-752845.html'),
    'north_karnataka_2009': ('2009-10-02', 'North Karnataka floods, Krishna and Tungabhadra overflowing, 28 Sep - 4 Oct 2009',
                             'https://earthobservatory.nasa.gov/images/40601/flooding-along-the-krishna-river'),
    'kali_2019': ('2019-08-06', 'Kadra dam releases flooded Kali river villages; Navy rescued over 300 people near Kadra, 6 Aug 2019',
                  'https://sandrp.in/2019/08/31/unprecedented-dam-flood-situation-in-uttara-kannada-in-aug-2019/'),
    'bhima_2020': ('2020-10-17', 'Bhima record flood in Afzalpur taluk, Sonna barrage release, 15-19 Oct 2020',
                   'https://www.deccanherald.com/state/kalaburagi/record-8l-cusecs-of-water-released-from-sonna-barrage-into-bhima-river-villages-inundated-903258.html'),
}

CANDIDATES = []  # filled at the bottom of the file


def http(url, data=None, tries=6):
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read()
                return json.loads(raw), hashlib.sha256(raw).hexdigest()
        except urllib.error.HTTPError as error:
            if error.code in (429, 502, 503, 504) and attempt < tries - 1:
                time.sleep(25)
                continue
            raise


def gumbel(annual_maxima, years):
    mean, sd = statistics.mean(annual_maxima), statistics.stdev(annual_maxima)
    alpha = sd * math.sqrt(6) / math.pi
    mu = mean - 0.5772156649 * alpha
    return round(mu - alpha * math.log(-math.log(1 - 1 / years)), 1)


def episodes(days, values, level):
    # Separate runs of days above a level; a run ends after 3 days below it.
    runs, current, gap = [], None, 0
    for day, value in zip(days, values):
        if value is not None and value > level:
            if current is None: current = {'start': day, 'end': day, 'peak_m3s': value}
            current['end'], current['peak_m3s'], gap = day, max(current['peak_m3s'], value), 0
        elif current is not None:
            gap += 1
            if gap > 3: runs.append(current); current, gap = None, 0
    if current: runs.append(current)
    return [{**r, 'peak_m3s': round(r['peak_m3s'], 1)} for r in runs]


def osm_rivers(lat, lon):
    query = f'[out:json][timeout:60];way(around:3000,{lat},{lon})["waterway"="river"]["name"];out tags;'
    body, _ = http(OVERPASS, data=urllib.parse.urlencode({'data': query}).encode())
    return sorted({w['tags'].get('name:en') or w['tags']['name'] for w in body['elements']})


def build(candidate):
    lat, lon = candidate['query_point']
    params = {'latitude': lat, 'longitude': lon, 'daily': 'river_discharge', 'models': 'consolidated_v4',
              'start_date': f'{YEARS[0]}-01-01', 'end_date': f'{YEARS[1]}-12-31'}
    body, sha = http(FLOOD + '?' + urllib.parse.urlencode(params))
    peaks = {}
    for day, value in zip(body['daily']['time'], body['daily']['river_discharge']):
        if value is not None and value > peaks.get(day[:4], (-1, ''))[0]:
            peaks[day[:4]] = (value, day)
    if len(peaks) != YEARS[1] - YEARS[0] + 1:
        raise ValueError(f"{candidate['id']}: incomplete annual maxima")
    maxima = [v for v, _ in peaks.values()]
    top3 = sorted(peaks.values(), reverse=True)[:3]
    names = osm_rivers(body['latitude'], body['longitude'])
    geography_ok = any(candidate['river'].lower() in n.lower() for n in names)
    matches = []
    for key in candidate['events']:
        when, text, url = EVENTS[key]
        for value, day in top3:
            if abs((date.fromisoformat(day) - date.fromisoformat(when)).days) <= 3:
                matches.append({'event': text, 'event_date': when, 'source': url, 'model_peak_date': day, 'model_peak_m3s': round(value, 1)})
    history_ok = bool(matches)
    # Hindcast with the same levels the live forecast uses: episodes above the 5- and 2-year levels.
    levels = {y: gumbel(maxima, y) for y in (2, 5, 10)}
    above5 = episodes(body['daily']['time'], body['daily']['river_discharge'], levels[5])
    above2 = episodes(body['daily']['time'], body['daily']['river_discharge'], levels[2])
    event_hits = [{'event_date': EVENTS[k][0], 'inside_5_year_episode': any(abs((date.fromisoformat(EVENTS[k][0]) - date.fromisoformat(e['start'])).days) <= 3 or e['start'] <= EVENTS[k][0] <= e['end'] for e in above5)} for k in candidate['events']]
    return {
        'id': candidate['id'], 'river': candidate['river'], 'place': candidate['place'], 'district': candidate['district'],
        'query_point': {'latitude': lat, 'longitude': lon},
        'grid': {'latitude': round(body['latitude'], 3), 'longitude': round(body['longitude'], 3)},
        'accepted': geography_ok and history_ok,
        'checks': {'osm_named_rivers_within_3km': names, 'geography_ok': geography_ok,
                   'top3_annual_peaks': [{'date': d, 'm3s': round(v, 1)} for v, d in top3],
                   'documented_flood_matches': matches, 'history_ok': history_ok},
        'hindcast': {'years': list(YEARS), 'episodes_above_5_year': len(above5), 'episodes_above_2_year': len(above2),
                     'documented_events': event_hits, 'above_5_year': above5},
        'flood_levels_m3s': {f'{y}_year': levels[y] for y in (2, 5, 10)},
        'mean_annual_maximum_m3s': round(statistics.mean(maxima), 1),
        'history': {'model': 'consolidated_v4', 'years': list(YEARS), 'annual_maxima': len(maxima), 'response_sha256': sha},
    }


def main():
    points = []
    for candidate in CANDIDATES:
        points.append(build(candidate))
        print(f"{points[-1]['id']:24s} accepted={points[-1]['accepted']} grid={points[-1]['grid']} "
              f"osm={points[-1]['checks']['osm_named_rivers_within_3km']} matches={len(points[-1]['checks']['documented_flood_matches'])} "
              f"5y-episodes={points[-1]['hindcast']['episodes_above_5_year']} 2y-episodes={points[-1]['hindcast']['episodes_above_2_year']} "
              f"events-in-5y={[e['inside_5_year_episode'] for e in points[-1]['hindcast']['documented_events']]} "
              f"levels={points[-1]['flood_levels_m3s']}", flush=True)
        time.sleep(8)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        'version': 'karnataka_river_points_v1', 'built_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'source': {'name': 'Copernicus GloFAS v4 via Open-Meteo Flood API', 'url': 'https://open-meteo.com/en/docs/flood-api', 'license': 'CC BY 4.0'},
        'geography_source': {'name': 'OpenStreetMap (Overpass API)', 'url': 'https://www.openstreetmap.org/copyright', 'license': 'ODbL 1.0'},
        'method': __doc__.strip(), 'points': points}, indent=1, ensure_ascii=False) + '\n')
    print('wrote', OUT, sum(p['accepted'] for p in points), 'accepted of', len(points))


def candidate(id, river, place, district, lat, lon, events):
    CANDIDATES.append({'id': id, 'river': river, 'place': place, 'district': district, 'query_point': (lat, lon), 'events': events})


# Query points are model cell centres found by testing cells along each river near the town.
candidate('krishna_kudachi', 'Krishna', 'Kudachi', 'Belagavi', 16.625, 74.875, ['krishna_2019', 'north_karnataka_2009'])
candidate('ghataprabha_gokak', 'Ghataprabha', 'Gokak', 'Belagavi', 16.175, 74.825, ['ghataprabha_2019'])
candidate('kabini_nanjangud', 'Kabini', 'Nanjangud', 'Mysuru', 12.175, 76.725, ['kabini_2018'])
candidate('netravati_bantwal', 'Netravati', 'Bantwal', 'Dakshina Kannada', 12.875, 74.925, ['netravati_2019'])
candidate('tungabhadra_hampi', 'Tungabhadra', 'Hampi', 'Vijayanagara', 15.325, 76.375, ['north_karnataka_2009'])
candidate('kali_dandeli', 'Kali', 'Dandeli', 'Uttara Kannada', 15.175, 74.675, ['kali_2019'])
# Expected to fail the history check; kept so the rejection is recorded with its evidence.
candidate('bhima_afzalpur', 'Bhima', 'Afzalpur', 'Kalaburagi', 17.125, 76.425, ['bhima_2020'])
candidate('cauvery_srirangapatna', 'Kaveri', 'Srirangapatna', 'Mandya', 12.425, 76.675, ['cauvery_2018'])

if __name__ == '__main__':
    main()
