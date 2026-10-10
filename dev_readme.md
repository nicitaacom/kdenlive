# Local development map

This checkout uses Qt 6, KDE Frameworks 6, MLT, and KDDockWidgets. It has a
custom compact workspace where the Clip Monitor can also preview the timeline.
Do not assume that the visible Clip Monitor always displays a bin clip.

## Build and run on this machine

The configured Ninja build is `/home/kali/.cache/kdenlive-compact-build`.
Its install prefix is `/home/kali/.local/kdenlive-compact`.
`/home/kali/.local/bin/kdenlive` launches that installed copy with its data path.
Changes to the build executable do not update the installed copy automatically.

```sh
cmake --build /home/kali/.cache/kdenlive-compact-build --target kdenlive modeltest effectstest --parallel 2
```

QML linting runs as part of the `kdenlive` target. Effects and other assets need
the installed data path; source the build's `prefix.sh` when running build binaries.

```sh
. /home/kali/.cache/kdenlive-compact-build/prefix.sh
export MLT_REPOSITORY=/home/kali/.local/kdenlive-compact/lib/mlt-7
QT_QPA_PLATFORM=offscreen /home/kali/.cache/kdenlive-compact-build/bin/modeltest '[TrackModel][Audio]'
QT_QPA_PLATFORM=offscreen /home/kali/.cache/kdenlive-compact-build/bin/effectstest '[Effects]'
```

After validation, update the local installation with:

```sh
cmake --install /home/kali/.cache/kdenlive-compact-build
```

A running application keeps its loaded code; restart it to use an updated build.
When launching a build binary, set `QML_IMPORT_PATH` to the build's `bin` directory
and use an isolated `XDG_CACHE_HOME` to avoid mixing cached QML from older builds.
Use a separate configuration and Xvfb for GUI checks without altering the user's
open project or dock layout. See `dev-docs/build.md` for a portable setup.
Xvfb isolates the display, **not audio**. Create a dedicated PulseAudio null sink
with `pactl load-module module-null-sink sink_name=kdenlive_codex_test`, then launch
test applications with `PULSE_SINK=kdenlive_codex_test SDL_AUDIODRIVER=dummy`.
Never change the user's default sink, master volume, or running application's
streams. Rendering to files and decoding PCM do not require speaker playback.

## Timeline track headers and audio gain

- `src/timeline2/view/qml/TrackHead.qml`: header buttons, mute, and volume dial.
- `src/timeline2/view/qml/Timeline.qml`: header delegates and minimum width.
- `src/timeline2/model/timelineitemmodel.*`: QML roles and undoable gain gestures.
- `src/timeline2/model/trackmodel.*`: track tractor and built-in volume filter.
- `src/audiomixer/mixerwidget.*`: mixer sliders and recording controls.
- `src/audiomixer/mixermanager.cpp`: mixer registration and model synchronization.

The mixer volume filter uses `mlt_service=volume` and `internal_added=237`.
It is separate from user-added Volume effects. The dial and mixer must share this
filter, preserve unity gain at 0 dB, and save it with the track's MLT service.
Recording input gain is a separate control. Regression coverage is in
`tests/modeltest.cpp` under `[TrackModel][Audio]`.

## Monitor previews

- `src/monitor/monitormanager.cpp`: compact timeline binding and refresh after effects.
- `src/monitor/monitor.cpp`: source clip selection, producer binding, empty-preview state.
- `src/monitor/videowidget.cpp`: MLT consumer and Quick widget clear color.
- `src/monitor/view/ClipMonitor.qml`: monitor overlays and compact presentation.
- `src/monitor/view/AudioView.qml`, `AudioZoomBar.qml`: waveform backgrounds.
- `src/monitor/view/EmptyPreview.qml`: empty-preview message.

Changing the widget clear color alone does not override an opaque QML waveform
background or its full-clip selection tint. Check both source audio clips and
audio-only timeline previews, then switch back to video to ensure the black
fallback does not obscure real frames.

## Inserting and displaying effects

- `src/timeline2/view/timelinewidget.cpp`: right-click favorites menu and target clip.
- `src/timeline2/view/timelinecontroller.cpp`: `addEffectToClip()` and `showAsset()`.
- `src/timeline2/model/timelinemodel.cpp`: `addClipEffect()` and undo/redo.
- `src/effects/effectstack/model/effectstackmodel.cpp`: effect creation and active row.
- `src/assets/assetpanel.cpp`: parameter UI for the selected effect stack.
- `src/mainwindow.cpp`: dock visibility and `raiseEffectStack()`.
- `data/effects/volume.xml`: Volume's animated `level` parameter in dB.

Selecting a clip follows the automatic-raise preferences. Explicitly inserting an
effect opens its controls even when the Effect/Composition Stack dock was closed.
KDDockWidgets needs `open()` as well as `setAsCurrentTab()` to reveal a closed dock.

## Audio Visualizer

Select an audio clip on the timeline and use **Tool → Audio Visualizer…**. The
dialog analyzes that selected cut and creates an exportable color producer on a
new video track. Select its timeline layer and use the same tool to edit it.
The Project Bin search also shows an **Audio Visualizer** tool result for
`visu`, `visualizer`, `visualiser`, `spectrum`, and matching multiword queries.
Click that result or press Enter to open the same editor. Clearing the search
hides the tool result and restores the normal media list. This discovery row is
in `src/bin/bin.cpp`, between the tags panel and the clip view; keep that layout
order when rebuilding tree/icon views.
Creating the bin asset, track and clip is one undo command; editing settings is
another. A generated asset stores the native effect in its bin effect stack, so
editing it also updates other timeline instances of that same asset. The dialog
also recognizes a visualizer effect attached to an individual timeline clip.

- `src/audiovisualizer/visualizerdialog.*`: editor, analysis worker, MLT preview,
  timeline insertion, media controls, speech recognition and subtitle import.
- `src/audiovisualizer/spectrum.*`: shared FFT analysis and QPainter drawing.
- `src/audiovisualizer/captionclient.*`: provider protocols, timestamp parsing,
  model discovery and text refinement, with keys held only in memory.
- `src/nativeeffects/filter_audiovisualizer.cpp`: native MLT renderer used both
  by the dialog preview and by monitor/export consumers.
- `data/effects/audio_visualizer.xml`: URL parameters for spectrum, background,
  portrait and extracted audio; a fixed JSON parameter stores style settings.
- `src/mainwindow.cpp` / `src/kdenliveui.rc`: the tool action and menu entry.

Analysis decodes the selected source range to 32 kHz mono PCM and extracts 64
logarithmic frequency bands using a 4096-sample Hann window. The `.kdviz` data and
extracted `.wav` live under the project's media output folder in
`audio-visualizers/`; keep them with the project. Spectra are a snapshot of the
analyzed cut, including its clip effects. Later edits to the source audio require
creating a new visualization. Rendering uses deterministic smoothing over past
frames, so backward seeks and trims retain their original source timing. MLT's
filter position excludes its in-point: add `mlt_filter_get_in()` when reading it.

Background images fill the frame. Shorter video backgrounds loop silently;
`audio_index=-1` and `set.test_audio=1` prevent background audio from being mixed.
The optional center image is cropped to a circle. Black is the default.

**MLT ownership:** `Mlt::Profile(mlt_profile)` owns its argument. Clone a borrowed
profile with `mlt_profile_clone()` and keep it alive longer than its producer.
`Mlt::Service::profile()` allocates a clone; wrap it in `unique_ptr`. XML cloning
a cut restores the full parent: restore the timeline cut's explicit in/out
before analysis. The effect import property is `kdenlive_id`, with an underscore.
MLT only resolves relative filenames on recognized properties. Keep spectrum data
in `filename`, background in `resource`, portrait in `filter.resource`, and
extracted audio in `av.file`; custom path property names break saved exports.

OpenAI and Grok speech APIs produce the initial timed captions. Claude, DeepSeek
and Nous default to existing local Whisper, then refine text through the selected
provider and model. A separate speech provider/key can also be chosen. Reasoning
effort depends on model support; provider default omits that option. Models are
loaded from each provider, and model fields remain editable. API keys are never
serialized to projects or application settings. Caption refinement preserves all
original cue times and refuses malformed responses. Import creates normal
editable Kdenlive subtitles at the audio clip's timeline position.

Configure/install Whisper through Kdenlive's speech settings before using the
local engine. `data/scripts/whisper/whispertosrt.py` takes source, model and
`key=value` options, and writes SRT beside the extracted WAV.

```sh
cmake --build /home/kali/.cache/kdenlive-compact-build --target kdenlive test_audio_visualizer --parallel 2
QT_QPA_PLATFORM=offscreen MLT_REPOSITORY=/home/kali/.local/kdenlive-compact/lib/mlt-7 /home/kali/.cache/kdenlive-compact-build/bin/test_audio_visualizer
```

`test_audio_visualizer` verifies actual FFT frequencies/silence, binary data
validation, native rendering, reverse seeks, trims, background changes, subtitle
times and asynchronous HTTP requests against local mock servers for all five
providers. It also checks OpenAI/Grok multipart transcription and diarization.
No credentials, provider calls or audio playback are needed for these tests.
Live-provider behavior still requires the user's key and a supported model.
