"""Every file a published dataset's manifest lists must be committed, or a fresh server checkout cannot load it.

The historical flood and drainage stores verify each manifest file by SHA-256, so a single missing raster makes the
whole dataset unavailable (503). This happened in production: the GeoTIFFs were kept out of Git by `*.tif`.
"""
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / 'data/processed'


def tracked_files():
    try:
        result = subprocess.run(['git', 'ls-files', '--', 'data/processed'], cwd=ROOT, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip('Not a Git checkout')
    return set(result.stdout.split())


@pytest.mark.parametrize('manifest', sorted(PROCESSED.glob('*/manifest.json')), ids=lambda p: p.parent.name)
def test_every_manifest_file_is_committed(manifest):
    tracked = tracked_files()
    listed = json.loads(manifest.read_text()).get('files', {})
    missing = sorted(name for name in listed if f'{manifest.parent.relative_to(ROOT).as_posix()}/{name}' not in tracked)
    assert not missing, f'{manifest.parent.name}: manifest files not committed: {missing}'
