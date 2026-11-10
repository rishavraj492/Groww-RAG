---
name: Fund Facts
colors:
  surface: '#0c1322'
  surface-dim: '#0c1322'
  surface-bright: '#323949'
  surface-container-lowest: '#070e1d'
  surface-container-low: '#141b2b'
  surface-container: '#191f2f'
  surface-container-high: '#232a3a'
  surface-container-highest: '#2e3545'
  on-surface: '#dce2f7'
  on-surface-variant: '#bbcac1'
  inverse-surface: '#dce2f7'
  inverse-on-surface: '#293040'
  outline: '#86948c'
  outline-variant: '#3c4a43'
  surface-tint: '#50ddad'
  primary: '#50ddad'
  on-primary: '#003828'
  primary-container: '#00b386'
  on-primary-container: '#003d2c'
  inverse-primary: '#006c4f'
  secondary: '#7bd0ff'
  on-secondary: '#00354a'
  secondary-container: '#00a6e0'
  on-secondary-container: '#00374d'
  tertiary: '#ffb95f'
  on-tertiary: '#472a00'
  tertiary-container: '#db8c00'
  on-tertiary-container: '#4d2e00'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#71fac8'
  primary-fixed-dim: '#50ddad'
  on-primary-fixed: '#002116'
  on-primary-fixed-variant: '#00513b'
  secondary-fixed: '#c4e7ff'
  secondary-fixed-dim: '#7bd0ff'
  on-secondary-fixed: '#001e2c'
  on-secondary-fixed-variant: '#004c69'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb95f'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#0c1322'
  on-background: '#dce2f7'
  surface-variant: '#2e3545'
typography:
  headline-xl:
    fontFamily: Geist
    fontSize: 2rem
    fontWeight: '600'
    lineHeight: 2.5rem
    letterSpacing: -0.025em
  headline-lg:
    fontFamily: Geist
    fontSize: 1.5rem
    fontWeight: '600'
    lineHeight: 2rem
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Geist
    fontSize: 1.25rem
    fontWeight: '500'
    lineHeight: 1.75rem
    letterSpacing: -0.015em
  body-lg:
    fontFamily: Geist
    fontSize: 1rem
    fontWeight: '400'
    lineHeight: 1.5rem
    letterSpacing: -0.01em
  body-md:
    fontFamily: Geist
    fontSize: 0.875rem
    fontWeight: '400'
    lineHeight: 1.375rem
    letterSpacing: -0.005em
  body-sm:
    fontFamily: Geist
    fontSize: 0.75rem
    fontWeight: '400'
    lineHeight: 1.125rem
    letterSpacing: 0em
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 0.8125rem
    fontWeight: '500'
    lineHeight: 1.125rem
    letterSpacing: -0.01em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 0.6875rem
    fontWeight: '500'
    lineHeight: 1rem
    letterSpacing: 0.02em
  code-inline:
    fontFamily: JetBrains Mono
    fontSize: 0.75rem
    fontWeight: '400'
    lineHeight: 1rem
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-desktop: 1.5rem
  margin: 1.25rem
  margin-desktop: 2rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1.25rem
  space-xl: 2rem
---

## Brand & Style

This design system is tailored for an institutional-grade, source-grounded mutual fund intelligence assistant. It marries the consumer agility and accessibility of modern fintech platforms with the rigorous, provenance-driven precision demanded by institutional wealth managers and meticulous retail investors. The system prioritizes objective retrieval over conversational fluff: every assertion is backed by verifiable statutory data, SID/KIM filings, and historical NAV ledgers.

The aesthetic philosophy is **Technical Minimalism with Focused Financial Density**:
- **Tone:** Impartial, authoritative, calm, and analytical.
- **Visual Stance:** Dark-mode primary workspace, razor-sharp information hierarchy, high data-ink ratio, and zero frivolous ornamentation.
- **Provenance System:** Inline statutory badges and source-grounded chips immediately delineate between confirmed regulatory facts, calculated fund analytics, and safe retrieval limits (e.g., policy refusals).

## Colors

The palette is engineered for prolonged analytical sessions on high-resolution desktop displays, anchoring deep contrasts without retinal fatigue.

- **Primary (`#00B386`):** The signature Groww-inspired emerald. Used strictly for confirmed factual synthesis, primary action gates, active toggles, and positive delta values. Its interactive hover state shifts to `#00A37A`.
- **Secondary (`#38BDF8`):** Official citation blue. Reserved exclusively for verifiable source-grounding anchors, statutory PDF extracts, SID/KIM page locators, and SEBI compliance tags. Its supporting deep tint is `#0284C7`.
- **Tertiary (`#F59E0B`):** Regulatory disclaimer and refusal amber. Highlights partial information gaps, RAG retrieval uncertainty bounds, risk warnings, or automated refusals when queries exceed statutory facts. Its dark shade is `#D97706`.
- **Neutral (Base `#0B0F14`, Surface Tier `#111827`):** The core charcoal chassis. Layered with deliberate tonal steps:
  - Canvas Deep: `#0B0F14`
  - Elevated Container: `#161B22`
  - Active/Hover Card: `#1C2430`
  - Floating Popover/Inspector: `#222B38`
- **Text & Stroke Contrast:** Primary high-contrast off-white (`#F8FAFC`), secondary analytical metadata (`#94A3B8`), and disabled or tertiary meta-labels (`#64748B`). Hairline division is maintained via precise stroke tiers (`#1E293B` baseline, `#334155` active).

## Typography

The type system is built on an austere dual-typeface architecture:
- **Geist** governs natural language parsing, query syntheses, question-answer dialogs, and structural UI headers. Its tight horizontal metrics prevent ragged layouts during dense data presentation.
- **JetBrains Mono** is deployed for numeric metrics (AUM, expense ratios, CAGR, standard deviation, tracking error), document provenance references (SEBI/AMFI registration codes, SID filing stamps), and citation metadata badges. Tabular numerical figures (`tnum`) must remain active across all numeric contexts to ensure clean scanning down ledger columns.

## Layout & Spacing

The layout is constructed for high-efficiency desktop interactions, optimized for 1280px to 1920px viewports with a 12-column grid.

- **Desktop Structure:** Dual-pane split configuration:
  - Left / Central Canvas (7–8 columns): Query input, RAG-grounded response cards, interactive Q&A stream, and factual data tables.
  - Right Inspector (4–5 columns): Sticky Provenance Drawer showing raw source excerpts, PDF page previews, filing dates, and verified fund audit metrics.
- **Rhythm:** Spacing relies on compact multiples of 4px. Element-dense interfaces use `space-xs` (4px) and `space-sm` (8px) for badge internals and micro-tags. Structural component margins use `space-md` (12px) and `space-lg` (20px) to keep response contexts interconnected without wasting analytical real estate.

## Elevation & Depth

Visual separation in this system does not rely on heavy drop shadows or dramatic blurs. Instead, depth is articulated through **tonal stratification and razor-sharp perimeter definition**:

- **Canvas Background (`#0B0F14`):** The foundational substrate of the entire viewport.
- **Base Containers & Cards (`#111827`):** Elevated over the canvas using a continuous 1px perimeter border of `#1E293B`.
- **Secondary Surfaces & Active Focus (`#161B22` / `#1C2430`):** Used for pinned queries, prompt inputs, and nested metric widgets. Hover interactions step up to `#1C2430` with border transition to `#334155`.
- **Overlays & Sticky Inspectors (`#222B38`):** Reserved for contextual hover cards, provenance tooltip inspectors, and document popovers. Supported by an ultra-subtle, deep ambient shadow: `0 8px 24px -4px rgba(0, 0, 0, 0.45)`.
- **Focus Rings:** Precise 1px inset glow in the primary emerald tint: `0 0 0 1px #00B386`.

## Shapes

The interface balances sharp technological precision with subtle ergonomic softening. 

- **Primary Geometry:** Base corner radius is soft (0.25rem / 4px) for data tables, text fields, cards, and response panels.
- **Pill Tags & Citation Badges:** Specific micro-components (source badges, compliance tags, metric capsules) use full pill rounding (`rounded-full` / 9999px) to distinctly contrast against the rectangular architectural grid.

## Components

### Buttons
- **Primary:** Background `#00B386`, text `#0B0F14` (ultra-dark contrast), font weight 500. Padding: 8px 16px. Hover state shifts to `#00A37A`. Active state: `#008F6B`.
- **Secondary / Citation Button:** Background `rgba(56, 189, 248, 0.08)`, border `1px solid rgba(56, 189, 248, 0.25)`, text `#38BDF8`. Hover state: background `rgba(56, 189, 248, 0.15)`.
- **Ghost / Neutral:** Background transparent, text `#94A3B8`, border `1px solid #1E293B`. Hover state: background `#161B22`, text `#F8FAFC`.

### Citation & Provenance Badges (Pills)
- Rendered inline within factual answers (e.g., `[Doc 1.2: SID Page 42]`).
- Structure: JetBrains Mono `0.6875rem`, pill-shaped border radius (9999px), background `rgba(56, 189, 248, 0.1)`, text `#38BDF8`, border `1px solid rgba(56, 189, 248, 0.3)`.
- On click or hover: Activates the right-side inspector pane showing the verified filing snippet.

### Disclaimer & Out-of-Bounds Badges
- Used when factual grounding is missing or query seeks speculative advice.
- Pill shape, background `rgba(245, 158, 11, 0.08)`, border `1px solid rgba(245, 158, 11, 0.3)`, text `#F59E0B`.

### Input Fields & Query Bar
- Primary prompt container styled with `#161B22`, border `1px solid #1E293B`, rounded `0.25rem`.
- Text input: `#F8FAFC` typography, placeholder in `#64748B`.
- Focus state: Border transitions to `#00B386` with zero outer fuzzy glow, maintaining a pure 1px crisp outline.

### Metric Cards & Ledger Tables
- Cards sit on `#111827` with a 1px `#1E293B` stroke. Header labels use `JetBrains Mono` sm in `#94A3B8`. Numeric values use `Geist` or `JetBrains Mono` medium at 1.25rem in `#F8FAFC`.
- Positive historical delta indicators utilize `#00B386`; negative performance indicators use standard high-contrast crimson (`#F43F5E`).

### Checkboxes & Toggle Controls
- Custom square markers with `2px` roundedness, background `#111827`, border `1px solid #334155`.
- Selected state: Background `#00B386`, border `#00B386`, displaying a solid `#0B0F14` check indicator.