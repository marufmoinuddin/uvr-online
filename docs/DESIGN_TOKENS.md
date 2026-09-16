# Design tokens

Extracted verbatim from `uvrvocalremover.com` and implemented as CSS variables
in `web/src/styles/globals.css`, mapped into Tailwind in
`web/tailwind.config.ts`.

## Color palette

Light tokens live on `:root`; dark tokens on `.dark` (class strategy, so the
theme toggle works alongside `prefers-color-scheme`).

| Token | Light | Dark |
|-------|-------|------|
| `--bg` | `255 255 255` | `8 9 10` (#08090A) |
| `--fg` | `15 15 15` | `255 255 255` |
| `--muted` | `113 113 113` | `113 113 113` |
| `--muted-fg` | `113 113 113` | `161 161 170` |
| `--border` | `226 226 226` | `255 255 255 / 0.05` |
| `--primary` | `99 102 241` (indigo-600) | `165 180 252` (indigo-300) |
| `--primary-fg` | `255 255 255` | `15 15 15` |
| `--primary-hover` | `79 70 229` | `199 210 254` |
| `--primary-glow` | `99 102 241 / 0.65` | `99 102 241 / 0.8` |
| `--card` | `255 255 255` | `255 255 255 / 0.03` |
| `--card-border` | `226 226 226` | `255 255 255 / 0.08` |
| `--control-bg` | `244 244 245` | `255 255 255 / 0.05` |
| `--control-border` | `228 228 231` | `255 255 255 / 0.1` |
| `--glass-bg` | `255 255 255 / 0.7` | `255 255 255 / 0.06` |
| `--glass-border` | `255 255 255 / 0.2` | `255 255 255 / 0.12` |

## Spacing & sizing

`--space-1` (4px) … `--space-16` (64px); `--container-max` 88rem; `--container-narrow` 80rem.

## Radius

`sm` 0.25rem · `md` 0.375rem · `lg` 0.5rem · `xl` 0.75rem · `2xl` 1rem · `full` 9999px.

## Shadows

- `--shadow-xs` `0 1px 2px 0 rgb(0 0 0 / 0.05)`
- `--shadow-md` `0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)`
- `--shadow-lg` `0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)`
- `--shadow-primary-glow` `0 10px 30px -16px rgb(var(--primary) / 0.65)`
- `--shadow-primary-glow-dark` `0 10px 30px -12px rgb(var(--primary) / 0.8)`

## Typography

`--font-sans: 'Inter', system-ui, sans-serif` · `--font-mono: 'JetBrains Mono', monospace`.
Sizes `xs`…`4xl` with `leading-tight/snug/normal/relaxed`.

## Animations

`slide-up`, `scale-in`, `fade-in`, `accordion-down/up`, `pulse`, `marquee`.
Staggered entrance via `animation-delay-100…500`. `prefers-reduced-motion`
disables everything except `fade-in`.

## Signature effects

- **`.glass-card`** — `backdrop-filter: blur(12px)` + 1px `--glass-border`
- **`.u-noise-overlay`** — inline SVG `feTurbulence` at 3% opacity
- **`.u-bg-gradient`** — double radial (indigo top-center, purple bottom-right);
  dark adds a rose glow
- **`.btn-primary-glow`** — indigo box-shadow that intensifies in dark mode