/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "filter_curves.hpp"

#include <cmath>
#include <cstdio>

using NativeMotion::FilterCurveContext;
using NativeMotion::Curves;
using NativeMotion::Key;
using NativeMotion::WaveWarpSettings;
using NativeMotion::animatedAt;
using NativeMotion::frameParameter;
using NativeMotion::fittedProgress;
using NativeMotion::mapWaves;

int main()
{
    mlt_properties original = mlt_properties_new();
    mlt_properties left = mlt_properties_new();
    mlt_properties right = mlt_properties_new();
    mlt_properties_set(original, "edit", "0=0;62=0.2;124=0.4");
    mlt_properties_set(left, "edit", "0=0;61=0.1967741935483871");
    mlt_properties_set(right, "edit", "62=0.2;124=0.4");
    FilterCurveContext whole{{}, original, 125, 0, 125, 0.0, 1.0};
    FilterCurveContext first{{}, left, 62, 0, 62, 0.0, 61.0 / 124.0};
    FilterCurveContext second{{}, right, 63, 62, 125, 62.0 / 124.0, 1.0};
    bool passed = true;
    mlt_properties_set(left, "native_event_role", "outgoing");
    mlt_properties_set(right, "native_event_role", "incoming");
    mlt_properties_set_double(left, "sparse_shift", 5.0);
    Curves sparseCurve;
    sparseCurve.insert("sparse_shift", {{0.4, 0.0, 0.4, 0.0, 0.4, 0.0, 0},
                                         {1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0}});
    if (frameParameter(left, sparseCurve, "sparse_shift", 0.0, 0, 62, 0.0, false) != 0.0 ||
        frameParameter(left, sparseCurve, "sparse_shift", 0.2, 0, 62, 0.0, false) != 0.0 ||
        std::abs(frameParameter(left, sparseCurve, "sparse_shift", 0.7, 0, 62, 0.0, false) - 0.5) > 1e-5) {
        std::fprintf(stderr, "a sparse source curve did not hold its first key before the key begins\n");
        passed = false;
    }
    if (fittedProgress(left, 0, 1) != 1.0 || fittedProgress(right, 0, 1) != 0.0) {
        std::fprintf(stderr, "one-frame event did not select outgoing/incoming role endpoints\n");
        passed = false;
    }
    if (fittedProgress(left, 0, 2) != 0.0 || fittedProgress(left, 1, 2) != 1.0 ||
        fittedProgress(right, 0, 2) != 0.0 || fittedProgress(right, 1, 2) != 1.0) {
        std::fprintf(stderr, "multi-frame event endpoints are not inclusive\n");
        passed = false;
    }
    WaveWarpSettings wave;
    const auto identity = mapWaves(173, 81, 320, 180, wave);
    if (std::abs(identity.x - 173.0) > 1e-9 || std::abs(identity.y - 81.0) > 1e-9) {
        std::fprintf(stderr, "zero-amplitude wave warp is not identity\n");
        passed = false;
    }
    wave.amplitude = 0.04;
    wave.frequency = 2.5;
    wave.angleDegrees = -45.0;
    wave.displacementAngleDegrees = 20.0;
    wave.phase = 0.3;
    wave.pixelAspectRatio = 1.2;
    const auto displaced = mapWaves(173, 81, 320, 180, wave);
    const auto repeated = mapWaves(173, 81, 320, 180, wave);
    if (!std::isfinite(displaced.x) || !std::isfinite(displaced.y) ||
        (std::abs(displaced.x - 173.0) < 0.01 && std::abs(displaced.y - 81.0) < 0.01)) {
        std::fprintf(stderr, "animated wave warp did not displace source coordinates\n");
        passed = false;
    }
    if (displaced.x != repeated.x || displaced.y != repeated.y) {
        std::fprintf(stderr, "wave mapping is not deterministic across seeks\n");
        passed = false;
    }
    for (int frame = 56; frame <= 68; ++frame) {
        const double time = frame / 124.0;
        const double expected = animatedAt(whole, "edit", time);
        const double actual = frame < 62 ? animatedAt(first, "edit", time) : animatedAt(second, "edit", time);
        if (std::abs(expected - actual) > 1e-6) {
            std::fprintf(stderr, "split adjustment differs at frame %d: %.9f versus %.9f\n", frame, actual, expected);
            passed = false;
        }
    }
    mlt_properties_close(original);
    mlt_properties_close(left);
    mlt_properties_close(right);
    return passed ? 0 : 1;
}
