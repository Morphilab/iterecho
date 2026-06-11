## Summary

<!-- One or two sentences. What does this PR do? -->

## Related issue

<!-- Link to the issue this closes, e.g. "Fixes #42" or "Refs #42". -->

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing
      functionality to change)
- [ ] Documentation only
- [ ] Refactor / cleanup

## Checklist

- [ ] Tests added or updated — `pytest` is green locally
- [ ] Lint passes: `ruff check iterecho/ tests/`
- [ ] Format passes: `black --check --line-length 100 iterecho/ tests/`
- [ ] Imports pass: `isort --check --profile black iterecho/ tests/`
- [ ] Types pass: `mypy iterecho/`
- [ ] Security audit clean: `bandit -r iterecho/ -q -ll` and `pip-audit`
- [ ] Build succeeds: `python -m build`
- [ ] `CHANGELOG.md` updated (Added / Changed / Fixed / Security)
- [ ] Public API change? — `__init__.py` exports updated and documented
- [ ] CLI change? — help text updated and a new test added in
      `tests/test_cli.py`

## Security review

If this PR touches the security boundary (`security.py`,
`config/sanitize.py`, `utils/file_utils.py`, or the lock logic in
`processing.py`):

- [ ] New tests cover the new behavior (regression-safe)
- [ ] No reduction in default protection
- [ ] Documented the impact in `CHANGELOG.md` under `### Security`

## Notes for reviewer

<!-- Anything the reviewer should pay special attention to. -->
