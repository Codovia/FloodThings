#!/usr/bin/env python3
"""Explicitly requested single-archive acquisition with checked Range resumption.

Only the pinned official v1 resource is permitted. No credentials, other datasets,
model training or overwrite of a completed archive. Every response is bounded.
"""
import argparse
import concurrent.futures
import datetime as dt
import fcntl
import hashlib
import http.client
import json
from pathlib import Path
import re
import shutil
import time
import urllib.request

URL = "https://zenodo.org/records/18647054/files/groundsource_2026.parquet"
SIZE = 667122400
MD5 = "cd1b5de6508f7aad8e1d1d0dd4cecea6"
CHUNK = 4 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/groundsource/zenodo_18647054_v1"


def file_hashes(path):
    sha, md5 = hashlib.sha256(), hashlib.md5(usedforsecurity=False)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
            md5.update(block)
    return {"bytes": path.stat().st_size, "sha256": sha.hexdigest(), "md5": md5.hexdigest()}


def preflight(record, page, directory):
    files = [f for f in record.get("files", []) if f.get("key") == "groundsource_2026.parquet"]
    if record.get("id") != 18647054 or record.get("doi") != "10.5281/zenodo.18647054" or len(files) != 1:
        raise ValueError("Publisher/resource identity differs")
    if record.get("metadata", {}).get("license", {}).get("id") != "cc-by-4.0":
        raise ValueError("Publisher licence changed")
    if files[0].get("size") != SIZE or files[0].get("checksum") != "md5:" + MD5:
        raise ValueError("Publisher size/checksum changed")
    if not re.search(r"Version\s+v1", re.sub(r"<[^>]+>", " ", page)):
        raise ValueError("Official HTML v1 designation absent; API has no version field")
    if shutil.disk_usage(directory).free < SIZE + 2 * 1024**3:
        raise ValueError("Insufficient free disk space for archive and bounded analysis")
    return {"record": 18647054, "version": "v1", "licence": "CC BY 4.0",
            "url": URL, "expected_bytes": SIZE, "publisher_md5": MD5,
            "free_disk_bytes": shutil.disk_usage(directory).free}


def verify(path):
    result = file_hashes(path)
    if result["bytes"] != SIZE or result["md5"] != MD5:
        raise ValueError("Full downloaded archive size/MD5 mismatch; do not extract")
    return result


def transfer(part, opener=urllib.request.urlopen, size=SIZE, chunk=CHUNK, receipt=None):
    """Append only a response's declared range; a failed response remains resumable."""
    if not 0 < chunk <= CHUNK or size <= 0:
        raise ValueError("Invalid transfer bounds")
    offset = part.stat().st_size if part.exists() else 0
    if offset > size:
        raise ValueError("Partial archive larger than publisher size")
    while offset < size:
        end = min(size - 1, offset + chunk - 1)
        request = urllib.request.Request(URL, headers={"Range": f"bytes={offset}-{end}", "Accept-Encoding": "identity"})
        with opener(request, timeout=90) as response:
            expected = f"bytes {offset}-{end}/{size}"
            if response.status != 206 or response.headers.get("Content-Range") != expected:
                raise ValueError("Server ignored or changed Range; partial bytes untouched")
            if int(response.headers.get("Content-Length", -1)) != end - offset + 1:
                raise ValueError("Range length differs")
            start, remaining = offset, end - offset + 1
            digest = hashlib.sha256()
            with part.open("ab") as stream:
                while remaining:
                    body = response.read(min(1024 * 1024, remaining))
                    if not body:
                        raise ValueError("Interrupted range; preserve exact written offset and resume")
                    if len(body) > remaining:
                        raise ValueError("Response exceeded requested range")
                    stream.write(body)
                    digest.update(body)
                    remaining -= len(body)
                    offset += len(body)
                if response.read(1):
                    raise ValueError("Response exceeded requested range")
            row = {"start": start, "end": end, "total": size, "sha256": digest.hexdigest(),
                   "received_at": dt.datetime.now(dt.timezone.utc).isoformat()}
            if receipt:
                with receipt.open("a") as stream:
                    stream.write(json.dumps(row) + "\n")
            print(f"Archive bytes retained: {offset}/{size}", flush=True)


def parallel_transfer(part, opener=urllib.request.urlopen, size=SIZE, chunk=CHUNK, workers=8):
    """Bounded concurrent ranges of the same archive, assembled in exact order.

Each worker streams to an ignored segment file. Completed segments are reused;
interrupted segments resume at their own offsets. Only the parent appends the
main partial archive. At most eight MiB streaming buffers, no archive in RAM.
"""
    if not 1 <= workers <= 8 or not 0 < chunk <= CHUNK:
        raise ValueError("Parallel transfer bounds invalid")
    pieces = part.parent / "range_chunks"
    pieces.mkdir(exist_ok=True)
    offset = part.stat().st_size if part.exists() else 0
    if offset > size:
        raise ValueError("Partial archive larger than publisher size")
    def fetch(start,end):
        segment=pieces/f"{start}-{end}.part"
        failures=0
        while True:
            retained=segment.stat().st_size if segment.exists() else 0
            if retained>end-start+1:raise ValueError("Range segment oversized")
            if retained==end-start+1:return segment
            first=start+retained
            request=urllib.request.Request(URL,headers={"Range":f"bytes={first}-{end}","Accept-Encoding":"identity"})
            try:
                with opener(request,timeout=90) as response:
                    if response.status!=206 or response.headers.get("Content-Range")!=f"bytes {first}-{end}/{size}":
                        raise ValueError("Server ignored or changed Range")
                    remaining=end-first+1
                    if int(response.headers.get("Content-Length",-1))!=remaining:raise ValueError("Range length differs")
                    with segment.open("ab") as stream:
                        while remaining:
                            body=response.read(min(1024*1024,remaining))
                            if not body:raise OSError("Interrupted range")
                            if len(body)>remaining:raise ValueError("Range overrun")
                            stream.write(body);remaining-=len(body)
                        if response.read(1):raise ValueError("Range overrun")
                return segment
            except (OSError,http.client.IncompleteRead) as error:
                after=segment.stat().st_size if segment.exists() else 0
                failures=0 if after>retained else failures+1
                print(f"Range {start}-{end} interrupted; retained {after} bytes: {error}",flush=True)
                if failures>=5:raise ValueError("Five range attempts made no progress") from error
                time.sleep(2)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        while offset<size:
            ranges=[(start,min(start+chunk-1,size-1)) for start in range(offset,min(size,offset+workers*chunk),chunk)]
            pending=[pool.submit(fetch,start,end) for start,end in ranges]
            for (start,end),future in zip(ranges,pending,strict=True):
                segment=future.result()
                result=file_hashes(segment)
                if result['bytes']!=end-start+1:raise ValueError("Segment length differs")
                actual=part.stat().st_size if part.exists() else 0
                if actual!=start:raise ValueError("Partial file changed concurrently; stop before append")
                with part.open('ab') as target,segment.open('rb') as source:
                    shutil.copyfileobj(source,target,length=1024*1024)
                offset=end+1
                with (part.parent/'range-receipts.jsonl').open('a') as receipt:
                    receipt.write(json.dumps({'start':start,'end':end,'total':size,'sha256':result['sha256'],
                                              'received_at':dt.datetime.now(dt.timezone.utc).isoformat()})+'\n')
                segment.unlink()
                print(f"Archive bytes retained: {offset}/{size}",flush=True)


def _acquire_locked(directory, record, page):
    checked = preflight(record, page, directory)
    final = directory / "groundsource_2026.parquet"
    if final.exists():
        return verify(final)
    part = final.with_suffix(".parquet.part")
    failures = 0
    while True:
        before = part.stat().st_size if part.exists() else 0
        try:
            parallel_transfer(part)
            break
        except (OSError, http.client.IncompleteRead, ValueError) as error:
            if isinstance(error, ValueError) and not str(error).startswith("Interrupted range"):
                raise
            after = part.stat().st_size if part.exists() else 0
            failures = 0 if after > before else failures + 1
            print(f"Interrupted transfer at {after} bytes; resume only this archive: {error}", flush=True)
            if failures >= 5:
                raise ValueError("Five transfers made no progress; preserve partial archive") from error
            time.sleep(2)
    result = verify(part)
    part.rename(final)
    (directory / "integrity.json").write_text(json.dumps({**checked, **result, "full_publisher_checksum_verified": True}, indent=2) + "\n")
    return result


def acquire(directory, record, page):
    with (directory / "download.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Another archive transfer holds the exclusive lock") from error
        return _acquire_locked(directory,record,page)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "download", "verify"))
    parser.add_argument("--raw", type=Path, default=RAW)
    parser.add_argument("--page", type=Path, default=ROOT / "data/recovery/phase12c_v1/publisher-page.html")
    args = parser.parse_args()
    try:
        if args.raw.resolve() != RAW.resolve():
            raise ValueError("CLI acquisition path must be the existing ignored research-data structure")
        record = json.loads((args.raw / "publisher-record.json").read_text())
        if args.command == "verify":
            result = verify(args.raw / "groundsource_2026.parquet")
        elif args.command == "preflight":
            result = preflight(record, args.page.read_text(), args.raw)
        else:
            result = acquire(args.raw, record, args.page.read_text())
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, f"Groundsource acquisition failed: {error}\n")
