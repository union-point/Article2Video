# Stage 7 template library

See the project README for generation, review, and source contracts.

`npm ci`, then `npm run dev -- --no-open` opens the GPT‑6.1 article storyboard.
`public/storyboard.json` is staged from the isolated GPT‑6.1 run. Synthetic
six-template fixtures live only under `tests/fixtures/`. To preview a generated article storyboard:

```sh
npm run prepare-storyboard -- ../runs/20261108-224733-gpt61-stages2-4/output/storyboard.json
npm run dev -- --no-open
```

The Python generator checks approvals and source/timing provenance. The preview
staging script checks only Zod; it cannot approve an edited manifest. Template
instances intentionally come from one data-driven timeline. Edit production copy
upstream and regenerate rather than making independent Studio source edits.

Use `npm test`, `npm run lint`, and `npm run build` to validate this package.
The Python Stage 7 tests also need this Node installation. Audio/export is Stage 8.
