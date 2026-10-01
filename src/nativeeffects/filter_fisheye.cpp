/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "filter_curves.hpp"

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
    if (error != 0 || !*image || *width <= 0 || *height <= 0) {
        return error;
    }
    const size_t bytes = static_cast<size_t>(*width) * static_cast<size_t>(*height) * 4;
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
    const Curves curves = parseCurves(curveString ? QByteArray(curveString) : QByteArray("{}"), &valid);
    if (!valid) {
        mlt_pool_release(output);
        return 1;
    }
    const int configuredFrames = mlt_properties_get_int(properties, "native_event_frames");
    const int eventFrames = std::max(1, configuredFrames > 0 ? configuredFrames : static_cast<int>(mlt_filter_get_length2(filter, frame)));
    const int position = std::clamp(static_cast<int>(mlt_filter_get_position(filter, frame)), 0, eventFrames - 1);
    const int keyframePosition = static_cast<int>(mlt_filter_get_in(filter)) + position;
    const int animationLength = std::max(1, static_cast<int>(mlt_filter_get_out(filter)) + 1);
    const double progress = fittedProgress(properties, position, eventFrames);
    const double amount = frameParameter(properties, curves, "amount", progress, keyframePosition, animationLength, 0, false);
    const double centerX = frameParameter(properties, curves, "center_x", progress, keyframePosition, animationLength, 0, false);
    const double centerY = frameParameter(properties, curves, "center_y", progress, keyframePosition, animationLength, 0, false);
    const double zDistance = frameParameter(properties, curves, "z_distance", progress, keyframePosition, animationLength, 1, true);
    const double rotation = frameParameter(properties, curves, "rotation", progress, keyframePosition, animationLength, 0, false);
    const double shiftX = frameParameter(properties, curves, "shift_orig_x", progress, keyframePosition, animationLength, 0, false);
    const double shiftY = frameParameter(properties, curves, "shift_orig_y", progress, keyframePosition, animationLength, 0, false);
    const int wrapX = mlt_properties_anim_get_int(properties, "wrap_x", keyframePosition, animationLength);
    const int wrapY = mlt_properties_anim_get_int(properties, "wrap_y", keyframePosition, animationLength);
    const bool subpixel = mlt_properties_anim_get_int(properties, "subpixel", keyframePosition, animationLength) != 0;
    mlt_profile profile = mlt_service_profile(MLT_FILTER_SERVICE(filter));
    const double aspect = profile && profile->sample_aspect_den > 0
                              ? static_cast<double>(profile->sample_aspect_num) / profile->sample_aspect_den : 1.0;
    for (int y = 0; y < *height; ++y) {
        for (int x = 0; x < *width; ++x) {
            const Point source = mapFisheye(x, y, *width, *height, centerX, centerY,
                                            amount, zDistance, rotation, shiftX, shiftY, aspect);
            const Pixel pixel = std::isfinite(source.x) && std::isfinite(source.y)
                                    ? sampleRgba(*image, *width, *height, source.x, source.y, wrapX, wrapY, subpixel)
                                    : Pixel{};
            uint8_t *destination = output + (static_cast<size_t>(y) * *width + x) * 4;
            const auto channel = [&](double premultiplied) {
                return static_cast<uint8_t>(std::clamp(std::round(pixel.a > 1e-9 ? premultiplied / pixel.a : 0.0), 0.0, 255.0));
            };
            destination[0] = channel(pixel.r);
            destination[1] = channel(pixel.g);
            destination[2] = channel(pixel.b);
            destination[3] = static_cast<uint8_t>(std::clamp(std::round(pixel.a * 255.0), 0.0, 255.0));
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

extern "C" mlt_filter createNativeFisheye(mlt_profile profile, mlt_service_type type, const char *id, const void *arg)
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
    mlt_properties_set_double(properties, "amount", 0);
    mlt_properties_set_double(properties, "center_x", 0.5);
    mlt_properties_set_double(properties, "center_y", 0.5);
    mlt_properties_set_double(properties, "z_distance", 1);
    mlt_properties_set_double(properties, "rotation", 0);
    mlt_properties_set_double(properties, "shift_orig_x", 0);
    mlt_properties_set_double(properties, "shift_orig_y", 0);
    for (const char *name : {"amount_adjust", "center_x_adjust", "center_y_adjust", "rotation_adjust",
                             "shift_orig_x_adjust", "shift_orig_y_adjust"}) {
        mlt_properties_set_double(properties, name, 0);
    }
    mlt_properties_set_double(properties, "z_distance_adjust", 1);
    mlt_properties_set_int(properties, "wrap_x", 2);
    mlt_properties_set_int(properties, "wrap_y", 2);
    mlt_properties_set_int(properties, "subpixel", 1);
    return filter;
}

extern "C" mlt_properties nativeFisheyeMetadata(mlt_service_type type, const char *id, void *data)
{
    Q_UNUSED(type)
    Q_UNUSED(data)
    mlt_properties properties = mlt_properties_new();
    mlt_properties_set(properties, "identifier", id);
    mlt_properties_set(properties, "title", "Kdenlive Radial Fisheye Warp");
    mlt_properties_set(properties, "description", "Native editable radial warp with source-pixel reflection");
    mlt_properties_set(properties, "version", "0.1");
    return properties;
}
