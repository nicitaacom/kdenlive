/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "distortchroma.hpp"

#include "motioncurve.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <vector>

namespace NativeMotion {
namespace {

int clampIndex(int value, int length)
{
    return std::clamp(value, 0, length - 1);
}

std::vector<double> sourceLuminance(const uint8_t *source, int width, int height)
{
    std::vector<double> luma(static_cast<size_t>(width) * height);
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            const uint8_t *pixel = source + (static_cast<size_t>(y) * width + x) * 4;
            // Sapphire describes a brightness-derived lens. This is Rec. 709
            // luma from the straight source RGB values.
            luma[static_cast<size_t>(y) * width + x] =
                (0.2126 * pixel[0] + 0.7152 * pixel[1] + 0.0722 * pixel[2]) / 255.0;
        }
    }
    return luma;
}

std::vector<double> boxBlur(const std::vector<double> &input, int width, int height, int radius)
{
    if (radius <= 0) {
        return input;
    }
    std::vector<double> horizontal(input.size());
    std::vector<double> result(input.size());
    const int diameter = radius * 2 + 1;
    for (int y = 0; y < height; ++y) {
        double sum = 0;
        for (int offset = -radius; offset <= radius; ++offset) {
            sum += input[static_cast<size_t>(y) * width + clampIndex(offset, width)];
        }
        for (int x = 0; x < width; ++x) {
            horizontal[static_cast<size_t>(y) * width + x] = sum / diameter;
            sum -= input[static_cast<size_t>(y) * width + clampIndex(x - radius, width)];
            sum += input[static_cast<size_t>(y) * width + clampIndex(x + radius + 1, width)];
        }
    }
    for (int x = 0; x < width; ++x) {
        double sum = 0;
        for (int offset = -radius; offset <= radius; ++offset) {
            sum += horizontal[static_cast<size_t>(clampIndex(offset, height)) * width + x];
        }
        for (int y = 0; y < height; ++y) {
            result[static_cast<size_t>(y) * width + x] = sum / diameter;
            sum -= horizontal[static_cast<size_t>(clampIndex(y - radius, height)) * width + x];
            sum += horizontal[static_cast<size_t>(clampIndex(y + radius + 1, height)) * width + x];
        }
    }
    return result;
}

double lumaAt(const std::vector<double> &luma, int width, int height, int x, int y)
{
    x = clampIndex(x, width);
    y = clampIndex(y, height);
    return luma[static_cast<size_t>(y) * width + x];
}

} // namespace

void renderDistortChroma(const uint8_t *source, uint8_t *output, int width, int height,
                         const DistortChromaSettings &inputSettings)
{
    if (!source || !output || width <= 0 || height <= 0) {
        return;
    }
    const auto &settings = inputSettings;
    if (std::abs(settings.amount) < 1e-15) {
        std::memcpy(output, source, static_cast<size_t>(width) * height * 4);
        return;
    }
    const int steps = std::clamp(settings.steps, 3, 100);
    const int blurRadius = std::clamp(static_cast<int>(std::lround(std::max(0.0, settings.blurLens) *
                                                                  std::min(width, height))),
                                      0, std::max(width, height));
    const std::vector<double> luma = boxBlur(sourceLuminance(source, width, height), width, height, blurRadius);
    const double radians = settings.rotateWarpDegrees * (3.14159265358979323846 / 180.0);
    const double cosine = std::cos(radians);
    const double sine = std::sin(radians);
    // Amount is a normalized source-space displacement. This keeps the
    // behavior resolution independent; channel factors remain signed.
    const double scaleX = settings.amount * std::min(width, height) * settings.amountRelX;
    const double scaleY = settings.amount * std::min(width, height) * settings.amountRelY;
    const double redNorm = settings.warpRed;
    const double blueNorm = settings.warpBlue;
    // Sapphire describes red, middle, and blue spectral bands. Compute the
    // weighted center of each band from the configured number of spectral
    // positions, then sample only those three output channels. This preserves
    // the Steps control while avoiding a full RGBA read for every band.
    double redFactorSum = 0.0;
    double greenFactorSum = 0.0;
    double blueFactorSum = 0.0;
    double redWeightSum = 0.0;
    double greenWeightSum = 0.0;
    double blueWeightSum = 0.0;
    for (int index = 0; index < steps; ++index) {
        const double t = static_cast<double>(index) / (steps - 1);
        const double factor = redNorm + (blueNorm - redNorm) * t;
        const double redWeight = std::max(0.0, 1.0 - 2.0 * t);
        const double greenWeight = 1.0 - std::abs(2.0 * t - 1.0);
        const double blueWeight = std::max(0.0, 2.0 * t - 1.0);
        redFactorSum += redWeight * factor;
        greenFactorSum += greenWeight * factor;
        blueFactorSum += blueWeight * factor;
        redWeightSum += redWeight;
        greenWeightSum += greenWeight;
        blueWeightSum += blueWeight;
    }
    const double redFactor = redWeightSum > 0 ? redFactorSum / redWeightSum : redNorm;
    const double greenFactor = greenWeightSum > 0 ? greenFactorSum / greenWeightSum : 0.5 * (redNorm + blueNorm);
    const double blueFactor = blueWeightSum > 0 ? blueFactorSum / blueWeightSum : blueNorm;

    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            // Sobel estimates a smooth brightness gradient. Border samples
            // clamp for the lens calculation; warped source samples use the
            // preset's independent Wrap X/Wrap Y behavior.
            const double gx = (lumaAt(luma, width, height, x + 1, y - 1) +
                               2.0 * lumaAt(luma, width, height, x + 1, y) +
                               lumaAt(luma, width, height, x + 1, y + 1) -
                               lumaAt(luma, width, height, x - 1, y - 1) -
                               2.0 * lumaAt(luma, width, height, x - 1, y) -
                               lumaAt(luma, width, height, x - 1, y + 1)) / 8.0;
            const double gy = (lumaAt(luma, width, height, x - 1, y + 1) +
                               2.0 * lumaAt(luma, width, height, x, y + 1) +
                               lumaAt(luma, width, height, x + 1, y + 1) -
                               lumaAt(luma, width, height, x - 1, y - 1) -
                               2.0 * lumaAt(luma, width, height, x, y - 1) -
                               lumaAt(luma, width, height, x + 1, y - 1)) / 8.0;
            const double rotatedX = cosine * gx - sine * gy;
            const double rotatedY = sine * gx + cosine * gy;
            const Pixel redSample = sampleRgba(source, width, height,
                                               x - rotatedX * scaleX * redFactor,
                                               y - rotatedY * scaleY * redFactor,
                                               settings.wrapX, settings.wrapY, settings.subpixel);
            const Pixel greenSample = sampleRgba(source, width, height,
                                                 x - rotatedX * scaleX * greenFactor,
                                                 y - rotatedY * scaleY * greenFactor,
                                                 settings.wrapX, settings.wrapY, settings.subpixel);
            const Pixel blueSample = sampleRgba(source, width, height,
                                                x - rotatedX * scaleX * blueFactor,
                                                y - rotatedY * scaleY * blueFactor,
                                                settings.wrapX, settings.wrapY, settings.subpixel);
            const uint8_t *unwarped = source + (static_cast<size_t>(y) * width + x) * 4;
            uint8_t *destination = output + (static_cast<size_t>(y) * width + x) * 4;
            destination[0] = static_cast<uint8_t>(std::clamp(std::lround(redSample.a > 1e-9 ? redSample.r / redSample.a : 0), 0L, 255L));
            destination[1] = static_cast<uint8_t>(std::clamp(std::lround(greenSample.a > 1e-9 ? greenSample.g / greenSample.a : 0), 0L, 255L));
            destination[2] = static_cast<uint8_t>(std::clamp(std::lround(blueSample.a > 1e-9 ? blueSample.b / blueSample.a : 0), 0L, 255L));
            destination[3] = unwarped[3];
        }
    }
}

} // namespace NativeMotion
