/*
    SPDX-FileCopyrightText: 2025 Jean-Baptiste Mardelle <jb@kdenlive.org>

SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/

#include "kddocksetup.h"
#include "core.h"
#include "kdenlivesettings.h"

#include <kddockwidgets/qtwidgets/views/DockWidget.h>

#include <QActionEvent>
#include <QLayout>
#include <QMenu>
#include <QPainter>
#include <QProxyStyle>
#include <QStyleFactory>
#include <QTabBar>
#include <QTimer>

DockMenuBar::DockMenuBar(QMenuBar *source, QWidget *dockWindow, QWidget *window)
    : QObject(window)
    , m_source(source)
    , m_dockWindow(dockWindow)
    , m_window(window)
{
    source->setNativeMenuBar(false);
    qApp->installEventFilter(this);
    updateDock();
}

void DockMenuBar::attachMenu(QAction *action)
{
    if (QMenu *menu = action->menu()) {
        // The XMLGUI menu bar remains the action container and visibility setting,
        // but only this dock menu bar handles keyboard navigation. Keep popups
        // owned by the window so disabling the source does not disable its menus.
        if (menu->parentWidget() == m_source) {
            const bool explicitlyDisabled = menu->testAttribute(Qt::WA_ForceDisabled);
            menu->setParent(m_window, menu->windowFlags());
            menu->setEnabled(!explicitlyDisabled);
        }
    }
}

void DockMenuBar::scheduleUpdate()
{
    if (m_inUpdate || m_updatePending) {
        return;
    }
    m_updatePending = true;
    QTimer::singleShot(200, this, [this]() {
        m_updatePending = false;
        updateDock();
    });
}

void DockMenuBar::setAccessory(QWidget *accessory)
{
    m_accessory = accessory;
    m_applied = false;
    scheduleUpdate();
}

void DockMenuBar::detachAccessory()
{
    if (!m_accessory || !m_window) {
        return;
    }
    if (m_accessory->parentWidget() != m_window) {
        m_accessory->setParent(m_window);
        m_accessory->hide();
    }
}

void DockMenuBar::placeAccessory(QMenuBar *menu)
{
    if (!m_accessory || !menu) {
        return;
    }
    QMenuBar *bars[2] = {m_source, m_bar.data()};
    for (QMenuBar *bar : bars) {
        if (bar && bar != menu && bar->cornerWidget(Qt::TopRightCorner) == m_accessory) {
            bar->setCornerWidget(nullptr, Qt::TopRightCorner);
        }
    }
    if (menu->cornerWidget(Qt::TopRightCorner) != m_accessory) {
        menu->setCornerWidget(m_accessory, Qt::TopRightCorner);
    }
    if (!m_accessory->isVisible()) {
        m_accessory->show();
    }
}

void DockMenuBar::updateDock()
{
    if (m_inUpdate) {
        return;
    }
    // A visible host already has the menu. Searching every dock on each repaint
    // is what made the overflow arrow blink and stall the window.
    if (m_applied && m_host && m_host->isVisible()) {
        return;
    }
    m_inUpdate = true;
    if (!m_accessory && m_window) {
        m_accessory = m_window->findChild<QWidget *>(QStringLiteral("layoutMenuAccessory"));
    }
    if (!m_bar) {
        // Layout restoration deletes dock contents. Recreate the presentation
        // while XMLGUI keeps the shared actions and menus owned by the window.
        m_bar = new QMenuBar(m_window);
        m_bar->setObjectName(QStringLiteral("dockMenuBar"));
        m_bar->setNativeMenuBar(false);
        // The dock width determines which menus fit; QMenuBar provides overflow.
        m_bar->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Fixed);
        m_bar->addActions(m_source->actions());
    }
    KDDockWidgets::QtWidgets::Group *host = nullptr;
    QPoint hostPosition;
    for (auto group : m_dockWindow->findChildren<KDDockWidgets::QtWidgets::Group *>()) {
        if (!group->isVisible() || !group->group()->isInMainWindow()) {
            continue;
        }
        bool previewOrTimeline = false;
        for (auto dock : group->group()->dockWidgets()) {
            const QString name = dock->uniqueName();
            if (name == QLatin1String("clipmonitor") || name == QLatin1String("projectmonitor") || name == QLatin1String("timeline")) {
                previewOrTimeline = true;
                break;
            }
        }
        if (previewOrTimeline) {
            continue;
        }
        const QPoint position = group->QWidget::mapTo(m_dockWindow, QPoint(0, 0));
        if (!host || position.x() < hostPosition.x() || (position.x() == hostPosition.x() && position.y() < hostPosition.y())) {
            host = group;
            hostPosition = position;
        }
    }

    QMenuBar *accessoryMenu = host ? static_cast<QMenuBar *>(m_bar.data()) : m_source;
    const bool accessoryReady = !m_accessory || (accessoryMenu && accessoryMenu->cornerWidget(Qt::TopRightCorner) == m_accessory && m_accessory->isVisible());
    if (m_applied && host == m_host && accessoryReady) {
        m_inUpdate = false;
        return;
    }

    if (host != m_host) {
        detachAccessory();
        if (m_host && m_host->layout()) {
            m_host->layout()->setMenuBar(nullptr);
        }
        m_bar->setParent(m_window);
        m_host = host;
        if (host) {
            host->layout()->setMenuBar(m_bar);
            // The controller survives the group; its menu bar is recreated after
            // the docking library has finished destroying the old layout.
            connect(host, &QObject::destroyed, this, [this, host]() {
                detachAccessory();
                if (!m_host || m_host == host) {
                    m_host.clear();
                    m_applied = false;
                    scheduleUpdate();
                }
            });
        }
    }

    if (host) {
        for (auto action : m_bar->actions()) {
            attachMenu(action);
        }
        if (m_source->maximumHeight() != 0) {
            m_source->setFixedHeight(0);
        }
        m_source->setEnabled(false);
        const bool wantVisible = !m_source->isHidden();
        if (m_bar->isVisible() != wantVisible) {
            m_bar->setVisible(wantVisible);
        }
    } else {
        // Monitors and the timeline are not menu hosts. Keep the window menu.
        m_source->setMinimumHeight(0);
        m_source->setMaximumHeight(QWIDGETSIZE_MAX);
        m_source->setEnabled(true);
        if (!m_bar->isHidden()) {
            m_bar->hide();
        }
    }
    placeAccessory(accessoryMenu);
    m_applied = true;
    m_inUpdate = false;
}

bool DockMenuBar::eventFilter(QObject *object, QEvent *event)
{
    if (event->type() == QEvent::Destroy && (object == m_bar || object == m_host)) {
        detachAccessory();
        m_applied = false;
    }
    if (m_inUpdate || object == m_bar || object == m_accessory) {
        return QObject::eventFilter(object, event);
    }
    if (object == m_source) {
        if (event->type() == QEvent::ActionAdded) {
            auto actionEvent = static_cast<QActionEvent *>(event);
            if (m_bar) {
                m_bar->insertAction(actionEvent->before(), actionEvent->action());
            }
            attachMenu(actionEvent->action());
        } else if (event->type() == QEvent::ActionRemoved) {
            if (m_bar) {
                m_bar->removeAction(static_cast<QActionEvent *>(event)->action());
            }
        } else if (event->type() == QEvent::Show || event->type() == QEvent::Hide) {
            if (m_bar) {
                m_bar->setVisible(m_host && !m_source->isHidden());
            }
        }
    }
    switch (event->type()) {
    case QEvent::Show:
    case QEvent::Hide:
        if (m_applied && m_host && m_host->isVisible() && object != m_host) {
            break;
        }
        if (qobject_cast<KDDockWidgets::QtWidgets::Group *>(object)) {
            scheduleUpdate();
        }
        break;
    case QEvent::ParentChange:
        if (qobject_cast<KDDockWidgets::QtWidgets::Group *>(object) || qobject_cast<KDDockWidgets::QtWidgets::DockWidget *>(object)) {
            m_applied = false;
            scheduleUpdate();
        }
        break;
    default:
        break;
    }
    return QObject::eventFilter(object, event);
}

class KdenliveDockTabBar : public KDDockWidgets::QtWidgets::TabBar
{
public:
    explicit KdenliveDockTabBar(KDDockWidgets::Core::TabBar *controller, KDDockWidgets::Core::View *parent = nullptr)
        : KDDockWidgets::QtWidgets::TabBar(controller, KDDockWidgets::QtCommon::View_qt::asQWidget(parent))
    {
        auto parentWidget = KDDockWidgets::QtCommon::View_qt::asQWidget(parent);
        setProperty("_breeze_force_frame", false);
        setDocumentMode(true);
        setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        setExpanding(false);
        setStyleSheet(QStringLiteral("QTabBar::tab { border: none; padding: 0 4px; }"));
        parentWidget->setProperty("_breeze_force_frame", false);
        setContextMenuPolicy(Qt::CustomContextMenu);
        // The constructor of KDDockWidgets::QtWidgets::TabBar makes a QProxyStyle
        // that ends up taking ownership of the style for the entire application!
        if (QProxyStyle *proxy_style = qobject_cast<QProxyStyle *>(style())) {
            proxy_style->baseStyle()->setParent(qApp);
            proxy_style->setBaseStyle(QStyleFactory::create(qApp->style()->name()));
        }
        setPalette(qApp->palette());

        connect(this, &QWidget::customContextMenuRequested, []() { Q_EMIT pCore.get()->switchTitleBars(); });
        connect(this, &KDDockWidgets::QtWidgets::TabBar::countChanged, [&]() {
            if (!KdenliveSettings::showtitlebars()) {
                pCore->startHideBarsTimer();
            }
        });
    }

protected:
    void paintEvent(QPaintEvent *event) override
    {
        KDDockWidgets::QtWidgets::TabBar::paintEvent(event);
        QPainter painter(this);
        painter.setPen(QPen(palette().midlight().color(), 1));
        painter.drawLine(0, 0, width() - 1, 0);
        const int selectedIndex = currentIndex();
        for (int index = 0; index < count(); ++index) {
            const QRect tab = tabRect(index);
            painter.setPen(QPen(palette().midlight().color(), 1));
            painter.drawLine(tab.right(), tab.top(), tab.right(), tab.bottom());
        }
        if (selectedIndex >= 0) {
            const QRect selectedTab = tabRect(selectedIndex);
            painter.setPen(QPen(palette().highlight().color(), 2));
            painter.drawLine(selectedTab.left(), 0, selectedTab.right(), 0);
        }
    }
};

class KdenliveDockGroup : public KDDockWidgets::QtWidgets::Group
{
public:
    explicit KdenliveDockGroup(KDDockWidgets::Core::Group *controller, KDDockWidgets::Core::View *parent = nullptr)
        : KDDockWidgets::QtWidgets::Group(controller, KDDockWidgets::QtCommon::View_qt::asQWidget(parent))
    {
    }
    void paintEvent(QPaintEvent *) override
    {
        // KDDockWidgets sizes the tab bar to its contents. Keep the divider
        // visually full-width by drawing the continuation on the group itself.
        // The tab bar paints the same rule over its own area, with the active
        // tab replacing that segment with the accent color.
        const auto tabBar = findChild<QTabBar *>();
        if (!tabBar || !tabBar->isVisible()) {
            return;
        }
        QPainter painter(this);
        painter.setPen(QPen(palette().midlight().color(), 1));
        painter.drawLine(0, tabBar->geometry().top(), width() - 1, tabBar->geometry().top());
    }
};

class KdenliveDockStack : public KDDockWidgets::QtWidgets::Stack
{
public:
    explicit KdenliveDockStack(KDDockWidgets::Core::Stack *controller, KDDockWidgets::Core::View *parent = nullptr)
        : KDDockWidgets::QtWidgets::Stack(controller, KDDockWidgets::QtCommon::View_qt::asQWidget(parent))
    {
    }
    void paintEvent(QPaintEvent *) override {}
};

class KdenliveDockTitleBar : public KDDockWidgets::QtWidgets::TitleBar
{
public:
    explicit KdenliveDockTitleBar(KDDockWidgets::Core::TitleBar *controller, KDDockWidgets::Core::View *parent = nullptr)
        : KDDockWidgets::QtWidgets::TitleBar(controller, parent)
        , m_controller(controller)
    {
        connect(pCore.get(), &Core::hideBars, this, [this](bool hide) {
            if (hide) {
#if defined(Q_OS_WIN)
                auto parentWidget = m_controller->view()->parentView();
                if (parentWidget && parentWidget->asFloatingWindowController() != nullptr) {
                    // Floating window, don't show as we already have the widget titlebar
                    return;
                }
#endif
            } else {
                if (m_controller->dockWidgets().size() > 1) {
                    // Don't show title bar when there are tabbed widgets
                    return;
                }
                auto parentWidget = m_controller->view()->parentView();
                if (parentWidget && parentWidget->asFloatingWindowController() != nullptr) {
                    // Floating window, don't show as we already have the widget titlebar
                    return;
                }
            }
            setVisible(!hide);
        });
    }

private:
    KDDockWidgets::Core::TitleBar *const m_controller;
};

class KdenliveDockSeparator : public KDDockWidgets::QtWidgets::Separator
{
public:
    explicit KdenliveDockSeparator(KDDockWidgets::Core::Separator *controller, KDDockWidgets::Core::View *parent)
        : KDDockWidgets::QtWidgets::Separator(controller, parent)
        , m_controller(controller)
    {
    }

    ~KdenliveDockSeparator() override;

    void enterEvent(KDDockWidgets::Qt5Qt6Compat::QEnterEvent *event) override
    {
        hovered = true;
        KDDockWidgets::QtWidgets::Separator::enterEvent(event);
        update();
    }

    void leaveEvent(QEvent *event) override
    {
        hovered = false;
        KDDockWidgets::QtWidgets::Separator::leaveEvent(event);
        update();
    }

    void paintEvent(QPaintEvent *) override
    {
        QPainter p(this);
        QColor separatorColor = hovered ? palette().highlight().color() : palette().midlight().color();
        if (hovered) {
            separatorColor.setAlpha(128);
        }
        QPen pen(separatorColor);
        pen.setWidth(2);
        if (m_controller->isVertical()) {
            // Vertical rect
            p.fillRect(QWidget::rect(), palette().window());
            p.setPen(pen);
            p.drawLine(QWidget::rect().x(), QWidget::rect().y() + QWidget::rect().height() / 2, QWidget::rect().right(),
                       QWidget::rect().y() + QWidget::rect().height() / 2);
        } else {
            // Horizontal rect
            p.fillRect(QWidget::rect(), palette().window());
            p.setPen(pen);
            p.drawLine(QWidget::rect().x() + QWidget::rect().width() / 2, QWidget::rect().top(), QWidget::rect().x() + QWidget::rect().width() / 2,
                       QWidget::rect().bottom());
        }
    }

private:
    KDDockWidgets::Core::Separator *const m_controller;
    bool hovered{false};
};

KdenliveDockSeparator::~KdenliveDockSeparator() = default;

KDDockWidgets::Core::View *CustomWidgetFactory::createTitleBar(KDDockWidgets::Core::TitleBar *controller, KDDockWidgets::Core::View *parent) const
{
    return new KdenliveDockTitleBar(controller, parent);
}

KDDockWidgets::Core::View *CustomWidgetFactory::createGroup(KDDockWidgets::Core::Group *controller, KDDockWidgets::Core::View *parent) const
{
    return new KdenliveDockGroup(controller, parent);
}

KDDockWidgets::Core::View *CustomWidgetFactory::createStack(KDDockWidgets::Core::Stack *controller, KDDockWidgets::Core::View *parent) const
{
    return new KdenliveDockStack(controller, parent);
}

KDDockWidgets::Core::View *CustomWidgetFactory::createSeparator(KDDockWidgets::Core::Separator *controller, KDDockWidgets::Core::View *parent) const
{
    return new KdenliveDockSeparator(controller, parent);
}

KDDockWidgets::Core::View *CustomWidgetFactory::createTabBar(KDDockWidgets::Core::TabBar *controller, KDDockWidgets::Core::View *parent) const
{
    return new KdenliveDockTabBar(controller, parent);
}
