/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "spatialblur.hpp"

#include <array>
#include <cstdio>
#include <cstring>

using NativeMotion::SpatialBlurSettings;
using NativeMotion::renderSpatialBlur;

int main()
{
    constexpr int width = 17;
    constexpr int height = 17;
    std::array<uint8_t, width * height * 4> source{};
    std::array<uint8_t, width * height * 4> result{};
    std::array<uint8_t, width * height * 4> repeated{};
    for (int pixel = 0; pixel < width * height; ++pixel) {
        source[pixel * 4 + 3] = 255;
    }
    auto channel = [&](const auto &image, int x, int y) {
        return image[(y * width + x) * 4];
    };
    source[(8 * width + 8) * 4] = 255;
    SpatialBlurSettings settings;
    renderSpatialBlur(source.data(), result.data(), width, height, settings);
    if (result != source) {
        std::fprintf(stderr, "zero blur must be identity\n");
        return 1;
    }
    settings.amount = 0.8;
    settings.samples = 17;
    renderSpatialBlur(source.data(), result.data(), width, height, settings);
    renderSpatialBlur(source.data(), repeated.data(), width, height, settings);
    if (result != repeated || channel(result, 8, 8) >= 255 ||
        channel(result, 9, 8) == 0 || channel(result, 8, 9) != 0) {
        std::fprintf(stderr, "linear blur direction or determinism failed\n");
        return 1;
    }
    settings.mode = 1;
    settings.centerX = 0.5;
    settings.centerY = 0.5;
    renderSpatialBlur(source.data(), result.data(), width, height, settings);
    if (channel(result, 9, 8) == 0 || channel(result, 8, 9) == 0) {
        std::fprintf(stderr, "radial blur axis failed\n");
        return 1;
    }
    return 0;
}
