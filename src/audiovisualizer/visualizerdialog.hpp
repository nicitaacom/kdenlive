/* SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL */
#pragma once
#include "captionclient.hpp"
#include "spectrum.hpp"
#include <QDialog>
#include <QFutureWatcher>
#include <QMap>
#include <atomic>
#include <memory>
#include <mlt++/Mlt.h>

class TimelineItemModel;
class EffectItemModel;
class QLabel;
class QSlider;
class QComboBox;
class QLineEdit;
class QPushButton;
class QPlainTextEdit;
class QTabWidget;
class QCheckBox;
class QMediaPlayer;
class QAudioOutput;
class QProcess;
namespace AudioVisualizer {
struct Analysis
{
    Spectrum spectrum;
    QString wav, spectrumPath, error;
};
class VisualizerDialog : public QDialog
{
    Q_OBJECT
public:
    VisualizerDialog(std::shared_ptr<TimelineItemModel> timeline, int clipId, QWidget *parent = nullptr);
    ~VisualizerDialog() override;
    static void open(std::shared_ptr<TimelineItemModel> timeline, int clipId, QWidget *parent);

protected:
    void reject() override;

private:
    void buildUi();
    void analyzeAudio();
    void updatePreview();
    void applyLayer();
    void providerChanged();
    void generateCaptions();
    void refineCaptions();
    void importCaptions();
    void setBusy(bool busy, const QString &message = {});
    void chooseKey(QLineEdit *field);
    void colorButton(const QString &property, const QString &label, QWidget *container);
    QJsonObject settings() const;
    std::shared_ptr<TimelineItemModel> m_timeline;
    int m_clipId, m_position = 0, m_frames = 0;
    double m_fps = 0;
    QString m_spectrumPath, m_wav, m_sourceName;
    QJsonObject m_settings;
    std::shared_ptr<EffectItemModel> m_effect;
    std::shared_ptr<Mlt::Producer> m_source;
    std::unique_ptr<Mlt::Profile> m_previewProfile;
    std::unique_ptr<Mlt::Producer> m_previewProducer;
    std::unique_ptr<Mlt::Filter> m_previewFilter;
    QFutureWatcher<Analysis> m_watcher;
    std::shared_ptr<std::atomic_bool> m_cancel;
    bool m_busy = false;
    bool m_refineAfterSpeech = false;
    QCheckBox *m_autoRefine = nullptr;
    QLabel *m_preview = nullptr, *m_status = nullptr, *m_clock = nullptr;
    QComboBox *m_preset = nullptr, *m_provider = nullptr, *m_model = nullptr, *m_effort = nullptr, *m_engine = nullptr;
    QLineEdit *m_background = nullptr, *m_portrait = nullptr, *m_key = nullptr, *m_speechKey = nullptr, *m_speechModel = nullptr;
    QPlainTextEdit *m_captions = nullptr;
    QSlider *m_seek = nullptr;
    QPushButton *m_apply = nullptr, *m_play = nullptr, *m_generate = nullptr, *m_refine = nullptr, *m_import = nullptr, *m_loadModels = nullptr;
    QTabWidget *m_tabs = nullptr;
    QMap<QString, QSlider *> m_sliders;
    CaptionClient *m_client = nullptr;
    QMediaPlayer *m_player = nullptr;
    QAudioOutput *m_audio = nullptr;
    QProcess *m_whisper = nullptr;
};
} // namespace AudioVisualizer
