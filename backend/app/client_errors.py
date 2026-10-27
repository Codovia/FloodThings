"""Browser crash reports: the page path and a short message go to the server log under the visitor's error ID.

No query strings, coordinates, form contents or stack traces are accepted, so nothing personal is logged. Same-origin
only, and the general public-API rate limit applies (rate_limit.py).
"""
import logging
import re

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .shelter_security import SecurityConfig

router = APIRouter()
log = logging.getLogger('floodpulse')


class ClientError(BaseModel):
    model_config = ConfigDict(extra='forbid')
    error_id: str = Field(pattern=r'^[0-9a-f]{12}$')
    page: str = Field(pattern=r'^/[A-Za-z0-9/_-]{0,80}$')
    message: str = Field(min_length=1, max_length=300)

    @field_validator('message')
    @classmethod
    def plain(cls, value):
        # Control characters could forge log lines; long digit runs may be coordinates or phone numbers.
        return re.sub(r'\d{4,}', '#', re.sub(r'[\x00-\x1f\x7f]', ' ', value)).strip() or 'unknown'


@router.post('/api/client-errors', status_code=204)
def client_error(payload: ClientError, request: Request):
    SecurityConfig().same_origin(request)
    log.warning('browser error %s on %s: %s', payload.error_id, payload.page, payload.message)
    return Response(status_code=204)
