/*
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include <QColor>
#include <QPalette>
#include <QVector>

#include <cmath>
#include <limits>

namespace ColorContrast {
inline double linearChannel(double value)
{
    return value <= 0.04045 ? value / 12.92 : std::pow((value + 0.055) / 1.055, 2.4);
}

inline double relativeLuminance(const QColor &color)
{
    return 0.2126 * linearChannel(color.redF()) + 0.7152 * linearChannel(color.greenF()) + 0.0722 * linearChannel(color.blueF());
}

inline double ratio(const QColor &first, const QColor &second)
{
    const double firstLuminance = relativeLuminance(first);
    const double secondLuminance = relativeLuminance(second);
    return (qMax(firstLuminance, secondLuminance) + 0.05) / (qMin(firstLuminance, secondLuminance) + 0.05);
}

inline QColor bestTextColor(const QVector<QColor> &backgrounds)
{
    const QColor black(Qt::black);
    const QColor white(Qt::white);
    double blackScore = std::numeric_limits<double>::max();
    double whiteScore = std::numeric_limits<double>::max();
    for (const QColor &background : backgrounds) {
        blackScore = qMin(blackScore, ratio(background, black));
        whiteScore = qMin(whiteScore, ratio(background, white));
    }
    return blackScore >= whiteScore ? black : white;
}

inline QColor readableTextColor(const QColor &background, const QColor &currentText)
{
    if (ratio(background, currentText) >= 4.5) {
        return currentText;
    }
    return bestTextColor({background});
}

inline bool ensurePaletteTextContrast(QPalette &palette)
{
    bool changed = false;
    for (QPalette::ColorGroup group : {QPalette::Active, QPalette::Inactive, QPalette::Disabled}) {
        const auto repair = [&palette, group, &changed](QPalette::ColorRole textRole, QPalette::ColorRole backgroundRole) {
            const QColor text = palette.color(group, textRole);
            const QColor background = palette.color(group, backgroundRole);
            const QColor readable = readableTextColor(background, text);
            if (readable != text) {
                palette.setColor(group, textRole, readable);
                changed = true;
            }
        };
        repair(QPalette::WindowText, QPalette::Window);
        repair(QPalette::ButtonText, QPalette::Button);
        repair(QPalette::Text, QPalette::Base);
        repair(QPalette::HighlightedText, QPalette::Highlight);
        repair(QPalette::ToolTipText, QPalette::ToolTipBase);
        repair(QPalette::PlaceholderText, QPalette::Base);
        repair(QPalette::Link, QPalette::Base);
        repair(QPalette::LinkVisited, QPalette::Base);
    }
    return changed;
}
}
