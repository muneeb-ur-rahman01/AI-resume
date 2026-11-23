# Accessibility guidelines (target: WCAG 2.2 AA)

Implemented:

- Semantic landmarks (`header`, `nav` with labels, `main#main`, `footer`), one H1 per page, and a skip link.
- Every control has a programmatic label (`Field` component or `aria-label` for icon buttons).
- Errors are tied to inputs with `aria-describedby` and announced with `role="alert"`; `aria-invalid` is set.
- Visible 3 px focus outline on all focusable elements (`:focus-visible`).
- Status is never conveyed by color alone: badges have text, the match meter has a numeric label, and checklist
  icons have screen-reader text.
- Dialogs use native `<dialog>` with `showModal()` (focus containment, Esc to close, labelled by the title).
- Live regions: toasts (`aria-live=polite`), loading blocks (`role=status`), job search results.
- Reduced motion respected (`prefers-reduced-motion`).
- Text contrast meets 4.5:1 or better (see color-tokens.json); interactive borders meet 3:1.
- Tables have captions (visually hidden) and header cells.

To verify before release (not yet done): automated axe scans in Playwright, manual screen-reader passes (NVDA +
Firefox, VoiceOver + Safari), 200%/400% zoom and reflow at 320 px, and keyboard-only completion of the e2e journey.
