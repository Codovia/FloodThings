"""The application may evolve; the frozen research inputs must still match exactly."""
import hashlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

spec = importlib.util.spec_from_file_location('frozen_reviews', Path(__file__).resolve().parents[2] / 'scripts/validate_frozen_app_reviews.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def fixture(root):
    contents = {name: b'controlled historical source\n' for name in module.APP_INPUTS}
    records = [{'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in contents.items()]
    for review in module.REVIEWS:
        p = root / 'data/working' / review / 'manifest.json'; p.parent.mkdir(parents=True)
        p.write_text(json.dumps({'inputs': records}))
    return contents


def test_recorded_input_check_is_read_only_and_does_not_require_reverting_current_app(tmp_path):
    with TemporaryDirectory(dir=tmp_path) as folder:
        root = Path(folder); contents = fixture(root)
        (root / 'README.md').write_text('different current application documentation\n')
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
        assert len(module.verify_recorded_inputs(root, contents)) == 2
        assert before == {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('name', module.APP_INPUTS)
def test_changed_historical_bytes_rejected_without_changing_expected_checksum(tmp_path, name):
    with TemporaryDirectory(dir=tmp_path) as folder:
        root = Path(folder); contents = fixture(root)
        originals = {p: p.read_bytes() for p in root.rglob('manifest.json')}
        contents[name] = b'wrong reconstruction\n'
        with pytest.raises(ValueError, match='immutable manifest'): module.verify_recorded_inputs(root, contents)
        assert all(p.read_bytes() == data for p, data in originals.items())
