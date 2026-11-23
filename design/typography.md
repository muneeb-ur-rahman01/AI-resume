# Typography

Font stack: Inter if installed, otherwise the system UI font (no web font is downloaded, which keeps CSP strict
and pages fast).

| Style | Tailwind | Size / line height | Weight | Use |
| --- | --- | --- | --- | --- |
| Display | `text-4xl md:text-5xl` | 36-48 / 1.1 | 600 | Landing hero only |
| H1 | `text-2xl` | 24 / 32 | 600 | Page titles (`PageHeader`) |
| H2 | `font-semibold` (16) | 16 / 24 | 600 | Card titles |
| Body | `text-sm` | 14 / 20 | 400 | Default UI text |
| Body large | `text-lg` | 18 / 28 | 400 | Landing intro |
| Caption | `text-xs` | 12 / 16 | 400-500 | Hints, metadata, badges |

Use sentence case everywhere. Numbers that matter (scores, counts) use `font-semibold`.
