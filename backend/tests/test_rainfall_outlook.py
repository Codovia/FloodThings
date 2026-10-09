"""Offline tests. Synthetic weather exists only in tests, never training artifacts."""
import asyncio
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
import httpx
import numpy as np
import pytest

from app.main import app,get_weather
from app.rainfall_features import FEATURES,VARIABLES,UNITS,THRESHOLD_MM,parse_hourly,past_features,future_target,RainfallUnavailable
from app.rainfall_outlook import ARTIFACT,RainfallModel,rainfall_outlook

NOW=datetime(2026,10,9,13,30,tzinfo=timezone.utc)
CUTOFF=datetime(2026,10,9,14,tzinfo=timezone.utc)
POINT=(13.6250993,74.6915722)


def payload():
    times=[CUTOFF+timedelta(hours=i) for i in range(-74,25)]
    hourly={'time':[t.replace(tzinfo=None).isoformat(timespec='minutes') for t in times],
            'precipitation':[1.0 for _ in times], 'temperature_2m':[27.0 for _ in times],
            'relative_humidity_2m':[80.0 for _ in times],'surface_pressure':[1005.0 for _ in times]}
    return {'latitude':13.6,'longitude':74.7,'utc_offset_seconds':0,'hourly_units':UNITS,'hourly':hourly}


def trainer():
    p=Path(__file__).resolve().parents[2]/'scripts/train_rainfall_outlook.py'
    spec=importlib.util.spec_from_file_location('rainfall_training_tests',p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_past_windows_and_independent_scalar_calculations():
    series=parse_hourly(payload());features=past_features(series,CUTOFF)
    assert features['rain_24h_mm']==24 and features['rain_72h_mm']==72
    assert features['max_hourly_rain_24h_mm']==1 and features['temperature_mean_24h_c']==27
    independent=sum(series[CUTOFF-timedelta(hours=i)]['precipitation'] for i in range(1,25))
    assert independent==features['rain_24h_mm']
    assert future_target(series,CUTOFF)==(24,0)


def test_future_and_start_hour_cannot_change_antecedent_features():
    series=parse_hourly(payload());before=past_features(series,CUTOFF)
    for t in series:
        if t>=CUTOFF:series[t]['precipitation']=1000
    assert past_features(series,CUTOFF)==before
    assert future_target(series,CUTOFF)[1]==1
    series[CUTOFF-timedelta(hours=1)]['precipitation']=8
    assert past_features(series,CUTOFF)['rain_24h_mm']==31


@pytest.mark.parametrize('total,label',[(64.4,0),(64.5,1),(115.6,1),(204.5,1)])
def test_authoritative_at_least_heavy_boundary(total,label):
    series=parse_hourly(payload())
    for i in range(1,25):series[CUTOFF+timedelta(hours=i)]['precipitation']=0
    series[CUTOFF+timedelta(hours=1)]['precipitation']=total
    assert future_target(series,CUTOFF)==(total,label)


@pytest.mark.parametrize('target',[False,True])
def test_missing_inputs_or_target_never_become_zero_or_negative(target):
    series=parse_hourly(payload());stamp=CUTOFF+timedelta(hours=1) if target else CUTOFF-timedelta(hours=1)
    series[stamp]['precipitation']=None
    with pytest.raises(RainfallUnavailable):
        (future_target if target else past_features)(series,CUTOFF)


@pytest.mark.parametrize('kind',['units','duplicate','negative','nan','bool','timezone','length'])
def test_source_schema_and_physical_validation(kind):
    p=deepcopy(payload())
    if kind=='units':p['hourly_units']={**UNITS,'precipitation':'inch'}
    if kind=='duplicate':p['hourly']['time'][1]=p['hourly']['time'][0]
    if kind=='negative':p['hourly']['precipitation'][0]=-1
    if kind=='nan':p['hourly']['temperature_2m'][0]=float('nan')
    if kind=='bool':p['hourly']['surface_pressure'][0]=True
    if kind=='timezone':p['utc_offset_seconds']=19800
    if kind=='length':p['hourly']['precipitation'].pop()
    with pytest.raises(RainfallUnavailable):parse_hourly(p)


def test_real_artifact_target_scope_and_checksum():
    model=RainfallModel()
    assert model.metadata['target']['threshold_mm']==64.5 and model.metadata['target']['horizon_hours']==24
    assert model.supported(*POINT)['name']=='Kundapur'
    assert model.supported(12.8698101,74.8430082)['name']=='Mangaluru'
    assert model.supported(12.9767936,77.590082) is None
    assert 'PROXY_REQUIRES_VALIDATION' in model.metadata['training_serving_parity']
    assert 'Retrospective' in model.metadata['historical_availability']
    with TemporaryDirectory() as folder:
        p=Path(folder)
        for name in ['model.json','metadata.json']:(p/name).write_bytes((ARTIFACT/name).read_bytes())
        (p/'model.json').write_bytes((p/'model.json').read_bytes()+b' ')
        with pytest.raises(RainfallUnavailable,match='checksum'):RainfallModel(p)


def test_real_training_reproduction_chronological_split_and_actual_metrics():
    t=trainer()
    if not t.RAW.exists():pytest.skip('Retained real training sources required for offline retraining')
    rows,missing=t.assemble();train,test=t.chronological_split(rows)
    assert not missing and len(rows)==8768 and len(train)==5842 and len(test)==2888
    assert max(r['target_end_utc'] for r in train)<min(r['feature_start_utc'] for r in test)
    pipe=t.fit(train);again=t.fit(train);model=RainfallModel()
    assert np.array_equal(pipe['classifier'].coef_,again['classifier'].coef_)
    assert np.array_equal(pipe['scaler'].mean_,model.mean)
    x=np.asarray([[r[f] for f in FEATURES] for r in test]);expected=pipe.predict(x)
    actual=[model.predict({f:r[f] for f in FEATURES}) for r in test]
    assert np.array_equal(expected,actual)
    from sklearn.metrics import confusion_matrix,precision_score,recall_score,f1_score
    y=[r['heavy_rainfall'] for r in test];m=model.metadata['holdout_metrics']
    assert confusion_matrix(y,actual,labels=[0,1]).tolist()==[[2273,519],[8,88]]==m['confusion_matrix_tn_fp_fn_tp']
    assert precision_score(y,actual)==m['precision'] and recall_score(y,actual)==m['recall'] and f1_score(y,actual)==m['f1']
    assert set(actual)=={False,True} # Genuine retained inputs exercise both trained outputs.


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr('app.rainfall_outlook.datetime',type('Clock',(datetime,),{'now':staticmethod(lambda tz:NOW)}))


def test_live_api_pipeline_with_mocked_transport_and_actual_saved_model(clock):
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.url.params['past_hours']=='74' and request.url.params['timezone']=='UTC'
        assert 'daily' not in request.url.params
        return httpx.Response(200,json=payload())
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await rainfall_outlook(client,*POINT)
    result=asyncio.run(run())
    assert len(calls)==1 and result['model_version']=='rainfall_logistic_v1' and result['probability'] is None
    assert result['prediction']=='heavy_rainfall_predicted' if RainfallModel().predict(result['features']) else result['prediction']=='below_heavy_threshold_predicted'
    assert result['horizon']['start_utc']==CUTOFF.isoformat() and result['horizon']['end_utc']==(CUTOFF+timedelta(hours=24)).isoformat()
    assert datetime.fromisoformat(result['feature_valid_through_utc'])<NOW
    assert result['provider_issued_at'] is None and result['source']['data_kind'].startswith('past-hourly')


@pytest.mark.parametrize('kind',['http','timeout','missing','units','bad_grid'])
def test_provider_failures_and_missing_data_no_prediction(clock,kind):
    p=payload()
    if kind=='missing':p['hourly']['precipitation'][-26]=None
    if kind=='units':p['hourly_units']={**UNITS,'temperature_2m':'°F'}
    if kind=='bad_grid':p['latitude']=None
    def handler(request):
        if kind=='timeout':raise httpx.ReadTimeout('Controlled fixture timeout')
        return httpx.Response(502 if kind=='http' else 200,json=p)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await rainfall_outlook(client,*POINT)
    with pytest.raises(RainfallUnavailable):asyncio.run(run())


@pytest.mark.parametrize('query',['','?latitude=91&longitude=75','?latitude=13&longitude=181','?latitude=nan&longitude=74'])
def test_api_invalid_coordinates_do_not_fetch(query):
    with TestClient(app) as client:assert client.get('/api/ai/rainfall-outlook'+query).status_code==422


def test_api_failure_and_unsupported_location_do_not_substitute(clock):
    calls=[]
    transport=httpx.MockTransport(lambda request:(calls.append(request) or httpx.Response(503)))
    http=httpx.AsyncClient(transport=transport)
    app.dependency_overrides[get_weather]=lambda:SimpleNamespace(client=http)
    try:
        with TestClient(app) as client:
            failed=client.get('/api/ai/rainfall-outlook',params={'latitude':POINT[0],'longitude':POINT[1]})
            assert failed.status_code==503 and failed.json()['prediction'] is None
            response=client.get('/api/ai/rainfall-outlook?latitude=12.9767936&longitude=77.590082')
            assert response.status_code==503 and response.json()['prediction'] is None and len(calls)==1
    finally:
        app.dependency_overrides.pop(get_weather,None);asyncio.run(http.aclose())
