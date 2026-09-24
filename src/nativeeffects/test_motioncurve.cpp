/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "motioncurve.hpp"

#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

using namespace NativeMotion;

static void require(bool condition, const char *message)
{
    if (!condition) {
        std::fprintf(stderr, "%s\n", message);
        std::exit(1);
    }
}

static Transform motion(double time, void *)
{
    Transform result;
    result.shiftX = time * 0.5;
    return result;
}

int main()
{
    require(reflectIndex(-1, 4) == 0 && reflectIndex(-2, 4) == 1 && reflectIndex(4, 4) == 3 &&
                reflectIndex(5, 4) == 2 && reflectIndex(11, 4) == 3,
            "reflect mapping failed");
    require(tileIndex(-1, 4) == 3 && tileIndex(4, 4) == 0, "tile mapping failed");
    const std::array<uint8_t, 4> borderSource{255, 0, 0, 255};
    const Pixel blackBorder = sampleRgba(borderSource.data(), 1, 1, -1, 0, 0, 0, false);
    require(blackBorder.r == 0 && blackBorder.a == 1, "no-wrap sampling must use opaque black beyond the source");
    const Point identityWarp = mapFisheye(1, 1, 4, 4, 0.5, 0.5, 0, 1, 0, 0, 0, 1);
    require(std::abs(identityWarp.x - 1) < 1e-12 && std::abs(identityWarp.y - 1) < 1e-12,
            "zero fisheye amount changed pixel position");
    const Point expanded = mapFisheye(1, 1, 4, 4, 0.5, 0.5, 1, 1, 0, 0, 0, 1);
    const Point compressed = mapFisheye(1, 1, 4, 4, 0.5, 0.5, -1, 1, 0, 0, 0, 1);
    require(expanded.x > identityWarp.x && expanded.x < 1.5 && compressed.x < identityWarp.x,
            "fisheye amount has wrong nonlinear direction");
    const Point identityStretch = mapAxisStretch(0, 3, 5, 5, 1, 1, 0, 0, 1);
    const Point wider = mapAxisStretch(0, 3, 5, 5, 2, 1, 0, 0, 1);
    const Point taller = mapAxisStretch(0, 3, 5, 5, 1, 2, 0, 0, 1);
    require(identityStretch.x == 0 && identityStretch.y == 3 && wider.x == 1 && wider.y == 3 &&
                taller.x == 0 && taller.y == 2.5,
            "axis stretch must scale the selected axis around the image center");
    const CornerPinMapping identityPin = makeCornerPin({0, 1}, {1, 1}, {0, 0}, {1, 0}, 1, 1);
    const Point identityPinned = mapCornerPin(identityPin, 3, 7, 11, 11);
    require(identityPin.valid && std::abs(identityPinned.x - 3) < 1e-10 &&
                std::abs(identityPinned.y - 7) < 1e-10, "identity corner pin changed source coordinates");
    const CornerPinMapping perspectivePin = makeCornerPin({0, 1}, {0.8, 1}, {0, 0}, {1, 0}, 1, 1);
    const Point movedCorner = mapCornerPin(perspectivePin, 8, 0, 11, 11);
    require(perspectivePin.valid && std::abs(movedCorner.x - 10) < 1e-9 &&
                std::abs(movedCorner.y) < 1e-9, "corner pin does not map edited corner to source corner");
    const CornerPinMapping bulgedPin = makeCornerPin({0, 1}, {1, 1}, {0, 0}, {1, 0}, 0, 0);
    const Point bentCenter = mapCornerPin(bulgedPin, 5, 5, 11, 11);
    require(bentCenter.x < 5 && bentCenter.y > 5, "bulge does not move image toward upper/right");
    require(!makeCornerPin({0, 1}, {0, 1}, {0, 0}, {1, 0}, 1, 1).valid,
            "degenerate pin must be rejected");
    bool valid = false;
    Curves curves = parseCurves(R"({"shift_x":[[0,0,0,0,0.1,0,0],[1,1,0.9,1,1,1,0]]})", &valid);
    require(valid && curves.contains("shift_x"), "curve parse failed");
    const QVector<Key> keys = curves.value("shift_x");
    require(evaluate(keys, -1, 5) == 0 && evaluate(keys, 2, 5) == 1 &&
                std::abs(evaluate(keys, 0.5, 5) - 0.5) < 1e-5,
            "continuous curve evaluation failed");
    parseCurves("{broken", &valid);
    require(!valid, "invalid curves must be rejected");
    parseCurves(R"({"shift_x":[[0,0,0,0,0,0,4]]})", &valid);
    require(!valid, "source interpolation codes cannot be passed as native types");
    parseCurves(R"({"shift_x":[[0,"bad",0,0,0,0,0]]})", &valid);
    require(!valid, "non-numeric curve fields must be rejected");
    parseCurves(R"({"shift_x":[[0,0,0,0,0,0,0],[0,1,0,1,0,1,0]]})", &valid);
    require(!valid, "colliding normalized key times must be rejected");
    curves = parseCurves(R"({"shift_x":[[0,0,0,0,0,0,2],[1,1,1,1,1,1,0]]})", &valid);
    require(valid && evaluate(curves.value("shift_x"), 0.5, 5) == 0, "native hold segment failed");

    const std::array<uint8_t, 16> source{255, 0, 0, 255, 0, 255, 0, 255,
                                          0, 0, 255, 255, 255, 255, 0, 255};
    std::array<uint8_t, 16> first{};
    std::array<uint8_t, 16> last{};
    std::array<uint8_t, 16> blurred{};
    std::array<uint8_t, 16> repeat{};
    SampleSettings settings;
    settings.samples = 1;
    settings.wrapX = 2;
    settings.wrapY = 2;
    renderRgba(source.data(), first.data(), 4, 1, 0, 1, settings, motion, nullptr);
    renderRgba(source.data(), last.data(), 4, 1, 1, 1, settings, motion, nullptr);
    require(first == source, "identity endpoint changed source pixels");
    require(last[0] == 0 && last[1] == 255 && last[2] == 0 && last[3] == 255,
            "translated reflected endpoint has wrong source pixel");

    settings.samples = 16;
    settings.shutterFrames = 1;
    renderRgba(source.data(), blurred.data(), 4, 1, 0.5, 1, settings, motion, nullptr);
    renderRgba(source.data(), repeat.data(), 4, 1, 0.5, 1, settings, motion, nullptr);
    require(blurred == repeat, "render differs on repeated seek");
    require(blurred[3] == 255 && blurred[0] != first[0] && blurred[0] != last[0],
            "shutter integration did not mix trajectory samples");
    return 0;
}
