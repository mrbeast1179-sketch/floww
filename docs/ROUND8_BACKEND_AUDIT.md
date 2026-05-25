# Round 8 Backend Endpoint Audit (read-only)

Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) by DeepSeek V4 Pro.

## Inventory of /api/* endpoints called from React

Total: $(wc -l < /tmp/react_apis.txt | tr -d ' ')

$(cat /tmp/react_apis.txt | while read line; do echo "- \`$line\`"; done)

## Live health probe (via CRA proxy)

$(cat /tmp/api_audit.txt | while read line; do echo "| $line |"; done)

## Findings

- 200 application/json endpoints: $(grep -c "application/json" /tmp/api_audit.txt || echo 0)
- 200 text/html (proxy passthrough, backend likely not running): $(grep -c "text/html" /tmp/api_audit.txt || echo 0)
- 404 (route missing): $(grep -c " 404 " /tmp/api_audit.txt || echo 0)
- 500 (route error): $(grep -c " 500 " /tmp/api_audit.txt || echo 0)

## Recommendations for Round 9

- All endpoints returned 200 but with text/html content type. This indicates the
  CRA proxy is falling through to serve the React index.html rather than proxying
  to a running backend. The backend Python server is likely not running.
- Start the backend server and re-probe for proper JSON responses.
- Endpoints returning 404 after backend is running need route implementation.
- Endpoints returning 500 have backend bugs.
