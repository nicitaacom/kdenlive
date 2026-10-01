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
#include <cstring>
#include <limits>

using namespace NativeMotion;

namespace {

using CurveContext = FilterCurveContext;

double parameterAt(const CurveContext &context, const char *name, double time)
{
    const QByteArray key(name);
    const bool multiply = key == "z_distance" || key == "scale_x" || key == "scale_y" || key == "brightness" ||
                          key == "shutter_gain" || key == "shutter_envelope";
    return adjustedAt(context, name, time, multiply ? 1 : 0, multiply);
}

Transform transformAt(double time, void *opaque)
{
    const auto &context = *static_cast<CurveContext *>(opaque);
    Transform transform;
    transform.centerX = parameterAt(context, "center_x", time);
    transform.centerY = parameterAt(context, "center_y", time);
    transform.shiftX = parameterAt(context, "shift_x", time);
    transform.shiftY = parameterAt(context, "shift_y", time);
    transform.scaleX = parameterAt(context, "scale_x", time);
    transform.scaleY = parameterAt(context, "scale_y", time);
    transform.zDistance = parameterAt(context, "z_distance", time);
    transform.rotateDegrees = parameterAt(context, "rotation", time);
    return transform;
}

bool isIdentityFrame(mlt_filter filter, mlt_frame frame)
{
    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    const int configuredFrames = mlt_properties_get_int(properties, "native_event_frames");
    const int filterFrames = static_cast<int>(mlt_filter_get_length2(filter, frame));
    const int eventFrames = std::max(1, configuredFrames > 0 ? configuredFrames : filterFrames);
    const int localPosition = std::clamp(
        static_cast<int>(mlt_filter_get_position(filter, frame)) - mlt_properties_get_int(properties, "native_reference_source_in"),
        0, eventFrames - 1);
    const int filterIn = static_cast<int>(mlt_filter_get_in(filter));
    const int animationLength = std::max(1, static_cast<int>(mlt_filter_get_out(filter)) + 1);
    bool curvesValid = false;
    const char *curveString = mlt_properties_get(properties, "native_curves");
    const Curves curves = parseCurves(curveString ? QByteArray(curveString) : QByteArray("{}"), &curvesValid);
    if (!curvesValid) {
        return false;
    }

    CurveContext context{curves, properties, eventFrames, filterIn, animationLength,
                         mlt_properties_get(properties, "native_curve_start")
                             ? mlt_properties_get_double(properties, "native_curve_start") : 0.0,
                         mlt_properties_get(properties, "native_curve_end")
                             ? mlt_properties_get_double(properties, "native_curve_end") : 1.0};
    const double progress = fittedProgress(properties, localPosition, eventFrames);
    const Transform transform = transformAt(progress, &context);
    const int nominalFrames = std::max(1, mlt_properties_get_int(properties, "native_nominal_frames") > 0
                                                ? mlt_properties_get_int(properties, "native_nominal_frames") : eventFrames);
    const double shutterFrames = fittedShutterFrames(parameterAt(context, "shutter_duration", progress),
                                                      parameterAt(context, "shutter_gain", progress),
                                                      parameterAt(context, "shutter_envelope", progress),
                                                      eventFrames, nominalFrames);
    const double brightness = parameterAt(context, "brightness", progress);
    constexpr double epsilon = 1e-10;
    return std::abs(transform.shiftX) <= epsilon && std::abs(transform.shiftY) <= epsilon &&
           std::abs(transform.scaleX - 1.0) <= epsilon && std::abs(transform.scaleY - 1.0) <= epsilon &&
           std::abs(transform.zDistance - 1.0) <= epsilon && std::abs(transform.rotateDegrees) <= epsilon &&
           std::abs(shutterFrames) <= epsilon && std::abs(brightness - 1.0) <= epsilon;
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
    CurveContext context{parseCurves(curveString ? QByteArray(curveString) : QByteArray("{}"), &curvesValid), properties, 1,
                         static_cast<int>(mlt_filter_get_in(filter)), std::max(1, static_cast<int>(mlt_filter_get_out(filter)) + 1)};
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
    const int configuredNominalFrames = mlt_properties_get_int(properties, "native_nominal_frames");
    const int nominalFrames = configuredNominalFrames > 0 ? configuredNominalFrames : context.eventFrames;
    const int localPosition = std::clamp(
        static_cast<int>(mlt_filter_get_position(filter, frame)) - mlt_properties_get_int(properties, "native_reference_source_in"),
        0, context.eventFrames - 1);
    const int keyframePosition = context.filterIn + localPosition;
    const double progress = fittedProgress(properties, localPosition, context.eventFrames);
    SampleSettings settings;
    const double sourceSpan = std::max(1, nominalFrames - 1);
    const double eventSpan = std::max(1, context.eventFrames - 1);
    settings.shutterFrames = fittedShutterFrames(parameterAt(context, "shutter_duration", progress),
                                                  parameterAt(context, "shutter_gain", progress),
                                                  parameterAt(context, "shutter_envelope", progress),
                                                  context.eventFrames, nominalFrames);
    settings.shutterShiftFrames = context.eventFrames == 1 ? 0.0 : parameterAt(context, "shutter_shift", progress) * eventSpan / sourceSpan;
    settings.exposureBias = parameterAt(context, "exposure_bias", progress);
    settings.brightness = parameterAt(context, "brightness", progress);
    settings.samples = std::clamp(mlt_properties_anim_get_int(properties, "quality_samples", keyframePosition, context.animationLength), 1, 64);
    settings.wrapX = mlt_properties_anim_get_int(properties, "wrap_x", keyframePosition, context.animationLength);
    settings.wrapY = mlt_properties_anim_get_int(properties, "wrap_y", keyframePosition, context.animationLength);
    settings.subpixel = mlt_properties_anim_get_int(properties, "subpixel", keyframePosition, context.animationLength) != 0;
    mlt_profile profile = mlt_service_profile(MLT_FILTER_SERVICE(filter));
    settings.pixelAspectRatio = profile && profile->sample_aspect_den > 0
                                    ? static_cast<double>(profile->sample_aspect_num) / profile->sample_aspect_den
                                    : 1.0;
    renderRgba(*image, output, *width, *height, progress, eventSpan, settings, transformAt, &context);
    mlt_frame_set_image(frame, output, static_cast<int>(bytes), mlt_pool_release);
    *image = output;
    *format = mlt_image_rgba;
    return 0;
}

mlt_frame process(mlt_filter filter, mlt_frame frame)
{
    // Later native effects can evaluate this exact editable transform on
    // neighboring source frames. The pointer is valid for this frame only.
    mlt_properties_set_data(MLT_FRAME_PROPERTIES(frame), "_native_upstream_motion_filter", filter, 0, nullptr, nullptr);
    if (isIdentityFrame(filter, frame)) {
        return frame;
    }
    mlt_frame_push_service(frame, filter);
    mlt_frame_push_get_image(frame, getImage);
    return frame;
}

mlt_filter createMotionCurve(mlt_profile profile, mlt_service_type type, const char *id, const void *arg)
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
    mlt_properties_set_double(properties, "shift_x", 0.0);
    mlt_properties_set_double(properties, "shift_y", 0.0);
    mlt_properties_set_double(properties, "scale_x", 1.0);
    mlt_properties_set_double(properties, "scale_y", 1.0);
    mlt_properties_set_double(properties, "z_distance", 1.0);
    mlt_properties_set_double(properties, "rotation", 0.0);
    mlt_properties_set_double(properties, "shutter_duration", 1.0);
    mlt_properties_set_double(properties, "shutter_gain", 1.0);
    mlt_properties_set_double(properties, "shutter_envelope", 1.0);
    mlt_properties_set_double(properties, "shutter_gain_adjust", 1.0);
    mlt_properties_set_double(properties, "shutter_envelope_adjust", 1.0);
    mlt_properties_set_double(properties, "shutter_shift", 0.0);
    mlt_properties_set_double(properties, "exposure_bias", 0.5);
    mlt_properties_set_double(properties, "brightness", 1.0);
    for (const char *name : {"center_x_adjust", "center_y_adjust", "shift_x_adjust", "shift_y_adjust",
                             "rotation_adjust", "shutter_duration_adjust", "shutter_shift_adjust",
                             "exposure_bias_adjust"}) {
        mlt_properties_set_double(properties, name, 0.0);
    }
    mlt_properties_set_double(properties, "scale_x_adjust", 1.0);
    mlt_properties_set_double(properties, "scale_y_adjust", 1.0);
    mlt_properties_set_double(properties, "z_distance_adjust", 1.0);
    mlt_properties_set_double(properties, "brightness_adjust", 1.0);
    mlt_properties_set_int(properties, "wrap_x", 2);
    mlt_properties_set_int(properties, "wrap_y", 2);
    mlt_properties_set_int(properties, "quality_samples", 8);
    mlt_properties_set_int(properties, "subpixel", 1);
    return filter;
}

mlt_properties metadata(mlt_service_type type, const char *id, void *data)
{
    Q_UNUSED(type)
    Q_UNUSED(data)
    mlt_properties properties = mlt_properties_new();
    mlt_properties_set(properties, "identifier", id);
    mlt_properties_set(properties, "title", "Kdenlive Motion Transform and Blur");
    mlt_properties_set(properties, "description", "Native continuous motion transform with shutter-path blur and reflected sampling");
    mlt_properties_set(properties, "version", "0.1");
    return properties;
}

} // namespace

extern "C" mlt_filter createNativeFisheye(mlt_profile, mlt_service_type, const char *, const void *);
extern "C" mlt_properties nativeFisheyeMetadata(mlt_service_type, const char *, void *);
extern "C" mlt_filter createNativeShake(mlt_profile, mlt_service_type, const char *, const void *);
extern "C" mlt_properties nativeShakeMetadata(mlt_service_type, const char *, void *);
extern "C" mlt_filter createNativeAxisStretch(mlt_profile, mlt_service_type, const char *, const void *);
extern "C" mlt_properties nativeAxisStretchMetadata(mlt_service_type, const char *, void *);
extern "C" mlt_filter createNativeCornerPin(mlt_profile, mlt_service_type, const char *, const void *);
extern "C" mlt_properties nativeCornerPinMetadata(mlt_service_type, const char *, void *);
extern "C" mlt_filter createNativeWarpChroma(mlt_profile, mlt_service_type, const char *, const void *);
extern "C" mlt_properties nativeWarpChromaMetadata(mlt_service_type, const char *, void *);
extern "C" mlt_filter createNativeMotionVectorBlur(mlt_profile, mlt_service_type, const char *, const void *);
extern "C" mlt_properties nativeMotionVectorBlurMetadata(mlt_service_type, const char *, void *);
extern "C" mlt_filter createNativeSpatialBlur(mlt_profile, mlt_service_type, const char *, const void *);
extern "C" mlt_properties nativeSpatialBlurMetadata(mlt_service_type, const char *, void *);
extern "C" mlt_filter createNativeBlurMotion(mlt_profile, mlt_service_type, const char *, const void *);
extern "C" mlt_properties nativeBlurMotionMetadata(mlt_service_type, const char *, void *);
extern "C" mlt_filter createNativeMagnify(mlt_profile, mlt_service_type, const char *, const void *);
extern "C" mlt_properties nativeMagnifyMetadata(mlt_service_type, const char *, void *);
extern "C" mlt_filter createNativePinchPunch(mlt_profile, mlt_service_type, const char *, const void *);
extern "C" mlt_properties nativePinchPunchMetadata(mlt_service_type, const char *, void *);
extern "C" mlt_filter createNativeWaves(mlt_profile, mlt_service_type, const char *, const void *);
extern "C" mlt_properties nativeWavesMetadata(mlt_service_type, const char *, void *);
extern "C" mlt_filter createNativeBubbleWarp(mlt_profile, mlt_service_type, const char *, const void *);
extern "C" mlt_properties nativeBubbleWarpMetadata(mlt_service_type, const char *, void *);
extern "C" mlt_filter createNativeDistortChroma(mlt_profile, mlt_service_type, const char *, const void *);
extern "C" mlt_properties nativeDistortChromaMetadata(mlt_service_type, const char *, void *);
extern "C" mlt_filter createNativeBrightnessContrast(mlt_profile, mlt_service_type, const char *, const void *);
extern "C" mlt_properties nativeBrightnessContrastMetadata(mlt_service_type, const char *, void *);

extern "C" __attribute__((visibility("default"))) MLT_REPOSITORY
{
    MLT_REGISTER(mlt_service_filter_type, "kdenlive_motion_curve", createMotionCurve);
    MLT_REGISTER_METADATA(mlt_service_filter_type, "kdenlive_motion_curve", metadata, nullptr);
    MLT_REGISTER(mlt_service_filter_type, "kdenlive_brightness_contrast", createNativeBrightnessContrast);
    MLT_REGISTER_METADATA(mlt_service_filter_type, "kdenlive_brightness_contrast", nativeBrightnessContrastMetadata, nullptr);
    MLT_REGISTER(mlt_service_filter_type, "kdenlive_fisheye_warp", createNativeFisheye);
    MLT_REGISTER_METADATA(mlt_service_filter_type, "kdenlive_fisheye_warp", nativeFisheyeMetadata, nullptr);
    MLT_REGISTER(mlt_service_filter_type, "kdenlive_shake", createNativeShake);
    MLT_REGISTER_METADATA(mlt_service_filter_type, "kdenlive_shake", nativeShakeMetadata, nullptr);
    MLT_REGISTER(mlt_service_filter_type, "kdenlive_axis_stretch", createNativeAxisStretch);
    MLT_REGISTER_METADATA(mlt_service_filter_type, "kdenlive_axis_stretch", nativeAxisStretchMetadata, nullptr);
    MLT_REGISTER(mlt_service_filter_type, "kdenlive_corner_pin", createNativeCornerPin);
    MLT_REGISTER_METADATA(mlt_service_filter_type, "kdenlive_corner_pin", nativeCornerPinMetadata, nullptr);
    MLT_REGISTER(mlt_service_filter_type, "kdenlive_warp_chroma", createNativeWarpChroma);
    MLT_REGISTER_METADATA(mlt_service_filter_type, "kdenlive_warp_chroma", nativeWarpChromaMetadata, nullptr);
    MLT_REGISTER(mlt_service_filter_type, "kdenlive_motion_vector_blur", createNativeMotionVectorBlur);
    MLT_REGISTER_METADATA(mlt_service_filter_type, "kdenlive_motion_vector_blur", nativeMotionVectorBlurMetadata, nullptr);
    MLT_REGISTER(mlt_service_filter_type, "kdenlive_spatial_blur", createNativeSpatialBlur);
    MLT_REGISTER_METADATA(mlt_service_filter_type, "kdenlive_spatial_blur", nativeSpatialBlurMetadata, nullptr);
    MLT_REGISTER(mlt_service_filter_type, "kdenlive_blur_motion", createNativeBlurMotion);
    MLT_REGISTER_METADATA(mlt_service_filter_type, "kdenlive_blur_motion", nativeBlurMotionMetadata, nullptr);
    MLT_REGISTER(mlt_service_filter_type, "kdenlive_magnify_warp", createNativeMagnify);
    MLT_REGISTER_METADATA(mlt_service_filter_type, "kdenlive_magnify_warp", nativeMagnifyMetadata, nullptr);
    MLT_REGISTER(mlt_service_filter_type, "kdenlive_pinch_punch", createNativePinchPunch);
    MLT_REGISTER_METADATA(mlt_service_filter_type, "kdenlive_pinch_punch", nativePinchPunchMetadata, nullptr);
    MLT_REGISTER(mlt_service_filter_type, "kdenlive_warp_waves", createNativeWaves);
    MLT_REGISTER_METADATA(mlt_service_filter_type, "kdenlive_warp_waves", nativeWavesMetadata, nullptr);
    MLT_REGISTER(mlt_service_filter_type, "kdenlive_warp_bubble2", createNativeBubbleWarp);
    MLT_REGISTER_METADATA(mlt_service_filter_type, "kdenlive_warp_bubble2", nativeBubbleWarpMetadata, nullptr);
    MLT_REGISTER(mlt_service_filter_type, "kdenlive_distort_chroma", createNativeDistortChroma);
    MLT_REGISTER_METADATA(mlt_service_filter_type, "kdenlive_distort_chroma", nativeDistortChromaMetadata, nullptr);
}
