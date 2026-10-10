/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

extern "C" {
#include <framework/mlt.h>
#include <framework/mlt_pool.h>
}

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>

namespace {

int getImage(mlt_frame frame, uint8_t **image, mlt_image_format *format, int *width, int *height, int writable)
{
    (void)writable;
    auto filter = static_cast<mlt_filter>(mlt_frame_pop_service(frame));
    *format = mlt_image_rgba;
    const int error = mlt_frame_get_image(frame, image, format, width, height, 0);
    if (error || !*image || *width < 1 || *height < 1) {
        return error ? error : 1;
    }
    const size_t bytes = static_cast<size_t>(*width) * *height * 4;
    if (bytes > static_cast<size_t>(std::numeric_limits<int>::max())) {
        return 1;
    }
    mlt_service_lock(MLT_FILTER_SERVICE(filter));
    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    const char *service = mlt_properties_get(properties, "region_filter");
    auto child = static_cast<mlt_filter>(mlt_properties_get_data(properties, "_region_child", nullptr));
    if (!child && service && std::strcmp(service, "kdenlive_region_blur") != 0) {
        child = mlt_factory_filter(mlt_service_profile(MLT_FILTER_SERVICE(filter)), service, nullptr);
        if (child) {
            mlt_properties_set_data(properties, "_region_child", child, 0, reinterpret_cast<mlt_destructor>(mlt_filter_close), nullptr);
        }
    }
    if (!child) {
        mlt_service_unlock(MLT_FILTER_SERVICE(filter));
        return 1;
    }
    // Forward the original blur's settings, including its keyframes and time range.
    // Keep each child's service identity and private rendering state intact.
    mlt_properties childProperties = MLT_FILTER_PROPERTIES(child);
    for (int i = 0; i < mlt_properties_count(properties); ++i) {
        const char *name = mlt_properties_get_name(properties, i);
        if (name && name[0] != '_' && std::strncmp(name, "region_", 7) != 0 && std::strcmp(name, "mlt_service") != 0) {
            mlt_properties_pass_property(childProperties, properties, name);
        }
    }
    // Render on an independent frame so blur kernels cannot modify pixels outside
    // the area, or the alpha channel of the source frame, in place.
    mlt_frame blurredFrame = mlt_frame_clone_image(frame, 1);
    if (!blurredFrame) {
        mlt_service_unlock(MLT_FILTER_SERVICE(filter));
        return 1;
    }
    // MLT 7.38/7.40 image clones do not retain the format conversion callback.
    // YUV-only blur kernels need the same converter as the source frame.
    blurredFrame->convert_image = frame->convert_image;
    mlt_filter_process(child, blurredFrame);
    uint8_t *blurred = nullptr;
    mlt_image_format blurredFormat = mlt_image_rgba;
    int blurredWidth = *width;
    int blurredHeight = *height;
    const int blurError = mlt_frame_get_image(blurredFrame, &blurred, &blurredFormat, &blurredWidth, &blurredHeight, 1);
    if (blurError || !blurred || blurredFormat != mlt_image_rgba || blurredWidth != *width || blurredHeight != *height) {
        mlt_frame_close(blurredFrame);
        mlt_service_unlock(MLT_FILTER_SERVICE(filter));
        return blurError ? blurError : 1;
    }
    auto *output = static_cast<uint8_t *>(mlt_pool_alloc(static_cast<int>(bytes)));
    if (!output) {
        mlt_frame_close(blurredFrame);
        mlt_service_unlock(MLT_FILTER_SERVICE(filter));
        return 1;
    }
    std::memcpy(output, *image, bytes);
    int left = 0;
    int top = 0;
    int right = *width;
    int bottom = *height;
    if (!mlt_properties_get_int(properties, "region_full_frame")) {
        const int position = mlt_filter_get_position(filter, frame) + mlt_filter_get_in(filter);
        const int length = mlt_filter_get_length2(filter, frame) + mlt_filter_get_in(filter);
        const mlt_rect rect = mlt_properties_anim_get_rect(properties, "region_rect", position, length);
        const mlt_profile profile = mlt_service_profile(MLT_FILTER_SERVICE(filter));
        const double scaleX = profile && profile->width > 0 ? static_cast<double>(*width) / profile->width : 1.0;
        const double scaleY = profile && profile->height > 0 ? static_cast<double>(*height) / profile->height : 1.0;
        if (std::isfinite(rect.x) && std::isfinite(rect.y) && std::isfinite(rect.w) && std::isfinite(rect.h) && rect.w > 0 && rect.h > 0) {
            left = static_cast<int>(std::clamp(std::ceil(rect.x * scaleX), 0.0, static_cast<double>(*width)));
            top = static_cast<int>(std::clamp(std::ceil(rect.y * scaleY), 0.0, static_cast<double>(*height)));
            right = static_cast<int>(std::clamp(std::ceil((rect.x + rect.w) * scaleX), 0.0, static_cast<double>(*width)));
            bottom = static_cast<int>(std::clamp(std::ceil((rect.y + rect.h) * scaleY), 0.0, static_cast<double>(*height)));
        } else {
            right = bottom = 0;
        }
    }
    for (int y = top; y < bottom; ++y) {
        for (int x = left; x < right; ++x) {
            const size_t offset = (static_cast<size_t>(y) * *width + x) * 4;
            std::memcpy(output + offset, blurred + offset, 3);
        }
    }
    mlt_frame_close(blurredFrame);
    mlt_service_unlock(MLT_FILTER_SERVICE(filter));
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

extern "C" mlt_filter createNativeRegionBlur(mlt_profile profile, mlt_service_type type, const char *id, const void *arg)
{
    (void)type; (void)id; (void)arg;
    mlt_filter filter = mlt_filter_new();
    if (!filter) {
        return nullptr;
    }
    filter->process = process;
    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    mlt_properties_set_int(properties, "region_full_frame", 0);
    char rect[128];
    std::snprintf(rect, sizeof(rect), "%g %g %g %g", profile->width * 0.375, profile->height * 0.375,
                  profile->width * 0.25, profile->height * 0.25);
    mlt_properties_set(properties, "region_rect", rect);
    return filter;
}

extern "C" mlt_properties nativeRegionBlurMetadata(mlt_service_type type, const char *id, void *data)
{
    (void)type; (void)data;
    mlt_properties properties = mlt_properties_new();
    mlt_properties_set(properties, "identifier", id);
    mlt_properties_set(properties, "title", "Kdenlive Region Blur");
    mlt_properties_set(properties, "description", "Apply a blur inside an editable rectangle, preserving the source outside it");
    mlt_properties_set(properties, "version", "0.1");
    return properties;
}
