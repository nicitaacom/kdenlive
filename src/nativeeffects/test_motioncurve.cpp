/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "motioncurve.hpp"

#include <algorithm>
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

static Transform anisotropicScale(double, void *)
{
    Transform result;
    result.scaleX = 2.0;
    result.scaleY = 1.0;
    return result;
}

int main()
{
    require(reflectIndex(-1, 4) == 0 && reflectIndex(-2, 4) == 1 && reflectIndex(4, 4) == 3 &&
                reflectIndex(5, 4) == 2 && reflectIndex(11, 4) == 3,
            "reflect mapping failed");
    require(tileIndex(-1, 4) == 3 && tileIndex(4, 4) == 0, "tile mapping failed");
    require(fittedShutterFrames(1.5, 8.0, 1.0, 15, 15) == 12.0,
            "source shutter gain/envelope did not preserve the 15-frame nominal peak");
    require(std::abs(fittedShutterFrames(1.5, 8.0, 1.0, 30, 15) - 12.0 * 29.0 / 14.0) < 1e-12,
            "fitted shutter must stretch with inclusive event endpoints");
    require(fittedShutterFrames(1.5, 8.0, 0.0, 15, 15) == 0.0,
            "zero shutter envelope must turn off path blur");
    require(fittedShutterFrames(1.5, 8.0, 1.0, 1, 15) == 0.0,
            "one-frame event must not create a shutter interval");
    require(fittedShutterFrames(-1.0, 8.0, 1.0, 15, 15) == 0.0 &&
                fittedShutterFrames(NAN, 8.0, 1.0, 15, 15) == 0.0,
            "invalid or negative shutter input must not reach the sampler");
    const std::array<uint8_t, 4> borderSource{255, 0, 0, 255};
    const Pixel blackBorder = sampleRgba(borderSource.data(), 1, 1, -1, 0, 0, 0, false);
    require(blackBorder.r == 0 && blackBorder.a == 1, "no-wrap sampling must use opaque black beyond the source");
    const std::array<uint8_t, 16> bilinearSource{0, 10, 20, 255, 100, 110, 120, 255,
                                                  200, 210, 220, 255, 255, 245, 235, 255};
    const Pixel insideReflect = sampleRgba(bilinearSource.data(), 2, 2, 0.25, 0.5, 2, 2, true);
    const Pixel outsideReflect = sampleRgba(bilinearSource.data(), 2, 2, -0.25, 0.5, 2, 2, true);
    require(std::abs(insideReflect.r - 119.375) < 1e-9 && insideReflect.a == 1.0 &&
                std::abs(outsideReflect.r - 100.0) < 1e-9 && outsideReflect.a == 1.0,
            "fast in-bounds sampling or reflected subpixel edge mapping changed its result");
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
    const Point identityLens = mapMagnify(3, 7, 11, 11, 0.5, 0.5, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1);
    const Point squeezedLens = mapMagnify(3, 7, 11, 11, 0.5, 0.5, 1, 1.5, 0.5, 1, 1, 1, 1, 0, 1, 1);
    require(std::abs(identityLens.x - 3) < 1e-12 && std::abs(identityLens.y - 7) < 1e-12 &&
                squeezedLens.x > 3 && squeezedLens.y > 7,
            "magnify lens must preserve identity and scale independent axes");
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
    const QVector<Key> linearKeys{{0, 0, 0, 0, 0.3, 0.3, 1}, {1, 1, 0.7, 0.7, 1, 1, 0}};
    require(std::abs(evaluateExtrapolated(linearKeys, -0.5, 5) + 0.5) < 1e-5 &&
                std::abs(evaluateExtrapolated(linearKeys, 1.5, 5) - 1.5) < 1e-5,
            "linear endpoint tangent was not extrapolated");
    const QVector<Key> bezierKeys{{0, 0, 0, 0, 0.25, 0.25, 1}, {1, 1, 0.75, 0.5, 1, 1, 0}};
    require(std::abs(evaluateExtrapolated(bezierKeys, -0.1, 5) + 0.1) < 1e-4 &&
                evaluateExtrapolated(bezierKeys, 1.1, 5) > 1.1,
            "Bezier endpoint tangent was not extrapolated");
    const QVector<Key> sparseStartKeys{{0.4, 0.0, 0.4, 0.0, 0.4, 0.0, 0},
                                       {1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0}};
    const QVector<Key> eventEdgeKeys{{0.0, 0.0, 0.0, 0.0, 0.3, 0.3, 1},
                                     {1.0, 1.0, 0.7, 0.7, 1.0, 1.0, 0}};
    require(evaluateEventCurve(sparseStartKeys, 0.0, 5.0) == 0.0 &&
                evaluateEventCurve(sparseStartKeys, 0.2, 5.0) == 0.0 &&
                std::abs(evaluateEventCurve(sparseStartKeys, 0.7, 0.0) - 0.5) < 1e-5 &&
                evaluateEventCurve(sparseStartKeys, -0.1, 5.0) == 0.0,
            "a sparse curve must hold its first key before it begins within the event");
    require(std::abs(evaluateEventCurve(sparseStartKeys, 1.0, 5.0) - 1.0) < 1e-9,
            "a sparse curve must retain its last key through the event endpoint");
    require(std::abs(evaluateEventCurve(eventEdgeKeys, 0.4, 0.0, 0.5, 0.75) - 0.4) < 1e-3 &&
                std::abs(evaluateEventCurve(eventEdgeKeys, 0.8, 0.0, 0.5, 0.75) - 0.8) < 1e-3,
            "a trimmed event must continue the source curve across both split boundaries");
    require(std::abs(evaluateEventCurve(eventEdgeKeys, -0.1, 0.0) + 0.1) < 1e-3 &&
                std::abs(evaluateEventCurve(eventEdgeKeys, 1.1, 0.0) - 1.1) < 1e-3,
            "shutter samples outside the selected event must continue its edge tangent");
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

    settings.samples = 1;
    std::array<uint8_t, 16> horizontallyScaled{};
    renderRgba(source.data(), horizontallyScaled.data(), 4, 1, 0.5, 1, settings, anisotropicScale, nullptr);
    require(horizontallyScaled != source && horizontallyScaled[3] == 255,
            "independent horizontal scale did not change the rendered pixels");

    settings.samples = 16;
    settings.shutterFrames = 1;
    renderRgba(source.data(), blurred.data(), 4, 1, 0.5, 1, settings, motion, nullptr);
    renderRgba(source.data(), repeat.data(), 4, 1, 0.5, 1, settings, motion, nullptr);
    require(blurred == repeat, "render differs on repeated seek");
    require(blurred[3] == 255 && blurred[0] != first[0] && blurred[0] != last[0],
            "shutter integration did not mix trajectory samples");
    std::array<uint8_t, 16> clampedBoundary{};
    std::array<uint8_t, 16> extrapolatedBoundary{};
    renderRgba(source.data(), clampedBoundary.data(), 4, 1, 1.0, 1, settings,
               [](double time, void *opaque) {
                   return motion(std::clamp(time, 0.0, 1.0), opaque);
               }, nullptr);
    renderRgba(source.data(), extrapolatedBoundary.data(), 4, 1, 1.0, 1, settings, motion, nullptr);
    require(clampedBoundary != extrapolatedBoundary,
            "shutter samples past an endpoint were still clamped to the endpoint image");
    return 0;
}
