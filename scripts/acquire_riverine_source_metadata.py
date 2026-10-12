#!/usr/bin/env python3
"""Pinned Phase12F public metadata only. No accounts, data archives or forecasts fitted.

Reuses the tested Phase12E bounded transport without changing its frozen files.
Each response is limited to 2MiB, redirects/authentication are never bypassed.
"""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path

import acquire_direct_observation_metadata as transport

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/riverine_forecasting_phase12f_v1/sources'
HOSTS = {'cwc.gov.in', 'nwdp.nwic.gov.in', 'www.pib.gov.in', 'api.imd.gov.in',
         'ksndmc.org', 'ewds.climate.copernicus.eu', 'ecds.ecmwf.int',
         'confluence.ecmwf.int', 'raw.githubusercontent.com', 'openhydronet.readthedocs.io',
         'mausam.imd.gov.in'}
JOBS = (
    ('cwc-ho.html', 'https://cwc.gov.in/hydro-meteorological-observation'),
    ('cwc-copyright.html', 'https://cwc.gov.in/en/copyright-policy'),
    ('cwc-mso-directory.html', 'https://cwc.gov.in/en/mso/tel-directory'),
    ('nwdp-api.html', 'https://nwdp.nwic.gov.in/en/dataset_api/home_api_page'),
    ('floodwatch-launch.html', 'https://www.pib.gov.in/PressReleasePage.aspx?PRID=2044887'),
    ('imd-reference.html', 'https://api.imd.gov.in/public/api_reference.html'),
    ('imd-register.html', 'https://api.imd.gov.in/public/register.php'),
    ('imd-contact.html', 'https://api.imd.gov.in/public/contact.php'),
    ('imd-basin-qpf.json', 'https://api.imd.gov.in/api/v1/basinqpf'),
    ('ksndmc-flood.html', 'https://ksndmc.org/en/Media/Flood'),
    ('ksndmc-hydrology.html', 'https://ksndmc.org/en/Activities/Hydrology'),
    ('glofas-forecast.html', 'https://ewds.climate.copernicus.eu/datasets/cems-glofas-forecast?tab=overview'),
    ('glofas-reforecast.html', 'https://ewds.climate.copernicus.eu/datasets/cems-glofas-reforecast?tab=overview'),
    ('glofas-historical.html', 'https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical?tab=overview'),
    ('glofas-licence.html', 'https://ecds.ecmwf.int/licences/cems-floods'),
    ('glofas-access.html', 'https://confluence.ecmwf.int/plugins/viewsource/viewpagesrc.action?pageId=278538391'),
    ('openhydronet-readme.md', 'https://raw.githubusercontent.com/google-research/flood-forecasting/main/README.md'),
    ('openhydronet-licence.txt', 'https://raw.githubusercontent.com/google-research/flood-forecasting/main/LICENSE'),
    ('openhydronet-docs.html', 'https://openhydronet.readthedocs.io/en/latest/'),
    ('floodwatch-launch-explicit.html', 'https://www.pib.gov.in/PressReleasePage.aspx?PRID=2044887&lang=2&noshow=1&reg=48'),
    ('glofas-web-services.html', 'https://confluence.ecmwf.int/spaces/CEMS/pages/242067472/Web+Services'),
    ('imd-hydrology-sop.pdf', 'https://mausam.imd.gov.in/imd_latest/contents/pdf/hydrology_sop.pdf'),
)


@contextmanager
def metadata_hosts():
    original = transport.HOSTS
    transport.HOSTS = HOSTS
    try:
        yield
    finally:
        transport.HOSTS = original


def plan():
    return {'phase': '12F', 'purpose': 'Station-data access and forecast integration feasibility',
            'authentication': False, 'large_datasets_authorized': False,
            'maximum_total_bytes': len(JOBS)*transport.MAX_BYTES,
            'maximum_response_bytes': transport.MAX_BYTES, 'requests': list(JOBS),
            'resume': 'Existing immutable receipts skipped; no automatic retries or redirects'}


def validate(raw=RAW):
    raw = Path(raw)
    receipts = sorted(raw.glob('*.receipt.json'))
    if {p.name.removesuffix('.receipt.json') for p in receipts} != {n for n, _ in JOBS}:
        raise ValueError('Exact pinned source receipt set required')
    urls = dict(JOBS)
    for path in receipts:
        row = json.loads(path.read_text())
        name = path.name.removesuffix('.receipt.json')
        if row['url'] != urls[name] or row['status'] not in {
                'RETRIEVED', 'UNAVAILABLE_HTTP', 'UNAVAILABLE_OR_BUDGET_REJECTED'}:
            raise ValueError('Source URL/status changed')
    with metadata_hosts():
        return transport.validate_receipts(raw)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['plan', 'fetch', 'validate'])
    args = parser.parse_args()
    if args.command == 'plan':
        print(json.dumps(plan(), indent=2))
    elif args.command == 'validate':
        print(json.dumps(validate(), indent=2))
    else:
        for name, url in JOBS:
            if (RAW/(name+'.receipt.json')).exists():
                print(json.dumps({'name': name, 'status': 'EXISTING_RECEIPT_SKIPPED'}), flush=True)
            else:
                with metadata_hosts():
                    result = transport.fetch(name, url, raw=RAW)
                print(json.dumps(result), flush=True)
