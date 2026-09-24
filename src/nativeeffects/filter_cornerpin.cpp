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
#include <utility>

using namespace NativeMotion;

namespace {

using Context = FilterCurveContext;

double parameterAt(const Context &context, const char *name, double time)
{
    return adjustedAt(context, name, time, 0, false);
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
    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    bool valid = false;
    const char *curveString = mlt_properties_get(properties, "native_curves");
    Context context{parseCurves(curveString ? QByteArray(curveString) : QByteArray("{}"), &valid), properties, 1,
                    static_cast<int>(mlt_filter_get_in(filter)), std::max(1, static_cast<int>(mlt_filter_get_out(filter)) + 1)};
    if (!valid) {
        return 1;
    }
    const int configuredFrames = mlt_properties_get_int(properties, "native_event_frames");
    context.eventFrames = std::max(1, configuredFrames > 0 ? configuredFrames : static_cast<int>(mlt_filter_get_length2(filter, frame)));
    const int nominalFrames = std::max(1, mlt_properties_get_int(properties, "native_nominal_frames") > 0
                                   ? mlt_properties_get_int(properties, "native_nominal_frames") : context.eventFrames);
    const int position = std::clamp(static_cast<int>(mlt_filter_get_position(filter, frame)), 0, context.eventFrames - 1);
    const int keyframePosition = context.filterIn + position;
    const char *role = mlt_properties_get(properties, "native_event_role");
    const double progress = context.eventFrames > 1 ? static_cast<double>(position) / (context.eventFrames - 1)
                                                    : (role && QByteArray(role) == "incoming" ? 0.0 : 1.0);
    const double shutterAngle = parameterAt(context, "shutter_angle", progress);
    const bool motionBlur = mlt_properties_anim_get_int(properties, "motion_blur_enable", keyframePosition,
                                                         context.animationLength) != 0;
    const double shutter = context.eventFrames == 1 || !motionBlur ? 0.0
                               : std::clamp(shutterAngle, 0.0, 360.0) / 360.0 / std::max(1, nominalFrames - 1);
    const int samples = shutter > 0 ? std::clamp(mlt_properties_anim_get_int(properties, "quality_samples", keyframePosition,
                                                                              context.animationLength), 1, 64) : 1;
    const int wrapX = mlt_properties_anim_get_int(properties, "wrap_x", keyframePosition, context.animationLength);
    const int wrapY = mlt_properties_anim_get_int(properties, "wrap_y", keyframePosition, context.animationLength);
    const bool subpixel = mlt_properties_anim_get_int(properties, "subpixel", keyframePosition, context.animationLength) != 0;
    QVector<CornerPinMapping> mappings;
    mappings.reserve(samples);
    for (int sample = 0; sample < samples; ++sample) {
        const double t = std::clamp(progress + ((sample + 0.5) / samples - 0.5) * shutter, 0.0, 1.0);
        const auto corner = [&](const char *x, const char *y) -> Point {
            return {parameterAt(context, x, t), parameterAt(context, y, t)};
        };
        const CornerPinMapping mapping = makeCornerPin(corner("tl_x", "tl_y"), corner("tr_x", "tr_y"),
                                                        corner("bl_x", "bl_y"), corner("br_x", "br_y"),
                                                        parameterAt(context, "bulge_x", t), parameterAt(context, "bulge_y", t));
        if (!mapping.valid) {
            return 1;
        }
        mappings.push_back(mapping);
    }
    auto *output = static_cast<uint8_t *>(mlt_pool_alloc(static_cast<int>(bytes)));
    if (!output) {
        return 1;
    }
    for (int y = 0; y < *height; ++y) {
        for (int x = 0; x < *width; ++x) {
            Pixel accumulated;
            for (const CornerPinMapping &mapping : std::as_const(mappings)) {
                const Point source = mapCornerPin(mapping, x, y, *width, *height);
                const Pixel pixel = std::isfinite(source.x) && std::isfinite(source.y)
                                        ? sampleRgba(*image, *width, *height, source.x, source.y, wrapX, wrapY, subpixel)
                                        : Pixel{};
                accumulated.r += pixel.r;
                accumulated.g += pixel.g;
                accumulated.b += pixel.b;
                accumulated.a += pixel.a;
            }
            const double alpha = accumulated.a / samples;
            uint8_t *destination = output + (static_cast<size_t>(y) * *width + x) * 4;
            const auto channel = [&](double premultiplied) {
                return static_cast<uint8_t>(std::clamp(std::round(alpha > 1e-9 ? premultiplied / accumulated.a : 0.0), 0.0, 255.0));
            };
            destination[0] = channel(accumulated.r);
            destination[1] = channel(accumulated.g);
            destination[2] = channel(accumulated.b);
            destination[3] = static_cast<uint8_t>(std::clamp(std::round(alpha * 255.0), 0.0, 255.0));
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

extern "C" mlt_filter createNativeCornerPin(mlt_profile profile, mlt_service_type type, const char *id, const void *arg)
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
    for (const char *name : {"tl_x", "bl_x", "tr_y", "br_y", "bulge_x_adjust", "bulge_y_adjust",
                             "shutter_angle_adjust", "tl_x_adjust", "tl_y_adjust", "tr_x_adjust", "tr_y_adjust",
                             "bl_x_adjust", "bl_y_adjust", "br_x_adjust", "br_y_adjust"}) {
        mlt_properties_set_double(properties, name, 0);
    }
    for (const char *name : {"tl_y", "tr_x", "tr_y", "br_x", "bulge_x", "bulge_y"}) {
        mlt_properties_set_double(properties, name, 1);
    }
    mlt_properties_set_double(properties, "bl_y", 0);
    mlt_properties_set_double(properties, "shutter_angle", 180);
    mlt_properties_set_int(properties, "quality_samples", 16);
    mlt_properties_set_int(properties, "motion_blur_enable", 1);
    mlt_properties_set_int(properties, "wrap_x", 0);
    mlt_properties_set_int(properties, "wrap_y", 0);
    mlt_properties_set_int(properties, "subpixel", 1);
    return filter;
}

extern "C" mlt_properties nativeCornerPinMetadata(mlt_service_type type, const char *id, void *data)
{
    Q_UNUSED(type)
    Q_UNUSED(data)
    mlt_properties properties = mlt_properties_new();
    mlt_properties_set(properties, "identifier", id);
    mlt_properties_set(properties, "title", "Kdenlive Perspective and Bulge Warp");
    mlt_properties_set(properties, "description", "Editable four-corner perspective mapping with nonlinear bulge and shutter sampling");
    mlt_properties_set(properties, "version", "0.1");
    return properties;
}
