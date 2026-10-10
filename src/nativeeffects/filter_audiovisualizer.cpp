/* SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL */
#include "../audiovisualizer/spectrum.hpp"
#include <QJsonDocument>
#include <QMutex>
#include <QMutexLocker>
#include <QPainter>
#include <algorithm>
#include <cstring>
#include <limits>
#include <mlt++/Mlt.h>

namespace {
struct State
{
    QMutex mutex;
    QString spectrumPath, backgroundPath, portraitPath;
    AudioVisualizer::Spectrum spectrum;
    QImage portrait, backgroundImage;
    std::unique_ptr<Mlt::Profile> backgroundProfile;
    std::unique_ptr<Mlt::Producer> background;
};
void destroyState(void *data)
{
    delete static_cast<State *>(data);
}
QString property(mlt_properties properties, const char *name)
{
    const char *value = mlt_properties_get(properties, name);
    return value ? QString::fromUtf8(value) : QString();
}
int getImage(mlt_frame frame, uint8_t **image, mlt_image_format *format, int *width, int *height, int)
{
    auto filter = static_cast<mlt_filter>(mlt_frame_pop_service(frame));
    *format = mlt_image_rgba;
    int error = mlt_frame_get_image(frame, image, format, width, height, 0);
    if (error || !*image || *width < 1 || *height < 1) return error ? error : 1;
    const qint64 bytes = qint64(*width) * *height * 4;
    if (bytes > std::numeric_limits<int>::max()) return 1;
    auto *output = static_cast<uint8_t *>(mlt_pool_alloc(int(bytes)));
    if (!output) return 1;
    std::memcpy(output, *image, size_t(bytes));
    auto properties = MLT_FILTER_PROPERTIES(filter);
    mlt_service_lock(MLT_FILTER_SERVICE(filter));
    auto *state = static_cast<State *>(mlt_properties_get_data(properties, "_visualizer_state", nullptr));
    if (!state) {
        state = new State;
        mlt_properties_set_data(properties, "_visualizer_state", state, 0, destroyState, nullptr);
    }
    mlt_service_unlock(MLT_FILTER_SERVICE(filter));
    QMutexLocker lock(&state->mutex);
    // MLT recognizes these file properties when resolving saved relative paths.
    const QString spectrumPath = property(properties, "filename");
    if (state->spectrumPath != spectrumPath) {
        state->spectrumPath = spectrumPath;
        state->spectrum = AudioVisualizer::Spectrum::load(spectrumPath);
    }
    const auto settings = QJsonDocument::fromJson(property(properties, "settings").toUtf8()).object();
    const int position = std::max(0, int(mlt_filter_get_position(filter, frame) + mlt_filter_get_in(filter)));
    const double fps = mlt_profile_fps(mlt_service_profile(MLT_FILTER_SERVICE(filter)));
    QImage canvas(output, *width, *height, QImage::Format_RGBA8888);
    const QString background = property(properties, "resource");
    if (state->backgroundPath != background) {
        state->backgroundPath = background;
        state->background.reset();
        state->backgroundProfile.reset();
        state->backgroundImage = background.isEmpty() ? QImage() : QImage(background);
        if (!background.isEmpty() && state->backgroundImage.isNull()) {
            state->backgroundProfile = std::make_unique<Mlt::Profile>(mlt_profile_clone(mlt_service_profile(MLT_FILTER_SERVICE(filter))));
            auto &profile = *state->backgroundProfile;
            state->background = std::make_unique<Mlt::Producer>(profile, "avformat", background.toUtf8().constData());
            state->background->set("audio_index", -1);
            state->background->set("set.test_audio", 1);
            Mlt::Filter convert(profile, "avcolor_space"), scale(profile, "swscale"), imageConvert(profile, "imageconvert");
            state->background->attach(convert);
            state->background->attach(scale);
            state->background->attach(imageConvert);
        }
    }
    auto drawBackground = [&](const QImage &bg) {
        QPainter p(&canvas);
        p.setRenderHint(QPainter::SmoothPixmapTransform);
        const double scale = std::max(double(*width) / bg.width(), double(*height) / bg.height());
        p.drawImage(QRectF((*width - bg.width() * scale) / 2, (*height - bg.height() * scale) / 2, bg.width() * scale, bg.height() * scale), bg);
        p.fillRect(canvas.rect(), QColor(0, 0, 0, int(std::clamp(settings.value("dim").toDouble(25), 0.0, 100.0) * 2.55)));
    };
    if (!state->backgroundImage.isNull()) {
        drawBackground(state->backgroundImage);
    } else if (state->background && state->background->is_valid()) {
        state->background->seek(position % std::max(1, state->background->get_length()));
        std::unique_ptr<Mlt::Frame> bgFrame(state->background->get_frame());
        int w = *width, h = *height;
        mlt_image_format bgFormat = mlt_image_rgba;
        auto *pixels = bgFrame->get_image(bgFormat, w, h);
        if (pixels && bgFormat == mlt_image_rgba) {
            drawBackground(QImage(pixels, w, h, QImage::Format_RGBA8888));
        }
    }
    const QString portrait = property(properties, "filter.resource");
    if (state->portraitPath != portrait) {
        state->portraitPath = portrait;
        state->portrait = portrait.isEmpty() ? QImage() : QImage(portrait);
    }
    AudioVisualizer::paint(canvas, AudioVisualizer::amplitudes(state->spectrum, position / std::max(1.0, fps), settings), settings, state->portrait);
    mlt_frame_set_image(frame, output, int(bytes), mlt_pool_release);
    *image = output;
    *format = mlt_image_rgba;
    return 0;
}
mlt_frame process(mlt_filter filter, mlt_frame frame)
{
    mlt_frame_push_service(frame, filter);
    mlt_frame_push_get_image(frame, getImage);
    return frame;
}
} // namespace
extern "C" mlt_filter createAudioVisualizer(mlt_profile, mlt_service_type, const char *, const void *)
{
    auto filter = mlt_filter_new();
    if (!filter) return nullptr;
    filter->process = process;
    mlt_properties_set(MLT_FILTER_PROPERTIES(filter), "settings", QJsonDocument(AudioVisualizer::defaults()).toJson(QJsonDocument::Compact).constData());
    return filter;
}
extern "C" mlt_properties audioVisualizerMetadata(mlt_service_type, const char *id, void *)
{
    auto properties = mlt_properties_new();
    mlt_properties_set(properties, "identifier", id);
    mlt_properties_set(properties, "title", "Audio Visualizer");
    mlt_properties_set(properties, "description", "Rounded bars and circular spectra from measured audio frequencies");
    mlt_properties_set(properties, "version", "1");
    return properties;
}
