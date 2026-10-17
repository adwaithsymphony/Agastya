# Design system

Tokens live in `frontend/src/index.css` (`@theme`). Components live in `frontend/src/components/ui.tsx` and `domain.tsx`.

## Colour
| Token | Hex | Use |
|---|---|---|
| forest | #254B38 | primary actions, selected text, confirmed states |
| forest-deep | #19382A | sidebar, hero |
| sage / sage-pale | #8FA58B / #E6EDE2 | highlights, selected surfaces, "eligible under recorded rules" |
| cream / paper | #F5F1E7 / #FBF9F4 | canvas / panels |
| beige, earth | #E8DDC9, #806B49 | secondary surfaces, facts |
| charcoal, muted | #29342D, #727970 | text |
| danger / amber / water | #A3402B / #A8701A / #3B6A85 | restricted & errors / needs verification & warnings / informational |

Status colours carry meaning only. "Eligible" is shown in sage without a checkmark because it reflects recorded rules, not a safety guarantee; "needs verification" uses amber with a question icon.

## Type
Manrope throughout. Page title 24px/700; panel title 15px/700; body 15px; labels 13px/600; metadata 12px; metrics 26px/700 tabular figures. Landing headline 60px/800, tight tracking.

## Shape and depth
Radii 6 / 10 / 14px (inputs / panels / dialogs); buttons are fully rounded. One soft shadow for raised elements and one lift shadow for primary buttons, menus and dialogs.

## Components
Button (primary, secondary, ghost, danger, quiet), Badge / StatusBadge, Panel, PageHeader, Metric, Field + Input/Select/Textarea, FormError, Dialog / ConfirmDialog (focus-trapped, Esc closes), Toasts, Tabs, Table, Help tooltip, Loading / ErrorState / EmptyState, HarvestStrip, PredictionPanel, ConfidenceBar, UrgencyBadge.

## Layout
Desktop: 248px forest sidebar, sticky header with section, notifications and account. Mobile: drawer navigation. Content max 1240px. Operational records use tables, the crop history a timeline, pollination a 90-day calendar, rerouting a ranked list with score breakdowns.

## Rules
Sentence case, plain verbs, buttons name the action ("Confirm destination"). No decorative gradients, glow, or emoji. Motion only for the hero entrance, dialogs and toasts; `prefers-reduced-motion` respected. Logo: `public/assets/agastya-logo.svg` replaces the neutral placeholder automatically.
