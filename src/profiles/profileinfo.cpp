/*
   SPDX-FileCopyrightText: 2017 Nicolas Carion
   SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
   This file is part of Kdenlive. See www.kdenlive.org.
*/

#include "profileinfo.hpp"
#include <KLocalizedString>

#include <cmath>
#include <mlt++/MltProfile.h>

bool ProfileInfo::operator==(const ProfileInfo &other) const
{
    if (!description().isEmpty() && other.description() == description()) {
        return true;
    }
    int fps = frame_rate_num() * 100 / frame_rate_den();
    int sar = sample_aspect_num() * 100 / sample_aspect_den();
    int dar = display_aspect_num() * 100 / display_aspect_den();
    return other.frame_rate_num() * 100 / other.frame_rate_den() == fps && other.width() == width() && other.height() == height() &&
           other.progressive() == progressive() && (progressive() ? true : other.bottom_field_first() == bottom_field_first()) &&
           other.sample_aspect_num() * 100 / other.sample_aspect_den() == sar && other.display_aspect_num() * 100 / other.display_aspect_den() == dar &&
           other.colorspace() == colorspace();
}

bool ProfileInfo::isCompatible(std::unique_ptr<ProfileInfo> &other) const
{
    return frame_rate_num() * 100 / frame_rate_den() == other->frame_rate_num() * 100 / other->frame_rate_den();
}

bool ProfileInfo::isCompatible(Mlt::Profile *other) const
{
    return frame_rate_num() * 100 / frame_rate_den() == other->frame_rate_num() * 100 / other->frame_rate_den();
}

bool ProfileInfo::hasValidFps() const
{
    const auto num = frame_rate_num();
    const auto den = frame_rate_den();
    double fps = double(num) / den;
    double fps_int;
    double fps_frac = std::modf(fps, &fps_int);
    if (fps_frac > 0.) {
        // The project profiles store broadcast rates as exact rational values
        // (24000/1001, 30000/1001, and 60000/1001). Comparing those values
        // with the rounded labels 23.98, 29.97, and 59.94 rejects valid
        // 23.976/29.97/59.94 projects because their difference is larger than
        // qFuzzyCompare's tolerance.
        const auto isRate = [num, den](qint64 standardNum, qint64 standardDen) {
            return qint64(num) * standardDen == standardNum * qint64(den);
        };
        return isRate(24000, 1001) || isRate(30000, 1001) || isRate(60000, 1001) || qFuzzyCompare(fps, 23.98) || qFuzzyCompare(fps, 29.97) ||
               qFuzzyCompare(fps, 59.94);
    }
    // Integer fps
    return true;
}

const QString ProfileInfo::descriptiveString() const
{
    QString data = description();
    if (!data.isEmpty()) {
        data.append(QLatin1Char(' '));
    }
    QString fps_str;
    if (frame_rate_num() % frame_rate_den() == 0) {
        fps_str = QString::number(frame_rate_num() / frame_rate_den());
    } else {
        fps_str = QString::number(double(frame_rate_num()) / frame_rate_den(), 'f', 2);
    }
    data.append(QStringLiteral("(%1x%2, %3fps)").arg(width()).arg(height()).arg(fps_str));
    return data;
}

const QString ProfileInfo::dialogDescriptiveString() const
{
    QString text;
    if (frame_rate_num() % frame_rate_den() == 0) {
        text = QString::number(frame_rate_num() / frame_rate_den());
    } else {
        text = QString::number(frame_rate_num() / frame_rate_den(), 'f', 2);
    }
    text.append(i18nc("frames per second", "fps"));
    if (!progressive()) {
        text.append(i18n(" interlaced"));
    }
    return text;
}
