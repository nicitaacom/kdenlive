/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include "motioncurve.hpp"

extern "C" {
#include <framework/mlt.h>
}

#include <algorithm>
#include <cmath>

namespace NativeMotion {

struct FilterCurveContext {
    Curves curves;
    mlt_properties properties = nullptr;
    int eventFrames = 1;
    int filterIn = 0;
    int animationLength = 1;
    double curveStart = 0.0;
    double curveEnd = 1.0;
};

inline double fittedProgress(mlt_properties properties, int position, int eventFrames)
{
    const char *role = mlt_properties_get(properties, "native_event_role");
    // A one-frame event still touches a cut at one specific side: outgoing
    // variants land on the end of their curve; incoming variants begin at the
    // start of theirs. Multi-frame events include both endpoints.
    const double local = eventFrames > 1 ? std::clamp(static_cast<double>(position) / (eventFrames - 1), 0.0, 1.0)
                                         : (role && QByteArray(role) == "incoming" ? 0.0 : 1.0);
    const double start = mlt_properties_get(properties, "native_curve_start")
                             ? mlt_properties_get_double(properties, "native_curve_start") : 0.0;
    const double end = mlt_properties_get(properties, "native_curve_end")
                           ? mlt_properties_get_double(properties, "native_curve_end") : 1.0;
    return std::clamp(start + (end - start) * local, 0.0, 1.0);
}

inline double animatedAt(const FilterCurveContext &context, const char *name, double time)
{
    const double span = context.curveEnd - context.curveStart;
    const double local = std::abs(span) > 1e-12 ? (time - context.curveStart) / span : 0.0;
    const int lastFrame = std::max(0, context.eventFrames - 1);
    const double position = local * lastFrame;
    if (lastFrame > 0 && position < 0.0) {
        // A split does not end the original shutter interval. Continue the
        // editable curve's edge slope for samples just across the cut.
        const double first = mlt_properties_anim_get_double(context.properties, name, context.filterIn, context.animationLength);
        const double second = mlt_properties_anim_get_double(context.properties, name, context.filterIn + 1, context.animationLength);
        return first + position * (second - first);
    }
    if (lastFrame > 0 && position > lastFrame) {
        const double previous = mlt_properties_anim_get_double(context.properties, name, context.filterIn + lastFrame - 1, context.animationLength);
        const double last = mlt_properties_anim_get_double(context.properties, name, context.filterIn + lastFrame, context.animationLength);
        return last + (position - lastFrame) * (last - previous);
    }
    const int lower = context.filterIn + static_cast<int>(std::floor(position));
    const int upper = std::min(context.filterIn + context.eventFrames - 1, lower + 1);
    const double fraction = position - std::floor(position);
    const double first = mlt_properties_anim_get_double(context.properties, name, lower, context.animationLength);
    const double second = mlt_properties_anim_get_double(context.properties, name, upper, context.animationLength);
    return first + (second - first) * fraction;
}

inline double sourceAt(const FilterCurveContext &context, const char *name, double time)
{
    const double fallback = animatedAt(context, name, time);
    const auto found = context.curves.constFind(QByteArray(name));
    return found == context.curves.cend()
               ? fallback
               : evaluateEventCurve(found.value(), time, fallback, context.curveStart, context.curveEnd);
}

inline double adjustedAt(const FilterCurveContext &context, const char *name, double time,
                         double adjustmentDefault, bool multiply)
{
    const QByteArray adjustmentName = QByteArray(name) + "_adjust";
    const double adjustment = mlt_properties_get(context.properties, adjustmentName.constData())
                                  ? animatedAt(context, adjustmentName.constData(), time) : adjustmentDefault;
    const double base = sourceAt(context, name, time);
    return multiply ? base * adjustment : base + adjustment;
}

inline double frameParameter(mlt_properties properties, const Curves &curves, const char *name,
                             double progress, int position, int animationLength,
                             double adjustmentDefault, bool multiply)
{
    const QByteArray key(name);
    const double fallback = mlt_properties_anim_get_double(properties, name, position, animationLength);
    const auto found = curves.constFind(key);
    const double eventStart = mlt_properties_get(properties, "native_curve_start")
                                  ? mlt_properties_get_double(properties, "native_curve_start") : 0.0;
    const double eventEnd = mlt_properties_get(properties, "native_curve_end")
                                ? mlt_properties_get_double(properties, "native_curve_end") : 1.0;
    const double base = found == curves.cend()
                            ? fallback
                            : evaluateEventCurve(found.value(), progress, fallback, eventStart, eventEnd);
    const QByteArray adjustmentName = key + "_adjust";
    const double adjustment = mlt_properties_get(properties, adjustmentName.constData())
                                  ? mlt_properties_anim_get_double(properties, adjustmentName.constData(), position, animationLength)
                                  : adjustmentDefault;
    return multiply ? base * adjustment : base + adjustment;
}

} // namespace NativeMotion
