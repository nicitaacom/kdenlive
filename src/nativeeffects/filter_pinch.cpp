/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "filter_curves.hpp"
#include "pinchwarp.hpp"

extern "C" {
#include <framework/mlt.h>
#include <framework/mlt_pool.h>
}

#include <algorithm>
#include <cmath>
#include <limits>

using namespace NativeMotion;

namespace {

int getImage(mlt_frame frame, uint8_t **image, mlt_image_format *format, int *width, int *height, int writable)
{
    Q_UNUSED(writable)
    mlt_filter filter = static_cast<mlt_filter>(mlt_frame_pop_service(frame));
    *format = mlt_image_rgba;
    const int error = mlt_frame_get_image(frame, image, format, width, height, 0);
    if (error != 0 || !*image || *width < 1 || *height < 1) {
        return error;
    }
    const size_t bytes = static_cast<size_t>(*width) * *height * 4;
    if (bytes > static_cast<size_t>(std::numeric_limits<int>::max())) {
        return 1;
    }
    auto *output = static_cast<uint8_t *>(mlt_pool_alloc(static_cast<int>(bytes)));
    if (!output) {
        return 1;
    }

    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    bool valid = false;
    const char *curveString = mlt_properties_get(properties, "native_curves");
    FilterCurveContext context{parseCurves(curveString ? QByteArray(curveString) : QByteArray("{}"), &valid),
                               properties, 1, static_cast<int>(mlt_filter_get_in(filter)),
                               std::max(1, static_cast<int>(mlt_filter_get_out(filter)) + 1)};
    if (!valid) {
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
    const int position = std::clamp(static_cast<int>(mlt_filter_get_position(filter, frame)), 0, context.eventFrames - 1);
    const int keyframePosition = context.filterIn + position;
    const double progress = fittedProgress(properties, position, context.eventFrames);
    const double amount = adjustedAt(context, "amount", progress, 0.0, false);
    const double centerX = adjustedAt(context, "center_x", progress, 0.0, false);
    const double centerY = adjustedAt(context, "center_y", progress, 0.0, false);
    const double horizontal = adjustedAt(context, "horizontal", progress, 1.0, true);
    const double vertical = adjustedAt(context, "vertical", progress, 1.0, true);
    const bool proportional = mlt_properties_anim_get_int(properties, "proportional", keyframePosition,
                                                          context.animationLength) != 0;
    const int wrapX = mlt_properties_anim_get_int(properties, "wrap_x", keyframePosition, context.animationLength);
    const int wrapY = mlt_properties_anim_get_int(properties, "wrap_y", keyframePosition, context.animationLength);
    const bool subpixel = mlt_properties_anim_get_int(properties, "subpixel", keyframePosition,
                                                       context.animationLength) != 0;
    mlt_profile profile = mlt_service_profile(MLT_FILTER_SERVICE(filter));
    const double aspect = profile && profile->sample_aspect_den > 0
                              ? static_cast<double>(profile->sample_aspect_num) / profile->sample_aspect_den : 1.0;
    PinchLookup lookup;
    makePinchLookup(amount, lookup);
    for (int y = 0; y < *height; ++y) {
        for (int x = 0; x < *width; ++x) {
            const Point source = mapPinchPunch(x, y, *width, *height, centerX, centerY,
                                               horizontal, vertical, proportional, aspect, lookup);
            const Pixel pixel = sampleRgba(*image, *width, *height, source.x, source.y, wrapX, wrapY, subpixel);
            auto *destination = output + (static_cast<size_t>(y) * *width + x) * 4;
            const auto channel = [&](double premultiplied) {
                return static_cast<uint8_t>(std::clamp(std::lround(pixel.a > 1e-9 ? premultiplied / pixel.a : 0.0), 0l, 255l));
            };
            destination[0] = channel(pixel.r);
            destination[1] = channel(pixel.g);
            destination[2] = channel(pixel.b);
            destination[3] = static_cast<uint8_t>(std::clamp(std::lround(pixel.a * 255.0), 0l, 255l));
        }
    }
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

extern "C" mlt_filter createNativePinchPunch(mlt_profile profile, mlt_service_type type,
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
    mlt_properties_set_int(properties, "native_event_frames", 0);
    mlt_properties_set_double(properties, "native_curve_start", 0.0);
    mlt_properties_set_double(properties, "native_curve_end", 1.0);
    mlt_properties_set_double(properties, "amount", 0.0);
    mlt_properties_set_double(properties, "center_x", 0.0);
    mlt_properties_set_double(properties, "center_y", 0.0);
    mlt_properties_set_double(properties, "horizontal", 1.0);
    mlt_properties_set_double(properties, "vertical", 1.0);
    mlt_properties_set_int(properties, "proportional", 1);
    mlt_properties_set_double(properties, "amount_adjust", 0.0);
    mlt_properties_set_double(properties, "center_x_adjust", 0.0);
    mlt_properties_set_double(properties, "center_y_adjust", 0.0);
    mlt_properties_set_double(properties, "horizontal_adjust", 1.0);
    mlt_properties_set_double(properties, "vertical_adjust", 1.0);
    mlt_properties_set_int(properties, "wrap_x", 2);
    mlt_properties_set_int(properties, "wrap_y", 2);
    mlt_properties_set_int(properties, "subpixel", 1);
    return filter;
}

extern "C" mlt_properties nativePinchPunchMetadata(mlt_service_type type, const char *id, void *data)
{
    Q_UNUSED(type)
    Q_UNUSED(data)
    mlt_properties properties = mlt_properties_new();
    mlt_properties_set(properties, "identifier", id);
    mlt_properties_set(properties, "title", "Kdenlive Pinch/Punch Warp");
    mlt_properties_set(properties, "description", "Editable radial Pinch/Punch reconstruction with reflected edges");
    mlt_properties_set(properties, "version", "0.1");
    return properties;
}
