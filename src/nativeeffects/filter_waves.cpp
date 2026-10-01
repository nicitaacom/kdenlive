/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "filter_curves.hpp"
#include "parallelrows.hpp"

extern "C" {
#include <framework/mlt.h>
#include <framework/mlt_pool.h>
}

#include <algorithm>
#include <cmath>
#include <limits>

using namespace NativeMotion;

namespace {

bool isNoOpFrame(mlt_filter filter, mlt_frame frame)
{
    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    bool curvesValid = false;
    const char *curveString = mlt_properties_get(properties, "native_curves");
    Curves curves = parseCurves(curveString ? QByteArray(curveString) : QByteArray("{}"), &curvesValid);
    if (!curvesValid) {
        return false;
    }

    FilterCurveContext context{curves, properties, 1, static_cast<int>(mlt_filter_get_in(filter)),
                               std::max(1, static_cast<int>(mlt_filter_get_out(filter)) + 1)};
    const int configuredFrames = mlt_properties_get_int(properties, "native_event_frames");
    const int filterFrames = static_cast<int>(mlt_filter_get_length2(filter, frame));
    context.eventFrames = std::max(1, configuredFrames > 0 ? configuredFrames : filterFrames);
    context.curveStart = mlt_properties_get(properties, "native_curve_start")
                             ? mlt_properties_get_double(properties, "native_curve_start") : 0.0;
    context.curveEnd = mlt_properties_get(properties, "native_curve_end")
                           ? mlt_properties_get_double(properties, "native_curve_end") : 1.0;
    const int referenceIn = mlt_properties_get_int(properties, "native_reference_source_in");
    const int localPosition = std::clamp(static_cast<int>(mlt_filter_get_position(filter, frame)) - referenceIn,
                                         0, context.eventFrames - 1);
    const double progress = fittedProgress(properties, localPosition, context.eventFrames);
    const double amplitude = adjustedAt(context, "amplitude", progress, 0.0, false);
    const double zoom = adjustedAt(context, "z_distance", progress, 1.0, true);
    return std::isfinite(amplitude) && std::isfinite(zoom) && std::abs(amplitude) <= 1e-12 &&
           std::abs(zoom - 1.0) <= 1e-12;
}

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
    const int filterFrames = static_cast<int>(mlt_filter_get_length2(filter, frame));
    context.eventFrames = std::max(1, configuredFrames > 0 ? configuredFrames : filterFrames);
    context.curveStart = mlt_properties_get(properties, "native_curve_start")
                             ? mlt_properties_get_double(properties, "native_curve_start") : 0.0;
    context.curveEnd = mlt_properties_get(properties, "native_curve_end")
                           ? mlt_properties_get_double(properties, "native_curve_end") : 1.0;
    const int referenceIn = mlt_properties_get_int(properties, "native_reference_source_in");
    const int localPosition = std::clamp(static_cast<int>(mlt_filter_get_position(filter, frame)) - referenceIn,
                                         0, context.eventFrames - 1);
    const int keyframePosition = context.filterIn + localPosition;
    const double progress = fittedProgress(properties, localPosition, context.eventFrames);

    WaveWarpSettings settings;
    settings.centerX = mlt_properties_get_double(properties, "center_x");
    settings.centerY = mlt_properties_get_double(properties, "center_y");
    settings.amplitude = adjustedAt(context, "amplitude", progress, 0.0, false);
    settings.frequency = adjustedAt(context, "frequency", progress, 0.0, false);
    settings.angleDegrees = adjustedAt(context, "angle", progress, 0.0, false);
    settings.displacementAngleDegrees = adjustedAt(context, "displace_angle", progress, 0.0, false);
    settings.phase = adjustedAt(context, "phase_start", progress, 0.0, false) +
                     adjustedAt(context, "phase_speed", progress, 0.0, false) * progress;
    settings.zoom = adjustedAt(context, "z_distance", progress, 1.0, true);
    mlt_profile profile = mlt_service_profile(MLT_FILTER_SERVICE(filter));
    settings.pixelAspectRatio = profile && profile->sample_aspect_den > 0
                                    ? static_cast<double>(profile->sample_aspect_num) / profile->sample_aspect_den
                                    : 1.0;
    const int wrapX = mlt_properties_anim_get_int(properties, "wrap_x", keyframePosition, context.animationLength);
    const int wrapY = mlt_properties_anim_get_int(properties, "wrap_y", keyframePosition, context.animationLength);
    const bool subpixel = mlt_properties_anim_get_int(properties, "subpixel", keyframePosition, context.animationLength) != 0;

    parallelRows(*height, [&](int y) {
        for (int x = 0; x < *width; ++x) {
            const Point source = mapWaves(x, y, *width, *height, settings);
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
    });

    mlt_frame_set_image(frame, output, static_cast<int>(bytes), mlt_pool_release);
    *image = output;
    *format = mlt_image_rgba;
    return 0;
}

mlt_frame process(mlt_filter filter, mlt_frame frame)
{
    // Preserve the original pixel buffer at neutral endpoints. Re-sampling an
    // identity wave map introduces tiny edge/interpolation changes that make
    // the fitted final frame differ from untreated footage.
    if (isNoOpFrame(filter, frame)) {
        return frame;
    }
    mlt_frame_push_service(frame, filter);
    mlt_frame_push_get_image(frame, getImage);
    return frame;
}

} // namespace

extern "C" mlt_filter createNativeWaves(mlt_profile profile, mlt_service_type type, const char *id, const void *arg)
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
    mlt_properties_set_double(properties, "center_x", 0.5);
    mlt_properties_set_double(properties, "center_y", 0.5);
    mlt_properties_set_double(properties, "amplitude", 0.0);
    mlt_properties_set_double(properties, "frequency", 1.0);
    mlt_properties_set_double(properties, "angle", 0.0);
    mlt_properties_set_double(properties, "displace_angle", 90.0);
    mlt_properties_set_double(properties, "phase_start", 0.0);
    mlt_properties_set_double(properties, "phase_speed", 0.0);
    mlt_properties_set_double(properties, "z_distance", 1.0);
    for (const char *name : {"amplitude_adjust", "frequency_adjust", "angle_adjust", "displace_angle_adjust",
                             "phase_start_adjust", "phase_speed_adjust"}) {
        mlt_properties_set_double(properties, name, 0.0);
    }
    mlt_properties_set_double(properties, "z_distance_adjust", 1.0);
    mlt_properties_set_int(properties, "wrap_x", 2);
    mlt_properties_set_int(properties, "wrap_y", 2);
    mlt_properties_set_int(properties, "subpixel", 1);
    return filter;
}

extern "C" mlt_properties nativeWavesMetadata(mlt_service_type type, const char *id, void *data)
{
    Q_UNUSED(type)
    Q_UNUSED(data)
    mlt_properties properties = mlt_properties_new();
    mlt_properties_set(properties, "identifier", id);
    mlt_properties_set(properties, "title", "Kdenlive Wave Pattern Warp");
    mlt_properties_set(properties, "description", "Native animated sinusoidal image warp with configurable direction and reflected edges");
    mlt_properties_set(properties, "version", "0.1");
    return properties;
}
