/*
    SPDX-FileCopyrightText: Kdenlive contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "uidensitystyle.h"

#include <QApplication>
#include <QLayout>
#include <QPainter>
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
    const int padding = m_density == Default ? 12 : (m_density == Compact ? 8 : 4);
    const int gap = m_density == Default ? 8 : (m_density == Compact ? 4 : 2);
    switch (metric) {
    case PM_LayoutLeftMargin:
    case PM_LayoutTopMargin:
    case PM_LayoutRightMargin:
    case PM_LayoutBottomMargin:
    case PM_ButtonMargin:
    case PM_TabBarTabHSpace:
    case PM_TabBarTabVSpace:
    case PM_MenuHMargin:
    case PM_MenuVMargin:
    case PM_DockWidgetTitleMargin:
        return padding;
    case PM_LayoutHorizontalSpacing:
    case PM_LayoutVerticalSpacing:
    case PM_ToolBarItemSpacing:
    case PM_MenuBarItemSpacing:
        return gap;
    case PM_ToolBarItemMargin:
        return padding;
    case PM_DefaultFrameWidth:
        if (m_density == Default) {
            return base + 2;
        }
        return m_density == Minimalist ? qMax(1, base - 1) : base;
    default:
        return base;
    }
}

QSize UiDensityStyle::sizeFromContents(ContentsType type, const QStyleOption *option, const QSize &contentsSize, const QWidget *widget) const
{
    QSize size = QProxyStyle::sizeFromContents(type, option, contentsSize, widget);
    if (type == CT_ItemViewItem) {
        // List and tree rows often contain text rendered by custom delegates.
        // Shrinking their style hint clips/overlaps that text, so density only
        // changes their breathing room in the spacious modes.
        if (m_density == Default) {
            size.rheight() += 8;
        } else if (m_density == Compact) {
            size.rheight() += 4;
        }
        return size;
    }
    if (m_density == Compact) {
        return size;
    }

    // Default adds room around controls; Minimalist trims two pixels per side
    // from the base style while retaining a usable target size.
    const int changePerSide = m_density == Default ? 4 : -2;
    switch (type) {
    case CT_PushButton:
    case CT_ToolButton:
    case CT_ComboBox:
    case CT_LineEdit:
    case CT_SpinBox:
    case CT_MenuItem:
    case CT_TabBarTab:
        size.rwidth() += changePerSide * 2;
        size.rheight() += changePerSide * 2;
        break;
    default:
        break;
    }
    return size.expandedTo(QSize(1, 1));
}

void UiDensityStyle::drawControl(ControlElement element, const QStyleOption *option, QPainter *painter, const QWidget *widget) const
{
    if (element == CE_TabBarTabShape && option && (option->state & State_Selected)) {
        const QColor accent = option->palette.color(QPalette::Highlight);
        painter->save();
        painter->setRenderHint(QPainter::Antialiasing);
        painter->setPen(Qt::NoPen);
        painter->setBrush(accent);
        painter->drawRoundedRect(option->rect.adjusted(1, 1, -1, -1), 3, 3);
        painter->restore();
        return;
    }
    if (element == CE_TabBarTabLabel && option && (option->state & State_Selected)) {
        auto *tabOption = static_cast<const QStyleOptionTab *>(option);
        QStyleOptionTab adjusted(*tabOption);
        adjusted.palette.setColor(QPalette::WindowText, adjusted.palette.color(QPalette::HighlightedText));
        adjusted.palette.setColor(QPalette::ButtonText, adjusted.palette.color(QPalette::HighlightedText));
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
