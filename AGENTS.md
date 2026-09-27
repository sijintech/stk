# Repository workflow

- Default to developing, committing and pushing directly on `main`, as requested by the owner.
- Do not create a feature branch or PR for routine changes unless the owner asks for one or a
  repository protection rule requires it.
- Existing unrelated open PRs are not implicitly approved for integration by this workflow choice.

# Development direction

- Read `docs/development-plan.md` for the current roadmap and delivery status.
- Product decisions live in `docs/design/project-workbench.md`; the proposed SQLite project model
  and evaluation rules live in `docs/design/project-model.md`.
- Distinguish planned capabilities from implemented features. Published contracts in `docs/specs/`
  remain authoritative until explicitly versioned or extended.
