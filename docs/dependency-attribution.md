# Dependencies and model attribution

## Interface typography

Manrope is bundled locally as a variable font (weights 200–800), under the SIL Open Font License 1.1. Source: [Google Fonts Manrope distribution](https://github.com/google/fonts/tree/main/ofl/manrope). The copyright and full license are preserved in `frontend/src/assets/fonts/OFL-Manrope.txt`. Technical code and identifiers retain the system monospace font.

## Agent lab additions

React/React DOM (MIT), Vite (MIT), TypeScript (Apache-2.0), Lucide React (ISC), Playwright (Apache-2.0), SQLAlchemy (MIT), Alembic (MIT), and Hypothesis (MPL-2.0) retain their own licenses. Preserve distribution notices.

No NVIDIA model is bundled. Initial live evaluations used `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` through Nebius Token Factory. Verify its model-card license and provider terms before public release. MIT licensing of our code does not relicense model weights.

The notes below include retained dependencies of the historical robotics prototype.

Skylark's original application code is MIT licensed. Dependencies retain their own
licenses. The table below records metadata from the installed versions in
`requirements.lock.txt`; distribution packages include their license texts.

| Package | Version verified | License | Role |
|---|---|---|---|
| FastAPI | 0.143.3 | MIT | Local data/review HTTP API |
| Starlette | 1.8.0 | BSD-3-Clause | FastAPI HTTP implementation and test client |
| Uvicorn | 0.54.0 | BSD-3-Clause | Local ASGI server |
| Pydantic | 2.14.1 | MIT | Strict data contracts and JSON validation |
| Pillow | 12.3.0 | MIT-CMU | Image decoding, rotation, resizing, and fixture creation |
| OpenAI Python client | 2.54.0 | Apache-2.0 | Compatible client for the Nebius endpoint |
| python-multipart | 0.0.32 | Apache-2.0 | Reserved for the planned upload API |
| pytest | 9.1.1 | MIT | Automated verification |
| HTTPX | 0.28.1 | BSD-3-Clause | HTTP client and mocked transport tests |

Transitive dependencies are pinned in the lock file and retain the licenses
shipped in their distributions. No dependency source is copied into this repository.

The OpenAI SDK is a transport client here; live inference is directed to the
fixed Nebius Token Factory endpoint. No OpenAI-hosted model is called by Skylark.
The selected model's exact catalog identifier is `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`.
Record its model-card/license URL, endpoint, pricing verification date, and actual
contribution in the benchmark report. Do not imply
that the SDK author or NVIDIA has validated the output.

The supplied geometric fixtures are original software-test assets. They are not
photographs, generated model output, robot simulations, or evidence of detection
performance. Real photographs remain subject to their owners' permissions. Model
weights, model outputs, and third-party datasets are not covered by Skylark's MIT
license.

## Supplied landing component

The landing page adapts the TypingKeyboard React component supplied by the user. Its upstream author and license were not included; confirm redistribution permission before public release. Adaptations remove HTML injection, clean up animation timers, respect reduced motion, and integrate local routing and styling.

## RailSetu landing sections

The slideshow, FAQ accordion, and split-flap creator credit are adapted with the owner's permission from https://github.com/anki0476/RailSetu-v2 (`app/components/intro-carousel.tsx`, `landing-faq.tsx`, and `handwritten-signature.tsx`). Skylark-specific content and scoped styles preserve the existing interface.

## About-page particles

The user-supplied InteractiveParticles component credits Bruno Imbrizi's Codrops Interactive Particles and Ashima / Stefan Gustavson's simplex noise. Those credits remain in the adapted source; confirm the upstream component/shader redistribution terms before public release. Three.js retains its MIT license; GSAP retains its Standard no-charge license (https://gsap.com/standard-license). The SKYLARK source graphic is created locally for this project. Rendering is lazy-loaded on About, capped at 30 fps, stopped offscreen, and replaced with static text for reduced motion or WebGL initialization failure.

- Annotated Text: Componentry registry component (@componentry/annotated-text), adapted to local CSS for the landing headline and About title.
- Circuit Board: Componentry registry component (@componentry/circuit-board), adapted to SVG and local CSS for the About workflow.
