/* SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL */
#include "../audiovisualizer/captionclient.hpp"
#include "../audiovisualizer/spectrum.hpp"
#include <QEventLoop>
#include <QFile>
#include <QGuiApplication>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QTimer>
#include <QtEndian>
#include <algorithm>
#include <cmath>
#include <iostream>
#include <mlt++/Mlt.h>

extern "C" mlt_filter createAudioVisualizer(mlt_profile, mlt_service_type, const char *, const void *);
using namespace AudioVisualizer;
#define CHECK(condition)                                                                                                                                       \
    do {                                                                                                                                                       \
        if (!(condition)) {                                                                                                                                    \
            std::cerr << "FAILED line " << __LINE__ << ": " << #condition << '\n';                                                                             \
            return 1;                                                                                                                                          \
        }                                                                                                                                                      \
    } while (false)
static QImage imageAt(Mlt::Producer &producer, int position)
{
    producer.seek(position);
    std::unique_ptr<Mlt::Frame> frame(producer.get_frame());
    int w = 640, h = 360;
    mlt_image_format format = mlt_image_rgba;
    auto *data = frame->get_image(format, w, h);
    return data && format == mlt_image_rgba ? QImage(data, w, h, QImage::Format_RGBA8888).copy() : QImage();
}
int main(int argc, char **argv)
{
    QGuiApplication app(argc, argv);
    QTemporaryDir directory;
    CHECK(directory.isValid());
    QVector<float> pcm(SampleRate * 2);
    for (int i = 0; i < SampleRate; ++i)
        pcm[i] = 0.25f * std::sin(2 * M_PI * 440 * i / SampleRate);
    for (int i = SampleRate; i < pcm.size(); ++i)
        pcm[i] = 0.25f * std::sin(2 * M_PI * 4000 * i / SampleRate);
    const auto data = analyze(pcm, 30);
    CHECK(data.frames() == 60);
    auto config = defaults();
    config.insert("smoothing", 0);
    const auto low = amplitudes(data, 0.5, config), high = amplitudes(data, 1.5, config);
    const int lowBand = int(std::max_element(low.begin(), low.end()) - low.begin());
    const int highBand = int(std::max_element(high.begin(), high.end()) - high.begin());
    CHECK(std::abs(lowBand - int(std::log(440.0 / 30) / std::log(500.0) * Bands)) <= 1);
    CHECK(std::abs(highBand - int(std::log(4000.0 / 30) / std::log(500.0) * Bands)) <= 1);
    CHECK(lowBand < highBand && low[lowBand] > 0.7f);
    const auto silence = analyze(QVector<float>(SampleRate, 0), 30);
    const auto quiet = amplitudes(silence, 0.5, config);
    CHECK(*std::max_element(quiet.begin(), quiet.end()) == 0);
    CHECK(analyze({}, 30).frames() == 0 && analyze(pcm, 0).frames() == 0);
    const QString spectrum = directory.filePath("audio.kdviz");
    CHECK(data.save(spectrum));
    CHECK(Spectrum::load(spectrum).levels == data.levels);
    QFile corrupt(directory.filePath("broken.kdviz"));
    CHECK(corrupt.open(QIODevice::WriteOnly));
    corrupt.write("KDVIZ001");
    corrupt.close();
    CHECK(Spectrum::load(corrupt.fileName()).frames() == 0);
    QImage bars(640, 360, QImage::Format_RGBA8888);
    bars.fill(Qt::black);
    paint(bars, low, config);
    QImage ring(640, 360, QImage::Format_RGBA8888);
    ring.fill(Qt::black);
    config.insert("preset", "ring");
    paint(ring, low, config);
    CHECK(bars != ring && bars.pixelColor(0, 0) == Qt::black && ring.pixelColor(320, 180) == Qt::black);
    config.insert("preset", "bars");
    Mlt::Factory::init();
    Mlt::Profile profile;
    profile.set_width(640);
    profile.set_height(360);
    profile.set_frame_rate(30, 1);
    Mlt::Producer producer(profile, "color", "#000000");
    producer.set("length", 60);
    producer.set_in_and_out(0, 59);
    Mlt::Filter filter(createAudioVisualizer(profile.get_profile(), mlt_service_filter_type, "test", nullptr));
    filter.set("mlt_service", "kdenlive_audio_visualizer");
    mlt_service_set_profile(filter.get_service(), profile.get_profile());
    filter.set("_unique_id", "visualizer-test");
    filter.set("filename", spectrum.toUtf8().constData());
    filter.set("settings", QJsonDocument(config).toJson(QJsonDocument::Compact).constData());
    producer.attach(filter);
    const QImage nativeLow = imageAt(producer, 15), nativeHigh = imageAt(producer, 45);
    CHECK(!nativeLow.isNull() && nativeLow != nativeHigh);
    CHECK(imageAt(producer, 15) == nativeLow); // Scrubbing backward gives exactly the same result.
    filter.set_in_and_out(10, 59);
    CHECK(imageAt(producer, 15) == nativeLow); // Trimming must not restart the spectrum.
    QImage background(640, 360, QImage::Format_RGBA8888);
    background.fill(QColor("#204080"));
    CHECK(background.save(directory.filePath("background.png")));
    filter.set("resource", directory.filePath("background.png").toUtf8().constData());
    const QImage withBackground = imageAt(producer, 15);
    CHECK(withBackground.pixelColor(0, 0) != Qt::black);
    {
        Mlt::Consumer writer(profile, "xml", "string");
        writer.set("root", directory.path().toUtf8().constData());
        writer.connect(producer);
        CHECK(writer.run() == 0);
        const QString xml = QString::fromUtf8(writer.get("string"));
        CHECK(xml.contains(QStringLiteral(">background.png<")) && xml.contains(QStringLiteral(">audio.kdviz<")));
        Mlt::Producer restored(profile, "xml-string", xml.toUtf8().constData());
        CHECK(restored.is_valid() && imageAt(restored, 15) == withBackground);
    }
    filter.set("resource", "");
    CHECK(imageAt(producer, 15).pixelColor(0, 0) == Qt::black);
    const QVector<Cue> cues{{0.25, 1.25, QStringLiteral("Hello, world.")}, {2, 3, QStringLiteral("Second line.")}};
    QString error;
    auto parsed = fromSrt(toSrt(cues), &error);
    CHECK(error.isEmpty() && parsed.size() == 2 && parsed[0].start == 0.25 && parsed[1].text == cues[1].text);
    CHECK(fromSrt(QStringLiteral("1\n00:00:03,000 --> 00:00:02,000\nBad\n"), &error).isEmpty() && !error.isEmpty());
    auto transcript = transcriptionCues(QJsonObject{{"words", QJsonArray{QJsonObject{{"start", 0.5}, {"end", 1.0}, {"word", "Hello"}},
                                                                         QJsonObject{{"start", 1.0}, {"end", 1.5}, {"word", "world"}}}}},
                                        300);
    CHECK(transcript.size() == 1 && transcript[0].start == 300.5 && transcript[0].end == 301.5 && transcript[0].text == "Hello world");
    error.clear();
    CHECK(transcriptionCues(QJsonObject{{"text", "Untimed"}}, 0, &error).isEmpty() && !error.isEmpty());
    for (int provider = 0; provider < 5; ++provider) {
        auto body = CaptionClient::polishBody(provider, QStringLiteral("chosen-model"), {}, cues);
        CHECK(body.value("model").toString() == "chosen-model");
        CHECK(!body.contains("reasoning") && !body.contains("reasoning_effort") && !body.contains("output_config"));
    }
    CHECK(CaptionClient::polishBody(2, "model", "high", cues).value("output_config").toObject().value("effort") == "high");
    CHECK(CaptionClient::polishBody(3, "model", "max", cues).value("reasoning_effort") == "max");
    CHECK(CaptionClient::polishBody(0, "model", "low", cues).value("reasoning").toObject().value("effort") == "low");
    CHECK(CaptionClient::polishBody(4, "model", "high", cues).value("reasoning").toObject().value("enabled").toBool());
    // Exercise real asynchronous HTTP requests without sending audio or keys to any provider.
    for (int provider = 0; provider < 5; ++provider) {
        QTcpServer server;
        CHECK(server.listen(QHostAddress::LocalHost, 0));
        auto endpoints = providers();
        endpoints[provider].base = QUrl(QStringLiteral("http://127.0.0.1:%1/v1/").arg(server.serverPort()));
        CaptionClient client(nullptr, endpoints);
        QEventLoop loop;
        QString failure;
        QVector<Cue> received;
        QByteArray requestBytes;
        QObject::connect(&server, &QTcpServer::newConnection, &loop, [&] {
            auto *socket = server.nextPendingConnection();
            QObject::connect(socket, &QTcpSocket::readyRead, &loop, [&, socket] {
                requestBytes += socket->readAll();
                const int separator = requestBytes.indexOf("\r\n\r\n");
                if (separator < 0) return;
                const auto headers = requestBytes.left(separator).split('\n');
                int length = 0;
                for (const auto &header : headers)
                    if (header.toLower().startsWith("content-length:")) length = header.mid(15).trimmed().toInt();
                if (requestBytes.size() < separator + 4 + length) return;
                const QString corrected = QStringLiteral("{\"captions\":[{\"id\":0,\"text\":\"Corrected.\"},{\"id\":1,\"text\":\"Second.\"}]}");
                QJsonObject response;
                if (provider == 2)
                    response.insert("content", QJsonArray{QJsonObject{{"type", "text"}, {"text", corrected}}});
                else if (provider <= 1)
                    response.insert("output", QJsonArray{QJsonObject{{"type", "message"},
                                                                     {"content", QJsonArray{QJsonObject{{"type", "output_text"}, {"text", corrected}}}}}});
                else
                    response.insert("choices", QJsonArray{QJsonObject{{"message", QJsonObject{{"content", corrected}}}}});
                const QByteArray body = QJsonDocument(response).toJson(QJsonDocument::Compact);
                socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + QByteArray::number(body.size()) +
                              "\r\nConnection: close\r\n\r\n" + body);
                socket->disconnectFromHost();
            });
        });
        QObject::connect(&client, &CaptionClient::failed, &loop, [&](const QString &message) {
            failure = message;
            loop.quit();
        });
        QObject::connect(&client, &CaptionClient::captionsReady, &loop, [&](const QVector<Cue> &result) {
            received = result;
            loop.quit();
        });
        QTimer::singleShot(3000, &loop, &QEventLoop::quit);
        client.polish(provider, QStringLiteral("test-key"), QStringLiteral("chosen-model"), QStringLiteral("high"), cues);
        loop.exec();
        CHECK(failure.isEmpty() && received.size() == 2);
        CHECK(received[0].start == cues[0].start && received[0].end == cues[0].end && received[0].text == "Corrected.");
        CHECK(requestBytes.contains("chosen-model"));
        CHECK(requestBytes.toLower().contains(provider == 2 ? "x-api-key: test-key" : "authorization: bearer test-key"));
        CHECK(requestBytes.startsWith(provider == 2 ? "POST /v1/messages" : provider <= 1 ? "POST /v1/responses" : "POST /v1/chat/completions"));
    }
    // Transcription uses multipart WAV uploads and actual provider timestamp
    // formats, including diarization's required automatic chunking setting.
    QByteArray wav(44 + SampleRate * 2, '\0');
    wav.replace(0, 4, "RIFF");
    wav.replace(8, 8, "WAVEfmt ");
    wav.replace(36, 4, "data");
    qToLittleEndian<quint32>(quint32(wav.size() - 8), wav.data() + 4);
    qToLittleEndian<quint32>(16, wav.data() + 16);
    qToLittleEndian<quint16>(1, wav.data() + 20);
    qToLittleEndian<quint16>(1, wav.data() + 22);
    qToLittleEndian<quint32>(SampleRate, wav.data() + 24);
    qToLittleEndian<quint32>(SampleRate * 2, wav.data() + 28);
    qToLittleEndian<quint16>(2, wav.data() + 32);
    qToLittleEndian<quint16>(16, wav.data() + 34);
    qToLittleEndian<quint32>(SampleRate * 2, wav.data() + 40);
    QFile wavFile(directory.filePath("speech.wav"));
    CHECK(wavFile.open(QIODevice::WriteOnly) && wavFile.write(wav) == wav.size());
    wavFile.close();
    for (int mode = 0; mode < 3; ++mode) {
        const int provider = mode == 1 ? 1 : 0;
        const QString model = mode == 0   ? QStringLiteral("whisper-1")
                              : mode == 1 ? QStringLiteral("grok-voice-transcribe-2.0")
                                          : QStringLiteral("gpt-4o-transcribe-diarize");
        QTcpServer server;
        CHECK(server.listen(QHostAddress::LocalHost, 0));
        auto endpoints = providers();
        endpoints[provider].base = QUrl(QStringLiteral("http://127.0.0.1:%1/v1/").arg(server.serverPort()));
        CaptionClient client(nullptr, endpoints);
        QEventLoop loop;
        QString failure;
        QVector<Cue> received;
        QByteArray requestBytes;
        QObject::connect(&server, &QTcpServer::newConnection, &loop, [&] {
            auto *socket = server.nextPendingConnection();
            QObject::connect(socket, &QTcpSocket::readyRead, &loop, [&, socket] {
                requestBytes += socket->readAll();
                const int separator = requestBytes.indexOf("\r\n\r\n");
                if (separator < 0) return;
                int length = 0;
                for (const auto &header : requestBytes.left(separator).split('\n'))
                    if (header.toLower().startsWith("content-length:")) length = header.mid(15).trimmed().toInt();
                if (requestBytes.size() < separator + 4 + length) return;
                const QJsonObject token{{"start", 0.2}, {"end", 0.8}, {mode == 0 ? "word" : "text", "Hello."}};
                const QJsonObject response{{mode == 2 ? "segments" : "words", QJsonArray{token}}};
                const QByteArray body = QJsonDocument(response).toJson(QJsonDocument::Compact);
                socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + QByteArray::number(body.size()) +
                              "\r\nConnection: close\r\n\r\n" + body);
                socket->disconnectFromHost();
            });
        });
        QObject::connect(&client, &CaptionClient::failed, &loop, [&](const QString &message) {
            failure = message;
            loop.quit();
        });
        QObject::connect(&client, &CaptionClient::captionsReady, &loop, [&](const QVector<Cue> &result) {
            received = result;
            loop.quit();
        });
        QTimer::singleShot(3000, &loop, &QEventLoop::quit);
        client.transcribe(provider, QStringLiteral("test-key"), model, wavFile.fileName());
        loop.exec();
        CHECK(failure.isEmpty() && received.size() == 1);
        CHECK(received[0].start == 0.2 && received[0].end == 0.8 && received[0].text == "Hello.");
        CHECK(requestBytes.startsWith(provider == 0 ? "POST /v1/audio/transcriptions" : "POST /v1/stt"));
        CHECK(requestBytes.contains("audio/wav") && requestBytes.contains("RIFF") && requestBytes.contains(model.toUtf8()));
        CHECK(requestBytes.indexOf("name=\"model\"") < requestBytes.indexOf("name=\"file\""));
        if (mode == 2) CHECK(requestBytes.contains("name=\"chunking_strategy\"") && requestBytes.contains("auto"));
    }
    std::cout << "Spectrum, deterministic rendering, trims, backgrounds, subtitle timing and provider protocols passed.\n";
    return 0;
}
