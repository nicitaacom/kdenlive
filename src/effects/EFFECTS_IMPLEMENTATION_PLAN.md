# Effects, Presets, and Responsive Preview Plan

## Product constraints

- Keep the existing Kdenlive timeline, MLT effect stack, keyframe editor, undo stack, and project serialization as the primary editing path.
- Reuse native effect definitions and effect-stack templates. Add a renderer only when no installed MLT, FFmpeg, Frei0r, LADSPA, or other suitable open component provides the required behavior.
- Keep aliases, effect status, preset metadata, and category labels in data files where possible. Avoid one special widget or code path per effect.
- A pending item must be searchable and explain its status, but must never apply a different effect as a substitute.
- User-authored effect values, keyframes, and templates must survive save, close, and reopen.

## Current baseline

- Kdenlive already has project profiles, video/audio tracks, mute/solo, grouping, splitting, frame navigation, speed effects, freeze, transform, chroma key, grayscale, reverse, titles, and native transitions. Prefer improving discoverability and presets over duplicating those systems.
- Shake is usable as a native effect group. Its current Sapphire coverage is partial; missing seed, Z/Tilt, and independent edge modes remain tracked.
- Gaussian Blur exposes horizontal and vertical sigma. Proportional lock and Apply Linear controls remain pending.
- Matching effects and the 194-entry native transition-template catalog are documented in `PRESET_EFFECT_INVENTORY.md`. Preset thumbnails currently depict motion direction; they are not rendered video previews.
- `S_BlurMoCurves`, `S_BlurMotion`, and RE:Vision `RSMB` now appear as non-applicable Pending entries for their vendor IDs and common search terms.
- The 194 catalog entries are editable per-clip effect stacks for the Sapphire event presets. Their `(1)` and `(2)` variants target the first/outgoing and second/incoming video events. Animations are now bounded to their labeled frame count and the relevant clip edge; playback/render validation in the application is still required. They are not dual-input Sapphire `S_Transition` effects, and this catalog does not yet reproduce every Sapphire component.

## Prioritized backlog

### Must-have — correctness and the requested workflow

1. **Search, status, and safe application**
   - Keep visible names, vendor IDs, abbreviations, and common terms in searchable metadata.
   - Show `Pending` in the result name and description. Exclude pending entries from drag/drop, double-click apply, and shortcut menus.
   - Acceptance: searching `S_BlurMoCurves`, `motion curve blur`, `S_BlurMotion`, `motion blur`, or `RSMB` returns the corresponding pending result; none can be applied. Searching `S_Shake`, `Shake`, `screen shake`, `camera shake`, or `TRIGGERED` returns the usable Shake effect.

2. **Effect definitions and controls**
   - Finish Shake controls where the current Frei0r filters support them: amplitude, frequency, phase, X/Y motion, rotation, scale/zoom, seed if supported, edge mode, and optional motion blur. Keep Sapphire-only unsupported channels explicit as pending.
   - Implement Motion Curve Blur only with a renderer that evaluates animated center, zoom, rotation, and X/Y shifts across a shutter interval; expose shutter duration/shift, exposure, and quality.
   - Implement motion-vector blur/RSMB separately from temporal retiming. Expose blur amount, vector quality/radius, and artifact controls supported by the selected renderer.
   - Improve Gaussian Blur with linked horizontal/vertical values, an unlock control, and a real linear-light processing option. Do not add UI-only parameters that do not affect rendering.
   - Acceptance: each effect has grouped, labeled controls in Effect Stack; animatable parameters use Kdenlive keyframes; reset returns documented defaults; values serialize and undo/redo correctly; preview and final render use the same parameters.

3. **Named equivalents and missing effects**
   - Keep equivalent mappings truthful: chroma shift, position/zoom, corner pin, wave, fisheye correction, color/HSL correction, cookie-cutter masks, and directional blur are not exact Sapphire/Vegas implementations.
   - Implement or keep explicitly pending bubble warps, magnifying warp, radial blur, 3D swish, and any vendor effect without an equivalent renderer.
   - Acceptance: no pending search term silently selects an unrelated effect. The inventory states which operations are native equivalents, partial matches, and pending.

4. **Audio EQ and basic effect workflows**
   - Make the existing multi-band audio equalizer easy to find and save as a user preset. Provide at least one editable muffled/underwater starting preset; all bands remain adjustable.
   - Reuse built-in chroma key, selective mask/blur, grayscale, reverse, text animation, transform, and speed tools. Add focused one-click presets rather than duplicate effects.
   - Acceptance: a user can find an effect by its familiar term, apply it, edit every exposed control, save a native preset, and reopen a project without losing settings.

5. **Native preset browser**
   - Extend the existing Effects Library with searchable categories, readable titles, duration and direction variants, a preview, and editable effect-stack insertion.
   - Keep first-clip and second-clip directions separate. Show whether a preset is a native interpretation or an exact implementation; Vegas `.sfpreset` files are never presented as directly compatible.
   - Acceptance: search for `Scroll Right (20k)` and `Smooth R to L` finds the appropriate entries; applying one adds its editable stack to the selected clip; users can change or remove each component in Effect Stack.

6. **Make native event-preset transitions reliable**
   - **Use the actual source model:** `Переходы.sfpreset` and `Other.sfpreset` are read-only RIFF/SFPD Vegas packages containing per-event effect presets. Their Sapphire IDs (such as `S_WarpTransform`, `S_BlurMoCurves`, and `S_Shake`) are event effects, not evidence that each entry is a Sapphire `S_Transition` two-input transition. Do not run installers or load vendor plug-ins.
   - **Keep the two event variants clear:** show `(1)` as the first/outgoing video event and `(2)` as the second/incoming video event, matching the user's workflow. Preserve readable names and source durations such as `Scroll Left (20k)` while displaying `20 frames` in Kdenlive.
   - **Bound clip-edge animation:** apply `(1)` over the final N frames of its clip and `(2)` over the first N frames. Clamp the keyframe endpoint to the clip and to N frames, then restore the original transform when the effect interval ends. Never let a short preset's last geometry persist over the rest of a clip.
   - **Map the effects honestly:** retain a native, editable stack for components with a suitable Kdenlive/MLT equivalent. Use real Sapphire effects where their renderer is available. Keep unsupported components searchable and explicitly pending; do not replace blur, shake, warp, or color effects with an unrelated control. Remove no-op components from generated stacks.
   - **Complete the simple workflow:** make presets searchable in the Effects Library, show direction, duration, and implementation status, and apply the editable effect stack to the selected clip. Keep first/outgoing and second/incoming variants distinct. Add a real video preview when sample clips can be rendered; schematic thumbnails are only a fallback.
   - **Reproduce and verify:** use two visibly different 40-frame clips with corner markers and frame numbers. For 20-frame entries, verify exactly the intended 20-frame clip-edge animation and normal framing outside it. Inspect frames 1, 2, 8, 9, 10, 11, 22, 23, 24, 25, and 40; compare Project Monitor playback, save/reopen, undo/redo, and final export. Confirm that there are no unexplained black frames, thin-strip collapse, flash, or jump. Track each preset as implemented, equivalent, or pending only after render validation.
7. **RAM preview cache**
   - Add a configurable shortcut, default `Ctrl+B` unless it conflicts with the active keymap. It caches the selected timeline range; an explicit menu/button action starts the same operation.
   - Render the final preview frames asynchronously through the same project profile, effect chain, compositing, and color pipeline used for playback. Key cache entries by project/clip identity, source frame, project profile, effect parameters/keyframes, and relevant track/composition state.
   - Enforce a user memory budget below detected available RAM, retaining a configurable OS reserve. Store fixed-format frames with bounded metadata overhead; stop before exceeding budget and report the cached range.
   - Invalidate only affected frame ranges after edits when dependencies can be identified; clear all affected entries on profile, source, effect, keyframe, track-composition, or color-pipeline changes. Provide Clear Cache on demand.
   - Acceptance: after the selected range finishes caching, playback reads cached frames at project FPS with no render-induced dropped frames while the cache remains valid and within budget. Cache work is cancellable, does not block editing, survives neither invalidating edits nor project close, and reports when the full range cannot fit.

### Should-have — simpler editing and resilient playback

1. **Preview quality**
   - Add Auto / Quarter / Half / Full to the monitor toolbar and Preferences. Auto may lower render resolution during interactive scrubbing and restore the chosen quality for playback/cache.
   - Keep cached full-quality output distinct from reduced-resolution interactive preview; never silently use a lower quality for final export.
   - Acceptance: changing preview quality takes effect without changing export quality, project profile, or saved effect values.

2. **Selective blur and flying picture presets**
   - Offer mask-based blur with editable shape, position, feather, strength, and keyframes. Build flying-picture/background-blur presets from native transform, blur, and mask components.
   - Acceptance: each component remains visible and editable; keyframed masks and transforms persist through save/reopen and final render.

3. **Speed and transition presets**
   - Polish edge-drag speed changes and precise playback-rate entry while keeping the existing timewarp/retiming path. Add native transition/effect presets with adjustable duration.
   - Keep optical-flow slow motion distinct from motion blur; do not describe frame blending as optical flow.
   - Acceptance: speed changes have a visible timeline result, undo correctly, and render consistently. Transition lengths are frame-accurate and editable.

4. **Text looks and audio presets**
   - Add searchable flying, swinging/rocking, and styled text presets. Add editable EQ examples such as underwater, telephone, and bass emphasis.
   - Acceptance: templates use native keyframes/effects; every generated stack can be opened and edited in Effect Stack.

5. **Preset-pack import**
   - Define a versioned archive manifest for native effect stacks, transitions, thumbnails, and optional user assets. Validate IDs, versions, paths, and media sizes before import; never execute package installers or scripts.
   - Acceptance: import either completes with editable native assets or reports each unsupported/missing item; it does not modify unrelated projects or overwrite user presets without an explicit choice.

### Nice-to-have — quality and efficiency

- Generate real sample-frame or short-loop previews for presets when the source/placeholder media is available; retain schematic thumbnails as a fast fallback.
- Add GPU implementations for supported filters and benchmarked CPU fallbacks. Surface unsupported GPU filters without changing the result silently.
- Add cache memory telemetry, cache hit indicators, per-range recache, background prefetch, and reusable cache blocks for unchanged timeline dependencies.
- Add an effect/preset favorites row and keyboard navigation without expanding the default UI into nested expert menus.

## RAM cache design notes

- **Layering:** Timeline requests a frame from a preview-cache interface. The cache serves a matching frame or submits a render job to the existing MLT render pipeline. The UI only sees progress, cancellation, memory use, and cache status.
- **Memory:** Set a configurable maximum and preserve an OS reserve. Estimate decoded frame bytes from project dimensions and pixel format before starting; account for row alignment and metadata. Evict least-recently-used entries only outside the actively cached range. Never exceed the configured cap to complete a request.
- **Invalidation:** Track dependencies at frame/range granularity for source edits, trims, transforms, effects, keyframes, transitions, compositing, profile, and color settings. If dependency tracking cannot prove a region unaffected, invalidate the smallest safe enclosing range.
- **Concurrency:** Render cache jobs off the GUI thread with bounded workers. Cancellation and edits must not wait on blocked render tasks. Tag every job with a timeline revision so stale frames cannot be published after an edit.
- **GPU/CPU:** Reuse MLT/FFmpeg hardware processing where the current chain supports it. Fall back to CPU for unsupported filters; cache output is renderer-independent after completion. Report render failure rather than marking incomplete frames cached.
- **Storage scope:** Keep this cache in RAM and disposable. It is not project media and does not change final export. Persistent disk cache can be considered later with explicit versioning and disk limits.

## Simple UI components

- **Effects Library:** one search field, category/favorite filters, preset cards with thumbnail and duration/direction, drag-to-clip, and a small details/implementation-status pane.
- **Effect Stack:** native effect rows and grouped parameters, numeric entry plus sliders, reset/default, keyframe controls, and visible pending/equivalent labels.
- **Monitor toolbar:** Preview Quality selector, Cache Selected Range button/progress/cancel, and Clear Cache action.
- **Preferences:** one Preview section with Dynamic RAM Preview limit, OS reserve, shortcut, Auto/Quarter/Half/Full default, and cache clear.
- **Timeline:** retain current track controls and tools; add cache-range highlighting and clear status icons without adding a new mandatory panel.

## Architecture boundaries

- Keep the UI in existing Qt/QML asset and monitor components. Put cache scheduling and memory accounting behind a small C++ preview-cache service; keep rendering on existing MLT/FFmpeg paths.
- Keep effect identity, names, aliases, category, status, and defaults in effect XML/catalog data. Share generic alias matching and template loading instead of duplicating effect-specific search code.
- Keep each renderer responsible for rendering only. Reuse effect parameters and keyframe serialization through the current asset model so undo, project persistence, preview, and export share one source of truth.
- Build composite looks and transitions from editable effect-stack templates. Add custom rendering modules only for capabilities absent from existing open renderers, with versioned parameters and explicit CPU/GPU behavior.
