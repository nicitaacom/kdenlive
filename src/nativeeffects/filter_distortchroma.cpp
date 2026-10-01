/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "distortchroma.hpp"
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
    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    bool valid = false;
    const char *curveString = mlt_properties_get(properties, "native_curves");
    const Curves curves = parseCurves(curveString ? QByteArray(curveString) : QByteArray("{}"), &valid);
    if (!valid) {
        return 1;
    }
    const int configuredFrames = mlt_properties_get_int(properties, "native_event_frames");
    const int eventFrames = std::max(1, configuredFrames > 0 ? configuredFrames : static_cast<int>(mlt_filter_get_length2(filter, frame)));
    const int position = std::clamp(static_cast<int>(mlt_filter_get_position(filter, frame)), 0, eventFrames - 1);
    const int keyframePosition = static_cast<int>(mlt_filter_get_in(filter)) + position;
    const int animationLength = std::max(1, static_cast<int>(mlt_filter_get_out(filter)) + 1);
    const double progress = fittedProgress(properties, position, eventFrames);
    DistortChromaSettings settings;
    settings.amount = frameParameter(properties, curves, "amount", progress, keyframePosition, animationLength, 1.0, true);
    settings.blurLens = mlt_properties_get_double(properties, "blur_lens");
    settings.rotateWarpDegrees = mlt_properties_get_double(properties, "rotate_warp_dir");
    settings.warpRed = mlt_properties_get_double(properties, "warp_red");
    settings.warpBlue = mlt_properties_get_double(properties, "warp_blue");
    settings.amountRelX = mlt_properties_get_double(properties, "amount_rel_x");
    settings.amountRelY = mlt_properties_get_double(properties, "amount_rel_y");
    settings.steps = mlt_properties_get_int(properties, "steps");
    settings.wrapX = mlt_properties_get_int(properties, "wrap_x");
    settings.wrapY = mlt_properties_get_int(properties, "wrap_y");
    settings.subpixel = mlt_properties_get_int(properties, "subpixel") != 0;
    const double values[] = {settings.amount, settings.blurLens, settings.rotateWarpDegrees,
                             settings.warpRed, settings.warpBlue, settings.amountRelX, settings.amountRelY};
    if (!std::all_of(std::begin(values), std::end(values), [](double value) { return std::isfinite(value); }) ||
        settings.blurLens < 0 || settings.amountRelX < 0 || settings.amountRelY < 0 ||
        settings.wrapX < 0 || settings.wrapX > 2 || settings.wrapY < 0 || settings.wrapY > 2) {
        return 1;
    }
    auto *output = static_cast<uint8_t *>(mlt_pool_alloc(static_cast<int>(bytes)));
    if (!output) {
        return 1;
    }
    renderDistortChroma(*image, output, *width, *height, settings);
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

extern "C" mlt_filter createNativeDistortChroma(mlt_profile, mlt_service_type, const char *, const void *)
{
    mlt_filter filter = mlt_filter_new();
    if (!filter) {
        return nullptr;
    }
    filter->process = process;
    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    mlt_properties_set(properties, "native_curves", "{}");
    mlt_properties_set(properties, "native_event_role", "outgoing");
    mlt_properties_set_int(properties, "native_event_frames", 0);
    mlt_properties_set_double(properties, "amount", 0.0);
    mlt_properties_set_double(properties, "amount_adjust", 1.0);
    mlt_properties_set_double(properties, "blur_lens", 0.0);
    mlt_properties_set_double(properties, "rotate_warp_dir", 0.0);
    mlt_properties_set_double(properties, "warp_red", 0.5);
    mlt_properties_set_double(properties, "warp_blue", 1.0);
    mlt_properties_set_double(properties, "amount_rel_x", 1.0);
    mlt_properties_set_double(properties, "amount_rel_y", 1.0);
    mlt_properties_set_int(properties, "steps", 8);
    mlt_properties_set_int(properties, "wrap_x", 2);
    mlt_properties_set_int(properties, "wrap_y", 2);
    mlt_properties_set_int(properties, "subpixel", 1);
    return filter;
}

extern "C" mlt_properties nativeDistortChromaMetadata(mlt_service_type, const char *id, void *)
{
    mlt_properties properties = mlt_properties_new();
    mlt_properties_set(properties, "identifier", id);
    mlt_properties_set(properties, "title", "Kdenlive Lens-Gradient Chroma Distortion");
    mlt_properties_set(properties, "description", "Separates source color samples along a source-luminance gradient");
    mlt_properties_set(properties, "version", "0.1");
    return properties;
}
