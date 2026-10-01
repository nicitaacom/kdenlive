/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include "filter_curves.hpp"

#include <array>

namespace NativeMotion {

constexpr int PinchLookupSize = 4096;
using PinchLookup = std::array<double, PinchLookupSize + 1>;

void makePinchLookup(double amount, PinchLookup &lookup);
Point mapPinchPunch(int x, int y, int width, int height, double centerXOffset, double centerYOffset,
                    double horizontal, double vertical, bool proportional, double pixelAspectRatio,
                    const PinchLookup &lookup);

} // namespace NativeMotion
