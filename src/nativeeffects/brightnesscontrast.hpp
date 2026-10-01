/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace NativeMotion {

inline void applyBrightnessContrast(uint8_t *rgba, int width, int height,
                                    double brightness, double contrast, double center)
{
    if (!rgba || width < 1 || height < 1) {
        return;
    }
    const double offset = brightness * 255.0;
    const double multiplier = std::max(0.0, 1.0 + 2.0 * contrast);
    const double pivot = std::clamp(center, 0.0, 1.0) * 255.0;
    const size_t pixels = static_cast<size_t>(width) * static_cast<size_t>(height);
    for (size_t index = 0; index < pixels; ++index) {
        uint8_t *pixel = rgba + index * 4;
        if (pixel[3] == 0) {
            pixel[0] = pixel[1] = pixel[2] = 0;
            continue;
        }
        for (int channel = 0; channel < 3; ++channel) {
            const double adjusted = (static_cast<double>(pixel[channel]) - pivot) * multiplier + pivot + offset;
            pixel[channel] = static_cast<uint8_t>(std::clamp(std::lround(adjusted), 0L, 255L));
        }
    }
}

} // namespace NativeMotion
