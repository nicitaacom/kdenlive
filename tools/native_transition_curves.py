#!/usr/bin/env python3
"""Build deterministic, monotone native curve handles for preset reconstruction.

The source packages retain interpolation codes and auxiliary control points,
but their proprietary meanings are not established. This helper is an explicit
native equivalent: it preserves every decoded normalized key time and value,
then connects them with a monotone cubic curve that eases to zero velocity at
the first and last keys. It must not be described as decoding the source curve.
"""

from __future__ import annotations

import math
from bisect import bisect_right


def monotone_bezier_points(points: list[list[float]]) -> list[list[float]]:
    """Return seven-field native Bezier keys without moving source keys.

    Each input point has ``[time, value, in_time, in_value, out_time,
    out_value, interpolation]``. Only ``time`` and ``value`` are retained;
    handles are generated from the shape-preserving Fritsch-Carlson tangent
    rule. Flat segments stay flat, extrema do not overshoot, and both ends
    ease to/from rest.
    """
    if not points:
        return []

    keys = [(float(point[0]), float(point[1])) for point in points]
    if any(not math.isfinite(t) or not math.isfinite(v) for t, v in keys):
        raise ValueError("curve times and values must be finite")
    if any(keys[i + 1][0] <= keys[i][0] for i in range(len(keys) - 1)):
        raise ValueError("curve key times must be strictly increasing")
    if len(keys) == 1:
        time, value = keys[0]
        return [[time, value, time, value, time, value, 0]]

    times = [item[0] for item in keys]
    values = [item[1] for item in keys]
    intervals = [times[i + 1] - times[i] for i in range(len(keys) - 1)]
    secants = [(values[i + 1] - values[i]) / intervals[i]
               for i in range(len(keys) - 1)]

    # Flat endpoints make the fitted path settle cleanly. Interior weighted
    # harmonic means keep monotone sections monotone and set turning points to
    # rest rather than creating cubic overshoot.
    tangents = [0.0] * len(keys)
    for index in range(1, len(keys) - 1):
        left = secants[index - 1]
        right = secants[index]
        if left == 0 or right == 0 or left * right < 0:
            continue
        before = intervals[index - 1]
        after = intervals[index]
        w1 = 2 * after + before
        w2 = after + 2 * before
        tangents[index] = (w1 + w2) / (w1 / left + w2 / right)

    result: list[list[float]] = []
    for index, (time, value) in enumerate(keys):
        if index == 0:
            in_time, in_value = time, value
        else:
            interval = intervals[index - 1]
            in_time = time - interval / 3
            in_value = value - tangents[index] * interval / 3

        if index == len(keys) - 1:
            out_time, out_value = time, value
            interpolation = 0
        else:
            interval = intervals[index]
            out_time = time + interval / 3
            out_value = value + tangents[index] * interval / 3
            interpolation = 1

        result.append([time, value, in_time, in_value,
                       out_time, out_value, interpolation])
    return result


def cubic_ease_out_endpoint_points(start: float, end: float) -> list[list[float]]:
    """Return a normalized cubic ease-out from the source start to end values.

    This keeps the initial velocity and settles to zero at the last frame. It
    is an explicit native timing profile for visually confirmed recovery, not
    an interpretation of proprietary interpolation metadata.
    """
    if not math.isfinite(start) or not math.isfinite(end):
        raise ValueError("ease-out endpoints must be finite")
    delta = end - start
    return [
        [0.0, start, 0.0, start, 1.0 / 3.0, start + delta, 1],
        [1.0, end, 2.0 / 3.0, end, 1.0, end, 0],
    ]


def reverse_event_time_monotone_candidate(points: list[dict]) -> list[list[float]]:
    """Reverse a full-event source curve and fit a monotone cubic candidate.

    This is a role-timing hypothesis for source variants whose decoded curve
    starts displaced and ends neutral while the record is explicitly outgoing.
    It preserves every decoded value, reverses their event-time order, and
    replaces unknown source interpolation with native monotone Bezier handles.
    It is not a generic rule for outgoing records and must stay opt-in per row.
    """
    if not points:
        return []
    keys = [(float(point["normalized_event_position"]), float(point["value"]))
            for point in points]
    if any(not math.isfinite(time) or not math.isfinite(value) for time, value in keys):
        raise ValueError("source curve times and values must be finite")
    if any(keys[index + 1][0] <= keys[index][0] for index in range(len(keys) - 1)):
        raise ValueError("source curve times must be strictly increasing")
    if abs(keys[0][0]) > 1e-9 or abs(keys[-1][0] - 1.0) > 1e-9:
        raise ValueError("role-time reversal requires keys at both event endpoints")
    reversed_points = [[1.0 - time, value, 0.0, value, 0.0, value, 0]
                       for time, value in reversed(keys)]
    reversed_points[0][0] = 0.0
    reversed_points[-1][0] = 1.0
    return monotone_bezier_points(reversed_points)


def incoming_full_event_recovery_points(points: list[list[float]],
                                        ease_weight: float = 0.5) -> list[list[float]]:
    """Spread an incoming source curve's remaining recovery over the full event.

    Source key values and their order are retained. If the final decoded key
    occurs before the event endpoint, all key times are proportionally fitted
    so that final value lands at normalized time 1. Each segment is converted
    to an explicit native Bezier with a linear velocity floor blended with
    smoothstep easing. This avoids an early neutral hold while keeping every
    sampled frame moving. It is an explicit native timing reconstruction, not
    a claim about proprietary source interpolation.
    """
    if not points:
        return []
    if not math.isfinite(ease_weight) or not 0.0 <= ease_weight < 1.0:
        raise ValueError("ease weight must be finite and in [0, 1)")
    keys = [(float(point[0]), float(point[1])) for point in points]
    if any(not math.isfinite(time) or not math.isfinite(value) for time, value in keys):
        raise ValueError("curve times and values must be finite")
    if any(keys[index + 1][0] <= keys[index][0] for index in range(len(keys) - 1)):
        raise ValueError("curve key times must be strictly increasing")
    first_time, last_time = keys[0][0], keys[-1][0]
    if abs(first_time) > 1e-8 or last_time <= 0.0 or last_time > 1.0 + 1e-8:
        raise ValueError("incoming recovery curve must start at zero and end in (0, 1]")
    if len(keys) == 1:
        time, value = keys[0]
        return [[time, value, time, value, time, value, 0]]

    # Retiming all keys as a group preserves their relative progression and
    # places the last decoded value on the last displayed event frame.
    fitted = [(time / last_time, value) for time, value in keys]
    fitted[0] = (0.0, fitted[0][1])
    fitted[-1] = (1.0, fitted[-1][1])
    linear_floor = 1.0 - ease_weight
    result: list[list[float]] = []
    for index, (time, value) in enumerate(fitted):
        if index == 0:
            in_time, in_value = time, value
        else:
            previous_time, previous_value = fitted[index - 1]
            interval = time - previous_time
            delta = value - previous_value
            in_time = time - interval / 3.0
            in_value = value - delta * linear_floor / 3.0

        if index == len(fitted) - 1:
            out_time, out_value, interpolation = time, value, 0
        else:
            next_time, next_value = fitted[index + 1]
            interval = next_time - time
            delta = next_value - value
            out_time = time + interval / 3.0
            out_value = value + delta * linear_floor / 3.0
            interpolation = 1
        result.append([time, value, in_time, in_value, out_time, out_value, interpolation])
    return result


def apply_scroll_right_27_incoming_recovery_v1(tree, record: dict | None = None) -> None:
    """Retiming candidate scoped to source record 2.7 Scroll Right (2) 20k."""
    import json

    expected_id = "{CEFDEE77-588E-4932-9CBD-5D707852264A}"
    if record is not None and (record.get("source_identifier") != expected_id
                               or record.get("event_variant") != "incoming"):
        raise ValueError("Scroll Right incoming recovery policy is scoped to its source UUID")
    root = tree.getroot()
    filters = root.findall(".//producer/filter")
    updated = 0
    motion_found = False
    for element in filters:
        service = element.find("property[@name='mlt_service']")
        if service is None:
            continue
        curves_node = element.find("property[@name='native_curves']")
        if curves_node is None or not curves_node.text:
            continue
        role = element.find("property[@name='native_event_role']")
        if role is None or role.text != "incoming":
            raise ValueError("Scroll Right incoming recovery cannot modify an outgoing effect filter")
        curves = json.loads(curves_node.text)
        if service.text == "kdenlive_motion_curve":
            if not {"shift_x", "z_distance"}.issubset(curves):
                raise ValueError("Scroll Right incoming transform curves changed unexpectedly")
            shutter = element.find("property[@name='shutter_duration']")
            if shutter is None or shutter.text is None:
                raise ValueError("Scroll Right incoming motion filter has no shutter-duration setting")
            source_shutter = float(shutter.text)
            if not math.isfinite(source_shutter) or source_shutter < 0.0:
                raise ValueError("Scroll Right incoming shutter duration is invalid")
            curves["shutter_duration"] = incoming_full_event_recovery_points(
                [[0.0, source_shutter, 0.0, source_shutter, 0.0, source_shutter, 0],
                 [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0]], ease_weight=0.5)
            motion_found = True
        for name, points in curves.items():
            curves[name] = incoming_full_event_recovery_points(points, ease_weight=0.5)
            updated += 1
        curves_node.text = json.dumps(curves, separators=(",", ":"))
    if updated == 0 or not motion_found:
        raise ValueError("Scroll Right incoming fixture has no complete native effect curves")


def apply_scroll_down_34_incoming_recovery_v1(tree, record: dict | None = None) -> None:
    """Fit the incoming 3.4 Scroll Down recovery, including native-only settling.

    The decoded Shift Y curve reaches zero at 60% and then holds, while the
    decoded Sapphire Shake amplitude is static. Preserve all decoded curve
    values and their order, retime their keys across the whole event, and add
    an explicit amplitude/shutter taper so the last frame returns to the
    untreated incoming source. The taper is a documented native fit, not a
    decoded Sapphire animation.
    """
    import json

    expected_id = "{95BA992E-E4B3-43A3-B4B9-872F2CD9D135}"
    if record is not None and (record.get("source_identifier") != expected_id
                               or record.get("event_variant") != "incoming"):
        raise ValueError("Scroll Down incoming recovery policy is scoped to its source UUID")
    root = tree.getroot()
    filters = root.findall(".//producer/filter")
    updated = 0
    motion_found = False
    shake_found = False
    for element in filters:
        service = element.find("property[@name='mlt_service']")
        curves_node = element.find("property[@name='native_curves']")
        if service is None or curves_node is None or not curves_node.text:
            continue
        role = element.find("property[@name='native_event_role']")
        if role is None or role.text != "incoming":
            raise ValueError("Scroll Down incoming recovery cannot modify an outgoing effect filter")
        curves = json.loads(curves_node.text)
        if service.text == "kdenlive_motion_curve":
            if not {"shift_y", "z_distance"}.issubset(curves):
                raise ValueError("Scroll Down incoming transform curves changed unexpectedly")
            shutter = element.find("property[@name='shutter_duration']")
            if shutter is None or shutter.text is None:
                raise ValueError("Scroll Down incoming motion filter has no shutter-duration setting")
            source_shutter = float(shutter.text)
            if not math.isfinite(source_shutter) or source_shutter < 0.0:
                raise ValueError("Scroll Down incoming shutter duration is invalid")
            curves["shutter_duration"] = incoming_full_event_recovery_points(
                [[0.0, source_shutter, 0.0, source_shutter, 0.0, source_shutter, 0],
                 [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0]], ease_weight=0.5)
            motion_found = True
        elif service.text == "kdenlive_shake":
            amplitude = curves.get("amplitude")
            if not amplitude or len(amplitude) != 1 or abs(float(amplitude[0][0])) > 1e-8:
                raise ValueError("Scroll Down incoming static shake amplitude changed unexpectedly")
            source_amplitude = float(amplitude[0][1])
            if not math.isfinite(source_amplitude) or source_amplitude < 0.0:
                raise ValueError("Scroll Down incoming shake amplitude is invalid")
            curves["amplitude"] = incoming_full_event_recovery_points(
                [[0.0, source_amplitude, 0.0, source_amplitude, 0.0, source_amplitude, 0],
                 [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0]], ease_weight=0.5)
            shake_found = True
        for name, points in curves.items():
            if name in ("shutter_duration", "amplitude") and len(points) == 2 and points[-1][1] == 0.0:
                # The inserted native taper already uses the full normalized event.
                continue
            curves[name] = incoming_full_event_recovery_points(points, ease_weight=0.5)
            updated += 1
        curves_node.text = json.dumps(curves, separators=(",", ":"))
    if updated == 0 or not motion_found or not shake_found:
        raise ValueError("Scroll Down incoming fixture has no complete motion and shake curves")


def apply_scroll_left_14_incoming_recovery_v1(tree, record: dict | None = None) -> None:
    """Fit the 1.4 incoming scroll, shake, and fisheye curves to the event.

    This row's decoded Shift X curve reaches zero at 60% then holds. The native
    reconstruction spreads that remaining motion across the event and tapers
    the decoded static motion shutter to zero at the final displayed frame.
    Animated shake amplitude and fisheye values retain their decoded key
    values/order. Unknown source interpolation is represented with the same
    per-segment 50% linear-floor/smoothstep native Bezier fit.
    """
    _apply_scroll_family_incoming_recovery(
        tree, record, "{286C285F-FCFD-4B86-BD12-398F6E99BC63}", "shift_x",
        "Scroll Left 1.4 incoming")


def apply_scroll_left_14_outgoing_shift_fit_v1(tree, record: dict | None = None) -> None:
    """Fit 1.4 outgoing keys to their screen-space motion over the event.

    The source Shift X keys occupy only normalized time .4..1.0. A shared
    pixel-weighted path map removes the idle source-time interval, while
    retaining the decoded values and a sparse, editable set of keyframes.
    The source Shift X start key becomes an early, subtle event value; the
    large late translation and its associated blur remain at the cut. This is
    an explicit native timing fit, not a claim about Sapphire interpolation.
    """
    import json

    expected_id = "{A3C456BE-54DE-4FC4-AB4C-8CFD7AA28A72}"
    if record is not None and (record.get("source_identifier") != expected_id
                               or record.get("event_variant") != "outgoing"):
        raise ValueError("Scroll Left outgoing fit is scoped to its source UUID")
    root = tree.getroot()
    producers = [root] if root.tag == "producer" else root.findall(".//producer")
    updated = 0
    for producer in producers:
        filters = producer.findall("filter")
        role = next((item.findtext("property[@name='native_event_role']") for item in filters
                     if item.findtext("property[@name='mlt_service']") == "kdenlive_motion_curve"), None)
        if role is None:
            continue
        if role != "outgoing":
            raise ValueError("Scroll Left outgoing fit cannot modify an incoming filter")
        curves_by_filter = []
        curve_nodes = []
        for element in filters:
            curves_node = element.find("property[@name='native_curves']")
            curves = json.loads(curves_node.text) if curves_node is not None and curves_node.text else {}
            curves_by_filter.append(curves)
            curve_nodes.append(curves_node)
        source_map = screen_space_arc_length_time_map(curves_by_filter, 640, 360, 121)

        def event_time(source_time: float) -> float:
            source_time = min(1.0, max(0.0, float(source_time)))
            if source_time <= source_map[0]:
                return 0.0
            for index in range(1, len(source_map)):
                right = source_map[index]
                if right >= source_time:
                    left = source_map[index - 1]
                    if right <= left + 1e-12:
                        return index / (len(source_map) - 1)
                    fraction = (source_time - left) / (right - left)
                    return (index - 1 + fraction) / (len(source_map) - 1)
            return 1.0

        producer_updated = False
        for element, curves, curves_node in zip(filters, curves_by_filter, curve_nodes):
            if not curves or curves_node is None:
                continue
            if element.findtext("property[@name='mlt_service']") == "kdenlive_motion_curve":
                points = curves.get("shift_x")
                if not points or len(points) < 2:
                    raise ValueError("Scroll Left outgoing Shift X must have at least two decoded keys")
                if abs(float(points[0][0]) - 0.4) > 1e-5 or abs(float(points[-1][0]) - 1.0) > 1e-5:
                    raise ValueError("Scroll Left outgoing Shift X source key range changed unexpectedly")
            retimed = {}
            for name, points in curves.items():
                fitted = []
                for point in points:
                    if len(point) != 7:
                        raise ValueError("native curve keys must contain seven fields")
                    mapped = list(point)
                    for time_index in (0, 2, 4):
                        mapped[time_index] = event_time(point[time_index])
                    if fitted and mapped[0] <= fitted[-1][0]:
                        mapped[0] = fitted[-1][0] + 1e-7
                        mapped[2] = max(mapped[2], mapped[0])
                        mapped[4] = max(mapped[4], mapped[0])
                    fitted.append(mapped)
                retimed[name] = fitted
            if element.findtext("property[@name='mlt_service']") == "kdenlive_motion_curve":
                shift = retimed["shift_x"]
                if shift[0][0] <= 0.0 or shift[-1][0] != 1.0:
                    raise ValueError("screen-space fit did not preserve the full outgoing Shift X interval")
                producer_updated = True
            curves_node.text = json.dumps(retimed, separators=(",", ":"))
        if producer_updated:
            updated += 1
    if updated != 1:
        raise ValueError(f"Scroll Left outgoing fit expected one event producer, got {updated}")


def _apply_scroll_family_incoming_recovery(tree, record: dict | None,
                                           expected_id: str, required_motion_curve: str | set[str],
                                           label: str) -> None:
    import json

    if record is not None and (record.get("source_identifier") != expected_id
                               or record.get("event_variant") != "incoming"):
        raise ValueError(f"{label} recovery policy is scoped to its source UUID")
    filters = tree.getroot().findall(".//producer/filter")
    updated = 0
    motion_found = False
    for element in filters:
        service = element.find("property[@name='mlt_service']")
        curves_node = element.find("property[@name='native_curves']")
        if service is None or curves_node is None or not curves_node.text:
            continue
        role = element.find("property[@name='native_event_role']")
        if role is None or role.text != "incoming":
            raise ValueError(f"{label} recovery cannot modify an outgoing effect filter")
        curves = json.loads(curves_node.text)
        inserted_curves = set()
        if service.text == "kdenlive_motion_curve":
            required = ({required_motion_curve} if isinstance(required_motion_curve, str)
                        else required_motion_curve)
            if not required.issubset(curves):
                raise ValueError(f"{label} transform no longer contains {sorted(required)}")
            shutter = element.find("property[@name='shutter_duration']")
            if shutter is None or shutter.text is None:
                raise ValueError(f"{label} motion filter has no shutter-duration setting")
            source_shutter = float(shutter.text)
            if not math.isfinite(source_shutter) or source_shutter < 0.0:
                raise ValueError(f"{label} shutter duration is invalid")
            curves["shutter_duration"] = incoming_full_event_recovery_points(
                [[0.0, source_shutter, 0.0, source_shutter, 0.0, source_shutter, 0],
                 [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0]], ease_weight=0.5)
            inserted_curves.add("shutter_duration")
            motion_found = True
        if service.text == "kdenlive_shake":
            amplitude = curves.get("amplitude")
            if amplitude and len(amplitude) == 1:
                source_amplitude = float(amplitude[0][1])
                if not math.isfinite(source_amplitude) or source_amplitude < 0.0:
                    raise ValueError(f"{label} static shake amplitude is invalid")
                curves["amplitude"] = incoming_full_event_recovery_points(
                    [[0.0, source_amplitude, 0.0, source_amplitude, 0.0, source_amplitude, 0],
                     [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0]], ease_weight=0.5)
                inserted_curves.add("amplitude")
        for name, points in curves.items():
            if name in inserted_curves:
                continue
            curves[name] = incoming_full_event_recovery_points(points, ease_weight=0.5)
            updated += 1
        curves_node.text = json.dumps(curves, separators=(",", ":"))
    if updated == 0 or not motion_found:
        raise ValueError(f"{label} fixture has no complete incoming motion curves")


SCROLL_FAMILY_INCOMING_RECOVERY_AXES = {
    "{7B7CC980-5669-44C9-A142-CE84AFA06957}": {"shift_x"},
    "{C7810381-0CC1-4888-BFD9-14428DDA5083}": {"shift_x"},
    "{12F189CB-AACF-47F1-9554-82886B4948D3}": {"shift_y"},
    "{49DF4B2D-390F-42DE-A52D-112AEF706028}": {"shift_x", "shift_y"},
    "{44907BDF-F91F-44F9-AE30-916C2E56D2F8}": {"shift_x", "shift_y"},
}


def apply_scroll_family_incoming_recovery_v1(tree, record: dict | None = None) -> None:
    """Apply event-wide recovery to the explicitly enumerated scroll records.

    The UUID-to-axis list is deliberately explicit. This candidate preserves
    each record's decoded values and key order, retimes early-ending tracks to
    the full event, and fades static shutter and shake settings to zero at the
    final incoming frame. It must not be applied to unlisted presets by name
    matching alone.
    """
    if record is None:
        raise ValueError("scroll family recovery requires the exact source record")
    source_id = record.get("source_identifier")
    axes = SCROLL_FAMILY_INCOMING_RECOVERY_AXES.get(source_id)
    if axes is None:
        raise ValueError("scroll family incoming recovery is not enabled for this source UUID")
    _apply_scroll_family_incoming_recovery(
        tree, record, source_id, axes, record.get("exact_name", "incoming scroll"))


def vegas_enum_order_candidate(points: list[dict]) -> list[list[float]]:
    """Translate a *candidate* VEGAS enum-order mapping to native curves.

    The source binary codes 0–5 match the order of ``VideoKeyframeType`` in
    MAGIX's public API summary. The docs list names and behavior but not the
    serialized integer values, so this mapping remains an inference. It also
    ignores the package's still-opaque auxiliary tangent pairs.

    Candidate mapping: 0 linear, 1 hold, 2 slow/ease-in, 3 fast/ease-out,
    4 smooth/ease-in-out. Sharp (5) is rejected until its numeric shape is
    established. The returned seven-field keys use Kdenlive's own codes:
    0 linear, 1 explicit Bezier, and 2 hold.
    """
    if not points:
        return []
    keys = [(float(point["normalized_event_position"]), float(point["value"]),
             int(point["interpolation_code"])) for point in points]
    if any(not math.isfinite(t) or not math.isfinite(v) for t, v, _ in keys):
        raise ValueError("source curve times and values must be finite")
    if any(keys[i + 1][0] <= keys[i][0] for i in range(len(keys) - 1)):
        raise ValueError("source curve times must be strictly increasing")
    if any(code not in range(5) for _, _, code in keys[:-1]):
        raise ValueError("source Sharp/unknown interpolation is not implemented")

    result = [[time, value, time, value, time, value, 0] for time, value, _ in keys]
    for index, (time, value, code) in enumerate(keys[:-1]):
        next_time, next_value, _ = keys[index + 1]
        delta_time = next_time - time
        delta_value = next_value - value
        if code == 0:
            result[index][6] = 0
        elif code == 1:
            result[index][6] = 2
        else:
            result[index][6] = 1
            result[index][4] = time + delta_time / 3
            result[index + 1][2] = next_time - delta_time / 3
            if code == 2:  # Slow: acceleration from rest (t^2)
                result[index][5] = value
                result[index + 1][3] = next_value - delta_value / 3
            elif code == 3:  # Fast: deceleration to rest (2t - t^2)
                result[index][5] = value + 2 * delta_value / 3
                result[index + 1][3] = next_value
            else:  # Smooth: symmetric ease (3t^2 - 2t^3)
                result[index][5] = value
                result[index + 1][3] = next_value
    return result


def vegas_zero_hold_candidate(points: list[dict]) -> list[list[float]]:
    """Test a second serializer hypothesis: zero=Hold, one=Linear.

    Codes 2–5 then match the documented Slow/Fast/Smooth/Sharp order. This is
    not an established source mapping; it is kept separate so renders can be
    compared without silently selecting either interpretation.
    """
    remapped = []
    for point in points:
        clone = dict(point)
        code = int(point["interpolation_code"])
        clone["interpolation_code"] = {0: 1, 1: 0}.get(code, code)
        remapped.append(clone)
    return vegas_enum_order_candidate(remapped)


def vegas_zero_hold_incoming_key_candidate(points: list[dict]) -> list[list[float]]:
    """Test the zero-hold mapping with interpolation stored on the destination key.

    Some keyframe formats associate a key's interpolation type with the
    segment ending at that key. The package does not establish whether its
    code is incoming- or outgoing-key based, so this is a disposable-render
    candidate, not a production conversion. It shares the zero=Hold, one=Linear
    hypothesis with :func:`vegas_zero_hold_candidate`.
    """
    if not points:
        return []
    remapped = [dict(point) for point in points]
    for index in range(len(remapped) - 1):
        remapped[index]["interpolation_code"] = int(points[index + 1]["interpolation_code"])
    return vegas_zero_hold_candidate(remapped)


def _evaluate_linear_curve(points: list[list[float]], time: float) -> float:
    """Evaluate a decoded value path with linear segments for a pilot only."""
    if not points:
        return 0.0
    if time <= points[0][0]:
        return float(points[0][1])
    if time >= points[-1][0]:
        return float(points[-1][1])
    right_index = bisect_right([float(point[0]) for point in points], time)
    left = points[right_index - 1]
    right = points[right_index]
    fraction = (time - float(left[0])) / (float(right[0]) - float(left[0]))
    return float(left[1]) + fraction * (float(right[1]) - float(left[1]))


def shared_arc_length_time_map(component_curves: list[dict[str, list[list[float]]]],
                               sample_count: int = 121) -> list[float]:
    """Return one eased source-time map for an ordered set of component curves.

    The decoded parameter values and component synchronization are retained,
    while source-time pauses shared by the entire stack are compressed. Every
    animated parameter is normalized by its own value range and contributes
    equally within its component; components are then weighted equally. The
    returned map is a diagnostic native-equivalent candidate, not a decoding
    of the proprietary interpolation/tangent fields.
    """
    if sample_count < 2:
        raise ValueError("time-map sample count must be at least two")

    dynamic: list[tuple[list[list[float]], float, float, float]] = []
    key_times = {0.0, 1.0}
    for component in component_curves:
        candidates = []
        for points in component.values():
            if len(points) < 2:
                continue
            values = [float(point[1]) for point in points]
            low, high = min(values), max(values)
            if not math.isfinite(low) or not math.isfinite(high):
                raise ValueError("curve values must be finite")
            if high - low <= 1e-12:
                continue
            if any(not math.isfinite(float(point[0])) or not 0.0 <= float(point[0]) <= 1.0
                   for point in points):
                raise ValueError("curve times must be finite and in [0, 1]")
            if any(float(right[0]) <= float(left[0]) for left, right in zip(points, points[1:])):
                raise ValueError("curve times must be strictly increasing")
            candidates.append((points, low, high))
            key_times.update(float(point[0]) for point in points)
        if candidates:
            weight = 1.0 / math.sqrt(len(candidates))
            dynamic.extend((points, low, high, weight) for points, low, high in candidates)

    if not dynamic:
        return [index / (sample_count - 1) for index in range(sample_count)]

    progress = sorted(key_times)
    cumulative = [0.0]
    previous = []
    for points, low, high, weight in dynamic:
        previous.append((_evaluate_linear_curve(points, progress[0]) - low) / (high - low) * weight)
    for time in progress[1:]:
        current = [(_evaluate_linear_curve(points, time) - low) / (high - low) * weight
                   for points, low, high, weight in dynamic]
        distance = math.sqrt(sum((right - left) ** 2 for left, right in zip(previous, current)))
        cumulative.append(cumulative[-1] + distance)
        previous = current

    total = cumulative[-1]
    if total <= 1e-12:
        return [index / (sample_count - 1) for index in range(sample_count)]

    # Collapse duplicate arc positions from full-stack holds, retaining the
    # later source time so the hold consumes no rendered interval.
    unique_distance: list[float] = []
    unique_time: list[float] = []
    for time, distance in zip(progress, cumulative):
        normalized = distance / total
        if unique_distance and normalized <= unique_distance[-1] + 1e-12:
            unique_time[-1] = time
        else:
            unique_distance.append(normalized)
            unique_time.append(time)

    result = []
    for index in range(sample_count):
        event_progress = index / (sample_count - 1)
        eased_distance = event_progress * event_progress * (3.0 - 2.0 * event_progress)
        right = bisect_right(unique_distance, eased_distance)
        if right <= 0:
            result.append(unique_time[0])
        elif right >= len(unique_distance):
            result.append(unique_time[-1])
        else:
            left = right - 1
            span = unique_distance[right] - unique_distance[left]
            fraction = (eased_distance - unique_distance[left]) / span if span > 1e-12 else 1.0
            result.append(unique_time[left] + fraction * (unique_time[right] - unique_time[left]))
    result[0] = 0.0
    result[-1] = 1.0
    return result


def screen_space_arc_length_time_map(component_curves: list[dict[str, list[list[float]]]],
                                     width: int, height: int,
                                     sample_count: int = 121) -> list[float]:
    """Return a diagnostic time map weighted by approximate raster motion.

    Unlike :func:`shared_arc_length_time_map`, this does not normalize each
    control to an equal 0..1 range. Translation fractions are weighted in
    output pixels, scale and Z by their approximate mean radius, rotation by
    pixel-radius per degree, and fisheye/shake controls by conservative raster
    estimates. This makes a five-frame-width pan count more than a 10% zoom.
    The estimates are useful for a controlled pilot, not a Sapphire algorithm
    or a production interpolation rule.
    """
    if width <= 0 or height <= 0 or sample_count < 2:
        raise ValueError("raster dimensions and sample count must be positive")
    diagonal = math.hypot(width, height)
    shortest = min(width, height)
    weights = {
        "shift_x": float(width), "shift_y": float(height),
        "shift_orig_x": float(width), "shift_orig_y": float(height),
        "center_x": float(width), "center_y": float(height),
        "scale_x": width / math.sqrt(12.0),
        "scale_y": height / math.sqrt(12.0),
        "z_distance": math.hypot(width, height) / math.sqrt(12.0),
        "rotation": diagonal * math.pi / 360.0,
        "amount": diagonal * 0.25,
        "amplitude": float(shortest),
    }
    dynamic: list[tuple[list[list[float]], float]] = []
    key_times = {0.0, 1.0}
    for component in component_curves:
        for name, points in component.items():
            if len(points) < 2 or name not in weights:
                continue
            if any(not math.isfinite(float(point[0])) or not math.isfinite(float(point[1]))
                   or not 0.0 <= float(point[0]) <= 1.0 for point in points):
                raise ValueError("curve times and values must be finite and in [0, 1]")
            if any(float(right[0]) <= float(left[0]) for left, right in zip(points, points[1:])):
                raise ValueError("curve times must be strictly increasing")
            dynamic.append((points, weights[name]))
            key_times.update(float(point[0]) for point in points)

    if not dynamic:
        return [index / (sample_count - 1) for index in range(sample_count)]

    progress = sorted(key_times)
    cumulative = [0.0]
    previous = [_evaluate_linear_curve(points, progress[0]) * scale
                for points, scale in dynamic]
    for time in progress[1:]:
        current = [_evaluate_linear_curve(points, time) * scale
                   for points, scale in dynamic]
        distance = math.sqrt(sum((right - left) ** 2 for left, right in zip(previous, current)))
        cumulative.append(cumulative[-1] + distance)
        previous = current

    total = cumulative[-1]
    if total <= 1e-12:
        return [index / (sample_count - 1) for index in range(sample_count)]

    unique_distance: list[float] = []
    unique_time: list[float] = []
    for time, distance in zip(progress, cumulative):
        normalized = distance / total
        if unique_distance and normalized <= unique_distance[-1] + 1e-12:
            unique_time[-1] = time
        else:
            unique_distance.append(normalized)
            unique_time.append(time)

    result = []
    for index in range(sample_count):
        event_progress = index / (sample_count - 1)
        eased_distance = event_progress * event_progress * (3.0 - 2.0 * event_progress)
        right = bisect_right(unique_distance, eased_distance)
        if right <= 0:
            result.append(unique_time[0])
        elif right >= len(unique_distance):
            result.append(unique_time[-1])
        else:
            left = right - 1
            span = unique_distance[right] - unique_distance[left]
            fraction = (eased_distance - unique_distance[left]) / span if span > 1e-12 else 1.0
            result.append(unique_time[left] + fraction * (unique_time[right] - unique_time[left]))
    result[0] = 0.0
    result[-1] = 1.0
    return result


def effect_strength_time_map(component_curves: list[dict[str, list[list[float]]]],
                             width: int, height: int, role: str,
                             sample_count: int = 241,
                             ease_weight: float = 0.1) -> list[float]:
    """Fit a shared candidate time map to increasing/decreasing effect strength.

    For an outgoing event, the expected strength rises from the neutral start;
    for incoming it falls toward the neutral endpoint. A single raster-scaled
    magnitude is formed from decoded transform/warp/shake controls, then
    monotonized in the expected direction. Inverting that envelope distributes
    the same source trajectory across a near-linear whole-event strength curve
    with a modest smoothstep blend, so subtle terminal motion is not compressed
    into an early-settled hold. Component order and synchronization are
    preserved. This is a diagnostic
    native-equivalent candidate; the weights and source interpolation are not
    decoded Sapphire behavior.
    """
    if width <= 0 or height <= 0 or sample_count < 2:
        raise ValueError("raster dimensions and sample count must be positive")
    if role not in ("incoming", "outgoing"):
        raise ValueError("effect-strength easing requires an incoming or outgoing role")
    if not math.isfinite(ease_weight) or not 0.0 <= ease_weight <= 1.0:
        raise ValueError("ease weight must be finite and in [0, 1]")
    diagonal = math.hypot(width, height)
    neutral = {
        "shift_x": 0.0, "shift_y": 0.0,
        "shift_orig_x": 0.0, "shift_orig_y": 0.0,
        "center_x": 0.5, "center_y": 0.5,
        "scale_x": 1.0, "scale_y": 1.0,
        "z_distance": 1.0, "rotation": 0.0,
        "amount": 0.0, "amplitude": 0.0,
    }
    weights = {
        "shift_x": float(width), "shift_y": float(height),
        "shift_orig_x": float(width), "shift_orig_y": float(height),
        "center_x": float(width), "center_y": float(height),
        "scale_x": width / math.sqrt(12.0),
        "scale_y": height / math.sqrt(12.0),
        "z_distance": diagonal / math.sqrt(12.0),
        "rotation": diagonal * math.pi / 360.0,
        "amount": diagonal * 0.25,
        "amplitude": float(min(width, height)),
    }
    tracks: list[tuple[str, list[list[float]], float, float]] = []
    for component in component_curves:
        for name, points in component.items():
            if name not in weights or len(points) < 2:
                continue
            if any(not math.isfinite(float(point[0])) or not math.isfinite(float(point[1]))
                   or not 0.0 <= float(point[0]) <= 1.0 for point in points):
                raise ValueError("curve times and values must be finite and in [0, 1]")
            if any(float(right[0]) <= float(left[0]) for left, right in zip(points, points[1:])):
                raise ValueError("curve times must be strictly increasing")
            tracks.append((name, points, neutral[name], weights[name]))
    if not tracks:
        return [index / (sample_count - 1) for index in range(sample_count)]

    source_times = [index / (sample_count - 1) for index in range(sample_count)]
    strength = []
    for time in source_times:
        strength.append(math.sqrt(sum(
            ((_evaluate_linear_curve(points, time) - target) * scale) ** 2
            for _, points, target, scale in tracks
        )))
    envelope = []
    for value in strength:
        if not envelope:
            envelope.append(value)
        elif role == "incoming":
            envelope.append(min(envelope[-1], value))
        else:
            envelope.append(max(envelope[-1], value))

    start_strength, end_strength = envelope[0], envelope[-1]
    span = end_strength - start_strength if role == "outgoing" else start_strength - end_strength
    if span <= 1e-12:
        return source_times

    normalized_strength = []
    for value in envelope:
        progress = ((value - start_strength) / span if role == "outgoing"
                    else (start_strength - value) / span)
        normalized_strength.append(min(1.0, max(0.0, progress)))

    unique_progress: list[float] = []
    unique_time: list[float] = []
    for time, progress in zip(source_times, normalized_strength):
        if unique_progress and progress <= unique_progress[-1] + 1e-12:
            unique_time[-1] = time
        else:
            unique_progress.append(progress)
            unique_time.append(time)

    result = []
    for index in range(sample_count):
        event_progress = index / (sample_count - 1)
        smoothstep = event_progress * event_progress * (3.0 - 2.0 * event_progress)
        target_progress = (1.0 - ease_weight) * event_progress + ease_weight * smoothstep
        right = bisect_right(unique_progress, target_progress)
        if right <= 0:
            result.append(unique_time[0])
        elif right >= len(unique_progress):
            result.append(unique_time[-1])
        else:
            left = right - 1
            span = unique_progress[right] - unique_progress[left]
            fraction = (target_progress - unique_progress[left]) / span if span > 1e-12 else 1.0
            result.append(unique_time[left] + fraction * (unique_time[right] - unique_time[left]))
    result[0] = 0.0
    result[-1] = 1.0
    return result


def apply_shared_arc_length_time_candidate(tree, sample_count: int = 121) -> None:
    """Re-time a disposable fixture along one shared, eased parameter path.

    All component curves use the same mapping so their decoded relative
    synchronization cannot drift. Dense keys approximate the continuous
    reparameterized paths for fixture renders; this is not production data.
    """
    import json

    filters = tree.getroot().findall(".//producer/filter")
    components = []
    original: list[dict[str, list[list[float]]]] = []
    for element in filters:
        prop = element.find("property[@name='native_curves']")
        if prop is None or not prop.text:
            curves = {}
        else:
            curves = json.loads(prop.text)
        original.append(curves)
        components.append(curves)
    time_map = shared_arc_length_time_map(components, sample_count)
    event_samples = [index / (sample_count - 1) for index in range(sample_count)]
    for element, curves in zip(filters, original):
        prop = element.find("property[@name='native_curves']")
        if prop is None or not curves:
            continue
        retimed = {}
        for name, points in curves.items():
            retimed[name] = [
                [event_time, _evaluate_linear_curve(points, source_time),
                 event_time, _evaluate_linear_curve(points, source_time),
                 event_time, _evaluate_linear_curve(points, source_time), 0]
                for event_time, source_time in zip(event_samples, time_map)
            ]
        prop.text = json.dumps(retimed, separators=(",", ":"))


def apply_screen_space_arc_length_candidate(tree, width: int, height: int,
                                            sample_count: int = 121) -> None:
    """Retiming pilot with one approximate pixel-weighted map per producer stack."""
    import json

    event_samples = [index / (sample_count - 1) for index in range(sample_count)]
    root = tree.getroot()
    producers = [root] if root.tag == "producer" else root.findall(".//producer")
    for producer in producers:
        filters = producer.findall("filter")
        curves_by_filter = []
        for element in filters:
            prop = element.find("property[@name='native_curves']")
            curves_by_filter.append(json.loads(prop.text) if prop is not None and prop.text else {})
        time_map = screen_space_arc_length_time_map(curves_by_filter, width, height, sample_count)
        for element, curves in zip(filters, curves_by_filter):
            prop = element.find("property[@name='native_curves']")
            if prop is None or not curves:
                continue
            retimed = {}
            for name, points in curves.items():
                retimed[name] = [
                    [event_time, _evaluate_linear_curve(points, source_time),
                     event_time, _evaluate_linear_curve(points, source_time),
                     event_time, _evaluate_linear_curve(points, source_time), 0]
                    for event_time, source_time in zip(event_samples, time_map)
                ]
            prop.text = json.dumps(retimed, separators=(",", ":"))


def apply_effect_strength_ease_candidate(tree, width: int, height: int,
                                        sample_count: int = 121,
                                        ease_weight: float = 0.1) -> None:
    """Retiming pilot that eases a shared raster-scaled effect-strength path."""
    import json

    filters = tree.getroot().findall(".//producer/filter")
    curves_by_filter = []
    for element in filters:
        prop = element.find("property[@name='native_curves']")
        curves_by_filter.append(json.loads(prop.text) if prop is not None and prop.text else {})
    role = "outgoing"
    if filters:
        prop = filters[0].find("property[@name='native_event_role']")
        if prop is not None and prop.text in ("incoming", "outgoing"):
            role = prop.text
    time_map = effect_strength_time_map(curves_by_filter, width, height, role, sample_count,
                                        ease_weight)
    event_samples = [index / (sample_count - 1) for index in range(sample_count)]
    for element, curves in zip(filters, curves_by_filter):
        prop = element.find("property[@name='native_curves']")
        if prop is None or not curves:
            continue
        retimed = {}
        for name, points in curves.items():
            retimed[name] = [
                [event_time, _evaluate_linear_curve(points, source_time),
                 event_time, _evaluate_linear_curve(points, source_time),
                 event_time, _evaluate_linear_curve(points, source_time), 0]
                for event_time, source_time in zip(event_samples, time_map)
            ]
        prop.text = json.dumps(retimed, separators=(",", ":"))


def apply_endpoint_progress_candidate(tree, sample_count: int = 121,
                                      ease_weight: float = 0.4) -> None:
    """Fit every animated track from neutral to its event endpoint.

    This disposable visual candidate tests the user's specific requirement:
    the transition should progress across every displayed frame. It replaces
    intermediate source key positions with a shared event-wide easing while
    retaining each track's source endpoint values. Outgoing curves move from
    their neutral values toward their source endpoints; incoming curves move
    from their source starts toward neutral. The easing retains a linear floor
    so the per-frame parameter step cannot collapse to zero at either end.
    The shutter opens across an outgoing event and closes across an incoming
    event, making their outer endpoints sharp. The native renderer then scales
    that shutter curve with its frame-inclusive event/nominal duration ratio.

    This is not a decoded Sapphire interpolation and must not be enabled as a
    preset conversion without visual and source-fidelity review.
    """
    import json

    if sample_count < 2:
        raise ValueError("sample count must be at least two")
    if not math.isfinite(ease_weight) or not 0.0 <= ease_weight <= 1.0:
        raise ValueError("ease weight must be finite and in [0, 1]")

    neutral = {
        "z_distance": 1.0, "shift_x": 0.0, "shift_y": 0.0,
        "shift_orig_x": 0.0, "shift_orig_y": 0.0,
        "rotation": 0.0, "scale_x": 1.0, "scale_y": 1.0,
        "amount": 0.0, "amplitude": 0.0,
        "center_x": 0.5, "center_y": 0.5,
    }
    filters = tree.getroot().findall(".//producer/filter")
    for element in filters:
        curves_prop = element.find("property[@name='native_curves']")
        if curves_prop is None or not curves_prop.text:
            continue
        role_prop = element.find("property[@name='native_event_role']")
        role = (role_prop.text if role_prop is not None and role_prop.text in ("incoming", "outgoing")
                else "outgoing")
        curves = json.loads(curves_prop.text)
        rebuilt = {}
        for name, points in curves.items():
            if not points:
                continue
            source_start = float(points[0][1])
            source_end = float(points[-1][1])
            if role == "outgoing":
                start = neutral.get(name, source_start)
                end = source_end
            else:
                start = source_start
                end = neutral.get(name, source_end)
            output_points = []
            for index in range(sample_count):
                t = index / (sample_count - 1)
                if role == "outgoing":
                    ease = t * t
                else:
                    ease = 1.0 - (1.0 - t) * (1.0 - t)
                progress = (1.0 - ease_weight) * t + ease_weight * ease
                value = start + (end - start) * progress
                output_points.append([t, value, t, value, t, value, 0])
            rebuilt[name] = output_points
        service_prop = element.find("property[@name='mlt_service']")
        shutter_prop = element.find("property[@name='shutter_duration']")
        if (service_prop is not None and service_prop.text == "kdenlive_motion_curve"
                and shutter_prop is not None):
            shutter = float(shutter_prop.text)
            shutter_start, shutter_end = ((0.0, shutter) if role == "outgoing"
                                          else (shutter, 0.0))
            shutter_curve = []
            for index in range(sample_count):
                t = index / (sample_count - 1)
                eased = (t * t if role == "outgoing"
                         else 1.0 - (1.0 - t) * (1.0 - t))
                progress = (1.0 - ease_weight) * t + ease_weight * eased
                value = shutter_start + (shutter_end - shutter_start) * progress
                shutter_curve.append([t, value, t, value, t, value, 0])
            rebuilt["shutter_duration"] = shutter_curve
        curves_prop.text = json.dumps(rebuilt, separators=(",", ":"))


def endpoint_progress_bezier_points(start: float, end: float, role: str,
                                    ease_weight: float = 0.4) -> list[list[float]]:
    """Return a two-key cubic Bezier for the endpoint-progress easing.

    The curve is exactly ``(1-w)t + w*t²`` for outgoing and
    ``(1-w)t + w*(2t-t²)`` for incoming. Its time handles lie at one-third
    and two-thirds, so Bezier x is linear and the y function has a nonzero
    linear floor. Two keys keep the editable preset compact.
    """
    if role not in ("incoming", "outgoing"):
        raise ValueError("endpoint easing requires an incoming or outgoing role")
    if not math.isfinite(start) or not math.isfinite(end):
        raise ValueError("endpoint values must be finite")
    if not math.isfinite(ease_weight) or not 0.0 <= ease_weight <= 1.0:
        raise ValueError("ease weight must be finite and in [0, 1]")
    delta = end - start
    if role == "outgoing":
        handle1 = (1.0 - ease_weight) / 3.0
        handle2 = (2.0 - ease_weight) / 3.0
    else:
        handle1 = (1.0 + ease_weight) / 3.0
        handle2 = (2.0 + ease_weight) / 3.0
    return [
        [0.0, start, 0.0, start, 1.0 / 3.0, start + delta * handle1, 1],
        [1.0, end, 2.0 / 3.0, start + delta * handle2, 1.0, end, 0],
    ]


def slide_right_outgoing_points(start: float, end: float) -> list[list[float]]:
    """Shape the outgoing phase from readable start to strong cut-side smear."""
    delta = end - start
    return [
        [0.0, start, 0.0, start, 0.2, start + delta * 0.04, 1],
        [1.0, end, 0.65, start + delta * 0.60, 1.0, end, 0],
    ]


def slide_right_cut_acceleration_points(start: float, end: float) -> list[list[float]]:
    """Keep the start subtle and retain accelerating motion at the cut.

    The first and last decoded values are preserved. The initial tangent is
    0.2 times the average rate; the cut-side tangent is 2 times the average
    rate. This is a visual-fit candidate, not a decoded Sapphire interpolation.
    """
    delta = end - start
    return [
        [0.0, start, 0.0, start, 0.2, start + delta * 0.04, 1],
        [1.0, end, 0.82, start + delta * 0.64, 1.0, end, 0],
    ]


def slide_right_cut_shutter_envelope(start: float, end: float) -> list[list[float]]:
    """35%-linear-floor smoothstep envelope for the coordinated cut peak."""
    delta = end - start
    first_handle = 0.35 / 3.0
    second_handle = 1.0 - first_handle
    return [
        [0.0, start, 0.0, start, 1.0 / 3.0, start + delta * first_handle, 1],
        [1.0, end, 2.0 / 3.0, start + delta * second_handle, 1.0, end, 0],
    ]


def apply_slide_right_phase_shutter_candidate(tree, gain: float = 8.0,
                                              cut_acceleration: bool = False,
                                              incoming_ease_weight: float = 1.0) -> None:
    """Keep decoded single-axis slide endpoints and shape a blur peak at the cut.

    Sapphire's serialized interpolation codes are not mapped to native easing.
    This reconstruction applies to a Shift X-only or Shift Y-only source curve.
    With ``cut_acceleration=True``, it retains an accelerating outgoing tangent
    at the cut and uses a shared linear-floor smoothstep shutter envelope. It
    preserves source endpoints and shutter values. The extra gain/envelope and
    the 16 transform-path samples are native visual-fit controls, not decoded
    Sapphire values. The sample count was selected from a direct-render
    comparison because 8 samples left visibly separated trails.
    """
    import json
    import xml.etree.ElementTree as ET

    if not math.isfinite(gain) or gain < 0.0 or gain > 16.0:
        raise ValueError("Slide Right shutter gain must be finite and in [0, 16]")
    if not math.isfinite(incoming_ease_weight) or not 0.0 <= incoming_ease_weight <= 1.0:
        raise ValueError("incoming easing weight must be finite and in [0, 1]")
    filters = tree.getroot().findall(".//filter")
    phase_envelope = None
    for element in filters:
        properties = {prop.get("name"): prop for prop in element.findall("property")}
        if properties.get("mlt_service") is None or properties["mlt_service"].text != "kdenlive_motion_curve":
            continue
        role_node = properties.get("native_event_role")
        role = role_node.text if role_node is not None else "outgoing"
        if role not in ("outgoing", "incoming"):
            raise ValueError(f"unsupported Slide Right event role: {role!r}")
        curves_node = properties.get("native_curves")
        if curves_node is None or not curves_node.text:
            raise ValueError("Slide Right motion filter has no source curves")
        curves = json.loads(curves_node.text)
        shift_keys = {"shift_x", "shift_y"}.intersection(curves)
        if len(shift_keys) != 1:
            raise ValueError(f"slide candidate needs exactly one animated translation axis: {sorted(curves)}")
        required = shift_keys
        allowed = required | {"shutter_duration", "brightness"}
        if not required.issubset(curves) or not set(curves).issubset(allowed):
            raise ValueError(f"single-axis slide decoded curve set changed: {sorted(curves)}")
        for name in sorted(curves):
            points = curves[name]
            if (len(points) != 2 or abs(float(points[0][0])) > 1e-8
                    or not 0.999 <= float(points[-1][0]) <= 1.0):
                raise ValueError(f"Slide Right {name} must retain its two normalized source endpoints")
            if role == "outgoing":
                points_builder = (slide_right_cut_acceleration_points if cut_acceleration
                                  else slide_right_outgoing_points)
                curves[name] = points_builder(float(points[0][1]), float(points[-1][1]))
            else:
                curves[name] = endpoint_progress_bezier_points(
                    float(points[0][1]), float(points[-1][1]), role, incoming_ease_weight)
        envelope_start, envelope_end = (0.0, 1.0) if role == "outgoing" else (1.0, 0.0)
        if cut_acceleration:
            curves["shutter_envelope"] = slide_right_cut_shutter_envelope(envelope_start, envelope_end)
        else:
            curves["shutter_envelope"] = (slide_right_outgoing_points(envelope_start, envelope_end)
                                           if role == "outgoing"
                                           else endpoint_progress_bezier_points(envelope_start, envelope_end, role, 1.0))
        phase_envelope = curves["shutter_envelope"]
        curves_node.text = json.dumps(curves, separators=(",", ":"))

        # Motion-path integration needs enough subframe transforms to render a
        # continuous smear at the cut. This is deliberately scoped to the
        # transform filter; vector-blur quality remains independently editable.
        quality_node = properties.get("quality_samples")
        if quality_node is None:
            quality_node = ET.SubElement(element, "property", {"name": "quality_samples"})
            properties["quality_samples"] = quality_node
        quality_node.text = "16"

        # The active value is saved with the group while its animated
        # adjustment is exposed as an ordinary effect-stack control.
        for name, value in (("shutter_gain", "1"), ("shutter_envelope", "1"),
                            ("shutter_gain_adjust", str(gain)), ("shutter_envelope_adjust", "1")):
            node = properties.get(name)
            if node is None:
                node = ET.SubElement(element, "property", {"name": name})
                properties[name] = node
            node.text = value

    if phase_envelope is None:
        raise ValueError("Slide Right group has no Motion Transform and Blur component")
    for element in filters:
        properties = {prop.get("name"): prop for prop in element.findall("property")}
        service = properties.get("mlt_service")
        if service is None or service.text != "kdenlive_motion_vector_blur":
            continue
        curves_node = properties.get("native_curves")
        if curves_node is None:
            curves_node = ET.SubElement(element, "property", {"name": "native_curves"})
            properties["native_curves"] = curves_node
        curves = json.loads(curves_node.text or "{}")
        curves["blur_envelope"] = phase_envelope
        curves_node.text = json.dumps(curves, separators=(",", ":"))
        adjustment = properties.get("blur_envelope_adjust")
        if adjustment is None:
            adjustment = ET.SubElement(element, "property", {"name": "blur_envelope_adjust"})
        adjustment.text = "1"


def apply_slide_down_33_cut_peak_candidate(tree, record: dict,
                                            local_animation_keys: bool = False) -> None:
    """Fit an editable vertical displacement and shutter peak to a 3.3 event.

    This is a per-record visual reconstruction, not decoded Sapphire data. It
    preserves the source Shift Y curve and adds a role-specific animated
    adjustment: the outgoing event builds downwards into the cut, while the
    incoming event starts displaced upwards and settles. A shutter adjustment
    follows the same event span so the image becomes strongly streaked at the
    boundary and returns to a sharp endpoint.

    Template XML stores key positions relative to the nominal event. Direct
    fixture projects use their source/filter coordinate range instead.
    """
    import xml.etree.ElementTree as ET

    valid_ids = {
        "{5CA7AF07-AEAC-4DC1-84FF-2ADDE18EDE37}": "outgoing",
        "{6198F889-3A81-4EB9-9064-294B1203958A}": "incoming",
    }
    source_id = record.get("source_identifier")
    role = valid_ids.get(source_id)
    if role is None or record.get("event_variant") != role:
        raise ValueError("Slide Down 3.3 peak fit requires one of the exact source records")

    filters = tree.getroot().findall(".//producer/filter")
    if len(filters) != 1:
        raise ValueError("Slide Down 3.3 peak fit requires exactly one Motion Transform and Blur row")
    element = filters[0]
    properties = {prop.get("name"): prop for prop in element.findall("property")}
    if properties.get("mlt_service") is None or properties["mlt_service"].text != "kdenlive_motion_curve":
        raise ValueError("Slide Down 3.3 peak fit requires the native motion renderer")
    event_role = properties.get("native_event_role")
    if event_role is None or event_role.text != role:
        raise ValueError("Slide Down 3.3 event role does not match its source identity")
    event_frames_node = properties.get("native_event_frames")
    event_frames = int(event_frames_node.text) if event_frames_node is not None and event_frames_node.text else 0
    if event_frames < 1:
        raise ValueError("Slide Down 3.3 peak fit has no event duration")

    start = 0 if local_animation_keys else int(element.get("in", "0"))
    end = start + event_frames - 1
    if event_frames == 1:
        shift_adjust = 0.75 if role == "outgoing" else -0.75
        shutter_adjust = 16.0
        animations = {
            "shift_y_adjust": f"{start}={shift_adjust:g}",
            "shutter_duration_adjust": f"{start}={shutter_adjust:g}",
        }
    elif role == "outgoing":
        animations = {
            "shift_y_adjust": f"{start}=0;{end}=0.75",
            "shutter_duration_adjust": f"{start}=-1;{end}=16",
        }
    else:
        animations = {
            "shift_y_adjust": f"{start}=-0.75;{end}=0",
            "shutter_duration_adjust": f"{start}=16;{end}=-1",
        }
    for name, value in animations.items():
        node = properties.get(name)
        if node is None:
            node = ET.SubElement(element, "property", {"name": name})
            properties[name] = node
        node.text = value
    quality = properties.get("quality_samples")
    if quality is None:
        quality = ET.SubElement(element, "property", {"name": "quality_samples"})
    quality.text = "32"


def apply_endpoint_progress_bezier_candidate(tree, ease_weight: float = 0.4) -> None:
    """Create compact editable Bezier curves for an endpoint-progress pilot."""
    import json

    neutral = {
        "z_distance": 1.0, "shift_x": 0.0, "shift_y": 0.0,
        "shift_orig_x": 0.0, "shift_orig_y": 0.0,
        "rotation": 0.0, "scale_x": 1.0, "scale_y": 1.0,
        "amount": 0.0, "amplitude": 0.0,
        "center_x": 0.5, "center_y": 0.5,
    }
    filters = tree.getroot().findall(".//producer/filter")
    role = "outgoing"
    if filters:
        role_prop = filters[0].find("property[@name='native_event_role']")
        if role_prop is not None and role_prop.text in ("incoming", "outgoing"):
            role = role_prop.text

    for element in filters:
        curves_prop = element.find("property[@name='native_curves']")
        if curves_prop is None or not curves_prop.text:
            continue
        curves = json.loads(curves_prop.text)
        rebuilt = {}
        for name, points in curves.items():
            if not points:
                continue
            source_start = float(points[0][1])
            source_end = float(points[-1][1])
            if role == "outgoing":
                start, end = neutral.get(name, source_start), source_end
            else:
                start, end = source_start, neutral.get(name, source_end)
            rebuilt[name] = endpoint_progress_bezier_points(start, end, role, ease_weight)

        service_prop = element.find("property[@name='mlt_service']")
        shutter_prop = element.find("property[@name='shutter_duration']")
        if (service_prop is not None and service_prop.text == "kdenlive_motion_curve"
                and shutter_prop is not None):
            shutter = float(shutter_prop.text)
            start, end = ((0.0, shutter) if role == "outgoing" else (shutter, 0.0))
            rebuilt["shutter_duration"] = endpoint_progress_bezier_points(start, end, role, ease_weight)
        curves_prop.text = json.dumps(rebuilt, separators=(",", ":"))


def smoothstep_endpoint_bezier_points(start: float, end: float,
                                      ease_weight: float = 0.65) -> list[list[float]]:
    """Return a cubic Bezier for a linear-floor, smoothstep endpoint ramp.

    The normalized progress is ``(1-w)t + w(3t² - 2t³)``. The linear part
    keeps each sampled frame moving, while the smoothstep portion reduces the
    initial and final velocity. This is a render candidate, not a decoded
    source interpolation rule.
    """
    if not math.isfinite(start) or not math.isfinite(end):
        raise ValueError("curve endpoint values must be finite")
    if not math.isfinite(ease_weight) or not 0.0 <= ease_weight < 1.0:
        raise ValueError("smoothstep ease weight must be finite and in [0, 1)")
    linear_floor = 1.0 - ease_weight
    delta = end - start
    first_value = start + delta * linear_floor / 3.0
    second_value = end - delta * linear_floor / 3.0
    return [
        [0.0, start, 0.0, start, 1.0 / 3.0, first_value, 1],
        [1.0, end, 2.0 / 3.0, second_value, 1.0, end, 0],
    ]


def apply_smoothstep_endpoint_bezier_candidate(tree, ease_weight: float = 0.65,
                                               fit_shutter_shift: bool = False) -> None:
    """Fit native effect filters in a fixture or delivery MLT to a candidate curve.

    ``fit_shutter_shift`` is an explicitly approximate pilot: it retains the
    source shift's peak value but tapers the offset to zero at both event
    endpoints. This can prevent a stretched, forward-shifted shutter from
    reaching the curve endpoint early. It is not the source plugin's static
    Shutter Shift behavior and must remain opt-in until rendered comparison.
    """
    import json

    neutral = {
        "z_distance": 1.0, "shift_x": 0.0, "shift_y": 0.0,
        "shift_orig_x": 0.0, "shift_orig_y": 0.0,
        "rotation": 0.0, "scale_x": 1.0, "scale_y": 1.0,
        "amount": 0.0, "amplitude": 0.0,
        "center_x": 0.5, "center_y": 0.5,
    }
    filters = tree.getroot().findall(".//filter")
    for element in filters:
        curves_prop = element.find("property[@name='native_curves']")
        if curves_prop is None or not curves_prop.text:
            continue
        role_prop = element.find("property[@name='native_event_role']")
        role = (role_prop.text if role_prop is not None and role_prop.text in ("incoming", "outgoing")
                else "outgoing")
        curves = json.loads(curves_prop.text)
        rebuilt = {}
        for name, points in curves.items():
            if not points:
                continue
            first, last = float(points[0][1]), float(points[-1][1])
            start, end = ((neutral.get(name, first), last) if role == "outgoing"
                          else (first, neutral.get(name, last)))
            rebuilt[name] = smoothstep_endpoint_bezier_points(start, end, ease_weight)

        service_prop = element.find("property[@name='mlt_service']")
        shutter_prop = element.find("property[@name='shutter_duration']")
        if (service_prop is not None and service_prop.text == "kdenlive_motion_curve"
                and shutter_prop is not None):
            shutter = float(shutter_prop.text)
            start, end = ((0.0, shutter) if role == "outgoing" else (shutter, 0.0))
            rebuilt["shutter_duration"] = smoothstep_endpoint_bezier_points(start, end, ease_weight)
            shift_prop = element.find("property[@name='shutter_shift']")
            if fit_shutter_shift and shift_prop is not None:
                shift = float(shift_prop.text or "0")
                rebuilt["shutter_shift"] = monotone_bezier_points([
                    [0.0, 0.0], [0.5, shift], [1.0, 0.0],
                ])
        curves_prop.text = json.dumps(rebuilt, separators=(",", ":"))


def apply_scroll_right_27_cut_peak_candidate(tree, record: dict,
                                             ease_weight: float = 0.65) -> None:
    """Fit the exact 2.7 Scroll Right pair to one coordinated cut peak.

    This visual reconstruction preserves each native component and its source
    endpoint values, while replacing source intermediate timing with an eased
    whole-event path. The decoded motion blur was too weak at the cut in the
    previous direct render, so an individually editable shutter-gain control
    and 32-sample integration are applied to the Motion Transform and Blur row.
    Values are deliberately scoped to these two source UUIDs and are not claimed
    to be decoded Sapphire parameters.
    """
    import xml.etree.ElementTree as ET

    configurations = {
        "{A00199B4-139C-420E-88BE-4189A635B769}":
            ("2.7 Scroll Right (1) 20k", "outgoing", 8),
        "{CEFDEE77-588E-4932-9CBD-5D707852264A}":
            ("2.7 Scroll Right (2) 20k", "incoming", 16),
    }
    source_id = record.get("source_identifier")
    expected = configurations.get(source_id)
    if expected is None or (record.get("exact_name"), record.get("event_variant")) != expected[:2]:
        raise ValueError("cut-peak fit is limited to the exact 2.7 Scroll Right source pair")

    apply_smoothstep_endpoint_bezier_candidate(tree, ease_weight=ease_weight)
    filters = tree.getroot().findall(".//filter")
    motion = [element for element in filters
              if element.findtext("property[@name='mlt_service']") == "kdenlive_motion_curve"]
    if len(motion) != 1:
        raise ValueError("2.7 Scroll Right requires exactly one Motion Transform and Blur component")
    properties = {node.get("name"): node for node in motion[0].findall("property")}
    gain = expected[2]
    for name, value in (("shutter_gain_adjust", str(gain)), ("quality_samples", "32")):
        node = properties.get(name)
        if node is None:
            node = ET.SubElement(motion[0], "property", {"name": name})
            properties[name] = node
        node.text = value


def apply_scroll_right_27_incoming_cubic_ease_out_v2(tree, record: dict) -> None:
    """Use a monotone ease-out for the 2.7 incoming recovery half.

    The source-id-scoped cut-peak candidate made the final endpoint exact, but
    its symmetric smoothstep held the strongest incoming distortion too long
    on short events. This keeps the cut-side values and component chain, then
    makes each incoming parameter recover quickly at first and settle more
    gently into its neutral endpoint. It is a native timing fit, not decoded
    Sapphire interpolation.
    """
    import json

    expected_id = "{CEFDEE77-588E-4932-9CBD-5D707852264A}"
    if (record.get("source_identifier") != expected_id
            or record.get("exact_name") != "2.7 Scroll Right (2) 20k"
            or record.get("event_variant") != "incoming"):
        raise ValueError("cubic ease-out is limited to 2.7 Scroll Right (2) 20k")

    neutral = {
        "z_distance": 1.0, "shift_x": 0.0, "shift_y": 0.0,
        "shift_orig_x": 0.0, "shift_orig_y": 0.0,
        "rotation": 0.0, "scale_x": 1.0, "scale_y": 1.0,
        "amount": 0.0, "amplitude": 0.0,
        "center_x": 0.5, "center_y": 0.5,
    }
    filters = tree.getroot().findall(".//filter")
    updated = 0
    motion_found = False
    services = []
    for element in filters:
        role = element.find("property[@name='native_event_role']")
        if role is None or role.text != "incoming":
            raise ValueError("2.7 incoming easing cannot modify an outgoing filter")
        service = element.findtext("property[@name='mlt_service']")
        curves_property = element.find("property[@name='native_curves']")
        if not service or curves_property is None or not curves_property.text:
            continue
        services.append(service)
        curves = json.loads(curves_property.text)
        if service == "kdenlive_motion_curve":
            if not {"shift_x", "z_distance", "shutter_duration"}.issubset(curves):
                raise ValueError("2.7 incoming motion curves are incomplete")
            motion_found = True
        for name, points in curves.items():
            if not points:
                continue
            start = float(points[0][1])
            end = neutral.get(name, float(points[-1][1]))
            curves[name] = cubic_ease_out_endpoint_points(start, end)
            updated += 1
        curves_property.text = json.dumps(curves, separators=(",", ":"))
    if (services != ["kdenlive_motion_curve", "kdenlive_shake", "kdenlive_fisheye_warp"]
            or not motion_found or updated < 3):
        raise ValueError("2.7 incoming stack did not contain its complete native curve chain")


def apply_zoom_out_spin_clockwise_incoming_eventwide_candidate(
        tree, record: dict, ease_weight: float = 0.65) -> None:
    """Spread the exact 10.6 incoming active curve over the selected event.

    This is a narrowly scoped visual candidate, not a Sapphire timing decode.
    It retains the decoded incoming endpoint values for Z distance, rotation,
    and shutter duration, remaps the active source span [0.7541, 1] to [0, 1],
    and applies the same 35%-linear-floor smoothstep to each coupled curve.
    The source inventory and active preset are never modified by this helper.
    """
    import json
    from xml.etree import ElementTree as ET

    source_id = "{8251884A-4379-40BE-BBB4-A30EFC673140}"
    if (record.get("source_identifier") != source_id
            or record.get("exact_name") != "10.6 Zoom Out Spin ClockWise (2) 15k"
            or record.get("event_variant") != "incoming"):
        raise ValueError("event-wide timing candidate is limited to the 10.6 clockwise incoming source record")
    components = record.get("components") or []
    if (len(components) != 1
            or not components[0].get("vendor_id", "").endswith("S_BlurMoCurves}")):
        raise ValueError("10.6 incoming candidate requires its single S_BlurMoCurves source component")

    source_names = {"Z Dist": "z_distance", "Rotate": "rotation", "Shutter Duration": "shutter_duration"}
    source_curves = {}
    for parameter in components[0].get("parameters", []):
        native_name = source_names.get(parameter.get("name"))
        animation = parameter.get("animation") or {}
        points = animation.get("points") or []
        if native_name and points:
            source_curves[native_name] = [
                (float(point["normalized_event_position"]), float(point["value"])) for point in points
            ]
    expected = {
        "z_distance": [(0.7540976357699892, 0.5), (1.0, 1.0)],
        "rotation": [(0.0, 45.0), (0.7540976357699892, 45.0), (1.0, 0.0)],
        "shutter_duration": [(0.7540976357699892, 1.5), (1.0, 1.0)],
    }
    if set(source_curves) != set(expected):
        raise ValueError("10.6 incoming candidate source curves differ from the decoded Z/Rotate/Shutter set")
    for name, expected_points in expected.items():
        actual_points = source_curves[name]
        if len(actual_points) != len(expected_points) or any(
                abs(actual[0] - expected_point[0]) > 1e-6 or abs(actual[1] - expected_point[1]) > 1e-6
                for actual, expected_point in zip(actual_points, expected_points)):
            raise ValueError(f"10.6 incoming {name} source keys differ from the reviewed record")

    matching = []
    for element in tree.getroot().findall(".//filter"):
        props = {prop.get("name"): prop for prop in element.findall("property")}
        if props.get("native_preset_id") is not None and props["native_preset_id"].text == source_id:
            matching.append((element, props))
    if len(matching) != 1:
        raise ValueError("candidate project must contain exactly one filter for the incoming 10.6 source UUID")
    element, props = matching[0]
    if (props.get("mlt_service") is None or props["mlt_service"].text != "kdenlive_motion_curve"
            or props.get("native_event_role") is None or props["native_event_role"].text != "incoming"):
        raise ValueError("candidate filter service or event role does not match the incoming source record")
    curves_prop = props.get("native_curves")
    if curves_prop is None or not curves_prop.text:
        raise ValueError("candidate filter has no native_curves property")
    curves = json.loads(curves_prop.text)
    for name, expected_points in expected.items():
        points = curves.get(name)
        actual_points = [(float(point[0]), float(point[1])) for point in points or []]
        if len(actual_points) != len(expected_points) or any(
                abs(actual[0] - source[0]) > 1e-6 or abs(actual[1] - source[1]) > 1e-6
                for actual, source in zip(actual_points, expected_points)):
            raise ValueError(f"saved project {name} keys do not match the decoded source curve")
        curves[name] = smoothstep_endpoint_bezier_points(
            expected_points[0][1], expected_points[-1][1], ease_weight)

    curves_prop.text = json.dumps(curves, separators=(",", ":"))
    candidate_id = "10.6-cw-incoming-eventwide-linear-floor-smoothstep-65-v1"
    for name, value in (("native_curve_candidate_id", candidate_id),
                        ("native_curve_candidate_note", "Remaps decoded active key span 0.7540976..1.0 to selected-event progress 0..1; endpoint values retained; candidate timing differs from source keys.")):
        prop = props.get(name)
        if prop is None:
            prop = ET.SubElement(element, "property", {"name": name})
        prop.text = value


def apply_zoom_out_spin_counterclockwise_incoming_shutter_taper_candidate(
        tree, record: dict, ease_weight: float = 0.65) -> None:
    """Test endpoint-sharp recovery for the exact 10.7 incoming spin row.

    The decoded Z-distance and rotation curves are retained exactly. Only the
    decoded shutter-duration curve's final value changes: it eases from the
    source's 1.5 value at 0.7541 to zero at event progress 1, so a stretched,
    centered shutter cannot continue integrating earlier rotation at the last
    frame. This is an explicit native visual candidate, not a source decode.
    """
    import json
    from xml.etree import ElementTree as ET

    source_id = "{57C53ED1-D794-4D49-9665-47A23F873410}"
    if (record.get("source_identifier") != source_id
            or record.get("exact_name") != "10.7 Zoom Out Spin CounterClockWise (2) 15k"
            or record.get("event_variant") != "incoming"):
        raise ValueError("shutter taper candidate is limited to the 10.7 counterclockwise incoming source record")
    components = record.get("components") or []
    if (len(components) != 1
            or not components[0].get("vendor_id", "").endswith("S_BlurMoCurves}")):
        raise ValueError("10.7 incoming candidate requires its single S_BlurMoCurves source component")

    source_names = {"Z Dist": "z_distance", "Rotate": "rotation", "Shutter Duration": "shutter_duration"}
    source_curves = {}
    for parameter in components[0].get("parameters", []):
        native_name = source_names.get(parameter.get("name"))
        points = (parameter.get("animation") or {}).get("points") or []
        if native_name and points:
            source_curves[native_name] = [
                (float(point["normalized_event_position"]), float(point["value"])) for point in points
            ]
    active = 0.7540976357699892
    expected = {
        "z_distance": [(active, 0.5), (1.0, 1.0)],
        "rotation": [(0.0, 45.0), (active, -45.0), (1.0, 0.0)],
        "shutter_duration": [(active, 1.5), (1.0, 1.0)],
    }
    if set(source_curves) != set(expected):
        raise ValueError("10.7 incoming candidate source curves differ from the decoded Z/Rotate/Shutter set")
    for name, expected_points in expected.items():
        actual_points = source_curves[name]
        if len(actual_points) != len(expected_points) or any(
                abs(actual[0] - point[0]) > 1e-6 or abs(actual[1] - point[1]) > 1e-6
                for actual, point in zip(actual_points, expected_points)):
            raise ValueError(f"10.7 incoming {name} source keys differ from the reviewed record")

    matching = []
    for element in tree.getroot().findall(".//filter"):
        props = {prop.get("name"): prop for prop in element.findall("property")}
        if props.get("native_preset_id") is not None and props["native_preset_id"].text == source_id:
            matching.append((element, props))
    if len(matching) != 1:
        raise ValueError("candidate project must contain exactly one filter for the incoming 10.7 source UUID")
    element, props = matching[0]
    if (props.get("mlt_service") is None or props["mlt_service"].text != "kdenlive_motion_curve"
            or props.get("native_event_role") is None or props["native_event_role"].text != "incoming"):
        raise ValueError("candidate filter service or event role does not match the incoming 10.7 source record")
    curves_prop = props.get("native_curves")
    if curves_prop is None or not curves_prop.text:
        raise ValueError("candidate filter has no native_curves property")
    curves = json.loads(curves_prop.text)
    for name, expected_points in expected.items():
        points = curves.get(name)
        actual_points = [(float(point[0]), float(point[1])) for point in points or []]
        if len(actual_points) != len(expected_points) or any(
                abs(actual[0] - point[0]) > 1e-6 or abs(actual[1] - point[1]) > 1e-6
                for actual, point in zip(actual_points, expected_points)):
            raise ValueError(f"saved project {name} keys do not match the decoded 10.7 source curve")

    shutter = smoothstep_endpoint_bezier_points(1.5, 0.0, ease_weight)
    span = 1.0 - active
    for point in shutter:
        point[0] = active + point[0] * span
        point[2] = active + point[2] * span
        point[4] = active + point[4] * span
    curves["shutter_duration"] = shutter
    curves_prop.text = json.dumps(curves, separators=(",", ":"))
    ease_percent = int(round(ease_weight * 100))
    candidate_id = f"10.7-ccw-incoming-endpoint-sharp-shutter-taper-smoothstep-{ease_percent}-v1"
    note = (f"Retains decoded Z/Rotate paths; changes Shutter Duration from 1.5 at 0.7540976 to 0 at event end to remove endpoint path integration using a {ease_percent}% smoothstep blend. "
            "Candidate differs from source shutter endpoint 1.0.")
    for name, value in (("native_curve_candidate_id", candidate_id), ("native_curve_candidate_note", note)):
        prop = props.get(name)
        if prop is None:
            prop = ET.SubElement(element, "property", {"name": name})
        prop.text = value


def apply_zoom_out_spin_counterclockwise_incoming_settle_candidate(
        tree, record: dict, ease_weight: float = 0.65) -> None:
    """Ease the final source rotation segment and taper its incoming shutter.

    Source key times and values stay fixed. The 0.7541-to-1.0 rotation segment
    gets an explicit linear-floor smoothstep Bezier, while shutter duration
    tapers to zero so the last frame is sharp. The earlier rotation segment and
    the Z-distance curve remain unchanged. This is a visual candidate only.
    """
    import json

    apply_zoom_out_spin_counterclockwise_incoming_shutter_taper_candidate(
        tree, record, ease_weight)
    source_id = "{57C53ED1-D794-4D49-9665-47A23F873410}"
    matching = []
    for element in tree.getroot().findall(".//filter"):
        props = {prop.get("name"): prop for prop in element.findall("property")}
        if props.get("native_preset_id") is not None and props["native_preset_id"].text == source_id:
            matching.append((element, props))
    if len(matching) != 1:
        raise ValueError("candidate project must contain exactly one filter for the incoming 10.7 source UUID")
    element, props = matching[0]
    curves_prop = props.get("native_curves")
    if curves_prop is None or not curves_prop.text:
        raise ValueError("candidate filter has no native_curves property")
    curves = json.loads(curves_prop.text)
    rotation = curves.get("rotation") or []
    if len(rotation) != 3 or abs(float(rotation[1][0]) - 0.7540976357699892) > 1e-6:
        raise ValueError("10.7 incoming rotation key positions differ from the reviewed source curve")
    eased = smoothstep_endpoint_bezier_points(-45.0, 0.0, ease_weight)
    start_time, end_time = float(rotation[1][0]), float(rotation[2][0])
    span = end_time - start_time
    rotation[1][4] = start_time + eased[0][4] * span
    rotation[1][5] = eased[0][5]
    rotation[1][6] = eased[0][6]
    rotation[2][2] = start_time + eased[1][2] * span
    rotation[2][3] = eased[1][3]
    curves_prop.text = json.dumps(curves, separators=(",", ":"))
    ease_percent = int(round(ease_weight * 100))
    props["native_curve_candidate_id"].text = (
        f"10.7-ccw-incoming-shutter-taper-rotation-settle-{ease_percent}-v2")
    props["native_curve_candidate_note"].text = (
        f"Preserves decoded Z/Rotate key times and values; eases the final rotation segment with a {ease_percent}% smoothstep blend and tapers Shutter Duration from 1.5 at 0.7540976 to 0 at event end. "
        "Candidate interpolation and shutter endpoint differ from source semantics."
    )


def apply_endpoint_preserving_smoothstep_candidate(tree, ease_weight: float = 0.4) -> None:
    """Ease two-key curves without changing decoded values or shutter controls.

    This narrow pilot is for records whose animated native parameters each
    contain exactly two decoded endpoint keys. It preserves every key value
    and rejects multi-key tracks rather than silently dropping their source
    timing or intermediate values.
    """
    import json

    filters = tree.getroot().findall(".//filter")
    for element in filters:
        curves_prop = element.find("property[@name='native_curves']")
        if curves_prop is None or not curves_prop.text:
            continue
        curves = json.loads(curves_prop.text)
        rebuilt = {}
        for name, points in curves.items():
            if len(points) != 2:
                raise ValueError(f"{name} has {len(points)} keys; endpoint-preserving pilot requires exactly two")
            rebuilt[name] = smoothstep_endpoint_bezier_points(
                float(points[0][1]), float(points[1][1]), ease_weight)
        curves_prop.text = json.dumps(rebuilt, separators=(",", ":"))


def apply_smooth_r_to_l_pair_candidate(tree, record: dict, ease_weight: float = 0.4) -> None:
    """Build the narrowly scoped 1.1 Smooth R-to-L easing trial.

    The outgoing source values are encoded from displaced to neutral, while
    this selected-event reconstruction needs a readable start and a displaced
    outgoing endpoint. The incoming record already has the opposite transform
    endpoints, so they are retained and fitted with a complementary ease-out.
    Its decoded shutter duration ends at one frame, which leaves visible blur
    at the endpoint; the native reconstruction tapers it to zero there.
    Sapphire's original interpolation and shutter timing remain unresolved;
    callers must keep this explicitly a candidate.
    """
    import json

    identities = {
        "{1AD8B510-4D09-4263-BEA1-FA45C59E7594}": "outgoing",
        "{7F0C983A-CA01-48EA-8430-079520B606D5}": "incoming",
    }
    source_id = record.get("source_identifier")
    role = identities.get(source_id)
    if role is None or record.get("event_variant") != role:
        raise ValueError("Smooth R to L easing is limited to its two source identities and roles")

    filters = tree.getroot().findall("./producer/filter")
    components = record.get("components") or []
    expected_chain = ["S_BlurMoCurves"] if role == "outgoing" else ["S_BlurMoCurves", "S_WarpTransform"]
    source_chain = [component.get("vendor_id", "").rsplit(".", 1)[-1].rstrip("}")
                    for component in components]
    if source_chain != expected_chain or len(filters) != len(components):
        raise ValueError("Smooth R to L candidate requires the complete source-ordered native chain")

    def property_node(element, name: str):
        return element.find(f"property[@name='{name}']")

    motion_curves = property_node(filters[0], "native_curves")
    if motion_curves is None or not motion_curves.text:
        raise ValueError("Smooth R to L motion filter has no decoded curves")
    motion = json.loads(motion_curves.text)
    if role == "outgoing":
        source_shift = motion.get("shift_x")
        shutter = property_node(filters[0], "shutter_duration")
        if (not source_shift or len(source_shift) != 2 or shutter is None
                or float(source_shift[0][1]) != -0.5 or float(source_shift[-1][1]) != 0.0):
            raise ValueError("outgoing Smooth R to L source endpoints or shutter do not match the decoded record")
        # Event-role candidate: readable neutral frame, then move left toward
        # the decoded -0.5 endpoint. Open the fitted shutter with the same arc.
        motion["shift_x"] = endpoint_progress_bezier_points(0.0, -0.5, "outgoing", ease_weight)
        motion["shutter_duration"] = endpoint_progress_bezier_points(
            0.0, float(shutter.text), "outgoing", ease_weight)
        property_node(filters[0], "shift_x").text = "0"
        shutter.text = "0"
    else:
        # Preserve every decoded animated endpoint; change only intermediate
        # pacing so the incoming scene eases toward its clean endpoint.
        for component_filter, component in zip(filters, components):
            curves_node = property_node(component_filter, "native_curves")
            if curves_node is None or not curves_node.text:
                raise ValueError("incoming Smooth R to L component has no decoded curves")
            curves = json.loads(curves_node.text)
            kind = component["vendor_id"].rsplit(".", 1)[-1].rstrip("}")
            names = SOURCE_TARGETS.get(kind, {})
            for parameter in component.get("parameters") or []:
                animation = parameter.get("animation")
                if not animation:
                    continue
                target = names.get(parameter["name"])
                points = curves.get(target) if target else None
                if target is None or not points or len(points) != 2:
                    raise ValueError(f"unhandled incoming Smooth R to L animation: {kind}.{parameter['name']}")
                end_value = 0.0 if target == "shutter_duration" else float(points[-1][1])
                curves[target] = endpoint_progress_bezier_points(
                    float(points[0][1]), end_value, "incoming", ease_weight)
                base_value = property_node(component_filter, target)
                if base_value is not None:
                    base_value.text = str(points[0][1])
            curves_node.text = json.dumps(curves, separators=(",", ":"))
        return
    motion_curves.text = json.dumps(motion, separators=(",", ":"))


SOURCE_TARGETS = {
    "S_BlurMoCurves": {
        "Z Dist": "z_distance", "Rotate": "rotation",
        "Shift X": "shift_x", "Shift Y": "shift_y",
        "Shutter Duration": "shutter_duration",
        "Brightness": "brightness",
    },
    "S_Shake": {"Amplitude": "amplitude", "Frequency": "frequency"},
    "S_WarpFishEye": {"Amount": "amount"},
    "S_WarpTransform": {"Scale X": "scale_x", "Scale Y": "scale_y"},
}


def apply_reverse_time_monotone_candidate(tree, record: dict) -> None:
    """Apply the role-time reversal hypothesis to one outgoing fixture only."""
    import json

    if record.get("event_variant") != "outgoing":
        raise ValueError("role-time reversal candidate only supports outgoing records")
    filters = tree.getroot().findall("./producer/filter")
    components = record.get("components") or []
    if len(filters) != len(components):
        raise ValueError("source component count does not match fixture filter count")
    for filter_element, component in zip(filters, components):
        kind = component.get("vendor_id", "").rsplit(".", 1)[-1].rstrip("}")
        target_names = SOURCE_TARGETS.get(kind)
        if target_names is None:
            raise ValueError(f"role-time reversal pilot does not support {kind}")
        curves_property = filter_element.find("property[@name='native_curves']")
        if curves_property is None or not curves_property.text:
            raise ValueError(f"{kind} fixture has no native curve table")
        curves = json.loads(curves_property.text)
        for parameter in component.get("parameters") or []:
            animation = parameter.get("animation")
            if not animation:
                continue
            target = target_names.get(parameter["name"])
            if target is None or target not in curves:
                raise ValueError(f"no native curve for {kind}.{parameter['name']}")
            curves[target] = reverse_event_time_monotone_candidate(animation["points"])
        curves_property.text = json.dumps(curves, separators=(",", ":"))


def apply_vegas_enum_order_candidate(tree, record: dict, zero_hold: bool = False) -> None:
    """Replace fixture linear curves with an inferred source-type candidate.

    This helper is intentionally limited to disposable renders. It raises when
    an animated source control lacks a mapping, keeping a partial chain from
    appearing like a successful reconstruction.
    """
    import json

    filters = tree.getroot().findall("./producer/filter")
    components = record.get("components") or []
    if len(filters) != len(components):
        raise ValueError("source component count does not match fixture filter count")
    for filter_element, component in zip(filters, components):
        animated_parameters = [parameter for parameter in component.get("parameters") or []
                               if parameter.get("animation")]
        if not animated_parameters:
            continue
        kind = component.get("vendor_id", "").rsplit(".", 1)[-1].rstrip("}")
        names = SOURCE_TARGETS.get(kind)
        if names is None:
            raise ValueError(f"source interpolation pilot does not support {kind}")
        curves_prop = filter_element.find("property[@name='native_curves']")
        if curves_prop is None or not curves_prop.text:
            raise ValueError(f"{kind} fixture has no native curve table")
        curves = json.loads(curves_prop.text)
        for parameter in animated_parameters:
            animation = parameter["animation"]
            source_name = parameter["name"]
            target_name = names.get(source_name)
            if target_name is None or target_name not in curves:
                raise ValueError(f"no source interpolation mapping for {kind}.{source_name}")
            converter = vegas_zero_hold_candidate if zero_hold else vegas_enum_order_candidate
            curves[target_name] = converter(animation["points"])
        curves_prop.text = json.dumps(curves, separators=(",", ":"))


def apply_vegas_zero_hold_destination_candidate(tree, record: dict) -> None:
    """Apply the unverified destination-key/zero-hold interpretation to a fixture.

    This remains a disposable-render hypothesis. Keep the component-to-native
    parameter map shared with the source-key candidate so animated shutter
    timing is converted together with the transform path.
    """
    import json

    filters = tree.getroot().findall("./producer/filter")
    components = record.get("components") or []
    if len(filters) != len(components):
        raise ValueError("source component count does not match fixture filter count")
    for filter_element, component in zip(filters, components):
        animated_parameters = [parameter for parameter in component.get("parameters") or []
                               if parameter.get("animation")]
        if not animated_parameters:
            continue
        kind = component.get("vendor_id", "").rsplit(".", 1)[-1].rstrip("}")
        target_names = SOURCE_TARGETS.get(kind)
        if target_names is None:
            raise ValueError(f"incoming-key pilot does not support {kind}")
        curves_property = filter_element.find("property[@name='native_curves']")
        if curves_property is None or not curves_property.text:
            raise ValueError(f"{kind} fixture has no native curve table")
        curves = json.loads(curves_property.text)
        for parameter in animated_parameters:
            animation = parameter["animation"]
            target = target_names.get(parameter["name"])
            if target is None or target not in curves:
                raise ValueError(f"no native curve for {kind}.{parameter['name']}")
            curves[target] = vegas_zero_hold_incoming_key_candidate(animation["points"])
        curves_property.text = json.dumps(curves, separators=(",", ":"))


def apply_curve_policy(tree, policy: str) -> None:
    """Apply a named reconstruction policy to all native curves in a fixture."""
    if policy != "monotone-cubic-equivalent":
        raise ValueError(f"unsupported native curve policy: {policy}")

    import json

    for filter_element in tree.getroot().findall(".//producer/filter"):
        for prop in filter_element.findall("property"):
            if prop.get("name") != "native_curves" or not prop.text:
                continue
            curves = json.loads(prop.text)
            prop.text = json.dumps(
                {name: monotone_bezier_points(points)
                 for name, points in curves.items()},
                separators=(",", ":"))


def apply_zoom_out_10_5_incoming_ease_out_v1(tree, record: dict) -> None:
    """Test a full-event ease-out recovery for the 10.5 incoming Pinch pair.

    The decoded incoming Z-distance is held at 0.5 through progress 0.7541,
    while the supplied visual progression calls for recovery from the first
    incoming frame. The candidate preserves the decoded start/end values,
    distributes Z distance and shutter recovery over the whole event, and
    eases the Pinch amount from -1 to 0. It intentionally replaces the
    intermediate hold; it is a visual reconstruction, not a source-curve
    decode.
    """
    import json

    expected_id = "{B9BD2DB7-A2A8-4C60-BF31-93DFFDF9EF17}"
    expected_name = "10.5 Zoom Out Pinch (2) 15k"
    if (record.get("source_identifier") != expected_id
            or record.get("exact_name") != expected_name
            or record.get("event_variant") != "incoming"):
        raise ValueError("10.5 ease-out recovery is limited to its incoming source identity")

    components = record.get("components") or []
    source_chain = [component.get("vendor_id", "").rsplit(".", 1)[-1].rstrip("}")
                    for component in components]
    if source_chain != ["S_BlurMoCurves", "{C8E20570-4059-4EDF-9CAE-EEF966DF3B19"]:
        raise ValueError("10.5 incoming recovery requires Motion Transform and Pinch/Punch in source order")

    filters = tree.getroot().findall("./producer/filter")
    services = [element.findtext("property[@name='mlt_service']") for element in filters]
    if services != ["kdenlive_motion_curve", "kdenlive_pinch_punch"]:
        raise ValueError("10.5 incoming recovery requires the complete native component chain")

    motion = json.loads(filters[0].findtext("property[@name='native_curves']") or "{}")
    pinch = json.loads(filters[1].findtext("property[@name='native_curves']") or "{}")
    if not all(name in motion and len(motion[name]) >= 2
               for name in ("z_distance", "shutter_duration")):
        raise ValueError("10.5 incoming motion source endpoints are missing")
    if "amount" not in pinch or len(pinch["amount"]) != 2:
        raise ValueError("10.5 incoming Pinch amount endpoints are missing")

    z_start, z_end = float(motion["z_distance"][0][1]), float(motion["z_distance"][-1][1])
    shutter_start = float(motion["shutter_duration"][0][1])
    shutter_end = float(motion["shutter_duration"][-1][1])
    amount_start, amount_end = float(pinch["amount"][0][1]), float(pinch["amount"][-1][1])
    if not (math.isclose(z_start, 0.5) and math.isclose(z_end, 1.0)
            and math.isclose(shutter_start, 1.5) and math.isclose(shutter_end, 1.0)
            and math.isclose(amount_start, -1.0) and math.isclose(amount_end, 0.0)):
        raise ValueError("10.5 incoming source endpoints no longer match the reviewed recovery candidate")

    motion["z_distance"] = cubic_ease_out_endpoint_points(z_start, z_end)
    motion["shutter_duration"] = cubic_ease_out_endpoint_points(shutter_start, shutter_end)
    pinch["amount"] = cubic_ease_out_endpoint_points(amount_start, amount_end)
    filters[0].find("property[@name='native_curves']").text = json.dumps(motion, separators=(",", ":"))
    filters[1].find("property[@name='native_curves']").text = json.dumps(pinch, separators=(",", ":"))


def apply_zoom_out_10_5_outgoing_monotone_cubic_v1(tree, record: dict) -> None:
    """Use the paired candidate's monotone native curves for the 10.5 out row."""
    expected_id = "{C5FCEC32-DB49-47AF-9CDF-1580ED35F114}"
    expected_name = "10.5 Zoom Out Pinch (1) 15k"
    if (record.get("source_identifier") != expected_id
            or record.get("exact_name") != expected_name
            or record.get("event_variant") != "outgoing"):
        raise ValueError("10.5 outgoing monotone curve policy is limited to its source identity")
    apply_curve_policy(tree, "monotone-cubic-equivalent")


def apply_zoom_spin_rsmb_monotone_cubic_v1(tree, record: dict) -> None:
    """Fit decoded Zoom Out CCW/CW Spin curves with native monotone handles.

    The source IDs are restricted to the paired 10.8/10.9 Motion Transform +
    RSMB rows. All decoded key times and values are retained; only native
    interpolation handles are generated. The CPU motion-vector component
    remains a documented reconstruction of proprietary RSMB.
    """
    import json

    identities = {
        "{93B540EF-2897-4212-8355-BF902EB0B43E}": ("10.8 Zoom Out CCW Spin (1) 15k", "outgoing"),
        "{E64E63EC-2395-41F9-985A-78CB5169E7E9}": ("10.8 Zoom Out CCW Spin (2) 15k", "incoming"),
        "{2187A5C0-E3D7-4C41-A5B4-78CD7F0C7A50}": ("10.9 Zoom Out CW Spin (1) 15k", "outgoing"),
    }
    identity = identities.get(record.get("source_identifier"))
    if identity != (record.get("exact_name"), record.get("event_variant")):
        raise ValueError("10.8/10.9 Zoom Out Spin monotone policy is limited to its four source identities")
    chain = [component.get("vendor_id", "").rsplit(".", 1)[-1].rstrip("}")
             for component in record.get("components", [])]
    if chain != ["S_BlurMoCurves", "RSMB"]:
        raise ValueError("10.8/10.9 Zoom Out Spin candidate requires Motion Transform followed by RSMB")
    filters = tree.getroot().findall("./producer/filter")
    services = [element.findtext("property[@name='mlt_service']") for element in filters]
    if services != ["kdenlive_motion_curve", "kdenlive_motion_vector_blur"]:
        raise ValueError("10.8/10.9 Zoom Out Spin candidate requires the complete native Motion→RSMB chain")
    curves = json.loads(filters[0].findtext("property[@name='native_curves']") or "{}")
    if not {"z_distance", "rotation", "shutter_duration", "brightness"}.issubset(curves):
        raise ValueError("10.8/10.9 Zoom Out Spin transform curves changed unexpectedly")
    apply_curve_policy(tree, "monotone-cubic-equivalent")


def apply_zoom_spin_rsmb_incoming_ease_out_v1(tree, record: dict) -> None:
    """Spread the 10.9 incoming zoom, spin, blur, and brightness recovery.

    The source starts its Z-distance and shutter keys at 0.7541 and holds the
    45-degree rotation through that point. Preserve transform and brightness
    endpoints, reconstruct their recovery over the complete event, and taper
    both shutter blur and RSMB amount to zero for an untreated final frame.
    """
    import json
    from xml.etree import ElementTree as ET

    expected_id = "{9C289FCD-6DE1-4720-A57E-7D90E3A2307A}"
    expected_name = "10.9 Zoom Out CW Spin (2) 15k"
    if (record.get("source_identifier") != expected_id
            or record.get("exact_name") != expected_name
            or record.get("event_variant") != "incoming"):
        raise ValueError("10.9 incoming ease-out policy is limited to its source identity")
    chain = [component.get("vendor_id", "").rsplit(".", 1)[-1].rstrip("}")
             for component in record.get("components", [])]
    if chain != ["S_BlurMoCurves", "RSMB"]:
        raise ValueError("10.9 incoming ease-out requires Motion Transform followed by RSMB")
    filters = tree.getroot().findall("./producer/filter")
    services = [element.findtext("property[@name='mlt_service']") for element in filters]
    if services != ["kdenlive_motion_curve", "kdenlive_motion_vector_blur"]:
        raise ValueError("10.9 incoming ease-out requires the complete native Motion→RSMB chain")
    curves = json.loads(filters[0].findtext("property[@name='native_curves']") or "{}")
    decoded_endpoints = {
        "z_distance": (0.5, 1.0),
        "rotation": (45.0, 0.0),
        "shutter_duration": (1.5, 1.0),
        "brightness": (1.25, 1.0),
    }
    if not decoded_endpoints.keys() <= curves.keys():
        raise ValueError("10.9 incoming source transform curves changed unexpectedly")
    candidate_endpoints = dict(decoded_endpoints)
    candidate_endpoints["shutter_duration"] = (1.5, 0.0)
    for name, (start, source_end) in decoded_endpoints.items():
        points = curves[name]
        if (len(points) < 2 or not math.isclose(float(points[0][1]), start, abs_tol=1e-8)
                or not math.isclose(float(points[-1][1]), source_end, abs_tol=1e-8)):
            raise ValueError(f"10.9 incoming {name} source endpoints changed")
        _, end = candidate_endpoints[name]
        curves[name] = cubic_ease_out_endpoint_points(start, end)
    filters[0].find("property[@name='native_curves']").text = json.dumps(curves, separators=(",", ":"))
    rsmb_curves_node = filters[1].find("property[@name='native_curves']")
    if rsmb_curves_node is None:
        rsmb_curves_node = ET.SubElement(filters[1], "property", {"name": "native_curves"})
    rsmb_curves_node.text = json.dumps({
        "blur_envelope": cubic_ease_out_endpoint_points(1.0, 0.0),
    }, separators=(",", ":"))


def apply_spin_11_2_11_3_incoming_recovery_v1(tree, record: dict) -> None:
    """Replace the incoming spin's long hold with a full-event recovery.

    The 11.2 source holds 45 degrees through 75.4% of the event. The 11.3
    source additionally swings through -45 degrees at that point. Both decoded
    tracks end at zero rotation. For this visual-fit policy, keep the incoming
    start/end rotation and peak shutter values, remove the hold/overshoot, and
    ease rotation and shutter blur down over the whole event. The decoded
    intermediate 11.3 key remains in the inventory, but is intentionally not
    serialized into the active native reconstruction because it creates a
    second rotation peak after the cut.
    """
    import json

    identities = {
        "{FE94B468-D68F-47F0-A99C-7F1D094D6279}": "11.2 Spin ClockWise (2) 15k",
        "{9F7C46F0-C4AA-46F0-BB51-A307971D2A19}": "11.3 Spin CounterClockWise (2) 15k",
    }
    expected_name = identities.get(record.get("source_identifier"))
    if (expected_name != record.get("exact_name")
            or record.get("event_variant") != "incoming"):
        raise ValueError("11.2/11.3 spin recovery is limited to the two incoming source identities")
    chain = [component.get("vendor_id", "").rsplit(".", 1)[-1].rstrip("}")
             for component in record.get("components", [])]
    if chain != ["S_BlurMoCurves"]:
        raise ValueError("11.2/11.3 spin recovery requires the single BlurMoCurves source component")
    filters = tree.getroot().findall("./producer/filter")
    if len(filters) != 1 or filters[0].findtext("property[@name='mlt_service']") != "kdenlive_motion_curve":
        raise ValueError("11.2/11.3 spin recovery requires one native Motion Transform and Blur filter")
    curves = json.loads(filters[0].findtext("property[@name='native_curves']") or "{}")
    if not {"rotation", "shutter_duration"} <= curves.keys():
        raise ValueError("11.2/11.3 incoming spin curves are missing rotation or shutter duration")
    rotation = curves["rotation"]
    shutter = curves["shutter_duration"]
    start_rotation = float(rotation[0][1])
    end_rotation = float(rotation[-1][1])
    peak_shutter = max(float(point[1]) for point in shutter)
    if not (math.isclose(start_rotation, 45.0, abs_tol=1e-8)
            and math.isclose(end_rotation, 0.0, abs_tol=1e-8)
            and math.isclose(peak_shutter, 1.5, abs_tol=1e-8)):
        raise ValueError("11.2/11.3 incoming source endpoints or shutter peak changed")
    curves["rotation"] = incoming_full_event_recovery_points(
        [[0.0, start_rotation, 0.0, start_rotation, 0.0, start_rotation, 0],
         [1.0, end_rotation, 1.0, end_rotation, 1.0, end_rotation, 0]],
        ease_weight=0.5)
    curves["shutter_duration"] = incoming_full_event_recovery_points(
        [[0.0, peak_shutter, 0.0, peak_shutter, 0.0, peak_shutter, 0],
         [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0]],
        ease_weight=0.5)
    filters[0].find("property[@name='native_curves']").text = json.dumps(curves, separators=(",", ":"))


def apply_spin_10_6_incoming_eventwide_v1(tree, record: dict) -> None:
    """Spread the decoded 10.6 incoming recovery across the selected event.

    The source keys for zoom and shutter begin at 75.4% of the incoming event,
    leaving almost the whole event static. This native reconstruction preserves
    the decoded first and last values but retimes the three decoded curves to
    the full normalized event using a linear-floor smoothstep. The original
    source key positions remain available in the inventory; this does not claim
    to reproduce Sapphire's unresolved interpolation or timing semantics.
    """
    import json

    expected = ("{8251884A-4379-40BE-BBB4-A30EFC673140}",
                "10.6 Zoom Out Spin ClockWise (2) 15k", "incoming")
    actual = (record.get("source_identifier"), record.get("exact_name"),
              record.get("event_variant"))
    if actual != expected:
        raise ValueError("event-wide zoom/spin recovery is limited to the 10.6 incoming source identity")
    chain = [component.get("vendor_id", "").rsplit(".", 1)[-1].rstrip("}")
             for component in record.get("components", [])]
    if chain != ["S_BlurMoCurves"]:
        raise ValueError("10.6 incoming event-wide recovery requires one BlurMoCurves source component")
    filters = tree.getroot().findall("./producer/filter")
    if (len(filters) != 1
            or filters[0].findtext("property[@name='mlt_service']") != "kdenlive_motion_curve"):
        raise ValueError("10.6 incoming event-wide recovery requires one Motion Transform and Blur filter")
    curves_node = filters[0].find("property[@name='native_curves']")
    if curves_node is None or not curves_node.text:
        raise ValueError("10.6 incoming event-wide recovery has no decoded source curves")
    curves = json.loads(curves_node.text)
    required = ("z_distance", "rotation", "shutter_duration")
    if any(name not in curves or len(curves[name]) < 2 for name in required):
        raise ValueError("10.6 incoming event-wide recovery is missing decoded zoom, rotation, or shutter keys")
    expected_endpoints = {
        "z_distance": (0.5, 1.0),
        "rotation": (45.0, 0.0),
        "shutter_duration": (1.5, 1.0),
    }
    for name in required:
        points = curves[name]
        source_start, source_end = expected_endpoints[name]
        if (not math.isclose(float(points[0][1]), source_start, abs_tol=1e-8)
                or not math.isclose(float(points[-1][1]), source_end, abs_tol=1e-8)):
            raise ValueError(f"10.6 incoming {name} decoded endpoints changed")
        curves[name] = smoothstep_endpoint_bezier_points(
            source_start, source_end, ease_weight=0.65)
    curves_node.text = json.dumps(curves, separators=(",", ":"))
