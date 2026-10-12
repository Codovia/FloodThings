#!/usr/bin/env python3
"""Bounded primary-source metadata receipts for Phase12E; no full raster transfer.

No authentication headers, cookies, credentials, model fits or restricted geometry
uploads. Existing receipts are immutable. Raster ZIP/SAFE/HDF/NetCDF URLs are not
accepted by this metadata command. Native acquisition needs a separate approval.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/direct_flood_observations_phase12e_v1"
HOSTS = {"cmr.earthdata.nasa.gov", "catalogue.dataspace.copernicus.eu",
         "podaac.jpl.nasa.gov", "archive.podaac.earthdata.nasa.gov",
         "developers.google.com", "ewds.climate.copernicus.eu",
         "confluence.ecmwf.int", "www.nrsc.gov.in", "bhuvan-gp1.nrsc.gov.in",
         "bhuvan-app1.nrsc.gov.in", "bhuvan-app3.nrsc.gov.in", "bhuvan.nrsc.gov.in",
         "www.earthdata.nasa.gov", "d2pn8kiwq2w21t.cloudfront.net", "nwdp.nwic.gov.in", "cwc.gov.in"}
MAX_BYTES = 2 * 1024 * 1024
S1_NAMES = (
    "S1A_IW_GRDH_1SDV_20210705T004732_20210705T004757_038635_048F13_BF03",
    "S1A_IW_GRDH_1SDV_20210717T004732_20210717T004757_038810_049451_0405",
    "S1A_IW_GRDH_1SDV_20210729T004733_20210729T004758_038985_049989_7AE1")


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(body):
    return hashlib.sha256(body).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.fragment):
        raise ValueError("only pinned HTTPS metadata hosts without credentials accepted")
    if any(k.lower() in {'token', 'access_token', 'api_key', 'password', 'signature'}
           for k in urllib.parse.parse_qs(parsed.query)):
        raise ValueError('Authentication parameters prohibited')
    if re.search(r"\.(tiff?|zip|safe|hdf|nc|grib2?)(/|$)", urllib.parse.unquote(parsed.path), re.I):
        raise ValueError("full raster/archive URLs prohibited in metadata acquisition")
    return url


def read_bounded(response, ceiling=MAX_BYTES):
    if isinstance(ceiling, bool) or not isinstance(ceiling, int) or not 0 < ceiling <= MAX_BYTES:
        raise ValueError('Invalid metadata byte budget')
    length = response.headers.get("Content-Length")
    if length and int(length) > ceiling:
        raise ValueError("declared response exceeds metadata/preview budget")
    chunks, count = [], 0
    while True:
        chunk = response.read(min(65536, ceiling+1-count))
        if not chunk:
            break
        chunks.append(chunk)
        count += len(chunk)
        if count > ceiling:
            raise ValueError("stream exceeds metadata/preview budget")
    body = b"".join(chunks)
    if length and len(body) != int(length):
        raise ValueError("truncated response")
    return body


def fetch(name, url, raw=RAW, ceiling=MAX_BYTES):
    validate_url(url)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]+", name):
        raise ValueError("invalid receipt filename")
    raw = Path(raw)
    raw.mkdir(parents=True, exist_ok=True)
    path, receipt = raw/name, raw/(name+".receipt.json")
    if path.exists() or receipt.exists():
        raise ValueError("receipt already exists; use validate or a new reviewed name")
    record = {"url": url, "started_at": utcnow(), "byte_ceiling": ceiling,
              "timeout_seconds": 25, "authentication_used": False}
    opener = urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "FloodPulse-research-metadata/12E", "Accept-Encoding": "identity"})
    try:
        with opener.open(request, timeout=25) as response:
            body = read_bounded(response, ceiling)
            if body.startswith((b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+",
                                b"PK\x03\x04", b"\x89HDF", b"\x0e\x03\x13\x01", b"CDF")):
                raise ValueError("native raster/archive response prohibited")
            path.write_bytes(body)
            allowed = ("Content-Type", "Content-Length", "Date", "Last-Modified", "CMR-Hits")
            record.update(status="RETRIEVED", http_status=response.status, bytes=len(body), sha256=sha(body),
                          response_headers={k.lower(): response.headers[k] for k in allowed if response.headers.get(k)})
    except urllib.error.HTTPError as error:
        record.update(status="UNAVAILABLE_HTTP", http_status=error.code, bytes=0,
                      reason="No data read; redirects/authentication are not bypassed")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
        record.update(status="UNAVAILABLE_OR_BUDGET_REJECTED", bytes=0, reason=type(error).__name__)
    record["finished_at"] = utcnow()
    receipt.write_text(json.dumps(record, indent=2, sort_keys=True)+"\n")
    return {"name": name, "status": record["status"], "bytes": record["bytes"], "http_status": record.get("http_status")}


def query(base, params):
    return base + "?" + urllib.parse.urlencode(params)


def validate_receipts(raw=RAW):
    counts, total = {}, 0
    for receipt in sorted(Path(raw).glob('*.receipt.json')):
        row = json.loads(receipt.read_text())
        validate_url(row['url'])
        status = row['status']
        counts[status] = counts.get(status, 0)+1
        path = receipt.with_name(receipt.name.removesuffix('.receipt.json'))
        if row['byte_ceiling'] != MAX_BYTES or row['authentication_used'] is not False:
            raise ValueError('Metadata receipt budget/authentication changed')
        if status == 'RETRIEVED':
            body = path.read_bytes()
            if len(body) != row['bytes'] or len(body) > MAX_BYTES or sha(body) != row['sha256']:
                raise ValueError('Metadata checksum/size mismatch: '+path.name)
            total += len(body)
        elif path.exists() or row['bytes'] != 0:
            raise ValueError('Failed request cannot contain accepted source bytes')
    if not counts:
        raise ValueError('No metadata acquisition receipts')
    return {'requests':sum(counts.values()), 'statuses':counts, 'retained_metadata_document_bytes':total}


def requests():
    old = json.loads((ROOT / "data/recovery/phase12b_v1/opera-cmr-with-headers.json").read_text())["feed"]["entry"]
    jobs = [("opera-2025-current.json", query("https://cmr.earthdata.nasa.gov/search/granules.json", {
        "collection_concept_id": "C2949811996-POCLOUD", "bounding_box": "74.733574299,13.328235746,74.761305332,13.355390503",
        "temporal": "2025-08-01T00:00:00Z,2025-08-31T23:59:59Z", "page_size": 10})),
        ("opera-2026-current.json", query("https://cmr.earthdata.nasa.gov/search/granules.json", {
        "collection_concept_id": "C2949811996-POCLOUD", "bounding_box": "74.733574299,13.328235746,74.761305332,13.355390503",
        "temporal": "2026-08-01T00:00:00Z,2026-08-31T23:59:59Z", "page_size": 5, "sort_key": "start_date"})),
        ("sentinel1-native-catalogue.json", query("https://catalogue.dataspace.copernicus.eu/odata/v1/Products", {
            "$filter": " or ".join("Name eq '"+name+".SAFE'" for name in S1_NAMES), "$expand": "Attributes", "$top": 10, "$count": "true"})),
        ("opera-product-page.html", "https://podaac.jpl.nasa.gov/dataset/OPERA_L3_DSWX-S1_V1"),
        ("opera-ee-catalogue.html", "https://developers.google.com/earth-engine/datasets/catalog/OPERA_DSWX_L3_V1_S1"),
        ("glofas-reforecast.html", "https://ewds.climate.copernicus.eu/datasets/cems-glofas-reforecast"),
        ("glofas-historical.html", "https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical"),
        ("bhuvan-wms-capabilities.xml", query("https://bhuvan-gp1.nrsc.gov.in/bhuvan/gwc/service/wms", {"service": "WMS", "request": "GetCapabilities", "version": "1.1.1"})),
        ("nrsc-satellite-services.html", "https://www.nrsc.gov.in/nrscnew/Services_Bhuvan_SatelliteDataServices.php")]
    for index, entry in enumerate(old[:2]):
        jobs.append((f"opera-2025-umm-{index}.json", query("https://cmr.earthdata.nasa.gov/search/granules.umm_json", {"concept_id": entry["id"], "page_size": 1})))
    for year, date in ((2005, "2005-09-14"), (2009, "2009-09-25")):
        jobs.append((f"modis-{year}-metadata.json", query("https://cmr.earthdata.nasa.gov/search/granules.json", {
            "short_name": "MOD09GQ", "version": "061", "bounding_box": "74.733574299,13.328235746,74.761305332,13.355390503",
            "temporal": date+"T00:00:00Z,"+date+"T23:59:59Z", "page_size": 2})))
    return jobs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "fetch", "validate"))
    args = parser.parse_args()
    if args.command == 'validate':
        print(json.dumps(validate_receipts(), indent=2))
        exit()
    jobs = requests()
    if args.command == "plan":
        print(json.dumps({"maximum_responses": len(jobs), "maximum_total_metadata_bytes": len(jobs)*MAX_BYTES, "requests": jobs}, indent=2))
    else:
        # Metadata only: intentionally sequential and capped to this reviewed set.
        for name, url in jobs:
            print(json.dumps(fetch(name, url)), flush=True)
