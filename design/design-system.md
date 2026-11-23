# Design system

CareerPilot should feel like a trustworthy professional tool: calm, legible, explicit about what AI did and what
the user controls.

- **Tokens:** [color-tokens.json](color-tokens.json), implemented in `apps/web/src/app/globals.css` (`@theme`).
- **Typography:** [typography.md](typography.md). **Layout:** [spacing-and-layout.md](spacing-and-layout.md).
- **Components:** [component-inventory.md](component-inventory.md), implemented in `apps/web/src/components/`.
- **Accessibility:** [accessibility-guidelines.md](accessibility-guidelines.md).
- **Flows:** [user-flows.md](user-flows.md). **Wireframes:** [wireframes/](wireframes/). **Screens:** [screens/](screens/).
- **Decisions:** [design-decisions.md](design-decisions.md). **Brand:** [brand-guidelines.md](brand-guidelines.md).

## Principles

1. **Show provenance.** Every AI-derived item shows its source ("Stated in resume", source quote, confidence) or
   a mock-provider label.
2. **User control before action.** Review, then confirm. Destructive or outward-facing actions use a
   `ConfirmDialog` that states what will happen.
3. **Honest numbers.** Relevance is shown as `NN/100` with "not a hiring prediction" copy; missing skills are
   phrased as "not in your confirmed profile".
4. **Every state designed.** Loading (skeletons), empty (EmptyState with a next step), error (ErrorState with
   retry), permission-denied (warning alert), success (toast).
5. **Restraint.** Neutral backgrounds, one accent color, subtle borders, no gradients or decorative motion.

## Figma

No Figma file was created. To recreate the system in Figma: import `color-tokens.json` with a tokens plugin
(for example Tokens Studio), create text styles from typography.md, and build the components listed in
component-inventory.md with the documented sizes and states.
