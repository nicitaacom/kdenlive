/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "motioncurve.hpp"
#include "parallelrows.hpp"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <algorithm>
#include <cmath>
#include <utility>

namespace NativeMotion {

static double cubic(double p0, double p1, double p2, double p3, double u)
{
    const double inverse = 1.0 - u;
    return inverse * inverse * inverse * p0 + 3.0 * inverse * inverse * u * p1 +
           3.0 * inverse * u * u * p2 + u * u * u * p3;
}

Curves parseCurves(const QByteArray &json, bool *valid)
{
    QJsonParseError error;
    const QJsonDocument doc = QJsonDocument::fromJson(json, &error);
    Curves curves;
    bool ok = error.error == QJsonParseError::NoError && doc.isObject();
    if (ok) {
        const QJsonObject root = doc.object();
        for (auto it = root.begin(); it != root.end() && ok; ++it) {
            if (!it.value().isArray()) {
                ok = false;
                break;
            }
            QVector<Key> keys;
            for (const QJsonValue &value : it.value().toArray()) {
                const QJsonArray point = value.toArray();
                if (point.size() != 7) {
                    ok = false;
                    break;
                }
                if (!std::all_of(point.cbegin(), point.cend(), [](const QJsonValue &entry) { return entry.isDouble(); }) ||
                    std::floor(point[6].toDouble()) != point[6].toDouble()) {
                    ok = false;
                    break;
                }
                Key key{point[0].toDouble(), point[1].toDouble(), point[2].toDouble(),
                        point[3].toDouble(), point[4].toDouble(), point[5].toDouble(), point[6].toInt()};
                if (!std::isfinite(key.time) || !std::isfinite(key.value) || !std::isfinite(key.inTime) ||
                    !std::isfinite(key.inValue) || !std::isfinite(key.outTime) || !std::isfinite(key.outValue) ||
                    key.time < 0 || key.time > 1 || key.interpolationCode < 0 || key.interpolationCode > 2) {
                    ok = false;
                    break;
                }
                keys.push_back(key);
            }
            if (!std::is_sorted(keys.cbegin(), keys.cend(), [](const Key &a, const Key &b) { return a.time < b.time; }) ||
                std::adjacent_find(keys.cbegin(), keys.cend(), [](const Key &a, const Key &b) { return a.time == b.time; }) != keys.cend()) {
                ok = false;
            }
            if (!keys.isEmpty()) {
                curves.insert(it.key().toUtf8(), keys);
            }
        }
    }
    if (valid) {
        *valid = ok;
    }
    if (!ok) {
        curves.clear();
    }
    return curves;
}

double evaluate(const QVector<Key> &keys, double time, double fallback)
{
    if (keys.isEmpty()) {
        return fallback;
    }
    if (time <= keys.first().time) {
        return keys.first().value;
    }
    if (time >= keys.last().time) {
        return keys.last().value;
    }
    auto next = std::upper_bound(keys.cbegin(), keys.cend(), time,
                                 [](double t, const Key &key) { return t < key.time; });
    const Key &right = *next;
    const Key &left = *(next - 1);
    if (right.time <= left.time) {
        return right.value;
    }
    // These are native curve types, not the still-unknown source numeric codes.
    // A type belongs to the segment leaving the left key.
    if (left.interpolationCode == 2) {
        return left.value;
    }
    if (left.interpolationCode == 0) {
        const double fraction = (time - left.time) / (right.time - left.time);
        return left.value + fraction * (right.value - left.value);
    }
    // Explicit native Bezier segment. Solve its time axis before evaluating
    // the value axis, preserving subframe motion without rounded keyframes.
    const double x1 = std::clamp(left.outTime, left.time, right.time);
    const double x2 = std::clamp(right.inTime, left.time, right.time);
    double lower = 0.0;
    double upper = 1.0;
    for (int iteration = 0; iteration < 24; ++iteration) {
        const double mid = (lower + upper) * 0.5;
        if (cubic(left.time, x1, x2, right.time, mid) < time) {
            lower = mid;
        } else {
            upper = mid;
        }
    }
    return cubic(left.value, left.outValue, right.inValue, right.value, (lower + upper) * 0.5);
}

double evaluateExtrapolated(const QVector<Key> &keys, double time, double fallback)
{
    if (keys.isEmpty()) {
        return fallback;
    }
    if (keys.size() < 2 || (time >= keys.first().time && time <= keys.last().time)) {
        return evaluate(keys, time, fallback);
    }

    const bool before = time < keys.first().time;
    const Key &left = before ? keys[0] : keys[keys.size() - 2];
    const Key &right = before ? keys[1] : keys.last();
    const double dt = right.time - left.time;
    if (dt <= 0) {
        return before ? left.value : right.value;
    }
    if (left.interpolationCode == 2) {
        return before ? left.value : right.value;
    }
    if (left.interpolationCode == 0) {
        const double slope = (right.value - left.value) / dt;
        return (before ? left.value : right.value) +
               (time - (before ? left.time : right.time)) * slope;
    }

    // Continue the endpoint tangent of an explicit Bezier segment. The time
    // handles are clamped the same way as in evaluate(); when an endpoint
    // handle is vertical, fall back to the nearest finite secant.
    const double x1 = std::clamp(left.outTime, left.time, right.time);
    const double x2 = std::clamp(right.inTime, left.time, right.time);
    const double startDx = x1 - left.time;
    const double startDy = left.outValue - left.value;
    const double endDx = right.time - x2;
    const double endDy = right.value - right.inValue;
    double slope = 0;
    if (before) {
        if (std::abs(startDx) > 1e-12) {
            slope = startDy / startDx;
        } else if (std::abs(right.time - x2) > 1e-12) {
            slope = (right.inValue - left.value) / (x2 - left.time);
        } else {
            slope = (right.value - left.value) / dt;
        }
        return left.value + (time - left.time) * slope;
    }
    if (std::abs(endDx) > 1e-12) {
        slope = endDy / endDx;
    } else if (std::abs(x1 - left.time) > 1e-12) {
        slope = (right.value - left.outValue) / (right.time - x1);
    } else {
        slope = (right.value - left.value) / dt;
    }
    return right.value + (time - right.time) * slope;
}

double evaluateEventCurve(const QVector<Key> &keys, double time, double fallback,
                          double eventStart, double eventEnd)
{
    if (keys.isEmpty()) {
        return fallback;
    }
    if (!std::isfinite(time)) {
        return fallback;
    }
    if (!std::isfinite(eventStart) || !std::isfinite(eventEnd) || eventEnd <= eventStart) {
        return evaluate(keys, time, fallback);
    }
    const auto valueAtEventTime = [&](double position) {
        // The animated track owns its value even where the first key is
        // sparse: hold that key before it, and hold the last key after it.
        // The serialized static property is commonly the last edited value,
        // not a trustworthy event-start value for an animated parameter.
        return evaluate(keys, position, fallback);
    };
    if (time >= eventStart && time <= eventEnd) {
        // Keys that start or end inside the selected event hold their nearest
        // animated endpoint through unkeyed time. Do not extrapolate a
        // key-to-key slope across unkeyed clip time.
        return valueAtEventTime(time);
    }

    const bool before = time < eventStart;
    const double endpoint = before ? eventStart : eventEnd;
    const double value = valueAtEventTime(endpoint);
    const double epsilon = std::min(1e-5, (eventEnd - eventStart) * 1e-3);
    if (epsilon <= 0.0) {
        return value;
    }
    // Extend the effective event edge for shutter samples only. This preserves
    // motion blur across a moving cut while a sparse track with no motion at
    // the event edge has a zero tangent there.
    const double neighbor = before ? endpoint + epsilon : endpoint - epsilon;
    const double neighboringValue = valueAtEventTime(neighbor);
    const double slope = before ? (neighboringValue - value) / epsilon
                                : (value - neighboringValue) / epsilon;
    return value + (time - endpoint) * slope;
}

int reflectIndex(int index, int length)
{
    if (length <= 1) {
        return 0;
    }
    const int period = length * 2;
    int wrapped = index % period;
    if (wrapped < 0) {
        wrapped += period;
    }
    return wrapped < length ? wrapped : period - 1 - wrapped;
}

int tileIndex(int index, int length)
{
    if (length <= 1) {
        return 0;
    }
    int wrapped = index % length;
    return wrapped < 0 ? wrapped + length : wrapped;
}

double fittedShutterFrames(double sourceShutterFrames, double gain, double envelope,
                           int eventFrames, int nominalFrames)
{
    if (eventFrames <= 1 || !std::isfinite(sourceShutterFrames) || !std::isfinite(gain) ||
        !std::isfinite(envelope)) {
        return 0.0;
    }
    const double eventSpan = static_cast<double>(std::max(1, eventFrames - 1));
    const double nominalSpan = static_cast<double>(std::max(1, nominalFrames - 1));
    const double fitted = sourceShutterFrames * std::max(0.0, gain) * std::max(0.0, envelope) * eventSpan / nominalSpan;
    return std::isfinite(fitted) ? std::max(0.0, fitted) : 0.0;
}

static Pixel tap(const uint8_t *image, int width, int height, int x, int y, int wrapX, int wrapY)
{
    if (wrapX == 2) {
        // Most samples stay inside the image. Avoid the signed modulo in
        // reflectIndex() for that common path; the result is exactly x there.
        if (x < 0 || x >= width) {
            x = reflectIndex(x, width);
        }
    } else if (wrapX == 1) {
        if (x < 0 || x >= width) {
            x = tileIndex(x, width);
        }
    } else if (x < 0 || x >= width) {
        return {0, 0, 0, 1};
    }
    if (wrapY == 2) {
        if (y < 0 || y >= height) {
            y = reflectIndex(y, height);
        }
    } else if (wrapY == 1) {
        if (y < 0 || y >= height) {
            y = tileIndex(y, height);
        }
    } else if (y < 0 || y >= height) {
        return {0, 0, 0, 1};
    }
    const uint8_t *input = image + (static_cast<size_t>(y) * width + x) * 4;
    const double alpha = input[3] / 255.0;
    return {input[0] * alpha, input[1] * alpha, input[2] * alpha, alpha};
}

Pixel sampleRgba(const uint8_t *image, int width, int height, double x, double y,
                 int wrapX, int wrapY, bool subpixel)
{
    if (!subpixel) {
        return tap(image, width, height, static_cast<int>(std::round(x)), static_cast<int>(std::round(y)),
                   wrapX, wrapY);
    }
    const int left = static_cast<int>(std::floor(x));
    const int top = static_cast<int>(std::floor(y));
    const double fx = x - left;
    const double fy = y - top;
    const Pixel p00 = tap(image, width, height, left, top, wrapX, wrapY);
    const Pixel p10 = tap(image, width, height, left + 1, top, wrapX, wrapY);
    const Pixel p01 = tap(image, width, height, left, top + 1, wrapX, wrapY);
    const Pixel p11 = tap(image, width, height, left + 1, top + 1, wrapX, wrapY);
    const double a = (1 - fx) * (1 - fy);
    const double b = fx * (1 - fy);
    const double c = (1 - fx) * fy;
    const double d = fx * fy;
    return {a * p00.r + b * p10.r + c * p01.r + d * p11.r,
            a * p00.g + b * p10.g + c * p01.g + d * p11.g,
            a * p00.b + b * p10.b + c * p01.b + d * p11.b,
            a * p00.a + b * p10.a + c * p01.a + d * p11.a};
}

Point mapFisheye(int x, int y, int width, int height, double centerX, double centerY,
                 double amount, double zDistance, double rotateDegrees,
                 double shiftOrigX, double shiftOrigY, double pixelAspectRatio)
{
    const double aspect = pixelAspectRatio > 0 ? pixelAspectRatio : 1.0;
    const double cx = centerX * width - 0.5;
    const double cy = centerY * height - 0.5;
    const double radians = rotateDegrees * (3.14159265358979323846 / 180.0);
    const double cosine = std::cos(radians);
    const double sine = std::sin(radians);
    const double dx = (x - cx) * aspect;
    const double dy = y - cy;
    const double distance = std::max(0.001, zDistance);
    const double rx = (cosine * dx + sine * dy) * distance;
    const double ry = (-sine * dx + cosine * dy) * distance;
    const double radius = std::hypot(rx, ry);
    const double maximumRadius = std::max(1.0, std::hypot(width * aspect * 0.5, height * 0.5));
    const double normalizedRadius = radius / maximumRadius;
    // A native radial reconstruction: positive amount expands the center,
    // negative amount compresses it, and the outer reference radius remains
    // stationary. Sapphire's exact radial kernel is not public.
    const double exponent = std::clamp(-amount * (1.0 - normalizedRadius * normalizedRadius), -20.0, 20.0);
    const double factor = std::exp(exponent);
    return {cx + rx * factor / aspect - shiftOrigX * width,
            cy + ry * factor - shiftOrigY * height};
}

Point mapAxisStretch(int x, int y, int width, int height, double scaleX, double scaleY,
                     double shiftX, double shiftY, double zDistance)
{
    const double cx = (width - 1) * 0.5;
    const double cy = (height - 1) * 0.5;
    return {cx + (x - cx - shiftX * width) * zDistance / scaleX,
            cy + (y - cy - shiftY * height) * zDistance / scaleY};
}

Point mapMagnify(int x, int y, int width, int height, double centerX, double centerY,
                 double magnifyAmount, double magnifyRelX, double magnifyRelY,
                 double lensRadius, double lensEdgeWidth, double lensRelWidth,
                 double lensRelHeight, double lensRotate, double lensEdgeShape,
                 double pixelAspectRatio)
{
    const double aspect = pixelAspectRatio > 0 ? pixelAspectRatio : 1.0;
    const double cx = centerX * width - 0.5;
    const double cy = (1.0 - centerY) * height - 0.5;
    const double radians = lensRotate * (3.14159265358979323846 / 180.0);
    const double cosine = std::cos(radians);
    const double sine = std::sin(radians);
    const double dx = (x - cx) * aspect;
    const double dy = y - cy;
    const double rx = cosine * dx + sine * dy;
    const double ry = -sine * dx + cosine * dy;
    const double reference = std::max(1.0, std::min(width * aspect, static_cast<double>(height)) * 0.5);
    const double radiusX = std::max(0.001, lensRadius * lensRelWidth * reference);
    const double radiusY = std::max(0.001, lensRadius * lensRelHeight * reference);
    const double normalizedRadius = std::hypot(rx / radiusX, ry / radiusY);
    double weight = 1.0;
    if (normalizedRadius > 1.0) {
        const double edge = std::max(1e-6, lensEdgeWidth);
        weight = std::clamp(1.0 - (normalizedRadius - 1.0) / edge, 0.0, 1.0);
        // The source's Edge Shape=1 has a smooth taper. Other values blend
        // toward a linear taper. The proprietary kernel is not public.
        const double smooth = weight * weight * (3.0 - 2.0 * weight);
        weight = (1.0 - std::clamp(lensEdgeShape, 0.0, 1.0)) * weight +
                 std::clamp(lensEdgeShape, 0.0, 1.0) * smooth;
    }
    const double scaleX = std::max(0.001, magnifyAmount * magnifyRelX);
    const double scaleY = std::max(0.001, magnifyAmount * magnifyRelY);
    const double sourceRX = rx * (1.0 - weight + weight / scaleX);
    const double sourceRY = ry * (1.0 - weight + weight / scaleY);
    return {cx + (cosine * sourceRX - sine * sourceRY) / aspect,
            cy + sine * sourceRX + cosine * sourceRY};
}

Point mapWaves(int x, int y, int width, int height, const WaveWarpSettings &settings)
{
    const double aspect = std::isfinite(settings.pixelAspectRatio) && settings.pixelAspectRatio > 0
                              ? settings.pixelAspectRatio : 1.0;
    const double zoom = std::isfinite(settings.zoom) ? std::max(0.001, settings.zoom) : 1.0;
    const double cx = settings.centerX * width - 0.5;
    const double cy = settings.centerY * height - 0.5;
    const double shortestSide = std::max(1.0, std::min(width * aspect, static_cast<double>(height)));
    const double angle = settings.angleDegrees * (3.14159265358979323846 / 180.0);
    const double displacementAngle = (settings.angleDegrees + settings.displacementAngleDegrees) *
                                     (3.14159265358979323846 / 180.0);
    const double worldX = (x - cx) * aspect;
    const double worldY = cy - y;
    const double phase = 2.0 * 3.14159265358979323846 *
                         (settings.frequency * (worldX * std::cos(angle) + worldY * std::sin(angle)) / shortestSide +
                          settings.phase);
    const double displacement = settings.amplitude * shortestSide * std::sin(phase);
    const double sourceWorldX = worldX / zoom - displacement * std::cos(displacementAngle);
    const double sourceWorldY = worldY / zoom - displacement * std::sin(displacementAngle);
    return {cx + sourceWorldX / aspect, cy - sourceWorldY};
}

CornerPinMapping makeCornerPin(Point topLeft, Point topRight, Point bottomLeft, Point bottomRight,
                               double bulgeX, double bulgeY)
{
    CornerPinMapping mapping;
    mapping.bulgeX = bulgeX;
    mapping.bulgeY = bulgeY;
    // The source coordinates are normalized with Y increasing upward. Convert
    // the supplied corner locations to output image coordinates (Y downward).
    const Point output[4] = {{topLeft.x, 1 - topLeft.y}, {topRight.x, 1 - topRight.y},
                             {bottomLeft.x, 1 - bottomLeft.y}, {bottomRight.x, 1 - bottomRight.y}};
    const Point source[4] = {{0, 0}, {1, 0}, {0, 1}, {1, 1}};
    const Point quad[4] = {output[0], output[1], output[3], output[2]};
    double orientation = 0;
    for (int i = 0; i < 4; ++i) {
        const Point &a = quad[i];
        const Point &b = quad[(i + 1) % 4];
        const Point &c = quad[(i + 2) % 4];
        const double cross = (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x);
        if (std::abs(cross) < 1e-10 || (orientation != 0 && cross * orientation < 0)) {
            return mapping;
        }
        orientation = cross;
    }
    double system[8][9]{};
    for (int i = 0; i < 4; ++i) {
        const double x = output[i].x;
        const double y = output[i].y;
        const double u = source[i].x;
        const double v = source[i].y;
        double *horizontal = system[i * 2];
        double *vertical = system[i * 2 + 1];
        horizontal[0] = x; horizontal[1] = y; horizontal[2] = 1;
        horizontal[6] = -u * x; horizontal[7] = -u * y; horizontal[8] = u;
        vertical[3] = x; vertical[4] = y; vertical[5] = 1;
        vertical[6] = -v * x; vertical[7] = -v * y; vertical[8] = v;
    }
    // Solve the eight homography coefficients with partial pivoting. A folded
    // or degenerate quadrilateral is rejected rather than producing NaNs.
    for (int column = 0; column < 8; ++column) {
        int pivot = column;
        for (int row = column + 1; row < 8; ++row) {
            if (std::abs(system[row][column]) > std::abs(system[pivot][column])) {
                pivot = row;
            }
        }
        if (std::abs(system[pivot][column]) < 1e-10) {
            return mapping;
        }
        for (int index = column; index < 9; ++index) {
            std::swap(system[column][index], system[pivot][index]);
        }
        const double diagonal = system[column][column];
        for (int index = column; index < 9; ++index) {
            system[column][index] /= diagonal;
        }
        for (int row = 0; row < 8; ++row) {
            if (row == column) {
                continue;
            }
            const double factor = system[row][column];
            for (int index = column; index < 9; ++index) {
                system[row][index] -= factor * system[column][index];
            }
        }
    }
    for (int i = 0; i < 8; ++i) {
        mapping.h[i] = system[i][8];
    }
    mapping.valid = true;
    return mapping;
}

static double signedPower(double value, double exponent)
{
    return std::copysign(std::pow(std::abs(value), exponent), value);
}

Point mapCornerPin(const CornerPinMapping &mapping, int x, int y, int width, int height)
{
    if (!mapping.valid || width <= 0 || height <= 0) {
        return {NAN, NAN};
    }
    const double px = width > 1 ? static_cast<double>(x) / (width - 1) : 0.5;
    const double py = height > 1 ? static_cast<double>(y) / (height - 1) : 0.5;
    const double denominator = 1 + mapping.h[6] * px + mapping.h[7] * py;
    if (std::abs(denominator) < 1e-10) {
        return {NAN, NAN};
    }
    const double u = (mapping.h[0] * px + mapping.h[1] * py + mapping.h[2]) / denominator;
    const double v = (mapping.h[3] * px + mapping.h[4] * py + mapping.h[5]) / denominator;
    // A native reconstruction of the documented bulge direction: 1 is
    // identity, values below 1 draw the image toward the upper/right corner.
    // Sapphire's exact nonlinear kernel is not published.
    const double exponentX = std::max(0.1, 1 + 0.75 * (1 - mapping.bulgeX));
    const double exponentY = std::max(0.1, 1 + 0.75 * (1 - mapping.bulgeY));
    const double bentX = signedPower(u, exponentX);
    const double bentY = 1 - signedPower(1 - v, exponentY);
    return {bentX * (width - 1), bentY * (height - 1)};
}

void renderRgba(const uint8_t *source, uint8_t *output, int width, int height,
                double progress, double frameSpan, const SampleSettings &settings,
                TransformEvaluator transformAt, void *context)
{
    if (!source || !output || width <= 0 || height <= 0 || !transformAt) {
        return;
    }
    const int samples = std::clamp(settings.samples, 1, 64);
    const double aspect = settings.pixelAspectRatio > 0 ? settings.pixelAspectRatio : 1.0;
    const double shutter = frameSpan > 0 ? settings.shutterFrames / frameSpan : 0;
    const double shift = frameSpan > 0 ? settings.shutterShiftFrames / frameSpan : 0;
    const double exposure = std::clamp(settings.exposureBias, 0.0, 1.0);
    struct State { Transform transform; double cosine; double sine; double weight; };
    QVector<State> states;
    states.reserve(samples);
    double totalWeight = 0;
    for (int index = 0; index < samples; ++index) {
        const double sampleFraction = (index + 0.5) / samples;
        // The shutter continues the endpoint trajectory across the event
        // boundary. Clamping here creates a pile-up of samples at the final
        // transform and can make the first/last transition frames look sharp.
        // evaluateExtrapolated() continues the curve tangent for these samples.
        const double t = progress + shift + (sampleFraction - 0.5) * shutter;
        const Transform transform = transformAt(t, context);
        const double radians = transform.rotateDegrees * (3.14159265358979323846 / 180.0);
        const double weight = std::max(0.0, 1.0 + (2.0 * exposure - 1.0) * (2.0 * sampleFraction - 1.0));
        states.push_back({transform, std::cos(radians), std::sin(radians), weight});
        totalWeight += weight;
    }
    if (totalWeight <= 0) {
        totalWeight = 1;
    }
    parallelRows(height, [&](int y) {
        for (int x = 0; x < width; ++x) {
            Pixel accumulated;
            for (const State &state : std::as_const(states)) {
                const Transform &tr = state.transform;
                const double cx = tr.centerX * width - 0.5;
                const double cy = tr.centerY * height - 0.5;
                const double dx = (x - cx - tr.shiftX * width) * aspect;
                const double dy = y - cy - tr.shiftY * height;
                const double distance = std::max(0.001, tr.zDistance);
                const double scaleX = std::max(0.001, tr.scaleX);
                const double scaleY = std::max(0.001, tr.scaleY);
                const double sx = cx + (state.cosine * dx + state.sine * dy) * distance / (aspect * scaleX);
                const double sy = cy + (-state.sine * dx + state.cosine * dy) * distance / scaleY;
                const Pixel p = sampleRgba(source, width, height, sx, sy,
                                           settings.wrapX, settings.wrapY, settings.subpixel);
                accumulated.r += p.r * state.weight;
                accumulated.g += p.g * state.weight;
                accumulated.b += p.b * state.weight;
                accumulated.a += p.a * state.weight;
            }
            const double alpha = accumulated.a / totalWeight;
            uint8_t *destination = output + (static_cast<size_t>(y) * width + x) * 4;
            const double brightness = std::max(0.0, settings.brightness);
            auto channel = [&](double weighted) {
                return static_cast<uint8_t>(std::clamp(std::round(alpha > 1e-9 ? weighted / accumulated.a * brightness : 0.0), 0.0, 255.0));
            };
            destination[0] = channel(accumulated.r);
            destination[1] = channel(accumulated.g);
            destination[2] = channel(accumulated.b);
            destination[3] = static_cast<uint8_t>(std::clamp(std::round(alpha * 255.0), 0.0, 255.0));
        }
    });
}

} // namespace NativeMotion
