/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "bubblewarp.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace NativeMotion {
namespace {

uint64_t mix64(uint64_t value)
{
    value += 0x9e3779b97f4a7c15ULL;
    value = (value ^ (value >> 30)) * 0xbf58476d1ce4e5b9ULL;
    value = (value ^ (value >> 27)) * 0x94d049bb133111ebULL;
    return value ^ (value >> 31);
}

uint64_t bubbleKey(double seed, int64_t x, int64_t y, int octave)
{
    const auto seedBits = static_cast<uint64_t>(std::llround(std::clamp(seed, -1e9, 1e9) * 1000000.0));
    uint64_t value = mix64(seedBits ^ 0x75ab4c3dULL);
    value ^= mix64(static_cast<uint64_t>(x) + 0x632be59bd9b4e019ULL);
    value ^= mix64(static_cast<uint64_t>(y) + 0x8cb92baa3f3d8dd7ULL);
    value ^= mix64(static_cast<uint64_t>(octave) + 0x58f38ded4d42b8a1ULL);
    return mix64(value);
}

double unit16(uint64_t key, int shift)
{
    return static_cast<double>((key >> shift) & 0xffffULL) / 65535.0;
}

Point bubbleDisplacement(double u, double v, int width, int height, const BubbleSetSettings &set,
                         int octave, double pixelAspectRatio)
{
    const double frequency = std::clamp(set.frequency, 0.01, 128.0) * std::ldexp(1.0, octave);
    const double cellX = u * frequency;
    const double cellY = v * frequency;
    const int64_t baseX = static_cast<int64_t>(std::floor(cellX));
    const int64_t baseY = static_cast<int64_t>(std::floor(cellY));
    const double amplitudeScale = set.amplitude * std::min(width, height) * 0.075 / std::ldexp(1.0, octave);
    const double aspect = std::clamp(pixelAspectRatio, 0.01, 100.0);
    Point displacement;
    const double seed = set.seed + octave * 13.371;
    for (int64_t gy = baseY - 1; gy <= baseY + 1; ++gy) {
        for (int64_t gx = baseX - 1; gx <= baseX + 1; ++gx) {
            const uint64_t key = bubbleKey(seed, gx, gy, octave);
            const double centerX = (static_cast<double>(gx) + 0.2 + 0.6 * unit16(key, 0)) / frequency;
            const double centerY = (static_cast<double>(gy) + 0.2 + 0.6 * unit16(key, 16)) / frequency;
            const double radius = (0.22 + 0.22 * unit16(key, 32)) / frequency;
            const double dx = u - centerX;
            const double dy = v - centerY;
            const double physicalDx = dx * width * aspect;
            const double physicalDy = dy * height;
            const double distance = std::sqrt(physicalDx * physicalDx + physicalDy * physicalDy);
            const double radiusPx = radius * std::min(width * aspect, static_cast<double>(height));
            if (distance >= radiusPx || distance < 1e-9) {
                continue;
            }
            const double radial = distance / radiusPx;
            const double shell = std::sin(radial * 3.14159265358979323846);
            const double polarity = (key >> 48) & 1ULL ? -1.0 : 1.0;
            const double amount = polarity * shell * amplitudeScale;
            displacement.x += (physicalDx / distance) * amount / aspect;
            displacement.y += (physicalDy / distance) * amount;
        }
    }
    return displacement;
}

Point applySet(Point mapped, double u, double v, int width, int height, double progress,
               const BubbleSetSettings &set, const BubbleWarpSettings &settings)
{
    if (std::abs(set.amplitude) < 1e-12) {
        return mapped;
    }
    const int octaves = std::clamp(set.octaves, 1, 10);
    const double nominalFrames = std::max(1, settings.nominalFrames);
    const double shiftedU = u + set.shiftStartX + set.speedX * progress * nominalFrames;
    const double shiftedV = v + set.shiftStartY + set.speedY * progress * nominalFrames;
    Point displacement;
    for (int octave = 0; octave < octaves; ++octave) {
        const Point octaveDisplacement = bubbleDisplacement(shiftedU, shiftedV, width, height, set,
                                                           octave, settings.pixelAspectRatio);
        displacement.x += octaveDisplacement.x;
        displacement.y += octaveDisplacement.y;
    }
    mapped.x += std::clamp(displacement.x, -0.25 * width, 0.25 * width);
    mapped.y += std::clamp(displacement.y, -0.25 * height, 0.25 * height);
    return mapped;
}

} // namespace

Point mapBubbleWarp(double x, double y, int width, int height, double progress,
                    const BubbleWarpSettings &settings)
{
    if (width <= 0 || height <= 0) {
        return {};
    }
    const double zoom = std::clamp(settings.zDistance, 1e-4, 1e4);
    Point mapped{(x - (width - 1) * 0.5) / zoom + (width - 1) * 0.5,
                 (y - (height - 1) * 0.5) / zoom + (height - 1) * 0.5};
    const double u = width > 1 ? x / (width - 1.0) : 0.5;
    const double v = height > 1 ? y / (height - 1.0) : 0.5;
    mapped = applySet(mapped, u, v, width, height, progress, settings.a, settings);
    mapped = applySet(mapped, u, v, width, height, progress, settings.b, settings);
    return mapped;
}

} // namespace NativeMotion
