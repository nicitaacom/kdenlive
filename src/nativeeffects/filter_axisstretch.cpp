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
    const double scaleX = frameParameter(properties, curves, "scale_x", progress, keyframePosition, animationLength, 1, true);
    const double scaleY = frameParameter(properties, curves, "scale_y", progress, keyframePosition, animationLength, 1, true);
    const double shiftX = frameParameter(properties, curves, "shift_x", progress, keyframePosition, animationLength, 0, false);
    const double shiftY = frameParameter(properties, curves, "shift_y", progress, keyframePosition, animationLength, 0, false);
    const double zDistance = frameParameter(properties, curves, "z_distance", progress, keyframePosition, animationLength, 1, true);
    const int wrapX = mlt_properties_anim_get_int(properties, "wrap_x", keyframePosition, animationLength);
    const int wrapY = mlt_properties_anim_get_int(properties, "wrap_y", keyframePosition, animationLength);
    const bool subpixel = mlt_properties_anim_get_int(properties, "subpixel", keyframePosition, animationLength) != 0;
    if (!std::isfinite(scaleX) || !std::isfinite(scaleY) || !std::isfinite(shiftX) || !std::isfinite(shiftY) ||
        !std::isfinite(zDistance) || std::abs(scaleX) < 1e-6 || std::abs(scaleY) < 1e-6 || zDistance < 1e-6) {
        mlt_pool_release(output);
        return 1;
    }
    // Preserve the original frame exactly at an identity endpoint. Sampling
    // through the generic bilinear path needlessly changes a few pixel values
    // even when the transform is neutral, leaving a faint residual effect.
    constexpr double epsilon = 1e-10;
    if (std::abs(scaleX - 1.0) <= epsilon && std::abs(scaleY - 1.0) <= epsilon &&
        std::abs(zDistance - 1.0) <= epsilon && std::abs(shiftX) <= epsilon && std::abs(shiftY) <= epsilon) {
        mlt_pool_release(output);
        return 0;
    }
    for (int y = 0; y < *height; ++y) {
        for (int x = 0; x < *width; ++x) {
            const Point source = mapAxisStretch(x, y, *width, *height, scaleX, scaleY, shiftX, shiftY, zDistance);
            const Pixel pixel = sampleRgba(*image, *width, *height, source.x, source.y, wrapX, wrapY, subpixel);
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

extern "C" mlt_filter createNativeAxisStretch(mlt_profile profile, mlt_service_type type, const char *id, const void *arg)
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
    for (const char *name : {"scale_x", "scale_y", "z_distance", "scale_x_adjust", "scale_y_adjust", "z_distance_adjust"}) {
        mlt_properties_set_double(properties, name, 1);
    }
    for (const char *name : {"shift_x", "shift_y", "shift_x_adjust", "shift_y_adjust"}) {
        mlt_properties_set_double(properties, name, 0);
    }
    mlt_properties_set_int(properties, "wrap_x", 0);
    mlt_properties_set_int(properties, "wrap_y", 0);
    mlt_properties_set_int(properties, "subpixel", 1);
    return filter;
}

extern "C" mlt_properties nativeAxisStretchMetadata(mlt_service_type type, const char *id, void *data)
{
    Q_UNUSED(type)
    Q_UNUSED(data)
    mlt_properties properties = mlt_properties_new();
    mlt_properties_set(properties, "identifier", id);
    mlt_properties_set(properties, "title", "Kdenlive Axis Stretch Warp");
    mlt_properties_set(properties, "description", "Independent horizontal and vertical scaling with source-pixel reflection");
    mlt_properties_set(properties, "version", "0.1");
    return properties;
}
