"""Read a Rive .riv file and rewrite its colour values (design tooling, not runtime).

The .riv format: "RIVE", major and minor version (varuint), file id (varuint),
a table of contents of property keys with their field types (2 bits each), then
a list of objects. Each object is a type key (varuint) followed by
(property key, value) pairs ending in a 0 key. Field types: 0 uint (varuint),
1 string (varuint length + bytes), 2 double (float32 LE), 3 colour (uint32 LE).
Only colour values are changed; every other byte is copied through, and
parsing must consume the file exactly or nothing is written.

Usage: python tools/riv_recolor.py IN.riv OUT.riv '{"0xff313131": "0x00000000"}'
       python tools/riv_recolor.py IN.riv --list
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

# Field type of every core property key, generated from rive-runtime's
# include/rive/generated/core_registry.hpp (MIT, commit 364421d0) because
# older files leave their table of contents empty.
_WIRE = {
    "CoreUintType": 0, "CoreIdType": 0, "CoreIntType": 0, "CoreBoolType": 0,
    "CoreStringType": 1, "CoreBytesType": 1, "CoreDoubleType": 2, "CoreColorType": 3,
}
CORE_TYPES = {
    int(key): _WIRE[kind]
    for key, kind in json.loads(
        (Path(__file__).with_name("riv_field_types.json")).read_text(encoding="utf-8")
    ).items()
}


def _varuint(data: bytes, pos: int) -> tuple[int, int]:
    """Decode an unsigned LEB128 integer at pos."""
    result = shift = 0
    while True:
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def parse(data: bytes) -> tuple[list[tuple[int, int, int, int]], dict[int, int]]:
    """Return colour fields as (object index, type key, property key, offset) and the field-type table."""
    if data[:4] != b"RIVE":
        raise ValueError("not a .riv file")
    pos = 4
    _major, pos = _varuint(data, pos)
    _minor, pos = _varuint(data, pos)
    _file_id, pos = _varuint(data, pos)
    keys = []
    while True:
        key, pos = _varuint(data, pos)
        if key == 0:
            break
        keys.append(key)
    types: dict[int, int] = dict(CORE_TYPES)
    current = 0
    for i, key in enumerate(keys):
        if i % 4 == 0:
            current = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        types[key] = (current >> ((i % 4) * 2)) & 3
    colours = []
    index = 0
    while pos < len(data):
        type_key, pos = _varuint(data, pos)
        while True:
            prop, pos = _varuint(data, pos)
            if prop == 0:
                break
            field = types.get(prop)
            if field is None:
                raise ValueError(f"unknown property {prop} on type {type_key} at byte {pos}")
            if field == 0:
                _, pos = _varuint(data, pos)
            elif field == 1:
                length, pos = _varuint(data, pos)
                pos += length
            elif field == 2:
                pos += 4
            else:
                colours.append((index, type_key, prop, pos))
                pos += 4
        index += 1
    if pos != len(data):
        raise ValueError("parse did not end at the end of the file")
    return colours, types


def main(argv: list[str]) -> int:
    """List or replace colours."""
    data = Path(argv[1]).read_bytes()
    colours, _ = parse(data)
    if argv[2] == "--list":
        for index, type_key, prop, offset in colours:
            value = struct.unpack_from("<I", data, offset)[0]
            print(f"object {index} type {type_key} prop {prop} colour 0x{value:08x}")
        return 0
    mapping = {int(k, 16): int(v, 16) for k, v in json.loads(argv[3]).items()}
    out = bytearray(data)
    changed = 0
    for _i, _t, _p, offset in colours:
        value = struct.unpack_from("<I", data, offset)[0]
        if value in mapping:
            struct.pack_into("<I", out, offset, mapping[value])
            changed += 1
    Path(argv[2]).write_bytes(bytes(out))
    print(f"changed {changed} colour values")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
