/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/
#pragma once

#include <cstdint>

namespace NativeMotion {

struct SpatialBlurSettings {
    int mode = 0; // 0: linear, 1: radial
    int radialType = 1; // 0: proportional, 1: fixed radius, 2: Gaussian weighted
    double amount = 0;
    double angleDegrees = 0;
    double centerX = 0.5;
    double centerY = 0.5;
    double pixelAspectRatio = 1;
    int samples = 17;
};

void renderSpatialBlur(const uint8_t *source, uint8_t *destination,
                       int width, int height, const SpatialBlurSettings &settings);

} // namespace NativeMotion
