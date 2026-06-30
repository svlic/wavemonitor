# Stock Data Monitor Design System

## Product intent
Stock Data Monitor is a local configuration console for monitoring stock and crypto instruments, runtime readiness, and Telegram alert availability. Todo 1 ships only the shell needed to prove the frontend can load and show recoverable API errors.

## Visual principles
- Clear operational status over decoration.
- Calm, high-contrast surfaces suitable for a monitoring console.
- No trading, portfolio, auth, charting, or exchange-account UI in the scaffold.

## Tokens
- Colors: `--color-bg #0f172a`, `--color-panel #111827`, `--color-text #e5e7eb`, `--color-muted #94a3b8`, `--color-accent #38bdf8`, `--color-danger #f87171`, `--color-border #1f2937`.
- Typography: system sans-serif stack, base 16px, headings 1.5rem/1.875rem.
- Spacing: 0.5rem, 1rem, 1.5rem, 2rem scale.
- Radius: 0.75rem cards, 0.5rem controls.

## Components
- App shell: centered max-width panel with heading, summary text, and status regions.
- Status card: bordered panel for backend/runtime state.
- Alert/error text: explicit recoverable copy, never raw stack traces or secrets.

## Accessibility
- Semantic headings and status regions.
- Text contrast must remain readable on dark backgrounds.
- Error states use text labels, not color alone.

## Motion
No motion in the Todo 1 scaffold.

## Implementation notes
Frontend source must consume these tokens through CSS custom properties. SVG icons only if icons are later required; no emoji icons.
