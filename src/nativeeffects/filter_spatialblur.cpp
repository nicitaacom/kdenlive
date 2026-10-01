/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "filter_curves.hpp"
#include "spatialblur.hpp"

extern "C" {
#include <framework/mlt.h>
#include <framework/mlt_pool.h>
}

#include <algorithm>
#include <cmath>
#include <limits>

using namespace NativeMotion;

namespace {

int getImage(mlt_frame frame, uint8_t **image, mlt_image_format *format,
             int *width, int *height, int writable)
{
    (void)writable;
    mlt_filter filter = static_cast<mlt_filter>(mlt_frame_pop_service(frame));
    *format = mlt_image_rgba;
    const int error = mlt_frame_get_image(frame, image, format, width, height, 0);
    if (error || !*image || *width < 1 || *height < 1) {
        return error ? error : 1;
    }
    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    bool curvesValid = false;
    const char *curveString = mlt_properties_get(properties, "native_curves");
    FilterCurveContext context{parseCurves(curveString ? QByteArray(curveString) : QByteArray("{}"), &curvesValid),
                               properties, 1, static_cast<int>(mlt_filter_get_in(filter)),
                               std::max(1, static_cast<int>(mlt_filter_get_out(filter)) + 1)};
    if (!curvesValid) {
        return 1;
    }
    const int configuredFrames = mlt_properties_get_int(properties, "native_event_frames");
    context.eventFrames = std::max(1, configuredFrames > 0 ? configuredFrames
                               : static_cast<int>(mlt_filter_get_length2(filter, frame)));
    context.curveStart = mlt_properties_get(properties, "native_curve_start")
                             ? mlt_properties_get_double(properties, "native_curve_start") : 0.0;
    context.curveEnd = mlt_properties_get(properties, "native_curve_end")
                           ? mlt_properties_get_double(properties, "native_curve_end") : 1.0;
    const int localPosition = std::clamp(static_cast<int>(mlt_filter_get_position(filter, frame)), 0, context.eventFrames - 1);
    const double progress = fittedProgress(properties, localPosition, context.eventFrames);
    const auto parameter = [&](const char *name) {
        return adjustedAt(context, name, progress, 0.0, false);
    };
    SpatialBlurSettings settings;
    settings.mode = mlt_properties_get_int(properties, "mode");
    settings.radialType = mlt_properties_get_int(properties, "radial_type");
    settings.amount = parameter("amount");
    settings.angleDegrees = parameter("angle");
    settings.centerX = parameter("center_x");
    settings.centerY = parameter("center_y");
    settings.samples = std::clamp(mlt_properties_anim_get_int(properties, "quality_samples",
                                  context.filterIn + localPosition, context.animationLength), 1, 65);
    mlt_profile profile = mlt_service_profile(MLT_FILTER_SERVICE(filter));
    settings.pixelAspectRatio = profile && profile->sample_aspect_den > 0
                                    ? static_cast<double>(profile->sample_aspect_num) / profile->sample_aspect_den : 1.0;
    const size_t bytes = static_cast<size_t>(*width) * *height * 4;
    if (bytes > static_cast<size_t>(std::numeric_limits<int>::max())) {
        return 1;
    }
    auto *output = static_cast<uint8_t *>(mlt_pool_alloc(static_cast<int>(bytes)));
    if (!output) {
        return 1;
    }
    renderSpatialBlur(*image, output, *width, *height, settings);
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

extern "C" mlt_filter createNativeSpatialBlur(mlt_profile profile, mlt_service_type type,
                                                 const char *id, const void *arg)
{
    (void)profile; (void)type; (void)id; (void)arg;
    mlt_filter filter = mlt_filter_new();
    if (!filter) {
        return nullptr;
    }
    filter->process = process;
    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    mlt_properties_set(properties, "native_curves", "{}");
    mlt_properties_set_int(properties, "mode", 0);
    mlt_properties_set_int(properties, "radial_type", 1);
    mlt_properties_set_double(properties, "amount", 0);
    mlt_properties_set_double(properties, "angle", 0);
    mlt_properties_set_double(properties, "center_x", 0.5);
    mlt_properties_set_double(properties, "center_y", 0.5);
    mlt_properties_set_int(properties, "quality_samples", 17);
    mlt_properties_set_int(properties, "native_event_frames", 0);
    mlt_properties_set_double(properties, "native_curve_start", 0);
    mlt_properties_set_double(properties, "native_curve_end", 1);
    return filter;
}

extern "C" mlt_properties nativeSpatialBlurMetadata(mlt_service_type type, const char *id, void *data)
{
    (void)type; (void)data;
    mlt_properties properties = mlt_properties_new();
    mlt_properties_set(properties, "identifier", id);
    mlt_properties_set(properties, "title", "Kdenlive Spatial Blur");
    mlt_properties_set(properties, "description", "Native deterministic directional and radial blur");
    mlt_properties_set(properties, "version", "0.1");
    return properties;
}
