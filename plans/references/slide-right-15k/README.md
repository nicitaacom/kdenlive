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
