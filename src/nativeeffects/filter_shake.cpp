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
#include <cstdint>
#include <limits>

using namespace NativeMotion;

namespace {

struct ShakeContext : FilterCurveContext {
    int nominalFrames = 1;
    double frameRate = 25;
};

double animated(const ShakeContext &context, const char *name, double time)
{
    return animatedAt(context, name, time);
}

double sourceParameter(const ShakeContext &context, const char *name, double time)
{
    return sourceAt(context, name, time);
}

uint64_t mix(uint64_t value)
{
    value += 0x9e3779b97f4a7c15ULL;
    value = (value ^ (value >> 30)) * 0xbf58476d1ce4e5b9ULL;
    value = (value ^ (value >> 27)) * 0x94d049bb133111ebULL;
    return value ^ (value >> 31);
}

double randomAt(int64_t index, uint64_t seed)
{
    const uint64_t bits = mix(static_cast<uint64_t>(index) ^ seed);
    return static_cast<double>(bits >> 11) / 4503599627370495.5 - 1.0;
}

double smoothNoise(double position, uint64_t seed)
{
    const double bounded = std::clamp(position, -1e9, 1e9);
    const auto lower = static_cast<int64_t>(std::floor(bounded));
    const double fraction = bounded - lower;
    const double smooth = fraction * fraction * (3.0 - 2.0 * fraction);
    return randomAt(lower, seed) * (1.0 - smooth) + randomAt(lower + 1, seed) * smooth;
}

double axis(const ShakeContext &context, const char *randAmpName, const char *randFreqName,
            const char *waveAmpName, const char *waveFreqName, const char *phaseName,
            uint64_t salt, double time, double seconds, double frequency, double amplitude)
{
    const double randAmp = animated(context, randAmpName, time);
    const double randFreq = animated(context, randFreqName, time);
    const double waveAmp = animated(context, waveAmpName, time);
    const double waveFreq = animated(context, waveFreqName, time);
    const double phase = animated(context, phaseName, time);
    const double seed = animated(context, "seed", time);
    const double random = smoothNoise(seconds * frequency * randFreq + phase,
                                      mix(static_cast<uint64_t>(std::llround(seed)) ^ salt));
    const double wave = std::sin(2.0 * 3.14159265358979323846 * seconds * frequency * waveFreq + phase);
    return amplitude * (randAmp * random + waveAmp * wave);
}

Transform transformAt(double time, void *opaque)
{
    const auto &context = *static_cast<ShakeContext *>(opaque);
    const double amplitude = sourceParameter(context, "amplitude", time) +
                             animated(context, "amplitude_adjust", time);
    const double frequency = std::max(0.0, sourceParameter(context, "frequency", time) +
                                           animated(context, "frequency_adjust", time));
    const double phase = animated(context, "phase", time);
    const double sourceSeconds = time * std::max(0, context.nominalFrames - 1) / std::max(1e-6, context.frameRate) + phase;
    Transform transform;
    transform.shiftX = axis(context, "x_rand_amp", "x_rand_freq", "x_wave_amp", "x_wave_freq", "x_phase",
                            0x13579bdfULL, time, sourceSeconds, frequency, amplitude);
    transform.shiftY = axis(context, "y_rand_amp", "y_rand_freq", "y_wave_amp", "y_wave_freq", "y_phase",
                            0x2468ace0ULL, time, sourceSeconds, frequency, amplitude);
    const double zoom = axis(context, "z_rand_amp", "z_rand_freq", "z_wave_amp", "z_wave_freq", "z_phase",
                             0x4cae1234ULL, time, sourceSeconds, frequency, amplitude);
    transform.zDistance = std::max(0.001, sourceParameter(context, "z_distance", time) + zoom);
    transform.rotateDegrees = axis(context, "tilt_rand_amp", "tilt_rand_freq", "tilt_wave_amp", "tilt_wave_freq", "tilt_phase",
                                   0x9bcd5678ULL, time, sourceSeconds, frequency, amplitude);
    return transform;
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
    const char *curveString = mlt_properties_get(properties, "native_curves");
    bool valid = false;
    Curves curves = parseCurves(curveString ? QByteArray(curveString) : QByteArray("{}"), &valid);
    if (!valid) {
        mlt_pool_release(output);
        return 1;
    }
    const int configuredFrames = mlt_properties_get_int(properties, "native_event_frames");
    const int eventFrames = std::max(1, configuredFrames > 0 ? configuredFrames : static_cast<int>(mlt_filter_get_length2(filter, frame)));
    const int nominalFrames = std::max(1, mlt_properties_get_int(properties, "native_nominal_frames") > 0
                                       ? mlt_properties_get_int(properties, "native_nominal_frames") : eventFrames);
    const int position = std::clamp(static_cast<int>(mlt_filter_get_position(filter, frame)), 0, eventFrames - 1);
    const char *role = mlt_properties_get(properties, "native_event_role");
    const double progress = eventFrames > 1 ? static_cast<double>(position) / (eventFrames - 1)
                                             : (role && QByteArray(role) == "incoming" ? 0.0 : 1.0);
    mlt_profile profile = mlt_service_profile(MLT_FILTER_SERVICE(filter));
    const double fps = profile && profile->frame_rate_den > 0
                           ? static_cast<double>(profile->frame_rate_num) / profile->frame_rate_den : 25.0;
    const int filterIn = static_cast<int>(mlt_filter_get_in(filter));
    const int animationLength = std::max(1, static_cast<int>(mlt_filter_get_out(filter)) + 1);
    const int keyframePosition = filterIn + position;
    ShakeContext context;
    context.properties = properties;
    context.curves = std::move(curves);
    context.eventFrames = eventFrames;
    context.nominalFrames = nominalFrames;
    context.frameRate = fps;
    context.filterIn = filterIn;
    context.animationLength = animationLength;
    SampleSettings settings;
    settings.samples = mlt_properties_anim_get_int(properties, "motion_blur", keyframePosition, animationLength)
                           ? std::clamp(mlt_properties_anim_get_int(properties, "quality_samples", keyframePosition, animationLength), 1, 64) : 1;
    settings.shutterFrames = eventFrames == 1 ? 0.0 :
        sourceParameter(context, "mo_blur_length", progress) * (eventFrames - 1) / std::max(1, nominalFrames - 1);
    settings.wrapX = mlt_properties_anim_get_int(properties, "wrap_x", keyframePosition, animationLength);
    settings.wrapY = mlt_properties_anim_get_int(properties, "wrap_y", keyframePosition, animationLength);
    settings.subpixel = mlt_properties_anim_get_int(properties, "subpixel", keyframePosition, animationLength) != 0;
    settings.pixelAspectRatio = profile && profile->sample_aspect_den > 0
                                    ? static_cast<double>(profile->sample_aspect_num) / profile->sample_aspect_den : 1.0;
    renderRgba(*image, output, *width, *height, progress, std::max(1, eventFrames - 1), settings, transformAt, &context);
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

extern "C" mlt_filter createNativeShake(mlt_profile profile, mlt_service_type type, const char *id, const void *arg)
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
    mlt_properties_set_int(properties, "native_nominal_frames", 0);
    mlt_properties_set_double(properties, "amplitude", 0);
    mlt_properties_set_double(properties, "frequency", 1);
    mlt_properties_set_double(properties, "amplitude_adjust", 0);
    mlt_properties_set_double(properties, "frequency_adjust", 0);
    mlt_properties_set_double(properties, "phase", 0);
    mlt_properties_set_double(properties, "seed", 0);
    mlt_properties_set_double(properties, "z_distance", 1);
    mlt_properties_set_int(properties, "motion_blur", 0);
    mlt_properties_set_double(properties, "mo_blur_length", 1);
    for (const char *axis : {"x", "y", "z", "tilt"}) {
        for (const char *suffix : {"_rand_amp", "_wave_amp", "_phase"}) {
            const QByteArray key = QByteArray(axis) + suffix;
            mlt_properties_set_double(properties, key.constData(), 0);
        }
        for (const char *suffix : {"_rand_freq", "_wave_freq"}) {
            const QByteArray key = QByteArray(axis) + suffix;
            mlt_properties_set_double(properties, key.constData(), 1);
        }
    }
    mlt_properties_set_int(properties, "wrap_x", 2);
    mlt_properties_set_int(properties, "wrap_y", 2);
    mlt_properties_set_int(properties, "quality_samples", 8);
    mlt_properties_set_int(properties, "subpixel", 1);
    return filter;
}

extern "C" mlt_properties nativeShakeMetadata(mlt_service_type type, const char *id, void *data)
{
    Q_UNUSED(type)
    Q_UNUSED(data)
    mlt_properties properties = mlt_properties_new();
    mlt_properties_set(properties, "identifier", id);
    mlt_properties_set(properties, "title", "Kdenlive Deterministic Shake");
    mlt_properties_set(properties, "description", "Native seeded smooth-noise and oscillating transform");
    mlt_properties_set(properties, "version", "0.1");
    return properties;
}
