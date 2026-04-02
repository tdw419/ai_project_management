## 1. Add PyGitHub Dependency

- [ ] 1.1 Add `PyGitHub>=2.0.0` to pyproject.toml dependencies
- [ ] 1.2 Create `aipm/github_client.py` with a shared `get_github_client()` that reads GH_TOKEN/GITHUB_TOKEN

## 2. Migrate issue_queue.py

- [ ] 2.1 Replace `subprocess.run(["gh", "issue", "list"])` with `repo.get_issues()` calls
- [ ] 2.2 Replace `subprocess.run(["gh", "issue", "create"])` with `repo.create_issue()`
- [ ] 2.3 Replace `subprocess.run(["gh", "issue", "close"])` with `issue.edit(state="closed")`
- [ ] 2.4 Add error handling for rate limits and API errors

## 3. Migrate github_sync.py

- [ ] 3.1 Replace label management subprocess calls with `repo.get_label()` / `repo.create_label()`
- [ ] 3.2 Replace milestone subprocess calls with PyGitHub equivalents
- [ ] 3.3 Replace issue CRUD with PyGitHub calls

## 4. Migrate auto_pr.py

- [ ] 4.1 Replace `subprocess.run(["gh", "pr", "create"])` with `repo.create_pull()`
- [ ] 4.2 Replace branch creation subprocess calls with `repo.create_git_ref()`

## 5. Migrate loop.py & followup.py & rca.py

- [ ] 5.1 Replace remaining `subprocess.run(["gh", ...])` calls in loop.py
- [ ] 5.2 Replace remaining calls in followup.py
- [ ] 5.3 Replace remaining calls in rca.py

## 6. Verification

- [ ] 6.1 `grep -r "subprocess.*gh" aipm/` returns zero matches
- [ ] 6.2 All existing tests pass
- [ ] 6.3 Manual test: `main.py run-once` works end-to-end
