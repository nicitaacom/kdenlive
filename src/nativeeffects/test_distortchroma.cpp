/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "distortchroma.hpp"

#include <algorithm>
#include <cassert>
#include <cstdint>
#include <vector>

int main()
{
    constexpr int width = 96;
    constexpr int height = 64;
    std::vector<uint8_t> source(width * height * 4);
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            uint8_t *p = source.data() + (y * width + x) * 4;
            const bool tile = ((x / 8) + (y / 8)) % 2;
            p[0] = tile ? 240 : 12;
            p[1] = static_cast<uint8_t>((x * 7 + y * 3) & 255);
            p[2] = tile ? 18 : 220;
            p[3] = static_cast<uint8_t>((x + y) % 5 == 0 ? 96 : 255);
        }
    }

    NativeMotion::DistortChromaSettings settings;
    settings.wrapX = 2;
    settings.wrapY = 2;
    std::vector<uint8_t> output(source.size());
    NativeMotion::renderDistortChroma(source.data(), output.data(), width, height, settings);
    assert(output == source); // zero Amount is an identity operation, including alpha

    settings.amount = 0.22;
    settings.blurLens = 0.03;
    settings.rotateWarpDegrees = 144.5;
    settings.warpRed = -0.99;
    settings.warpBlue = 2.0;
    settings.steps = 8;
    NativeMotion::renderDistortChroma(source.data(), output.data(), width, height, settings);
    assert(output != source);
    for (size_t index = 3; index < output.size(); index += 4) {
        assert(output[index] == source[index]); // chroma warp preserves source alpha
    }
    std::vector<uint8_t> repeated(source.size());
    NativeMotion::renderDistortChroma(source.data(), repeated.data(), width, height, settings);
    assert(output == repeated); // output does not depend on seek/render history

    settings.amount = 0.0;
    NativeMotion::renderDistortChroma(source.data(), output.data(), width, height, settings);
    assert(output == source); // animated endpoints may safely reach zero
}
