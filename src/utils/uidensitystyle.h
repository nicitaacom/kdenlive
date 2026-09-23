/*
    SPDX-FileCopyrightText: Kdenlive contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#pragma once

#include <QProxyStyle>

class UiDensityStyle : public QProxyStyle
{
public:
    enum Density { Default = 0, Compact = 1, Minimalist = 2 };

    explicit UiDensityStyle(const QString &baseStyle, Density density);

    void setDensity(Density density);
    int density() const;

    int pixelMetric(PixelMetric metric, const QStyleOption *option = nullptr, const QWidget *widget = nullptr) const override;
    QSize sizeFromContents(ContentsType type, const QStyleOption *option, const QSize &contentsSize, const QWidget *widget = nullptr) const override;
    void drawControl(ControlElement element, const QStyleOption *option, QPainter *painter, const QWidget *widget = nullptr) const override;

private:
    Density m_density;
};

void applyUiDensity(int density);
