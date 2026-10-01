/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "pinchwarp.hpp"

#include <algorithm>
#include <cmath>

namespace NativeMotion {

void makePinchLookup(double amount, PinchLookup &lookup)
{
    // VEGAS documents negative Amount as Pinch and positive Amount as Punch.
    // This monotone radial curve keeps the center and image boundary fixed;
    // the original DirectX kernel is proprietary, so this is an explicit CPU
    // reconstruction. The lookup keeps full-frame mapping inexpensive.
    const double k = std::clamp(amount, -1.0, 1.0) * 0.5;
    lookup[0] = 0.0;
    for (int index = 1; index <= PinchLookupSize; ++index) {
        const double target = static_cast<double>(index) / PinchLookupSize;
        double low = 0.0;
        double high = 1.0;
        for (int iteration = 0; iteration < 28; ++iteration) {
            const double source = (low + high) * 0.5;
            const double mapped = source * (1.0 + k * (1.0 - source) * (1.0 - source));
            if (mapped < target) {
                low = source;
            } else {
                high = source;
            }
        }
        lookup[index] = (low + high) * 0.5;
    }
    lookup[PinchLookupSize] = 1.0;
}

Point mapPinchPunch(int x, int y, int width, int height, double centerXOffset, double centerYOffset,
                    double horizontal, double vertical, bool proportional, double pixelAspectRatio,
                    const PinchLookup &lookup)
{
    if (width < 1 || height < 1) {
        return {};
    }
    const double cx = (0.5 + centerXOffset) * width;
    const double cy = (0.5 + centerYOffset) * height;
    const double par = std::isfinite(pixelAspectRatio) && pixelAspectRatio > 0.0 ? pixelAspectRatio : 1.0;
    const double sx = std::clamp(std::isfinite(horizontal) ? horizontal : 1.0, 0.01, 8.0);
    const double sy = proportional ? sx : std::clamp(std::isfinite(vertical) ? vertical : 1.0, 0.01, 8.0);

    const double x0 = -cx * par / sx;
    const double x1 = (width - 1.0 - cx) * par / sx;
    const double y0 = -cy / sy;
    const double y1 = (height - 1.0 - cy) / sy;
    const double radius = std::max({std::hypot(x0, y0), std::hypot(x0, y1),
                                    std::hypot(x1, y0), std::hypot(x1, y1), 1e-9});
    const double nx = (x - cx) * par / (sx * radius);
    const double ny = (y - cy) / (sy * radius);
    const double outRadius = std::clamp(std::hypot(nx, ny), 0.0, 1.0);
    if (outRadius < 1e-12) {
        return {cx, cy};
    }
    const double scaled = outRadius * PinchLookupSize;
    const int lower = std::clamp(static_cast<int>(scaled), 0, PinchLookupSize - 1);
    const double fraction = scaled - lower;
    const double inRadius = lookup[lower] + fraction * (lookup[lower + 1] - lookup[lower]);
    const double radialScale = inRadius / outRadius;
    return {cx + nx * radialScale * radius * sx / par,
            cy + ny * radialScale * radius * sy};
}

} // namespace NativeMotion
