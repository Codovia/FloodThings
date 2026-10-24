"""Bounded real-data acquisition, chronological training and immutable outputs."""
import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.rainfall_features import (FEATURES, VARIABLES, UNITS, VERSION, THRESHOLD_MM, THRESHOLD_URL,
                                  parse_hourly, past_features, future_target, RainfallUnavailable, require)
RAW=ROOT/'data/raw/open_meteo/rainfall_outlook_v1'
OUTPUT=ROOT/'data/working/rainfall_outlook_training_v1'
MODEL=ROOT/'backend/models'/VERSION
ARCHIVE='https://archive-api.open-meteo.com/v1/archive'


def encoded(value):
    return (json.dumps(value,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n').encode()


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def locations():
    p=ROOT/'data/reference/karnataka_location_directory_v2/directory.json'
    data=json.loads(p.read_bytes())
    return [{'id':r['id'],'name':r['name'],**r['coordinates']} for r in data['localities'] if r['name'] in ('Kundapur','Mangaluru') and r['selectable']]


def fetch():
    import httpx
    RAW.mkdir(parents=True,exist_ok=True)
    for point in locations():
        name=point['name'].lower();path=RAW/(name+'.json');receipt=RAW/(name+'_retrieval.json')
        if path.exists():
            require(receipt.exists() and checksum(path)==json.loads(receipt.read_bytes())['sha256'], 'Retained raw response has no matching verified receipt')
            parse_hourly(json.loads(path.read_bytes()));print(name,'verified cached source',flush=True);continue
        params={'latitude':point['latitude'],'longitude':point['longitude'],'start_date':'2022-12-28','end_date':'2026-01-01',
                'models':'era5','hourly':','.join(VARIABLES+['snowfall']),'timezone':'UTC','precipitation_unit':'mm','temperature_unit':'celsius'}
        # One bounded attempt per source; no hidden or unlimited retry.
        with httpx.Client(timeout=60,follow_redirects=False) as client:
            response=client.get(ARCHIVE,params=params);response.raise_for_status();body=response.content
        require(len(body)<10000000,'Source response exceeds bounded size')
        payload=json.loads(body);parse_hourly(payload)
        require(payload['hourly_units']['snowfall']=='cm' and all(v==0 for v in payload['hourly']['snowfall']), 'Rainfall target cannot be equated to snowy precipitation')
        path.write_bytes(body)
        receipt.write_bytes(encoded({'url':str(response.url),'parameters':params,'retrieved_at':datetime.now(timezone.utc).isoformat(),
                                    'status_code':response.status_code,'content_type':response.headers.get('content-type'),
                                    'bytes':len(body),'sha256':checksum(path),'requested_point':point,'provider_grid':{k:payload[k] for k in ('latitude','longitude','elevation')},
                                    'source_type':'ERA5 reanalysis, not station observations','license':'CC BY 4.0','documentation':'https://open-meteo.com/en/docs/historical-weather-api'}))
        print(name,'retrieved',len(body),'bytes',flush=True)


def assemble():
    rows=[];missing=[]
    for point in locations():
        p=RAW/(point['name'].lower()+'.json');receipt=json.loads((RAW/(point['name'].lower()+'_retrieval.json')).read_bytes())
        require(checksum(p)==receipt['sha256'],'Raw checksum failed')
        payload=json.loads(p.read_bytes());series=parse_hourly(payload)
        require(payload['hourly_units']['snowfall']=='cm' and all(v==0 for v in payload['hourly']['snowfall']),'Snow/missing snowfall cannot become rainfall evidence')
        cutoff=datetime(2023,1,1,tzinfo=timezone.utc)
        while cutoff<datetime(2026,1,1,tzinfo=timezone.utc):
            try:
                features=past_features(series,cutoff);total,label=future_target(series,cutoff)
                rows.append({'location_id':point['id'],'location_name':point['name'],'cutoff_utc':cutoff.isoformat(),
                             'feature_start_utc':(cutoff-timedelta(hours=73)).isoformat(),'feature_end_utc':(cutoff-timedelta(hours=1)).isoformat(),
                             'target_end_utc':(cutoff+timedelta(hours=24)).isoformat(),**features,'next_24h_rain_mm':total,'heavy_rainfall':label})
            except RainfallUnavailable as exc:missing.append({'location_id':point['id'],'cutoff':cutoff.isoformat(),'reason':str(exc)})
            cutoff+=timedelta(hours=6)
    return sorted(rows,key=lambda r:(r['cutoff_utc'],r['location_id'])),missing


def chronological_split(rows):
    split=datetime(2025,1,1,tzinfo=timezone.utc)
    train=[r for r in rows if datetime.fromisoformat(r['target_end_utc'])<=split]
    test=[r for r in rows if datetime.fromisoformat(r['cutoff_utc'])>=split+timedelta(days=4)]
    require(train and test and max(r['target_end_utc'] for r in train)<min(r['feature_start_utc'] for r in test),'Temporal split overlaps')
    require({r['heavy_rainfall'] for r in train}=={0,1} and {r['heavy_rainfall'] for r in test}=={0,1},'Both classes required in chronological train and holdout')
    return train,test


def fit(rows):
    import numpy as np
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    pipeline=Pipeline([('scaler',StandardScaler()),('classifier',LogisticRegression(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=7))])
    x=np.asarray([[r[f] for f in FEATURES] for r in rows]);y=np.asarray([r['heavy_rainfall'] for r in rows])
    pipeline.fit(x,y)
    require(pipeline['classifier'].n_iter_[0]<1000,'Logistic regression did not converge')
    return pipeline


def train():
    import numpy as np,sklearn
    from sklearn.metrics import confusion_matrix,precision_recall_fscore_support
    require(not OUTPUT.exists() and not (MODEL/'model.json').exists(),'Immutable training/model version already exists')
    rows,missing=assemble();training,testing=chronological_split(rows);pipeline=fit(training)
    def evaluate(pred):
        y=[r['heavy_rainfall'] for r in testing];p,r,f,_=precision_recall_fscore_support(y,pred,average='binary',zero_division=0)
        return {'confusion_matrix_tn_fp_fn_tp':confusion_matrix(y,pred,labels=[0,1]).tolist(),'precision':float(p),'recall':float(r),'f1':float(f)}
    x=np.asarray([[r[f] for f in FEATURES] for r in testing]);prediction=pipeline.predict(x)
    scaler=pipeline['scaler'];classifier=pipeline['classifier']
    model={'version':VERSION,'features':FEATURES,'feature_order':list(FEATURES),'threshold_mm':THRESHOLD_MM,'classes':[0,1],
           'scaler':{'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist()},
           'logistic_regression':{'coefficients':classifier.coef_[0].tolist(),'intercept':float(classifier.intercept_[0])},
           'decision_rule':'class 1 if trained decision function > 0; no calibrated probability exposed'}
    # Verify the portable JSON forward pass exactly agrees with the trained sklearn pipeline.
    forward=((x-np.asarray(model['scaler']['mean']))/np.asarray(model['scaler']['scale']))@np.asarray(model['logistic_regression']['coefficients'])+model['logistic_regression']['intercept']
    require(np.array_equal(forward>0,prediction==1),'Portable saved preprocessing/model differs from sklearn')
    OUTPUT.mkdir(parents=True);MODEL.mkdir(parents=True,exist_ok=True)
    with (OUTPUT/'training_examples.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (MODEL/'model.json').write_bytes(encoded(model))
    sources=[json.loads(p.read_bytes()) for p in sorted(RAW.glob('*_retrieval.json'))]
    def counts(part):return {'samples':len(part),'positive':sum(r['heavy_rainfall'] for r in part),'negative':sum(not r['heavy_rainfall'] for r in part),'first_cutoff':part[0]['cutoff_utc'],'last_cutoff':part[-1]['cutoff_utc']}
    meta={'version':VERSION,'trained_at':datetime.now(timezone.utc).isoformat(),'model_sha256':checksum(MODEL/'model.json'),'sklearn_version':sklearn.__version__,
          'algorithm':'StandardScaler + scikit-learn LogisticRegression; C=1, balanced class weights, lbfgs, random_state=7; no holdout tuning',
          'target':{'name':'at_least_heavy_rainfall_grid_proxy','threshold_mm':THRESHOLD_MM,'horizon_hours':24,'definition_url':THRESHOLD_URL,
                    'definition':'At least IMD heavy-rainfall amount, including very/extremely heavy. Applied to 24-hour model-grid precipitation, not station observations or flood labels.',
                    'timing':'Target sums precipitation at cutoff+1h through cutoff+24h. Precipitation is preceding-hour accumulation. This rolling UTC window differs from IMD 08:30 IST reporting day.'},
          'features':FEATURES,'locations':locations(),'sources':sources,'training':counts(training),'testing':counts(testing),'missing_examples':missing,
          'excluded_split_examples':len(rows)-len(training)-len(testing),'holdout_metrics':evaluate(prediction),'always_below_threshold_baseline':evaluate(np.zeros(len(testing),dtype=int)),
          'temporal_split':'Train labels end <=2025-01-01T00:00Z; holdout cutoff >=2025-01-05T00:00Z, four-day embargo; no shuffled/same-event temporal split.',
          'sample_dependence':'Six-hour cutoffs have overlapping 24-hour targets and nearby coast grids. Rows are not independent events; metrics are descriptive, not operational or station skill.',
          'training_serving_parity':'PROXY_REQUIRES_VALIDATION: historical ERA5 0.25-degree delayed reanalysis vs live Open-Meteo best-match forecast/model past-hours. Same units/feature algorithm; different products, grids and publication semantics. Live cutoffs may be at other UTC hours.',
          'historical_availability':'Retrospective ERA5 values were not proven available at historical issuance; only valid-time feature boundaries are leakage-free. No as-issued forecast skill claim.',
          'deployment_scope':'Only the two exact retained Kundapur/Mangaluru points. No statewide extrapolation, station accuracy, calibrated probability, flood predictions or emergency alerts.',
          'dataset':{'path':str((OUTPUT/'training_examples.csv').relative_to(ROOT)),'sha256':checksum(OUTPUT/'training_examples.csv'),'rows':len(rows)},
          'source_directory_sha256':checksum(ROOT/'data/reference/karnataka_location_directory_v2/directory.json'),'publication':'Open-Meteo CC BY 4.0, free API non-commercial terms; place metadata © OpenStreetMap contributors ODbL 1.0. Raw responses/detailed training table local; model/metadata public.'}
    (MODEL/'metadata.json').write_bytes(encoded(meta));(OUTPUT/'manifest.json').write_bytes(encoded(meta))
    print(json.dumps({k:meta[k] for k in ['training','testing','holdout_metrics','missing_examples','excluded_split_examples']},indent=2))


def validate():
    import numpy as np
    meta=json.loads((MODEL/'metadata.json').read_bytes());rows,missing=assemble();training,testing=chronological_split(rows)
    require(checksum(MODEL/'model.json')==meta['model_sha256'] and checksum(OUTPUT/'training_examples.csv')==meta['dataset']['sha256'],'Output checksum mismatch')
    with (OUTPUT/'training_examples.csv').open(newline='') as f:
        saved=list(csv.DictReader(f))
    require(len(saved)==len(rows) and missing==meta['missing_examples'],'Source coverage mismatch')
    for actual,wanted in zip(saved,rows):
        for key,value in wanted.items():
            require(actual[key]==str(value),'Every source-to-feature/target row must reproduce')
    pipe=fit(training);model=json.loads((MODEL/'model.json').read_bytes())
    require(np.array_equal(pipe['scaler'].mean_,model['scaler']['mean']) and np.array_equal(pipe['scaler'].scale_,model['scaler']['scale'])
            and np.array_equal(pipe['classifier'].coef_[0],model['logistic_regression']['coefficients']) and pipe['classifier'].intercept_[0]==model['logistic_regression']['intercept'],'Deterministic retraining failed')
    print('Real source-to-dataset and exact retraining passed:',len(rows),'examples')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['fetch','train','validate']);args=parser.parse_args()
    globals()[args.action]()
