/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "bubblewarp.hpp"

#include <cmath>
#include <cstdlib>
#include <iostream>

using namespace NativeMotion;

namespace {
void require(bool condition, const char *message)
{
    if (!condition) {
        std::cerr << "Bubble warp test failed: " << message << '\n';
        std::exit(1);
    }
}
} // namespace

int main()
{
    BubbleWarpSettings settings;
    settings.a.amplitude = 0.0;
    settings.b.amplitude = 0.0;
    for (const Point p : {mapBubbleWarp(0, 0, 160, 90, 0.0, settings),
                          mapBubbleWarp(63, 40, 160, 90, 0.5, settings),
                          mapBubbleWarp(159, 89, 160, 90, 1.0, settings)}) {
        const double x = p.x;
        const double y = p.y;
        require(std::isfinite(x) && std::isfinite(y), "identity coordinates must be finite");
    }
    const Point identity = mapBubbleWarp(63, 40, 160, 90, 0.5, settings);
    require(std::abs(identity.x - 63) < 1e-9 && std::abs(identity.y - 40) < 1e-9,
            "zero amplitude at unit zoom must preserve coordinates");

    settings.a.amplitude = 0.65;
    settings.a.frequency = 4.0;
    settings.a.seed = 5.0;
    settings.b.amplitude = 0.25;
    settings.b.frequency = 3.0;
    settings.b.seed = 0.34;
    bool displaced = false;
    for (int y = 0; y < 90 && !displaced; ++y) {
        for (int x = 0; x < 160 && !displaced; ++x) {
            const Point first = mapBubbleWarp(x, y, 160, 90, 0.5, settings);
            const Point repeated = mapBubbleWarp(x, y, 160, 90, 0.5, settings);
            require(std::abs(first.x - repeated.x) < 1e-12 && std::abs(first.y - repeated.y) < 1e-12,
                    "mapping must be deterministic");
            displaced = std::abs(first.x - x) + std::abs(first.y - y) > 0.01;
        }
    }
    require(displaced, "nonzero amplitudes must displace source coordinates");

    settings.a.amplitude = 0.0;
    settings.b.amplitude = 0.0;
    settings.zDistance = 2.0;
    const Point zoomed = mapBubbleWarp(63, 40, 160, 90, 0.5, settings);
    require(std::abs(zoomed.x - 63) > 1.0 || std::abs(zoomed.y - 40) > 1.0,
            "non-unit z distance must scale coordinates");
    return 0;
}
