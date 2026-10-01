/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "motionvector.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <vector>

using namespace NativeMotion;

int main()
{
    bool valid = false;
    const Curves outgoingEnvelope = parseCurves(
        R"({"blur_envelope":[[0,0,0,0,0.3,0,1],[1,1,0.7,0.8,1,1,0]]})", &valid);
    if (!valid || std::abs(applyBlurEnvelope(0.65, outgoingEnvelope, 0.0)) > 1e-9 ||
        !(applyBlurEnvelope(0.65, outgoingEnvelope, 0.5) > 0.1) ||
        std::abs(applyBlurEnvelope(0.65, outgoingEnvelope, 1.0) - 0.65) > 1e-9) {
        std::fprintf(stderr, "outgoing motion blur envelope did not build to its source amount\n");
        return 1;
    }
    const Curves incomingEnvelope = parseCurves(
        R"({"blur_envelope":[[0,1,0,1,0.3,0.8,1],[1,0,0.7,0,1,0,0]]})", &valid);
    if (!valid || std::abs(applyBlurEnvelope(0.65, incomingEnvelope, 0.0) - 0.65) > 1e-9 ||
        !(applyBlurEnvelope(0.65, incomingEnvelope, 0.5) < 0.55) ||
        std::abs(applyBlurEnvelope(0.65, incomingEnvelope, 1.0)) > 1e-9 ||
        std::abs(applyBlurEnvelope(0.65, Curves{}, 0.4) - 0.65) > 1e-9) {
        std::fprintf(stderr, "incoming motion blur envelope did not recover to identity\n");
        return 1;
    }
    if (std::abs(applyBlurEnvelope(0.65, outgoingEnvelope, 0.5, 0.0)) > 1e-9 ||
        std::abs(applyBlurEnvelope(0.65, Curves{}, 0.5, 0.5) - 0.325) > 1e-9) {
        std::fprintf(stderr, "editable motion vector blur envelope adjustment failed\n");
        return 1;
    }

    constexpr int width = 128;
    constexpr int height = 96;
    std::vector<uint8_t> current(static_cast<size_t>(width) * height * 4);
    std::vector<uint8_t> shifted(current.size());
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            const auto colorAt = [y](int sx) {
                const uint32_t n = static_cast<uint32_t>((sx / 4) * 73856093u) ^
                                   static_cast<uint32_t>((y / 4) * 19349663u);
                return static_cast<uint8_t>((n ^ (n >> 11) ^ (n >> 19)) & 255u);
            };
            const size_t index = (static_cast<size_t>(y) * width + x) * 4;
            current[index] = current[index + 1] = current[index + 2] = colorAt(x);
            current[index + 3] = 255;
            shifted[index] = shifted[index + 1] = shifted[index + 2] = colorAt(std::max(0, x - 8));
            shifted[index + 3] = 255;
        }
    }
    const MotionField first = estimateMotion(current.data(), shifted.data(), width, height, 24);
    const MotionField second = estimateMotion(current.data(), shifted.data(), width, height, 24);
    if (first.vectors.size() != second.vectors.size() || first.vectors.empty()) {
        std::fprintf(stderr, "motion field is empty or unstable\n");
        return 1;
    }
    for (size_t index = 0; index < first.vectors.size(); ++index) {
        if (first.vectors[index].x != second.vectors[index].x || first.vectors[index].y != second.vectors[index].y) {
            std::fprintf(stderr, "motion estimate depends on evaluation order\n");
            return 1;
        }
    }
    const MotionVector center = first.at(64, 48);
    if (std::abs(center.x - 8.0) > 2.0 || std::abs(center.y) > 2.0) {
        std::fprintf(stderr, "wrong synthetic translation: %.3f, %.3f\n", center.x, center.y);
        return 1;
    }
    std::vector<uint8_t> blurred(current.size());
    std::vector<uint8_t> blurredAgain(current.size());
    renderVectorBlur(current.data(), blurred.data(), width, height, first, 0.65, 1, 8);
    renderVectorBlur(current.data(), blurredAgain.data(), width, height, first, 0.65, 1, 8);
    if (blurred != blurredAgain) {
        std::fprintf(stderr, "parallel blur differs between repeated renders\n");
        return 1;
    }
    int changed = 0;
    for (size_t index = 0; index < current.size(); index += 4) {
        changed += std::abs(static_cast<int>(current[index]) - static_cast<int>(blurred[index])) > 1;
        if (blurred[index + 3] != 255) {
            std::fprintf(stderr, "opaque input lost alpha at pixel %zu\n", index / 4);
            return 1;
        }
    }
    if (changed < width * height / 20) {
        std::fprintf(stderr, "estimated motion did not blur source pixels\n");
        return 1;
    }
    return 0;
}
