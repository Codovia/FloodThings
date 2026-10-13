"""Disposable real PostGIS evidence flow; no actual citizen images or reports."""
import base64
from datetime import timedelta
from io import BytesIO
import secrets
import uuid
import pytest
from PIL import Image
from sqlalchemy import select, text, update
from app.main import app
from app.reports import ReportStore, get_report_store
from app.report_schema import reports, images, audit
from app.shelter_security import now
from test_shelter_postgres import api, sign_in, ORIGIN


@pytest.fixture
def report_api(api):
    client,db,*_=api
    app.dependency_overrides[get_report_store]=lambda:ReportStore(db)
    try:
        yield api
    finally:
        app.dependency_overrides.pop(get_report_store,None)


def payload(photo=True):
    stream=BytesIO(); image=Image.new('RGB',(16,12),(0,120,200)); exif=Image.Exif();exif[306]='2026:10:13 10:00:00';image.save(stream,'JPEG',exif=exif)
    body={'request_id':str(uuid.uuid4()),'withdrawal_secret':secrets.token_hex(32),'event_type':'drainage_blockage','description':'TEST ONLY synthetic image/report, not an actual incident','observed_at':now().isoformat(),'gps_at':now().isoformat(),'latitude':13.4,'longitude':74.7,'accuracy_m':40,'consent':True,'metadata_consent':True}
    if photo:
        body.update(photo_base64=base64.b64encode(stream.getvalue()).decode(),photo_mime='image/jpeg',image_rights=True)
    return body


def submit(api,body=None):
    body=body or payload()
    response=api[0].post('/api/reports',headers={'Origin':ORIGIN,'X-FloodPulse-Report':'1'},json=body)
    assert response.status_code==201,response.text
    return body,response.json()


def test_full_photo_gps_private_moderation_evidence_flow_and_audit(report_api):
    client,db,*_=report_api;body,row=submit(report_api)
    assert row['state']=='SUBMITTED' and row['source']=='USER_REPORTED'
    assert client.get('/api/admin/reports').status_code==401
    assert client.get('/api/admin/reports/'+row['id']+'/photo').status_code==401
    assert client.get('/api/reports/'+row['id']).status_code==404
    headers=sign_in(report_api)
    r=client.get('/api/admin/reports').json()['reports'][0]
    assert r['image_metadata']['width']==16 and r['image_metadata']['height']==12
    assert r['image_metadata']['vision_model']=='unavailable'
    assert 'EXIF_TIMEZONE_UNKNOWN' in r['image_metadata']['flags']
    assert 'withdrawal_hash' not in r and 'position' not in r
    assert client.get('/api/admin/reports/evidence').json()['records']==[]
    response=client.get('/api/admin/reports/'+row['id']+'/photo')
    assert response.headers['cache-control']=='no-store'
    with Image.open(BytesIO(response.content)) as image:
        assert not image.getexif()
    response=client.post('/api/admin/reports/'+row['id']+'/review',headers=headers,json={'state':'APPROVED','revision':1,'reason':'TEST ONLY fixture reviewed'})
    assert response.status_code==409
    for state,revision in [('UNDER_REVIEW',1),('APPROVED',2)]:
        response=client.post('/api/admin/reports/'+row['id']+'/review',headers=headers,json={'state':state,'revision':revision,'reason':'TEST ONLY fixture reviewed, not verified flooding'})
        assert response.status_code==200,response.text
    evidence=client.get('/api/admin/reports/evidence').json()
    assert len(evidence['records'])==1 and evidence['label_eligibility']=='NOT_ASSESSED'
    assert evidence['records'][0]['training_eligible'] is False and evidence['records'][0]['official_warning'] is False
    history=client.get('/api/admin/reports/'+row['id']+'/audit').json()['events']
    assert [r['after_state'] for r in history]==['SUBMITTED','SUBMITTED','UNDER_REVIEW','APPROVED']
    with db.connect() as c:
        point=c.execute(text('SELECT ST_X(position), ST_Y(position) FROM citizen_reports')).one()
        assert tuple(point)==(74.7,13.4)
    assert client.post('/api/admin/reports/'+row['id']+'/review',headers=headers,json={'state':'REJECTED','revision':2,'reason':'Outdated fixture review'}).status_code==409


def test_idempotent_retries_cannot_replace_content(report_api):
    client,db,*_=report_api;body,row=submit(report_api)
    assert submit(report_api,body)[1]['id']==row['id']
    body['description']='TEST ONLY changed content must not overwrite'
    assert client.post('/api/reports',headers={'Origin':ORIGIN,'X-FloodPulse-Report':'1'},json=body).status_code==409
    with db.connect() as c:
        assert len(c.execute(select(reports)).all())==1 and len(c.execute(select(audit)).all())==1


def test_csrf_origin_validation_upload_abuse_and_redaction(report_api):
    client=report_api[0];body=payload()
    assert client.post('/api/reports',json=body).status_code==403
    assert client.post('/api/reports',headers={'Origin':'https://evil.test','X-FloodPulse-Report':'1'},json=body).status_code==403
    bad={**body,'consent':False}
    response=client.post('/api/reports',headers={'Origin':ORIGIN,'X-FloodPulse-Report':'1'},json=bad)
    assert response.status_code==422 and body['withdrawal_secret'] not in response.text
    headers=sign_in(report_api)
    assert client.post('/api/admin/reports/retention/purge',headers={'Origin':ORIGIN}).status_code==403
    assert client.get('/api/admin/reports?limit=1000').status_code==422


def test_withdrawal_erases_private_data_and_excludes_evidence(report_api):
    client,db,*_=report_api;body,row=submit(report_api)
    path='/api/reports/'+row['id']+'/withdraw'
    assert client.post(path,headers={'Origin':ORIGIN},json={'withdrawal_secret':secrets.token_hex(32)}).status_code==404
    response=client.post(path,headers={'Origin':ORIGIN},json={'withdrawal_secret':body['withdrawal_secret']})
    assert response.status_code==200
    assert client.post(path,headers={'Origin':ORIGIN},json={'withdrawal_secret':body['withdrawal_secret']}).json()['state']=='WITHDRAWN'
    with db.connect() as c:
        r=c.execute(select(reports)).mappings().one()
        assert r['latitude'] is None and r['image_metadata'] is None and r['description']=='[private evidence removed]'
        assert not c.execute(select(images)).all()
        assert len(c.execute(select(audit)).all())==2


def test_rejected_reports_never_become_evidence_and_expired_photos_are_private(report_api):
    client,db,*_=report_api;body,row=submit(report_api);headers=sign_in(report_api)
    for state,rev in [('UNDER_REVIEW',1),('REJECTED',2)]:
        assert client.post('/api/admin/reports/'+row['id']+'/review',headers=headers,json={'state':state,'revision':rev,'reason':'TEST ONLY rejection evidence'}).status_code==200
    assert client.get('/api/admin/reports/evidence').json()['records']==[]
    with db.begin() as c:
        c.execute(update(images).values(expires_at=now()-timedelta(seconds=1)))
        c.execute(update(reports).values(received_at=now()-timedelta(days=31)))
    assert client.get('/api/admin/reports/'+row['id']+'/photo').status_code==404
    assert client.post('/api/admin/reports/retention/purge',headers=headers).json()['reports_removed']==1
    with db.connect() as c:
        assert c.execute(select(reports.c.state)).scalar_one()=='WITHDRAWN'


def test_invalid_image_rolls_back_and_rate_limit_is_persistent(report_api):
    client,db,*_=report_api;body=payload();body['photo_base64']=base64.b64encode(b'<svg>NOT AN IMAGE</svg>').decode()
    response=client.post('/api/reports',headers={'Origin':ORIGIN,'X-FloodPulse-Report':'1'},json=body)
    assert response.status_code==422
    with db.connect() as c:
        assert not c.execute(select(reports)).all()
    for _ in range(4):submit(report_api,payload(False))
    assert client.post('/api/reports',headers={'Origin':ORIGIN,'X-FloodPulse-Report':'1'},json=payload(False)).status_code==429
