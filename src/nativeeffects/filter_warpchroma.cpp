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

struct Band {
    double zDistance = 1;
    double cosine = 1;
    double sine = 0;
    double shiftX = 0;
    double shiftY = 0;
    double redWeight = 0;
    double greenWeight = 0;
    double blueWeight = 0;
};

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
    const auto value = [&](const char *name, double adjustmentDefault = 0, bool multiply = false) {
        return frameParameter(properties, curves, name, progress, keyframePosition, animationLength, adjustmentDefault, multiply);
    };
    const double centerX = value("center_x");
    const double centerY = value("center_y");
    const double fromZ = value("from_z_distance", 1, true);
    const double toZ = value("to_z_distance", 1, true);
    const double fromRotate = value("from_rotation");
    const double toRotate = value("to_rotation");
    const double fromShiftX = value("from_shift_x");
    const double fromShiftY = value("from_shift_y");
    const double toShiftX = value("to_shift_x");
    const double toShiftY = value("to_shift_y");
    const double amount = value("warp_amount", 1, true);
    const double brightness = value("brightness", 1, true);
    const double values[] = {centerX, centerY, fromZ, toZ, fromRotate, toRotate,
                             fromShiftX, fromShiftY, toShiftX, toShiftY, amount, brightness};
    if (!std::all_of(std::begin(values), std::end(values), [](double v) { return std::isfinite(v); }) ||
        fromZ < 1e-6 || toZ < 1e-6 || amount < 0 || brightness < 0) {
        return 1;
    }
    const int steps = std::clamp(mlt_properties_anim_get_int(properties, "spectrum_steps", keyframePosition,
                                                             animationLength), 3, 100);
    const int wrapX = mlt_properties_anim_get_int(properties, "wrap_x", keyframePosition, animationLength);
    const int wrapY = mlt_properties_anim_get_int(properties, "wrap_y", keyframePosition, animationLength);
    const bool subpixel = mlt_properties_anim_get_int(properties, "subpixel", keyframePosition, animationLength) != 0;
    mlt_profile profile = mlt_service_profile(MLT_FILTER_SERVICE(filter));
    const double aspect = profile && profile->sample_aspect_den > 0
                              ? static_cast<double>(profile->sample_aspect_num) / profile->sample_aspect_den : 1.0;
    QVector<Band> bands;
    bands.reserve(steps);
    double totalRed = 0;
    double totalGreen = 0;
    double totalBlue = 0;
    for (int index = 0; index < steps; ++index) {
        const double spectralPosition = static_cast<double>(index) / (steps - 1);
        const double z = 1 + amount * (fromZ + (toZ - fromZ) * spectralPosition - 1);
        const double degrees = amount * (fromRotate + (toRotate - fromRotate) * spectralPosition);
        const double radians = degrees * (3.14159265358979323846 / 180.0);
        Band band;
        band.zDistance = z;
        band.cosine = std::cos(radians);
        band.sine = std::sin(radians);
        band.shiftX = amount * (fromShiftX + (toShiftX - fromShiftX) * spectralPosition);
        band.shiftY = amount * (fromShiftY + (toShiftY - fromShiftY) * spectralPosition);
        band.redWeight = std::max(0.0, 1 - 2 * spectralPosition);
        band.greenWeight = 1 - std::abs(2 * spectralPosition - 1);
        band.blueWeight = std::max(0.0, 2 * spectralPosition - 1);
        totalRed += band.redWeight;
        totalGreen += band.greenWeight;
        totalBlue += band.blueWeight;
        bands.push_back(band);
    }
    auto *output = static_cast<uint8_t *>(mlt_pool_alloc(static_cast<int>(bytes)));
    if (!output) {
        return 1;
    }
    const double cx = centerX * *width - 0.5;
    const double cy = centerY * *height - 0.5;
    for (int y = 0; y < *height; ++y) {
        for (int x = 0; x < *width; ++x) {
            double red = 0;
            double green = 0;
            double blue = 0;
            double redAlpha = 0;
            double greenAlpha = 0;
            double blueAlpha = 0;
            for (const Band &band : std::as_const(bands)) {
                const double dx = (x - cx - band.shiftX * *width) * aspect;
                const double dy = y - cy - band.shiftY * *height;
                const double sx = cx + (band.cosine * dx + band.sine * dy) * band.zDistance / aspect;
                const double sy = cy + (-band.sine * dx + band.cosine * dy) * band.zDistance;
                const Pixel pixel = sampleRgba(*image, *width, *height, sx, sy, wrapX, wrapY, subpixel);
                red += band.redWeight * pixel.r;
                green += band.greenWeight * pixel.g;
                blue += band.blueWeight * pixel.b;
                redAlpha += band.redWeight * pixel.a;
                greenAlpha += band.greenWeight * pixel.a;
                blueAlpha += band.blueWeight * pixel.a;
            }
            const double alpha = (redAlpha + greenAlpha + blueAlpha) / (totalRed + totalGreen + totalBlue);
            uint8_t *destination = output + (static_cast<size_t>(y) * *width + x) * 4;
            const auto channel = [&](double weighted, double weightedAlpha) {
                return static_cast<uint8_t>(std::clamp(std::round(weightedAlpha > 1e-9
                                                        ? weighted / weightedAlpha * brightness : 0.0), 0.0, 255.0));
            };
            destination[0] = channel(red, redAlpha);
            destination[1] = channel(green, greenAlpha);
            destination[2] = channel(blue, blueAlpha);
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

extern "C" mlt_filter createNativeWarpChroma(mlt_profile profile, mlt_service_type type, const char *id, const void *arg)
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
    for (const char *name : {"center_x", "center_y"}) {
        mlt_properties_set_double(properties, name, 0.5);
    }
    for (const char *name : {"from_z_distance", "to_z_distance", "warp_amount", "brightness",
                             "from_z_distance_adjust", "to_z_distance_adjust", "warp_amount_adjust", "brightness_adjust"}) {
        mlt_properties_set_double(properties, name, 1);
    }
    for (const char *name : {"from_rotation", "to_rotation", "from_shift_x", "from_shift_y",
                             "to_shift_x", "to_shift_y", "center_x_adjust", "center_y_adjust",
                             "from_rotation_adjust", "to_rotation_adjust", "from_shift_x_adjust", "from_shift_y_adjust",
                             "to_shift_x_adjust", "to_shift_y_adjust"}) {
        mlt_properties_set_double(properties, name, 0);
    }
    mlt_properties_set_int(properties, "spectrum_steps", 15);
    mlt_properties_set_int(properties, "wrap_x", 0);
    mlt_properties_set_int(properties, "wrap_y", 0);
    mlt_properties_set_int(properties, "subpixel", 1);
    return filter;
}

extern "C" mlt_properties nativeWarpChromaMetadata(mlt_service_type type, const char *id, void *data)
{
    Q_UNUSED(type)
    Q_UNUSED(data)
    mlt_properties properties = mlt_properties_new();
    mlt_properties_set(properties, "identifier", id);
    mlt_properties_set(properties, "title", "Kdenlive Spectral Chroma Warp");
    mlt_properties_set(properties, "description", "Multi-band spatial transform interpolation between red and blue");
    mlt_properties_set(properties, "version", "0.1");
    return properties;
}
