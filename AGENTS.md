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
- See `docs/repository-structure.md` for active module boundaries and `archive/manifest.json` for
  archived paths. Do not import archived code or include it in builds, packages or test discovery.

# Handoff

- Read `handoff.md` before starting: it is the current handoff snapshot (state, pending owner decisions, how to build and
  test, code entry points). Check the real Git state and CI before trusting it, and update it when the state changes.
- Keep `handoff.md`, `docs/development-plan.md`, `docs/development-log.md` and `docs/runtime-validation.md` current at each
  delivery, with the actual commit, test and CI results and the remaining limits. Critically review each delivery, fix
  real problems and protect existing uncommitted changes.

# Rules that every agent must keep

- Never read, print or store secrets. The product's AI key is the environment variable `STK_TOKEN_PLAN_API_KEY`; do not put
  credentials in logs, projects, fixtures or commits. Test placeholders must be low-entropy (e.g. `abcdefghijklmnopqrstu`).
- Run tests with `STK_TOKEN_PLAN_API_KEY=` empty and `STK_TOKEN_PLAN_MODEL` unset. Refresh, reopen and tests must never make a
  charged model request. Do not change the product model endpoint.
- Changing model endpoints, keys or the network policy is desktop-only (never from scripts or the agent). Private project
  data never goes to an external model endpoint.
- In public repository documents, refer to the partner research group as "合作方", not by name.
- Push code only after the desktop CI of the previous code head has finished; record CI results in
  `docs/runtime-validation.md`. Run a secret scan (gitleaks with `.gitleaks.toml`) on staged changes before committing.
- Pending owner decisions are listed in `handoff.md`; do not build on an option the owner has not chosen.
