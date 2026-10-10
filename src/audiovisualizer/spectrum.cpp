/* SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL */
#include "spectrum.hpp"
#include "lib/external/kiss_fft/kiss_fftr.h"
#include <QDataStream>
#include <QFile>
#include <QPainter>
#include <QPainterPath>
#include <QSaveFile>
#include <algorithm>
#include <cmath>
#include <memory>

namespace AudioVisualizer {
QJsonObject defaults()
{
    return {{"preset", "bars"}, {"color", "#ffffff"}, {"accent", "#ffffff"}, {"size", 75}, {"x", 50},  {"y", 50},
            {"sensitivity", 0}, {"smoothing", 65},    {"thickness", 55},     {"glow", 0},  {"dim", 25}};
}

Spectrum analyze(const QVector<float> &pcm, double fps)
{
    Spectrum result;
    if (pcm.isEmpty() || !std::isfinite(fps) || fps <= 0 || fps > 240) return result;
    result.fps = fps;
    constexpr int Window = 4096;
    std::unique_ptr<kiss_fftr_state, decltype(&free)> fft(kiss_fftr_alloc(Window, 0, nullptr, nullptr), free);
    if (!fft) return {};
    QVector<kiss_fft_scalar> window(Window);
    QVector<kiss_fft_cpx> bins(Window / 2 + 1);
    const int count = int(std::ceil(pcm.size() * fps / SampleRate));
    result.levels.reserve(qsizetype(count) * Bands);
    for (int frame = 0; frame < count; ++frame) {
        const qint64 center = qint64(std::llround(frame * SampleRate / fps));
        for (int n = 0; n < Window; ++n) {
            const qint64 i = center + n - Window / 2;
            const float sample = i >= 0 && i < pcm.size() && std::isfinite(pcm[i]) ? pcm[i] : 0;
            window[n] = sample * float(0.5 - 0.5 * std::cos(2 * M_PI * n / (Window - 1)));
        }
        kiss_fftr(fft.get(), window.constData(), bins.data());
        for (int band = 0; band < Bands; ++band) {
            const double lo = 30 * std::pow(15000.0 / 30, double(band) / Bands);
            const double hi = 30 * std::pow(15000.0 / 30, double(band + 1) / Bands);
            const int first = std::clamp(int(std::ceil(lo * Window / SampleRate)), 1, Window / 2);
            const int last = std::clamp(int(std::ceil(hi * Window / SampleRate)), first + 1, Window / 2 + 1);
            float peak = 0;
            for (int k = first; k < last; ++k)
                peak = std::max(peak, std::hypot(bins[k].r, bins[k].i) * float(4.0 / Window));
            result.levels.append(20 * std::log10(std::max(peak, 0.000001f)));
        }
    }
    return result;
}

bool Spectrum::save(const QString &path) const
{
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly)) return false;
    QDataStream stream(&file);
    stream.setByteOrder(QDataStream::LittleEndian);
    stream.setFloatingPointPrecision(QDataStream::SinglePrecision);
    stream.writeRawData("KDVIZ001", 8);
    stream << float(fps) << quint32(frames()) << quint32(Bands);
    for (float value : levels)
        stream << value;
    return stream.status() == QDataStream::Ok && file.commit();
}

Spectrum Spectrum::load(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly) || file.size() < 20 || file.size() > 512 * 1024 * 1024) return {};
    QDataStream stream(&file);
    stream.setByteOrder(QDataStream::LittleEndian);
    stream.setFloatingPointPrecision(QDataStream::SinglePrecision);
    char magic[8];
    stream.readRawData(magic, 8);
    float fps;
    quint32 count, bands;
    stream >> fps >> count >> bands;
    if (QByteArray(magic, 8) != QByteArray("KDVIZ001") || !std::isfinite(fps) || fps <= 0 || fps > 240 || bands != Bands || count == 0 ||
        qint64(count) * Bands * 4 != file.size() - 20)
        return {};
    Spectrum result;
    result.fps = fps;
    result.levels.resize(qsizetype(count) * Bands);
    for (float &value : result.levels) {
        stream >> value;
        if (!std::isfinite(value)) return {};
    }
    return stream.status() == QDataStream::Ok ? result : Spectrum{};
}

QVector<float> amplitudes(const Spectrum &spectrum, double seconds, const QJsonObject &settings)
{
    QVector<float> output(Bands, 0);
    if (spectrum.frames() == 0 || !std::isfinite(seconds) || seconds < 0 || seconds * spectrum.fps >= spectrum.frames()) return output;
    const int frame = int(seconds * spectrum.fps);
    const double smoothing = std::clamp(settings.value("smoothing").toDouble(65), 0.0, 100.0) / 100;
    const int history = int(smoothing * spectrum.fps * 0.28);
    const double gain = std::clamp(settings.value("sensitivity").toDouble(), -30.0, 30.0);
    for (int b = 0; b < Bands; ++b) {
        double total = 0, weight = 0;
        for (int i = 0; i <= history && i <= frame; ++i) {
            const double w = std::exp(-double(i) / std::max(1.0, history / 2.5));
            total += w * std::clamp((spectrum.levels[(frame - i) * Bands + b] + gain + 65) / 60.0, 0.0, 1.0);
            weight += w;
        }
        output[b] = float(total / weight);
    }
    return output;
}

void paint(QImage &image, const QVector<float> &levels, const QJsonObject &settings, const QImage &portrait)
{
    if (image.isNull() || levels.size() != Bands) return;
    const double w = image.width(), h = image.height(), unit = std::min(w, h);
    const double size = std::clamp(settings.value("size").toDouble(75), 10.0, 100.0) / 100;
    const QPointF center(w * std::clamp(settings.value("x").toDouble(50), 0.0, 100.0) / 100,
                         h * std::clamp(settings.value("y").toDouble(50), 0.0, 100.0) / 100);
    QColor color(settings.value("color").toString("#ffffff")), accent(settings.value("accent").toString("#ffffff"));
    if (!color.isValid()) color = Qt::white;
    if (!accent.isValid()) accent = color;
    QLinearGradient gradient(center.x() - w * size / 2, 0, center.x() + w * size / 2, 0);
    gradient.setColorAt(0, color);
    gradient.setColorAt(1, accent);
    const double thickness = std::clamp(settings.value("thickness").toDouble(55), 10.0, 100.0) / 100;
    QPainter painter(&image);
    painter.setRenderHint(QPainter::Antialiasing);
    QPainterPath shape;
    const bool ring = settings.value("preset").toString() == QLatin1String("ring");
    const double radius = unit * size * 0.28;
    if (ring) {
        for (int i = 0; i <= Bands * 8; ++i) {
            const double b = double(i % (Bands * 8)) / 8;
            const int left = int(b), right = (left + 1) % Bands;
            const double t = b - left, smooth = t * t * (3 - 2 * t);
            const double level = levels[left] * (1 - smooth) + levels[right] * smooth;
            const double r = radius + unit * size * 0.14 * level;
            const double angle = double(i) * 2 * M_PI / (Bands * 8) - M_PI / 2;
            const QPointF p = center + QPointF(std::cos(angle) * r, std::sin(angle) * r);
            if (i == 0)
                shape.moveTo(p);
            else
                shape.lineTo(p);
        }
        shape.closeSubpath();
    } else {
        const double spacing = w * size / Bands;
        const double width = spacing * thickness;
        for (int i = 0; i < Bands; ++i) {
            const double height = std::max(width, unit * size * 0.25 * levels[i]);
            shape.addRoundedRect(QRectF(center.x() - w * size / 2 + i * spacing, center.y() - height / 2, width, height), width / 2, width / 2);
        }
    }
    const double line = std::max(1.0, unit / 240 * thickness);
    const double glow = std::clamp(settings.value("glow").toDouble(), 0.0, 100.0) / 100;
    for (int pass = 4; pass >= 1 && glow > 0; --pass) {
        painter.setOpacity(glow * 0.045);
        painter.setPen(QPen(QBrush(gradient), line + pass * unit * 0.004, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
        painter.setBrush(Qt::NoBrush);
        painter.drawPath(shape);
    }
    painter.setOpacity(1);
    painter.setPen(ring ? QPen(QBrush(gradient), line, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin) : QPen(Qt::NoPen));
    painter.setBrush(ring ? Qt::NoBrush : QBrush(gradient));
    painter.drawPath(shape);
    if (!portrait.isNull()) {
        const double r = ring ? radius * 0.88 : unit * size * 0.16;
        QPointF c = ring ? center : center - QPointF(0, unit * size * 0.27);
        QPainterPath clip;
        clip.addEllipse(c, r, r);
        painter.setClipPath(clip);
        const double crop = std::min(portrait.width(), portrait.height());
        painter.drawImage(QRectF(c.x() - r, c.y() - r, r * 2, r * 2), portrait,
                          QRectF((portrait.width() - crop) / 2, (portrait.height() - crop) / 2, crop, crop));
    }
}
} // namespace AudioVisualizer
