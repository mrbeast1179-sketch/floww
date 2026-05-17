# Claude Code Review Prompt

Paste this into Claude Code to review and improve Confluence Decoder:

---

Review the Confluence Decoder project at /Users/nav/Documents/GitHub/floww. This is a FastAPI + React + MongoDB options trading intelligence platform.

## What to Review

1. **Backend** (`backend/server.py` - 2700+ lines):
   - Check for bugs, security issues, performance problems
   - Review all API routes for correctness
   - Check error handling and edge cases
   - Look for code duplication that should be refactored

2. **Data Providers** (`backend/data_providers.py`, `backend/flashalpha_client.py`, `backend/alpaca_client.py`):
   - Check API key handling and security
   - Review rate limiting implementation
   - Check error handling for API failures
   - Verify fallback chain logic

3. **Alert Engine** (`backend/alert_engine.py`):
   - Review signal detection logic
   - Check for edge cases (division by zero, missing data)
   - Verify alert priority sorting
   - Suggest additional alert types

4. **Frontend** (`frontend/src/`):
   - Review React components for bugs
   - Check for memory leaks in useEffect hooks
   - Review state management
   - Check for accessibility issues

5. **Tests** (`backend/tests/test_api.py`):
   - Review test coverage
   - Suggest additional test cases
   - Check for missing edge case tests

6. **Configuration** (`.env.example`, `docker-compose.yml`, `.github/workflows/`):
   - Review security of configuration
   - Check for missing environment variables
   - Review CI/CD pipeline

## What to Improve

1. **Security**: Any hardcoded credentials, missing input validation, SQL injection risks
2. **Performance**: N+1 queries, missing database indexes, unnecessary API calls
3. **Code Quality**: Duplicated code, missing type hints, unclear variable names
4. **Error Handling**: Missing try/catch, unhandled promise rejections
5. **Best Practices**: REST API design, React patterns, Python conventions

## Output

For each issue found:
- File path and line number
- Severity (CRITICAL, HIGH, MEDIUM, LOW)
- Description of the issue
- Suggested fix with code

Prioritize issues that could cause bugs or security vulnerabilities in production.
