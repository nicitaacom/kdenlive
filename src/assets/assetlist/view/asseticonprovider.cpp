/*
    SPDX-FileCopyrightText: 2017 Nicolas Carion
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "asseticonprovider.hpp"
#include "assetlistwidget.hpp"

#include <QDebug>
#include <QFont>
#include <QPainter>

#include <cmath>

AssetIconProvider::AssetIconProvider(bool effect, QObject *parent)
    : QObject(parent)
    , m_effect(effect)
{
}

QImage AssetIconProvider::makeIcon(const QString &effectName)
{
    QPixmap pix = makePixmap(effectName);
    return pix.toImage();
}

const QPixmap AssetIconProvider::makePixmap(const QString &effectName, const QString &displayName, bool motionPreview)
{
    if (motionPreview) {
        QPixmap preview(96, 54);
        preview.fill(QColor(QStringLiteral("#12243a")));
        QPainter painter(&preview);
        painter.setRenderHint(QPainter::Antialiasing);
        painter.setPen(QPen(QColor(QStringLiteral("#42617e")), 1));
        painter.drawRoundedRect(QRectF(1, 1, 94, 52), 4, 4);

        QRectF frame(28, 13, 40, 28);
        const QString name = displayName.toLower();
        QPointF direction;
        if (name.contains(QLatin1String("left"))) {
            direction = QPointF(-16, 0);
        } else if (name.contains(QLatin1String("right"))) {
            direction = QPointF(16, 0);
        } else if (name.contains(QLatin1String("up"))) {
            direction = QPointF(0, -10);
        } else if (name.contains(QLatin1String("down"))) {
            direction = QPointF(0, 10);
        } else {
            direction = QPointF(0, 0);
        }
        if (name.contains(QLatin1String("zoom")) || name.contains(QLatin1String("pinch"))) {
            QRectF ghost = frame.adjusted(-8, -5, 8, 5);
            painter.setPen(QPen(QColor(QStringLiteral("#32b8cc")), 1, Qt::DashLine));
            painter.drawRect(ghost);
        }
        painter.setPen(QPen(QColor(QStringLiteral("#5bd2de")), 1));
        painter.setBrush(QColor(QStringLiteral("#1b5271")));
        painter.drawRoundedRect(frame.translated(direction), 2, 2);
        painter.setPen(QPen(QColor(QStringLiteral("#e8f6ff")), 2));
        QPointF start(48, 27);
        QPointF end = start + (direction.isNull() ? QPointF(15, 0) : direction);
        painter.drawLine(start, end);
        const QPointF vector = end - start;
        const qreal length = std::hypot(vector.x(), vector.y());
        const QPointF unit = vector / length;
        const QPointF normal(-unit.y() * 3.5, unit.x() * 3.5);
        painter.drawLine(end, end - unit * 5 + normal);
        painter.drawLine(end, end - unit * 5 - normal);
        return preview;
    }
    QPixmap pix(30, 30);
    if (effectName.isEmpty()) {
        pix.fill(Qt::red);
        return pix;
    }
    QFont ft = QFont();
    // ft.setBold(true);
    ft.setPixelSize(25);
    uint hex = qHash(effectName.section(QLatin1Char('/'), 0, -2));
    QString t = QStringLiteral("#") + QString::number(hex, 16).toUpper().left(6);
    QColor col(t);
    bool isAudio = false;
    bool isCustom = false;
    bool isGroup = false;
    AssetListType::AssetType type = AssetListType::AssetType(effectName.section(QLatin1Char('/'), -2, -2).toInt());
    if (m_effect) {
        isAudio = AssetListWidget::isAudioType(type);
        isCustom = AssetListWidget::isCustomType(type);
        if (isCustom) {
            // isGroup = EffectsRepository::get()->isGroup(effectId);
        }
    } else {
        isAudio = (type == AssetListType::AssetType::AudioComposition) || (type == AssetListType::AssetType::AudioTransition);
    }
    QPainter p;
    if (isCustom) {
        pix.fill(Qt::transparent);
        p.begin(&pix);
        p.setPen(Qt::NoPen);
        p.setBrush(isGroup ? Qt::magenta : Qt::red);
        p.drawRoundedRect(pix.rect(), 4, 4);
        p.setPen(QPen());
    } else if (isAudio) {
        pix.fill(Qt::transparent);
        p.begin(&pix);
        p.setPen(Qt::NoPen);
        p.setBrush(col);
        p.drawEllipse(pix.rect());
        p.setPen(QPen());
    } else {
        pix.fill(col);
        p.begin(&pix);
    }
    p.setFont(ft);
    p.drawText(pix.rect(), Qt::AlignCenter, effectName.at(effectName.length() - 1));
    p.end();
    return pix;
}
