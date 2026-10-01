/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "pinchwarp.hpp"

#include <cassert>
#include <cmath>

using namespace NativeMotion;

int main()
{
    PinchLookup identity;
    PinchLookup pinch;
    PinchLookup punch;
    makePinchLookup(0.0, identity);
    makePinchLookup(-1.0, pinch);
    makePinchLookup(1.0, punch);

    for (int index : {0, 1, PinchLookupSize / 4, PinchLookupSize / 2, PinchLookupSize - 1, PinchLookupSize}) {
        const double progress = static_cast<double>(index) / PinchLookupSize;
        assert(std::abs(identity[index] - progress) < 1e-8);
        assert(pinch[index] >= progress - 1e-9);
        assert(punch[index] <= progress + 1e-9);
    }

    const Point center = mapPinchPunch(50, 50, 100, 100, 0, 0, 1, 1, true, 1, pinch);
    assert(std::abs(center.x - 50) < 1e-9 && std::abs(center.y - 50) < 1e-9);
    const Point identityPoint = mapPinchPunch(65, 50, 100, 100, 0, 0, 1, 1, true, 1, identity);
    const Point pinchPoint = mapPinchPunch(65, 50, 100, 100, 0, 0, 1, 1, true, 1, pinch);
    const Point punchPoint = mapPinchPunch(65, 50, 100, 100, 0, 0, 1, 1, true, 1, punch);
    assert(std::abs(identityPoint.x - 65) < 0.001 && std::abs(identityPoint.y - 50) < 0.001);
    assert(pinchPoint.x > identityPoint.x); // Negative Amount pulls picture content inward.
    assert(punchPoint.x < identityPoint.x); // Positive Amount pushes picture content outward.
    assert(std::abs(pinchPoint.y - 50) < 0.001 && std::abs(punchPoint.y - 50) < 0.001);

    const Point corner = mapPinchPunch(0, 0, 100, 100, 0, 0, 1, 1, true, 1, pinch);
    assert(std::abs(corner.x) < 0.001 && std::abs(corner.y) < 0.001);
    const Point shiftedCenter = mapPinchPunch(60, 50, 100, 100, 0.1, 0, 1, 1, true, 1, identity);
    assert(std::abs(shiftedCenter.x - 60) < 0.001 && std::abs(shiftedCenter.y - 50) < 0.001);
    return 0;
}
