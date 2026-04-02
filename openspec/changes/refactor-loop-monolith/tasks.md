## 1. Extract Executor Module

- [ ] 1.1 Create `aipm/executor.py` with agent execution logic extracted from loop.py
- [ ] 1.2 Move `_run_agent()` method to executor
- [ ] 1.3 Move trust boundary setup/check to executor
- [ ] 1.4 Move outcome parsing call to executor

## 2. Extract Cycle Module

- [ ] 2.1 Create `aipm/cycle.py` with single-cycle orchestration
- [ ] 2.2 Move `_process_issue()` and `_process_spec_item()` to cycle
- [ ] 2.3 Move follow-up/PR creation logic to cycle
- [ ] 2.4 Move learnings write to cycle

## 3. Simplify Loop

- [ ] 3.1 Refactor `MultiProjectLoop` to call cycle.py for each project
- [ ] 3.2 Keep scanning, scheduling, health checks in loop.py
- [ ] 3.3 Update all imports in main.py and other modules

## 4. Verification

- [ ] 4.1 No module exceeds 400 lines (wc -l check)
- [ ] 4.2 Existing loop behavior unchanged (manual run-once test)
- [ ] 4.3 All new tests pass
