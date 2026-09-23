# Vegas preset package inventory

Read-only inspection of `kdenlive-plugins/Переходы/Other.sfpreset` and
`kdenlive-plugins/Переходы/Переходы.sfpreset` found the serialized preset
names, parameters, and vendor effect identifiers. Both source files remain
untouched. `Other.sfpreset` contains nine distinct vendor IDs; the transition
package contains 17. The transition package has 194 named variants, including
separate `(1)` and `(2)` entries for opposing clip directions. Preset records
are data only: they do not include the vendor rendering implementations.
“Equivalent” means a native Kdenlive effect can do the named operation; it
does not imply that it reproduces a vendor effect's exact algorithm.

## Requested effects

| Package identifier or effect | Status | Native Kdenlive effect / notes |
| --- | --- | --- |
| `S_Shake` | Kdenlive Shake available; Sapphire behavior partial | Native effect group combining Frei0r Shake0scillate and Camera Shake Ultimate. Search `S_Shake`, `Shake`, `camera shake`, `jitter`, `handheld shake`, or `TRIGGERED`. Exposes X/Y movement and speed, phase, rotation and speed, scale, mirrored edges, camera X/Y amplitude, frequency, zoom, opacity, motion-blur amount, and edge color in editable component effects. Seed, Z/Tilt shake, independent reflect/black/crop modes, and Sapphire's full Style/channel controls remain pending. |
| `S_BlurMoCurves` | Pending, searchable | Appears as “Motion Curve Blur (Pending)” for `S_BlurMoCurves`, `motion curve blur`, `motion curves blur`, `blur motion curves`, and `animated motion blur`. No MLT filter found that samples animated position, zoom, rotation, and shifts over a shutter interval. |
| `S_BlurMotion` | Pending, searchable | Appears as “Motion Vector Blur (Pending)” for `S_BlurMotion`, `motion blur`, `blur motion`, `motion vector blur`, and `vector blur`. Directional blur does not estimate per-pixel motion vectors. |
| `S_WarpBubble` | Pending | No equivalent bubble warp found. |
| `S_WarpBubble2` | Pending | No equivalent bubble warp found. |
| `S_WarpFishEye` | Partial equivalent | `frei0r.defish0r` provides selectable fisheye lens mappings and is searchable as `S_WarpFishEye`, `fisheye warp`, or `fisheye distortion`. It corrects lens distortion rather than reproducing Sapphire's arbitrary warp. |
| `S_WarpChroma` | Equivalent operation | `avfilter.chromashift`; search `S_WarpChroma`, `chroma warp`. Exact Sapphire warp behavior is not claimed. |
| `S_DistortChroma` | Equivalent operation | `avfilter.chromashift`; search `S_DistortChroma`, `chroma distortion`. Exact Sapphire distortion is not claimed. |
| `S_WarpTransform` | Equivalent operation | `Position and Zoom`; search `S_WarpTransform`, `warp transform`. |
| `S_WarpMagnify` | Pending | No equivalent magnifying warp found. |
| `S_WarpCornerPin` | Equivalent operation | Frei0r `Corners`; search `S_WarpCornerPin`, `corner pin`. It provides animated four-corner perspective transform. |
| `S_WarpWaves` | Equivalent operation | Kdenlive `Wave`; search `S_WarpWaves`, `wave warp`. Exact Sapphire controls are not claimed. |
| `S_Swish3D` | Pending | No equivalent 3D swish transition renderer found. |
| RE:Vision `RSMB` | Pending, searchable | Appears as “RE:Vision RSMB Motion Blur (Pending)” for `RSMB`, `RE:Vision RSMB`, `motion blur`, `optical flow blur`, and `motion-vector blur`. It is separate from Twixtor retiming. |
| Vegas color corrector | Equivalent operation | `avfilter.colorcorrect`; search `Vegas color corrector`, `color correction`. |
| Vegas secondary color corrector | Equivalent operation | Kdenlive secondary color correction template is an editable native effect stack; search `Vegas secondary color corrector`. |
| Vegas HSL adjustment | Equivalent operation | `avfilter.huesaturation`; search `Vegas HSL adjustment`, `HSL adjustment`. |
| Vegas cookie cutter | Partial equivalent | Frei0r `Alpha Shapes`; search `Vegas cookie cutter`, `cookie cutter mask`. Supports rectangle, ellipse, triangle, diamond masks and animated geometry; it does not reproduce all Vegas controls. |
| Vegas Gaussian blur | Equivalent | `avfilter.gblur` (Gaussian Blur); search `blur`, `Gaussian Blur`, `Vegas Gaussian Blur`. Horizontal and vertical sigma. The screenshot's proportional lock and Apply Linear controls are not part of this renderer. |
| Vegas radial blur | Pending | No matching radial blur renderer identified. |
| Vegas linear blur (both identifiers) | Equivalent operation | `avfilter.dblur` (Directional Blur), with angle and radius. Search `linear blur`, `Vegas linear blur`, `directional motion blur`. |
| Vegas brightness/contrast | Equivalent | `avfilter.eq` (Video Equalizer) includes brightness and contrast; search `Vegas brightness contrast`, `brightness and contrast`. |

## Audio equalizer

Kdenlive's existing 15 Band Equalizer is searchable as `Audio Equalizer`,
`custom equalizer`, `15 band EQ`, and `audio EQ`. It exposes 15 frequency-band
gain controls in the Effect Stack for custom tonal shaping such as a muffled,
underwater sound. It uses the existing LADSPA equalizer renderer; it is separate
from the pending motion-blur and video effects above.

The package's Shake preset also stores Style, Stillness, Twitch Frequency,
Drift, Center Bias, Z Distance, Seed, X/Y wrap, and separate X/Y/Z/Tilt shake
controls. The native Shake group adds phase and reflected edges by combining
two existing Frei0r filters, but those Sapphire-specific controls still need a
dedicated renderer. The requested proportional-lock Blur control also needs UI
and parameter-linking support beyond `avfilter.gblur`'s independent sigmas.

## Vendor IDs found in the files

`Other.sfpreset`: Sapphire `S_BlurMoCurves`, `S_Shake`, `S_WarpBubble`,
`S_WarpBubble2`; Vegas color corrector, secondary color corrector, cookie
cutter, Gaussian blur, and HSL adjustment.

`Переходы.sfpreset`: Sapphire `S_BlurMoCurves`, `S_BlurMotion`,
`S_DistortChroma`, `S_Shake`, `S_WarpBubble2`, `S_WarpChroma`,
`S_WarpCornerPin`, `S_WarpFishEye`, `S_WarpMagnify`, `S_WarpTransform`,
`S_WarpWaves`, `S_Swish3D`; RE:Vision `RSMB`; Vegas `brightnessandcontrast`,
`linearblur` (Sony and Vegas IDs), and `radialblur`.

## Preset browser work

The package includes names such as “Smooth R to L” and directional scroll,
slide, wipe, corner, zoom, spin, and warp entries. The `.sfpreset` files are
Vegas event-effect presets, not Kdenlive transition definitions or Sapphire
`S_Transition` records. As requested, `(1)` is the first/outgoing video event
and `(2)` is the second/incoming video event.
`data/effects/templates/native_transition_presets.xml` registers 194 editable
clip-effect templates in searchable Movement, Zoom, Spin, Blur, and Distortion
categories. The first and second event variants remain separate and retain the
source entry as a searchable alias. Applying a template inserts its editable
effect stack on a clip. The current icon-view thumbnails show motion direction;
they are not rendered video previews. Animations are bounded to the labeled
frame count at the outgoing or incoming clip edge so they cannot keep an
off-screen transform over the rest of the clip. The stacks are native
interpretations of names and durations, not converted vendor records or exact
reproductions. Any Sapphire component without a suitable renderer remains
pending; the available transform is not a substitute for bubble warp, wave, or
corner pin rendering.

## First-pass search names

| Search term | Result |
| --- | --- |
| `S_Shake`, `Shake`, `camera shake`, `jitter`, `handheld shake`, `TRIGGERED` | Shake (editable Shake0scillate + Camera Shake effect group) |
| `blur`, `Gaussian Blur`, `Vegas Gaussian Blur` | Gaussian Blur |
| `Audio Equalizer`, `custom equalizer`, `15 band EQ`, `audio EQ` | 15 Band Equalizer |
| `Scroll Right (20k)`, `Scroll Left (20 frames)`, `Smooth R to L` | Native directional templates; first and second clip choices remain separate |
| `linear blur`, `Vegas linear blur` | Directional Blur |
| `S_WarpChroma`, `S_DistortChroma`, `chroma warp`, `chroma distortion` | Chroma Shift |
| `S_WarpTransform`, `warp transform` | Position and Zoom |
| `S_WarpCornerPin`, `corner pin` | Corners |
| `S_WarpWaves`, `wave warp` | Wave |
| `S_WarpFishEye`, `fisheye warp`, `fisheye distortion` | Defish (partial fisheye equivalent) |
| `Vegas color corrector`, `Vegas secondary color corrector`, `Vegas HSL adjustment`, `Vegas cookie cutter` | Color Correct, Secondary Color Correction, Hue Saturation Intensity, Alpha Shapes |
| `Vegas brightness contrast`, `brightness and contrast` | Video Equalizer |
| `S_BlurMoCurves`, `motion curve blur`, `S_BlurMotion`, `motion blur`, `RSMB`, `optical flow blur` | Searchable pending entries that cannot be applied |
| `S_WarpBubble`, `S_WarpBubble2`, `S_WarpMagnify`, `S_Swish3D`, `radial blur` | Pending; no false alias to unrelated effects |
