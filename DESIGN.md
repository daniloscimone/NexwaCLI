---
name: NexwaCLI terminal design
description: Nexwa customer dashboard using the website identity and the user's terminal.
colors:
  brand: "#6800de"
  accent: "#b98aff"
  success: "#86d7a1"
  warning: "#edc575"
  danger: "#ffa1ae"
components:
  wordmark:
    backgroundColor: "{colors.brand}"
  screen-heading:
    textColor: "{colors.accent}"
  navigation-key:
    textColor: "{colors.accent}"
  feedback-success:
    textColor: "{colors.success}"
  feedback-warning:
    textColor: "{colors.warning}"
  feedback-error:
    textColor: "{colors.danger}"
---

# Design System: NexwaCLI

## Overview

The customer panel inherits the Nexwa website identity. It is a practical terminal dashboard with direct, concise copy, compact screens and ordinary line input. Preserve this incumbent system when adding screens.

Use the terminal's background rather than painting an assumed light or dark canvas. Nexwa purple identifies the wordmark; lighter purple makes headings and navigation keys readable in dark terminals. Information and actions remain understandable with color disabled.

**Key Characteristics:**

- Nexwa website colors on the user's terminal background.
- One compact header, a horizontal rule and a vertical content flow.
- Numbered choices, explicit prompts and written status feedback.
- English by default, with six selectable interface languages.

## Colors

The frontmatter records the exact palette from `TOKENS` in `nexwacli/panel.py`; Python remains the runtime source of truth.

### Primary

- **Nexwa purple (`brand`):** Wordmark background only.
- **Light purple (`accent`):** Screen titles, horizontal rules, navigation keys, service titles and request identifiers. The first home action has a bold key when color is available.

### Status

- **Soft green (`success`):** Connected and accepted feedback, receipt rows with confirmed responses, and wallet balance output.
- **Warm amber (`warning`):** Disconnected or unavailable states, unconfirmed outcomes, confirmations and recovery guidance.
- **Soft rose (`danger`):** Errors and failed status responses.

### Neutral

Body text and the screen background inherit the terminal's foreground and background. The wordmark requests ANSI bright-white text (`97`); the terminal controls its exact appearance. There is no fixed neutral palette.

Color is optional. Honor `NO_COLOR`, `TERM=dumb`, redirected output and the saved color preference. Windows enables virtual terminal output when available. If the terminal cannot support it, render plain text. Selecting Enabled still respects these capability and environment checks. Pair status colors with meaningful text.

## Typography

The application uses the terminal's font, size, line spacing and glyph rendering. It does not select a font family or define a pixel type scale.

- **Wordmark:** Uppercase ` NEXWA `, bold with bright-white text on the brand background when color is enabled; the CLI version follows on the same line.
- **Screen title:** One line of accent text below the rule; long titles wrap through the ordinary text renderer.
- **Body and labels:** Terminal foreground, sentence case, with blank lines separating groups.
- **Navigation keys:** Bracketed values such as `[1]`, colored with the accent. Primary keys can be bold; labels stay in the terminal foreground.

The interactive UI defaults to English. Settings offers English (`en`), Italian (`it`), French (`fr`), German (`de`), Spanish (`es`) and Russian (`ru`). Keep translated labels readable within the same hierarchy. Command syntax, JSON field names and API content remain stable; service content and server messages retain their returned language.

## Layout

Use one compact header and one horizontal rule per screen. Render content in a single vertical column with a two-space left inset. The wrapping width is `max(16, min(104, terminal_columns - 4))`; terminal detection falls back to 88 columns. Blank lines separate the title, content, navigation and input prompt.

Home places wallet credit and connection status above local receipt counts and direct numbered navigation. Balance is fetched on entry when its cached value is older than 60 seconds. New order is the first action (`[1]`); available credit also has a direct choice (`[4]`). This preserves the founder's balance and new-order priorities.

The catalog is paged at six services per page. Each service uses stacked title and metadata lines at every width; it does not switch to a wide table. Local receipt lists use five entries per page. Ordinary text, long URLs and purchase-review values wrap instead of being silently truncated.

The generic text renderer wraps by Python string length rather than terminal display-cell measurement. Navigation choices and input prompts are printed directly and do not use that wrapper. Do not assume arbitrary strings will fit a narrow terminal; keep choices concise and review translated output.

## Elevation & Depth

The interface is flat. Hierarchy comes from order, whitespace, the accent rule, the wordmark background and written state feedback. There are no shadows, floating surfaces or animated transitions. Color-capable screens clear and redraw the main terminal; plain output remains sequential. The application does not use an alternate-screen buffer.

## Shapes

The recurring shapes are the rectangular wordmark, a single horizontal rule and bracketed navigation keys. Unicode rules use `─`; incompatible output encodings use ASCII `-`. There are no rounded containers, boxed cards or pixel-based corner tokens.

## Components

### Header

A compact identity marker precedes every screen: wordmark and version, one accent rule spanning the wrapping width, then the translated screen title. Keep the surrounding blank lines and two-space inset.

### Navigation

Actions use numbered choices and ordinary line input. Home uses `[1]` through `[7]` plus `[0]` to exit. Subscreens expose a return choice, and paginated lists print their `n` / `p` commands. No mouse or hidden key bindings are required. There are no application hover or focus styles; the terminal handles text entry.

### Input and confirmation

Prompts start on a new line with the two-space inset and a colon. Customer-key entry is hidden. The confirmation question uses warning text and an explicit translated confirmation prompt; Enter cancels. Purchases display service, target URL, quantity and pricing guidance before confirmation. Refill requests also require confirmation.

Pause prompts return to the calling flow when Enter is pressed. Enter at catalog or receipt navigation returns to the dashboard. Ctrl+C exits. Preserve explicit prompts rather than assuming one Enter behavior everywhere.

### Service rows and details

Catalog rows use accent service identifiers and names, followed by platform, rate and quantity bounds. Details show labeled metadata and pricing guidance, then a direct new-order choice. Keep full service details available before ordering.

### Feedback and receipts

Use short written success, warning and error messages alongside their optional status color. Receipts show the order ID, charged amount when available and original request key. Local receipt counts and lists must be labeled as local records; live delivery status comes from the status action. Retain recovery guidance for unknown purchase outcomes.

### Settings

Settings uses the same numbered navigation for language, color preference and saved-key removal. Language names appear in their native forms. Color choices are Automatic, Enabled and Plain text in the selected language. Applying settings reconfigures the next screen without changing the terminal background.

## Do's and Don'ts

### Do:

- **Do** preserve the Nexwa palette and the terminal's own foreground and background.
- **Do** keep wallet credit and the first new-order action easy to find.
- **Do** pair status color with text and preserve usable plain-text output.
- **Do** wrap purchase-review values and check longer translated labels.
- **Do** document terminal behavior in cells, lines and input commands when those are the actual units.

### Don't:

- **Don't** introduce an assumed light or dark canvas, web typography or invented CSS tokens.
- **Don't** add invented customer metrics, simulated wallet balances or decorative charts to the real dashboard.
- **Don't** silently truncate purchase details or imply local receipts are complete account history.
- **Don't** replace explicit confirmations with an immediate purchase or refill action.
