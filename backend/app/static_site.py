"""Serve the built React app from FastAPI in production (one origin for site and API).

Enabled only when FLOODPULSE_STATIC_DIR points at the Vite build. Applies the same frame-denial,
nosniff and referrer headers as the Vite dev/preview servers. Unknown non-API paths return
index.html so client-side routes (/shelters, /admin, ...) work on reload; /api paths never do.
"""
import mimetypes
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

SECURITY_HEADERS = {'X-Frame-Options': 'DENY', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'same-origin'}
mimetypes.add_type('application/manifest+json', '.webmanifest')


def mount_frontend(app: FastAPI, directory):
    root = Path(directory).resolve()
    index = root / 'index.html'
    if not index.is_file():
        raise RuntimeError('FLOODPULSE_STATIC_DIR does not contain a built index.html')

    def respond(path: Path, cache: str):
        return FileResponse(path, headers={**SECURITY_HEADERS, 'Cache-Control': cache})

    @app.api_route('/{requested:path}', methods=['GET', 'HEAD'], include_in_schema=False)
    async def frontend(requested: str, request: Request):
        if requested == 'api' or requested.startswith('api/'):
            raise HTTPException(404, 'Not found')
        candidate = (root / requested).resolve()
        if requested and candidate.is_relative_to(root) and candidate.is_file():
            # Vite fingerprints files under assets/, so they can be cached for a year.
            immutable = candidate.is_relative_to(root / 'assets')
            return respond(candidate, 'public, max-age=31536000, immutable' if immutable else 'no-cache')
        return respond(index, 'no-cache')
