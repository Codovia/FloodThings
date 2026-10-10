"""Release checks use the existing artifact; model fitting is forbidden here."""
from pathlib import Path

import pytest


def test_saved_model_sources_features_and_holdout_without_refitting(monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / 'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    import validate_saved_rainfall as release
    monkeypatch.setattr(release.training, 'fit', lambda *a, **k: pytest.fail('Release validation must not refit'))
    report = release.validate()
    assert report['refitted'] is False
    assert (report['rows'], report['training'], report['testing']) == (8768, 5842, 2888)
    assert report['holdout_metrics']['confusion_matrix_tn_fp_fn_tp'] == [[2273, 519], [8, 88]]


def test_release_manifest_and_model_artifact_remain_immutable():
    from app.rainfall_outlook import RainfallModel
    assert RainfallModel().metadata['model_sha256'] == 'f3fa9b53d7047746f9d26cba8556705fb3fd2328128a236cb4f423575acf4316'
