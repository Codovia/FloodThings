"""Opaque server-side sessions; no public administrator registration."""
import hashlib
import hmac
import os
import secrets
import base64
import threading
from datetime import datetime,timezone
from functools import lru_cache
from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,Field

class ScryptHasher:
    """OWASP scrypt fallback: N=2^17, r=8, p=1, random 16-byte salt."""
    prefix='$scrypt$ln=17,r=8,p=1$'
    gate=threading.BoundedSemaphore(2)

    def derive(self,password,salt):
        if not self.gate.acquire(timeout=1):
            raise HTTPException(429,'Authentication busy; retry later')
        try:
            return hashlib.scrypt(password.encode('utf-8'),salt=salt,n=131072,r=8,p=1,dklen=64,maxmem=268435456)
        finally:self.gate.release()

    def hash(self,password):
        salt=secrets.token_bytes(16);derived=self.derive(password,salt)
        return self.prefix+base64.b64encode(salt).decode()+'$'+base64.b64encode(derived).decode()

    def verify(self,encoded,password):
        if not encoded.startswith(self.prefix):return False
        try:
            salt,value=encoded[len(self.prefix):].split('$')
            salt=base64.b64decode(salt,validate=True);value=base64.b64decode(value,validate=True)
            if len(salt)!=16 or len(value)!=64:return False
            return hmac.compare_digest(value,self.derive(password,salt))
        except (ValueError,TypeError):return False


HASHER=ScryptHasher()


def now():
    return datetime.now(timezone.utc)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(token):
    return digest('csrf:'+token)


@lru_cache(maxsize=1)
def dummy_hash():
    return HASHER.hash(secrets.token_urlsafe(32))


def password_matches(encoded,password):
    return HASHER.verify(encoded,password)


class Login(BaseModel):
    model_config=ConfigDict(extra='forbid')
    username: str=Field(min_length=3,max_length=64,pattern=r'^[a-z][a-z0-9._-]*$')
    password: str=Field(min_length=1,max_length=128)


class SecurityConfig:
    def __init__(self):
        origin=os.environ.get('SHELTER_PUBLIC_ORIGIN','')
        p=urlsplit(origin)
        if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.path or p.query or p.fragment:
            raise HTTPException(503,'Administrator origin is not configured correctly')
        self.origin=origin
        self.secure=os.environ.get('SHELTER_COOKIE_SECURE','true')=='true'
        if os.environ.get('SHELTER_COOKIE_SECURE','true') not in ('true','false'):
            raise HTTPException(503,'Invalid session security configuration')
        if not self.secure and (p.scheme!='http' or p.hostname not in ('localhost','127.0.0.1','::1')):
            raise HTTPException(503,'Insecure cookies are permitted only for explicit loopback development')
        if self.secure and p.scheme!='https':
            raise HTTPException(503,'Secure session deployment requires an HTTPS origin')
        self.cookie='__Host-floodpulse_session' if self.secure else 'floodpulse_dev_session'

    def same_origin(self,request):
        if request.headers.get('origin')!=self.origin or request.headers.get('sec-fetch-site')=='cross-site':
            raise HTTPException(403,'Same-origin request required')

    def require_csrf(self,request,token):
        self.same_origin(request)
        supplied=request.headers.get('x-csrf-token','')
        if not supplied or not hmac.compare_digest(supplied.encode('utf-8'),csrf_token(token).encode('ascii')):
            raise HTTPException(403,'CSRF token required')

    def set_cookie(self,response,token):
        response.set_cookie(self.cookie,token,max_age=8*60*60,httponly=True,secure=self.secure,samesite='strict',path='/')

    def clear_cookie(self,response):
        response.delete_cookie(self.cookie,path='/',httponly=True,secure=self.secure,samesite='strict')
