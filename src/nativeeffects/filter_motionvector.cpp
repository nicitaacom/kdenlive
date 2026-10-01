/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "motionvector.hpp"
#include "filter_curves.hpp"

extern "C" {
#include <framework/mlt.h>
#include <framework/mlt_pool.h>
}

#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#include <mutex>
#include <string>
#include <vector>

using namespace NativeMotion;

namespace {

struct ReferenceState {
    std::mutex mutex;
    mlt_producer producer = nullptr;
    std::string signature;

    ~ReferenceState()
    {
        if (producer) {
            mlt_producer_close(producer);
        }
    }
};

void destroyReferenceState(void *value)
{
    delete static_cast<ReferenceState *>(value);
}

std::string upstreamSignature(mlt_producer source, mlt_filter upstream, int sourceIn)
{
    mlt_properties sourceProperties = MLT_PRODUCER_PROPERTIES(source);
    const char *service = mlt_properties_get(sourceProperties, "mlt_service");
    const char *resource = mlt_properties_get(sourceProperties, "resource");
    if (!service || !resource) {
        return {};
    }
    std::string signature = std::string(service) + '\n' + resource + '\n' + std::to_string(sourceIn);
    if (!upstream) {
        return signature;
    }
    mlt_properties properties = MLT_FILTER_PROPERTIES(upstream);
    signature += "\nkdenlive_motion_curve";
    for (int propertyIndex = 0; propertyIndex < mlt_properties_count(properties); ++propertyIndex) {
        const char *key = mlt_properties_get_name(properties, propertyIndex);
        const char *value = key ? mlt_properties_get(properties, key) : nullptr;
        if (key && value && key[0] != '_') {
            signature += '\n';
            signature += key;
            signature += '=';
            signature += value;
        }
    }
    return signature;
}

bool copyUpstreamMotion(mlt_producer reference, mlt_filter upstream, int sourceIn)
{
    if (!upstream) {
        return true;
    }
    mlt_filter copy = mlt_factory_filter(mlt_service_profile(MLT_PRODUCER_SERVICE(reference)), "kdenlive_motion_curve", nullptr);
    if (!copy) {
        return false;
    }
    mlt_properties originalProperties = MLT_FILTER_PROPERTIES(upstream);
    mlt_properties copyProperties = MLT_FILTER_PROPERTIES(copy);
    for (int propertyIndex = 0; propertyIndex < mlt_properties_count(originalProperties); ++propertyIndex) {
        const char *name = mlt_properties_get_name(originalProperties, propertyIndex);
        if (!name || name[0] == '_' || std::strcmp(name, "mlt_service") == 0 || std::strcmp(name, "mlt_type") == 0 ||
            std::strcmp(name, "service") == 0 || std::strcmp(name, "in") == 0 || std::strcmp(name, "out") == 0) {
            continue;
        }
        const char *value = mlt_properties_get(originalProperties, name);
        if (value) {
            mlt_properties_set(copyProperties, name, value);
        }
    }
    const int eventFrames = std::max(1, mlt_properties_get_int(originalProperties, "native_event_frames"));
    // The clone is a media producer, so its position is a source frame. Its
    // editable keyframe values are still measured relative to the event.
    mlt_properties_set_int(copyProperties, "native_reference_source_in", sourceIn);
    mlt_filter_set_in_and_out(copy, 0, sourceIn + eventFrames - 1);
    const int attached = mlt_producer_attach(reference, copy);
    mlt_filter_close(copy);
    return attached == 0;
}

bool referenceImage(mlt_frame frame, mlt_filter filter, int position, int sourceIn,
                    int width, int height, std::vector<uint8_t> &pixels)
{
    mlt_producer origin = mlt_frame_get_original_producer(frame);
    if (!origin) {
        return false;
    }
    mlt_producer parent = mlt_producer_is_cut(origin) ? mlt_producer_cut_parent(origin) : origin;
    if (!parent) {
        return false;
    }
    mlt_properties originalProperties = MLT_PRODUCER_PROPERTIES(parent);
    const char *service = mlt_properties_get(originalProperties, "mlt_service");
    const char *resource = mlt_properties_get(originalProperties, "resource");
    if (!service || !resource || !*resource) {
        return false;
    }
    mlt_properties frameState = mlt_frame_get_unique_properties(frame, MLT_FILTER_SERVICE(filter));
    mlt_filter upstream = frameState ? static_cast<mlt_filter>(mlt_properties_get_data(frameState, "upstream_motion", nullptr)) : nullptr;
    const std::string signature = upstreamSignature(parent, upstream, sourceIn);
    auto *state = static_cast<ReferenceState *>(mlt_properties_get_data(MLT_FILTER_PROPERTIES(filter), "_native_reference_state", nullptr));
    if (!state) {
        return false;
    }
    std::lock_guard<std::mutex> lock(state->mutex);
    if (!state->producer || state->signature != signature) {
        if (state->producer) {
            mlt_producer_close(state->producer);
            state->producer = nullptr;
        }
        mlt_profile profile = mlt_service_profile(MLT_FILTER_SERVICE(filter));
        state->producer = mlt_factory_producer(profile, service, resource);
        if (!state->producer) {
            return false;
        }
        mlt_properties referenceProperties = MLT_PRODUCER_PROPERTIES(state->producer);
        for (const char *name : {"video_index", "audio_index", "force_fps", "force_aspect_ratio", "force_progressive", "force_tff", "autorotate"}) {
            const char *value = mlt_properties_get(originalProperties, name);
            if (value) {
                mlt_properties_set(referenceProperties, name, value);
            }
        }
        if (!copyUpstreamMotion(state->producer, upstream, sourceIn)) {
            mlt_producer_close(state->producer);
            state->producer = nullptr;
            return false;
        }
        state->signature = signature;
    }
    if (mlt_producer_seek(state->producer, position) != 0) {
        return false;
    }
    mlt_frame neighbor = nullptr;
    const int frameError = mlt_service_get_frame(MLT_PRODUCER_SERVICE(state->producer), &neighbor, 0);
    if (frameError || !neighbor) {
        return false;
    }
    uint8_t *image = nullptr;
    mlt_image_format format = mlt_image_rgba;
    int referenceWidth = width;
    int referenceHeight = height;
    mlt_properties frameProperties = MLT_FRAME_PROPERTIES(neighbor);
    mlt_properties_set(frameProperties, "consumer.rescale", "bilinear");
    mlt_properties_set_int(frameProperties, "rescale_width", width);
    mlt_properties_set_int(frameProperties, "rescale_height", height);
    mlt_properties_set_int(frameProperties, "distort", 1);
    const int imageError = mlt_frame_get_image(neighbor, &image, &format, &referenceWidth, &referenceHeight, 0);
    const bool valid = imageError == 0 && image && format == mlt_image_rgba && referenceWidth > 0 && referenceHeight > 0;
    if (valid) {
        if (referenceWidth == width && referenceHeight == height) {
            pixels.assign(image, image + static_cast<size_t>(width) * height * 4);
        } else {
            pixels.resize(static_cast<size_t>(width) * height * 4);
            for (int y = 0; y < height; ++y) {
                for (int x = 0; x < width; ++x) {
                    const double sx = (x + 0.5) * referenceWidth / width - 0.5;
                    const double sy = (y + 0.5) * referenceHeight / height - 0.5;
                    const Pixel pixel = sampleRgba(image, referenceWidth, referenceHeight, sx, sy, 2, 2, true);
                    uint8_t *destination = pixels.data() + (static_cast<size_t>(y) * width + x) * 4;
                    destination[3] = static_cast<uint8_t>(std::clamp(std::lround(pixel.a * 255.0), 0l, 255l));
                    const auto channel = [&](double premultiplied) {
                        return static_cast<uint8_t>(std::clamp(std::lround(pixel.a > 1e-9 ? premultiplied / pixel.a : 0.0), 0l, 255l));
                    };
                    destination[0] = channel(pixel.r);
                    destination[1] = channel(pixel.g);
                    destination[2] = channel(pixel.b);
                }
            }
        }
    }
    mlt_frame_close(neighbor);
    return valid;
}

double sampledDifference(const uint8_t *current, const std::vector<uint8_t> &neighbor, int width, int height)
{
    double difference = 0.0;
    int count = 0;
    const int strideX = std::max(1, width / 32);
    const int strideY = std::max(1, height / 18);
    for (int y = 0; y < height; y += strideY) {
        for (int x = 0; x < width; x += strideX) {
            const size_t offset = (static_cast<size_t>(y) * width + x) * 4;
            for (int channel = 0; channel < 3; ++channel) {
                difference += std::abs(static_cast<int>(current[offset + channel]) - static_cast<int>(neighbor[offset + channel]));
                ++count;
            }
        }
    }
    return difference / std::max(1, count);
}

int getImage(mlt_frame frame, uint8_t **image, mlt_image_format *format, int *width, int *height, int writable)
{
    (void)writable;
    mlt_filter filter = static_cast<mlt_filter>(mlt_frame_pop_service(frame));
    *format = mlt_image_rgba;
    const int error = mlt_frame_get_image(frame, image, format, width, height, 0);
    if (error || !*image || *width < 1 || *height < 1) {
        return error ? error : 1;
    }
    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    const int eventFrames = std::max(1, mlt_properties_get_int(properties, "native_event_frames"));
    const int localPosition = std::clamp(static_cast<int>(mlt_filter_get_position(filter, frame)), 0, eventFrames - 1);
    const int sourcePosition = static_cast<int>(mlt_frame_original_position(frame));
    const int sourceIn = sourcePosition - localPosition;
    const int animationLength = static_cast<int>(mlt_filter_get_out(filter)) + 1;
    const int keyframePosition = static_cast<int>(mlt_filter_get_in(filter)) + localPosition;
    const double baseAmount = mlt_properties_anim_get_double(properties, "blur_amount", keyframePosition, animationLength);
    const double envelopeAdjustment = mlt_properties_anim_get_double(properties, "blur_envelope_adjust", keyframePosition, animationLength);
    const double sensitivity = mlt_properties_anim_get_double(properties, "motion_sensitivity", keyframePosition, animationLength);
    const int samples = mlt_properties_anim_get_int(properties, "quality_samples", keyframePosition, animationLength);
    const char *curveString = mlt_properties_get(properties, "native_curves");
    bool curvesValid = false;
    const Curves curves = parseCurves(curveString ? QByteArray(curveString) : QByteArray("{}"), &curvesValid);
    if (!curvesValid) {
        return 1;
    }
    const double progress = fittedProgress(properties, localPosition, eventFrames);
    const double amount = applyBlurEnvelope(baseAmount, curves, progress, envelopeAdjustment);
    if (!std::isfinite(amount) || !std::isfinite(sensitivity) || amount < 0 || sensitivity < 0 || eventFrames == 1 || amount == 0) {
        return 0;
    }
    // RSMB tracks motion in the original media, whose playback speed does not
    // change when a preset is fitted to a longer timeline event. Its vector
    // amount therefore stays at the decoded value. The Motion Transform row
    // separately fits its own animation-path shutter to the event duration.
    const double shutterFrames = amount;
    std::vector<uint8_t> neighbor;
    int referenceDistance = 0;
    const int preferredDistance = std::clamp(static_cast<int>(std::ceil(shutterFrames)), 1, 4);
    std::vector<int> distances;
    for (int distance = preferredDistance; distance >= 1; --distance) {
        distances.push_back(distance);
    }
    for (int distance = preferredDistance + 1; distance <= 4; ++distance) {
        distances.push_back(distance);
    }
    for (int distance : distances) {
        for (int direction : {1, -1}) {
            const int candidateLocal = localPosition + direction * distance;
            const int candidate = sourcePosition + direction * distance;
            if (candidateLocal < 0 || candidateLocal >= eventFrames ||
                !referenceImage(frame, filter, candidate, sourceIn, *width, *height, neighbor)) {
                continue;
            }
            if (sampledDifference(*image, neighbor, *width, *height) >= 1.0 || distance == 4) {
                referenceDistance = distance;
                break;
            }
        }
        if (referenceDistance != 0) {
            break;
        }
    }
    if (referenceDistance == 0) {
        // A one-frame event or an unavailable neighbor must still preserve
        // the current source image instead of producing a transparent frame.
        return 0;
    }
    const int radius = std::clamp(static_cast<int>(std::lround(sensitivity * *width / 1920.0)) * referenceDistance,
                                  0, std::max(0, *width / 3));
    const MotionField flow = estimateMotion(*image, neighbor.data(), *width, *height, radius);
    const size_t bytes = static_cast<size_t>(*width) * *height * 4;
    if (bytes > static_cast<size_t>(std::numeric_limits<int>::max())) {
        return 1;
    }
    auto *output = static_cast<uint8_t *>(mlt_pool_alloc(static_cast<int>(bytes)));
    if (!output) {
        return 1;
    }
    renderVectorBlur(*image, output, *width, *height, flow, shutterFrames, referenceDistance, samples);
    mlt_frame_set_image(frame, output, static_cast<int>(bytes), mlt_pool_release);
    *image = output;
    *format = mlt_image_rgba;
    return 0;
}

bool isNoOpFrame(mlt_filter filter, mlt_frame frame)
{
    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    const int eventFrames = std::max(1, mlt_properties_get_int(properties, "native_event_frames"));
    if (eventFrames == 1) {
        return true;
    }
    const int localPosition = std::clamp(static_cast<int>(mlt_filter_get_position(filter, frame)), 0, eventFrames - 1);
    const int keyframePosition = static_cast<int>(mlt_filter_get_in(filter)) + localPosition;
    const int animationLength = std::max(1, static_cast<int>(mlt_filter_get_out(filter)) + 1);
    const double baseAmount = mlt_properties_anim_get_double(properties, "blur_amount", keyframePosition, animationLength);
    const double envelopeAdjustment = mlt_properties_anim_get_double(properties, "blur_envelope_adjust", keyframePosition, animationLength);
    if (!std::isfinite(baseAmount) || baseAmount <= 0.0) {
        return true;
    }
    const char *curveString = mlt_properties_get(properties, "native_curves");
    if (!curveString || std::strstr(curveString, "\"blur_envelope\"") == nullptr) {
        return false;
    }
    bool curvesValid = false;
    const Curves curves = parseCurves(QByteArray(curveString), &curvesValid);
    if (!curvesValid) {
        return false;
    }
    const double progress = fittedProgress(properties, localPosition, eventFrames);
    return applyBlurEnvelope(baseAmount, curves, progress, envelopeAdjustment) <= 0.0;
}

mlt_frame process(mlt_filter filter, mlt_frame frame)
{
    // Capture the upstream row now. MLT builds all image callbacks before
    // evaluating them, so reading the frame property later could see a Motion
    // row that the user has moved after this blur component.
    mlt_properties frameState = mlt_frame_unique_properties(frame, MLT_FILTER_SERVICE(filter));
    mlt_properties_set_data(frameState, "upstream_motion",
                            mlt_properties_get_data(MLT_FRAME_PROPERTIES(frame), "_native_upstream_motion_filter", nullptr),
                            0, nullptr, nullptr);
    if (isNoOpFrame(filter, frame)) {
        return frame;
    }
    mlt_frame_push_service(frame, filter);
    mlt_frame_push_get_image(frame, getImage);
    return frame;
}

} // namespace

extern "C" mlt_filter createNativeMotionVectorBlur(mlt_profile profile, mlt_service_type type, const char *id, const void *arg)
{
    (void)profile;
    (void)type;
    (void)id;
    (void)arg;
    mlt_filter filter = mlt_filter_new();
    if (!filter) {
        return nullptr;
    }
    filter->process = process;
    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    mlt_properties_set_double(properties, "blur_amount", 0.65);
    mlt_properties_set_double(properties, "blur_envelope_adjust", 1.0);
    mlt_properties_set_double(properties, "motion_sensitivity", 80.0);
    mlt_properties_set_int(properties, "quality_samples", 8);
    mlt_properties_set_int(properties, "native_nominal_frames", 0);
    mlt_properties_set_int(properties, "native_event_frames", 0);
    mlt_properties_set_double(properties, "native_curve_start", 0.0);
    mlt_properties_set_double(properties, "native_curve_end", 1.0);
    mlt_properties_set_data(properties, "_native_reference_state", new ReferenceState, 0, destroyReferenceState, nullptr);
    return filter;
}

extern "C" mlt_properties nativeMotionVectorBlurMetadata(mlt_service_type type, const char *id, void *data)
{
    (void)type;
    (void)data;
    mlt_properties properties = mlt_properties_new();
    mlt_properties_set(properties, "identifier", id);
    mlt_properties_set(properties, "title", "Kdenlive Motion Vector Blur");
    mlt_properties_set(properties, "description", "CPU block-flow blur from adjacent composited source frames");
    mlt_properties_set(properties, "version", "0.1");
    return properties;
}
