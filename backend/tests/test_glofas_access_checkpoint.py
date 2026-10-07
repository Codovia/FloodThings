"""Offline catalogue fixtures in temporary directories; no model observations."""
import importlib.util
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('glofas_checkpoint', ROOT / 'scripts/checkpoint_glofas_access.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
CATALOGUE = ('<p>https://ewds.climate.copernicus.eu/api/catalogue/v1/collections/'
    'cems-glofas-historical" Operational version - GloFAS v5.0 released 2026-07-15 '
    '0.05° x 0.05° Daily data</p>').encode()


def fixture_sources(raw):
    raw.mkdir()
    for name in ['glofas_catalogue.html', *[f'fixture_{i}.html' for i in range(15)]]:
        content = CATALOGUE if name == 'glofas_catalogue.html' else b'<p>controlled catalogue fixture</p>'
        (raw / name).write_bytes(content)
        metadata = {'source_url': 'https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical',
            'final_url': 'https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical',
            'retrieved_at': '2026-10-07T00:00:00+00:00', 'content_type': 'text/html',
            'status': 'retrieved', 'http_status': '200', 'bytes': len(content),
            'sha256': g.sha(content), 'deadline_seconds': 30, 'byte_ceiling': 2097152, 'attempts': 1}
        (raw / (name + '.json')).write_bytes(g.encode(metadata))


def test_exact_catalogue_identity_and_modelled_type():
    parsed = g.parse_catalogue(CATALOGUE)
    assert parsed['dataset_id'] == 'cems-glofas-historical'
    assert parsed['version'] == '5.0' and parsed['hydrology_source_type'] == 'modelled_glofas'
    assert parsed['verification_level'] == 'catalogue_only' and not parsed['native_files_verified']
    assert 'measured_cwc_nwdp' in g.SOURCE_TYPES and 'published_cwc_yearbook' in g.SOURCE_TYPES


@pytest.mark.parametrize('old,new', [(b'cems-glofas-historical', b'cems-glofas-forecast'),
    (b'v5.0', b'v4.0'), ('0.05°'.encode(), b'0.1'), (b'Daily data', b'Hourly data')])
def test_wrong_product_version_grid_or_frequency_rejected(old, new):
    with pytest.raises(ValueError): g.parse_catalogue(CATALOGUE.replace(old, new))


@pytest.mark.parametrize('field', ['station_grid_matches', 'upstream_areas', 'modelled_discharge',
    'maxima', 'measured_modelled_comparisons', 'calibration_relationships'])
def test_no_fabricated_results_without_retrieval(tmp_path, field):
    with TemporaryDirectory(dir=tmp_path) as folder:
        raw = Path(folder) / 'raw'; fixture_sources(raw)
        manifest = g.assemble(raw); manifest['results'][field] = []
        with pytest.raises(ValueError, match='prohibited'): g.check_blocked(manifest)


@pytest.mark.parametrize('change', ['authentication', 'readiness', 'source_type', 'native_files'])
def test_blocked_checkpoint_cannot_promote_itself(tmp_path, change):
    with TemporaryDirectory(dir=tmp_path) as folder:
        raw = Path(folder) / 'raw'; fixture_sources(raw); manifest = g.assemble(raw)
        if change == 'authentication': manifest['access']['authenticated_request_attempted'] = True
        if change == 'readiness': manifest['readiness'] = 'glofas_historical_context_ready'
        if change == 'source_type': manifest['product']['hydrology_source_type'] = 'measured_cwc_nwdp'
        if change == 'native_files': manifest['product']['native_files_verified'] = True
        with pytest.raises(ValueError): g.check_blocked(manifest)


def test_deterministic_manifest_immutable_build_and_readonly_validation(tmp_path):
    with TemporaryDirectory(dir=tmp_path) as folder:
        raw = Path(folder) / 'raw'; fixture_sources(raw); output = Path(folder) / 'manifest.json'
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in raw.iterdir()}
        assert g.encode(g.assemble(raw)) == g.encode(g.assemble(raw))
        result = g.build(output, raw); saved = (output.read_bytes(), output.stat().st_mtime_ns)
        assert result == g.validate(output, raw)
        assert saved == (output.read_bytes(), output.stat().st_mtime_ns)
        assert all(v == (p.read_bytes(), p.stat().st_mtime_ns) for p,v in before.items())
        with pytest.raises(FileExistsError): g.build(output, raw)
        assert saved == (output.read_bytes(), output.stat().st_mtime_ns)


def test_source_corruption_and_unofficial_url_rejected(tmp_path):
    with TemporaryDirectory(dir=tmp_path) as folder:
        raw = Path(folder) / 'raw'; fixture_sources(raw)
        p = raw / 'fixture_0.html'; original = p.read_bytes(); p.write_bytes(b'corrupt')
        with pytest.raises(ValueError, match='checksum'): g.assemble(raw)
        p.write_bytes(original); meta = raw / 'fixture_0.html.json'; values = json.loads(meta.read_bytes())
        values['source_url'] = 'https://unofficial.example/data'; meta.write_bytes(g.encode(values))
        with pytest.raises(ValueError, match='Unofficial'): g.assemble(raw)


def test_manifest_tampering_rejected(tmp_path):
    with TemporaryDirectory(dir=tmp_path) as folder:
        raw = Path(folder) / 'raw'; fixture_sources(raw); output = Path(folder) / 'manifest.json'
        g.build(output, raw); content = json.loads(output.read_bytes()); content['original_metadata_bytes'] = 0
        output.write_bytes(g.encode(content))
        with pytest.raises(ValueError, match='reproduction'): g.validate(output, raw)


@pytest.mark.parametrize('path', ['.cdsapirc', '.ecmwfapirc', '.ewds-config', '.env',
    'credentials.json', 'cookies.txt', '.bash_history'])
def test_repository_excludes_credentials(path):
    result = subprocess.run(['git', 'check-ignore', '--no-index', path], cwd=ROOT,
        capture_output=True, text=True, check=False)
    assert result.returncode == 0
