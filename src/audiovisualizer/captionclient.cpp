/* SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL */
#include "captionclient.hpp"
#include <KLocalizedString>
#include <QFile>
#include <QHttpMultiPart>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QtEndian>
#include <algorithm>
#include <cmath>

namespace AudioVisualizer {
QVector<Provider> providers()
{
    return {{"OpenAI", QUrl("https://api.openai.com/v1/")},
            {"Grok", QUrl("https://api.x.ai/v1/")},
            {"Claude", QUrl("https://api.anthropic.com/v1/"), true},
            {"DeepSeek", QUrl("https://api.deepseek.com/v1/")},
            {"Nous", QUrl("https://inference-api.nousresearch.com/v1/")}};
}
static QString timestamp(double seconds)
{
    qint64 ms = qRound64(seconds * 1000);
    return QStringLiteral("%1:%2:%3,%4")
        .arg(ms / 3600000, 2, 10, QLatin1Char('0'))
        .arg((ms / 60000) % 60, 2, 10, QLatin1Char('0'))
        .arg((ms / 1000) % 60, 2, 10, QLatin1Char('0'))
        .arg(ms % 1000, 3, 10, QLatin1Char('0'));
}
QString toSrt(const QVector<Cue> &cues)
{
    QString result;
    for (int i = 0; i < cues.size(); ++i)
        result += QStringLiteral("%1\n%2 --> %3\n%4\n\n").arg(i + 1).arg(timestamp(cues[i].start), timestamp(cues[i].end), cues[i].text.trimmed());
    return result;
}
QVector<Cue> fromSrt(const QString &srt, QString *error)
{
    QVector<Cue> result;
    QString text = srt;
    text.replace(QStringLiteral("\r"), QString());
    const QRegularExpression time(QStringLiteral("^(\\d+):(\\d{2}):(\\d{2})[,.](\\d{3})\\s+-->\\s+(\\d+):(\\d{2}):(\\d{2})[,.](\\d{3})$"));
    for (const QString &block : text.trimmed().split(QRegularExpression(QStringLiteral("\\n[ \\t]*\\n")), Qt::SkipEmptyParts)) {
        const QStringList lines = block.split(QLatin1Char('\n'));
        if (lines.size() < 3) {
            if (error) *error = i18n("Each subtitle needs a number, a time range and text.");
            return {};
        }
        const auto match = time.match(lines[1].trimmed());
        if (!match.hasMatch()) {
            if (error) *error = i18n("Invalid subtitle time range: %1", lines[1]);
            return {};
        }
        auto seconds = [&match](int i) {
            return match.captured(i).toDouble() * 3600 + match.captured(i + 1).toDouble() * 60 + match.captured(i + 2).toDouble() +
                   match.captured(i + 3).toDouble() / 1000;
        };
        Cue cue{seconds(1), seconds(5), lines.mid(2).join(QLatin1Char('\n')).trimmed()};
        if (cue.end <= cue.start || cue.text.isEmpty() || (!result.isEmpty() && cue.start < result.last().end)) {
            if (error) *error = i18n("Subtitle times must increase without overlap, with nonempty text.");
            return {};
        }
        result.append(cue);
    }
    return result;
}
QVector<Cue> transcriptionCues(const QJsonObject &response, double offset, QString *error)
{
    QVector<Cue> cues;
    const bool words = !response.value("words").toArray().isEmpty();
    const auto segments = response.value(words ? "words" : "segments").toArray();
    for (const auto &value : segments) {
        const auto item = value.toObject();
        const double start = item.value("start").toDouble(-1), end = item.value("end").toDouble(-1);
        const QString text = item.value(words && item.contains("word") ? "word" : "text").toString().trimmed();
        if (!std::isfinite(start) || !std::isfinite(end) || start < 0 || end <= start || text.isEmpty()) continue;
        if (words && !cues.isEmpty() && cues.last().text.size() + text.size() < 48 && end + offset - cues.last().start < 4 &&
            start + offset - cues.last().end < 0.6) {
            cues.last().text += QLatin1Char(' ') + text;
            cues.last().end = end + offset;
        } else
            cues.append({start + offset, end + offset, text});
    }
    if (cues.isEmpty() && !response.value("text").toString().trimmed().isEmpty() && error)
        *error = i18n("This transcription model returned text without timestamps. Choose a model supporting timed subtitles.");
    return cues;
}
CaptionClient::CaptionClient(QObject *parent, const QVector<Provider> &endpoints)
    : QObject(parent)
    , m_network(this)
    , m_endpoints(endpoints)
{
}
void CaptionClient::cancel()
{
    if (m_reply) {
        disconnect(m_reply, nullptr, this, nullptr);
        m_reply->abort();
        m_reply->deleteLater();
        m_reply.clear();
    }
    m_key.clear();
    m_pcm.clear();
}
QNetworkRequest CaptionClient::request(int provider, const QString &key, const QString &path) const
{
    QNetworkRequest req(m_endpoints[provider].base.resolved(QUrl(path)));
    req.setTransferTimeout(300000);
    req.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    if (m_endpoints[provider].messages) {
        req.setRawHeader("x-api-key", key.toUtf8());
        req.setRawHeader("anthropic-version", "2023-06-01");
    } else
        req.setRawHeader("Authorization", "Bearer " + key.toUtf8());
    return req;
}
void CaptionClient::finish(QNetworkReply *reply, const QString &key, const std::function<void(const QJsonObject &)> &callback)
{
    m_reply = reply;
    connect(reply, &QNetworkReply::finished, this, [this, reply, key, callback] {
        const QByteArray data = reply->readAll();
        const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const auto object = QJsonDocument::fromJson(data).object();
        const bool success = reply->error() == QNetworkReply::NoError && status >= 200 && status < 300 && !object.isEmpty();
        QString error = object.value("error").toObject().value("message").toString(reply->errorString());
        if (!key.isEmpty()) error.replace(key, QStringLiteral("[key]"));
        reply->deleteLater();
        m_reply.clear();
        if (!success) {
            m_key.clear();
            Q_EMIT failed(i18n("Provider request failed (%1): %2", status, error.left(800)));
        } else
            callback(object);
    });
}
void CaptionClient::models(int provider, const QString &key)
{
    cancel();
    finish(m_network.get(request(provider, key, QStringLiteral("models"))), key, [this](const QJsonObject &object) {
        QStringList ids;
        for (const auto &model : object.value("data").toArray())
            ids.append(model.toObject().value("id").toString());
        ids.removeAll(QString());
        ids.sort();
        Q_EMIT modelsReady(ids);
    });
}
void CaptionClient::transcribe(int provider, const QString &key, const QString &model, const QString &wav)
{
    cancel();
    if (provider != 0 && provider != 1) {
        Q_EMIT failed(i18n("Use local Whisper for this provider."));
        return;
    }
    QFile file(wav);
    if (!file.open(QIODevice::ReadOnly)) {
        Q_EMIT failed(i18n("Cannot read the extracted audio."));
        return;
    }
    const QByteArray header = file.read(44);
    if (header.size() != 44 || header.mid(0, 4) != "RIFF" || header.mid(36, 4) != "data" || qFromLittleEndian<quint32>(header.constData() + 24) != 32000 ||
        qFromLittleEndian<quint16>(header.constData() + 22) != 1) {
        Q_EMIT failed(i18n("The extracted audio has an invalid format."));
        return;
    }
    m_pcm = file.readAll();
    m_chunk = 0;
    m_cues.clear();
    m_provider = provider;
    m_key = key;
    m_model = model;
    nextTranscription();
}
static QByteArray wavHeader(quint32 size)
{
    QByteArray header(44, '\0');
    header.replace(0, 4, "RIFF");
    header.replace(8, 8, "WAVEfmt ");
    header.replace(36, 4, "data");
    qToLittleEndian<quint32>(size + 36, header.data() + 4);
    qToLittleEndian<quint32>(16, header.data() + 16);
    qToLittleEndian<quint16>(1, header.data() + 20);
    qToLittleEndian<quint16>(1, header.data() + 22);
    qToLittleEndian<quint32>(32000, header.data() + 24);
    qToLittleEndian<quint32>(64000, header.data() + 28);
    qToLittleEndian<quint16>(2, header.data() + 32);
    qToLittleEndian<quint16>(16, header.data() + 34);
    qToLittleEndian<quint32>(size, header.data() + 40);
    return header;
}
void CaptionClient::nextTranscription()
{
    constexpr int ChunkBytes = 300 * 32000 * 2;
    const qsizetype start = qsizetype(m_chunk) * ChunkBytes;
    if (start >= m_pcm.size()) {
        m_key.clear();
        m_pcm.clear();
        Q_EMIT captionsReady(m_cues);
        return;
    }
    Q_EMIT progress(i18n("Transcribing audio part %1 of %2…", m_chunk + 1, (m_pcm.size() + ChunkBytes - 1) / ChunkBytes));
    auto *multipart = new QHttpMultiPart(QHttpMultiPart::FormDataType);
    auto field = [multipart](const QByteArray &name, const QByteArray &body) {
        QHttpPart part;
        part.setHeader(QNetworkRequest::ContentDispositionHeader, QString::fromLatin1("form-data; name=\"" + name + "\""));
        part.setBody(body);
        multipart->append(part);
    };
    field("model", m_model.toUtf8());
    if (m_provider == 0) {
        field("response_format", m_model.contains(QLatin1String("diarize")) ? QByteArray("diarized_json") : QByteArray("verbose_json"));
        if (m_model.contains(QLatin1String("diarize"))) field("chunking_strategy", "auto");
        if (m_model == QLatin1String("whisper-1")) field("timestamp_granularities[]", "word");
    }
    const QByteArray pcm = m_pcm.mid(start, ChunkBytes);
    QHttpPart audio;
    audio.setHeader(QNetworkRequest::ContentDispositionHeader, QStringLiteral("form-data; name=\"file\"; filename=\"audio.wav\""));
    audio.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("audio/wav"));
    audio.setBody(wavHeader(quint32(pcm.size())) + pcm);
    multipart->append(audio);
    auto *reply = m_network.post(request(m_provider, m_key, m_provider == 0 ? QStringLiteral("audio/transcriptions") : QStringLiteral("stt")), multipart);
    multipart->setParent(reply);
    finish(reply, m_key, [this](const QJsonObject &object) {
        QString error;
        const auto cues = transcriptionCues(object, m_chunk * 300.0, &error);
        if (!error.isEmpty()) {
            m_key.clear();
            Q_EMIT failed(error);
            return;
        }
        m_cues += cues;
        ++m_chunk;
        nextTranscription();
    });
}
QJsonObject CaptionClient::polishBody(int provider, const QString &model, const QString &effort, const QVector<Cue> &cues)
{
    QJsonArray items;
    for (int i = 0; i < cues.size(); ++i)
        items.append(QJsonObject{{"id", i}, {"text", cues[i].text}});
    const QString instructions =
        QStringLiteral(
            "Correct punctuation and obvious transcription errors only. Preserve the original language and meaning. "
            "Do not invent speech. Return ONLY a JSON object with a captions array, each item containing the original integer id and corrected text. "
            "Keep every id exactly once, in order. Input: ") +
        QString::fromUtf8(QJsonDocument(items).toJson(QJsonDocument::Compact));
    QJsonObject body{{"model", model}};
    if (provider == 2) {
        body.insert("max_tokens", 16384);
        body.insert("messages", QJsonArray{QJsonObject{{"role", "user"}, {"content", instructions}}});
        if (!effort.isEmpty()) {
            body.insert("thinking", QJsonObject{{"type", "adaptive"}});
            body.insert("output_config", QJsonObject{{"effort", effort}});
        }
    } else if (provider == 0 || provider == 1) {
        body.insert("input", instructions);
        body.insert("store", false);
        if (!effort.isEmpty()) body.insert("reasoning", QJsonObject{{"effort", effort}});
    } else {
        body.insert("messages", QJsonArray{QJsonObject{{"role", "user"}, {"content", instructions}}});
        if (!effort.isEmpty()) {
            if (provider == 3) {
                body.insert("thinking", QJsonObject{{"type", "enabled"}});
                body.insert("reasoning_effort", effort);
            } else
                body.insert("reasoning", QJsonObject{{"enabled", true}, {"effort", effort}});
        }
    }
    return body;
}
void CaptionClient::polish(int provider, const QString &key, const QString &model, const QString &effort, const QVector<Cue> &cues)
{
    cancel();
    m_provider = provider;
    m_key = key;
    m_model = model;
    m_effort = effort;
    m_cues = cues;
    m_chunk = 0;
    m_polished.clear();
    nextPolish();
}
void CaptionClient::nextPolish()
{
    const auto chunk = m_cues.mid(m_chunk * 80, 80);
    if (chunk.isEmpty()) {
        m_key.clear();
        Q_EMIT captionsReady(m_polished);
        return;
    }
    Q_EMIT progress(i18n("Editing subtitle part %1…", m_chunk + 1));
    auto req = request(m_provider, m_key,
                       m_provider == 2   ? QStringLiteral("messages")
                       : m_provider <= 1 ? QStringLiteral("responses")
                                         : QStringLiteral("chat/completions"));
    req.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("application/json"));
    finish(m_network.post(req, QJsonDocument(polishBody(m_provider, m_model, m_effort, chunk)).toJson(QJsonDocument::Compact)), m_key,
           [this, chunk](const QJsonObject &object) {
               QString text;
               if (m_provider == 2) {
                   for (const auto &block : object.value("content").toArray())
                       if (block.toObject().value("type") == "text") text += block.toObject().value("text").toString();
               } else if (m_provider <= 1) {
                   for (const auto &item : object.value("output").toArray())
                       for (const auto &block : item.toObject().value("content").toArray())
                           if (block.toObject().value("type") == "output_text") text += block.toObject().value("text").toString();
               } else {
                   const auto choices = object.value("choices").toArray();
                   if (!choices.isEmpty()) text = choices.first().toObject().value("message").toObject().value("content").toString();
               }
               if (text.trimmed().startsWith(QLatin1String("```"))) {
                   text = text.mid(text.indexOf(QLatin1Char('\n')) + 1);
                   text = text.left(text.lastIndexOf(QStringLiteral("```")));
               }
               const auto captions = QJsonDocument::fromJson(text.toUtf8()).object().value("captions").toArray();
               QVector<Cue> corrected;
               bool valid = captions.size() == chunk.size();
               for (int i = 0; valid && i < captions.size(); ++i) {
                   const auto item = captions[i].toObject();
                   valid = item.value("id").toInt(-1) == i && !item.value("text").toString().trimmed().isEmpty();
                   corrected.append({chunk[i].start, chunk[i].end, item.value("text").toString().trimmed()});
               }
               if (!valid) {
                   m_key.clear();
                   Q_EMIT failed(i18n("The model returned invalid captions. Your original text and timing are preserved."));
                   return;
               }
               m_polished += corrected;
               ++m_chunk;
               nextPolish();
           });
}
} // namespace AudioVisualizer
