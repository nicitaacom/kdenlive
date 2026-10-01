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
    const int position = std::clamp(static_cast<int>(mlt_filter_get_position(filter, frame)), 0, context.eventFrames - 1);
    const double progress = fittedProgress(properties, position, context.eventFrames);
    const auto value = [&](const char *name, bool multiply) {
        return adjustedAt(context, name, progress, multiply ? 1.0 : 0.0, multiply);
    };
    const double centerX = value("center_x", false);
    const double centerY = value("center_y", false);
    const double amount = value("magnify_amount", true);
    const double relX = value("magnify_rel_x", true);
    const double relY = value("magnify_rel_y", true);
    const double radius = value("lens_radius", true);
    const double edgeWidth = value("lens_edge_width", true);
    const double lensWidth = value("lens_rel_width", true);
    const double lensHeight = value("lens_rel_height", true);
    const double rotation = value("lens_rotate", false);
    const double edgeShape = value("lens_edge_shape", false);
    const int keyframePosition = context.filterIn + position;
    const int wrapX = mlt_properties_anim_get_int(properties, "wrap_x", keyframePosition, context.animationLength);
    const int wrapY = mlt_properties_anim_get_int(properties, "wrap_y", keyframePosition, context.animationLength);
    const bool subpixel = mlt_properties_anim_get_int(properties, "subpixel", keyframePosition, context.animationLength) != 0;
    mlt_profile profile = mlt_service_profile(MLT_FILTER_SERVICE(filter));
    const double aspect = profile && profile->sample_aspect_den > 0
                              ? static_cast<double>(profile->sample_aspect_num) / profile->sample_aspect_den : 1.0;
    const size_t bytes = static_cast<size_t>(*width) * *height * 4;
    if (bytes > static_cast<size_t>(std::numeric_limits<int>::max())) {
        return 1;
    }
    auto *output = static_cast<uint8_t *>(mlt_pool_alloc(static_cast<int>(bytes)));
    if (!output) {
        return 1;
    }
    for (int y = 0; y < *height; ++y) {
        for (int x = 0; x < *width; ++x) {
            const Point source = mapMagnify(x, y, *width, *height, centerX, centerY,
                                             amount, relX, relY, radius, edgeWidth,
                                             lensWidth, lensHeight, rotation, edgeShape, aspect);
            const Pixel pixel = std::isfinite(source.x) && std::isfinite(source.y)
                                    ? sampleRgba(*image, *width, *height, source.x, source.y, wrapX, wrapY, subpixel)
                                    : Pixel{};
            auto *destination = output + (static_cast<size_t>(y) * *width + x) * 4;
            destination[3] = static_cast<uint8_t>(std::clamp(std::lround(pixel.a * 255.0), 0l, 255l));
            const auto channel = [&](double premultiplied) {
                return static_cast<uint8_t>(std::clamp(std::lround(pixel.a > 1e-9 ? premultiplied / pixel.a : 0.0), 0l, 255l));
            };
            destination[0] = channel(pixel.r);
            destination[1] = channel(pixel.g);
            destination[2] = channel(pixel.b);
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

extern "C" mlt_filter createNativeMagnify(mlt_profile profile, mlt_service_type type,
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
    mlt_properties_set(properties, "native_event_role", "outgoing");
    mlt_properties_set_int(properties, "native_event_frames", 0);
    mlt_properties_set_double(properties, "native_curve_start", 0);
    mlt_properties_set_double(properties, "native_curve_end", 1);
    for (const char *name : {"magnify_amount", "magnify_rel_x", "magnify_rel_y",
                             "lens_radius", "lens_edge_width", "lens_rel_width", "lens_rel_height",
                             "magnify_amount_adjust", "magnify_rel_x_adjust", "magnify_rel_y_adjust",
                             "lens_radius_adjust", "lens_edge_width_adjust",
                             "lens_rel_width_adjust", "lens_rel_height_adjust"}) {
        mlt_properties_set_double(properties, name, 1);
    }
    mlt_properties_set_double(properties, "center_x", 0.5);
    mlt_properties_set_double(properties, "center_y", 0.5);
    mlt_properties_set_double(properties, "lens_rotate", 0);
    mlt_properties_set_double(properties, "lens_edge_shape", 1);
    for (const char *name : {"center_x_adjust", "center_y_adjust", "lens_rotate_adjust", "lens_edge_shape_adjust"}) {
        mlt_properties_set_double(properties, name, 0);
    }
    mlt_properties_set_int(properties, "wrap_x", 2);
    mlt_properties_set_int(properties, "wrap_y", 2);
    mlt_properties_set_int(properties, "subpixel", 1);
    return filter;
}

extern "C" mlt_properties nativeMagnifyMetadata(mlt_service_type type, const char *id, void *data)
{
    (void)type; (void)data;
    mlt_properties properties = mlt_properties_new();
    mlt_properties_set(properties, "identifier", id);
    mlt_properties_set(properties, "title", "Kdenlive Magnify Warp");
    mlt_properties_set(properties, "description", "Editable elliptical lens warp with reflected edges");
    mlt_properties_set(properties, "version", "0.1");
    return properties;
}
