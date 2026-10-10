/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

extern "C" {
#include <framework/mlt.h>
#include <framework/mlt_pool.h>
mlt_filter createNativeRegionBlur(mlt_profile, mlt_service_type, const char *, const void *);
}

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

namespace {

void require(bool condition, const char *message)
{
    if (!condition) {
        std::fprintf(stderr, "%s\n", message);
        std::exit(1);
    }
}

std::vector<uint8_t> render(mlt_filter filter, const std::vector<uint8_t> &input, int width, int height, int position,
                            mlt_filter second = nullptr)
{
    mlt_frame frame = mlt_frame_init(nullptr);
    mlt_frame_set_position(frame, position);
    mlt_properties properties = MLT_FRAME_PROPERTIES(frame);
    mlt_properties_set_int(properties, "width", width);
    mlt_properties_set_int(properties, "height", height);
    mlt_properties_set_int(properties, "format", mlt_image_rgba);
    mlt_properties_set_int(properties, "colorspace", 709);
    mlt_properties_set_int(properties, "full_range", 1);
    auto *buffer = static_cast<uint8_t *>(mlt_pool_alloc(input.size()));
    std::memcpy(buffer, input.data(), input.size());
    mlt_frame_set_image(frame, buffer, input.size(), mlt_pool_release);
    mlt_filter conversion = mlt_factory_filter(mlt_service_profile(MLT_FILTER_SERVICE(filter)), "imageconvert", nullptr);
    require(conversion != nullptr, "image conversion service is unavailable");
    mlt_filter_process(conversion, frame);
    mlt_filter_process(filter, frame);
    if (second) {
        mlt_filter_process(second, frame);
    }
    mlt_image_format format = mlt_image_rgba;
    require(mlt_frame_get_image(frame, &buffer, &format, &width, &height, 0) == 0, "blur rendering failed");
    require(format == mlt_image_rgba, "blur did not return RGBA");
    std::vector<uint8_t> output(buffer, buffer + input.size());
    mlt_frame_close(frame);
    mlt_filter_close(conversion);
    return output;
}

void checkArea(const std::vector<uint8_t> &input, const std::vector<uint8_t> &output, const std::vector<uint8_t> &full,
               int width, int height, int left, int top, int right, int bottom, bool requireChange = true)
{
    bool changed = false;
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            const int offset = (y * width + x) * 4;
            const bool inside = x >= left && x < right && y >= top && y < bottom;
            for (int c = 0; c < 3; ++c) {
                if (output[offset + c] != (inside ? full[offset + c] : input[offset + c])) {
                    std::fprintf(stderr, "mismatch at %d,%d channel %d, inside=%d: input=%d output=%d full=%d\n",
                                 x, y, c, inside, input[offset + c], output[offset + c], full[offset + c]);
                }
                require(output[offset + c] == (inside ? full[offset + c] : input[offset + c]),
                        "blur pixels did not match the requested area");
                changed = changed || (inside && output[offset + c] != input[offset + c]);
            }
            require(output[offset + 3] == input[offset + 3], "area blur changed source transparency");
        }
    }
    if (requireChange && !changed) {
        std::fprintf(stderr, "unchanged area: %d,%d to %d,%d, frame size %dx%d\n", left, top, right, bottom, width, height);
    }
    require(!requireChange || changed, "blur did not change any pixels inside the area");
}

} // namespace

int main()
{
    mlt_factory_init(nullptr);
    mlt_profile profile = mlt_profile_init(nullptr);
    profile->width = 64;
    profile->height = 48;
    const int width = profile->width;
    const int height = profile->height;
    std::vector<uint8_t> input(width * height * 4);
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            const int offset = (y * width + x) * 4;
            input[offset] = (x + y) % 2 ? 255 : 0;
            input[offset + 1] = (x * 17 + y * 29) % 256;
            input[offset + 2] = (x * 47 + y * 11) % 256;
            input[offset + 3] = 80 + (x + y) % 176;
        }
    }
    mlt_filter blur = mlt_factory_filter(profile, "box_blur", nullptr);
    require(blur != nullptr, "box blur service is unavailable");
    mlt_properties_set(MLT_FILTER_PROPERTIES(blur), "hradius", "10");
    mlt_properties_set(MLT_FILTER_PROPERTIES(blur), "vradius", "10");
    mlt_properties_set_int(MLT_FILTER_PROPERTIES(blur), "preserve_alpha", 0);
    mlt_filter area = createNativeRegionBlur(profile, mlt_service_filter_type, "kdenlive_region_blur", nullptr);
    mlt_service_set_profile(MLT_FILTER_SERVICE(area), profile);
    mlt_properties properties = MLT_FILTER_PROPERTIES(area);
    mlt_properties_set(properties, "region_filter", "box_blur");
    mlt_properties_set(properties, "hradius", "10");
    mlt_properties_set(properties, "vradius", "10");
    mlt_properties_set_int(properties, "preserve_alpha", 0);
    const auto full = render(blur, input, width, height, 0);
    checkArea(input, render(area, input, width, height, 0), full, width, height, 24, 18, 40, 30);

    // Region keyframes use source time, including clips trimmed away from zero.
    mlt_filter_set_in_and_out(area, 10, 30);
    mlt_properties_set(properties, "region_rect", "10=4 6 12 8;30=32 22 12 8");
    checkArea(input, render(area, input, width, height, 10), full, width, height, 4, 6, 16, 14);
    checkArea(input, render(area, input, width, height, 30), full, width, height, 32, 22, 44, 30);

    // Preview resolutions scale the mask using the project dimensions.
    const std::vector<uint8_t> small(input.begin(), input.begin() + 32 * 24 * 4);
    mlt_properties_set(MLT_FILTER_PROPERTIES(blur), "hradius", "100");
    mlt_properties_set(MLT_FILTER_PROPERTIES(blur), "vradius", "100");
    mlt_properties_set(properties, "hradius", "100");
    mlt_properties_set(properties, "vradius", "100");
    const auto smallFull = render(blur, small, 32, 24, 0);
    checkArea(small, render(area, small, 32, 24, 10), smallFull, 32, 24, 2, 3, 8, 7);
    mlt_properties_set(MLT_FILTER_PROPERTIES(blur), "hradius", "10");
    mlt_properties_set(MLT_FILTER_PROPERTIES(blur), "vradius", "10");
    mlt_properties_set(properties, "hradius", "10");
    mlt_properties_set(properties, "vradius", "10");

    mlt_properties_set_int(properties, "region_full_frame", 1);
    checkArea(input, render(area, input, width, height, 10), full, width, height, 0, 0, width, height);
    mlt_properties_set_int(properties, "region_full_frame", 0);
    mlt_properties_set(properties, "region_rect", "-10 -10 0 0");
    require(render(area, input, width, height, 10) == input, "an empty area changed the image");
    mlt_properties_set(properties, "region_rect", "-4 -4 12 12");
    checkArea(input, render(area, input, width, height, 10), full, width, height, 0, 0, 8, 8);

    // Editing blur strength must update the child filter after the first render.
    mlt_properties_set(properties, "hradius", "30");
    mlt_properties_set(properties, "vradius", "30");
    mlt_properties_set(MLT_FILTER_PROPERTIES(blur), "hradius", "30");
    mlt_properties_set(MLT_FILTER_PROPERTIES(blur), "vradius", "30");
    const auto updatedFull = render(blur, input, width, height, 0);
    require(updatedFull != full, "editing blur strength did not change the full-frame reference");
    checkArea(input, render(area, input, width, height, 10), updatedFull, width, height, 0, 0, 8, 8);

    mlt_filter second = createNativeRegionBlur(profile, mlt_service_filter_type, "kdenlive_region_blur", nullptr);
    mlt_service_set_profile(MLT_FILTER_SERVICE(second), profile);
    mlt_properties secondProperties = MLT_FILTER_PROPERTIES(second);
    mlt_properties_set(secondProperties, "region_filter", "box_blur");
    mlt_properties_set(secondProperties, "region_rect", "40 30 12 12");
    mlt_properties_set(secondProperties, "hradius", "30");
    mlt_properties_set(secondProperties, "vradius", "30");
    const auto first = render(area, input, width, height, 10);
    const auto secondFull = render(blur, first, width, height, 0);
    checkArea(first, render(area, input, width, height, 10, second), secondFull, width, height, 40, 30, 52, 42);

    // FFmpeg kernels use other image formats. Their conversions must happen on
    // the independent frame too, without a color-space round trip outside the mask.
    for (const char *service : {"avfilter.avgblur", "avfilter.gblur", "avfilter.boxblur", "avfilter.dblur", "avfilter.smartblur", "avfilter.sab",
                                "frei0r.squareblur", "frei0r.IIRblur"}) {
        mlt_filter kernel = mlt_factory_filter(profile, service, nullptr);
        require(kernel != nullptr, "a supported blur service is unavailable");
        mlt_filter masked = createNativeRegionBlur(profile, mlt_service_filter_type, "kdenlive_region_blur", nullptr);
        mlt_service_set_profile(MLT_FILTER_SERVICE(masked), profile);
        mlt_properties maskedProperties = MLT_FILTER_PROPERTIES(masked);
        mlt_properties_set(maskedProperties, "region_filter", service);
        mlt_properties_set(maskedProperties, "region_rect", "8 8 40 24");
        // Shared nonzero controls are ignored by kernels that do not use them.
        for (mlt_properties target : {MLT_FILTER_PROPERTIES(kernel), maskedProperties}) {
            mlt_properties_set_double(target, "av.sigma", 4);
            mlt_properties_set_double(target, "av.luma_radius", 4);
            mlt_properties_set_double(target, "av.luma_strength", 1);
            mlt_properties_set_double(target, "av.radius", 4);
            mlt_properties_set_double(target, "Kernel size", 0.4);
            mlt_properties_set_double(target, "Amount", 0.4);
        }
        std::fprintf(stderr, "checking %s\n", service);
        const auto kernelFull = render(kernel, input, width, height, 0);
        const auto maskedOutput = render(masked, input, width, height, 0);
        checkArea(input, maskedOutput, kernelFull, width, height, 8, 8, 48, 32, false);
        mlt_filter_close(masked);
        mlt_filter_close(kernel);
    }

    mlt_filter_close(second);
    mlt_filter_close(area);
    mlt_filter_close(blur);
    mlt_profile_close(profile);
    mlt_factory_close();
    return 0;
}
