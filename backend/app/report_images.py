"""Actual decoded attributes only. No vision model or flood-depth inference."""
import base64
import binascii
from datetime import datetime, timezone
import hashlib
from io import BytesIO
from math import asin, cos, radians, sin, sqrt, isfinite
import threading
import warnings
from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 10000000
GATE = threading.BoundedSemaphore(2)


def extract_image(encoded, mime, metadata_consent, latitude, longitude, accuracy, observed_at):
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, 'Invalid photo encoding') from None
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(413, 'Photo must be at most 5 MiB')
    if not GATE.acquire(timeout=1):
        raise HTTPException(429, 'Image processing busy; retry later')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw), formats=['JPEG', 'PNG']) as probe:
                format = probe.format
                if mime != {'JPEG': 'image/jpeg', 'PNG': 'image/png'}.get(format):
                    raise ValueError('Photo content does not match selected MIME type')
                if probe.width * probe.height > MAX_PIXELS or getattr(probe, 'n_frames', 1) != 1:
                    raise ValueError('Photo must be a single image up to 10 megapixels')
                probe.verify()
            with Image.open(BytesIO(raw), formats=['JPEG', 'PNG']) as image:
                image.load()
                info = {'format': format, 'width': image.width, 'height': image.height,
                        'original_bytes': len(raw), 'source': 'DECODED_IMAGE_METADATA',
                        'vision_model': 'unavailable', 'exif': None, 'flags': []}
                if metadata_consent:
                    exif = image.getexif()
                    captured = exif.get(306)
                    try:
                        inner = exif.get_ifd(34665)
                        captured = inner.get(36867, captured)
                        offset = inner.get(36881)
                    except (KeyError, ValueError, TypeError):
                        offset = None
                    info['exif'] = {'captured_at_raw': str(captured)[:40] if captured else None,
                                    'offset_raw': str(offset)[:10] if offset else None,
                                    'gps': None, 'trust': 'user_supplied_metadata_not_verified'}
                    if captured:
                        if offset:
                            try:
                                clock = datetime.strptime(str(captured) + str(offset), '%Y:%m:%d %H:%M:%S%z')
                                info['exif']['captured_at_utc'] = clock.astimezone(timezone.utc).isoformat()
                                if abs((clock - observed_at).total_seconds()) > 3600:
                                    info['flags'].append('EXIF_TIME_DIFFERS_OVER_ONE_HOUR')
                            except ValueError:
                                info['flags'].append('EXIF_TIME_INVALID')
                        else:
                            info['flags'].append('EXIF_TIMEZONE_UNKNOWN')
                    try:
                        gps = exif.get_ifd(34853)
                        def degrees(values):
                            return float(values[0]) + float(values[1])/60 + float(values[2])/3600
                        if gps:
                            lat = degrees(gps[2]) * (-1 if gps[1] == 'S' else 1)
                            lon = degrees(gps[4]) * (-1 if gps[3] == 'W' else 1)
                            if gps[1] not in ('N','S') or gps[3] not in ('E','W') or not isfinite(lat) or not isfinite(lon) or abs(lat)>90 or abs(lon)>180:
                                raise ValueError()
                            info['exif']['gps'] = {'latitude': lat, 'longitude': lon}
                            a = sin(radians(lat-latitude)/2)**2 + cos(radians(latitude))*cos(radians(lat))*sin(radians(lon-longitude)/2)**2
                            distance = 6371000 * 2 * asin(sqrt(min(1, max(0, a))))
                            info['exif']['gps_difference_m'] = round(distance)
                            if distance > max(100, accuracy):
                                info['flags'].append('EXIF_GPS_DIFFERS_FROM_SUBMISSION')
                    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
                        info['flags'].append('EXIF_GPS_INVALID')
                else:
                    info['flags'].append('EXIF_EXTRACTION_NOT_CONSENTED')
                if accuracy > 100:
                    info['flags'].append('COARSE_SUBMITTED_GPS')
                # New image discards EXIF, GPS, text chunks, device/ICC metadata.
                oriented = ImageOps.exif_transpose(image).convert('RGB')
                clean = Image.new('RGB', oriented.size)
                clean.paste(oriented)
                clean.thumbnail((1920, 1920))
                output = BytesIO(); clean.save(output, 'JPEG', quality=85)
                preview = output.getvalue()
                return {'original': raw if metadata_consent else None, 'preview': preview,
                        'sha256': hashlib.sha256(raw).hexdigest(),
                        'preview_sha256': hashlib.sha256(preview).hexdigest(), 'metadata': info}
    except (ValueError, OSError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise HTTPException(422, 'Photo must decode as one JPEG/PNG image up to 10 megapixels with matching MIME type') from None
    finally:
        GATE.release()
