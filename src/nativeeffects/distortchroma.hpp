/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include <cstdint>

namespace NativeMotion {

struct DistortChromaSettings {
    double amount = 0.0;
    double blurLens = 0.0;
    double rotateWarpDegrees = 0.0;
    double warpRed = 0.5;
    double warpBlue = 1.0;
    double amountRelX = 1.0;
    double amountRelY = 1.0;
    int steps = 8;
    int wrapX = 2;
    int wrapY = 2;
    bool subpixel = true;
};

// Reconstruct the lens from source luminance because the Vegas record carries
// no separate Lens input connection. Pixels are straight RGBA on entry/exit.
void renderDistortChroma(const uint8_t *source, uint8_t *output, int width, int height,
                         const DistortChromaSettings &settings);

} // namespace NativeMotion
