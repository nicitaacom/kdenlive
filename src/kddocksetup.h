/*
    SPDX-FileCopyrightText: 2025 Jean-Baptiste Mardelle <jb@kdenlive.org>

SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include <QMenuBar>
#include <QPainter>
#include <QPointer>

#include <kddockwidgets/Config.h>
#include <kddockwidgets/core/Group.h>
#include <kddockwidgets/core/Separator.h>
#include <kddockwidgets/core/Stack.h>
#include <kddockwidgets/core/TitleBar.h>
#include <kddockwidgets/qtcommon/View.h>
#include <kddockwidgets/qtwidgets/ViewFactory.h>
#include <kddockwidgets/qtwidgets/views/Group.h>
#include <kddockwidgets/qtwidgets/views/Separator.h>
#include <kddockwidgets/qtwidgets/views/Stack.h>
#include <kddockwidgets/qtwidgets/views/TabBar.h>
#include <kddockwidgets/qtwidgets/views/TitleBar.h>

/** Keep the window menus above the left dock without reserving space above monitors. */
class DockMenuBar : public QObject
{
public:
    DockMenuBar(QMenuBar *source, QWidget *dockWindow, QWidget *window);
    void setAccessory(QWidget *accessory);

protected:
    bool eventFilter(QObject *object, QEvent *event) override;

private:
    void updateDock();
    void scheduleUpdate();
    void attachMenu(QAction *action);
    void placeAccessory(QMenuBar *menu);
    void detachAccessory();

    QMenuBar *const m_source;
    QPointer<QMenuBar> m_bar;
    QWidget *const m_dockWindow;
    QWidget *const m_window;
    QPointer<QWidget> m_host;
    QPointer<QWidget> m_accessory;
    bool m_updatePending{false};
    bool m_inUpdate{false};
    bool m_applied{false};
};

class CustomWidgetFactory : public KDDockWidgets::QtWidgets::ViewFactory
{
    Q_OBJECT
public:
    KDDockWidgets::Core::View *createTitleBar(KDDockWidgets::Core::TitleBar *, KDDockWidgets::Core::View *parent) const override;
    KDDockWidgets::Core::View *createGroup(KDDockWidgets::Core::Group *, KDDockWidgets::Core::View *parent) const override;
    KDDockWidgets::Core::View *createStack(KDDockWidgets::Core::Stack *, KDDockWidgets::Core::View *parent) const override;
    KDDockWidgets::Core::View *createTabBar(KDDockWidgets::Core::TabBar *, KDDockWidgets::Core::View *parent) const override;
    KDDockWidgets::Core::View *createSeparator(KDDockWidgets::Core::Separator *, KDDockWidgets::Core::View *parent) const override;
};
