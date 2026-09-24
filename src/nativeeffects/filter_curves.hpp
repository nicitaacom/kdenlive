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
};

inline double animatedAt(const FilterCurveContext &context, const char *name, double time)
{
    const double position = std::clamp(time, 0.0, 1.0) * std::max(0, context.eventFrames - 1);
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
    return found == context.curves.cend() ? fallback : evaluate(found.value(), time, fallback);
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
    const double base = found == curves.cend() ? fallback : evaluate(found.value(), progress, fallback);
    const QByteArray adjustmentName = key + "_adjust";
    const double adjustment = mlt_properties_get(properties, adjustmentName.constData())
                                  ? mlt_properties_anim_get_double(properties, adjustmentName.constData(), position, animationLength)
                                  : adjustmentDefault;
    return multiply ? base * adjustment : base + adjustment;
}

} // namespace NativeMotion
