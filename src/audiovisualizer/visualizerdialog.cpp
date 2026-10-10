/* SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL */
#include "visualizerdialog.hpp"
#include "assets/model/assetparametermodel.hpp"
#include "bin/bin.h"
#include "bin/model/subtitlemodel.hpp"
#include "bin/projectclip.h"
#include "bin/projectitemmodel.h"
#include "core.h"
#include "doc/kdenlivedoc.h"
#include "effects/effectstack/model/effectitemmodel.hpp"
#include "effects/effectstack/model/effectstackmodel.hpp"
#include "kdenlivesettings.h"
#include "mainwindow.h"
#include "monitor/monitormanager.h"
#include "pythoninterfaces/speechtotextwhisper.h"
#include "timeline2/model/timelineitemmodel.hpp"
#include "timeline2/view/timelinewidget.h"
#include <KLocalizedString>
#include <KMessageBox>
#include <QAudioOutput>
#include <QCheckBox>
#include <QColorDialog>
#include <QComboBox>
#include <QDialogButtonBox>
#include <QDir>
#include <QFileDialog>
#include <QFormLayout>
#include <QJsonDocument>
#include <QLabel>
#include <QLineEdit>
#include <QMediaPlayer>
#include <QPlainTextEdit>
#include <QProcess>
#include <QPushButton>
#include <QSaveFile>
#include <QScopeGuard>
#include <QScrollArea>
#include <QSlider>
#include <QSplitter>
#include <QTabWidget>
#include <QTimer>
#include <QUuid>
#include <QtConcurrent/QtConcurrentRun>
#include <QtEndian>
#include <algorithm>
#include <cmath>

namespace AudioVisualizer {
static std::shared_ptr<EffectItemModel> visualizerEffect(const std::shared_ptr<TimelineItemModel> &timeline, int cid)
{
    if (!timeline || !timeline->isClip(cid)) return {};
    const auto clip = pCore->projectItemModel()->getClipByBinID(timeline->getClipBinId(cid));
    // Generated media keeps its renderer on the bin producer. Also support an
    // effect on an individual timeline instance, which takes precedence.
    for (const auto &stack : {timeline->getClipEffectStack(cid), clip ? clip->getEffectStack() : nullptr}) {
        for (int i = 0; stack && i < stack->rowCount(); ++i) {
            auto effect = std::dynamic_pointer_cast<EffectItemModel>(stack->getEffectStackRow(i));
            if (effect && effect->getAssetId() == QLatin1String("audio_visualizer")) return effect;
        }
    }
    return {};
}
void VisualizerDialog::open(std::shared_ptr<TimelineItemModel> timeline, int cid, QWidget *parent)
{
    if (!timeline || !timeline->isClip(cid)) {
        KMessageBox::information(parent, i18n("Select an audio clip on the timeline to create a visualization, or select a visualizer layer to edit it."));
        return;
    }
    if (!visualizerEffect(timeline, cid) && timeline->getClipState(cid).first == PlaylistState::VideoOnly) {
        KMessageBox::information(parent, i18n("Select a clip containing audio, or an existing Audio Visualizer layer."));
        return;
    }
    VisualizerDialog dialog(std::move(timeline), cid, parent);
    dialog.exec();
}
VisualizerDialog::VisualizerDialog(std::shared_ptr<TimelineItemModel> timeline, int cid, QWidget *parent)
    : QDialog(parent)
    , m_timeline(std::move(timeline))
    , m_clipId(cid)
    , m_settings(defaults())
    , m_cancel(std::make_shared<std::atomic_bool>(false))
{
    m_fps = pCore->getCurrentFps();
    m_position = m_timeline->getClipPosition(cid);
    m_frames = m_timeline->getClipPlaytime(cid);
    m_effect = visualizerEffect(m_timeline, cid);
    m_sourceName = pCore->bin()->getBinClipName(m_timeline->getClipBinId(cid));
    if (m_effect) {
        const auto saved = QJsonDocument::fromJson(m_effect->getParam(QStringLiteral("settings")).toUtf8()).object();
        for (auto it = saved.begin(); it != saved.end(); ++it)
            m_settings.insert(it.key(), it.value());
        m_spectrumPath = m_effect->getParam(QStringLiteral("filename"));
        m_wav = m_effect->getParam(QStringLiteral("av.file"));
    } else {
        m_source = ProjectClip::cloneProducer(m_timeline->getClipProducer(cid));
        // XML restores the parent producer, so explicitly restore the selected cut.
        const int sourceIn = m_timeline->getClipIn(cid);
        m_source->set_in_and_out(sourceIn, sourceIn + m_frames - 1);
        m_source->set("set.test_image", 1);
    }
    buildUi();
    m_previewProfile = std::make_unique<Mlt::Profile>(mlt_profile_clone(pCore->getProjectProfile().get_profile()));
    const QSize frame = pCore->getCurrentFrameDisplaySize();
    m_previewProfile->set_width(800);
    m_previewProfile->set_height(std::max(2, int(800.0 * frame.height() / std::max(1, frame.width())) / 2 * 2));
    m_previewProfile->set_sample_aspect(1, 1);
    m_previewProducer = std::make_unique<Mlt::Producer>(*m_previewProfile, "color", "#000000");
    m_previewProducer->set("length", m_effect ? std::max(m_frames, int(Spectrum::load(m_spectrumPath).frames())) : m_frames);
    m_previewProducer->set_in_and_out(0, m_previewProducer->get_length() - 1);
    m_previewFilter = std::make_unique<Mlt::Filter>(*m_previewProfile, "kdenlive_audio_visualizer");
    m_previewProducer->attach(*m_previewFilter);
    if (m_effect) {
        m_background->setText(m_effect->getParam(QStringLiteral("resource")));
        m_portrait->setText(m_effect->getParam(QStringLiteral("filter.resource")));
        m_player->setSource(QUrl::fromLocalFile(m_wav));
        setBusy(false, i18n("Edit this layer. Changes also appear in exported video."));
        QTimer::singleShot(0, this, &VisualizerDialog::updatePreview);
    } else
        QTimer::singleShot(0, this, &VisualizerDialog::analyzeAudio);
}
VisualizerDialog::~VisualizerDialog()
{
    m_cancel->store(true);
    m_client->cancel();
    if (m_whisper && m_whisper->state() != QProcess::NotRunning) {
        m_whisper->kill();
        m_whisper->waitForFinished(1000);
    }
    m_watcher.waitForFinished();
}
void VisualizerDialog::reject()
{
    m_cancel->store(true);
    m_client->cancel();
    QDialog::reject();
}
void VisualizerDialog::chooseKey(QLineEdit *field)
{
    const auto path = QFileDialog::getOpenFileName(this, i18n("Load an API key from a text file"));
    if (path.isEmpty()) return;
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly) || file.size() > 4096) {
        m_status->setText(i18n("Choose a small text file containing only the API key."));
        return;
    }
    field->setText(QString::fromUtf8(file.readAll()).trimmed());
}
void VisualizerDialog::colorButton(const QString &property, const QString &label, QWidget *container)
{
    auto *button = new QPushButton(label, container);
    button->setStyleSheet(QStringLiteral("border-left: 6px solid %1;").arg(m_settings.value(property).toString()));
    container->layout()->addWidget(button);
    connect(button, &QPushButton::clicked, this, [this, button, property] {
        QColor color = QColorDialog::getColor(QColor(m_settings.value(property).toString()), this);
        if (!color.isValid()) return;
        m_settings.insert(property, color.name());
        button->setStyleSheet(QStringLiteral("border-left: 6px solid %1;").arg(color.name()));
        updatePreview();
    });
}
void VisualizerDialog::buildUi()
{
    setWindowTitle(i18n("Audio Visualizer"));
    resize(1200, 790);
    setMinimumSize(950, 650);
    setObjectName(QStringLiteral("audioVisualizer"));
    setStyleSheet(QStringLiteral(
        "QDialog#audioVisualizer { background: #10141c; color: #eaf0f7; }"
        "QDialog#audioVisualizer QLabel { color: #d4dce8; }"
        "QDialog#audioVisualizer QTabWidget::pane { border: 0; }"
        "QDialog#audioVisualizer QTabBar::tab { background: #1c2430; color: #aab8cb; padding: 10px 16px; border-radius: 6px; margin: 3px; }"
        "QDialog#audioVisualizer QTabBar::tab:selected { background: #24413f; color: #67edcf; }"
        "QDialog#audioVisualizer QLineEdit, QDialog#audioVisualizer QComboBox, QDialog#audioVisualizer QPlainTextEdit { background: #171e29; color: #eaf0f7; "
        "border: 1px solid #344050; border-radius: 6px; padding: 7px; }"
        "QDialog#audioVisualizer QPushButton { background: #253041; color: #eaf0f7; border: 1px solid #3c4b60; border-radius: 6px; padding: 8px 12px; }"
        "QDialog#audioVisualizer QPushButton:hover { border-color: #67edcf; }"
        "QDialog#audioVisualizer QPushButton:disabled { color: #68768b; }"
        "QDialog#audioVisualizer QPushButton#primary { background: #64e5c6; color: #0d2420; border: 0; font-weight: bold; }"
        "QDialog#audioVisualizer QSlider::groove:horizontal { height: 4px; background: #344050; border-radius: 2px; }"
        "QDialog#audioVisualizer QSlider::sub-page:horizontal { background: #64e5c6; }"
        "QDialog#audioVisualizer QSlider::handle:horizontal { width: 14px; margin: -5px 0; background: #d6fff5; border-radius: 7px; }"));
    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(24, 20, 24, 20);
    root->setSpacing(16);
    auto *title = new QLabel(i18n("Audio Visualizer"));
    QFont font = title->font();
    font.setPointSize(21);
    font.setBold(true);
    title->setFont(font);
    root->addWidget(title);
    auto *source = new QLabel(i18n("%1 · %2 seconds · %3 fps", m_sourceName, QString::number(m_frames / m_fps, 'f', 1), QString::number(m_fps, 'f', 2)));
    source->setTextFormat(Qt::PlainText);
    source->setWordWrap(true);
    root->addWidget(source);
    auto *splitter = new QSplitter(this);
    root->addWidget(splitter, 1);
    auto *previewPane = new QWidget;
    auto *previewLayout = new QVBoxLayout(previewPane);
    previewLayout->setContentsMargins(0, 0, 16, 0);
    m_preview = new QLabel;
    m_preview->setMinimumSize(480, 270);
    m_preview->setAlignment(Qt::AlignCenter);
    m_preview->setStyleSheet(QStringLiteral("background: black; border-radius: 12px;"));
    previewLayout->addWidget(m_preview, 1);
    auto *transport = new QHBoxLayout;
    m_play = new QPushButton(i18n("Play"));
    transport->addWidget(m_play);
    m_seek = new QSlider(Qt::Horizontal);
    m_seek->setRange(0, int(m_frames / m_fps * 1000));
    transport->addWidget(m_seek, 1);
    m_clock = new QLabel(QStringLiteral("0:00"));
    transport->addWidget(m_clock);
    previewLayout->addLayout(transport);
    auto *hint = new QLabel(i18n("Measured audio frequencies · Preview matches export"));
    hint->setAlignment(Qt::AlignCenter);
    previewLayout->addWidget(hint);
    splitter->addWidget(previewPane);
    m_tabs = new QTabWidget;
    m_tabs->setMinimumWidth(380);
    splitter->addWidget(m_tabs);
    splitter->setSizes({760, 400});
    auto page = [this](const QString &name) {
        auto *scroll = new QScrollArea;
        scroll->setWidgetResizable(true);
        scroll->setFrameShape(QFrame::NoFrame);
        auto *body = new QWidget;
        body->setStyleSheet(QStringLiteral("background: #10141c;"));
        scroll->setWidget(body);
        auto *layout = new QVBoxLayout(body);
        layout->setSpacing(16);
        layout->setContentsMargins(12, 16, 12, 12);
        m_tabs->addTab(scroll, name);
        return body;
    };
    auto *style = page(i18n("Style"));
    m_preset = new QComboBox;
    m_preset->addItem(i18n("Rounded bars"), QStringLiteral("bars"));
    m_preset->addItem(i18n("Circular spectrum"), QStringLiteral("ring"));
    m_preset->setCurrentIndex(m_settings.value("preset").toString() == QLatin1String("ring") ? 1 : 0);
    style->layout()->addWidget(new QLabel(i18n("Spectrum preset")));
    style->layout()->addWidget(m_preset);
    connect(m_preset, &QComboBox::currentIndexChanged, this, [this] { updatePreview(); });
    auto *colors = new QWidget;
    new QHBoxLayout(colors);
    style->layout()->addWidget(colors);
    colorButton(QStringLiteral("color"), i18n("Color"), colors);
    colorButton(QStringLiteral("accent"), i18n("Gradient end"), colors);
    auto control = [this, style](const QString &key, const QString &label, int minimum, int maximum) {
        auto *row = new QWidget;
        auto *layout = new QVBoxLayout(row);
        layout->setContentsMargins(0, 0, 0, 0);
        auto *caption = new QLabel;
        auto *slider = new QSlider(Qt::Horizontal);
        slider->setRange(minimum, maximum);
        slider->setValue(m_settings.value(key).toInt());
        caption->setText(i18n("%1  %2", label, slider->value()));
        layout->addWidget(caption);
        layout->addWidget(slider);
        style->layout()->addWidget(row);
        m_sliders.insert(key, slider);
        connect(slider, &QSlider::valueChanged, this, [this, caption, label](int value) {
            caption->setText(i18n("%1  %2", label, value));
            updatePreview();
        });
    };
    control(QStringLiteral("size"), i18n("Size (%)"), 10, 100);
    control(QStringLiteral("x"), i18n("Horizontal position (%)"), 0, 100);
    control(QStringLiteral("y"), i18n("Vertical position (%)"), 0, 100);
    control(QStringLiteral("sensitivity"), i18n("Sensitivity (dB)"), -30, 30);
    control(QStringLiteral("smoothing"), i18n("Smoothing (%)"), 0, 100);
    control(QStringLiteral("thickness"), i18n("Thickness (%)"), 10, 100);
    control(QStringLiteral("glow"), i18n("Glow (%)"), 0, 100);
    static_cast<QVBoxLayout *>(style->layout())->addStretch();
    auto *media = page(i18n("Media"));
    auto filePicker = [this, media](const QString &label, const QString &filter) {
        media->layout()->addWidget(new QLabel(label));
        auto *row = new QWidget;
        auto *layout = new QHBoxLayout(row);
        layout->setContentsMargins(0, 0, 0, 0);
        auto *field = new QLineEdit;
        field->setPlaceholderText(i18n("None"));
        layout->addWidget(field, 1);
        auto *browse = new QPushButton(i18n("Browse"));
        layout->addWidget(browse);
        media->layout()->addWidget(row);
        connect(browse, &QPushButton::clicked, this, [this, field, label, filter] {
            const QString path = QFileDialog::getOpenFileName(this, label, {}, filter);
            if (!path.isEmpty()) field->setText(path);
        });
        connect(field, &QLineEdit::textChanged, this, [this] { updatePreview(); });
        return field;
    };
    m_background =
        filePicker(i18n("Background image or video"), i18n("Images and videos (*.png *.jpg *.jpeg *.webp *.bmp *.mp4 *.mov *.mkv *.webm);;All files (*)"));
    m_portrait = filePicker(i18n("Center image"), i18n("Images (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*)"));
    auto *mediaHint = new QLabel(i18n(
        "Leave the background empty for black. Images fill the frame; shorter videos loop with their audio muted. The center image is cropped to a circle."));
    mediaHint->setWordWrap(true);
    media->layout()->addWidget(mediaHint);
    auto *dim = new QSlider(Qt::Horizontal);
    dim->setRange(0, 100);
    dim->setValue(m_settings.value("dim").toInt());
    m_sliders.insert(QStringLiteral("dim"), dim);
    media->layout()->addWidget(new QLabel(i18n("Background darkening")));
    media->layout()->addWidget(dim);
    connect(dim, &QSlider::valueChanged, this, [this] { updatePreview(); });
    static_cast<QVBoxLayout *>(media->layout())->addStretch();
    auto *captions = page(i18n("Captions"));
    auto *form = new QFormLayout;
    form->setRowWrapPolicy(QFormLayout::WrapLongRows);
    form->setFieldGrowthPolicy(QFormLayout::AllNonFixedFieldsGrow);
    static_cast<QVBoxLayout *>(captions->layout())->addLayout(form);
    m_provider = new QComboBox;
    for (const auto &provider : providers())
        m_provider->addItem(provider.name);
    form->addRow(i18n("AI provider"), m_provider);
    auto keyRow = [this](QLineEdit **field) {
        auto *row = new QWidget;
        auto *layout = new QHBoxLayout(row);
        layout->setContentsMargins(0, 0, 0, 0);
        *field = new QLineEdit;
        (*field)->setEchoMode(QLineEdit::Password);
        (*field)->setPlaceholderText(i18n("API key (this session only)"));
        layout->addWidget(*field, 1);
        auto *load = new QPushButton(i18n("Load"));
        layout->addWidget(load);
        connect(load, &QPushButton::clicked, this, [this, input = *field] { chooseKey(input); });
        return row;
    };
    form->addRow(i18n("API key"), keyRow(&m_key));
    m_model = new QComboBox;
    m_model->setEditable(true);
    m_model->setPlaceholderText(i18n("Choose or enter a text model"));
    form->addRow(i18n("Caption model"), m_model);
    m_loadModels = new QPushButton(i18n("Load available models"));
    form->addRow(m_loadModels);
    m_effort = new QComboBox;
    form->addRow(i18n("Reasoning effort"), m_effort);
    m_engine = new QComboBox;
    m_engine->addItems({i18n("OpenAI transcription"), i18n("Grok transcription"), i18n("Local Whisper")});
    form->addRow(i18n("Speech to text"), m_engine);
    m_speechModel = new QLineEdit;
    form->addRow(i18n("Speech model"), m_speechModel);
    form->addRow(i18n("Speech API key"), keyRow(&m_speechKey));
    m_speechKey->setPlaceholderText(i18n("Empty = provider key above"));
    auto *captionHint =
        new QLabel(i18n("Speech recognition creates the timing. Your selected AI model can correct the text while preserving it. Generate sends audio to the "
                        "selected speech provider; Refine sends subtitle text to the AI provider. Keys are never saved in the project."));
    captionHint->setWordWrap(true);
    captions->layout()->addWidget(captionHint);
    m_autoRefine = new QCheckBox(i18n("Automatically refine the transcript"));
    m_autoRefine->setToolTip(i18n("Refine with the selected AI model after transcription, preserving subtitle timing."));
    m_autoRefine->setChecked(true);
    captions->layout()->addWidget(m_autoRefine);
    auto *buttons = new QWidget;
    auto *captionButtons = new QHBoxLayout(buttons);
    captionButtons->setContentsMargins(0, 0, 0, 0);
    m_generate = new QPushButton(i18n("Generate"));
    m_refine = new QPushButton(i18n("Refine text"));
    captionButtons->addWidget(m_generate);
    captionButtons->addWidget(m_refine);
    captions->layout()->addWidget(buttons);
    m_captions = new QPlainTextEdit;
    m_captions->setMinimumHeight(180);
    m_captions->setPlaceholderText(i18n("Timed captions appear here. Edit the SRT text and timing before adding it to the timeline."));
    captions->layout()->addWidget(m_captions);
    auto *captionFiles = new QWidget;
    auto *filesLayout = new QHBoxLayout(captionFiles);
    filesLayout->setContentsMargins(0, 0, 0, 0);
    auto *loadSrt = new QPushButton(i18n("Load SRT"));
    filesLayout->addWidget(loadSrt);
    m_import = new QPushButton(i18n("Add subtitles"));
    filesLayout->addWidget(m_import);
    captions->layout()->addWidget(captionFiles);
    auto *speechSettings = new QPushButton(i18n("Configure local speech recognition…"));
    captions->layout()->addWidget(speechSettings);
    connect(speechSettings, &QPushButton::clicked, this, [] { pCore->window()->slotShowPreferencePage(Kdenlive::PageSpeech); });
    m_status = new QLabel;
    m_status->setWordWrap(true);
    m_status->setTextFormat(Qt::PlainText);
    root->addWidget(m_status);
    auto *bottom = new QHBoxLayout;
    root->addLayout(bottom);
    bottom->addStretch();
    auto *cancel = new QPushButton(i18n("Cancel"));
    bottom->addWidget(cancel);
    m_apply = new QPushButton(m_effect ? i18n("Apply changes") : i18n("Create video layer"));
    m_apply->setObjectName(QStringLiteral("primary"));
    bottom->addWidget(m_apply);
    connect(cancel, &QPushButton::clicked, this, &VisualizerDialog::reject);
    connect(m_apply, &QPushButton::clicked, this, &VisualizerDialog::applyLayer);
    m_client = new CaptionClient(this);
    connect(m_provider, &QComboBox::currentIndexChanged, this, &VisualizerDialog::providerChanged);
    connect(m_engine, &QComboBox::currentIndexChanged, this, [this](int index) {
        m_speechModel->setText(index == 0 ? QStringLiteral("whisper-1") : index == 1 ? QStringLiteral("grok-voice-transcribe-2.0") : QStringLiteral("base"));
        m_speechKey->setEnabled(index != 2);
    });
    providerChanged();
    connect(m_loadModels, &QPushButton::clicked, this, [this] {
        if (m_key->text().trimmed().isEmpty()) {
            m_status->setText(i18n("Enter the provider's API key first."));
            return;
        }
        setBusy(true, i18n("Loading available models…"));
        m_client->models(m_provider->currentIndex(), m_key->text().trimmed());
    });
    connect(m_client, &CaptionClient::modelsReady, this, [this](const QStringList &models) {
        m_model->clear();
        m_model->addItems(models);
        m_model->setCurrentIndex(-1);
        setBusy(false, i18n("Choose a text model for caption editing."));
    });
    connect(m_client, &CaptionClient::failed, this, [this](const QString &message) { setBusy(false, message); });
    connect(m_client, &CaptionClient::progress, m_status, &QLabel::setText);
    connect(m_client, &CaptionClient::captionsReady, this, [this](const QVector<Cue> &cues) {
        m_captions->setPlainText(toSrt(cues));
        setBusy(false, cues.isEmpty() ? i18n("No speech detected.") : i18n("Review the captions, then add them as editable timeline subtitles."));
        if (m_refineAfterSpeech && !cues.isEmpty()) {
            m_refineAfterSpeech = false;
            refineCaptions();
        }
    });
    connect(m_generate, &QPushButton::clicked, this, &VisualizerDialog::generateCaptions);
    connect(m_refine, &QPushButton::clicked, this, &VisualizerDialog::refineCaptions);
    connect(m_import, &QPushButton::clicked, this, &VisualizerDialog::importCaptions);
    connect(loadSrt, &QPushButton::clicked, this, [this] {
        const QString path = QFileDialog::getOpenFileName(this, i18n("Load subtitles"), {}, QStringLiteral("SubRip (*.srt)"));
        QFile file(path);
        if (file.open(QIODevice::ReadOnly)) m_captions->setPlainText(QString::fromUtf8(file.readAll()));
    });
    m_audio = new QAudioOutput(this);
    m_player = new QMediaPlayer(this);
    m_player->setAudioOutput(m_audio);
    connect(m_play, &QPushButton::clicked, this, [this] {
        if (m_player->playbackState() == QMediaPlayer::PlayingState)
            m_player->pause();
        else {
            const int offset = m_effect ? qRound(m_timeline->getClipIn(m_clipId) * 1000 / m_fps) : 0;
            if (m_player->position() < offset || m_player->position() >= offset + m_seek->maximum()) m_player->setPosition(offset);
            m_player->play();
        }
    });
    connect(m_player, &QMediaPlayer::playbackStateChanged, this,
            [this](QMediaPlayer::PlaybackState state) { m_play->setText(state == QMediaPlayer::PlayingState ? i18n("Pause") : i18n("Play")); });
    connect(m_seek, &QSlider::sliderMoved, this, [this](int position) {
        const int offset = m_effect ? qRound(m_timeline->getClipIn(m_clipId) * 1000 / m_fps) : 0;
        m_player->setPosition(offset + position);
    });
    connect(m_seek, &QSlider::valueChanged, this, [this](int value) {
        m_clock->setText(QStringLiteral("%1:%2").arg(value / 60000).arg((value / 1000) % 60, 2, 10, QLatin1Char('0')));
        updatePreview();
    });
    connect(m_player, &QMediaPlayer::positionChanged, this, [this](qint64 position) {
        const int offset = m_effect ? qRound(m_timeline->getClipIn(m_clipId) * 1000 / m_fps) : 0;
        if (!m_seek->isSliderDown()) m_seek->setValue(int(position - offset));
        if (position >= offset + m_seek->maximum()) m_player->pause();
    });
}
QJsonObject VisualizerDialog::settings() const
{
    auto result = m_settings;
    result.insert(QStringLiteral("preset"), m_preset->currentData().toString());
    for (auto it = m_sliders.begin(); it != m_sliders.end(); ++it)
        result.insert(it.key(), it.value()->value());
    return result;
}
void VisualizerDialog::setBusy(bool busy, const QString &message)
{
    m_busy = busy;
    m_apply->setEnabled(!busy && !m_spectrumPath.isEmpty());
    m_play->setEnabled(!busy && !m_wav.isEmpty());
    m_generate->setEnabled(!busy && !m_wav.isEmpty());
    m_refine->setEnabled(!busy);
    m_import->setEnabled(!busy);
    m_loadModels->setEnabled(!busy);
    m_provider->setEnabled(!busy);
    m_engine->setEnabled(!busy);
    m_model->setEnabled(!busy);
    m_effort->setEnabled(!busy);
    m_key->setEnabled(!busy);
    m_speechKey->setEnabled(!busy && m_engine->currentIndex() != 2);
    m_speechModel->setEnabled(!busy);
    if (!message.isEmpty()) m_status->setText(message);
}
static bool writeWav(const QString &path, const QVector<float> &pcm)
{
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly)) return false;
    QByteArray header(44, '\0');
    header.replace(0, 4, "RIFF");
    header.replace(8, 8, "WAVEfmt ");
    header.replace(36, 4, "data");
    const quint32 bytes = quint32(pcm.size() * 2);
    qToLittleEndian<quint32>(bytes + 36, header.data() + 4);
    qToLittleEndian<quint32>(16, header.data() + 16);
    qToLittleEndian<quint16>(1, header.data() + 20);
    qToLittleEndian<quint16>(1, header.data() + 22);
    qToLittleEndian<quint32>(SampleRate, header.data() + 24);
    qToLittleEndian<quint32>(SampleRate * 2, header.data() + 28);
    qToLittleEndian<quint16>(2, header.data() + 32);
    qToLittleEndian<quint16>(16, header.data() + 34);
    qToLittleEndian<quint32>(bytes, header.data() + 40);
    file.write(header);
    QByteArray samples(bytes, '\0');
    for (qsizetype i = 0; i < pcm.size(); ++i)
        qToLittleEndian<qint16>(qint16(std::clamp(pcm[i], -1.0f, 1.0f) * 32767), samples.data() + i * 2);
    if (file.write(samples) != samples.size()) return false;
    return file.commit();
}
void VisualizerDialog::analyzeAudio()
{
    setBusy(true, i18n("Analyzing the selected audio clip…"));
    const QString directory = pCore->currentDoc()->projectDataFolder() + QStringLiteral("/audio-visualizers");
    if (!QDir().mkpath(directory)) {
        setBusy(false, i18n("Cannot create the project visualizer folder."));
        return;
    }
    const QString base = directory + QLatin1Char('/') + QUuid::createUuid().toString(QUuid::WithoutBraces);
    connect(&m_watcher, &QFutureWatcher<Analysis>::finished, this, [this] {
        auto result = m_watcher.result();
        if (!result.error.isEmpty()) {
            setBusy(false, result.error);
            return;
        }
        m_spectrumPath = result.spectrumPath;
        m_wav = result.wav;
        m_player->setSource(QUrl::fromLocalFile(m_wav));
        setBusy(false, i18n("Ready. Choose a preset and create your video layer."));
        updatePreview();
    });
    m_watcher.setFuture(QtConcurrent::run([producer = m_source, frames = m_frames, fps = m_fps, base, cancel = m_cancel] {
        Analysis result;
        if (!producer || !producer->is_valid()) {
            result.error = i18n("Cannot read the selected audio producer.");
            return result;
        }
        QVector<float> pcm;
        std::unique_ptr<Mlt::Profile> profile(producer->profile());
        Mlt::Filter resample(*profile, "audioresample"), convert(*profile, "audioconvert");
        producer->attach(resample);
        producer->attach(convert);
        const auto detach = qScopeGuard([&] {
            producer->detach(resample);
            producer->detach(convert);
        });
        for (int i = 0; i < frames; ++i) {
            if (cancel->load()) {
                result.error = i18n("Analysis canceled.");
                return result;
            }
            producer->seek(producer->get_in() + i);
            std::unique_ptr<Mlt::Frame> frame(producer->get_frame());
            if (!frame || !frame->is_valid()) {
                result.error = i18n("Cannot decode audio frame %1.", i);
                return result;
            }
            int rate = SampleRate, channels = 1, samples = mlt_audio_calculate_frame_samples(float(fps), SampleRate, i);
            mlt_audio_format format = mlt_audio_f32le;
            auto *audio = static_cast<float *>(frame->get_audio(format, rate, channels, samples));
            if (!audio || format != mlt_audio_f32le || rate != SampleRate || channels < 1) {
                result.error = i18n("The selected clip cannot be decoded as audio.");
                return result;
            }
            for (int n = 0; n < samples; ++n) {
                float value = 0;
                for (int c = 0; c < channels; ++c)
                    value += audio[n * channels + c];
                pcm.append(std::isfinite(value) ? value / channels : 0);
            }
        }
        result.spectrum = AudioVisualizer::analyze(pcm, fps);
        result.spectrumPath = base + QStringLiteral(".kdviz");
        result.wav = base + QStringLiteral(".wav");
        if (!result.spectrum.save(result.spectrumPath) || !writeWav(result.wav, pcm)) result.error = i18n("Cannot save the extracted audio and spectrum data.");
        return result;
    }));
}
void VisualizerDialog::updatePreview()
{
    if (!m_previewProducer || !m_previewFilter || !m_previewFilter->is_valid()) return;
    m_previewFilter->set("settings", QJsonDocument(settings()).toJson(QJsonDocument::Compact).constData());
    m_previewFilter->set("filename", m_spectrumPath.toUtf8().constData());
    m_previewFilter->set("resource", m_background->text().toUtf8().constData());
    m_previewFilter->set("filter.resource", m_portrait->text().toUtf8().constData());
    const int in = m_effect ? m_timeline->getClipIn(m_clipId) : 0;
    m_previewProducer->seek(std::min(m_previewProducer->get_length() - 1, in + int(m_seek->value() * m_fps / 1000)));
    std::unique_ptr<Mlt::Frame> frame(m_previewProducer->get_frame());
    int w = m_previewProfile->width(), h = m_previewProfile->height();
    mlt_image_format format = mlt_image_rgba;
    auto *data = frame->get_image(format, w, h);
    if (data && format == mlt_image_rgba)
        m_preview->setPixmap(
            QPixmap::fromImage(QImage(data, w, h, QImage::Format_RGBA8888).copy()).scaled(m_preview->size(), Qt::KeepAspectRatio, Qt::SmoothTransformation));
}
void VisualizerDialog::applyLayer()
{
    if (m_busy || m_spectrumPath.isEmpty()) return;
    if ((!m_background->text().isEmpty() && !QFileInfo::exists(m_background->text())) ||
        (!m_portrait->text().isEmpty() && QImage(m_portrait->text()).isNull())) {
        m_status->setText(i18n("Choose valid background and center-image files."));
        return;
    }
    const QString json = QString::fromUtf8(QJsonDocument(settings()).toJson(QJsonDocument::Compact));
    const paramVector params{{QStringLiteral("settings"), json},
                             {QStringLiteral("filename"), m_spectrumPath},
                             {QStringLiteral("resource"), m_background->text()},
                             {QStringLiteral("filter.resource"), m_portrait->text()},
                             {QStringLiteral("av.file"), m_wav}};
    if (m_effect) {
        paramVector previous;
        for (const auto &param : params)
            previous.append({param.first, m_effect->getParam(param.first)});
        auto effect = m_effect;
        Fun undo = [effect, previous] {
            effect->setParameters(previous);
            return true;
        };
        Fun redo = [effect, params] {
            effect->setParameters(params);
            return true;
        };
        redo();
        pCore->pushUndo(undo, redo, i18n("Edit audio visualizer"));
    } else {
        auto producer = std::make_shared<Mlt::Producer>(pCore->getProjectProfile(), "color", "#000000");
        producer->set("length", m_frames);
        producer->set_in_and_out(0, m_frames - 1);
        producer->set("kdenlive:clipname", i18n("Visualizer — %1", m_sourceName).toUtf8().constData());
        producer->set("set.test_audio", 1);
        Mlt::Filter filter(pCore->getProjectProfile(), "kdenlive_audio_visualizer");
        if (!filter.is_valid()) {
            m_status->setText(i18n("The Audio Visualizer renderer is unavailable. Restart the updated application."));
            return;
        }
        filter.set("kdenlive_id", "audio_visualizer");
        for (const auto &param : params)
            filter.set(param.first.toUtf8().constData(), param.second.toString().toUtf8().constData());
        producer->attach(filter);
        Fun undo = [] { return true; }, redo = [] { return true; };
        QString binId;
        int trackId = -1, clipId = -1;
        bool ok = pCore->projectItemModel()->requestAddBinClip(binId, producer, QStringLiteral("-1"), undo, redo);
        if (ok) ok = m_timeline->requestTrackInsertion(-1, trackId, i18n("Audio Visualizer"), false, undo, redo);
        if (ok) ok = m_timeline->requestClipInsertion(QStringLiteral("V") + binId, trackId, m_position, clipId, false, true, false, undo, redo);
        if (!ok) {
            undo();
            m_status->setText(i18n("Could not add the visualizer layer."));
            return;
        }
        m_timeline->requestSetSelection({clipId});
        pCore->pushUndo(undo, redo, i18n("Create audio visualizer"));
    }
    pCore->monitorManager()->refreshProjectMonitor(true);
    accept();
}
void VisualizerDialog::providerChanged()
{
    const int provider = m_provider->currentIndex();
    m_model->clear();
    m_model->setCurrentIndex(-1);
    m_effort->clear();
    m_effort->addItem(i18n("Provider default"), QString());
    QStringList levels = provider == 3 ? QStringList{QStringLiteral("low"), QStringLiteral("high"), QStringLiteral("max")}
                                       : QStringList{QStringLiteral("low"), QStringLiteral("medium"), QStringLiteral("high"), QStringLiteral("xhigh")};
    if (provider == 0 || provider == 2 || provider == 4) levels.append(QStringLiteral("max"));
    for (const auto &level : levels)
        m_effort->addItem(level, level);
    m_effort->setToolTip(i18n("Supported effort levels depend on the selected model. Provider default works without forcing a reasoning setting."));
    m_engine->setCurrentIndex(provider <= 1 ? provider : 2);
    m_speechModel->setText(provider == 0 ? QStringLiteral("whisper-1") : provider == 1 ? QStringLiteral("grok-voice-transcribe-2.0") : QStringLiteral("base"));
    m_key->clear();
    m_speechKey->clear();
}
void VisualizerDialog::generateCaptions()
{
    m_refineAfterSpeech = m_autoRefine->isChecked() && !m_model->currentText().trimmed().isEmpty();
    if (m_refineAfterSpeech && m_key->text().trimmed().isEmpty()) {
        m_status->setText(i18n("Enter the AI provider key for caption refinement, or turn off automatic refinement."));
        return;
    }
    QString audio = m_wav;
    if (m_effect) {
        // Existing layers may have been trimmed; only send/play the selected region.
        QFile original(m_wav);
        if (!original.open(QIODevice::ReadOnly)) {
            m_status->setText(i18n("Cannot read the extracted audio."));
            return;
        }
        QByteArray header = original.read(44);
        const qint64 start = qRound64(m_timeline->getClipIn(m_clipId) * SampleRate / m_fps) * 2;
        const qint64 bytes = qRound64(m_frames * SampleRate / m_fps) * 2;
        original.seek(44 + start);
        const QByteArray pcm = original.read(bytes);
        if (header.size() != 44 || pcm.isEmpty()) {
            m_status->setText(i18n("The selected audio region is unavailable."));
            return;
        }
        qToLittleEndian<quint32>(quint32(pcm.size() + 36), header.data() + 4);
        qToLittleEndian<quint32>(quint32(pcm.size()), header.data() + 40);
        audio = QFileInfo(m_wav).absolutePath() + QLatin1Char('/') + QUuid::createUuid().toString(QUuid::WithoutBraces) + QStringLiteral(".wav");
        QSaveFile file(audio);
        if (!file.open(QIODevice::WriteOnly) || file.write(header + pcm) < 0 || !file.commit()) {
            m_status->setText(i18n("Cannot extract the selected audio region."));
            return;
        }
    }
    const int engine = m_engine->currentIndex();
    if (engine < 2) {
        const QString key = m_speechKey->text().trimmed().isEmpty() ? m_key->text().trimmed() : m_speechKey->text().trimmed();
        if (key.isEmpty()) {
            m_status->setText(i18n("Enter an API key for the speech provider."));
            return;
        }
        if (m_speechModel->text().trimmed().isEmpty()) {
            m_status->setText(i18n("Enter a speech model supporting timestamps."));
            return;
        }
        setBusy(true);
        m_client->transcribe(engine, key, m_speechModel->text().trimmed(), audio);
        return;
    }
    SpeechToTextWhisper whisper;
    if (!whisper.checkSetup(false) || whisper.getInstalledModels().isEmpty()) {
        m_status->setText(i18n("Configure local Whisper and install a speech model first, or choose OpenAI/Grok transcription."));
        return;
    }
    const QString python = whisper.venvPythonExecs().python;
    const QString script = whisper.subtitleScript();
    if (python.isEmpty() || script.isEmpty()) {
        m_status->setText(i18n("Local Whisper is not configured."));
        return;
    }
    if (!m_whisper) m_whisper = new QProcess(this);
    const QString srt = QFileInfo(audio).path() + QLatin1Char('/') + QFileInfo(audio).completeBaseName() + QStringLiteral(".srt");
    QStringList args{script,
                     audio,
                     m_speechModel->text().trimmed(),
                     QStringLiteral("ffmpeg_path=%1").arg(KdenliveSettings::ffmpegpath()),
                     QStringLiteral("device=cpu"),
                     QStringLiteral("fp16=False"),
                     QStringLiteral("max_line_width=48"),
                     QStringLiteral("max_line_count=1")};
    disconnect(m_whisper, nullptr, this, nullptr);
    connect(m_whisper, &QProcess::finished, this, [this, srt](int code, QProcess::ExitStatus status) {
        QFile file(srt);
        // The existing Whisper script names its result after the WAV basename.
        if (!file.exists()) file.setFileName(QFileInfo(m_wav).path() + QLatin1Char('/') + QFileInfo(m_wav).completeBaseName() + QStringLiteral(".srt"));
        if (code != 0 || status != QProcess::NormalExit || !file.open(QIODevice::ReadOnly)) {
            setBusy(false, i18n("Local Whisper failed. Check the installed speech model and speech settings."));
            return;
        }
        m_captions->setPlainText(QString::fromUtf8(file.readAll()));
        setBusy(false, i18n("Review the transcript or refine it with your selected AI model."));
        if (m_refineAfterSpeech) {
            m_refineAfterSpeech = false;
            refineCaptions();
        }
    });
    connect(m_whisper, &QProcess::errorOccurred, this, [this] { setBusy(false, i18n("Could not start local Whisper.")); });
    setBusy(true, i18n("Transcribing locally with Whisper…"));
    m_whisper->start(python, args);
}
void VisualizerDialog::refineCaptions()
{
    m_refineAfterSpeech = false;
    QString error;
    const auto cues = fromSrt(m_captions->toPlainText(), &error);
    if (!error.isEmpty() || cues.isEmpty()) {
        m_status->setText(error.isEmpty() ? i18n("Generate or load subtitles first.") : error);
        return;
    }
    if (m_key->text().trimmed().isEmpty() || m_model->currentText().trimmed().isEmpty()) {
        m_status->setText(i18n("Choose an AI model and enter its provider key."));
        return;
    }
    setBusy(true);
    m_client->polish(m_provider->currentIndex(), m_key->text().trimmed(), m_model->currentText().trimmed(), m_effort->currentData().toString(), cues);
}
void VisualizerDialog::importCaptions()
{
    QString error;
    const auto cues = fromSrt(m_captions->toPlainText(), &error);
    if (!error.isEmpty() || cues.isEmpty()) {
        m_status->setText(error.isEmpty() ? i18n("Generate or load subtitles first.") : error);
        return;
    }
    if (cues.last().end > m_frames / m_fps + 0.1) {
        m_status->setText(i18n("A subtitle extends beyond the selected audio clip. Adjust its end time."));
        return;
    }
    const QString srt = QFileInfo(m_wav).absolutePath() + QLatin1Char('/') + QUuid::createUuid().toString(QUuid::WithoutBraces) + QStringLiteral(".srt");
    QSaveFile file(srt);
    if (!file.open(QIODevice::WriteOnly) || file.write(toSrt(cues).toUtf8()) < 0 || !file.commit()) {
        m_status->setText(i18n("Cannot save the subtitles."));
        return;
    }
    if (!m_timeline->getSubtitleModel()) pCore->window()->slotEditSubtitle();
    m_timeline->getSubtitleModel()->importSubtitle(srt, m_position, true);
    m_status->setText(i18n("Subtitles added at the audio clip's timeline position. Edit their text and style in the subtitle track."));
}
} // namespace AudioVisualizer
