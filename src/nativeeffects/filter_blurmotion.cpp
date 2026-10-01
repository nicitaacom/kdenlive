/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "filter_curves.hpp"
#include "spatialtransformblur.hpp"

extern "C" {
#include <framework/mlt.h>
#include <framework/mlt_pool.h>
}

#include <algorithm>
#include <limits>

using namespace NativeMotion;

namespace {

int getImage(mlt_frame frame, uint8_t **image, mlt_image_format *format,
             int *width, int *height, int writable)
{
    Q_UNUSED(writable)
    mlt_filter filter = static_cast<mlt_filter>(mlt_frame_pop_service(frame));
    *format = mlt_image_rgba;
    const int error = mlt_frame_get_image(frame, image, format, width, height, 0);
    if (error || !*image || *width < 1 || *height < 1) {
        return error ? error : 1;
    }
    const size_t bytes = static_cast<size_t>(*width) * *height * 4;
    if (bytes > static_cast<size_t>(std::numeric_limits<int>::max())) {
        return 1;
    }

    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    bool valid = false;
    const char *curveString = mlt_properties_get(properties, "native_curves");
    FilterCurveContext context{parseCurves(curveString ? QByteArray(curveString) : QByteArray("{}"), &valid),
                               properties, 1, static_cast<int>(mlt_filter_get_in(filter)),
                               std::max(1, static_cast<int>(mlt_filter_get_out(filter)) + 1)};
    if (!valid) {
        return 1;
    }
    const int configuredFrames = mlt_properties_get_int(properties, "native_event_frames");
    context.eventFrames = std::max(1, configuredFrames > 0 ? configuredFrames
                               : static_cast<int>(mlt_filter_get_length2(filter, frame)));
    context.curveStart = mlt_properties_get(properties, "native_curve_start")
                             ? mlt_properties_get_double(properties, "native_curve_start") : 0.0;
    context.curveEnd = mlt_properties_get(properties, "native_curve_end")
                           ? mlt_properties_get_double(properties, "native_curve_end") : 1.0;
    const int localPosition = std::clamp(static_cast<int>(mlt_filter_get_position(filter, frame)),
                                         0, context.eventFrames - 1);
    const double progress = fittedProgress(properties, localPosition, context.eventFrames);
    const auto parameter = [&](const char *name, double fallback, bool multiply = false) {
        return adjustedAt(context, name, progress, fallback, multiply);
    };

    BlurMotionSettings settings;
    settings.from.zDistance = parameter("from_z_dist", 1.0, true);
    settings.from.rotateDegrees = parameter("from_rotate", 0.0);
    settings.from.shiftX = parameter("from_shift_x", 0.0);
    settings.from.shiftY = parameter("from_shift_y", 0.0);
    settings.to.zDistance = parameter("to_z_dist", 1.0, true);
    settings.to.rotateDegrees = parameter("to_rotate", 0.0);
    settings.to.shiftX = parameter("to_shift_x", 0.0);
    settings.to.shiftY = parameter("to_shift_y", 0.0);
    settings.centerX = parameter("center_x", 0.5);
    settings.centerY = parameter("center_y", 0.5);
    settings.brightness = parameter("brightness", 1.0, true);
    settings.exposureBias = parameter("exposure_bias", 0.5);
    const int animationPosition = context.filterIn + localPosition;
    settings.samples = std::clamp(mlt_properties_anim_get_int(properties, "quality_samples",
                                  animationPosition, context.animationLength), 2, 65);
    settings.wrapX = mlt_properties_anim_get_int(properties, "wrap_x", animationPosition, context.animationLength);
    settings.wrapY = mlt_properties_anim_get_int(properties, "wrap_y", animationPosition, context.animationLength);
    settings.subpixel = mlt_properties_anim_get_int(properties, "subpixel", animationPosition,
                                                     context.animationLength) != 0;
    mlt_profile profile = mlt_service_profile(MLT_FILTER_SERVICE(filter));
    settings.pixelAspectRatio = profile && profile->sample_aspect_den > 0
                                    ? static_cast<double>(profile->sample_aspect_num) / profile->sample_aspect_den
                                    : 1.0;

    auto *output = static_cast<uint8_t *>(mlt_pool_alloc(static_cast<int>(bytes)));
    if (!output) {
        return 1;
    }
    renderBlurMotion(*image, output, *width, *height, settings);
    mlt_frame_set_image(frame, output, static_cast<int>(bytes), mlt_pool_release);
    *image = output;
    *format = mlt_image_rgba;
    return 0;
}

mlt_frame process(mlt_filter filter, mlt_frame frame)
{
    mlt_frame_push_service(frame, filter);
    mlt_frame_push_get_image(frame, getImage);
    return frame;
}

} // namespace

extern "C" mlt_filter createNativeBlurMotion(mlt_profile profile, mlt_service_type type,
                                               const char *id, const void *arg)
{
    Q_UNUSED(profile)
    Q_UNUSED(type)
    Q_UNUSED(id)
    Q_UNUSED(arg)
    mlt_filter filter = mlt_filter_new();
    if (!filter) {
        return nullptr;
    }
    filter->process = process;
    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    mlt_properties_set(properties, "native_curves", "{}");
    mlt_properties_set(properties, "native_event_role", "outgoing");
    mlt_properties_set_int(properties, "native_nominal_frames", 0);
    mlt_properties_set_int(properties, "native_event_frames", 0);
    mlt_properties_set_double(properties, "native_curve_start", 0.0);
    mlt_properties_set_double(properties, "native_curve_end", 1.0);
    for (const char *name : {"from_z_dist", "to_z_dist", "brightness"}) {
        mlt_properties_set_double(properties, name, 1.0);
        QByteArray adjustment = QByteArray(name) + "_adjust";
        mlt_properties_set_double(properties, adjustment.constData(), 1.0);
    }
    for (const char *name : {"from_rotate", "from_shift_x", "from_shift_y", "to_rotate", "to_shift_x", "to_shift_y"}) {
        mlt_properties_set_double(properties, name, 0.0);
        QByteArray adjustment = QByteArray(name) + "_adjust";
        mlt_properties_set_double(properties, adjustment.constData(), 0.0);
    }
    mlt_properties_set_double(properties, "center_x", 0.5);
    mlt_properties_set_double(properties, "center_y", 0.5);
    mlt_properties_set_double(properties, "center_x_adjust", 0.0);
    mlt_properties_set_double(properties, "center_y_adjust", 0.0);
    mlt_properties_set_double(properties, "exposure_bias", 0.5);
    mlt_properties_set_double(properties, "exposure_bias_adjust", 0.0);
    mlt_properties_set_int(properties, "quality_samples", 17);
    mlt_properties_set_int(properties, "wrap_x", 2);
    mlt_properties_set_int(properties, "wrap_y", 2);
    mlt_properties_set_int(properties, "subpixel", 1);
    return filter;
}

extern "C" mlt_properties nativeBlurMotionMetadata(mlt_service_type type, const char *id, void *data)
{
    Q_UNUSED(type)
    Q_UNUSED(data)
    mlt_properties properties = mlt_properties_new();
    mlt_properties_set(properties, "identifier", id);
    mlt_properties_set(properties, "title", "Kdenlive Transform Path Blur");
    mlt_properties_set(properties, "description", "Deterministic blur integrated over source-derived spatial transform endpoints");
    mlt_properties_set(properties, "version", "0.1");
    return properties;
}
