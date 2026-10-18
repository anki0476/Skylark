# Dependencies and model attribution

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
No NVIDIA model has yet been selected or tested live. Once a model is selected,
record its exact catalog identifier, model-card/license URL, endpoint, pricing
verification date, and actual contribution in the benchmark report. Do not imply
that the SDK author or NVIDIA has validated the output.

The supplied geometric fixtures are original software-test assets. They are not
photographs, generated model output, robot simulations, or evidence of detection
performance. Real photographs remain subject to their owners' permissions. Model
weights, model outputs, and third-party datasets are not covered by Skylark's MIT
license.
