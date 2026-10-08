"""Read-only reproduction of Stage 5/5A with their exact historical app inputs.

Application evolution must not rewrite completed research versions or weaken
checksums. Only the two explicitly recorded application inputs are replayed from
Git, verified against both original manifests before any validator executes.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
INPUT_COMMIT = 'b987a4b59c58f77d90ce27434eb5ff6cf23def95'
APP_INPUTS = ('README.md', 'backend/app/weather.py')
REVIEWS = ('karnataka_prediction_methodology_v1', 'karnataka_target_archive_review_v1')


def verify_recorded_inputs(root, contents):
    """Require original hashes in both manifests; never accept the current file instead."""
    records = []
    for name in APP_INPUTS:
        content = contents[name]
        record = {'path': name, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
        for review in REVIEWS:
            manifest = json.loads((Path(root) / 'data/working' / review / 'manifest.json').read_bytes())
            original = next(r for r in manifest['inputs'] if r['path'] == name)
            if record != original:
                raise ValueError('Historical application input differs from immutable manifest: ' + name)
        records.append(record)
    return records


def validate(root=ROOT):
    root = Path(root)
    contents = {name: subprocess.check_output(['git', 'show', INPUT_COMMIT + ':' + name], cwd=root) for name in APP_INPUTS}
    records = verify_recorded_inputs(root, contents)
    with tempfile.TemporaryDirectory(prefix='floodpulse-frozen-review-') as folder:
        replay = Path(folder)
        for name in ('data', 'docs', 'QandA.md'):
            (replay / name).symlink_to(root / name, target_is_directory=(root / name).is_dir())
        for name, content in contents.items():
            target = replay / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        (replay / 'scripts').mkdir()
        for name in ('review_prediction_availability.py', 'review_target_archives.py',
                     'close_external_hydrology.py', 'close_hydrology_semantics.py', 'build_glofas_pilot.py'):
            shutil.copyfile(root / 'scripts' / name, replay / 'scripts' / name)
        # Every other original source/output remains linked to its protected bytes.
        results = []
        for name in ('review_prediction_availability', 'review_target_archives'):
            spec = importlib.util.spec_from_file_location(name + '_frozen', replay / 'scripts' / (name + '.py'))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.validate()
            results.append(name)
        if module.read(module.PUBLIC) != module.public_metadata():
            raise ValueError('Frozen public review metadata differs')
        results.append('public_review_metadata')
    return {'original_input_commit': INPUT_COMMIT, 'application_inputs': records,
            'validations': results, 'scientific_outputs_modified': False}


if __name__ == '__main__':
    print(json.dumps(validate(), indent=2))
