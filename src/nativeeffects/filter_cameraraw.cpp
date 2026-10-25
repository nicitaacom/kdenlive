/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

extern "C" {
#include <framework/mlt.h>
#include <framework/mlt_pool.h>
}

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <vector>

namespace {

struct Curve
{
    float x[16]{0, 1};
    float y[16]{0, 1};
    int count{2};
};

float clamp01(float value)
{
    return std::clamp(value, 0.f, 1.f);
}

float smooth(float edge0, float edge1, float value)
{
    const float span = edge1 - edge0;
    if (std::fabs(span) < 1e-6f) {
        return value >= edge1 ? 1.f : 0.f;
    }
    const float t = clamp01((value - edge0) / span);
    return t * t * (3.f - 2.f * t);
}

float luma(float r, float g, float b)
{
    return 0.2126f * r + 0.7152f * g + 0.0722f * b;
}

void parseCurve(const char *text, Curve &curve)
{
    curve.count = 0;
    if (!text || !text[0]) {
        curve.x[0] = 0.f;
        curve.y[0] = 0.f;
        curve.x[1] = 1.f;
        curve.y[1] = 1.f;
        curve.count = 2;
        return;
    }
    const char *cursor = text;
    while (*cursor && curve.count < 16) {
        while (*cursor == ' ' || *cursor == ';' || *cursor == ',') {
            ++cursor;
        }
        if (!*cursor) {
            break;
        }
        char *end = nullptr;
        const float x = std::strtof(cursor, &end);
        if (end == cursor || *end != '/') {
            break;
        }
        cursor = end + 1;
        const float y = std::strtof(cursor, &end);
        if (end == cursor) {
            break;
        }
        curve.x[curve.count] = x;
        curve.y[curve.count] = y;
        ++curve.count;
        cursor = end;
    }
    if (curve.count < 2) {
        curve.x[0] = 0.f;
        curve.y[0] = 0.f;
        curve.x[1] = 1.f;
        curve.y[1] = 1.f;
        curve.count = 2;
        return;
    }
    for (int i = 1; i < curve.count; ++i) {
        const float x = curve.x[i];
        const float y = curve.y[i];
        int j = i;
        while (j > 0 && curve.x[j - 1] > x) {
            curve.x[j] = curve.x[j - 1];
            curve.y[j] = curve.y[j - 1];
            --j;
        }
        curve.x[j] = x;
        curve.y[j] = y;
    }
}

float sampleCurve(const Curve &curve, float x)
{
    if (x <= curve.x[0]) {
        return curve.y[0];
    }
    const int last = curve.count - 1;
    if (x >= curve.x[last]) {
        return curve.y[last];
    }
    int hi = 1;
    while (hi < curve.count && curve.x[hi] < x) {
        ++hi;
    }
    const int lo = hi - 1;
    const float span = curve.x[hi] - curve.x[lo];
    const float t = span > 1e-6f ? (x - curve.x[lo]) / span : 0.f;
    return curve.y[lo] + t * (curve.y[hi] - curve.y[lo]);
}

void buildLut(uint8_t *lut, const Curve &channel, const Curve &master)
{
    for (int i = 0; i < 256; ++i) {
        const float shaped = sampleCurve(channel, i / 255.f);
        const float finalValue = sampleCurve(master, clamp01(shaped));
        lut[i] = static_cast<uint8_t>(std::lround(clamp01(finalValue) * 255.f));
    }
}

void boxBlur(const uint8_t *src, uint8_t *dst, int width, int height, int radius)
{
    if (radius < 1) {
        std::memcpy(dst, src, static_cast<size_t>(width) * height * 4);
        return;
    }
    const int window = radius * 2 + 1;
    std::vector<uint8_t> horizontal(static_cast<size_t>(width) * height * 4);
    for (int y = 0; y < height; ++y) {
        int sumR = 0;
        int sumG = 0;
        int sumB = 0;
        const uint8_t *row = src + static_cast<size_t>(y) * width * 4;
        for (int x = -radius; x <= radius; ++x) {
            const int sample = std::clamp(x, 0, width - 1) * 4;
            sumR += row[sample];
            sumG += row[sample + 1];
            sumB += row[sample + 2];
        }
        for (int x = 0; x < width; ++x) {
            uint8_t *out = horizontal.data() + (static_cast<size_t>(y) * width + x) * 4;
            out[0] = static_cast<uint8_t>(sumR / window);
            out[1] = static_cast<uint8_t>(sumG / window);
            out[2] = static_cast<uint8_t>(sumB / window);
            out[3] = row[x * 4 + 3];
            const int leave = std::clamp(x - radius, 0, width - 1) * 4;
            const int enter = std::clamp(x + radius + 1, 0, width - 1) * 4;
            sumR += row[enter] - row[leave];
            sumG += row[enter + 1] - row[leave + 1];
            sumB += row[enter + 2] - row[leave + 2];
        }
    }
    for (int x = 0; x < width; ++x) {
        int sumR = 0;
        int sumG = 0;
        int sumB = 0;
        for (int y = -radius; y <= radius; ++y) {
            const int sample = std::clamp(y, 0, height - 1);
            const uint8_t *pix = horizontal.data() + (static_cast<size_t>(sample) * width + x) * 4;
            sumR += pix[0];
            sumG += pix[1];
            sumB += pix[2];
        }
        for (int y = 0; y < height; ++y) {
            uint8_t *out = dst + (static_cast<size_t>(y) * width + x) * 4;
            const uint8_t *srcPix = src + (static_cast<size_t>(y) * width + x) * 4;
            out[0] = static_cast<uint8_t>(sumR / window);
            out[1] = static_cast<uint8_t>(sumG / window);
            out[2] = static_cast<uint8_t>(sumB / window);
            out[3] = srcPix[3];
            const int leave = std::clamp(y - radius, 0, height - 1);
            const int enter = std::clamp(y + radius + 1, 0, height - 1);
            const uint8_t *leavePix = horizontal.data() + (static_cast<size_t>(leave) * width + x) * 4;
            const uint8_t *enterPix = horizontal.data() + (static_cast<size_t>(enter) * width + x) * 4;
            sumR += enterPix[0] - leavePix[0];
            sumG += enterPix[1] - leavePix[1];
            sumB += enterPix[2] - leavePix[2];
        }
    }
}

float toneShift(float value, float amount, float weight)
{
    if (amount >= 0.f) {
        return value + amount * weight * (1.f - value);
    }
    return value + amount * weight * value;
}

int getImage(mlt_frame frame, uint8_t **image, mlt_image_format *format, int *width, int *height, int writable)
{
    (void)writable;
    auto filter = static_cast<mlt_filter>(mlt_frame_pop_service(frame));
    *format = mlt_image_rgba;
    const int error = mlt_frame_get_image(frame, image, format, width, height, 0);
    if (error || !*image || *width < 1 || *height < 1) {
        return error ? error : 1;
    }
    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    if (mlt_properties_get_int(properties, "compare") != 0) {
        return 0;
    }
    const float exposure = static_cast<float>(mlt_properties_get_double(properties, "exposure"));
    const float contrast = static_cast<float>(mlt_properties_get_double(properties, "contrast"));
    const float highlights = static_cast<float>(mlt_properties_get_double(properties, "highlights")) / 100.f;
    const float shadows = static_cast<float>(mlt_properties_get_double(properties, "shadows")) / 100.f;
    const float whites = static_cast<float>(mlt_properties_get_double(properties, "whites")) / 100.f;
    const float blacks = static_cast<float>(mlt_properties_get_double(properties, "blacks")) / 100.f;
    const float temperature = static_cast<float>(mlt_properties_get_double(properties, "temperature")) / 100.f;
    const float tint = static_cast<float>(mlt_properties_get_double(properties, "tint")) / 100.f;
    const float vibrance = static_cast<float>(mlt_properties_get_double(properties, "vibrance")) / 100.f;
    const float saturation = static_cast<float>(mlt_properties_get_double(properties, "saturation")) / 100.f;
    const float texture = static_cast<float>(mlt_properties_get_double(properties, "texture")) / 100.f;
    const float clarity = static_cast<float>(mlt_properties_get_double(properties, "clarity")) / 100.f;
    const float dehaze = static_cast<float>(mlt_properties_get_double(properties, "dehaze")) / 100.f;
    const float noise = static_cast<float>(mlt_properties_get_double(properties, "noise_reduction")) / 100.f;
    const float colorNoise = static_cast<float>(mlt_properties_get_double(properties, "color_noise_reduction")) / 100.f;

    Curve master;
    Curve red;
    Curve green;
    Curve blue;
    parseCurve(mlt_properties_get(properties, "curve_master"), master);
    parseCurve(mlt_properties_get(properties, "curve_r"), red);
    parseCurve(mlt_properties_get(properties, "curve_g"), green);
    parseCurve(mlt_properties_get(properties, "curve_b"), blue);
    uint8_t lutR[256];
    uint8_t lutG[256];
    uint8_t lutB[256];
    buildLut(lutR, red, master);
    buildLut(lutG, green, master);
    buildLut(lutB, blue, master);

    const bool curvesIdle = master.count == 2 && red.count == 2 && green.count == 2 && blue.count == 2 && master.y[0] == 0.f && master.y[1] == 1.f
                            && red.y[0] == 0.f && red.y[1] == 1.f && green.y[0] == 0.f && green.y[1] == 1.f && blue.y[0] == 0.f && blue.y[1] == 1.f;
    const bool colorIdle = exposure == 0.f && contrast == 0.f && highlights == 0.f && shadows == 0.f && whites == 0.f && blacks == 0.f
                           && temperature == 0.f && tint == 0.f && vibrance == 0.f && saturation == 0.f && curvesIdle;
    const bool spatialIdle = texture == 0.f && clarity == 0.f && dehaze == 0.f && noise == 0.f && colorNoise == 0.f;
    if (colorIdle && spatialIdle) {
        return 0;
    }

    const size_t count = static_cast<size_t>(*width) * static_cast<size_t>(*height);
    const size_t bytes = count * 4;
    auto *output = static_cast<uint8_t *>(mlt_pool_alloc(static_cast<int>(bytes)));
    if (!output) {
        return 1;
    }
    const float gain = std::exp2(exposure);
    const float contrastScale = 1.f + contrast / 100.f;
    const float satScale = 1.f + saturation;
    for (size_t i = 0; i < count; ++i) {
        const uint8_t *pix = *image + i * 4;
        float r = pix[0] / 255.f * gain;
        float g = pix[1] / 255.f * gain;
        float b = pix[2] / 255.f * gain;
        r = (r - 0.5f) * contrastScale + 0.5f;
        g = (g - 0.5f) * contrastScale + 0.5f;
        b = (b - 0.5f) * contrastScale + 0.5f;
        const float y = luma(clamp01(r), clamp01(g), clamp01(b));
        const float highW = smooth(0.45f, 1.f, y);
        const float shadowW = smooth(0.55f, 0.f, y);
        const float whiteW = smooth(0.75f, 1.f, y);
        const float blackW = smooth(0.25f, 0.f, y);
        r = toneShift(r, highlights, highW);
        g = toneShift(g, highlights, highW);
        b = toneShift(b, highlights, highW);
        r = toneShift(r, shadows, shadowW);
        g = toneShift(g, shadows, shadowW);
        b = toneShift(b, shadows, shadowW);
        r = toneShift(r, whites, whiteW);
        g = toneShift(g, whites, whiteW);
        b = toneShift(b, whites, whiteW);
        r = toneShift(r, blacks, blackW);
        g = toneShift(g, blacks, blackW);
        b = toneShift(b, blacks, blackW);
        r += temperature * 0.18f;
        b -= temperature * 0.18f;
        g += tint * 0.12f;
        r -= tint * 0.06f;
        b -= tint * 0.06f;
        const float maxC = std::max(r, std::max(g, b));
        const float minC = std::min(r, std::min(g, b));
        const float spread = std::clamp(maxC - minC, 0.f, 1.f);
        const float vibScale = 1.f + vibrance * (1.f - spread);
        const float y2 = luma(clamp01(r), clamp01(g), clamp01(b));
        r = y2 + (r - y2) * satScale * vibScale;
        g = y2 + (g - y2) * satScale * vibScale;
        b = y2 + (b - y2) * satScale * vibScale;
        auto *out = output + i * 4;
        out[0] = lutR[static_cast<int>(std::lround(clamp01(r) * 255.f))];
        out[1] = lutG[static_cast<int>(std::lround(clamp01(g) * 255.f))];
        out[2] = lutB[static_cast<int>(std::lround(clamp01(b) * 255.f))];
        out[3] = pix[3];
    }

    if (!spatialIdle) {
        std::vector<uint8_t> smallBlur;
        std::vector<uint8_t> wideBlur;
        const uint8_t *smallSrc = nullptr;
        const uint8_t *wideSrc = nullptr;
        if (texture != 0.f) {
            smallBlur.resize(bytes);
            boxBlur(output, smallBlur.data(), *width, *height, 1);
            smallSrc = smallBlur.data();
        }
        if (clarity != 0.f || dehaze != 0.f || noise != 0.f || colorNoise != 0.f) {
            wideBlur.resize(bytes);
            const int wideRadius = std::clamp(*width / 160, 2, 12);
            const int denoiseRadius = noise > 0.f || colorNoise > 0.f ? 1 + static_cast<int>(std::max(noise, colorNoise) * 6.f) : 0;
            boxBlur(output, wideBlur.data(), *width, *height, std::max(1, std::max(wideRadius, denoiseRadius)));
            wideSrc = wideBlur.data();
        }
        for (size_t i = 0; i < count; ++i) {
            uint8_t *pix = output + i * 4;
            float r = pix[0] / 255.f;
            float g = pix[1] / 255.f;
            float b = pix[2] / 255.f;
            if (smallSrc) {
                const uint8_t *blur = smallSrc + i * 4;
                r += texture * (r - blur[0] / 255.f);
                g += texture * (g - blur[1] / 255.f);
                b += texture * (b - blur[2] / 255.f);
            }
            if (wideSrc && (clarity != 0.f || dehaze != 0.f)) {
                const uint8_t *blur = wideSrc + i * 4;
                const float br = blur[0] / 255.f;
                const float bg = blur[1] / 255.f;
                const float bb = blur[2] / 255.f;
                const float y = luma(clamp01(r), clamp01(g), clamp01(b));
                const float mid = 1.f - std::fabs(y - 0.5f) * 2.f;
                r += clarity * mid * (r - br);
                g += clarity * mid * (g - bg);
                b += clarity * mid * (b - bb);
                if (dehaze >= 0.f) {
                    r += dehaze * (r - br) * 1.2f;
                    g += dehaze * (g - bg) * 1.2f;
                    b += dehaze * (b - bb) * 1.2f;
                    r *= 1.f - 0.12f * dehaze;
                    g *= 1.f - 0.12f * dehaze;
                    b *= 1.f - 0.12f * dehaze;
                } else {
                    const float fog = -dehaze;
                    r = r * (1.f - fog) + 0.85f * fog;
                    g = g * (1.f - fog) + 0.85f * fog;
                    b = b * (1.f - fog) + 0.85f * fog;
                }
            }
            if (wideSrc && (noise != 0.f || colorNoise != 0.f)) {
                const uint8_t *blur = wideSrc + i * 4;
                const float br = blur[0] / 255.f;
                const float bg = blur[1] / 255.f;
                const float bb = blur[2] / 255.f;
                r = r * (1.f - noise) + br * noise;
                g = g * (1.f - noise) + bg * noise;
                b = b * (1.f - noise) + bb * noise;
                const float y = luma(clamp01(r), clamp01(g), clamp01(b));
                const float yb = luma(br, bg, bb);
                r = y + (r - y) * (1.f - colorNoise) + (br - yb) * colorNoise;
                g = y + (g - y) * (1.f - colorNoise) + (bg - yb) * colorNoise;
                b = y + (b - y) * (1.f - colorNoise) + (bb - yb) * colorNoise;
            }
            pix[0] = static_cast<uint8_t>(std::lround(clamp01(r) * 255.f));
            pix[1] = static_cast<uint8_t>(std::lround(clamp01(g) * 255.f));
            pix[2] = static_cast<uint8_t>(std::lround(clamp01(b) * 255.f));
        }
    }

    mlt_frame_set_image(frame, output, static_cast<int>(bytes), mlt_pool_release);
    *image = output;
    *format = mlt_image_rgba;
    return 0;
}

mlt_frame process(mlt_filter filter, mlt_frame frame)
{
    mlt_frame_push_service(frame, filter);
    mlt_frame_push_get_image(frame, getImage);
    return frame;
}

} // namespace

extern "C" mlt_filter createNativeCameraRaw(mlt_profile profile, mlt_service_type type, const char *id, const void *arg)
{
    (void)profile;
    (void)type;
    (void)id;
    (void)arg;
    mlt_filter filter = mlt_filter_new();
    if (!filter) {
        return nullptr;
    }
    filter->process = process;
    mlt_properties properties = MLT_FILTER_PROPERTIES(filter);
    mlt_properties_set_double(properties, "exposure", 0);
    mlt_properties_set_double(properties, "contrast", 0);
    mlt_properties_set_double(properties, "highlights", 0);
    mlt_properties_set_double(properties, "shadows", 0);
    mlt_properties_set_double(properties, "whites", 0);
    mlt_properties_set_double(properties, "blacks", 0);
    mlt_properties_set_double(properties, "temperature", 0);
    mlt_properties_set_double(properties, "tint", 0);
    mlt_properties_set_double(properties, "vibrance", 0);
    mlt_properties_set_double(properties, "saturation", 0);
    mlt_properties_set_double(properties, "texture", 0);
    mlt_properties_set_double(properties, "clarity", 0);
    mlt_properties_set_double(properties, "dehaze", 0);
    mlt_properties_set_double(properties, "noise_reduction", 0);
    mlt_properties_set_double(properties, "color_noise_reduction", 0);
    mlt_properties_set(properties, "curve_master", "0/0 1/1");
    mlt_properties_set(properties, "curve_r", "0/0 1/1");
    mlt_properties_set(properties, "curve_g", "0/0 1/1");
    mlt_properties_set(properties, "curve_b", "0/0 1/1");
    mlt_properties_set_int(properties, "compare", 0);
    return filter;
}

extern "C" mlt_properties nativeCameraRawMetadata(mlt_service_type type, const char *id, void *data)
{
    (void)type;
    (void)data;
    mlt_properties properties = mlt_properties_new();
    mlt_properties_set(properties, "identifier", id);
    mlt_properties_set(properties, "title", "Camera Raw");
    mlt_properties_set(properties, "description", "Exposure, color, curves, and detail controls for a clip");
    mlt_properties_set(properties, "version", "0.1");
    return properties;
}
