# ADR-0009: Tracer Bullets and Spikes for Integrated Development

## Status

Accepted — 2026-05-07

## Context

The project follows a Pragmatic Clean Architecture (ADR-0006). While this ensures separation of concerns, it has historically led to "disconnected developments" where infrastructure adapters or domain entities are built in isolation and remain unused or "orphaned" for several iterations before being wired into a report.

To maintain a fast evolution and ensure that every line of code contributes to a functional whole, we need a methodology that prioritizes end-to-end integration over layer-by-layer completion.

## Decision

We adopt a hybrid workflow of **Spikes** and **Tracer Bullets**:

1.  **Spikes (Exploratory Research)**:
    - **Optional**: Used only when there is high technical uncertainty (e.g., a new external API or complex library).
    - **Throwaway**: Code is written in temporary branches and **must be deleted** once the knowledge is gained.
    - **Outcome**: The knowledge is "rescued" and documented in an RFC or a new ADR. It often helps define the *Tracer Bullet Path*.

2.  **Tracer Bullets (Integrated Development)**:
    - **Mandatory**: Every new RFC must start with a Tracer Bullet.
    - **Definition**: A thin, functional "vertical slice" that connects all layers: `Infrastructure` → `Application` → `Domain` → `Presentation`.
    - **Anchor**: It **must** be wired in the **Composition Root** (e.g., `bootstrap.py`) and produce a visible change in at least one report output (JSON/Markdown/Slack).
    - **Permanent**: Unlike a Spike, Tracer Bullet code is production-quality and becomes the foundation for subsequent iterations.

## Flow

```text
[ Uncertainty ] -> [ Spike (Optional) ] -> [ RFC/ADR ] -> [ Tracer Bullet (PR #1) ] -> [ Feature Completion ]
```

## Consequences

**Positive**
- **Zero Orphan Code**: Features are integrated from the first PR.
- **Immediate Feedback**: The design of domain entities is validated against the final report output immediately.
- **Faster Evolution**: Reduces the "integration pain" at the end of a long feature development.

**Negative**
- Requires more discipline in defining the "minimal functional path" before coding.
- The first PR of a feature might seem "empty" (e.g., a CSV with only one column), but it validates the entire "plumbing".
