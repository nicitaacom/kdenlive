# Slide Right 15k visual reference

These twelve PNGs are byte-for-byte copies of screenshots supplied by the user. They were sampled from a YouTube recording. They show broad appearance and sequence, not exact interpolation, shutter integration, frame timing, or the precise clip cut. The annotation inside the first frame image reads **6597**; the user identified that screenshot as **frame 6897**, so the filename and index use the user's label without modifying the image.

| File | User label and visible role |
| --- | --- |
| [outgoing-fx-settings.png](outgoing-fx-settings.png) | Image 1: outgoing Video Event FX settings |
| [incoming-fx-settings.png](incoming-fx-settings.png) | Image 2: incoming Video Event FX settings |
| [frame-6897.png](frame-6897.png) | Image 3: initial readable framing, frame 6897 |
| [frame-6903.png](frame-6903.png) | Image 4: early motion and blur, frame 6903 |
| [frame-6909.png](frame-6909.png) | Image 5: increasing horizontal displacement, frame 6909 |
| [frame-6913.png](frame-6913.png) | Image 6: reflected source content prominent, frame 6913 |
| [frame-6915.png](frame-6915.png) | Image 7: strong outgoing motion, frame 6915 |
| [frame-6918.png](frame-6918.png) | Image 8: incoming scene with reflection and blur, frame 6918 |
| [frame-6919.png](frame-6919.png) | Image 9: incoming recovery, frame 6919 |
| [frame-6924.png](frame-6924.png) | Image 10: reduced motion, frame 6924 |
| [frame-6928.png](frame-6928.png) | Image 11: near-normal framing, frame 6928 |
| [frame-6930.png](frame-6930.png) | Image 12: sharp recovered framing, frame 6930 |

The whole image, including its HUD and face-camera overlay, moves horizontally. Reflected source pixels fill exposed horizontal edges, with blur tied to movement. The images do not establish a cylindrical warp for this Slide Right preset. The earlier 4+4+12-frame cylindrical description remains a separate reference case.

The visible settings narrow the match to the `2.2`/`2.4` class: both source pairs start outgoing at Shift X `0`, Shutter Duration `1`, Brightness `1`, and incoming at Shift X `0.25`, Shutter Duration `1.5`, Brightness `1.25`, with Reflect borders. Both have identical ordered `S_BlurMoCurves` plus RSMB payloads. `2.3`, `2.5`, and `2.6` have a single `S_BlurMoCurves` component and static Brightness `1`, so they do not match the incoming Brightness field. Only the BlurMoCurves tab is visible in the screenshots, which does not establish whether RSMB was present elsewhere in the saved FX chain. No numbered identifier is visible; the references cannot distinguish `2.2` from `2.4`. Both candidates retain their own source UUID in the inventory and need separate validation.












=============



## Expected transition references

These are user-supplied examples of the expected visual result. Open the images at full size when comparing movement, blur, reflection, and recovery. Image numbers restart for the second batch.

### First reference table: Slide Right 15k

The first batch shows the effect settings and the movement inside the video preview. Frame labels follow the user's original numbering.

| Image | User label and visible role | Reference |
| --- | --- | --- |
| 1 | Outgoing Video Event FX settings | [outgoing-fx-settings.png](outgoing-fx-settings.png) |
| 2 | Incoming Video Event FX settings | [incoming-fx-settings.png](incoming-fx-settings.png) |
| 3 | Frame 6897: initial readable framing | [frame-6897.png](frame-6897.png) |
| 4 | Frame 6903: early motion and blur | [frame-6903.png](frame-6903.png) |
| 5 | Frame 6909: increasing horizontal displacement | [frame-6909.png](frame-6909.png) |
| 6 | Frame 6913: reflected source content prominent | [frame-6913.png](frame-6913.png) |
| 7 | Frame 6915: strong outgoing motion | [frame-6915.png](frame-6915.png) |
| 8 | Frame 6918: incoming scene with reflection and blur | [frame-6918.png](frame-6918.png) |
| 9 | Frame 6919: incoming recovery | [frame-6919.png](frame-6919.png) |
| 10 | Frame 6924: reduced motion | [frame-6924.png](frame-6924.png) |
| 11 | Frame 6928: near-normal framing | [frame-6928.png](frame-6928.png) |
| 12 | Frame 6930: sharp recovered framing | [frame-6930.png](frame-6930.png) |

=========================

### Second reference table: outgoing and incoming progression

**This second batch is the expected result.** The outgoing half is **Right Slide (1) 15k**. The user describes the incoming half as, for example, **Right Slide (2) 15k**. The table preserves all 21 attachments in their supplied order, with frame numbering restarting at the incoming half. Missing frame numbers represent screenshots that were not supplied; do not insert holds for those gaps.

The outgoing image becomes horizontally displaced and smeared, reaching broad, nearly gray curved bands at frame 15. The incoming half starts with similarly obscured bands, then reveals the next scene and settles toward its normal framing. From outgoing frame 10, the user identifies the composition as becoming barely recognizable.

In this batch, the recorded Vegas interface itself is part of the footage being distorted. The YouTube controls and turquoise frame labels are presentation overlays. Apply the transition to the full source image, including any graphics already baked into it; use those overlays only to identify the reference. The visible curvature describes this second example's appearance and does not establish an exact plugin or projection model.

| Part | Reference frame | Attachment | Expected appearance / user note | Expected image (click for full size) |
| --- | --- | --- | --- | --- |
| Right Slide (1) 15k | 1 | Image #1 | Opening sample; original composition still recognizable | [<img src="../slide-right-15k-round-2/outgoing-frame-001.png" alt="Second reference, Right Slide (1) 15k, frame 1, image 1" width="320">](../slide-right-15k-round-2/outgoing-frame-001.png) |
| Right Slide (1) 15k | 2 | Image #2 | Readable early framing | [<img src="../slide-right-15k-round-2/outgoing-frame-002.png" alt="Second reference, Right Slide (1) 15k, frame 2, image 2" width="320">](../slide-right-15k-round-2/outgoing-frame-002.png) |
| Right Slide (1) 15k | 4 | Image #3 | Early movement; composition remains readable | [<img src="../slide-right-15k-round-2/outgoing-frame-004.png" alt="Second reference, Right Slide (1) 15k, frame 4, image 3" width="320">](../slide-right-15k-round-2/outgoing-frame-004.png) |
| Right Slide (1) 15k | 6 | Image #4 | Pronounced horizontal motion and blur | [<img src="../slide-right-15k-round-2/outgoing-frame-006.png" alt="Second reference, Right Slide (1) 15k, frame 6, image 4" width="320">](../slide-right-15k-round-2/outgoing-frame-006.png) |
| Right Slide (1) 15k | 8 | Image #5 | Greater horizontal displacement with reflected content | [<img src="../slide-right-15k-round-2/outgoing-frame-008.png" alt="Second reference, Right Slide (1) 15k, frame 8, image 5" width="320">](../slide-right-15k-round-2/outgoing-frame-008.png) |
| Right Slide (1) 15k | 10 | Image #6 | User marks the start of barely recognizable composition | [<img src="../slide-right-15k-round-2/outgoing-frame-010.png" alt="Second reference, Right Slide (1) 15k, frame 10, image 6" width="320">](../slide-right-15k-round-2/outgoing-frame-010.png) |
| Right Slide (1) 15k | 11 | Image #7 | Heavy horizontal smearing; fine detail lost | [<img src="../slide-right-15k-round-2/outgoing-frame-011.png" alt="Second reference, Right Slide (1) 15k, frame 11, image 7" width="320">](../slide-right-15k-round-2/outgoing-frame-011.png) |
| Right Slide (1) 15k | 12 | Image #8 | Broad horizontal streaks dominate the image | [<img src="../slide-right-15k-round-2/outgoing-frame-012.png" alt="Second reference, Right Slide (1) 15k, frame 12, image 8" width="320">](../slide-right-15k-round-2/outgoing-frame-012.png) |
| Right Slide (1) 15k | 15 | Image #9 | Peak region: nearly gray curved bands, source barely identifiable | [<img src="../slide-right-15k-round-2/outgoing-frame-015.png" alt="Second reference, Right Slide (1) 15k, frame 15, image 9" width="320">](../slide-right-15k-round-2/outgoing-frame-015.png) |
| Incoming — Right Slide (2) 15k | 1 | Image #10 | Starts already strongly obscured, with curved bands matching the peak appearance | [<img src="../slide-right-15k-round-2/incoming-frame-001.png" alt="Second reference, incoming frame 1, image 10" width="320">](../slide-right-15k-round-2/incoming-frame-001.png) |
| Incoming — Right Slide (2) 15k | 2 | Image #11 | Still heavily obscured; recovery starts within the broad bands | [<img src="../slide-right-15k-round-2/incoming-frame-002.png" alt="Second reference, incoming frame 2, image 11" width="320">](../slide-right-15k-round-2/incoming-frame-002.png) |
| Incoming — Right Slide (2) 15k | 4 | Image #12 | Curved, blurred bands remain prominent during early recovery | [<img src="../slide-right-15k-round-2/incoming-frame-004.png" alt="Second reference, incoming frame 4, image 12" width="320">](../slide-right-15k-round-2/incoming-frame-004.png) |
| Incoming — Right Slide (2) 15k | 6 | Image #13 | Incoming scene emerges through blur and curvature | [<img src="../slide-right-15k-round-2/incoming-frame-006.png" alt="Second reference, incoming frame 6, image 13" width="320">](../slide-right-15k-round-2/incoming-frame-006.png) |
| Incoming — Right Slide (2) 15k | 8 | Image #14 | Scene recognizable while still displaced, curved, and blurred | [<img src="../slide-right-15k-round-2/incoming-frame-008.png" alt="Second reference, incoming frame 8, image 14" width="320">](../slide-right-15k-round-2/incoming-frame-008.png) |
| Incoming — Right Slide (2) 15k | 10 | Image #15 | Recovery continues toward the final composition | [<img src="../slide-right-15k-round-2/incoming-frame-010.png" alt="Second reference, incoming frame 10, image 15" width="320">](../slide-right-15k-round-2/incoming-frame-010.png) |
| Incoming — Right Slide (2) 15k | 11 | Image #16 | Text and scene become more readable; residual distortion remains | [<img src="../slide-right-15k-round-2/incoming-frame-011.png" alt="Second reference, incoming frame 11, image 16" width="320">](../slide-right-15k-round-2/incoming-frame-011.png) |
| Incoming — Right Slide (2) 15k | 12 | Image #17 | Clearer scene with remaining curvature and framing offset | [<img src="../slide-right-15k-round-2/incoming-frame-012.png" alt="Second reference, incoming frame 12, image 17" width="320">](../slide-right-15k-round-2/incoming-frame-012.png) |
| Incoming — Right Slide (2) 15k | 13 | Image #18 | Further settling toward normal framing | [<img src="../slide-right-15k-round-2/incoming-frame-013.png" alt="Second reference, incoming frame 13, image 18" width="320">](../slide-right-15k-round-2/incoming-frame-013.png) |
| Incoming — Right Slide (2) 15k | 14 | Image #19 | Late recovery; readable composition | [<img src="../slide-right-15k-round-2/incoming-frame-014.png" alt="Second reference, incoming frame 14, image 19" width="320">](../slide-right-15k-round-2/incoming-frame-014.png) |
| Incoming — Right Slide (2) 15k | 17 | Image #20 | Near the final framing; remaining motion settles | [<img src="../slide-right-15k-round-2/incoming-frame-017.png" alt="Second reference, incoming frame 17, image 20" width="320">](../slide-right-15k-round-2/incoming-frame-017.png) |
| Incoming — Right Slide (2) 15k | 20 | Image #21 | Final reference: sharp, stable, recovered framing | [<img src="../slide-right-15k-round-2/incoming-frame-020.png" alt="Second reference, incoming frame 20, image 21" width="320">](../slide-right-15k-round-2/incoming-frame-020.png) |

Reference numbering is separate from output timing: outgoing frame 15 and incoming frame 20 identify supplied reference endpoints. Resample the two phases into the chosen project duration; do not interpret these labels as a requirement to render 35 frames in every project. The complete transition remains at most one second, with 60 total frames at 60 fps or 30 total frames at 30 fps.

## Paired transition implementation prompt

```text
Fix the paired outgoing/incoming transitions in this Kdenlive project using the following visual and timing requirements.

Inspect both expected reference tables in plans/references/slide-right-15k/README.md and open the linked images before implementing. The second table contains 21 user-supplied screenshots showing the intended buildup, obscured midpoint, and recovery. Use that second sequence as the primary visual target for this example. Preserve each preset's intended effect family when applying the same timing principle to other transitions.

Each complete transition consists of two consecutive halves around the cut:

clean clip A → progressively stronger distortion → PEAK AT CUT → progressively weaker distortion → clean clip B

Treat the outgoing and incoming effects as one coordinated visual event. The strongest region may span adjacent frames on both sides of the cut; it must not become two separate pulses or an extended frozen hold.

1. Right Slide (1) 15k — OUTGOING HALF

Apply this to the end of clip A.

Begin with the original, readable image. The first affected frame should change only slightly. On successive frames, progressively increase the intended effect: blur, displacement, skew, zoom, rotation, or the preset’s particular combination.

By the last outgoing frame, the image must be strongly obscured or displaced, making the original composition barely recognizable.

The outgoing half must continue building toward the cut. It must not become clearer again before the cut.

Use these second-table reference stages:
- Frames 1, 2, and 4: the original composition is still readable; establish a subtle start.
- Frames 6 and 8: horizontal movement, reflection, and blur become pronounced.
- Frame 10: the user marks the point where the original composition starts becoming barely recognizable.
- Frames 11 and 12: detail dissolves into broad horizontal streaks.
- Frame 15: the image is reduced to strongly blurred, curved bands; the original scene is barely identifiable.

For this example, match the visible horizontal smear and curvature near the peak. Merely moving a readable image sideways is insufficient. Let the obscured appearance emerge from transformed source pixels.

2. INCOMING HALF

Apply this to the beginning of clip B.

The FIRST incoming frame must already have the strong distortion needed to match the outgoing peak perceptually.

Then progressively reduce the effect on successive frames until clip B reaches its original sharpness and framing.

Do not start clip B nearly clean and then build another effect peak. Its recovery begins immediately.

“Reverse of outgoing” describes the distortion-strength progression. It does not mean reversing the source video or automatically reversing the direction of travel.

For directional movement, preserve a coherent direction through the cut: clip A exits in that direction while clip B arrives from the opposite side and settles into place.

Use these second-table incoming stages, labeled by the user as an example of Right Slide (2) 15k:
- Frames 1, 2, and 4: begin inside the strongly blurred, curved-band appearance. The new scene should initially be difficult to identify.
- Frames 6 and 8: the incoming scene emerges while movement, blur, and curvature remain visible.
- Frames 10 through 14: progressively restore readability and normal framing.
- Frame 17: approach the final composition and let remaining motion settle.
- Frame 20: reach the sharp, stable final reference.

The last outgoing frame and first incoming frame must have compatible perceived distortion and motion. Their colors need not be identical because they contain different scenes. Avoid a clear-frame flash, sudden reset of the transform, or a reversal of travel at the cut.

3. DURATION AND FRAME COUNTS

The maximum duration is ONE SECOND TOTAL for the complete outgoing + incoming pair.

At 60 fps:
- 30 outgoing frames + 30 incoming frames = 60 total frames = 1 second.

At 30 fps:
- 15 outgoing frames + 15 incoming frames = 30 total frames = 1 second.

The two halves must share this duration. Do not allocate one second to each half.

These are the default equal allocations. The second reference's outgoing 1–15 and incoming 1–20 labels describe its sampled progression, not mandatory output frame counts. Preserve those labels in the documentation and resample the progression for the output. If preserving the reference's longer recovery requires an unequal allocation, keep the same total budget and state the chosen split. Never render 35 frames at 30 fps and describe it as a one-second transition.

Calculate frame counts from the actual project frame rate and selected duration. Shorter transitions must preserve the same progression, sampled across fewer frames. Assign any odd extra frame to one half without increasing the total frame count.

Use normalized progress within each phase so changing project fps or duration does not change the intended appearance or add extra animation cycles. Account for inclusive frame endpoints when placing the cut and computing the total duration. The gaps between supplied reference numbers are unsupplied samples, not instructions to hold or duplicate a frame.

4. MOTION AND BLUR

Use smooth easing with subtle changes near the clean endpoints and the strongest perceived motion/distortion around the cut.

For motion transitions, accelerate into the cut and decelerate out of it. Avoid curves that slow the outgoing motion before the cut and then accelerate the incoming motion afterward, creating two separate blur peaks.

Coordinate displacement, warp, and blur across both phases. A displacement value can be maximal while motion blur is weak if the image has already stopped moving. Ensure the rendered blur remains strong at the phase boundary, including the last outgoing and first incoming frames. Check whether endpoint clamping or shutter sampling weakens the blur there.

Judge the rendered image, not just increasing/decreasing parameter values. Increasing displacement can still produce repeated readable images when reflected borders cycle through the frame.

Avoid repeated full-screen scrolling, bouncing, or recurring recognizable compositions. Reflection should fill exposed edges where the reference calls for it.

Reflected fragments visible in the expected screenshots are allowed. Avoid repeated full-image cycles that make the original composition reappear clearly during the outgoing buildup. Use enough blur samples for a continuous smear instead of a stack of visibly separate copies or comb-like trails.

“Almost gray” or “almost black” describes how obscured the content may become. Do not insert a solid-color frame or force every preset to fade to gray or black.

The final frame must match the untreated incoming footage at the same source time, with no residual transition blur or transform. Source footage continues playing throughout.

Transform the entire source frame, including embedded HUDs, text, or face-camera overlays. In the second reference, the recorded editor interface is itself source content. Reproduce the effect on video pixels; YouTube controls, annotation labels, and the live Kdenlive interface are not part of the requested effect.

5. REFERENCES

Inspect:
plans/references/slide-right-15k/
plans/references/slide-right-15k-round-2/

Use outgoing-fx-settings.png and incoming-fx-settings.png for visible settings, and the ordered screenshots:
6897, 6903, 6909, 6913, 6915, 6918, 6919, 6924, 6928, 6930.

They illustrate readable framing, increasing movement and reflection, the scene change, and recovery to sharp framing. Treat them as visual guidance; my explicit progression and duration requirements govern the result.

For the second batch, use the exact attachment-to-frame mapping in plans/references/slide-right-15k/README.md: images 1–9 are outgoing reference frames 1, 2, 4, 6, 8, 10, 11, 12, 15; images 10–21 are incoming reference frames 1, 2, 4, 6, 8, 10, 11, 12, 13, 14, 17, 20. These files are expected examples, not candidate renders. Do not invent exact plugin settings or an exact warp model from screenshots alone.

Rejected example:
 /home/kali/.cache/kdenlive-native-transition-validation/scroll-up-43-exact-ui-timing-20260929/effects.mp4

Matched untreated baseline:
 /home/kali/.cache/kdenlive-native-transition-validation/scroll-up-43-exact-ui-timing-20260929/clean.mp4

6. VALIDATION

Render and inspect the complete transition at both 30 and 60 fps. Check every affected frame, especially the last outgoing and first incoming frames.

Use two clearly different scenes and render a matched untreated baseline with identical source times, project fps, and framing. Include clean footage before and after the affected interval, while reporting the transition duration separately from the preview file's total duration. Compare the first and final affected frames against their corresponding baseline frames.

Provide a labeled contact sheet and playable render demonstrating:
- Subtle outgoing start.
- Progressive buildup toward the cut.
- Strong distortion on BOTH sides of the cut.
- Immediate, progressive incoming recovery.
- Fully restored final framing.
- One second maximum for the complete pair.

Label output frames with their phase, frame number, time, and cut location. Show representative buildup and recovery frames plus consecutive frames immediately around the cut. Review playback at normal speed and frame by frame. Report the actual project fps, outgoing/incoming frame counts, total affected duration, and paths to the render, baseline, and contact sheet.

Do not claim success solely because keyframes, parameter values, or automated checks pass. Confirm that the rendered sequence visibly follows the requested progression.
```
