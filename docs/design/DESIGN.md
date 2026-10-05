# Design System: ECHO - Institutional Intelligence

Source of truth for the web UI (`frontend/src/index.css`). It is derived from the ECHO Google Stitch project
"ECHO Corporate Health Observatory" (project 14802857973600350452): its DESIGN.md ("Institutional
Intelligence") defines the light theme, and its rendered screens (Overview portal, Methodology, Signals radar,
Enterprise dossier, Shader) define the dark terminal theme, which is the default.

Content rule: the Stitch screens contain illustrative figures (enterprise counts, SOC2 claims, precision rates).
The product shows only real values from this deployment: API status and measured latency, company, report and
model counts, model-card metrics, and each company's own report.

## 1. Atmosphere
A calm institutional intelligence terminal. Charcoal surfaces, hairline rules, mono system labels and one emerald
accent. Hierarchy comes from type scale and weight, not fills or shadows. The landing hero sits on the Stitch
"silk ribbons" WebGL shader (emerald to teal light ribbons); everything else stays flat.

## 2. Colour
| Role | Dark (default) | Light |
|---|---|---|
| Page | #090A0D | #F8F8F6 |
| Surface | #0F1117 | #FFFFFF |
| Surface raised / inset | #151821 / #1B1F29 | #F2F2EE / #EBEBE7 |
| Hairline / strong | #1B1F29 / #2B3446 | #E2E3DF / #D1D3CD |
| Ink / secondary / muted | #E5E7EB / #A3AAB6 / #737B88 | #121316 / #3A3E45 / #5D6168 |
| Primary button | #E5E7EB on #090A0D | #1E2530 on #F8F8F6 |
| Accent (emerald) | #10B981, text #4EDEA3 | #1B6E48, text #1B5E3C |

- Status colours (good, warning, serious, critical) are reserved for health bands and always come with an icon and a label.
- Charts use the dataviz reference palette re-ordered emerald first, validated with `validate_palette.js`:
  - light, against #FFFFFF: #0E9468, #EB6834, #2A78D6, #C98500;
  - dark, against #0F1117: #199E70, #D95926, #3987E5, #C98500.
- Diverging charts stay blue (raises health) against red (lowers health), the CVD-safe pair.

## 3. Typography
- **IBM Plex Sans** for UI and narrative. Headlines use Light (300) at large sizes with tracking -0.02 to -0.03em; card titles use SemiBold at 14px.
- **JetBrains Mono** for every number, ticker, CIK, date in lists, metric and axis tick, with tabular lining figures.
- **Micro labels** are mono, 11px, uppercase, tracking 0.12em, in the muted colour: eyebrows ("METHODOLOGY // ATTRIBUTION ENGINE"), metric captions and status text.

## 4. Shape and depth
- **Radius:** controls 5px, badges 3-4px, cards and windows 8px. No pills, except status dots.
- **Depth:** hairline 1px borders and tonal steps; no drop shadows on cards. Only popovers get the spec's subtle shadow.
- **Cards** have a 36px header strip with a hairline bottom rule.
- **Window chrome** (three dots plus a mono file name) frames illustrative panels: `echo_field.health`, `scoring.py`, auth.

## 5. Components
- **Buttons, 32px:**
  - primary (ink fill);
  - accent (emerald fill, for sign-up and CTAs);
  - secondary (hairline outline);
  - ghost.
  Pressing nudges the button down by 1px.
- **Search:** 5px field with an emerald 1px focus ring, a "/" shortcut and an "Analyse" action.
- **Tabs:** underline tabs; a 2px emerald indicator glides between them.
- **Dossier hero** (report page):
  - breadcrumb `COMPANIES / SECTOR / DOSSIER // TICKER-DATE`;
  - mono chips (ticker, SIC, CIK);
  - a key-metrics row (as of, data coverage, distress, signals);
  - a ring gauge with the band badge and the band's meaning.
- **Pillar cards:** "PILLAR I to V" label, band-style tag, a mono score out of 100, and a 1px progress rule.
- **Status:**
  - the header pill shows "API ONLINE // n ms", measured in the browser;
  - the footer telemetry bar shows system status, latency, models in production and data sources.

## 6. Layout
- **Containers:** max width 1360px; gutters of 16px on mobile and 24px on desktop. The landing hero and the ticker are full bleed.
- **Landing**, in order:
  1. split hero (copy and search on the left, the echo-field window on the right);
  2. demo-company ticker;
  3. four live figures;
  4. dossier cards;
  5. methodology (an auto-advancing step list beside a code window whose highlighted lines follow the active step);
  6. five pillar cards;
  7. the model scoreboard table;
  8. the CTA panel.
- **Mobile:** below 768px everything is a single column, with no horizontal scroll.

## 7. Motion
- **Easing:** fluid `cubic-bezier(0.16, 1, 0.3, 1)` and spring `cubic-bezier(0.32, 0.72, 0, 1)`.
- **Entry:** content rises 12px over 0.7s, siblings stagger by 55ms, and landing sections reveal on scroll (IntersectionObserver).
- **Data:** the gauge ring draws in while its number counts up, and pillar and progress rules grow from the left.
- **Continuous:**
  - the shader ribbons follow the pointer;
  - echo pulses;
  - floating pillar chips;
  - live status dots;
  - the ticker marquee, which pauses on hover.
- **Performance:**
  - the shader renders at 0.6x resolution and pauses off-screen and in hidden tabs;
  - only transform and opacity are animated;
  - reduced motion turns every animation off and the shader becomes a single still frame.

## 8. Banned
No emojis, no fabricated figures, no colour-only status, no dual-axis charts, no glassmorphism on content, no
gradient text, no pills on cards or buttons, no em dashes.
