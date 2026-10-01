/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "spatialtransformblur.hpp"

#include <algorithm>
#include <cassert>
#include <cstdint>
#include <vector>

using namespace NativeMotion;

int main()
{
    constexpr int width = 48;
    constexpr int height = 32;
    std::vector<uint8_t> source(width * height * 4);
    std::vector<uint8_t> identity(source.size());
    std::vector<uint8_t> blurred(source.size());
    std::vector<uint8_t> repeated(source.size());
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            const size_t offset = (static_cast<size_t>(y) * width + x) * 4;
            const bool marker = x > 13 && x < 25 && y > 7 && y < 24;
            source[offset] = marker ? 240 : static_cast<uint8_t>((x * 13 + y * 3) % 180);
            source[offset + 1] = marker ? 18 : static_cast<uint8_t>((x * 5 + y * 11) % 190);
            source[offset + 2] = marker ? 30 : static_cast<uint8_t>((x * 7 + y * 17) % 200);
            source[offset + 3] = 255;
        }
    }

    BlurMotionSettings settings;
    settings.from = {1.0, 0.0, 0.0, 0.0};
    settings.to = settings.from;
    settings.samples = 17;
    renderBlurMotion(source.data(), identity.data(), width, height, settings);
    assert(identity == source); // identical transform endpoints preserve the source.

    settings.to.zDistance = 0.78;
    settings.to.rotateDegrees = 9.0;
    settings.to.shiftX = 0.035;
    settings.wrapX = 2;
    settings.wrapY = 2;
    renderBlurMotion(source.data(), blurred.data(), width, height, settings);
    renderBlurMotion(source.data(), repeated.data(), width, height, settings);
    assert(blurred == repeated); // seek order cannot alter the accumulated result.
    size_t changed = 0;
    for (size_t i = 0; i < source.size(); i += 4) {
        changed += source[i] != blurred[i] || source[i + 1] != blurred[i + 1] || source[i + 2] != blurred[i + 2];
        assert(blurred[i + 3] == 255);
    }
    assert(changed > width * height / 3); // transform-space samples visibly move image detail.

    settings.brightness = 0.5;
    renderBlurMotion(source.data(), repeated.data(), width, height, settings);
    assert(repeated != blurred);

    settings.brightness = 1.0;
    settings.from = {1.0, 0.0, 0.7, 0.0};
    settings.to = settings.from;
    settings.wrapX = 0;
    std::fill(repeated.begin(), repeated.end(), 0);
    renderBlurMotion(source.data(), repeated.data(), width, height, settings);
    size_t blackNoWrap = 0;
    for (size_t offset = 0; offset < repeated.size(); offset += 4) {
        blackNoWrap += repeated[offset] == 0 && repeated[offset + 1] == 0 && repeated[offset + 2] == 0;
    }
    assert(blackNoWrap > 0); // Wrap X = No exposes opaque black beyond the shifted image.

    settings.wrapX = 2;
    renderBlurMotion(source.data(), repeated.data(), width, height, settings);
    size_t blackReflect = 0;
    for (size_t offset = 3; offset < repeated.size(); offset += 4) {
        assert(repeated[offset] == 255); // Reflect keeps source-derived pixels at the exposed edge.
    }
    for (size_t offset = 0; offset < repeated.size(); offset += 4) {
        blackReflect += repeated[offset] == 0 && repeated[offset + 1] == 0 && repeated[offset + 2] == 0;
    }
    assert(blackReflect < blackNoWrap);
}
