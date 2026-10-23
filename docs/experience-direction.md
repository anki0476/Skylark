# Product experience: from agent failure to verified repair

The clean-install review on 23 October 2026 exposed a gap between the landing-page promise and the current workflow. A first-time user expected to bring an existing agent, describe its failure, and receive a tested fix. The browser instead opened a reservation example with unexplained resource and customer fields. Results did not make the latest run easy to locate, and Settings named environment variables without showing where to set them.

## Product promise and current boundary

Skylark should help an agent owner answer: **What failed, what happened in the real system, what change prevents a repeat, and what evidence supports that claim?** The included reservation agent demonstrates this loop in a controlled sandbox. Trusted local Python agents can use an adapter. The browser cannot yet connect to a deployed arbitrary agent, import its code, infer a verifier, or apply a repair to its production environment. A Nebius key powers the included model evaluation; it is not a connection to the user's agent.

The interface must keep those boundaries visible. A scripted fixture verifies the workflow, not model reliability. A passing comparison verifies the tested configuration, not universal recovery or production deployment. Never present a sample safeguard as a fix already applied to a user's agent.

## Target journey

The intended experience is a service centre for agents: hand over the problem and a safe test connection, then receive a diagnosis and a tested repair. The user should not have to understand tool instrumentation or edit a runtime policy to get a useful answer. The sample must work without the user owning an agent.

1. **Hand over the problem.** With no agent, one click starts a practice case. With an agent, the user describes the observed failure and expected outcome, then grants only the access needed for a supported connector. Keep technical setup in a developer path.
2. **Check that the agent can be tested.** A connector must identify the actions Skylark can observe and an independent source of actual state. A description or trace alone cannot establish whether the agent succeeded.
3. **Reproduce safely.** Run in an isolated test environment or against recorded data with clear consent and cost limits. Show which failure was injected and whether it was reached.
4. **Diagnose and propose.** Present what the agent saw beside what actually happened, then the consequence and a scoped repair. The user reviews the proposed change, not a list of implementation switches.
5. **Verify and hand back.** Compare original and repaired attempts under the same protocol; show dated evidence and unknown outcomes. A separate, explicit approval is required before changing any external agent or production system.

## Next engineering milestones

- Build a first-class connection flow for **one named agent integration**, beginning with the existing local Python adapter. It should validate the adapter contract and verifier before offering a run. A generic “connect any agent” button would overpromise.
- Add an agent-owner intake and a paired local runner so users can hand over a supported agent without uploading executable code to the web server. Then add named hosted connectors with scoped, revocable access. Each connector needs a tested independent outcome check; a repository URL or credentials alone are not a repair path.
- Support a natural-language incident description as intake context while keeping the selected fault schedule and verifier explicit. Do not silently map free text to a fault or pretend an uninstrumented agent was tested.
- Let Skylark prepare and test a proposed repair automatically once enough evidence is available. Make application to an external agent a separate, reviewable step. The present reservation presets do not modify external agents. For custom environments, replay and repair hooks must be implemented and tested.
- Run another independent review with someone who has never seen the project. Success means they can identify the sample path, understand that example names are fictional, find their latest run, and state exactly what Skylark did and did not fix without coaching.

## Immediate review fixes

The workbench now presents agent connection and the sample in one entry point; makes the practice booking understandable without editing example names; keeps those details optional; explains the chosen failure beside the run action; and moves developer setup behind an expandable section. It also hides model-only guidance during scripted runs, shows local PowerShell setup instructions, and puts dated, sortable attempts before aggregate Results. These reduce confusion, but they do not complete the service-centre journey above.
