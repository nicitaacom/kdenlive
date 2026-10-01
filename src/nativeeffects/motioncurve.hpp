/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include <QByteArray>
#include <QHash>
#include <QVector>
#include <cstdint>

namespace NativeMotion {

struct Key {
    double time = 0;
    double value = 0;
    double inTime = 0;
    double inValue = 0;
    double outTime = 0;
    double outValue = 0;
    int interpolationCode = 0;
};

using Curves = QHash<QByteArray, QVector<Key>>;

Curves parseCurves(const QByteArray &json, bool *valid = nullptr);
double evaluate(const QVector<Key> &keys, double time, double fallback);
double evaluateExtrapolated(const QVector<Key> &keys, double time, double fallback);
double evaluateEventCurve(const QVector<Key> &keys, double time, double fallback,
                          double eventStart = 0.0, double eventEnd = 1.0);
int reflectIndex(int index, int length);
int tileIndex(int index, int length);
double fittedShutterFrames(double sourceShutterFrames, double gain, double envelope,
                           int eventFrames, int nominalFrames);

struct Transform {
    double centerX = 0.5;
    double centerY = 0.5;
    double shiftX = 0;
    double shiftY = 0;
    double scaleX = 1;
    double scaleY = 1;
    double zDistance = 1;
    double rotateDegrees = 0;
};

struct SampleSettings {
    double shutterFrames = 0;
    double shutterShiftFrames = 0;
    double exposureBias = 0.5;
    double brightness = 1;
    int samples = 8;
    int wrapX = 0;
    int wrapY = 0;
    bool subpixel = true;
    double pixelAspectRatio = 1;
};

struct Pixel {
    double r = 0; // premultiplied, on the 0..255 channel scale
    double g = 0;
    double b = 0;
    double a = 0; // 0..1
};

struct Point {
    double x = 0;
    double y = 0;
};

struct WaveWarpSettings {
    double centerX = 0.5;
    double centerY = 0.5;
    double amplitude = 0.0;
    double frequency = 1.0;
    double angleDegrees = 0.0;
    double displacementAngleDegrees = 90.0;
    double phase = 0.0;
    double zoom = 1.0;
    double pixelAspectRatio = 1.0;
};

Pixel sampleRgba(const uint8_t *image, int width, int height, double x, double y,
                 int wrapX, int wrapY, bool subpixel);
Point mapFisheye(int x, int y, int width, int height, double centerX, double centerY,
                 double amount, double zDistance, double rotateDegrees,
                 double shiftOrigX, double shiftOrigY, double pixelAspectRatio);
Point mapAxisStretch(int x, int y, int width, int height, double scaleX, double scaleY,
                     double shiftX, double shiftY, double zDistance);
Point mapMagnify(int x, int y, int width, int height, double centerX, double centerY,
                 double magnifyAmount, double magnifyRelX, double magnifyRelY,
                 double lensRadius, double lensEdgeWidth, double lensRelWidth,
                 double lensRelHeight, double lensRotate, double lensEdgeShape,
                 double pixelAspectRatio);
Point mapWaves(int x, int y, int width, int height, const WaveWarpSettings &settings);

struct CornerPinMapping {
    // Output unit coordinates to source unit coordinates, with denominator 1 + h[6]x + h[7]y.
    double h[8]{};
    double bulgeX = 1;
    double bulgeY = 1;
    bool valid = false;
};

CornerPinMapping makeCornerPin(Point topLeft, Point topRight, Point bottomLeft, Point bottomRight,
                               double bulgeX, double bulgeY);
Point mapCornerPin(const CornerPinMapping &mapping, int x, int y, int width, int height);

using TransformEvaluator = Transform (*)(double time, void *context);

void renderRgba(const uint8_t *source, uint8_t *output, int width, int height,
                double progress, double frameSpan, const SampleSettings &settings,
                TransformEvaluator transformAt, void *context);

} // namespace NativeMotion
