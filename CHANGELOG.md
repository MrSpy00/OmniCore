# Changelog

All notable changes to OmniCore are documented in this file.

This project follows a milestone-based release narrative where each major version captures a clear architectural step forward.

## [V33.0] - 2026-04-02

### Added
- Omni-Agent Swarm execution model with delegated subtask orchestration.
- MCP bridge tool (`sys_mcp_bridge`) with `ping`, `read`, and `write` actions.
- Slash command runtime controls (`/plan`, `/doctor`, `/memory`, `/commit`).
- Context compression snapshots for short-term memory evictions.
- Developer swarm helpers: `dev_glob_search`, `dev_grep_analyzer`, `agent_spawn_subtask`.

### Changed
- Router now supports delegated step execution and subtask result aggregation.
- Planner now annotates delegation strategy for search and analysis heavy steps.
- README upgraded to a full bilingual V33.0 operational guide with Mermaid swarm diagram.

### Quality
- Test suite reached 97 passing tests for the V33.0 baseline.

## [V-AEGIS] - 2026-04-02

### Changed
- Enforced federation failover hardening and strict zero-trust execution gates.
- Strengthened policy-first execution boundaries before tool dispatch.

### Why It Matters
- Marked the formal Zero-Trust Guardian tightening phase before swarm rollout.

## [V32.1] - 2026-04-02

### Changed
- Architectural refactor focused on async purity and lower cyclomatic complexity.
- Introduced and stabilized OS-Adapter patterns for cross-platform shell behavior.

### Why It Matters
- Established cleaner architecture seams that enabled V33.0 delegation and MCP expansion.

## [V32.0] - 2026-03-21

### Changed
- Broad platform mastery and repo-wide polish pass.
- Bilingual enterprise-grade documentation refresh.

### Quality
- Zero-defect stabilization push prior to V32.1 and V-AEGIS hardening.

## [V31.0] - 2026-03-21

### Added
- Copilot parity override capabilities for developer workflows.

### Changed
- Introduced Zero-Wait 429 rotation strategy to avoid provider stall conditions.
- Fixed startup crash paths and improved bootstrap resilience.

### Why It Matters
- Zero-Wait Rotator became the reliability backbone for multi-provider continuity.

## [V30.x] - 2026-03 (internal bridge phase)

### Notes
- No standalone public `V30.0` commit tag appears in the current git history.
- Internal transitions in this interval fed directly into V31.0 and V32.0 milestones.

## [V29.0] - 2026-03-21

### Added
- Self-healing vision behavior and resilient fallback mechanics.

### Changed
- Improved recovery behavior during ambiguous or partially failing execution paths.

## [V28.0] - 2026-03-21

### Changed
- Major bilingual README and architecture audit refresh.
- Stability-focused consolidation across tooling surfaces.

## [V27.0] - 2026-03-21

### Added
- Expanded OpenClaw execution depth with stronger OS-level operational scope.

### Changed
- Hardened API rotation behavior and broad bug eradication pass.

## [V26.0] - 2026-03-21

### Added
- Cross-platform root-level execution primitives.
- Vision action loop as a foundation for physical and visual operations.

### Changed
- Core runtime moved closer to autonomous, self-learning orchestration patterns.

## [V25.0] - 2026-03-21

### Added
- Zero-hallucination execution direction and physical GUI mastery baseline.
- Large omnipotent toolset expansion that set the modern OmniCore trajectory.

### Why It Matters
- This release is the beginning of the modern V25 to V33 transformation arc.

---

## Paradigm Shift Summary (V25 -> V33)

### 1) Zero-Wait Rotator
- Landed in V31.0 to eliminate waiting behavior under rate-limit pressure.
- Upgraded runtime continuity by rotating providers/keys without flow interruption.

### 2) OS-Adapters
- Formalized in V32.1 to normalize shell and system behavior across platforms.
- Reduced coupling and enabled cleaner extension points for future tooling.

### 3) Zero-Trust Guardian
- Hardened in V-AEGIS with strict policy-first gates and safer execution guarantees.
- Converted safety from optional logic to a mandatory orchestration contract.

### 4) Omni-Agent Swarming
- Delivered in V33.0 with delegated task execution and subtask coordination.
- Shifted OmniCore from single-path orchestration to swarm-capable cognitive execution.

---

## Current State After V33.0

- Swarm-capable router with delegation metadata and subtask orchestration.
- Context compression integrated into memory lifecycle.
- Slash-command operational controls available in CLI runtime.
- MCP bridge online for protocol-aligned local integrations.
- Stable quality baseline validated by lint and tests.
