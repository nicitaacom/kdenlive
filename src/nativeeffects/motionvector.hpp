/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include "motioncurve.hpp"

#include <cstdint>
#include <vector>

namespace NativeMotion {

struct MotionVector {
    double x = 0.0;
    double y = 0.0;
};

struct MotionField {
    int columns = 0;
    int rows = 0;
    int tileSize = 32;
    std::vector<MotionVector> vectors;

    MotionVector at(double x, double y) const;
};

// Estimate motion between two *already composited* RGBA frames. Sensitivity is
// a search radius in output pixels; the two-resolution search keeps the CPU
// baseline practical without relying on temporal state or seek order.
MotionField estimateMotion(const uint8_t *current, const uint8_t *neighbor,
                           int width, int height, int sensitivity);

// Apply an optional normalized event envelope to the editable motion blur
// amount. The base amount remains a user control; the envelope shapes only
// how much of that amount is active over the fitted event.
double applyBlurEnvelope(double amount, const Curves &curves, double progress, double adjustment = 1.0);

// Integrate current-frame pixels along the measured vector field. Both the
// reference distance and shutter amount are in displayed project frames.
void renderVectorBlur(const uint8_t *current, uint8_t *output, int width, int height,
                      const MotionField &field, double shutterFrames,
                      int referenceDistance, int samples);

} // namespace NativeMotion
