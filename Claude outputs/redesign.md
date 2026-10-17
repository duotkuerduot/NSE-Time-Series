# Visual redesign of the web app

Status: proposal for review (17 October 2026). The style guide at `/styleguide` shows it. Nothing
on the pages changes until the owner approves it. This redesign changes how the app looks, not
what it does: routes, data fetching, the API contract, component logic and what each page shows
stay as they are (ENGINEERING.md §15).

## 1. What we took from the reference

The owner likes the style of tihada.com. It could only be read in part from the build
environment. The page's text and structure came through, but its stylesheets and images did not:
the sandbox's browser was refused by its network policy. So the qualities below come from the
page's structure plus the owner's notes ("minimal", "cream, charcoal, deep blue"), not from its
exact styles.

1. **One idea per section, in a fixed rhythm.** Each section opens with a short label, then a
   large statement, then one short paragraph and its detail. The rhythm is predictable, so the
   page reads calmly however long it is.
2. **Big type with room around it.** Headlines carry the message, and body copy stays short.
   Space, not decoration, separates one idea from the next.
3. **Numbers as display elements.** Key figures are set large, each with a one-line caption,
   and steps are numbered. The figure is the hero of its block.
4. **A restrained, high-contrast palette.** A dark mark sits on a light ground, with almost no
   colour besides. The calm comes from what is left out.
5. **Detail lives where it is needed.** Imagery is product views, not decoration. Fine detail
   sits close to the thing it explains rather than spread across the page.
6. **One primary action per view.** Secondary actions are plain text links.
7. **Plain, direct language** in short sentences.
8. **Almost no motion.** Nothing animates on scroll.

What we use here: the rhythm (1), big type and space (2), and large figures (3), for the current
price and the forecast close. Also the restrained palette (4), detail kept close to its subject
(5) and one primary action (6): the stock search on the homepage.

What we do not take: the logo, text, images, illustrations, icons or page layouts. Nor any
marketing pattern such as call-to-action buttons, carousels, stats bands or testimonial cards.
NSE Forecast shows the same content as before, in its own typographic voice.

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

A primary button is `--bg` text on an `--ink` fill, at 16.36 in light and 15.90 in dark.

## 3. Typography

The pairing is editorial: a serif for page titles and the two hero numbers (the current price
and the forecast close), and a clean sans for everything else. All figures use tabular numerals,
so prices line up in columns and do not shift as they change.

| Role | Font | Size and line height (px) |
|---|---|---|
| Hero number (price, forecast close) | Newsreader Medium | 56 / 60; 44 / 48 under 600px |
| Page title (h1) | Newsreader Medium | 44 / 52; 34 / 40 under 600px |
| Section heading (h2) | Inter SemiBold | 24 / 32 |
| Subheading (h3) | Inter SemiBold | 18 / 28 |
| Body | Inter Regular | 16 / 24 |
| Small and meta text, tables | Inter Regular | 14 / 20 |
| Label (small capitals style) | Inter SemiBold, uppercase, tracking 0.08em | 12 / 16 |

Spacing follows a 4px grid (4, 8, 12, 16, 24, 32, 48, 64, 96), and every line height is a
multiple of 4. Text columns stay under 72 characters.

### Font files and licences

There are three self-hosted woff2 files: two families, latin subset, about 70 KB in total. They
are vendored from Fontsource into `web/src/assets/fonts/` and bundled into `web_dist`. Nothing
loads from a CDN, so the app works offline.

| File | Family and weight | Source | Licence |
|---|---|---|---|
| `inter-latin-400-normal.woff2` | Inter Regular | `@fontsource/inter` 5.3.0 | SIL Open Font License 1.1 (`OFL-Inter.txt`) |
| `inter-latin-600-normal.woff2` | Inter SemiBold | `@fontsource/inter` 5.3.0 | SIL Open Font License 1.1 |
| `newsreader-latin-500-normal.woff2` | Newsreader Medium | `@fontsource/newsreader` 5.3.0 | SIL Open Font License 1.1 (`OFL-Newsreader.txt`) |

Both families provide tabular figures (`tnum`), checked in the files themselves. The copyright
and licence notices are both in the licence files next to the fonts and in each font's own
metadata.

## 4. Layout, detail and motion

- **Page:** the content is at most 1120px wide, with a 16px gutter on phones. It is a single
  column, apart from two-column pairs on wide screens that already exist today, such as gainers
  and losers.
- **Sections:** separated by vertical space and one thin `--rule` line, not boxes. There are no
  cards and no shadows. `--surface` is used only for strips: notices, table headers and the
  selected search result.
- **Controls:**
  - Buttons and the search field are at least 44px tall and pill-shaped.
  - The primary button is `--ink` with `--bg` text. A secondary button is an `--ink-2` outline.
  - Links are `--ink` and underlined.
- **Focus:** a 2px `--model` ring with a 2px offset on every focusable element.
- **Charts:**
  - The actual price is a 2px `--ink` line, and the forecast point and range are `--model`.
  - Gridlines and axes are hairline `--rule`, and axis text is `--ink-2` at 12px with tabular
    figures.
  - Each chart keeps its text summary, and two-line charts keep their legend.
- **Motion:** 150ms opacity, colour or 1px transform changes, only in response to hover, focus
  or press. All of it is turned off under `prefers-reduced-motion`.
- **Dark mode:** follows `prefers-color-scheme`, with its own tested values rather than an
  automatic inversion.

## 5. Before and after

**Homepage.**
- *Before:* system font at 15px on white with a green-grey palette. The search label, set as
  the h1, is small, and the market summary, movers, NASI chart, breadth and track record follow
  in thin-ruled sections.
- *After:* the same content and order on cream. "Find an NSE stock" is set as a serif page
  title above a large pill search field, the one primary action. Sections get more space, Inter
  section headings, and the index chart and track record in the new chart style. Movers tables
  get `--surface` header strips.

**Stock page.**
- *Before:* a small h1, the price at 34px in the system font, and the forecast in blue body
  text.
- *After:*
  - The company name is a serif title, with ticker and sector as a label line.
  - The current price is a serif hero number, with its change (▲/▼, gain or loss colour) beside
    it.
  - The forecast close is the second hero number, in deep blue, under a "Model forecast for…"
    label, with the 80% range and the backtest sentence beneath it.
  - "Research forecast, not investment advice." stays with the forecast.
  - The backtest table gets tabular figures and a `--surface` header strip.

**About page.**
- *Before:* one long column of system-font text, the gate table and a small bar chart.
- *After:* the same text with a serif title, Inter headings and a comfortable measure. The
  results headline is set as a lead paragraph, and the gate table is set in tabular figures.
  The skill-by-year bars are deep blue, at most 24px wide, with 4px rounded ends. Method and
  limitations get clear numbered lists, and the sections are separated by space and rules.

## 6. Notes

- **Styling approach:** the brief mentions uPlot and CSS Modules. This app uses its own small
  SVG charts (`LineChart`, `BarChart`) and global CSS with tokens in
  `web/src/styles/tokens.css`. The stack stays as it is; only the styling changes.
- **Temporary scoping:** the light and dark token sets can also be scoped with the
  `.theme-light` and `.theme-dark` classes. Only the style guide uses them, to show both modes
  side by side, and they are removed with it.
