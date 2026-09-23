/*
    SPDX-FileCopyrightText: Kdenlive contributors
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

import QtQuick

import org.kde.ki18n

Item {
    id: root
    anchors.fill: parent
    property bool showEmptyState: false
    visible: showEmptyState
    z: 1000

    Column {
        anchors.centerIn: parent
        spacing: 4

        Text {
            text: KI18n.i18n("No video")
            color: "white"
            font.family: "Arial"
            font.pixelSize: 14
            horizontalAlignment: Text.AlignHCenter
            anchors.horizontalCenter: parent.horizontalCenter
        }

        Text {
            text: KI18n.i18n("Drag&drop video on a timeline")
            color: "white"
            font.family: "Arial"
            font.pixelSize: 11
            horizontalAlignment: Text.AlignHCenter
            anchors.horizontalCenter: parent.horizontalCenter
        }
    }
}
