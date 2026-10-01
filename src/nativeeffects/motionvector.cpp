/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "motionvector.hpp"
#include "motioncurve.hpp"
#include "parallelrows.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace NativeMotion {
namespace {

struct LumaPlane {
    int width = 0;
    int height = 0;
    std::vector<uint8_t> pixels;

    int at(int x, int y) const
    {
        x = std::clamp(x, 0, width - 1);
        y = std::clamp(y, 0, height - 1);
        return pixels[static_cast<size_t>(y) * width + x];
    }
};

LumaPlane downsample(const uint8_t *rgba, int width, int height, int scale)
{
    LumaPlane result;
    result.width = (width + scale - 1) / scale;
    result.height = (height + scale - 1) / scale;
    result.pixels.resize(static_cast<size_t>(result.width) * result.height);
    for (int y = 0; y < result.height; ++y) {
        for (int x = 0; x < result.width; ++x) {
            unsigned sum = 0;
            unsigned count = 0;
            for (int sy = y * scale; sy < std::min(height, (y + 1) * scale); ++sy) {
                for (int sx = x * scale; sx < std::min(width, (x + 1) * scale); ++sx) {
                    const uint8_t *pixel = rgba + (static_cast<size_t>(sy) * width + sx) * 4;
                    const unsigned luma = (54u * pixel[0] + 183u * pixel[1] + 19u * pixel[2]) >> 8;
                    sum += luma * pixel[3] / 255u;
                    ++count;
                }
            }
            result.pixels[static_cast<size_t>(y) * result.width + x] = static_cast<uint8_t>(sum / std::max(1u, count));
        }
    }
    return result;
}

double patchCost(const LumaPlane &source, const LumaPlane &candidate,
                 int x, int y, int dx, int dy, int radius)
{
    unsigned difference = 0;
    for (int row = -radius; row <= radius; ++row) {
        for (int column = -radius; column <= radius; ++column) {
            difference += std::abs(source.at(x + column, y + row) -
                                   candidate.at(x + column + dx, y + row + dy));
        }
    }
    return static_cast<double>(difference) / ((radius * 2 + 1) * (radius * 2 + 1));
}

double patchRange(const LumaPlane &source, int x, int y)
{
    int minimum = 255;
    int maximum = 0;
    for (int row = -2; row <= 2; ++row) {
        for (int column = -2; column <= 2; ++column) {
            const int value = source.at(x + column, y + row);
            minimum = std::min(minimum, value);
            maximum = std::max(maximum, value);
        }
    }
    return maximum - minimum;
}

} // namespace

MotionVector MotionField::at(double x, double y) const
{
    if (columns < 1 || rows < 1 || vectors.empty()) {
        return {};
    }
    const double gridX = std::clamp(x / tileSize - 0.5, 0.0, static_cast<double>(columns - 1));
    const double gridY = std::clamp(y / tileSize - 0.5, 0.0, static_cast<double>(rows - 1));
    const int left = static_cast<int>(std::floor(gridX));
    const int top = static_cast<int>(std::floor(gridY));
    const int right = std::min(columns - 1, left + 1);
    const int bottom = std::min(rows - 1, top + 1);
    const double fx = gridX - left;
    const double fy = gridY - top;
    const MotionVector a = vectors[static_cast<size_t>(top) * columns + left];
    const MotionVector b = vectors[static_cast<size_t>(top) * columns + right];
    const MotionVector c = vectors[static_cast<size_t>(bottom) * columns + left];
    const MotionVector d = vectors[static_cast<size_t>(bottom) * columns + right];
    return {(1 - fy) * ((1 - fx) * a.x + fx * b.x) + fy * ((1 - fx) * c.x + fx * d.x),
            (1 - fy) * ((1 - fx) * a.y + fx * b.y) + fy * ((1 - fx) * c.y + fx * d.y)};
}

MotionField estimateMotion(const uint8_t *current, const uint8_t *neighbor,
                           int width, int height, int sensitivity)
{
    MotionField field;
    if (!current || !neighbor || width < 1 || height < 1) {
        return field;
    }
    field.columns = (width + field.tileSize - 1) / field.tileSize;
    field.rows = (height + field.tileSize - 1) / field.tileSize;
    field.vectors.resize(static_cast<size_t>(field.columns) * field.rows);
    const LumaPlane current8 = downsample(current, width, height, 8);
    const LumaPlane neighbor8 = downsample(neighbor, width, height, 8);
    const LumaPlane current4 = downsample(current, width, height, 4);
    const LumaPlane neighbor4 = downsample(neighbor, width, height, 4);
    const int radius8 = std::clamp((sensitivity + 7) / 8, 0, 24);
    for (int by = 0; by < field.rows; ++by) {
        for (int bx = 0; bx < field.columns; ++bx) {
            const int centerX = std::min(width - 1, bx * field.tileSize + field.tileSize / 2);
            const int centerY = std::min(height - 1, by * field.tileSize + field.tileSize / 2);
            const int x8 = centerX / 8;
            const int y8 = centerY / 8;
            const int x4 = centerX / 4;
            const int y4 = centerY / 4;
            if (patchRange(current4, x4, y4) < 5) {
                continue;
            }
            int bestX8 = 0;
            int bestY8 = 0;
            double bestCost = std::numeric_limits<double>::infinity();
            for (int dy = -radius8; dy <= radius8; ++dy) {
                for (int dx = -radius8; dx <= radius8; ++dx) {
                    const double cost = patchCost(current8, neighbor8, x8, y8, dx, dy, 1) +
                                        0.15 * (std::abs(dx) + std::abs(dy));
                    if (cost < bestCost) {
                        bestCost = cost;
                        bestX8 = dx;
                        bestY8 = dy;
                    }
                }
            }
            int bestX4 = bestX8 * 2;
            int bestY4 = bestY8 * 2;
            bestCost = std::numeric_limits<double>::infinity();
            for (int dy = bestY8 * 2 - 2; dy <= bestY8 * 2 + 2; ++dy) {
                for (int dx = bestX8 * 2 - 2; dx <= bestX8 * 2 + 2; ++dx) {
                    const double cost = patchCost(current4, neighbor4, x4, y4, dx, dy, 2) +
                                        0.08 * (std::abs(dx) + std::abs(dy));
                    if (cost < bestCost) {
                        bestCost = cost;
                        bestX4 = dx;
                        bestY4 = dy;
                    }
                }
            }
            field.vectors[static_cast<size_t>(by) * field.columns + bx] =
                {static_cast<double>(bestX4 * 4), static_cast<double>(bestY4 * 4)};
        }
    }
    return field;
}

double applyBlurEnvelope(double amount, const Curves &curves, double progress, double adjustment)
{
    const auto envelope = curves.constFind(QByteArray("blur_envelope"));
    if (envelope == curves.cend()) {
        return amount * std::clamp(adjustment, 0.0, 1.0);
    }
    const double factor = std::clamp(evaluate(envelope.value(), progress, 1.0) * adjustment, 0.0, 1.0);
    return amount * factor;
}

void renderVectorBlur(const uint8_t *current, uint8_t *output, int width, int height,
                      const MotionField &field, double shutterFrames,
                      int referenceDistance, int samples)
{
    if (!current || !output || width < 1 || height < 1) {
        return;
    }
    samples = std::clamp(samples, 1, 32);
    const double span = std::clamp(shutterFrames / std::max(1, referenceDistance), 0.0, 16.0);
    parallelRows(height, [&](int y) {
        for (int x = 0; x < width; ++x) {
            const MotionVector vector = field.at(x, y);
            Pixel sum;
            for (int index = 0; index < samples; ++index) {
                const double phase = (static_cast<double>(index) + 0.5) / samples - 0.5;
                const Pixel pixel = sampleRgba(current, width, height,
                                               x + phase * span * vector.x,
                                               y + phase * span * vector.y, 2, 2, true);
                sum.r += pixel.r;
                sum.g += pixel.g;
                sum.b += pixel.b;
                sum.a += pixel.a;
            }
            uint8_t *destination = output + (static_cast<size_t>(y) * width + x) * 4;
            destination[3] = static_cast<uint8_t>(std::clamp(std::lround(sum.a / samples * 255.0), 0l, 255l));
            const auto channel = [&](double premultiplied) {
                return static_cast<uint8_t>(std::clamp(std::lround(sum.a > 1e-9 ? premultiplied / sum.a : 0.0), 0l, 255l));
            };
            destination[0] = channel(sum.r);
            destination[1] = channel(sum.g);
            destination[2] = channel(sum.b);
        }
    });
}

} // namespace NativeMotion
