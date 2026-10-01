#!/usr/bin/env python3
"""Read-only inventory of Vegas RIFF/SFPD effect-preset packages.

The RIFF, record, component, and Sapphire parameter-table boundaries are
checked before any value is read. Unknown vendor payloads are retained with
their byte range and digest; this program never loads or executes plug-ins.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
from dataclasses import dataclass
from pathlib import Path


class FormatError(ValueError):
    pass


# These are candidate native renderers, not validated preset conversions.
# Retain an explicit null for every source operation without a tested service.
NATIVE_CANDIDATES = {
    "{C8E20570-4059-4EDF-9CAE-EEF966DF3B19}": (
        "kdenlive_pinch_punch",
        "Native inverse-radius mapping is a documented reconstruction of the VEGAS Pinch/Punch warp, not its original DirectX kernel; source interpolation/tangent codes remain undecoded.",
    ),
    "S_BlurMoCurves": ("kdenlive_motion_curve", "Source interpolation and some Sapphire controls are not converted."),
    "S_WarpFishEye": ("kdenlive_fisheye_warp", "The native radial kernel differs from Sapphire's unpublished kernel."),
    "S_Shake": ("kdenlive_shake", "The native seeded oscillation does not establish Sapphire's noise function."),
    "S_WarpTransform": ("kdenlive_axis_stretch", "All source instances animate only Scale X or Scale Y; source interpolation and exact adaptive filtering remain unresolved."),
    "S_WarpCornerPin": ("kdenlive_corner_pin", "The native perspective mapping works, but its nonlinear bulge kernel is a documented reconstruction, not Sapphire's unpublished function."),
    "S_WarpChroma": ("kdenlive_warp_chroma", "The native multi-band warp uses an explicit spectral weighting reconstruction; Sapphire's exact kernel and adaptive Filter are not decoded."),
    "S_DistortChroma": ("kdenlive_distort_chroma", "The native renderer derives a lens from the source image's luminance because this Vegas record does not carry a separate Lens input; its gradient and spectral sampling approximate Sapphire's proprietary kernel."),
    "RSMB": ("kdenlive_motion_vector_blur", "Native CPU block-flow tracking differs from proprietary per-pixel motion estimation."),
    "sonycreativesoftware:linearblur": ("kdenlive_spatial_blur", "Native directional blur uses a documented approximate sample radius and reflected borders."),
    "vegascreativesoftware:linearblur": ("kdenlive_spatial_blur", "Native directional blur uses a documented approximate sample radius and reflected borders."),
    "sonycreativesoftware:radialblur": ("kdenlive_spatial_blur", "Native radial blur uses a documented approximate sample radius and reflected borders."),
    "S_WarpMagnify": ("kdenlive_magnify_warp", "Native lens falloff and sampling approximate Sapphire WarpMagnify's unpublished kernel."),
    "S_WarpBubble2": ("kdenlive_warp_bubble2", "Native seeded bubble displacement fields approximate Sapphire's proprietary overlapping bubble patterns and adaptive sampling."),
    "S_WarpWaves": ("kdenlive_warp_waves", "Native sinusoidal displacement approximates Sapphire's proprietary wave field; phase units and exact interpolation remain unverified."),
    "S_BlurMotion": ("kdenlive_blur_motion", "Native CPU samples the source along the decoded From/To spatial transform path; sampling and exposure weighting are documented reconstructions of Sapphire's proprietary kernel."),
    "S_Swish3D": ("kdenlive_motion_curve", "Per-event translation/scale and synthetic shutter-path blur are reconstructed with the shared native motion renderer. Sapphire's two-input dissolve/compositing and 3D swivel/tilt kernel are not reproduced; all currently inventoried records use zero swivel/tilt/rotation/shear."),
    "sonycreativesoftware:brightnessandcontrast": ("kdenlive_brightness_contrast", "Normalized brightness is added to RGB and contrast is reconstructed as a 1+2x multiplier around the decoded center; VEGAS documents the controls but not this package's serialized slider conversion, so this is an explicitly documented equivalent."),
}

VEGAS_PINCH_PUNCH_ID = "{C8E20570-4059-4EDF-9CAE-EEF966DF3B19}"
OPAQUE_PAYLOAD_SIGNATURES = (b"MBL2",)


def _opaque_payload_signatures(data: bytes, start: int, end: int) -> list[dict]:
    """Record literal magic-byte offsets without interpreting vendor payloads."""
    payload = data[start:end]
    signatures = []
    for signature in OPAQUE_PAYLOAD_SIGNATURES:
        offsets = [match.start() for match in re.finditer(re.escape(signature), payload)]
        if offsets:
            signatures.append({"signature_ascii": signature.decode("ascii"),
                               "relative_offsets": offsets})
    return signatures


def _vegas_pinch_parameters(data: bytes, start: int, end: int) -> tuple[str, list[dict], dict]:
    """Decode the bounded VEGAS Pinch/Punch control and keyframe records.

    The component payload stores a UTF-16 preset label, five IEEE-754 base
    controls, the proportional flag, then 76-byte key records. Key records
    carry a source time, interpolation code, and five doubles (the value plus
    four vendor auxiliary values). Only the value and source time are mapped;
    interpolation and tangent meanings remain unknown.
    """
    size = end - start
    if size < 56 or u32(data, start, end) != 56:
        raise FormatError(f"unsupported VEGAS Pinch/Punch header at 0x{start:x}")
    vendor_guid = data[start + 4 : start + 20]
    if vendor_guid != bytes.fromhex("7005e2c85940df4e9caeeef966df3b19"):
        raise FormatError(f"unexpected VEGAS Pinch/Punch identifier at 0x{start + 4:x}")
    name_size = u32(data, start + 52, end)
    name_start = start + 56
    label = utf16z(data, name_start, name_size, end)
    controls_start = name_start + name_size
    controls_size = 48
    keys_start = controls_start + controls_size
    if keys_start > end or (end - keys_start) % 76:
        raise FormatError(f"invalid VEGAS Pinch/Punch key region at 0x{keys_start:x}")
    amount, center_x, center_y, horizontal, vertical = struct.unpack_from("<5d", data, controls_start)
    proportional = u32(data, controls_start + 40, end)
    if proportional not in (0, 1):
        raise FormatError(f"invalid VEGAS Pinch/Punch proportional flag at 0x{controls_start + 40:x}")
    base_values = (amount, center_x, center_y, horizontal, vertical)
    if not all(math.isfinite(value) for value in base_values):
        raise FormatError(f"non-finite VEGAS Pinch/Punch control at 0x{controls_start:x}")
    key_count = (end - keys_start) // 76
    if key_count < 1 or key_count > 512:
        raise FormatError(f"unsupported VEGAS Pinch/Punch key count {key_count} at 0x{keys_start:x}")
    points = []
    ignored_points = []
    for index in range(key_count):
        point_start = keys_start + index * 76
        if u32(data, point_start, end) != 28 or u32(data, point_start + 24, end) != 48:
            raise FormatError(f"invalid VEGAS Pinch/Punch key record at 0x{point_start:x}")
        # The host serializes key positions as signed 64-bit ticks (not doubles).
        time = struct.unpack_from("<q", data, point_start + 4)[0]
        interpolation_code = u32(data, point_start + 12, end)
        value, tangent_a_x, tangent_a_y, tangent_b_x, tangent_b_y = struct.unpack_from("<5d", data, point_start + 28)
        if not math.isfinite(value):
            raise FormatError(f"non-finite VEGAS Pinch/Punch key at 0x{point_start:x}")
        # The four trailing IEEE-754 slots are vendor tangent/handle metadata;
        # some records use NaN sentinels there. Keep their locations and map
        # non-finite sentinels to null instead of treating them as curve values.
        auxiliary = [number if math.isfinite(number) else None
                     for number in (tangent_a_x, tangent_a_y, tangent_b_x, tangent_b_y)]
        point = {
            "time": time,
            "interpolation_code": interpolation_code,
            "interpolation_name": None,
            "value": value,
            "auxiliary_pair_a": {"first": auxiliary[0], "second": auxiliary[1], "meaning": None},
            "auxiliary_pair_b": {"first": auxiliary[2], "second": auxiliary[3], "meaning": None},
            "offset": point_start,
        }
        if time < 0:
            # Negative sentinel/pre-event keys are retained by the payload
            # hash and provenance below; the event-fit curve starts at the
            # first nonnegative source key.
            ignored_points.append(point)
        else:
            points.append(point)
    if not points:
        raise FormatError(f"VEGAS Pinch/Punch has no nonnegative event keys at 0x{keys_start:x}")
    first, last = points[0]["time"], points[-1]["time"]
    if key_count > 1 and last <= first:
        raise FormatError(f"non-increasing VEGAS Pinch/Punch key times at 0x{keys_start:x}")
    for point in points:
        point["normalized_event_position"] = 0.0 if key_count == 1 else (point["time"] - first) / (last - first)
    animation = {
        "points": points,
        "original_timing_units": "VEGAS signed 64-bit serialized ticks; scale and interpolation meanings unverified",
        "normalization_basis": "this component's first and last key times",
    }

    def parameter(name: str, value: object, offset: int, size: int, animated: dict | None = None) -> dict:
        raw = data[offset : offset + size]
        return {"name": name, "offset": offset, "size": size, "raw_hex": raw.hex(),
                "value": value, "animation": animated, "interpolation": None,
                "decoding_confidence": "structural; control order corroborated by VEGAS Pinch/Punch documentation"}

    parameters = [
        parameter("Amount", amount, controls_start, 8, animation),
        parameter("Center", [center_x, center_y], controls_start + 8, 16),
        parameter("Horizontal", horizontal, controls_start + 24, 8),
        parameter("Vertical", vertical, controls_start + 32, 8),
        parameter("Proportional", proportional, controls_start + 40, 4),
    ]
    provenance = {
        "preset_label": label,
        "control_block_offset": controls_start,
        "keyframes_offset": keys_start,
        "keyframe_count": key_count,
        "ignored_negative_time_points": ignored_points,
        "layout": "UTF-16 preset label; Amount, Center X/Y, Horizontal, Vertical, Proportional; then 76-byte key records",
        "limitations": ["Key interpolation codes and tangent fields are retained but not decoded.",
                        "The native renderer uses linear interpolation between decoded amount values."],
    }
    return label, parameters, provenance


@dataclass(frozen=True)
class Chunk:
    offset: int
    tag: str
    size: int
    kind: str | None
    data_start: int
    end: int


def u32(data: bytes, offset: int, limit: int) -> int:
    if offset < 0 or offset + 4 > limit:
        raise FormatError(f"truncated integer at 0x{offset:x}")
    return struct.unpack_from("<I", data, offset)[0]


def chunks(data: bytes, start: int, end: int) -> list[Chunk]:
    if start < 0 or end > len(data) or start > end:
        raise FormatError("invalid chunk region")
    result: list[Chunk] = []
    pos = start
    while pos < end:
        if pos + 8 > end:
            raise FormatError(f"truncated chunk header at 0x{pos:x}")
        tag_bytes = data[pos : pos + 4]
        if any(c < 32 or c > 126 for c in tag_bytes):
            raise FormatError(f"invalid chunk tag at 0x{pos:x}")
        size = u32(data, pos + 4, end)
        chunk_end = pos + 8 + size
        if chunk_end > end:
            raise FormatError(f"chunk {tag_bytes!r} at 0x{pos:x} exceeds parent")
        tag = tag_bytes.decode("ascii")
        kind = None
        data_start = pos + 8
        if tag in ("RIFF", "LIST"):
            if size < 4:
                raise FormatError(f"container at 0x{pos:x} has no type")
            kind = data[data_start : data_start + 4].decode("ascii", "strict")
            data_start += 4
        result.append(Chunk(pos, tag, size, kind, data_start, chunk_end))
        pad_end = chunk_end + (size & 1)
        if pad_end > end:
            raise FormatError(f"missing alignment byte after 0x{pos:x}")
        pos = pad_end
    return result


def utf16z(data: bytes, start: int, length: int, limit: int) -> str:
    if length < 2 or length & 1 or start < 0 or start + length > limit:
        raise FormatError(f"invalid UTF-16 range at 0x{start:x}")
    raw = data[start : start + length]
    if raw[-2:] != b"\0\0":
        raise FormatError(f"unterminated UTF-16 string at 0x{start:x}")
    return raw[:-2].decode("utf-16le", "strict")


def _parameter_table(data: bytes, start: int, end: int) -> tuple[int, list[dict]] | None:
    """Find a Sapphire table only when its entries consume the payload exactly."""
    candidates = []
    for offset in range(start, end - 7):
        table_size = u32(data, offset, end)
        count = u32(data, offset + 4, end)
        if count == 0 or count > 512 or offset + 8 + table_size != end:
            continue
        pos = offset + 8
        params = []
        try:
            for _ in range(count):
                value_size = u32(data, pos, end)
                name_size = u32(data, pos + 4, end)
                pos += 8
                if name_size < 4 or name_size > 512 or name_size & 1 or value_size > end - pos - name_size:
                    raise FormatError("invalid parameter length")
                name = utf16z(data, pos, name_size, end)
                if not name or any(ord(char) < 32 for char in name):
                    raise FormatError("invalid parameter name")
                pos += name_size
                params.append(_parameter(data, name, pos, value_size))
                pos += value_size
            if pos == end:
                candidates.append((offset, params))
        except (FormatError, UnicodeError):
            pass
    if len(candidates) > 1:
        raise FormatError(f"ambiguous parameter table at 0x{start:x}")
    return candidates[0] if candidates else None


def _parameter(data: bytes, name: str, offset: int, size: int) -> dict:
    raw = data[offset : offset + size]
    item = {"name": name, "offset": offset, "size": size, "raw_hex": raw.hex(),
            "value": None, "animation": None, "interpolation": None,
            "decoding_confidence": "unknown"}
    if size == 8:
        first, second = struct.unpack("<II", raw)
        item.update(value=first, auxiliary=second, decoding_confidence="structural")
    elif size in (12, 20, 28):
        dimensions = (size - 4) // 8
        values = struct.unpack_from("<" + "d" * dimensions, raw)
        if all(math.isfinite(value) for value in values):
            item.update(value=values[0] if dimensions == 1 else list(values),
                        auxiliary=struct.unpack_from("<I", raw, size - 4)[0],
                        decoding_confidence="structural")
    elif size >= 64 and (size - 12) % 52 == 0:
        count = struct.unpack_from("<I", raw, 8)[0]
        if count == (size - 12) // 52:
            points = []
            for index in range(count):
                point_offset = 12 + index * 52
                time = struct.unpack_from("<d", raw, point_offset)[0]
                interpolation_code = struct.unpack_from("<I", raw, point_offset + 8)[0]
                values = struct.unpack_from("<ddddd", raw, point_offset + 12)
                points.append({"time": time, "interpolation_code": interpolation_code,
                               "interpolation_name": None, "value": values[0],
                               "auxiliary_pair_a": {"first": values[1], "second": values[2], "meaning": None},
                               "auxiliary_pair_b": {"first": values[3], "second": values[4], "meaning": None},
                               "offset": offset + point_offset})
            value = struct.unpack_from("<d", raw)[0]
            if math.isfinite(value) and all(math.isfinite(number) for point in points for number in
                                             (point["time"], point["value"], point["auxiliary_pair_a"]["first"],
                                              point["auxiliary_pair_a"]["second"], point["auxiliary_pair_b"]["first"],
                                              point["auxiliary_pair_b"]["second"])):
                item.update(value=value,
                            animation={"points": points, "original_timing_units": "source keyframe positions; frame interpretation unverified"},
                            decoding_confidence="structural")
    return item


def _component(data: bytes, offset: int, end: int) -> tuple[dict, int]:
    if offset + 20 > end:
        raise FormatError(f"truncated component at 0x{offset:x}")
    instance_id = data[offset : offset + 16].hex()
    id_size = u32(data, offset + 16, end)
    if id_size < 4 or id_size > 1024:
        raise FormatError(f"invalid component identifier length at 0x{offset:x}")
    vendor_id = utf16z(data, offset + 20, id_size, end)
    length_pos = offset + 20 + id_size
    payload_size = u32(data, length_pos, end)
    payload_start = length_pos + 4
    payload_end = payload_start + payload_size
    if payload_end > end:
        raise FormatError(f"component {vendor_id} exceeds record")
    table = _parameter_table(data, payload_start, payload_end)
    vendor_preset = None
    custom_parameters = None
    custom_decode = None
    if vendor_id == VEGAS_PINCH_PUNCH_ID:
        vendor_preset, custom_parameters, custom_decode = _vegas_pinch_parameters(data, payload_start, payload_end)
    edge_modes = {}
    decoded_parameters = table[1] if table else custom_parameters
    for parameter in decoded_parameters or []:
        if parameter["name"] in ("Wrap X", "Wrap Y"):
            value = parameter["value"]
            # The numeric 2 -> Reflect mapping is corroborated by the
            # supplied Slide Right settings; 0 is the documented No mode.
            edge_modes[parameter["name"]] = {"code": value, "mode": {0: "No", 2: "Reflect"}.get(value)}
    short_id = vendor_id.removesuffix("}").rsplit(".", 1)[-1]
    candidate = NATIVE_CANDIDATES.get(vendor_id) or NATIVE_CANDIDATES.get(short_id)
    opaque_signatures = []
    if not candidate and not table and custom_parameters is None:
        opaque_signatures = _opaque_payload_signatures(data, payload_start, payload_end)
    component = {
        "vendor_id": vendor_id,
        "instance_id_hex": instance_id,
        "offset": offset,
        "payload_offset": payload_start,
        "payload_size": payload_size,
        "payload_sha256": hashlib.sha256(data[payload_start:payload_end]).hexdigest(),
        "parameter_table_offset": table[0] if table else None,
        "parameters": table[1] if table else custom_parameters,
        "edge_modes": edge_modes,
        "unparsed_prefix_hex": data[payload_start:table[0]].hex() if table else None,
        "vendor_preset": custom_decode,
        "opaque_payload_signatures": opaque_signatures,
        "decoding_confidence": "partial" if table or custom_parameters else "unknown",
        "native_component": ({"service": candidate[0], "mapping_status": "candidate; source preset remains Pending",
                              "known_difference_or_gap": candidate[1]} if candidate else None),
    }
    return component, payload_end


def _record(data: bytes, record: Chunk, index: int, package: str, package_hash: str) -> dict:
    children = chunks(data, record.data_start, record.end)
    if record.tag != "LIST" or record.kind != "chn " or len(children) != 1 or children[0].tag != "chnh":
        raise FormatError(f"unsupported preset record at 0x{record.offset:x}")
    body = children[0]
    start = body.data_start
    if body.end - start < 624:
        raise FormatError(f"short preset record at 0x{start:x}")
    header_words = struct.unpack_from("<III", data, start)
    if header_words != (0, 2, 5):
        raise FormatError(f"unsupported preset header {header_words} at 0x{start:x}")
    name_block = data[start + 12 : start + 524]
    name_end = next((i for i in range(0, len(name_block), 2) if name_block[i : i + 2] == b"\0\0"), -1)
    if name_end < 0:
        raise FormatError(f"unterminated preset name at 0x{start:x}")
    name = utf16z(data, start + 12, name_end + 2, start + 524)
    source_id = utf16z(data, start + 532, 78, start + 612)
    blob_offset = start + 612
    blob_size = u32(data, blob_offset, body.end)
    if blob_offset + 4 + blob_size != body.end:
        raise FormatError(f"preset payload size mismatch at 0x{blob_offset:x}")
    version = u32(data, blob_offset + 4, body.end)
    component_count = u32(data, blob_offset + 8, body.end)
    if version != 1 or component_count > 128:
        raise FormatError(f"unsupported component header at 0x{blob_offset:x}")
    pos = blob_offset + 12
    components = []
    for _ in range(component_count):
        component, pos = _component(data, pos, body.end)
        components.append(component)
    if pos + 8 != body.end:
        raise FormatError(f"record trailer mismatch at 0x{pos:x}")
    duration_match = re.search(r"(?<!\d)(\d+)k$", name)
    role_match = re.search(r"\(([12])\)(?:\s+\d+k)?$", name)
    direction_match = re.search(r"\b(Left|Right|Up|Down|L to R|R to L)\b", name, re.IGNORECASE)
    role = {"1": "outgoing", "2": "incoming"}.get(role_match.group(1)) if role_match else None
    source_times = [point["time"] for component in components if component["vendor_id"] != VEGAS_PINCH_PUNCH_ID
                    for parameter in (component["parameters"] or [])
                    if parameter["animation"] for point in parameter["animation"]["points"]]
    timing = None
    if source_times:
        first, last = min(source_times), max(source_times)
        if last > first:
            timing = {"first_source_position": first, "last_source_position": last,
                      "formula": "(source_position - first_source_position) / (last_source_position - first_source_position)",
                      "displayed_frame_formula": "normalized_event_position * (event_frame_count - 1)",
                      "note": "Source position unit and interpolation code meanings are unverified; positions are not rounded."}
            for component in components:
                if component["vendor_id"] == VEGAS_PINCH_PUNCH_ID:
                    continue
                for parameter in component["parameters"] or []:
                    if parameter["animation"]:
                        for point in parameter["animation"]["points"]:
                            point["normalized_event_position"] = (point["time"] - first) / (last - first)
    return {
        "package": package, "package_sha256": package_hash,
        "record_index": index, "record_offset": record.offset,
        "source_identifier": source_id, "exact_name": name,
        "nominal_frames": int(duration_match.group(1)) if duration_match else None,
        "direction": direction_match.group(1) if direction_match else None,
        "event_variant": role,
        # Transition package entries carry the (1)/(2) event role in their
        # labels. The companion Other.sfpreset contains reusable looks and
        # effects: they have neither that role nor the transition's nominal
        # duration suffix. Keep these in the inventory without inventing
        # event timing or exposing them as incomplete transition presets.
        "scope": ("transition" if role else
                  "standalone_effect" if not duration_match else "undetermined"),
        "scope_basis": ("numbered event variant in preset name" if role else
                        "no event variant or nominal duration in preset name" if not duration_match else
                        "nominal duration present; event role unresolved"),
        "components": components, "original_timing_units": "unknown; numeric key positions retained",
        "normalized_event_time_conversion": timing,
        "native_component_mapping": [component["native_component"] for component in components],
        "decoding_confidence": "partial" if all(c["parameters"] is not None for c in components) else "unknown",
        "status": "Pending", "implementation_limitations": ["Source animation timing and interpolation are not fully decoded."],
        "validation_evidence": [],
        "trailer_hex": data[pos:body.end].hex(),
    }


def parse_package(path: Path) -> dict:
    data = path.read_bytes()
    package_hash = hashlib.sha256(data).hexdigest()
    root_chunks = chunks(data, 0, len(data))
    if len(root_chunks) != 1 or root_chunks[0].tag != "RIFF" or root_chunks[0].kind != "SFPD":
        raise FormatError("expected one RIFF/SFPD root")
    root = root_chunks[0]
    top = chunks(data, root.data_start, root.end)
    if len(top) != 2 or top[0].tag != "fmt " or top[1].tag != "LIST" or top[1].kind != "clst":
        raise FormatError("expected fmt and clst chunks")
    fmt = top[0]
    if fmt.size != 16:
        raise FormatError("unsupported SFPD fmt size")
    format_words = struct.unpack_from("<HHIII", data, fmt.data_start)
    records = chunks(data, top[1].data_start, top[1].end)
    if format_words[3] != len(records):
        raise FormatError(f"fmt record count {format_words[3]} differs from {len(records)}")
    return {
        "package": path.name, "sha256": package_hash, "size_bytes": len(data),
        "format_words": list(format_words), "record_count": len(records),
        "records": [_record(data, chunk, index, path.name, package_hash) for index, chunk in enumerate(records)],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    packages = [parse_package(path) for path in args.packages]
    inventory = {"schema_version": 1, "source": "read-only RIFF/SFPD structural parse",
                 "record_count": sum(package["record_count"] for package in packages),
                 "packages": packages}
    output = json.dumps(inventory, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
