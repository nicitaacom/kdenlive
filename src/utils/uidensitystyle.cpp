/*
    SPDX-FileCopyrightText: Kdenlive contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "uidensitystyle.h"

#include "colorcontrast.h"

#include <QApplication>
#include <QLayout>
#include <QPainter>
#include <QTabBar>
#include <QStyleOptionTab>
#include <QWidget>

UiDensityStyle::UiDensityStyle(const QString &baseStyle, Density density)
    : QProxyStyle(baseStyle)
    , m_density(density)
{
}

void UiDensityStyle::setDensity(Density density)
{
    if (m_density == density) {
        return;
    }
    m_density = density;
    if (auto *app = qobject_cast<QApplication *>(QApplication::instance())) {
        // Style metrics are queried by layouts on demand. Invalidate existing
        // widget geometry so a runtime density change takes effect immediately.
        const auto widgets = app->allWidgets();
        for (QWidget *widget : widgets) {
            widget->updateGeometry();
            if (QLayout *layout = widget->layout()) {
                layout->invalidate();
                layout->activate();
            }
            widget->update();
        }
    }
}

int UiDensityStyle::density() const
{
    return m_density;
}

int UiDensityStyle::pixelMetric(PixelMetric metric, const QStyleOption *option, const QWidget *widget) const
{
    const int base = QProxyStyle::pixelMetric(metric, option, widget);
    const int padding = m_density == Default ? 8 : (m_density == Compact ? 4 : 2);
    const int gap = m_density == Default ? 4 : (m_density == Compact ? 2 : 0);
    switch (metric) {
    case PM_ButtonMargin:
        return padding;
    case PM_ToolBarItemSpacing:
    case PM_MenuBarItemSpacing:
        return gap;
    case PM_ToolBarItemMargin:
        return m_density == Default ? 4 : (m_density == Compact ? 2 : 0);
    default:
        return base;
    }
}

QSize UiDensityStyle::sizeFromContents(ContentsType type, const QStyleOption *option, const QSize &contentsSize, const QWidget *widget) const
{
    QSize size = QProxyStyle::sizeFromContents(type, option, contentsSize, widget);
    if (type == CT_PushButton || type == CT_ToolButton) {
        const int extra = m_density == Default ? 2 : (m_density == Compact ? 0 : -2);
        size += QSize(extra, extra);
    }
    return size.expandedTo(QSize(1, 1));
}

void UiDensityStyle::drawControl(ControlElement element, const QStyleOption *option, QPainter *painter, const QWidget *widget) const
{
    if (element == CE_TabBarTabShape && option) {
        QProxyStyle::drawControl(element, option, painter, widget);
        const auto *tabOption = qstyleoption_cast<const QStyleOptionTab *>(option);
        if (!tabOption || (tabOption->shape != QTabBar::RoundedNorth && tabOption->shape != QTabBar::TriangularNorth)) {
            return;
        }
        painter->save();
        painter->setPen(QPen(option->palette.midlight().color(), 1));
        painter->drawLine(option->rect.right(), option->rect.top(), option->rect.right(), option->rect.bottom());
        if (option->state & State_Selected) {
            painter->setPen(QPen(option->palette.color(QPalette::Highlight), 2));
            painter->drawLine(option->rect.left(), option->rect.top(), option->rect.right(), option->rect.top());
        }
        painter->restore();
        return;
    }
    if (element == CE_TabBarTabLabel && option && (option->state & State_Selected)) {
        auto *tabOption = static_cast<const QStyleOptionTab *>(option);
        QStyleOptionTab adjusted(*tabOption);
        // Selected tabs use HighlightedText in the base style. That role may
        // be intended for a bright selection fill, while Kdenlive's tab style
        // keeps the tab surface dark and only draws a colored accent. Resolve
        // the text against the actual tab surface instead of blindly reusing
        // HighlightedText (which can become black on black in custom themes).
        const QColor tabBackground = adjusted.palette.color(QPalette::Window);
        const QColor tabText = ColorContrast::readableTextColor(tabBackground, adjusted.palette.color(QPalette::WindowText));
        adjusted.palette.setColor(QPalette::WindowText, tabText);
        adjusted.palette.setColor(QPalette::ButtonText, tabText);
        adjusted.palette.setColor(QPalette::HighlightedText, tabText);
        QProxyStyle::drawControl(element, &adjusted, painter, widget);
        return;
    }
    QProxyStyle::drawControl(element, option, painter, widget);
}

void applyUiDensity(int density)
{
    auto *app = qobject_cast<QApplication *>(QApplication::instance());
    if (!app) {
        return;
    }
    density = qBound(int(UiDensityStyle::Default), density, int(UiDensityStyle::Minimalist));
    if (auto *style = dynamic_cast<UiDensityStyle *>(app->style())) {
        style->setDensity(static_cast<UiDensityStyle::Density>(density));
        return;
    }

    const QString baseStyle = app->style()->objectName();
    app->setStyle(new UiDensityStyle(baseStyle, static_cast<UiDensityStyle::Density>(density)));
}
