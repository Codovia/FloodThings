"""Read-only release validation of retained sources and saved model; never fits."""
import csv
import json

import train_rainfall_outlook as training
from app.rainfall_outlook import RainfallModel


def validate():
    from sklearn.metrics import confusion_matrix, precision_score, recall_score, f1_score

    model = RainfallModel()
    meta = model.metadata
    rows, missing = training.assemble()
    train, test = training.chronological_split(rows)
    training.require(training.checksum(training.OUTPUT / 'training_examples.csv') == meta['dataset']['sha256'], 'Training table checksum differs')
    training.require(training.checksum(training.ROOT / 'data/reference/karnataka_location_directory_v2/directory.json') == meta['source_directory_sha256'], 'Location source checksum differs')
    training.require(json.loads((training.OUTPUT / 'manifest.json').read_bytes()) == meta, 'Model/dataset metadata differs')
    with (training.OUTPUT / 'training_examples.csv').open(newline='') as stream:
        saved = list(csv.DictReader(stream))
    training.require(len(saved) == len(rows) == meta['dataset']['rows'] and missing == meta['missing_examples'], 'Source coverage differs')
    for actual, expected in zip(saved, rows):
        training.require(actual == {key: str(value) for key, value in expected.items()}, 'Source-to-feature/target row differs')
    for source in meta['sources']:
        raw = training.RAW / (source['requested_point']['name'].lower() + '.json')
        training.require(raw.stat().st_size == source['bytes'] and training.checksum(raw) == source['sha256'], 'Original weather source differs')
    for name, examples in [('training', train), ('testing', test)]:
        expected = meta[name]
        training.require(len(examples) == expected['samples'] and sum(r['heavy_rainfall'] for r in examples) == expected['positive'], 'Chronological split differs')
        training.require(examples[0]['cutoff_utc'] == expected['first_cutoff'] and examples[-1]['cutoff_utc'] == expected['last_cutoff'], 'Split dates differ')
    labels = [r['heavy_rainfall'] for r in test]
    predictions = [model.predict({f: row[f] for f in training.FEATURES}) for row in test]
    metrics = {'confusion_matrix_tn_fp_fn_tp': confusion_matrix(labels, predictions, labels=[0, 1]).tolist(),
               'precision': float(precision_score(labels, predictions)), 'recall': float(recall_score(labels, predictions)),
               'f1': float(f1_score(labels, predictions))}
    training.require(metrics == meta['holdout_metrics'], 'Saved-model held-out metrics differ')
    return {'status': 'passed', 'rows': len(rows), 'training': len(train), 'testing': len(test),
            'holdout_metrics': metrics, 'model_sha256': meta['model_sha256'], 'refitted': False}


if __name__ == '__main__':
    print(json.dumps(validate(), indent=2))
