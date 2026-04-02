## 1. Test Infrastructure

- [ ] 1.1 Add pytest, pytest-cov to pyproject.toml dev dependencies
- [ ] 1.2 Add pytest config section to pyproject.toml (testpaths = ["tests"])
- [ ] 1.3 Create tests/__init__.py
- [ ] 1.4 Create tests/conftest.py with shared fixtures (temp dirs, mock configs, mock sqlite)

## 2. Config & State Tests

- [ ] 2.1 Test `config.ProjectConfig.from_yaml()` with valid and invalid inputs
- [ ] 2.2 Test `state.StateManager` save/get/prune operations
- [ ] 2.3 Test `scanner.ProjectScanner` language detection from file markers

## 3. Spec System Tests

- [ ] 3.1 Test `spec/__init__.py` data models: Change, Task, Proposal lifecycle
- [ ] 3.2 Test `spec_discoverer.SpecDiscoverer` parsing proposal.md, tasks.md
- [ ] 3.3 Test `spec_queue.SpecQueue` get_pending/start_task/complete_task round-trip
- [ ] 3.4 Test `openspec_adapter.extract_task_context()` complexity scoring

## 4. Prompt Generation Tests

- [ ] 4.1 Test `driver.GroundedDriver` prompt generation with spec data
- [ ] 4.2 Test `prompt_strategies.select_strategy()` with various attempt histories
- [ ] 4.3 Test `model_router.select_model()` routing decisions

## 5. Outcome & Trust Tests

- [ ] 5.1 Test `outcome.parse_outcome()` for all status types
- [ ] 5.2 Test `trust.TrustBoundary` hash snapshot and violation detection
- [ ] 5.3 Test `prompt_log.PromptLog` record/retrieve cycle

## 6. Post-Execution Tests

- [ ] 6.1 Test `followup.create_followup_issues()` with mock issue data
- [ ] 6.2 Test `rca.analyze_failures()` pattern matching
- [ ] 6.3 Test `learnings.write_learnings()` and `collect_related_learnings()`

## 7. Verification

- [ ] 7.1 All tests pass with `pytest tests/ -v`
- [ ] 7.2 Coverage report shows >40% on core modules (loop, spec_queue, outcome, driver)
