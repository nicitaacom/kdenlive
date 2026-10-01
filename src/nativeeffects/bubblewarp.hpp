/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include "motioncurve.hpp"

namespace NativeMotion {

struct BubbleSetSettings {
    double amplitude = 0.0; // Fraction of the smaller frame dimension.
    double frequency = 1.0; // Bubble cells across normalized image width/height.
    int octaves = 1;
    double seed = 0.23;
    double shiftStartX = 0.0;
    double shiftStartY = 0.0;
    double speedX = 0.0;
    double speedY = 0.0;
};

struct BubbleWarpSettings {
    BubbleSetSettings a;
    BubbleSetSettings b;
    double zDistance = 1.0;
    double pixelAspectRatio = 1.0;
    int nominalFrames = 20;
};

Point mapBubbleWarp(double x, double y, int width, int height, double progress,
                    const BubbleWarpSettings &settings);

} // namespace NativeMotion
