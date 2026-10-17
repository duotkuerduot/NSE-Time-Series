# Visual redesign of the web app

Status: applied, 17 October 2026 (decision D-42 in ENGINEERING.md). The redesign changes how the
app looks, not what it does. Routes, data fetching, the API contract, component logic and what
each page shows all stay as they were (ENGINEERING.md §15).

## 1. What we took from the reference

The owner likes the style of tihada.com. Only part of it could be read from the build
environment: the page's text and structure came through, but its stylesheets and images did not,
because the sandbox's browser was refused by its network policy. So the qualities below come from
the page's structure plus the owner's notes ("minimal", "cream, charcoal, deep blue"), not from
its exact styles.

1. **One idea per section, in a fixed rhythm.** Each section opens with a short label, then a
   large statement, then one short paragraph and its detail. The rhythm is predictable, so the
   page reads calmly however long it is.
2. **Big, confident type with room around it.** Headlines carry the message, and body copy stays
   short. Space, not decoration, separates one idea from the next.
3. **Numbers as display elements.** Key figures are set large, each with a one-line caption,
   and steps are numbered. The figure is the hero of its block.
4. **A restrained, high-contrast palette.** A dark mark sits on a light ground, with almost no
   colour besides. The calm comes from what is left out.
5. **Detail lives where it is needed.** Imagery is product views, not decoration. Fine detail
   sits close to the thing it explains rather than spread across the page.
6. **One primary action per view.** Secondary actions are plain text links.
7. **Plain, direct language** in short sentences.
8. **Almost no motion.** Nothing animates on scroll.

What we use here:
- the rhythm (1), as a small label above each title on the stock page and in the forecast panel;
- big, bold type and space (2) and large figures (3), for the current price and the forecast
  close;
- the restrained palette (4), with detail kept close to its subject (5);
- one primary action (6): the stock search on the homepage.

What we do not take: the logo, text, images, illustrations, icons or page layouts. Nor any
marketing pattern such as call-to-action buttons, carousels, stats bands or testimonial cards.
NSE Forecast shows the same content as before, in its own voice.

## 2. Palette

Cream, near-black and deep blue form the core palette. Each colour keeps one job, as in
ENGINEERING.md:

- **Deep blue (`--model`):** model output only (forecasts, ranges, model lines and bars). It is
  never a general accent, although it is also used for the focus ring.
- **Green and red:** only actual price changes, always next to ▲ or ▼ and a signed number.
- **Links and buttons:** `--ink`, with underline or weight.
- **`--rule`:** decorative dividers and chart gridlines only. Input borders use `--ink-2`.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#F6F1E7` cream | `#121110` warm black | Page background |
| `--surface` | `#ECE4D4` | `#1D1B18` | Strips: notices, table headers, the selected search result |
| `--ink` | `#141414` | `#F2EBDD` | Main text, the actual price line, primary buttons |
| `--ink-2` | `#4D483F` | `#B5AD9D` | Secondary text, input borders |
| `--model` | `#1B3A7A` deep blue | `#93B2FF` | Model output; focus ring |
| `--gain` | `#1E6B3A` | `#6FCB91` | Actual price rises |
| `--loss` | `#A3311D` | `#FF907B` | Actual price falls |
| `--rule` | `#9C9483` | `#6B6559` | Decorative dividers and gridlines |

### Measured contrast (WCAG 2.2)

Ratios use the WCAG relative-luminance formula, computed by script, not estimated. Text needs at
least 4.5:1 (AA). Focus rings, input borders and chart marks need at least 3:1.

| Foreground | On `--bg` (light) | On `--surface` (light) | On `--bg` (dark) | On `--surface` (dark) | Requirement | Result |
|---|---|---|---|---|---|---|
| `--ink` | 16.36 | 14.58 | 15.90 | 14.48 | 4.5 (text) | Pass |
| `--ink-2` | 8.06 | 7.18 | 8.47 | 7.71 | 4.5 (text), 3 (input border) | Pass |
| `--model` | 9.65 | 8.60 | 9.03 | 8.23 | 4.5 (text), 3 (focus ring, chart) | Pass |
| `--gain` | 5.79 | 5.16 | 9.54 | 8.70 | 4.5 (text) | Pass |
| `--loss` | 6.19 | 5.51 | 8.56 | 7.80 | 4.5 (text) | Pass |
| `--rule` | 2.67 | 2.38 | 3.26 | 2.97 | Decorative only | Never used for text or controls |

A primary button is `--bg` text on an `--ink` fill, at 16.36 in light and 15.90 in dark. axe
(WCAG 2.0, 2.1 and 2.2 AA rules) finds no serious or critical problems on any page, in either
mode, at 1440px and at 360px wide.

## 3. Typography

The owner chose this after reviewing the first style guide, which paired the Newsreader serif
with Inter:

- **Inter Tight ExtraBold** for headlines (page titles) and the two hero numbers: the current
  price and the forecast close.
- **Inter** for everything else, from section headings to body text, labels and tables.
- **Tabular numerals** for all figures, so prices line up in columns and do not shift as they
  change.

The font stacks are the owner's: `Inter, ui-sans-serif, system-ui, -apple-system,
BlinkMacSystemFont, "Segoe UI", sans-serif`, with `"Inter Tight"` in front of it for headlines.

| Role | Font | Size and line height (px) |
|---|---|---|
| Hero number (price, forecast close) | Inter Tight ExtraBold (800), tracking −0.02em | 56 / 60; 44 / 48 under 600px |
| Page title (h1) | Inter Tight ExtraBold (800), tracking −0.02em | 44 / 52; 34 / 40 under 600px |
| Section heading (h2) | Inter SemiBold (600) | 24 / 32; 22 / 28 under 600px |
| Subheading (h3) | Inter SemiBold | 18 / 28 |
| Body | Inter Regular (400) | 16 / 24 |
| Small and meta text, tables | Inter Regular | 14 / 20 |
| Label (uppercase, tracking 0.08em) | Inter SemiBold | 12 / 16 |

Spacing follows a 4px grid (4, 8, 12, 16, 24, 32, 48, 64, 96), and every line height is a
multiple of 4. Text columns stay under 72 characters.

### Font files and licences

There are three self-hosted woff2 files: two families, latin subset, 71 KB in total. They are
vendored from Fontsource into `web/src/assets/fonts/` and bundled into `web_dist`. Nothing loads
from a CDN, so the app works offline.

| File | Family and weight | Source | Licence |
|---|---|---|---|
| `inter-latin-400-normal.woff2` | Inter Regular | `@fontsource/inter` 5.3.0 | SIL Open Font License 1.1 (`OFL-Inter.txt`) |
| `inter-latin-600-normal.woff2` | Inter SemiBold | `@fontsource/inter` 5.3.0 | SIL Open Font License 1.1 |
| `inter-tight-latin-800-normal.woff2` | Inter Tight ExtraBold | `@fontsource/inter-tight` 5.3.0 | SIL Open Font License 1.1 (`OFL-InterTight.txt`) |

Both families provide tabular figures (`tnum`), checked in the files themselves. The copyright
and licence notices are both in the licence files next to the fonts and in each font's own
metadata. Git treats `*.woff2` as binary (`.gitattributes`).

## 4. Layout, detail and motion

- **Page:** the content is at most 1120px wide, with a 16px gutter on phones and 32px from 900px
  up.
- **Sections:** separated by vertical space (48px, or 64px on wide screens) and one thin
  `--rule` line, not boxes. There are no cards and no shadows. `--surface` is used only for
  strips: notices, table headers and the selected search result.
- **Controls:**
  - Buttons are pill-shaped and at least 44px tall. The primary button is `--ink` with `--bg`
    text; a secondary button is an `--ink-2` outline.
  - The search field is a 56px pill. Its text is 16px, so phones do not zoom into it.
  - Links are `--ink`, underlined, and the underline thickens on hover.
- **Touch targets:** at least 44 × 44px for buttons, the search field and its results, the
  wordmark, gate-detail toggles, contact links, standalone footer links and tickers in tables.
  Ticker links get their size without making the rows taller.
- **Focus:** a 2px `--model` ring with a 2px offset on every focusable element.
- **Wide tables:** the backtest table and the gate table scroll sideways on small screens,
  inside a labelled region that the keyboard can reach. No page scrolls sideways at 360px.
- **Charts:**
  - The actual price is a 2px `--ink` line. The forecast point and range are `--model`, and the
    range band is a light wash of it.
  - Markers for moves left out of modelling are `--ink-2`, because red is reserved for price
    falls.
  - Gridlines and axes are hairline `--rule`, and axis text is 12px `--ink-2`.
  - Bars are `--model`, at most 24px wide, with 4px rounded ends at the value and square at the
    zero line.
  - Each chart keeps its text summary, and the two-line chart keeps its legend.
- **Motion:** 150ms opacity, underline-colour, border-colour or 1px transform changes, only in
  response to hover, focus or press. All of it is turned off under `prefers-reduced-motion`.
- **Dark mode:** follows `prefers-color-scheme`, with its own measured values rather than an
  automatic inversion.

## 5. Before and after

**Homepage.**
- *Before:* system font at 15px on white with a green-grey palette. The small search label
  doubled as the h1, and the market summary was one dense line.
- *After:*
  - The same content and order on cream. "Find an NSE stock" is an Inter Tight ExtraBold
    headline above a 56px pill search field, the one primary action, with generous space
    around it.
  - The market summary is spaced into four groups (NASI, NSE 20, breadth, turnover).
  - The movers tables have hairline rows and full-size ticker targets. The NASI chart and the
    track record use the new chart style, and sections are separated by space and thin rules.

**Stock page.**
- *Before:* a small h1, the ticker and sector line below it, the price at 34px in the system
  font, and the forecast in blue body text below the chart.
- *After:*
  - The ticker and sector sit as a label above the company name, which is the headline.
  - The current price is a large Inter Tight ExtraBold figure, with its change (▲/▼, in the
    gain or loss colour) beside it.
  - On wide screens the price chart and the forecast sit side by side. The forecast close is
    the second large figure, in deep blue, under a "Model forecast for…" label, with the 80%
    range, the backtest sentence and "Research forecast, not investment advice." beneath it.
  - The backtest table has a `--surface` header strip and tabular figures, and scrolls sideways
    on phones.

**About page.**
- *Before:* one long column of system-font text, with the gate table and a small bar chart.
- *After:*
  - The same text, under an Inter Tight ExtraBold title, with the introduction as a lead
    paragraph.
  - The results section keeps its headline sentence, the gate table (header strip, tabular
    figures, scrolls on phones), the gate details as tidy toggles and the skill-by-year bars
    in deep blue.
  - "What the numbers mean", "Method", "Limitations", "Data" and "Contact" are now separate
    sections divided by space and rules. Contact links are full-size targets.

**Not-found page.** The title is a headline, and the link home is a secondary pill button.

## 6. How it was checked

- **vitest:** 34 tests pass, including the banned-word language test and the page tests.
- **Playwright and axe:**
  - The smoke test passes against the contract fixtures at mobile and desktop sizes.
  - The end-to-end test passes against `nsefc serve` after `uv run nsefc run --sample`.
- **Contract:** the contract check and the fixture validation pass.
- **Build:** `web-hash --check` passes. JavaScript is 99 KB gzipped, against a 150 KB budget.
- **Manual look:** every page was checked in light and dark mode with the sample data and the
  real data, at 1280px and 360px wide.

## 7. Notes

- **Styling approach:** the brief mentions uPlot and CSS Modules. This app uses its own small
  SVG charts (`LineChart`, `BarChart`) and global CSS, with tokens in
  `web/src/styles/tokens.css` and styles in `web/src/styles/base.css`. The stack stayed as it
  was; only the styling changed.
- **Markup changes (presentation only):**
  - class names, and two wrappers: the side-by-side grid on the stock page and the scroll
    region around wide tables;
  - the stock page's ticker line moved above the name;
  - the forecast title is now an h3 inside the "Forecast" section (it was a second h2);
  - the About page's single long section was split into one section per topic.
- **Style guide:** the temporary `/styleguide` route was removed once the style was applied.
