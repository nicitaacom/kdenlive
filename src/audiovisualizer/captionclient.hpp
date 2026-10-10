/* SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL */
#pragma once
#include <QJsonArray>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QObject>
#include <QPointer>
#include <QUrl>
#include <QVector>
#include <functional>

namespace AudioVisualizer {
struct Cue
{
    double start = 0, end = 0;
    QString text;
};
QString toSrt(const QVector<Cue> &cues);
QVector<Cue> fromSrt(const QString &srt, QString *error = nullptr);
QVector<Cue> transcriptionCues(const QJsonObject &response, double offset, QString *error = nullptr);
struct Provider
{
    QString name;
    QUrl base;
    bool messages = false;
};
QVector<Provider> providers();
class CaptionClient : public QObject
{
    Q_OBJECT
public:
    explicit CaptionClient(QObject *parent = nullptr, const QVector<Provider> &endpoints = providers());
    void cancel();
    void models(int provider, const QString &key);
    void transcribe(int provider, const QString &key, const QString &model, const QString &wav);
    void polish(int provider, const QString &key, const QString &model, const QString &effort, const QVector<Cue> &cues);
    // Public for protocol regression tests; excludes credentials.
    static QJsonObject polishBody(int provider, const QString &model, const QString &effort, const QVector<Cue> &cues);
Q_SIGNALS:
    void failed(const QString &message);
    void modelsReady(const QStringList &models);
    void captionsReady(const QVector<AudioVisualizer::Cue> &cues);
    void progress(const QString &message);

private:
    QNetworkRequest request(int provider, const QString &key, const QString &path) const;
    void finish(QNetworkReply *reply, const QString &key, const std::function<void(const QJsonObject &)> &callback);
    void nextTranscription();
    void nextPolish();
    QNetworkAccessManager m_network;
    QVector<Provider> m_endpoints;
    QPointer<QNetworkReply> m_reply;
    int m_provider = 0, m_chunk = 0;
    QString m_key, m_model, m_effort;
    QByteArray m_pcm;
    QVector<Cue> m_cues, m_polished;
};
} // namespace AudioVisualizer
Q_DECLARE_METATYPE(QVector<AudioVisualizer::Cue>)
