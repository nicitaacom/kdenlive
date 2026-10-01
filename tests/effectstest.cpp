/*
    SPDX-FileCopyrightText: 2017-2019 Nicolas Carion <french.ebook.lover@gmail.com>
    SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
*/
#include "catch.hpp"
#include "test_utils.hpp"
// test specific headers
#include "doc/docundostack.hpp"
#include "doc/kdenlivedoc.h"

#include "core.h"
#include "effects/effectsrepository.hpp"
#include "effects/effectstack/model/effectitemmodel.hpp"
#include "effects/effectstack/model/effectstackmodel.hpp"
#include "effects/effectstack/model/nativepresetanimation.hpp"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>

QString anEffect;
TEST_CASE("Effects stack", "[Effects]")
{
    // Create timeline
    auto binModel = pCore->projectItemModel();
    std::shared_ptr<DocUndoStack> undoStack = std::make_shared<DocUndoStack>(nullptr);

    // Here we do some trickery to enable testing.
    // We mock the project class so that the undoStack function returns our undoStack
    KdenliveDoc document(undoStack);

    pCore->projectManager()->testSetDocument(&document);
    QDateTime documentDate = QDateTime::currentDateTime();
    KdenliveTests::updateTimeline(false, QString(), QString(), documentDate, 0);
    auto timeline = document.getTimeline(document.uuid());
    pCore->projectManager()->testSetActiveTimeline(timeline);

    // Create a request
    int tid1;
    REQUIRE(timeline->requestTrackInsertion(-1, tid1));

    // Create clip
    QString binId = KdenliveTests::createProducer(pCore->getProjectProfile(), "red", binModel);
    int cid1;
    REQUIRE(timeline->requestClipInsertion(binId, tid1, 100, cid1));
    std::shared_ptr<ProjectClip> clip = binModel->getClipByBinID(binId);

    auto model = clip->getEffectStack();

    REQUIRE(model->checkConsistency());
    REQUIRE(model->rowCount() == 0);

    // Check whether repo works
    QVector<QPair<QString, QString>> effects = EffectsRepository::get()->getNames();
    REQUIRE(!effects.isEmpty());

    anEffect = QStringLiteral("sepia"); // effects.first().first;

    REQUIRE(!anEffect.isEmpty());

    SECTION("Create and delete effects")
    {
        REQUIRE(model->appendEffect(anEffect));
        REQUIRE(model->checkConsistency());
        REQUIRE(model->rowCount() == 1);

        REQUIRE(model->appendEffect(anEffect));
        REQUIRE(model->checkConsistency());
        REQUIRE(model->rowCount() == 2);

        undoStack->undo();
        REQUIRE(model->checkConsistency());
        REQUIRE(model->rowCount() == 1);
    }

    SECTION("Create cut with fade in")
    {
        auto clipModel = timeline->getClipEffectStackModel(cid1);
        REQUIRE(clipModel->rowCount() == 0);
        clipModel->appendEffect("fade_from_black");
        REQUIRE(clipModel->checkConsistency());
        REQUIRE(clipModel->rowCount() == 1);

        int l = timeline->getClipPlaytime(cid1);
        REQUIRE(TimelineFunctions::requestClipCut(timeline, cid1, 100 + l - 10));
        int splitted = timeline->getClipByPosition(tid1, 100 + l - 9);
        auto splitModel = timeline->getClipEffectStackModel(splitted);
        REQUIRE(clipModel->rowCount() == 1);
        REQUIRE(splitModel->rowCount() == 0);
    }

    SECTION("Create cut with fade out")
    {
        auto clipModel = timeline->getClipEffectStackModel(cid1);
        REQUIRE(clipModel->rowCount() == 0);
        clipModel->appendEffect("fade_to_black");
        REQUIRE(clipModel->checkConsistency());
        REQUIRE(clipModel->rowCount() == 1);

        int l = timeline->getClipPlaytime(cid1);
        REQUIRE(TimelineFunctions::requestClipCut(timeline, cid1, 100 + l - 10));
        int splitted = timeline->getClipByPosition(tid1, 100 + l - 9);
        auto splitModel = timeline->getClipEffectStackModel(splitted);
        REQUIRE(clipModel->rowCount() == 0);
        REQUIRE(splitModel->rowCount() == 1);
    }

    SECTION("Apply and undo a fitted native transition with event-relative adjustment curves")
    {
        auto clipModel = timeline->getClipEffectStackModel(cid1);
        REQUIRE(clipModel->rowCount() == 0);
        // Exercise the exact generated Effects Library record rather than a
        // hand-built stand-in: source identity, role, values, and editable
        // adjustment curves must survive EffectStackModel insertion.
        const QString presetId = QStringLiteral("native.transition.5ca7af07-aeac-4dc1-84ff-2adde18ede37");
        REQUIRE(EffectsRepository::get()->exists(presetId));
        const QDomElement group = EffectsRepository::get()->getXml(presetId);
        REQUIRE(group.attribute(QStringLiteral("sourceId")) == QStringLiteral("{5CA7AF07-AEAC-4DC1-84FF-2ADDE18EDE37}"));
        REQUIRE(group.attribute(QStringLiteral("nativePresetVersion")) == QStringLiteral("1"));
        REQUIRE(group.attribute(QStringLiteral("transitionRole")) == QStringLiteral("out"));

        Fun undo = []() { return true; };
        Fun redo = []() { return true; };
        REQUIRE(clipModel->fromXml(group, undo, redo));
        REQUIRE(clipModel->rowCount() == 1);
        auto asset = clipModel->getAssetModelById(QStringLiteral("kdenlive_motion_curve"));
        REQUIRE(asset != nullptr);
        auto fittedEffect = std::static_pointer_cast<EffectItemModel>(asset);
        const int filterIn = fittedEffect->filter().get_in();
        const int eventFrames = timeline->getClipPlaytime(cid1);
        REQUIRE(eventFrames > 1);
        CHECK(QString::fromUtf8(fittedEffect->filter().get("native_preset_id")) ==
              QStringLiteral("{5CA7AF07-AEAC-4DC1-84FF-2ADDE18EDE37}"));
        const char *raw = fittedEffect->filter().get("shift_y_adjust");
        REQUIRE(raw != nullptr);
        Mlt::Properties animationProperties;
        animationProperties.set("value", raw);
        (void)animationProperties.anim_get_double("value", filterIn, filterIn + eventFrames);
        Mlt::Animation animationKeys = animationProperties.get_animation("value");
        REQUIRE(animationKeys.is_valid());
        REQUIRE(animationKeys.key_count() == 2);
        CHECK(animationKeys.key_get_frame(0) == filterIn);
        CHECK(animationKeys.key_get_frame(1) == filterIn + eventFrames - 1);
        CHECK(animationProperties.anim_get_double("value", filterIn, filterIn + eventFrames) == Approx(0.0));
        CHECK(animationProperties.anim_get_double("value", filterIn + eventFrames - 1, filterIn + eventFrames) == Approx(0.75));

        pCore->pushUndo(undo, redo, QStringLiteral("Apply native transition"));
        undoStack->undo();
        CHECK(clipModel->rowCount() == 0);
        undoStack->redo();
        CHECK(clipModel->rowCount() == 1);
    }
    SECTION("Apply and undo the sparse-key Scroll Left native group")
    {
        auto clipModel = timeline->getClipEffectStackModel(cid1);
        const int durationBefore = timeline->getClipPlaytime(cid1);
        const QString presetId = QStringLiteral("native.transition.a3c456be-54de-4fc4-ab4c-8cfd7aa28a72");
        REQUIRE(EffectsRepository::get()->exists(presetId));
        const QDomElement group = EffectsRepository::get()->getXml(presetId);
        REQUIRE(group.attribute(QStringLiteral("sourceId")) == QStringLiteral("{A3C456BE-54DE-4FC4-AB4C-8CFD7AA28A72}"));
        REQUIRE(group.attribute(QStringLiteral("transitionRole")) == QStringLiteral("out"));
        REQUIRE(group.attribute(QStringLiteral("transitionFrames")) == QStringLiteral("20"));

        Fun undo = []() { return true; };
        Fun redo = []() { return true; };
        REQUIRE(clipModel->fromXml(group, undo, redo));
        REQUIRE(clipModel->rowCount() == 2);
        CHECK(timeline->getClipPlaytime(cid1) == durationBefore);

        auto motionAsset = clipModel->getAssetModelById(QStringLiteral("kdenlive_motion_curve"));
        auto fisheyeAsset = clipModel->getAssetModelById(QStringLiteral("kdenlive_fisheye_warp"));
        REQUIRE(motionAsset != nullptr);
        REQUIRE(fisheyeAsset != nullptr);
        auto motion = std::static_pointer_cast<EffectItemModel>(motionAsset);
        CHECK(QString::fromUtf8(motion->filter().get("native_preset_id")) ==
              QStringLiteral("{A3C456BE-54DE-4FC4-AB4C-8CFD7AA28A72}"));
        CHECK(QString::fromUtf8(motion->filter().get("native_event_role")) == QStringLiteral("outgoing"));
        CHECK(QString::fromUtf8(motion->filter().get("native_event_frames")) == QString::number(durationBefore));
        const char *curveData = motion->filter().get("native_curves");
        REQUIRE(curveData != nullptr);
        const QJsonDocument curveDocument = QJsonDocument::fromJson(QByteArray(curveData));
        REQUIRE(curveDocument.isObject());
        const QJsonArray shiftX = curveDocument.object().value(QStringLiteral("shift_x")).toArray();
        REQUIRE(shiftX.size() == 3);
        CHECK(shiftX[0].toArray()[1].toDouble() == Approx(0.0));
        CHECK(shiftX[1].toArray()[1].toDouble() == Approx(-0.2));
        CHECK(shiftX[2].toArray()[1].toDouble() == Approx(5.0));
        CHECK(shiftX[0].toArray()[0].toDouble() == Approx(0.049).epsilon(0.001));
        CHECK(shiftX[1].toArray()[0].toDouble() == Approx(0.125).epsilon(0.001));
        CHECK(shiftX[2].toArray()[0].toDouble() == Approx(1.0));

        pCore->pushUndo(undo, redo, QStringLiteral("Apply Scroll Left native transition"));
        undoStack->undo();
        CHECK(clipModel->rowCount() == 0);
        CHECK(timeline->getClipPlaytime(cid1) == durationBefore);
        undoStack->redo();
        CHECK(clipModel->rowCount() == 2);
        CHECK(timeline->getClipPlaytime(cid1) == durationBefore);
    }
    SECTION("Apply and undo the outgoing 2.7 Scroll Right cut-peak stack")
    {
        auto clipModel = timeline->getClipEffectStackModel(cid1);
        const int durationBefore = timeline->getClipPlaytime(cid1);
        const QString presetId = QStringLiteral("native.transition.a00199b4-139c-420e-88be-4189a635b769");
        REQUIRE(EffectsRepository::get()->exists(presetId));
        const QDomElement group = EffectsRepository::get()->getXml(presetId);
        REQUIRE(group.attribute(QStringLiteral("sourceId")) == QStringLiteral("{A00199B4-139C-420E-88BE-4189A635B769}"));
        REQUIRE(group.attribute(QStringLiteral("transitionRole")) == QStringLiteral("out"));
        REQUIRE(group.attribute(QStringLiteral("transitionFrames")) == QStringLiteral("20"));

        Fun undo = []() { return true; };
        Fun redo = []() { return true; };
        REQUIRE(clipModel->fromXml(group, undo, redo));
        REQUIRE(clipModel->rowCount() == 2);
        CHECK(timeline->getClipPlaytime(cid1) == durationBefore);
        auto motionAsset = clipModel->getAssetModelById(QStringLiteral("kdenlive_motion_curve"));
        auto fisheyeAsset = clipModel->getAssetModelById(QStringLiteral("kdenlive_fisheye_warp"));
        REQUIRE(motionAsset != nullptr);
        REQUIRE(fisheyeAsset != nullptr);
        auto motion = std::static_pointer_cast<EffectItemModel>(motionAsset);
        CHECK(QString::fromUtf8(motion->filter().get("native_preset_id")) ==
              QStringLiteral("{A00199B4-139C-420E-88BE-4189A635B769}"));
        CHECK(QString::fromUtf8(motion->filter().get("native_event_role")) == QStringLiteral("outgoing"));
        CHECK(QString::fromUtf8(motion->filter().get("native_event_frames")) == QString::number(durationBefore));
        CHECK(QString::fromUtf8(motion->filter().get("shutter_gain_adjust")) == QStringLiteral("0=8"));
        CHECK(QString::fromUtf8(motion->filter().get("quality_samples")) == QStringLiteral("0=32"));

        pCore->pushUndo(undo, redo, QStringLiteral("Apply 2.7 Scroll Right outgoing"));
        undoStack->undo();
        CHECK(clipModel->rowCount() == 0);
        CHECK(timeline->getClipPlaytime(cid1) == durationBefore);
        undoStack->redo();
        CHECK(clipModel->rowCount() == 2);
        CHECK(timeline->getClipPlaytime(cid1) == durationBefore);
    }
    SECTION("Apply and undo the incoming 2.7 Scroll Right cut-peak stack")
    {
        auto clipModel = timeline->getClipEffectStackModel(cid1);
        const int durationBefore = timeline->getClipPlaytime(cid1);
        const QString presetId = QStringLiteral("native.transition.cefdee77-588e-4932-9cbd-5d707852264a");
        REQUIRE(EffectsRepository::get()->exists(presetId));
        const QDomElement group = EffectsRepository::get()->getXml(presetId);
        REQUIRE(group.attribute(QStringLiteral("sourceId")) == QStringLiteral("{CEFDEE77-588E-4932-9CBD-5D707852264A}"));
        REQUIRE(group.attribute(QStringLiteral("transitionRole")) == QStringLiteral("in"));
        REQUIRE(group.attribute(QStringLiteral("transitionFrames")) == QStringLiteral("20"));

        Fun undo = []() { return true; };
        Fun redo = []() { return true; };
        REQUIRE(clipModel->fromXml(group, undo, redo));
        REQUIRE(clipModel->rowCount() == 3);
        CHECK(timeline->getClipPlaytime(cid1) == durationBefore);
        auto motionAsset = clipModel->getAssetModelById(QStringLiteral("kdenlive_motion_curve"));
        auto shakeAsset = clipModel->getAssetModelById(QStringLiteral("kdenlive_shake"));
        auto fisheyeAsset = clipModel->getAssetModelById(QStringLiteral("kdenlive_fisheye_warp"));
        REQUIRE(motionAsset != nullptr);
        REQUIRE(shakeAsset != nullptr);
        REQUIRE(fisheyeAsset != nullptr);
        auto motion = std::static_pointer_cast<EffectItemModel>(motionAsset);
        CHECK(QString::fromUtf8(motion->filter().get("native_preset_id")) ==
              QStringLiteral("{CEFDEE77-588E-4932-9CBD-5D707852264A}"));
        CHECK(QString::fromUtf8(motion->filter().get("native_event_role")) == QStringLiteral("incoming"));
        CHECK(QString::fromUtf8(motion->filter().get("native_event_frames")) == QString::number(durationBefore));
        CHECK(QString::fromUtf8(motion->filter().get("shutter_gain_adjust")) == QStringLiteral("0=16"));
        CHECK(QString::fromUtf8(motion->filter().get("quality_samples")) == QStringLiteral("0=32"));

        pCore->pushUndo(undo, redo, QStringLiteral("Apply 2.7 Scroll Right incoming"));
        undoStack->undo();
        CHECK(clipModel->rowCount() == 0);
        CHECK(timeline->getClipPlaytime(cid1) == durationBefore);
        undoStack->redo();
        CHECK(clipModel->rowCount() == 3);
        CHECK(timeline->getClipPlaytime(cid1) == durationBefore);
    }
    SECTION("Every active native transition group inserts and undoes as one event-local edit")
    {
        auto clipModel = timeline->getClipEffectStackModel(cid1);
        const int durationBefore = timeline->getClipPlaytime(cid1);
        QStringList presetIds;
        for (const auto &entry : EffectsRepository::get()->getNames()) {
            if (entry.first.startsWith(QStringLiteral("native.transition."))) {
                const QDomElement group = EffectsRepository::get()->getXml(entry.first);
                if (group.attribute(QStringLiteral("nativePresetVersion")) == QLatin1String("1")) {
                    presetIds.append(entry.first);
                }
            }
        }
        REQUIRE(presetIds.size() == 194);
        for (const QString &presetId : presetIds) {
            CAPTURE(presetId);
            REQUIRE(clipModel->rowCount() == 0);
            const QDomElement group = EffectsRepository::get()->getXml(presetId);
            REQUIRE(group.attribute(QStringLiteral("nativePresetVersion")) == QLatin1String("1"));
            const int components = group.elementsByTagName(QStringLiteral("effect")).count();
            REQUIRE(components > 0);

            Fun undo = []() { return true; };
            Fun redo = []() { return true; };
            REQUIRE(clipModel->fromXml(group, undo, redo));
            CHECK(clipModel->rowCount() == components);
            CHECK(clipModel->checkConsistency());
            CHECK(timeline->getClipPlaytime(cid1) == durationBefore);

            pCore->pushUndo(undo, redo, QStringLiteral("Apply native transition"));
            undoStack->undo();
            CHECK(clipModel->rowCount() == 0);
            CHECK(clipModel->checkConsistency());
            CHECK(timeline->getClipPlaytime(cid1) == durationBefore);
        }
    }
    timeline.reset();
    clip.reset();
    pCore->projectManager()->closeCurrentDocument(false, false);
}

TEST_CASE("Native transition adjustment curves fit inclusive event frames", "[Effects]")
{
    QString fitted;
    REQUIRE(NativePresetAnimation::fitScalarAnimation(QStringLiteral("0=0;14=0.75"), 15, 120, 42, true, &fitted));
    Mlt::Properties properties;
    properties.set("value", fitted.toUtf8().constData());
    (void)properties.anim_get_double("value", 42, 162);
    Mlt::Animation keys = properties.get_animation("value");
    REQUIRE(keys.is_valid());
    REQUIRE(keys.key_count() == 2);
    CHECK(keys.key_get_frame(0) == 42);
    CHECK(keys.key_get_frame(1) == 161);
    CHECK(properties.anim_get_double("value", 42, 162) == Approx(0.0));
    CHECK(properties.anim_get_double("value", 161, 162) == Approx(0.75));

    REQUIRE(NativePresetAnimation::fitScalarAnimation(QStringLiteral("0=-0.75;14=0"), 15, 120, 240, false, &fitted));
    properties.set("value", fitted.toUtf8().constData());
    (void)properties.anim_get_double("value", 240, 360);
    keys = properties.get_animation("value");
    REQUIRE(keys.key_count() == 2);
    CHECK(keys.key_get_frame(0) == 240);
    CHECK(keys.key_get_frame(1) == 359);
    CHECK(properties.anim_get_double("value", 240, 360) == Approx(-0.75));
    CHECK(properties.anim_get_double("value", 359, 360) == Approx(0.0));

    REQUIRE(NativePresetAnimation::fitScalarAnimation(QStringLiteral("0=-0.75;14=0"), 15, 1, 7, false, &fitted));
    properties.set("value", fitted.toUtf8().constData());
    (void)properties.anim_get_double("value", 7, 8);
    CHECK(properties.anim_get_double("value", 7, 8) == Approx(-0.75));
    REQUIRE(NativePresetAnimation::fitScalarAnimation(QStringLiteral("0=0;14=0.75"), 15, 1, 7, true, &fitted));
    properties.set("value", fitted.toUtf8().constData());
    (void)properties.anim_get_double("value", 7, 8);
    CHECK(properties.anim_get_double("value", 7, 8) == Approx(0.75));

    CHECK_FALSE(NativePresetAnimation::fitScalarAnimation(QStringLiteral("bad"), 15, 20, 0, true, &fitted));
}
