import base64
from datetime import datetime, timezone
from io import BytesIO
import pytest
from fastapi import HTTPException
from PIL import Image
from app.report_images import extract_image

NOW=datetime(2026,10,13,10,tzinfo=timezone.utc)


def photo(format='JPEG',exif=None):
    stream=BytesIO();image=Image.new('RGB',(24,18),(0,120,200))
    image.save(stream,format,**({'exif':exif} if exif else {}))
    return base64.b64encode(stream.getvalue()).decode()


def extract(encoded,consent=True,mime='image/jpeg'):
    return extract_image(encoded,mime,consent,13.4,74.7,40,NOW)


def test_actual_dimensions_sha_and_metadata_stripped_preview():
    exif=Image.Exif();exif[306]='2026:10:13 10:00:00'
    result=extract(photo(exif=exif))
    assert result['metadata']['width']==24 and result['metadata']['height']==18
    assert len(result['sha256'])==len(result['preview_sha256'])==64
    assert 'EXIF_TIMEZONE_UNKNOWN' in result['metadata']['flags']
    assert result['metadata']['vision_model']=='unavailable'
    with Image.open(BytesIO(result['preview'])) as preview:
        assert preview.format=='JPEG' and not preview.getexif()


def test_no_metadata_consent_keeps_only_sanitized_bytes():
    result=extract(photo(),consent=False)
    assert result['original'] is None and result['metadata']['exif'] is None
    assert result['metadata']['flags']==['EXIF_EXTRACTION_NOT_CONSENTED']


@pytest.mark.parametrize('encoded,mime',[(base64.b64encode(b'<svg>fake</svg>').decode(),'image/png'),('!!invalid!!','image/jpeg'),(photo('PNG'),'image/jpeg')])
def test_invalid_images_and_mime_spoofing_are_rejected(encoded,mime):
    with pytest.raises(HTTPException) as error:extract(encoded,mime=mime)
    assert error.value.status_code==422


def test_image_gps_and_time_disagreement_is_a_flag_not_a_flood_label():
    exif=Image.Exif();exif[34853]={1:'N',2:(13,0,0),3:'E',4:(74,0,0)}
    exif[34665]={36867:'2026:10:13 04:00:00',36881:'+00:00'}
    result=extract(photo(exif=exif))
    flags=result['metadata']['flags']
    assert 'EXIF_GPS_DIFFERS_FROM_SUBMISSION' in flags and 'EXIF_TIME_DIFFERS_OVER_ONE_HOUR' in flags
    assert result['metadata']['exif']['trust']=='user_supplied_metadata_not_verified'


def test_oversized_pixel_dimensions_rejected_before_full_decode():
    stream=BytesIO();Image.new('1',(4000,3000)).save(stream,'PNG')
    with pytest.raises(HTTPException):extract(base64.b64encode(stream.getvalue()).decode(),mime='image/png')
