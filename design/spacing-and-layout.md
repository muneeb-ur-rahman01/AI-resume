# Spacing and layout

- 4 px base scale (Tailwind default). Common steps: 8 (gap-2), 12 (gap-3), 16 (p-4), 20 (card padding p-5),
  24 (section gap space-y-6).
- Content width: `max-w-6xl` (1152 px) for app pages, `max-w-4xl` for job detail, `max-w-md` for auth cards.
- Gutters: 16 px (`px-4`) at all widths.
- Breakpoints (Tailwind): `sm` 640, `md` 768 (primary nav switches from the mobile scroller to the inline bar),
  `lg` 1024 (two- and three-column dashboards).
- Grids: dashboard `lg:grid-cols-3` (1 + 2); forms `md:grid-cols-2` or `md:grid-cols-3`.
- Header: sticky, 56 px; mobile adds a horizontally scrollable nav row.
- Touch targets: buttons are 40 px high (32 px for `size="sm"` in dense tables, which also have row padding).
- Tables scroll horizontally inside their card on small screens (`overflow-x-auto`).
