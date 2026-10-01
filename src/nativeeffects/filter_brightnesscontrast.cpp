/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "brightnesscontrast.hpp"
#include "filter_curves.hpp"

extern "C" {
#include <framework/mlt.h>
#include <framework/mlt_pool.h>
}

#include <algorithm>
#include <cstring>
#include <limits>

using namespace NativeMotion;

namespace {

int getImage(mlt_frame frame, uint8_t **image, mlt_image_format *format, int *width, int *height, int writable)
{
    Q_UNUSED(writable)
    mlt_filter filter = static_cast<mlt_filter>(mlt_frame_pop_service(frame));
    *format = mlt_image_rgba;
    const int error = mlt_frame_get_image(frame, image, format, width, height, 0);
    if (error || !*image || *width < 1 || *height < 1) {
        return error ? error : 1;
    }
    const size_t bytes = static_cast<size_t>(*width) * static_cast<size_t>(*height) * 4;
    if (bytes > static_cast<size_t>(std::numeric_limits<int>::max())) {
        return 1;
    }
    auto *output = static_cast<uint8_t *>(mlt_pool_alloc(static_cast<int>(bytes)));
    if (!output) {
        return 1;
    }
    std::memcpy(output, *image, bytes);
    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    bool curvesValid = false;
    const char *curveString = mlt_properties_get(properties, "native_curves");
    FilterCurveContext context{parseCurves(curveString ? QByteArray(curveString) : QByteArray("{}"), &curvesValid),
                               properties, 1, static_cast<int>(mlt_filter_get_in(filter)),
                               std::max(1, static_cast<int>(mlt_filter_get_out(filter)) + 1)};
    if (!curvesValid) {
        mlt_pool_release(output);
        return 1;
    }
    const int configuredFrames = mlt_properties_get_int(properties, "native_event_frames");
    context.eventFrames = std::max(1, configuredFrames > 0 ? configuredFrames
                               : static_cast<int>(mlt_filter_get_length2(filter, frame)));
    context.curveStart = mlt_properties_get(properties, "native_curve_start")
                             ? mlt_properties_get_double(properties, "native_curve_start") : 0.0;
    context.curveEnd = mlt_properties_get(properties, "native_curve_end")
                           ? mlt_properties_get_double(properties, "native_curve_end") : 1.0;
    const int referenceIn = mlt_properties_get_int(properties, "native_reference_source_in");
    const int localPosition = std::clamp(static_cast<int>(mlt_filter_get_position(filter, frame)) - referenceIn,
                                         0, context.eventFrames - 1);
    const double progress = fittedProgress(properties, localPosition, context.eventFrames);
    const double brightness = adjustedAt(context, "brightness", progress, 0.0, false);
    const double contrast = adjustedAt(context, "contrast", progress, 0.0, false);
    const double center = adjustedAt(context, "contrast_center", progress, 0.0, false);
    applyBrightnessContrast(output, *width, *height, brightness, contrast, center);
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

extern "C" mlt_filter createNativeBrightnessContrast(mlt_profile profile, mlt_service_type type,
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
    mlt_properties_set_double(properties, "brightness", 0.0);
    mlt_properties_set_double(properties, "contrast", 0.0);
    mlt_properties_set_double(properties, "contrast_center", 0.5);
    mlt_properties_set_double(properties, "brightness_adjust", 0.0);
    mlt_properties_set_double(properties, "contrast_adjust", 0.0);
    mlt_properties_set_double(properties, "contrast_center_adjust", 0.0);
    mlt_properties_set_int(properties, "native_event_frames", 0);
    mlt_properties_set_double(properties, "native_curve_start", 0.0);
    mlt_properties_set_double(properties, "native_curve_end", 1.0);
    return filter;
}

extern "C" mlt_properties nativeBrightnessContrastMetadata(mlt_service_type type, const char *id, void *data)
{
    Q_UNUSED(type)
    Q_UNUSED(data)
    mlt_properties properties = mlt_properties_new();
    mlt_properties_set(properties, "identifier", id);
    mlt_properties_set(properties, "title", "Kdenlive Brightness and Contrast");
    mlt_properties_set(properties, "description", "Editable whole-event brightness and contrast curves");
    mlt_properties_set(properties, "version", "0.1");
    return properties;
}
