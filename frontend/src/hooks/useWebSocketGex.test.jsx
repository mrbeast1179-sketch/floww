/**
 * useWebSocketGex.test.jsx
 */
var useWebSocketGex = require("./useWebSocketGex").useWebSocketGex;

describe("useWebSocketGex", () => {
  test("module exports useWebSocketGex function", function() {
    expect(typeof useWebSocketGex).toBe("function");
  });

  var fs = require("fs");
  var path = require("path");
  var src = fs.readFileSync(path.join(__dirname, "useWebSocketGex.jsx"), "utf8");

  test("source code includes ws.close() in cleanup", function() {
    expect(src).toContain("ws.close()");
  });

  test("source code nullifies onclose before closing", function() {
    expect(src).toContain("wsRef.current.onclose = null");
  });

  test("source code clears reconnect timeout on unmount", function() {
    expect(src).toContain("clearTimeout(reconnectRef.current)");
  });

  test("source code sets mountedRef.current = false on cleanup", function() {
    expect(src).toContain("mountedRef.current = false");
  });

  test("source code resets wsRef to null after close", function() {
    expect(src).toContain("wsRef.current = null");
  });

  test("cleanup is returned from useEffect", function() {
    expect(src).toMatch(/return\s*\(\)\s*=>\s*\{/);
  });
});
