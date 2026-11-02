---
name: Dibsly
description: A bright editorial freelance marketplace with private, comparable pitches.
colors:
  coral: "#c6402f"
  coral-dark: "#a83225"
  paper: "#f7f5ef"
  white: "#fffefa"
  ink: "#252b27"
  muted: "#62665f"
  peach: "#f5c9b8"
  lilac: "#e3def0"
  green: "#275c48"
  line: "#d9dbd1"
  sage: "#e9ecdf"
  tag: "#eeeee6"
typography:
  display:
    fontFamily: "Manrope, 'Segoe UI', sans-serif"
    fontSize: "clamp(4rem, 6.6vw, 6rem)"
    fontWeight: 750
    lineHeight: 1.02
    letterSpacing: "-.04em"
  headline:
    fontFamily: "Manrope, 'Segoe UI', sans-serif"
    fontSize: "clamp(1.8rem, 3vw, 2.8rem)"
    fontWeight: 750
    lineHeight: 1.15
    letterSpacing: "-.035em"
  title:
    fontSize: "1.35rem"
    fontWeight: 750
    lineHeight: 1.4
    letterSpacing: "-.025em"
  body:
    fontFamily: "Manrope, 'Segoe UI', sans-serif"
    fontSize: "1rem"
    fontWeight: 450
    lineHeight: 1.6
  label:
    fontSize: ".78rem"
    fontWeight: 700
    lineHeight: 1.6
rounded:
  tag: "5px"
  input: "7px"
  button: "8px"
  compact: "10px"
  panel: "12px"
  card: "14px"
  board: "18px"
spacing:
  inline: "12px"
  compact: "18px"
  grid: "22px"
  panel: "24px"
  card: "28px"
  gutter: "clamp(20px, 4vw, 64px)"
components:
  button-primary:
    backgroundColor: "{colors.coral}"
    textColor: "white"
    rounded: "{rounded.button}"
    padding: "13px 23px"
  button-primary-hover:
    backgroundColor: "{colors.coral-dark}"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    padding: "13px 23px"
  button-text:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    padding: "8px 0"
  input:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.input}"
    padding: "12px 13px"
  tag:
    backgroundColor: "{colors.tag}"
    textColor: "{colors.ink}"
    rounded: "{rounded.tag}"
    padding: "5px 9px"
  project-card:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "28px"
  navigation:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
---

# Design System: Dibsly

## Overview

**Creative North Star: "The Bright Editorial Job Board"**

Warm paper, confident Manrope type, and coral actions support readable freelance briefs. Lavender holds illustrative comparison; sage supports operational context. The user approved this code-led world without a verified catalog reference board.

**Key Characteristics:**
- Ivory surfaces and coral actions.
- Readable briefs and comparable terms.
- Flat cards, tonal panels, responsive stacking.

## Colors

### Primary
Coral marks action; deep coral is hover.

### Secondary
Lavender supports comparison; sage supports budget/search; green marks affirmative status; peach accents avatars/selection.

### Neutral
Paper is the page, warm white the cards, ink the content, muted gray the supporting copy, and soft line the dividers. Frontmatter owns exact values.

**The Action Coral Rule.** Use coral for action, focus, and selective emphasis.

## Typography

Self-hosted Manrope (200–800, swap), with Segoe UI/sans-serif fallback. Frontmatter records display, h2, card title, body, and label roles. Card copy is .85rem/1.8; buttons .9rem/750/1.4. Paragraphs cap at 72ch. Hero sizes change at 1100/760/380px to 5.3rem, clamp(3.7rem,12vw,5rem), and 3.7rem.

**The Comparable Terms Rule.** Use tabular numerals for quotes, budgets, and totals.

## Layout

Content caps at 1280px; header/footer at 1408px. Sections use 64px/88px padding. Landing/browse grids have two/three columns. At 1100px browse has two and comparisons one. At 760px layouts stack, gutters become 22px, sections 45px/60px, and navigation a labeled menu. At 380px gutters become 16px. Preserve word spacing across hidden line breaks and constrain native selects. Audit tables scroll locally.

## Elevation & Depth

Flat cards use thin borders. Board shadow: `0 18px 36px -28px #443a57`; selected sample: `0 6px 18px -12px #5e4e73`.

**The Quiet Surface Rule.** Reserve existing shadows for comparison-preview depth.

## Shapes

Frontmatter defines gently rounded controls and softer panels. Avatars are circular. SVG interface icons use 1.8 strokes and typically 21px boxes.

## Components

Buttons: 48px minimum height, 42px compact; .2s ease hover; secondary hover #ebece4; disabled opacity .55. Fields: 46px minimum, #b9c0b5 border, labels above. Focus: 3px coral outline, 4px offset. Tags are static; active filter tabs use ink. Cards align brief and budget; offers align quote/delivery/support. Navigation is 88px desktop, 74px mobile. Illustrative pitch selection uses aria-pressed and polite announcements. Reduced motion removes transitions/animation.

## Do's and Don'ts

### Do:
- **Do** preserve labels, focus, mobile word spacing, and explicit statuses.
- **Do** identify examples and preserve privacy in copy.

### Don't:
- **Don't** imply adoption, payment protection, or library integration.
- **Don't** add decorative eyebrows or glyph icons.
