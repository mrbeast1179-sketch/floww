# Pull Request Template — floww / Confluence Decoder

## What

<!-- One paragraph: what this PR does and why. -->

## Verification

<!-- Evidence required per CLAUDE.md. Real output only — no invented results. -->

```bash
# paste the commands you ran and their actual output
```

- [ ] Backend tests: `cd backend && .venv/bin/python -m pytest tests -q --tb=no` (paste count)
- [ ] Frontend tests: `cd frontend && npx craco test --watchAll=false` (277 expected)
- [ ] ruff clean: `cd backend && .venv/bin/ruff check .`
- [ ] Live endpoint check (if API-touching): paste curl + response summary

## Checklist

- [ ] No forbidden files touched (`ml/inference.py`, `dash_ui.py`, `App.js` surgical-only, model artifacts)
- [ ] No forbidden git ops used
- [ ] Commit messages follow `type(scope): subject` with inline verification evidence
- [ ] Tests added/updated for behavior changes; never skip/xfail a passing test
