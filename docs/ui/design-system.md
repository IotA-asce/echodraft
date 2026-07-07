# Design System

See also: [frontend-architecture.md](frontend-architecture.md) (how these tokens and
components get implemented in the Next.js app — routing, state, virtualization,
canvas waveform rendering), [product-vision-v2.md](../product/product-vision-v2.md)
(why the product is being rebuilt), and the current implementation being replaced:
`apps/web/app/globals.css`, `apps/web/app/components/common/`.

This document is the complete monochrome design system for Echodraft's frontend. It
is written to be implemented without a design review: every color, size, weight,
duration, and easing curve below is a final value, not a placeholder. Where a value
is derived from a formula (contrast ratios, spacing scale), the formula and the
result are both given so it can be checked.

## 1. Purpose & design philosophy

Echodraft turns a manuscript into an audiobook. The manuscript — its structure, its
cast, its performance — is the content. The UI's job is to get out of the way of a
multi-hour creative-review session, not to compete with the book for attention.
Today's interface (cream/green/terracotta "craft paper" theme, serif headings, offset
box-shadows, dense multi-panel screens) reads as a prototype and, per real usage,
becomes unresponsive under its own weight during long pipeline jobs. The rebuild
target is a **calm, minimal, essentially two-color interface**: black, white, and the
gray steps between them, with thin, quiet typography and animation used only to
explain what just changed.

Three principles drive every decision in this document:

1. **The book is the color.** Manuscript text, character names, and audio are the
   only things allowed to feel rich. Chrome stays neutral so it never competes.
2. **Restraint is a feature, not a limitation.** A missing color is not a missing
   affordance — hierarchy comes from weight, size, spacing, and one accent hue used
   exactly once, for exactly one purpose (see §2).
3. **Calm interfaces survive long sessions.** Extraction and review sessions run for
   hours. Motion, density, and contrast choices are made for someone who will be
   looking at this screen for the fourth hour in a row, not for a first-impression
   screenshot.

### Explicit rejection list

The following patterns exist in the current UI (`apps/web/app/globals.css`,
`apps/web/app/project-dashboard.tsx`) and are **banned** from the rebuilt frontend.
Any PR reintroducing one of these should be treated as a design-system violation,
not a style nit:

- Offset "brutalist" box-shadows (`box-shadow: 10px 10px 0 rgba(...)`) — replaced by
  the neutral, non-offset elevation shadows in §4.
- Terracotta/moss/clay accent colors (`--clay:#c85a35`, `--moss:#304b3d`) used for
  navigation state, borders, and left-accent bars — replaced by the monochrome
  status language in §6 (Badge) and the single reserved red in §2.
- Mixing a serif display face (Iowan/Palatino) with a sans body face (Avenir Next) —
  replaced by one variable sans family across every role (§3).
- `<pre>` JSON dumps rendered inline in primary UI (segment evidence, source
  extraction results, structure warnings) — replaced by the Inspector disclosure
  pattern (§6 Modal/Drawer, §8 progressive disclosure).
- Walls of 12 stat tiles in a single strip (`.structure-quality`) — capped at 4
  visible metrics (§8).
- Raw browser control chrome: native `<select>`, `<input type="range">`,
  `<details>/<summary>` — replaced by the custom Select, Slider, and
  Modal/Disclosure components in §6.
- Text-only toolbar buttons ("Why?", "Lock", "Split", "Merge next") with no icon and
  no hover affordance beyond a background swap — replaced by icon+label /
  icon+tooltip patterns in §7.
- Uppercase-tracked labels used everywhere (labels, badges, section eyebrows, table
  headers all at once) — restricted to a single hierarchy level (§3, Overline role).
- Colored left-inset borders as a general-purpose accent (`box-shadow: inset 4px 0
  var(--moss)`) — the only surviving colored left-accent is the neutral
  "selected row" indicator in §6 (Table/List row), which is monochrome, not a status
  color.

## 2. Color tokens

### Anchors and the gray ramp

Two pure anchors, `--white` and `--black`, and a 12-step neutral gray ramp between
them. Every step is a true neutral (R=G=B — zero hue, zero saturation), so the palette
is monochrome at the pixel level, not just "mostly gray." Steps are numbered 1
(lightest) to 12 (darkest). Hex values were chosen so specific steps land on exact,
checkable WCAG contrast ratios against white (shown below) — this is what makes the
semantic mapping in the next section auditable rather than eyeballed.

| Token | Hex | RGB | Contrast vs `--white` | Contrast vs `--black` |
|---|---|---|---|---|
| `--white` | `#FFFFFF` | 255,255,255 | 1.00 : 1 | 21.00 : 1 |
| `--gray-1` | `#F9F9F9` | 249,249,249 | 1.05 : 1 | 20.00 : 1 |
| `--gray-2` | `#F4F4F4` | 244,244,244 | 1.10 : 1 | 19.08 : 1 |
| `--gray-3` | `#EAEAEA` | 234,234,234 | 1.20 : 1 | 17.46 : 1 |
| `--gray-4` | `#DEDEDE` | 222,222,222 | 1.35 : 1 | 15.61 : 1 |
| `--gray-5` | `#D3D3D3` | 211,211,211 | 1.50 : 1 | 14.03 : 1 |
| `--gray-6` | `#B7B7B7` | 183,183,183 | 2.01 : 1 | 10.47 : 1 |
| `--gray-7` | `#949494` | 148,148,148 | 3.03 : 1 | 6.93 : 1 |
| `--gray-8` | `#757575` | 117,117,117 | 4.61 : 1 | 4.56 : 1 |
| `--gray-9` | `#595959` | 89,89,89 | 7.01 : 1 | 2.996 : 1 |
| `--gray-10` | `#424242` | 66,66,66 | 10.05 : 1 | 2.09 : 1 |
| `--gray-11` | `#2C2C2C` | 44,44,44 | 13.97 : 1 | 1.50 : 1 |
| `--gray-12` | `#171717` | 23,23,23 | 17.93 : 1 | 1.17 : 1 |
| `--black` | `#000000` | 0,0,0 | 21.00 : 1 | 1.00 : 1 |

Ratios are computed from WCAG relative luminance
(`L = 0.2126R + 0.7152G + 0.0722B` on linearized channels;
`CR = (Lmax + 0.05) / (Lmin + 0.05)`); with R=G=B this reduces to the single
linearized channel value. §9 turns this table into pass/fail guidance per token role.

### Semantic tokens — light theme (default)

| Semantic token | Ramp value | Usage |
|---|---|---|
| `--color-bg` | `--white` | App canvas |
| `--color-surface` | `--white` | Default card/panel fill (sits on bg, separated by `--color-border`, not by a fill difference) |
| `--color-surface-sunken` | `--gray-1` | Recessed wells: input backgrounds, code/JSON blocks, disabled fills |
| `--color-surface-raised` | `--white` | Elevated surfaces (modal, popover, menu, toast) — same fill as surface; lift comes from `--shadow-*` (§4), not color |
| `--color-border` | `--gray-4` | Decorative hairline: card edges, row dividers, section rules |
| `--color-border-strong` | `--gray-7` | Meaningful boundaries: input borders, dividers that carry state, focus-adjacent outlines. Chosen to clear the WCAG 1.4.11 non-text 3:1 minimum (3.03:1 vs white) |
| `--color-text-primary` | `--gray-12` | Headings, primary body, primary button label |
| `--color-text-secondary` | `--gray-9` | Secondary body, metadata, captions that must stay comfortably legible (7.01:1, clears AAA) |
| `--color-text-tertiary` | `--gray-8` | Least-emphasis readable text, hint text (4.61:1, AA floor — see §3 for size/weight limits) |
| `--color-text-disabled` | `--gray-6` | Disabled control labels only (2.01:1, intentionally sub-AA — disabled content is not something a user must read to proceed) |
| `--color-bg-inverse` | `--gray-12` | Solid-fill surfaces: primary button, tooltip, dark toast |
| `--color-text-inverse-primary` | `--white` | Label/text on `--color-bg-inverse` (17.93:1) |
| `--color-text-inverse-secondary` | `--gray-6` | De-emphasized text on `--color-bg-inverse` (8.94:1 vs `--gray-12`) |
| `--color-border-inverse` | `--gray-10` | Subtle border inside an inverse-filled element (1.78:1 vs `--gray-12`) |

`--color-bg-inverse` is `--gray-12`, not raw `--black`. This mirrors the choice of
`--color-text-primary` also being `--gray-12` rather than raw black: a single "soft
ink" value is used everywhere the design wants "reads as black," and pure `--black`
is reserved for rare full-bleed cases (export/print preview backgrounds, a pupil-dot
in an icon) where zero softness is wanted. This avoids the harsh edge/halation effect
of large pure-black fields next to anti-aliased text.

### Semantic tokens — dark theme (`[data-theme="dark"]`)

Dark mode reuses the *exact same* 12-step ramp and two anchors — no new hex values
are introduced. Roles are re-pointed, and because contrast ratio is symmetric
(`CR(a,b) == CR(b,a)`), several pairs reuse the light-theme numbers exactly; others
are computed fresh against the dark canvas (`--gray-12`) since the ramp was built
relative to white, not black.

| Semantic token | Ramp value | Contrast vs canvas | Usage |
|---|---|---|---|
| `--color-bg` | `--gray-12` | — | App canvas |
| `--color-surface` | `--gray-12` | — | Default card/panel fill |
| `--color-surface-sunken` | `--black` | 1.17 : 1 | Recessed wells read as *deeper* than the canvas |
| `--color-surface-raised` | `--gray-11` | 1.28 : 1 | Elevation is a **lightness step**, not a shadow (see §4 — shadows barely register on dark backgrounds) |
| `--color-border` | `--gray-11` | 1.28 : 1 | Decorative hairline |
| `--color-border-strong` | `--gray-8` | 3.89 : 1 | Meaningful boundaries (clears 3:1) |
| `--color-text-primary` | `--white` | 17.93 : 1 | Headings, primary body |
| `--color-text-secondary` | `--gray-6` | 8.94 : 1 | Secondary body/metadata |
| `--color-text-tertiary` | `--gray-7` | 5.91 : 1 | Least-emphasis readable text (still clears AA with margin) |
| `--color-text-disabled` | `--gray-9` | 2.56 : 1 | Disabled labels only, intentionally sub-AA |
| `--color-bg-inverse` | `--white` | 17.93 : 1 | Solid-fill surfaces on a dark canvas (primary button becomes solid white) |
| `--color-text-inverse-primary` | `--gray-12` | 17.93 : 1 | Label on `--color-bg-inverse` |
| `--color-text-inverse-secondary` | `--gray-8` | 4.61 : 1 | De-emphasized text on `--color-bg-inverse` |
| `--color-border-inverse` | `--gray-4` | 1.35 : 1 | Subtle border inside an inverse-filled element |

### The one accent hue

The system contains exactly one non-gray hue: a single dark red, reserved
**exclusively** for destructive confirmation and fatal, pipeline-halting errors. It
does not appear in badges for ordinary warnings, in the waveform, in charts, or as a
general "attention" color. Two functional colors (a danger red *and* a success
green) would quietly become three, then four — the discipline only holds if there is
exactly one exception, reserved for the one class of event that must interrupt:
**irreversible action and hard failure.**

| Token | Hex | Where it applies | Contrast |
|---|---|---|---|
| `--color-danger` (light) | `#B3261E` | Error text/icon on light surfaces | 6.53 : 1 vs `--white` |
| `--color-danger` (dark) | `#E25950` | Error text/icon on dark surfaces | 4.93 : 1 vs `--gray-12` |
| `--color-danger-fill` | `#B3261E` | Destructive button/badge solid fill (both themes; label is always `--white`) | 6.53 : 1 (white label on fill) |
| `--color-danger-fill-hover` | `#A1221B` | Hover/press state of a destructive fill | — |
| `--color-danger-subtle-bg` (light) | `#FBEAE9` | Inline error/blocking banner background | — |
| `--color-danger-subtle-bg` (dark) | `#3A1F1D` | Inline error/blocking banner background | — |

**Success has no color.** A rendered chapter, an approved cast candidate, a passed
QA check are the *expected* outcome of a working pipeline — they are not an
interruption and do not need to shout. They are signaled by a filled solid badge
(`--color-bg-inverse` fill, §6 Badge) plus a check glyph, never by green. Warnings
(non-blocking issues, `needs_review` attribution rows) are signaled by a dashed
outline and a triangle glyph, also without color. See §6 (Badge/Status chip) for the
full four-style status language.

### Focus ring

One focus treatment, used everywhere, in both themes:

```
--focus-ring-color: var(--color-text-primary);   /* gray-12 light / white dark */
--focus-ring-width: 2px;
--focus-ring-offset: 2px;
--focus-ring-offset-color: var(--color-bg);
```

`box-shadow: 0 0 0 var(--focus-ring-offset) var(--focus-ring-offset-color), 0 0 0
calc(var(--focus-ring-offset) + var(--focus-ring-width)) var(--focus-ring-color);`
— an offset "halo" gap between control and ring, then a solid ring in the primary
text color. Because `--focus-ring-color` is a semantic token, it automatically flips
to `--white` for a focused control sitting on an inverse-filled surface (e.g. inside
a solid black button). Contrast of ring vs. adjacent surface is always ≥17.9:1 in
both themes — far above the 3:1 WCAG 2.4.11 minimum.

### Waveform and audio visualization in monochrome

Full component anatomy is in §6 (Waveform display); the color rule is stated here
because it is a direct extension of "only one accent, reserved for destructive
confirmation": **the waveform never uses the red.** Progress, played-state, and
issues are shown with lightness and shape only:

- **Unplayed** samples/bars: `--color-border-strong` (`--gray-7`).
- **Played** region (left of the playhead): `--color-text-primary` (solid
  black/white) — played-vs-unplayed is pure lightness contrast.
- **Playhead**: 2px solid `--color-text-primary` line.
- **Blocking issue marker**: solid filled triangle, `--color-text-primary`.
- **Warning issue marker**: hollow/outline triangle, `--color-border-strong` stroke.
- **Info marker**: small filled dot, `--color-text-tertiary`.

Severity is legible from shape and fill alone (solid vs. hollow vs. dot), so the
waveform reads correctly even to a color-blind user with no additional affordance.

## 3. Typography

### Family

| Role | Stack |
|---|---|
| `--font-sans` | `"Inter Variable", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif` |
| `--font-mono` | `"JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace` |

**Inter** (SIL Open Font License 1.1) is the single sans family for every text role in
the app. It is a variable font (weight axis 100–900, `opsz` optical sizing), free to
bundle into an offline desktop/mobile app with no runtime license check or network
fetch — a hard requirement given the product ships as a local-first, dependency-
bundling app across five platforms (see
[product-vision-v2.md](../product/product-vision-v2.md)). It also ships the `tnum`
(tabular numerals) and `ss`/`cv` OpenType feature sets needed below. No serif is used
anywhere — the current UI's Iowan/Palatino-for-headings + Avenir-for-body split
(§1 rejection list) is replaced by one family carrying every role through weight and
size alone.

**JetBrains Mono** (Apache 2.0) is used only for timecodes, durations, segment/render
IDs, hashes, and raw evidence text inside the Inspector — anywhere fixed-width
alignment matters more than typographic warmth.

Ship both as self-hosted variable `.woff2` files bundled with the app (no Google
Fonts CDN call — the product has no mandatory network dependency).

### Thin-weight discipline

The product direction calls for "thin fonts." Executed carelessly, thin weight at
small sizes becomes illegible, especially at the lower end of the gray ramp. The
rule: **weight floor rises as size drops and as text token gets lighter.**

| Text size | Weight floor — `text-primary` | Weight floor — `text-secondary` / `text-tertiary` | Weight 300 permitted? |
|---|---|---|---|
| ≥ 28px (Display, Title) | 300 | 400 | Yes, `text-primary` only |
| 16–27px (Section, Subsection) | 400 | 400 | No |
| < 16px (Body, Label, Caption, Overline, Mono) | 400 | 400 | Never |
| Any size, `text-disabled` token | 400 | — | Never (already sub-AA on contrast; compounding with thin weight makes it unreadable, not just quiet) |

In practice this means: page titles and empty-state headlines may render at weight
300; everything else — including all UI chrome, all body copy, all table and form
text — sits at 400, with 500 or 600 used *sparingly* for hierarchy (active tab, table
header, primary button label, a value that changed in a diff). No weight is ever
below 300, and 300 never appears on `text-secondary`/`text-tertiary`/`text-disabled`
regardless of size — thin-and-quiet is a compounding accessibility risk, thin-and-
loud (primary token, large size) is not.

### Type scale

Assumes a 16px root font size; divide px by 16 for the `rem` value.

| Role | Size | Line-height | Letter-spacing | Weight | Family | Usage |
|---|---|---|---|---|---|---|
| Display | 56px | 60px | −0.02em | 300 | Sans | Empty-state headline, rare hero numeral. Not used in dense UI. |
| Title (H1) | 28px | 34px | −0.01em | 500 | Sans | Page/project title, chapter title |
| Section (H2) | 20px | 26px | −0.01em | 500 | Sans | Panel/card headers |
| Subsection (H3) | 16px | 22px | 0 | 500 | Sans | Grouping labels inside a card |
| Body | 15px | 22px | 0 | 400 | Sans | Default reading and UI text |
| Body-emphasis | 15px | 22px | 0 | 500 | Sans | Inline emphasis, key values inside body copy |
| Label | 13px | 16px | 0.01em | 500 | Sans | Form labels, button text, table column headers |
| Caption | 12px | 16px | 0.01em | 400 | Sans | Metadata, timestamps, helper/error text |
| Overline | 11px | 14px | 0.04em, uppercase | 500 | Sans | Rare eyebrow/status text — **max one use per screen** (§1 rejection list bans blanket uppercase tracking) |
| Mono/Timecode | 13px | 16px | 0 | 400 | Mono | Durations, segment/render IDs, hashes |

### Tabular numerals

Any element displaying a duration, counter, timer, percentage, or page number must
set `font-variant-numeric: tabular-nums;` (Inter's `tnum` feature) so digits do not
jitter or reflow as they change — this matters specifically for the render-queue
progress percentages and job timers that update every poll tick. A `.mono-figures`
utility class applies this plus `--font-mono` for contexts needing true fixed-width
alignment (a column of timecodes); a `.tabular-nums` utility applies just the
OpenType feature to `--font-sans` text (a live-updating percentage inline in a
sentence).

## 4. Spacing, layout, radii, elevation

### Spacing scale (4px base)

| Token | Value |
|---|---|
| `--space-0` | 0px |
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-5` | 20px |
| `--space-6` | 24px |
| `--space-7` | 32px |
| `--space-8` | 40px |
| `--space-9` | 48px |
| `--space-10` | 64px |
| `--space-11` | 80px |
| `--space-12` | 96px |

Card interior padding defaults to `--space-6` (24px); dense/compact card variants use
`--space-4` (16px). Gutter between major panels is never less than `--space-7`
(32px). See §8 for the anti-clutter contract these feed into.

### Container widths

| Token | Value | Usage |
|---|---|---|
| `--container-max` | 1120px | Page content max-width |
| `--sidebar-width` | 280px | Fixed left navigation/workflow rail |
| `--drawer-width` | 400px | Right-anchored drawer (Inspector, issue detail) |
| `--modal-width-sm` | 400px | Confirmation dialogs |
| `--modal-width-md` | 560px | Default modal |
| `--modal-width-lg` | 720px | Modal containing a form or compact table |

### Grid rules

- Internal card layout uses a 12-column fluid grid, `--space-6` (24px) gutter.
- Breakpoint for stacking to a single column: `< 1024px`.
- Panel-count ceiling is a layout rule, not just a guideline — see §8 rule 2.

### Border radius

Small and consistent, not fully sharp (the current UI's `border-radius: 0`
everywhere reads harsh next to a serif/craft aesthetic; small radii read calmer and
more like a finished product) and not bubbly (no 16–24px "pill card" radii).

| Token | Value | Usage |
|---|---|---|
| `--radius-none` | 0px | Table cells, full-bleed images |
| `--radius-sm` | 4px | Buttons, inputs, badges, checkboxes |
| `--radius-md` | 8px | Cards, dropdown menus, popovers |
| `--radius-lg` | 12px | Modals, drawers, large sheets |
| `--radius-full` | 9999px | Pills: segmented control, toggle, avatar, badge |

Rule: a component never mixes more than one radius token internally, and a nested
surface never uses a *larger* radius than its parent.

### Elevation without colored shadows

Light theme lifts a surface with a neutral, non-offset shadow (no colored or
directional "brutalist" shadow, per §1):

```
--shadow-sm: 0 1px 2px rgba(0,0,0,0.06), 0 1px 1px rgba(0,0,0,0.04);   /* hover, small popovers */
--shadow-md: 0 4px 8px rgba(0,0,0,0.08), 0 1px 3px rgba(0,0,0,0.06);   /* menu, tooltip, dropdown */
--shadow-lg: 0 12px 24px rgba(0,0,0,0.10), 0 2px 6px rgba(0,0,0,0.06); /* modal, drawer */
```

Dark theme: a black shadow barely registers against an already-dark canvas, so
elevation there is carried primarily by the **lightness step** in §2
(`--color-surface-raised` = `--gray-11`, one step lighter than the `--gray-12`
canvas) plus a hairline border. A faint shadow is layered on top only for
extra depth on modal/drawer surfaces:

```
--shadow-sm-dark: 0 1px 2px rgba(0,0,0,0.4);
--shadow-md-dark: 0 4px 12px rgba(0,0,0,0.45);
--shadow-lg-dark: 0 16px 32px rgba(0,0,0,0.55);
```

**Rule stated plainly: light theme elevation = shadow; dark theme elevation =
lightness step (+ hairline border), shadow is secondary.**

### Hairline discipline

All borders are `1px` physical width by default. The only exceptions: the 2px focus
ring (§2), and the 2px monochrome "selected row" left-accent (§6, Table/List row).
Do not use 2px+ borders to express emphasis anywhere else — use
`--color-border-strong` at 1px, or a background tint, instead.

### Z-index scale

Introduced alongside the overlay system in §6 (modal/drawer/toast/tooltip do not
exist in the current UI, so there is no existing stacking order to preserve):

| Token | Value |
|---|---|
| `--z-base` | 0 |
| `--z-sticky` | 10 |
| `--z-dropdown` | 20 |
| `--z-drawer` | 30 |
| `--z-modal` | 40 |
| `--z-toast` | 50 |
| `--z-tooltip` | 60 |

## 5. Motion spec

### Philosophy

Animation exists to explain a state change — an element appearing, leaving,
reordering, or progressing. It never exists to decorate, celebrate, or add
perceived polish for its own sake (no confetti, no parallax, no scale-on-hover, no
spinning spinners). This matters doubly for Echodraft: sessions run for hours
against long-running pipeline jobs, so motion also has to communicate *calm,
truthful progress* rather than manufactured energy — see the progress-indicator
entry below, which is the direct answer to the current UI's five uncoordinated
`setTimeout` polling loops (documented in
[frontend-architecture.md](frontend-architecture.md)) causing visible jank.

### Duration and easing tokens

| Token | Value | Usage |
|---|---|---|
| `--motion-duration-instant` | 0ms | `prefers-reduced-motion` fallback for everything |
| `--motion-duration-fast` | 120ms | Hover/press, checkbox/toggle flip, tooltip show |
| `--motion-duration-base` | 200ms | Dropdown open/close, tab switch, badge state change |
| `--motion-duration-moderate` | 300ms | Panel/drawer/modal enter-exit, route/section transition |
| `--motion-duration-slow` | 480ms | List reorder, skeleton-to-content swap |
| `--motion-ease-standard` | `cubic-bezier(0.4, 0.0, 0.2, 1)` | Default for most transitions |
| `--motion-ease-decelerate` | `cubic-bezier(0.0, 0.0, 0.2, 1)` | Entrances — element should decelerate into place |
| `--motion-ease-accelerate` | `cubic-bezier(0.4, 0.0, 1, 1)` | Exits — element should accelerate away |
| `--motion-ease-linear` | `linear` | Determinate progress fills only — must track real progress, never "lie" with easing |

### Permitted animation inventory (exhaustive — nothing outside this list ships)

1. **Panel/route transition** — 200ms opacity cross-fade + 8px vertical settle
   (`translateY(8px) → 0`) on enter, `--motion-ease-decelerate`; 120ms fade-out on
   exit, `--motion-ease-accelerate`. No horizontal slide, no scale/zoom.
2. **List reorder** (render queue re-sort, chapter list) — FLIP-technique position
   animation, 300ms `--motion-ease-standard`; inserted/removed rows fade over 200ms.
3. **Progress indicators** — the calm, informative progress language for
   long-running pipeline jobs:
   - *Determinate bar*: width transitions with `--motion-ease-linear`, matching real
     progress %, and is re-rendered from the backend at most every 250ms — the bar's
     CSS transition (not the poll tick) is what makes motion feel smooth, decoupling
     visual smoothness from poll frequency.
   - *Per-stage stepper*: each pipeline stage node (Cleaning → Structure → Cast →
     Attribution → Direction → Render → QA) fills solid over 200ms
     `--motion-ease-standard` when that stage completes; the connecting line fills
     left-to-right over 300ms.
   - *Indeterminate*: for phases with no measurable sub-progress (e.g. waiting on a
     local LLM call), a static bar/icon breathes opacity between 100% and 55% over a
     1600ms `ease-in-out` infinite loop. No spinning spinner, no sliding
     "barber pole" — a slow breathing pulse reads as patient, not anxious.
4. **Waveform playhead** — position updates via `transform: translateX()` (GPU path,
   never `left`), driven by `requestAnimationFrame` synced to audio `currentTime`
   while playing (no CSS easing — it is 1:1 real time); a manual seek snaps with a
   120ms `--motion-ease-standard` transition.
5. **Hover/press states** — 120ms `--motion-ease-standard` opacity/background change
   only. No `scale()` on hover anywhere (decorative). `:active`/press may apply a 1px
   `translateY` or a small opacity dip over 80ms to confirm the input was registered
   — a tap-confirmation, not a bounce. The one exception is the Slider thumb (§6),
   which grows 16px → 20px on drag start: this is direct-manipulation feedback
   ("you are now holding this"), not decoration.
6. **Skeleton loading** — a monochrome shimmer, never colored:
   `background: linear-gradient(90deg, var(--color-surface-sunken) 25%, var(--color-border) 37%, var(--color-surface-sunken) 63%)`,
   `background-size: 400% 100%`, animating `background-position` 0% → 100% over
   1500ms linear, infinite.
7. **Modal/drawer/toast enter-exit** — modal: opacity 0→1 and scale 0.98→1 over
   200ms `--motion-ease-decelerate`, backdrop fades over 150ms; drawer: slides in
   from its anchored edge (`translateX`/`translateY` 100%→0) over 250ms
   `--motion-ease-decelerate` — the one place a "slide" is permitted, because a
   drawer's affordance *is* sliding on/off canvas, not decoration; toast: enters
   with `translateY(8px)→0` + fade over 200ms, exits with fade + `translateY(-4px)`
   over 150ms after its dwell time.
8. **Reduced motion** — `@media (prefers-reduced-motion: reduce)` collapses every
   duration above to effectively instant and removes every transform: only opacity
   cross-fades remain where they are load-bearing for comprehension (e.g. a tab
   content swap). The indeterminate pulse becomes a static "Working…" label with no
   animation; the skeleton shimmer becomes a flat `--color-surface-sunken` fill.

## 6. Component specs

Default control heights used throughout: `sm` = 32px, `md` = 40px (default), `lg` =
48px. Every interactive control has a minimum **hit area** of 44×44px regardless of
its visual size (§9) — padding, not visual bulk, closes that gap.

### Button

**Anatomy**: optional leading icon, label, optional trailing icon, 8px icon-label
gap.

**Variants**:
- `primary` — solid fill. `background: var(--color-bg-inverse)`;
  `color: var(--color-text-inverse-primary)`; `border: none`;
  `border-radius: var(--radius-sm)`; weight 500. Hover: fill steps one ramp value
  toward its own bg (`--gray-11` in light, `--gray-1` in dark — i.e. it visibly
  "lifts"). Active: opacity 0.92, 80ms. Disabled: `background: var(--gray-4)` (light)
  / `var(--gray-10)` (dark), `color: var(--color-text-disabled)`, no hover/press
  motion, `cursor: not-allowed`.
- `secondary` — hairline outline. `background: transparent`;
  `border: 1px solid var(--color-border-strong)`; `color: var(--color-text-primary)`.
  Hover: `background: var(--color-surface-sunken)`.
- `ghost` — no border, no fill until interaction. `color: var(--color-text-secondary)`.
  Hover: `background: var(--color-surface-sunken)`, `color: var(--color-text-primary)`.
  Replaces the current UI's unstyled inline text actions — same visual weight, but
  with a real hover affordance.
- `destructive` — solid fill in the one reserved red.
  `background: var(--color-danger-fill)`; `color: var(--white)`. Hover:
  `background: var(--color-danger-fill-hover)`. Always gated behind a confirmation
  step for anything irreversible (see Modal below).
- `icon` — square, no visible label; size matches `sm`/`md`/`lg`; icon centered;
  **always** paired with a Tooltip carrying its label (§7). This is the direct
  replacement for the current text-only toolbar buttons.

**Sizes**: `sm` 32px height / 12px horizontal padding / Label-scale (13px) text;
`md` 40px height / 16px padding / Body-scale (15px) text (default); `lg` 48px height
/ 20px padding / Body-scale text, weight 500.

### Input / Textarea / Select

Fully custom — no native `<select>`/`<input type="range">` chrome anywhere in
primary UI.

**Anatomy**: Label (Label scale, `text-secondary`) above the control; control; below
the control, either helper text (Caption scale, `text-tertiary`) or, on validation
failure, error text (Caption scale, `--color-danger`) which replaces the helper.

**Input/Textarea**: `height: 40px` (Input, single line) / `min-height: 96px`
(Textarea, vertical-resize only); `background: var(--color-surface-sunken)`;
`border: 1px solid var(--color-border)`; `border-radius: var(--radius-sm)`;
`padding: 10px 12px`; text = Body scale, `text-primary`. Hover:
`border-color: var(--color-border-strong)`. Focus: `border-color:
var(--color-text-primary)` + standard focus ring. Disabled: unchanged background,
`color: var(--color-text-disabled)`, no hover. Error: `border-color:
var(--color-danger)`, 1px.

**Select**: a custom listbox (WAI-ARIA `listbox`/`combobox` pattern), trigger styled
identically to Input. Opens a `surface-raised` menu (`--shadow-md`, `--radius-md`),
4px minimum margin from viewport edge, 40px option row height, selected option shows
a leading check glyph (icon+weight, not color). Full keyboard support: type-ahead,
arrow navigation, Home/End, Esc to close.

### Slider (direction controls: pace, intensity, gain)

**Anatomy**: 4px track (`--radius-full`, `background: var(--color-border)`); filled
portion from track-start to value, `background: var(--color-text-primary)`; 16px
circular thumb, `background: var(--color-surface)`, `border: 2px solid
var(--color-text-primary)` (a ring thumb, not a solid blob).

**States**: hover — no change to thumb size (reserved for drag, see §5 item 5);
drag/active — thumb grows to 20px over 120ms `--motion-ease-standard`, a floating
value tooltip appears above it showing the exact value in tabular mono figures;
focus — standard ring on the thumb; disabled — track and fill become `--gray-4`,
thumb becomes `--gray-6`, no interaction.

### Toggle (switch)

**Anatomy**: 40×24px pill track, 18px circular knob with `--shadow-sm` (the one
component where a small shadow is used purely to separate a floating knob from its
track, not as a color/decoration statement).

**Off**: `background: transparent`; `border: 1px solid var(--color-border-strong)`;
knob `background: var(--color-text-tertiary)`, positioned left.
**On**: `background: var(--color-text-primary)` (solid fill, no color); knob
`background: var(--color-bg)` — a "punch-through" circle showing the page's own
background color, guaranteeing contrast against the fill in both themes — positioned
right. Knob position transitions via `translateX` over 120ms
`--motion-ease-standard`; track background crossfades over 120ms. Disabled: whole
control at 50% opacity, no interaction.

### Checkbox / Radio

18×18px box (`--radius-sm`) or circle (`--radius-full`); `border: 1.5px solid
var(--color-border-strong)`; `background: var(--color-surface)`. Checked: fill
becomes `--color-text-primary`, the check mark / radio dot is drawn in
`--color-bg` (same punch-through trick as Toggle). Indeterminate (checkbox only):
same fill, a horizontal dash instead of a check. Label: Body scale, 8px gap from the
box; the entire row — not just the box — is a 44px-minimum-height hit target.

### Card / Surface

`background: var(--color-surface)`; `border: 1px solid var(--color-border)`;
`border-radius: var(--radius-md)`; padding `--space-6` (default) or `--space-4`
(compact/dense variant). `Raised` variant (modal, popover, menu only):
`background: var(--color-surface-raised)` + `--shadow-md`/`--shadow-lg` (light) or
the lightness-step + border approach (dark, §4). Nesting is capped at one level
(§8 rule 6) — a card may not contain another bordered card.

### Table / List row

Row height 56px (default, "comfortable") or 44px ("dense" — chosen to still clear
the 44px hit-target minimum for interactive rows). Header row 40px,
`background: var(--color-surface-sunken)`, Label scale, `text-secondary` — sentence
case by default; Overline-style uppercase tracking is permitted here as the single
sanctioned use of that treatment (§3). Row divider: 1px `--color-border`, no
zebra-striping (banded row backgrounds add visual noise without semantic meaning;
scanability instead comes from a hover highlight — `background:
var(--color-surface-sunken)` on `:hover`). Selected row: `background:
var(--color-surface-sunken)` + a 2px left inset border in `--color-text-primary` —
the one surviving colored-left-accent pattern from the current UI, now monochrome
and meaning strictly "selected," never a severity. Any list rendering more than 100
rows must use a virtualized renderer (hard contract, see
[frontend-architecture.md](frontend-architecture.md) — this is the direct fix for
the current unvirtualized segment/transcript lists).

### Tabs

40px height row. Inactive tab: Label scale, `text-secondary`, weight 500. Active
tab: `text-primary`; a 2px bottom border in `--color-text-primary` slides to the new
tab's position/width over 200ms `--motion-ease-standard` on switch (a track-and-
slide, not a fade — the motion itself explains which tab is now selected). Overflow:
horizontal scroll with a fade-edge mask; no overflow dropdown in v1.

### Badge / Status chip — the monochrome status language

Exactly four chip styles exist. No category invents a fifth, and no category gets a
bespoke color (this directly replaces the current UI's per-status clay/moss/red
proliferation).

| Style | Visual | Token | Icon | Meaning |
|---|---|---|---|---|
| Outline (neutral/info) | 1px `border-strong`, transparent fill | `text-secondary` label | none, or a small filled dot | Informational status (queued, draft) |
| Filled solid (positive) | `background: var(--color-bg-inverse)` | `text-inverse-primary` label | leading check glyph | Success/passed/approved — the strongest visual weight, reserved for "done, good" |
| Dashed outline (warning) | 1px **dashed** `border-strong`, transparent fill | `text-primary` label | leading hollow-triangle glyph | Non-blocking issue, `needs_review` |
| Outline, red (blocking/destructive) | 1px solid `--color-danger` border, `--color-danger-subtle-bg` fill | `--color-danger` label | leading filled-triangle glyph | The only chip variant allowed to use the reserved red — blocking issues, render failures, export blockers |

22px (small) / 26px (default) height, `padding: 4px 8px`, `border-radius:
var(--radius-full)`, Caption scale (12px), weight 500.

### Tooltip

`background: var(--color-bg-inverse)`; `color: var(--color-text-inverse-primary)`;
Caption scale; `padding: 6px 10px`; `border-radius: var(--radius-sm)`;
`--shadow-sm`; `max-width: 240px`. Trigger: hover with a 500ms show-delay, or focus
with **no** delay (keyboard accessibility — a tab-focused control must show its
tooltip immediately), or a 500ms long-press on touch. Position: 8px offset from
trigger, auto-flips at viewport edges. Motion: 120ms fade + 4px translate on show
(`--motion-ease-decelerate`), 80ms fade on hide, no hide delay. **Mandatory on every
icon-only button** (§7).

### Modal / Drawer / Toast — the overlay system

None of these exist in the current UI; this is new surface area.

**Modal**: centered; width `--modal-width-sm/md/lg`; `background:
var(--color-surface-raised)`; `border-radius: var(--radius-lg)`; padding
`--space-8`; backdrop `rgba(0,0,0,0.4)` (light) / `rgba(0,0,0,0.6)` (dark), with an
optional `backdrop-filter: blur(4px)`. Structure: Title (Section scale) + optional
description (Body, `text-secondary`) + content + right-aligned footer actions
(`secondary` button, then `primary`/`destructive`). Focus-trapped; Esc always closes
without side effects — a destructive confirmation modal never treats Esc as a
silent confirm. For a destructive confirmation specifically, the safe action
(`Cancel`, styled `secondary`) sits in the position users' muscle memory treats as
"primary" (rightmost-but-one / visually calmer), and the destructive action is
styled `destructive` (red fill) but is not given extra visual weight — this biases
against accidental confirmation.

**Drawer**: anchored right (`--drawer-width` = 400px) on desktop, bottom (max 80vh)
below the 1024px breakpoint. Same surface/radius rules, rounded only on the exposed
edge. This is the standard home for the evidence/JSON Inspector (§8).

**Toast**: bottom-center (bottom-right ≥1280px) stack, max 3 concurrent;
`background: var(--color-bg-inverse)`; `color: var(--color-text-inverse-primary)`;
`min-height: 40px`; `--radius-sm`; `--shadow-md`. Default toasts auto-dismiss after
4s; error/destructive-result toasts do not auto-dismiss and require manual close.
Each toast may carry the same iconography as Badge (check / hollow-triangle /
filled-triangle-red-only-for-fatal) and always has a close (`×`) icon button.

### Progress (bar, stepper, ring)

**Bar**: track 4px (inline) / 8px (standalone), `background:
var(--color-surface-sunken)`; fill `background: var(--color-text-primary)`,
`--radius-full`; width animates per §5 item 3.

**Stepper**: row of 24px circular nodes joined by 2px connecting lines. Pending:
outline only (`border-strong`, no fill). Active: `border: var(--color-text-primary)`
+ indeterminate pulse if sub-progress is unknown, or a small determinate ring inside
if it is known. Complete: solid `--color-text-primary` fill + a check glyph drawn in
`--color-bg`. This is the primary UI for the multi-stage pipeline job (Cleaning →
Structure → Cast Discovery → Speaker Attribution → Direction → Render → QA).

**Ring**: compact circular determinate indicator (24px or 32px diameter, 3px
stroke) for dense contexts (a single row's render % in a table). Track:
`--color-border`. Progress arc: `--color-text-primary`, animated via
`stroke-dashoffset` with `--motion-ease-linear`.

### Empty state

Icon (24–32px stroke icon, `text-tertiary`) + short title (Section scale,
`text-primary`) + one-line description (Body, `text-secondary`) + optional single
`primary` button. Max content width 320px, centered, `--space-10` (64px)+ vertical
padding. The icon replaces the current UI's decorative 5rem serif glyph (§1
rejection list).

### Segmented control

Single-row pill container, `--radius-full`, `background: var(--color-surface-
sunken)`, 2px internal padding, `border: 1px solid var(--color-border)`. 2–5 options,
each 32–40px tall. Selected option is drawn as a sliding "thumb"
(`background: var(--color-surface)`, `--shadow-sm`) that transform-animates between
positions over 200ms `--motion-ease-standard`; selected label `text-primary` weight
500, unselected `text-secondary` weight 400.

### Audio player transport

Row layout: `[play/pause icon-button, 40px circle] [current time, mono/tabular]
[waveform scrubber, flex-grow] [duration, mono/tabular] [volume icon-button + slider
on demand] [speed segmented control: 1× / 1.25× / 1.5× / 2×]`. The play/pause button
is the one circular, `bg-inverse`-filled icon button in the system — the single
"prominent" control, because transport is the one primary action of a player view.
The waveform itself is the seek control; there is no separate duplicate range
slider.

### Waveform display

Rendered on `<canvas>` (device-pixel-ratio aware) — this is a direct performance fix
replacing the current one-DOM-node-per-bucket rendering documented in
[frontend-architecture.md](frontend-architecture.md). Color rules are in §2; full
interaction: hovering/focusing an issue marker opens a Tooltip with the issue's
`evidence` text; clicking a marker seeks the transport to that timestamp and opens
the relevant panel in the Inspector drawer (never inline — §8). A fixed 12px-tall
minimap strip above the zoomed detail view keeps chapter-position orientation while
zoomed in (ctrl+scroll or pinch to zoom the time axis).

### Diff / compare view (render compare)

Two-column layout (stacked below 1024px): "Previous render" | "Current render",
each with its own compact waveform + transport, linked cursors (scrubbing one
scrubs both). A thin delta strip beneath both waveforms renders only *where* the two
renders differ, using `--color-text-primary` opacity proportional to the magnitude
of the difference — darker means more different — never a color heatmap. Metadata
diff (LUFS, true peak, duration, voice, direction parameters) renders as a compact
key-value table: changed rows are bolded (weight 600) and show an inline
"before → after" pair (e.g. `-19.2 LUFS → -19.0 LUFS`); unchanged rows render once,
in `text-secondary`, not duplicated per column. This replaces the current 12-stat-
tile-wall and inline `<pre>` JSON dump (§1) — raw evidence, if needed at all, lives
behind a collapsed Inspector disclosure at the bottom, in `--font-mono`, only opened
on request.

## 7. Iconography

**Lucide** (ISC license, free, tree-shakeable, MIT-compatible) is the single icon
set. Its consistent 24×24 grid and stroke-based construction match a thin,
variable-weight type system far better than a filled/glyph icon font would.

- **Stroke width**: 1.5px at 20–24px render size (Lucide's default 2px reads heavy
  next to 400-weight Inter at small sizes — pass `strokeWidth={1.5}`).
- **Sizing**: icon size mirrors the text role beside it — 16px next to Caption/Label
  text, 20px next to Body text, 24px standalone (toolbar, nav, empty state). Every
  interactive icon sits inside a hit area of at least 44×44px regardless of the
  icon's own visual size (padding, not a bigger icon, closes the gap).
- **Toolbar replacement rule**: every current text-only action (§1) becomes either
  icon+tooltip (icon-only button, §6) or icon+label, chosen by available space and
  action count — if a row has ≤4 actions and space is tight (dense table row,
  mobile), use icon+tooltip; otherwise icon+label.

Concrete mapping from current text-only actions to Lucide icons, for direct reuse
by implementers:

| Current text button | Icon | Pattern |
|---|---|---|
| "Why?" (attribution rationale) | `Info` | icon+tooltip |
| "Lock" / unlock (attribution) | `Lock` / `LockOpen` | icon+tooltip |
| "Split" (segment) | `Scissors` | icon+label |
| "Merge next" (segment) | `Merge` | icon+label |
| Delete / remove | `Trash2` | icon+tooltip, `destructive` variant |
| Approve / confirm cast | `Check` | icon+label |
| Play / Pause | `Play` / `Pause` | icon-only, transport |
| Re-render | `RotateCw` | icon+tooltip |
| Export | `Download` | icon+label |
| Settings / production settings | `Settings2` | icon+label |
| Warning / needs-review marker | `Triangle` (outline) | badge/marker glyph |
| Blocking issue marker | `Triangle` (filled) | badge/marker glyph, red only in the badge/toast context, monochrome in the waveform |

## 8. Density & information-hierarchy rules

Stated as testable rules, not guidelines, so a PR review can check them directly
against a screenshot:

1. **One primary action per view.** Exactly one `Button` styled `primary` may be
   visible in a panel/screen at a time. Every other action is `secondary`, `ghost`,
   `destructive`, or icon-only.
2. **Panel ceiling.** No more than 2 major panels are simultaneously visible at
   ≥1280px; exactly 1 at <1024px (everything else lives in a Drawer or is reached by
   navigation). This directly replaces the current Structure screen's 7+ stacked
   panel types.
3. **Progressive disclosure is mandatory, not optional.** Raw evidence, JSON, or a
   full attribution/decision trace is never rendered inline by default. It lives
   behind a closed Inspector (disclosure or drawer), and the closed state must show
   a one-line summary of what's inside — never a bare "Details ▸" with no preview.
4. **Metric ceiling.** No more than 4 stat/metric tiles are visible at once in any
   summary strip (down from the current 12-tile quality bar). Additional metrics
   move behind the Inspector or a `ghost`-styled "View all metrics" action.
5. **Whitespace floor.** Minimum `--space-6` (24px) interior card padding, minimum
   `--space-7` (32px) gutter between major panels, minimum one blank `--space-6` row
   between unrelated control groups inside a form.
6. **Nesting ceiling.** A card/surface may contain at most one nested bordered
   surface. No surface-on-surface-on-surface stacking (the current UI nests
   panel → section → card → list-item-article four deep in places).
7. **Prose width.** Body copy (manuscript preview text, descriptions) caps at ~72
   characters per line (`max-width: ~640px`).
8. **No raw browser chrome.** Native `<select>`, `<input type="range">`,
   `<details>/<summary>` do not appear in primary UI — each has a custom replacement
   specified in §6.

## 9. Accessibility

### Contrast — which text token is allowed on which surface

Computed per §2's WCAG relative-luminance method; "AA normal" = 4.5:1, "AA large/UI"
= 3:1, "AAA normal" = 7:1.

**Light theme** (surface = `--color-bg` / `--color-surface`, both `--white`):

| Token | Ratio | AA normal (4.5) | AA large/UI (3.0) | AAA normal (7.0) |
|---|---|---|---|---|
| `--color-text-primary` (`--gray-12`) | 17.93 | Pass | Pass | Pass |
| `--color-text-secondary` (`--gray-9`) | 7.01 | Pass | Pass | Pass |
| `--color-text-tertiary` (`--gray-8`) | 4.61 | Pass | Pass | Fail |
| `--color-text-disabled` (`--gray-6`) | 2.01 | Fail | Fail | Fail — intentional, disabled content only |
| `--color-border-strong` (`--gray-7`) | 3.03 | n/a (non-text) | Pass | n/a |
| `--color-danger` (`#B3261E`) | 6.53 | Pass | Pass | Fail |

**Dark theme** (surface = `--color-bg` / `--color-surface`, both `--gray-12`):

| Token | Ratio | AA normal (4.5) | AA large/UI (3.0) | AAA normal (7.0) |
|---|---|---|---|---|
| `--color-text-primary` (`--white`) | 17.93 | Pass | Pass | Pass |
| `--color-text-secondary` (`--gray-6`) | 8.94 | Pass | Pass | Pass |
| `--color-text-tertiary` (`--gray-7`) | 5.91 | Pass | Pass | Fail |
| `--color-text-disabled` (`--gray-9`) | 2.56 | Fail | Fail | Fail — intentional, disabled content only |
| `--color-border-strong` (`--gray-8`) | 3.89 | n/a (non-text) | Pass | n/a |
| `--color-danger` (`#E25950`) | 4.93 | Pass | Pass | Fail |

**Rule**: `text-disabled` may never be used for content a user must read to
proceed — its whole purpose is to read as "not currently actionable," and that
requires looking quieter than AA allows. Every other text token clears AA normal
text at minimum in both themes.

### Focus visibility

Every interactive element shows the §2 focus ring on keyboard focus
(`:focus-visible`, never suppressed with `outline: none` without the ring
replacement). Ring contrast is ≥17.9:1 in both themes against any adjacent surface,
well above the 3:1 minimum in WCAG 2.4.11.

### Hit targets

Every interactive control — button, icon button, checkbox row, tab, badge (if
clickable), waveform marker — has a minimum hit area of **44×44 CSS px**, regardless
of its visual/painted size. A 32px icon button gets 6px of invisible padding on each
side to reach 44px; an 18px checkbox's *row* (not the box itself) is the 44px target.

### Keyboard patterns

- Tab order follows visual/reading order on every screen.
- Custom components implement their WAI-ARIA APG pattern: `Select`/`Combobox`
  (listbox pattern, type-ahead, arrow keys, Home/End, Esc), `Slider` (arrow keys ±1
  step, Page Up/Down ±10%, Home/End to min/max), `Toggle`/`Checkbox`/`Radio` (Space
  to toggle, arrow keys within a radio group), `Tabs` (arrow keys to move, Home/End),
  `Modal` (focus trap, Esc to close, focus returns to the trigger on close).
- A skip-to-content link is present on every route.
- Async pipeline progress and toast notifications are announced via
  `aria-live="polite"` regions so a screen-reader user gets non-visual status
  updates during long-running jobs, not just a silently-updating progress bar.

## 10. Token export — CSS custom properties

Complete, copy-pasteable. Naming convention: `--{category}-{role}[-{variant}]`,
kebab-case (e.g. `--color-text-secondary`, `--space-4`, `--radius-md`,
`--motion-duration-base`). Raw ramp values (`--gray-*`, `--white`, `--black`) are
never referenced directly from component code — components consume only the
semantic layer (`--color-*`) so the ramp can be re-pointed without touching
component styles.

```css
:root {
  /* Raw ramp — light-mode default */
  --white: #FFFFFF;
  --gray-1: #F9F9F9;
  --gray-2: #F4F4F4;
  --gray-3: #EAEAEA;
  --gray-4: #DEDEDE;
  --gray-5: #D3D3D3;
  --gray-6: #B7B7B7;
  --gray-7: #949494;
  --gray-8: #757575;
  --gray-9: #595959;
  --gray-10: #424242;
  --gray-11: #2C2C2C;
  --gray-12: #171717;
  --black: #000000;

  /* Semantic color — light theme */
  --color-bg: var(--white);
  --color-surface: var(--white);
  --color-surface-sunken: var(--gray-1);
  --color-surface-raised: var(--white);
  --color-border: var(--gray-4);
  --color-border-strong: var(--gray-7);
  --color-text-primary: var(--gray-12);
  --color-text-secondary: var(--gray-9);
  --color-text-tertiary: var(--gray-8);
  --color-text-disabled: var(--gray-6);
  --color-bg-inverse: var(--gray-12);
  --color-text-inverse-primary: var(--white);
  --color-text-inverse-secondary: var(--gray-6);
  --color-border-inverse: var(--gray-10);

  /* The one accent hue — light theme */
  --color-danger: #B3261E;
  --color-danger-fill: #B3261E;
  --color-danger-fill-hover: #A1221B;
  --color-danger-subtle-bg: #FBEAE9;

  /* Focus ring */
  --focus-ring-color: var(--color-text-primary);
  --focus-ring-width: 2px;
  --focus-ring-offset: 2px;
  --focus-ring-offset-color: var(--color-bg);

  /* Typography */
  --font-sans: "Inter Variable", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --font-mono: "JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;

  --text-display-size: 56px;   --text-display-line: 60px;  --text-display-tracking: -0.02em; --text-display-weight: 300;
  --text-title-size: 28px;     --text-title-line: 34px;    --text-title-tracking: -0.01em;   --text-title-weight: 500;
  --text-section-size: 20px;   --text-section-line: 26px;  --text-section-tracking: -0.01em; --text-section-weight: 500;
  --text-subsection-size: 16px;--text-subsection-line: 22px;--text-subsection-tracking: 0;    --text-subsection-weight: 500;
  --text-body-size: 15px;      --text-body-line: 22px;     --text-body-tracking: 0;           --text-body-weight: 400;
  --text-body-emphasis-weight: 500;
  --text-label-size: 13px;     --text-label-line: 16px;    --text-label-tracking: 0.01em;     --text-label-weight: 500;
  --text-caption-size: 12px;   --text-caption-line: 16px;  --text-caption-tracking: 0.01em;   --text-caption-weight: 400;
  --text-overline-size: 11px;  --text-overline-line: 14px; --text-overline-tracking: 0.04em;  --text-overline-weight: 500;
  --text-mono-size: 13px;      --text-mono-line: 16px;     --text-mono-tracking: 0;           --text-mono-weight: 400;

  /* Spacing (4px base) */
  --space-0: 0px;  --space-1: 4px;  --space-2: 8px;  --space-3: 12px;
  --space-4: 16px; --space-5: 20px; --space-6: 24px; --space-7: 32px;
  --space-8: 40px; --space-9: 48px; --space-10: 64px; --space-11: 80px; --space-12: 96px;

  /* Layout */
  --container-max: 1120px;
  --sidebar-width: 280px;
  --drawer-width: 400px;
  --modal-width-sm: 400px;
  --modal-width-md: 560px;
  --modal-width-lg: 720px;

  /* Radius */
  --radius-none: 0px;
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-full: 9999px;

  /* Elevation — light theme */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.06), 0 1px 1px rgba(0,0,0,0.04);
  --shadow-md: 0 4px 8px rgba(0,0,0,0.08), 0 1px 3px rgba(0,0,0,0.06);
  --shadow-lg: 0 12px 24px rgba(0,0,0,0.10), 0 2px 6px rgba(0,0,0,0.06);

  /* Z-index */
  --z-base: 0; --z-sticky: 10; --z-dropdown: 20; --z-drawer: 30;
  --z-modal: 40; --z-toast: 50; --z-tooltip: 60;

  /* Motion */
  --motion-duration-instant: 0ms;
  --motion-duration-fast: 120ms;
  --motion-duration-base: 200ms;
  --motion-duration-moderate: 300ms;
  --motion-duration-slow: 480ms;
  --motion-ease-standard: cubic-bezier(0.4, 0.0, 0.2, 1);
  --motion-ease-decelerate: cubic-bezier(0.0, 0.0, 0.2, 1);
  --motion-ease-accelerate: cubic-bezier(0.4, 0.0, 1, 1);
  --motion-ease-linear: linear;

  /* Control sizing */
  --control-height-sm: 32px;
  --control-height-md: 40px;
  --control-height-lg: 48px;
  --hit-area-min: 44px;
}

/* System preference: dark, unless the user explicitly chose light */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --color-bg: var(--gray-12);
    --color-surface: var(--gray-12);
    --color-surface-sunken: var(--black);
    --color-surface-raised: var(--gray-11);
    --color-border: var(--gray-11);
    --color-border-strong: var(--gray-8);
    --color-text-primary: var(--white);
    --color-text-secondary: var(--gray-6);
    --color-text-tertiary: var(--gray-7);
    --color-text-disabled: var(--gray-9);
    --color-bg-inverse: var(--white);
    --color-text-inverse-primary: var(--gray-12);
    --color-text-inverse-secondary: var(--gray-8);
    --color-border-inverse: var(--gray-4);

    --color-danger: #E25950;
    --color-danger-fill: #B3261E;
    --color-danger-fill-hover: #A1221B;
    --color-danger-subtle-bg: #3A1F1D;

    --shadow-sm: var(--shadow-sm-dark, 0 1px 2px rgba(0,0,0,0.4));
    --shadow-md: var(--shadow-md-dark, 0 4px 12px rgba(0,0,0,0.45));
    --shadow-lg: var(--shadow-lg-dark, 0 16px 32px rgba(0,0,0,0.55));
  }
}

/* Explicit user override, wins regardless of system preference */
[data-theme="dark"] {
  --color-bg: var(--gray-12);
  --color-surface: var(--gray-12);
  --color-surface-sunken: var(--black);
  --color-surface-raised: var(--gray-11);
  --color-border: var(--gray-11);
  --color-border-strong: var(--gray-8);
  --color-text-primary: var(--white);
  --color-text-secondary: var(--gray-6);
  --color-text-tertiary: var(--gray-7);
  --color-text-disabled: var(--gray-9);
  --color-bg-inverse: var(--white);
  --color-text-inverse-primary: var(--gray-12);
  --color-text-inverse-secondary: var(--gray-8);
  --color-border-inverse: var(--gray-4);

  --color-danger: #E25950;
  --color-danger-fill: #B3261E;
  --color-danger-fill-hover: #A1221B;
  --color-danger-subtle-bg: #3A1F1D;

  --shadow-sm: 0 1px 2px rgba(0,0,0,0.4);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.45);
  --shadow-lg: 0 16px 32px rgba(0,0,0,0.55);
}

[data-theme="light"] {
  /* Explicit override back to light; identical to the :root defaults above. */
}
```

Utility classes built on these tokens (`.tabular-nums`, `.mono-figures`,
`.visually-hidden`, `.skip-link`) and the mapping from this token layer to React
component props are implementation concerns and belong in
[frontend-architecture.md](frontend-architecture.md), not in this spec.
