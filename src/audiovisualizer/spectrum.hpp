/* SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL */
#pragma once

#include <QImage>
#include <QJsonObject>
#include <QString>
#include <QVector>

namespace AudioVisualizer {
constexpr int Bands = 64;
constexpr int SampleRate = 32000;
struct Spectrum
{
    double fps = 0;
    QVector<float> levels;
    int frames() const { return int(levels.size() / Bands); }
    bool save(const QString &path) const;
    static Spectrum load(const QString &path);
};
// PCM is mono, normalized to [-1, 1]. Windows are centered on each video frame.
Spectrum analyze(const QVector<float> &pcm, double fps);
QVector<float> amplitudes(const Spectrum &spectrum, double seconds, const QJsonObject &settings);
QJsonObject defaults();
void paint(QImage &image, const QVector<float> &levels, const QJsonObject &settings, const QImage &portrait = {});
} // namespace AudioVisualizer
