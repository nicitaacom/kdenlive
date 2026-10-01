/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include <mlt++/MltAnimation.h>
#include <mlt++/MltProperties.h>

#include <QString>
#include <algorithm>
#include <cmath>
#include <cstdlib>

namespace NativePresetAnimation {

// Template keyframes are stored in nominal-event-local frame coordinates.
// Refit them to the selected event's inclusive [0, D-1] interval and then
// shift them into the attached MLT filter's coordinate space.
inline bool fitScalarAnimation(const QString &serialized, int nominalFrames, int eventFrames, int eventIn,
                               bool outgoing, QString *result)
{
    if (!result || nominalFrames < 1 || eventFrames < 1 || serialized.isEmpty()) {
        return false;
    }
    Mlt::Properties source;
    source.set("value", serialized.toUtf8().constData());
    (void)source.anim_get_double("value", 0, nominalFrames);
    Mlt::Animation sourceKeys = source.get_animation("value");
    if (!sourceKeys.is_valid() || sourceKeys.key_count() < 1) {
        return false;
    }

    const int sourceLast = std::max(0, nominalFrames - 1);
    const int eventLast = std::max(0, eventFrames - 1);
    const int animationLength = eventIn + eventFrames;
    const auto valueAt = [&](int frame) {
        return source.anim_get_double("value", std::clamp(frame, 0, sourceLast), nominalFrames);
    };
    Mlt::Properties fitted;
    if (eventFrames == 1) {
        // The outgoing role touches its end key at the cut; incoming touches
        // its start key. This avoids division by zero and preserves the role.
        const double endpoint = valueAt(outgoing ? sourceLast : 0);
        const mlt_keyframe_type type = sourceKeys.key_get_type(outgoing ? sourceKeys.key_count() - 1 : 0);
        fitted.anim_set("value", endpoint, eventIn, animationLength, type);
    } else {
        fitted.anim_set("value", valueAt(0), eventIn, animationLength, sourceKeys.key_get_type(0));
        for (int index = 0; index < sourceKeys.key_count(); ++index) {
            const int sourceFrame = sourceKeys.key_get_frame(index);
            const double normalized = sourceLast > 0
                                          ? std::clamp(static_cast<double>(sourceFrame) / sourceLast, 0.0, 1.0)
                                          : 0.0;
            const int eventFrame = eventIn + static_cast<int>(std::lround(normalized * eventLast));
            fitted.anim_set("value", valueAt(sourceFrame), eventFrame, animationLength, sourceKeys.key_get_type(index));
        }
        fitted.anim_set("value", valueAt(sourceLast), eventIn + eventLast, animationLength,
                        sourceKeys.key_get_type(sourceKeys.key_count() - 1));
    }
    Mlt::Animation fittedKeys = fitted.get_animation("value");
    if (!fittedKeys.is_valid() || fittedKeys.key_count() < 1) {
        return false;
    }
    char *encoded = fittedKeys.serialize_cut();
    if (!encoded) {
        return false;
    }
    *result = QString::fromUtf8(encoded);
    free(encoded);
    return !result->isEmpty();
}

} // namespace NativePresetAnimation
