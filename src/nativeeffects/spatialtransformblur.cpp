/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "spatialtransformblur.hpp"
#include "motioncurve.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>

namespace NativeMotion {
namespace {

Point inverseMap(double x, double y, int width, int height,
                 const BlurMotionSettings &settings, const SpatialTransform &transform)
{
    const double aspect = settings.pixelAspectRatio > 0 && std::isfinite(settings.pixelAspectRatio)
                              ? settings.pixelAspectRatio : 1.0;
    const double z = std::clamp(transform.zDistance, 0.001, 1000.0);
    const double cx = settings.centerX * width - 0.5;
    const double cy = (1.0 - settings.centerY) * height - 0.5;
    // Shift values use frame-relative units, matching the editable normalized
    // controls. Pixel aspect is applied in display space before inverse rotation.
    const double dx = (x - cx - transform.shiftX * width) * aspect;
    const double dy = y - cy - transform.shiftY * height;
    const double angle = transform.rotateDegrees * (3.14159265358979323846 / 180.0);
    const double cosine = std::cos(angle);
    const double sine = std::sin(angle);
    return {cx + z * (cosine * dx + sine * dy) / aspect,
            cy + z * (-sine * dx + cosine * dy)};
}

} // namespace

void renderBlurMotion(const uint8_t *source, uint8_t *destination,
                      int width, int height, const BlurMotionSettings &settings)
{
    if (!source || !destination || width < 1 || height < 1) {
        return;
    }
    const size_t bytes = static_cast<size_t>(width) * static_cast<size_t>(height) * 4;
    if (bytes > static_cast<size_t>(std::numeric_limits<int>::max())) {
        return;
    }
    const int sampleCount = std::clamp(settings.samples, 2, 65);
    const double bias = std::clamp(settings.exposureBias, 0.0, 1.0);
    const double biasSlope = (bias - 0.5) * 4.0;
    const double brightness = std::isfinite(settings.brightness)
                                  ? std::max(0.0, settings.brightness) : 1.0;

    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            Pixel total;
            double weightSum = 0.0;
            for (int i = 0; i < sampleCount; ++i) {
                const double t = static_cast<double>(i) / (sampleCount - 1);
                const double centered = t * 2.0 - 1.0;
                const double weight = std::exp(std::clamp(biasSlope * centered, -4.0, 4.0));
                SpatialTransform transform;
                transform.zDistance = settings.from.zDistance +
                                      (settings.to.zDistance - settings.from.zDistance) * t;
                transform.rotateDegrees = settings.from.rotateDegrees +
                                          (settings.to.rotateDegrees - settings.from.rotateDegrees) * t;
                transform.shiftX = settings.from.shiftX + (settings.to.shiftX - settings.from.shiftX) * t;
                transform.shiftY = settings.from.shiftY + (settings.to.shiftY - settings.from.shiftY) * t;
                const Point input = inverseMap(x, y, width, height, settings, transform);
                const Pixel pixel = sampleRgba(source, width, height, input.x, input.y,
                                               settings.wrapX, settings.wrapY, settings.subpixel);
                total.r += pixel.r * weight;
                total.g += pixel.g * weight;
                total.b += pixel.b * weight;
                total.a += pixel.a * weight;
                weightSum += weight;
            }
            auto *out = destination + (static_cast<size_t>(y) * width + x) * 4;
            const double alpha = weightSum > 0 ? total.a / weightSum : 0.0;
            out[3] = static_cast<uint8_t>(std::clamp(std::lround(alpha * 255.0), 0l, 255l));
            const auto channel = [&](double premultiplied) {
                const double value = total.a > 1e-9 ? premultiplied / total.a * brightness : 0.0;
                return static_cast<uint8_t>(std::clamp(std::lround(value), 0l, 255l));
            };
            out[0] = channel(total.r);
            out[1] = channel(total.g);
            out[2] = channel(total.b);
        }
    }
}

} // namespace NativeMotion
