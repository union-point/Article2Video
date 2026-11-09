# Storyboard templates and Stage 8 rendering

See the project README for unattended generation and source contracts.

`npm ci`, then `npm run dev -- --no-open` opens the GPT‑6.1 article storyboard.
`public/storyboard.json` is staged from the isolated GPT‑6.1 run. Synthetic
six-template fixtures live only under `tests/fixtures/`. To preview a generated article storyboard:

```sh
npm run prepare-storyboard -- ../runs/20261108-224733-gpt61-stages2-4/output/storyboard.json
npm run dev -- --no-open
```

The Python generator checks content checkpoints and source/timing provenance. The preview
staging script checks Zod and stages sentence captions from the neighboring
`timings.json`; it cannot approve an edited manifest. Template
instances intentionally come from one data-driven timeline. Edit production copy
upstream and regenerate rather than making independent Studio source edits.

Use `npm test`, `npm run lint`, and `npm run build` to validate this package.
The Python storyboard/render tests also need this Node installation.

Stage 8 adds one continuous `@remotion/media` narration track at frame zero.
The composition displays Stage 6 sentence timings in a persistent caption bar
and tracks each scene in a segmented progress bar.
The Python `render` command checks approvals, source evidence, diagram excerpts,
and timing before invoking `scripts/render.mjs`. The worker bundles isolated
assets and passes the same manifest/audio props to metadata selection and export;
it never changes the Studio manifest. Studio's default visual-only preview remains
available; use `render --preview` for a 960×540 MP4 with narration. See the root
README for unattended URL-to-MP4 commands and the 1920×1080 export.
