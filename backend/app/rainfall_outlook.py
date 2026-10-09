"""Experimental trained rainfall model, separate from unavailable flood prediction."""
import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import httpx
import numpy as np

from .rainfall_features import (FEATURES, VARIABLES, VERSION, THRESHOLD_MM, RainfallUnavailable,
                               parse_hourly, past_features, require)
from .weather import API_URL, number

ARTIFACT = Path(__file__).resolve().parents[1] / 'models' / VERSION


class RainfallModel:
    """Portable JSON contains fitted sklearn scaler and logistic parameters, no pickle."""
    def __init__(self, directory=ARTIFACT):
        path=Path(directory);raw=(path/'model.json').read_bytes();self.metadata=json.loads((path/'metadata.json').read_bytes());model=json.loads(raw)
        require(len(raw)<20000 and hashlib.sha256(raw).hexdigest()==self.metadata['model_sha256'],'Trained model checksum failed')
        require(self.metadata['target']['threshold_mm']==THRESHOLD_MM and self.metadata['target']['horizon_hours']==24 and self.metadata['features']==FEATURES,'Metadata target schema mismatch')
        require(model['version']==self.metadata['version']==VERSION and model['features']==FEATURES and model['feature_order']==list(FEATURES) and model['threshold_mm']==THRESHOLD_MM and model['classes']==[0,1],'Model feature/target schema mismatch')
        self.mean=np.asarray(model['scaler']['mean'],dtype=float);self.scale=np.asarray(model['scaler']['scale'],dtype=float)
        self.coefficients=np.asarray(model['logistic_regression']['coefficients'],dtype=float);self.intercept=float(model['logistic_regression']['intercept'])
        require(all(a.shape==(len(FEATURES),) and np.isfinite(a).all() for a in [self.mean,self.scale,self.coefficients]) and np.all(self.scale>0) and np.isfinite(self.intercept),'Invalid fitted model parameters')

    def supported(self, latitude, longitude):
        return next((p for p in self.metadata['locations'] if abs(p['latitude']-latitude)<1e-7 and abs(p['longitude']-longitude)<1e-7),None)

    def predict(self, features):
        require(list(features)==list(FEATURES),'Feature order/schema mismatch')
        x=np.asarray([features[f] for f in FEATURES],dtype=float)
        require(x.shape==self.mean.shape and np.isfinite(x).all(),'Missing or non-finite model feature')
        return bool(((x-self.mean)/self.scale)@self.coefficients+self.intercept>0)


@lru_cache(maxsize=1)
def get_model():
    return RainfallModel()


async def rainfall_outlook(client, latitude, longitude, model=None):
    try:
        latitude=number(latitude,minimum=-90,maximum=90);longitude=number(longitude,minimum=-180,maximum=180)
        require(latitude is not None and longitude is not None,'Coordinates required')
        model=model or get_model();point=model.supported(latitude,longitude)
        require(point is not None,'Experimental model supports only the verified Kundapur and Mangaluru training points. Weather remains available elsewhere.')
        params={'latitude':latitude,'longitude':longitude,'hourly':','.join(VARIABLES),'past_hours':74,'forecast_hours':1,
                'timezone':'UTC','temperature_unit':'celsius','precipitation_unit':'mm'}
        # Dedicated past-hourly inputs, not a duplicate seven-day weather fetch.
        async with asyncio.timeout(10):
            response=await client.get(API_URL,params=params)
        response.raise_for_status();raw=response.content;payload=response.json()
        require(len(raw)<200000,'Hourly response exceeds bound')
        retrieved=datetime.now(timezone.utc)
        require('latitude' in payload and 'longitude' in payload,'Provider grid unavailable')
        grid={k:number(payload[k],minimum=-90 if k=='latitude' else -180,maximum=90 if k=='latitude' else 180) for k in ('latitude','longitude')}
        require(all(v is not None for v in grid.values()),'Provider grid unavailable')
        series=parse_hourly(payload)
        # Start at the next full UTC hour. All input stamps are <= the last
        # completed hour, strictly before this horizon; no future rows consumed.
        cutoff=retrieved.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
        features=past_features(series,cutoff)
        require(cutoff-timedelta(hours=1)<=retrieved,'Future input cutoff')
        prediction=model.predict(features)
        return {'status':'available','experimental':True,'model_version':VERSION,
                'model_sha256':model.metadata['model_sha256'],'location':{'name':point['name'],'id':point['id'],'latitude':latitude,'longitude':longitude},
                'provider_grid':grid,'retrieved_at':retrieved.isoformat(),'provider_issued_at':None,
                'horizon':{'hours':24,'start_utc':cutoff.isoformat(),'end_utc':(cutoff+timedelta(hours=24)).isoformat(),
                           'meaning':'Next 24 complete UTC hours, beginning at the next full hour (within one hour of retrieval).'},
                'target':model.metadata['target'],'prediction':'heavy_rainfall_predicted' if prediction else 'below_heavy_threshold_predicted',
                'prediction_text':'At least 64.5 mm predicted by the experimental model' if prediction else 'Below 64.5 mm predicted by the experimental model',
                'probability':None,'probability_status':'not_calibrated_not_exposed',
                'features':features,'feature_units':FEATURES,'feature_valid_through_utc':(cutoff-timedelta(hours=1)).isoformat(),
                'hourly_response_sha256':hashlib.sha256(raw).hexdigest(),
                'source':{'name':'Open-Meteo','url':'https://open-meteo.com/en/docs','license':'CC BY 4.0','data_kind':'past-hourly best-match weather model output, not station observations'},
                'training_serving_parity':model.metadata['training_serving_parity'],
                'limitations':'Experimental reanalysis-trained grid-scale rainfall proxy at two points. Not station-validated or an official IMD warning. Below threshold does not mean dry or safe. Not flood probability, flood prediction or emergency advice.'}
    except RainfallUnavailable:
        raise
    except (httpx.HTTPError,TimeoutError) as exc:
        raise RainfallUnavailable('Hourly weather provider unavailable; no replacement prediction was generated.') from exc
    except (OSError,ValueError,KeyError,TypeError,OverflowError) as exc:
        raise RainfallUnavailable('Trained model or hourly inputs are missing, incompatible or invalid; no prediction was generated.') from exc
