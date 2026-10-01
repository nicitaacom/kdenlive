/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/
#pragma once

#include <cstdint>

namespace NativeMotion {

struct SpatialTransform {
    double zDistance = 1.0;
    double rotateDegrees = 0.0;
    double shiftX = 0.0;
    double shiftY = 0.0;
};

struct BlurMotionSettings {
    SpatialTransform from;
    SpatialTransform to;
    double centerX = 0.5;
    double centerY = 0.5;
    double brightness = 1.0;
    double exposureBias = 0.5;
    double pixelAspectRatio = 1.0;
    int samples = 17;
    int wrapX = 2;
    int wrapY = 2;
    bool subpixel = true;
};

// Render one source-derived image by accumulating samples along the spatial
// transform segment. From/To are geometry endpoints, not source-video times.
void renderBlurMotion(const uint8_t *source, uint8_t *destination,
                      int width, int height, const BlurMotionSettings &settings);

} // namespace NativeMotion
