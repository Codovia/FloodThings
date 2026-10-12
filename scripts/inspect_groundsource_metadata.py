#!/usr/bin/env python3
"""Inspect bounded publisher Parquet footer receipts, never fetch event pages.

No optional Parquet dependencies: decode the Apache Thrift Compact metadata
protocol with explicit size/depth limits. This is metadata inspection, not a
general Parquet reader. Full publisher MD5 cannot be verified from partial bytes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

MAX_FOOTER_BYTES = 1024 * 1024
TYPES = {0: "BOOLEAN", 1: "INT32", 2: "INT64", 3: "INT96", 4: "FLOAT", 5: "DOUBLE", 6: "BYTE_ARRAY", 7: "FIXED_LEN_BYTE_ARRAY"}


class CompactReader:
    def __init__(self, body):
        if len(body) > MAX_FOOTER_BYTES:
            raise ValueError("Metadata exceeds one MiB limit")
        self.body, self.position, self.fields = body, 0, 0

    def take(self, size):
        if size < 0 or self.position + size > len(self.body):
            raise ValueError("Truncated Compact metadata")
        value = self.body[self.position:self.position + size]
        self.position += size
        return value

    def byte(self):
        return self.take(1)[0]

    def varint(self):
        value = 0
        for shift in range(0, 70, 7):
            byte = self.byte()
            if shift == 63 and byte > 1:
                raise ValueError("Oversized Compact varint")
            value |= (byte & 127) << shift
            if byte < 128:
                return value
        raise ValueError("Oversized Compact varint")

    def integer(self):
        value = self.varint()
        return (value >> 1) ^ -(value & 1)

    def value(self, kind, depth=0, collection=False):
        if depth > 32:
            raise ValueError("Metadata nesting limit exceeded")
        if kind in (1, 2):
            if collection:
                boolean = self.byte()
                if boolean not in (1, 2):
                    raise ValueError("Invalid Compact boolean")
                return boolean == 1
            return kind == 1
        if kind == 3:
            return struct.unpack("b", self.take(1))[0]
        if kind in (4, 5, 6):
            return self.integer()
        if kind == 7:
            return struct.unpack("<d", self.take(8))[0]
        if kind == 8:
            return self.take(self.varint())
        if kind in (9, 10):
            header = self.byte()
            size = header >> 4
            if size == 15:
                size = self.varint()
            if size > 100000:
                raise ValueError("Metadata collection limit exceeded")
            return [self.value(header & 15, depth + 1, True) for _ in range(size)]
        if kind == 11:
            size = self.varint()
            if size > 100000:
                raise ValueError("Metadata map limit exceeded")
            kinds = self.byte() if size else 0
            return [(self.value(kinds >> 4, depth + 1, True), self.value(kinds & 15, depth + 1, True)) for _ in range(size)]
        if kind == 12:
            result, previous = {}, 0
            while True:
                header = self.byte()
                if not header:
                    return result
                field = previous + (header >> 4) if header >> 4 else self.integer()
                if field <= 0 or field in result:
                    raise ValueError("Invalid/duplicate Compact field")
                self.fields += 1
                if self.fields > 10000:
                    raise ValueError("Metadata field limit exceeded")
                result[field] = self.value(header & 15, depth + 1)
                previous = field
        raise ValueError(f"Unsupported Compact type {kind}")


def decode_footer(body):
    reader = CompactReader(body)
    result = reader.value(12)
    if reader.position != len(body):
        raise ValueError("Unconsumed footer bytes")
    if not isinstance(result.get(2), list) or not isinstance(result.get(4), list) or not isinstance(result.get(3), int):
        raise ValueError("Invalid Parquet FileMetaData")
    if isinstance(result[3], bool) or result[3] < 0 or any(not isinstance(g, dict) or
            isinstance(g.get(3), bool) or not isinstance(g.get(3), int) or g[3] < 0 for g in result[4]):
        raise ValueError("Invalid Parquet row counts")
    if sum(group[3] for group in result[4]) != result[3]:
        raise ValueError("Row-group count mismatch")
    return result


def text(value):
    if not isinstance(value, bytes):
        raise ValueError("Expected UTF-8 metadata bytes")
    return value.decode("utf-8", errors="strict")


def range_receipt(headers, body, start, end, total):
    """Reject servers ignoring Range; no partial file is called a full download."""
    statuses = re.findall(r"^HTTP/\S+ (\d+)", headers, re.MULTILINE)
    ranges = re.findall(r"^content-range:\s*bytes (\d+)-(\d+)/(\d+)\s*$", headers, re.MULTILINE | re.IGNORECASE)
    if not statuses or statuses[-1] != "206" or len(ranges) != 1 or tuple(map(int, ranges[0])) != (start, end, total):
        raise ValueError("HTTP Range not honored or publisher size differs")
    if len(body) != end - start + 1:
        raise ValueError("Range body length mismatch")


def inspect(record, tail, footer, tail_headers, footer_headers):
    if record.get("id") != 18647054 or record.get("metadata", {}).get("license", {}).get("id") != "cc-by-4.0":
        raise ValueError("Publisher identity/licence changed; review before use")
    files = [f for f in record.get("files", []) if f.get("key") == "groundsource_2026.parquet"]
    if len(files) != 1:
        raise ValueError("Publisher file identity ambiguous")
    info = files[0]
    size = info["size"]
    if not isinstance(size, int) or size < 12 or len(tail) != 8 or tail[-4:] != b"PAR1":
        raise ValueError("Invalid Parquet trailer or file size")
    length = struct.unpack("<I", tail[:4])[0]
    if not 0 < length <= MAX_FOOTER_BYTES or length != len(footer) or length > size - 12:
        raise ValueError("Invalid/oversized footer length")
    range_receipt(tail_headers, tail, size - 8, size - 1, size)
    range_receipt(footer_headers, footer, size - 8 - length, size - 9, size)
    data = decode_footer(footer)
    schema = []
    for field in data[2]:
        schema.append({"name": text(field[4]), "physical_type": TYPES.get(field.get(1), "GROUP"),
                       "repetition": {0: "REQUIRED", 1: "OPTIONAL", 2: "REPEATED"}.get(field.get(3)),
                       "children": field.get(5, 0), "converted_type": field.get(6),
                       "logical_type_field_ids": sorted(field.get(10, {}))})
    keyvalues = {text(entry[1]): text(entry[2]) for entry in data.get(5, []) if 2 in entry}
    # Preserve geo metadata/schema information, not raw Arrow schema or row statistics.
    geo = json.loads(keyvalues["geo"]) if "geo" in keyvalues else None
    pandas = json.loads(keyvalues["pandas"]) if "pandas" in keyvalues else None
    pandas_fields = [column["field_name"] for column in pandas["columns"]] if pandas else None
    if pandas_fields is not None and pandas_fields != [column["name"] for column in schema[1:]]:
        raise ValueError("Parquet schema disagrees with redundant pandas metadata")
    groups = []
    for index, group in enumerate(data[4]):
        columns = []
        for chunk in group[1]:
            if 3 not in chunk:
                raise ValueError("Encrypted/external column metadata unsupported")
            column = chunk[3]
            path = ".".join(text(part) for part in column[3])
            stats = column.get(12, {})
            item = {"path": path, "codec_id": column[4], "values": column[5],
                            "compressed_bytes": column[7], "data_page_offset": column[9],
                            "dictionary_page_offset": column.get(11), "null_count": stats.get(3),
                            "has_min_max": (5 in stats and 6 in stats) or (1 in stats and 2 in stats)}
            if path in {"start_date", "end_date"} and 5 in stats and 6 in stats:
                item["source_string_min"] = text(stats[6])
                item["source_string_max"] = text(stats[5])
            columns.append(item)
        groups.append({"ordinal": index, "rows": group[3], "columns": columns})
    names = {field["name"] for field in schema[1:]}
    return {"record_url": "https://zenodo.org/records/18647054", "licence": "CC BY 4.0",
            "publisher_file_bytes": size, "publisher_checksum": info["checksum"],
            "full_file_checksum_verified": False, "metadata_bytes_received": length + 8,
            "footer_sha256": hashlib.sha256(footer).hexdigest(), "schema": schema,
            "global_parquet_rows": data[3], "row_groups": groups, "geoparquet": geo,
            "key_value_metadata_keys": sorted(keyvalues), "created_by": text(data[6]) if 6 in data else None,
            "pandas_schema_crosscheck": pandas_fields,
            "geometry_column_scan_bytes": sum(c["compressed_bytes"] for g in groups for c in g["columns"] if c["path"] == "geometry"),
            "has_explicit_country_state_district_columns": sorted(names & {"country", "state", "district", "country_code"}),
            "has_explicit_latitude_longitude_columns": sorted(names & {"latitude", "longitude", "lat", "lon", "lng"}),
            "karnataka_records": None, "karnataka_coverage_status": "UNKNOWN_REQUIRES_REVIEWED_SPATIAL_ROW_SCAN",
            "event_rows_downloaded": 0, "duplicates_and_ifi_gfd_relationships": "UNKNOWN_NO_EVENT_ROWS_INSPECTED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("record", "tail", "footer", "tail-headers", "footer-headers"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        result = inspect(json.loads(args.record.read_text()), args.tail.read_bytes(), args.footer.read_bytes(),
                         args.tail_headers.read_text(), args.footer_headers.read_text())
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, f"Metadata inspection failed: {error}\n")


if __name__ == "__main__":
    main()
