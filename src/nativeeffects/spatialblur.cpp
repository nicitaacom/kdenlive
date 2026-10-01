/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "spatialblur.hpp"
#include "motioncurve.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>

namespace NativeMotion {

void renderSpatialBlur(const uint8_t *source, uint8_t *destination,
                       int width, int height, const SpatialBlurSettings &settings)
{
    if (!source || !destination || width < 1 || height < 1) {
        return;
    }
    const size_t bytes = static_cast<size_t>(width) * height * 4;
    if (!std::isfinite(settings.amount) || settings.amount <= 0 || settings.samples < 2) {
        std::memcpy(destination, source, bytes);
        return;
    }
    const int samples = std::clamp(settings.samples, 2, 65);
    const double radius = std::clamp(settings.amount, 0.0, 1.0) * std::max(width, height) * 0.25;
    const double radians = settings.angleDegrees * (3.14159265358979323846 / 180.0);
    const double aspect = settings.pixelAspectRatio > 0 ? settings.pixelAspectRatio : 1;
    const double centerX = settings.centerX * width - 0.5;
    const double centerY = (1.0 - settings.centerY) * height - 0.5;
    const double maximumDistance = std::max(1.0, std::hypot(width * aspect, height) * 0.5);
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            double directionX = std::cos(radians) / aspect;
            double directionY = -std::sin(radians);
            double currentRadius = radius;
            if (settings.mode == 1) {
                const double dx = (x - centerX) * aspect;
                const double dy = y - centerY;
                const double distance = std::hypot(dx, dy);
                if (distance > 1e-9) {
                    directionX = dx / distance / aspect;
                    directionY = dy / distance;
                }
                if (settings.radialType == 0) {
                    currentRadius *= distance / maximumDistance;
                }
            }
            Pixel total;
            double weightSum = 0;
            for (int sample = 0; sample < samples; ++sample) {
                const double phase = (static_cast<double>(sample) / (samples - 1)) * 2.0 - 1.0;
                const double offset = phase * currentRadius;
                const double weight = settings.mode == 1 && settings.radialType == 2
                                          ? std::exp(-2.0 * phase * phase) : 1.0;
                // Reflected source pixels keep the border filled. VEGAS does
                // not publish the exact sample kernel or maximum pixel radius.
                const Pixel pixel = sampleRgba(source, width, height,
                                               x + directionX * offset,
                                               y + directionY * offset, 2, 2, true);
                total.r += pixel.r * weight;
                total.g += pixel.g * weight;
                total.b += pixel.b * weight;
                total.a += pixel.a * weight;
                weightSum += weight;
            }
            auto *output = destination + (static_cast<size_t>(y) * width + x) * 4;
            const double alpha = total.a / weightSum;
            output[3] = static_cast<uint8_t>(std::clamp(std::lround(alpha * 255.0), 0l, 255l));
            const auto channel = [&](double premultiplied) {
                return static_cast<uint8_t>(std::clamp(std::lround(total.a > 1e-9 ? premultiplied / total.a : 0.0), 0l, 255l));
            };
            output[0] = channel(total.r);
            output[1] = channel(total.g);
            output[2] = channel(total.b);
        }
    }
}

} // namespace NativeMotion
