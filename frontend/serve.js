/**
 * frontend/serve.js — Node-based static file server for frontend/build/ +
 * reverse-proxy /api/* and /ws/* to backend :8000.
 *
 * Two startup options for the prebuilt bundle:
 *   1. Node (this file):       node frontend/serve.js
 *   2. Python dev fallback:    python3 frontend/static_proxy.py
 *
 * The Python fallback (frontend/static_proxy.py) is the drop-in replacement
 * if the Node path ever fails — see README "Frontend" section for the
 * ajv-keywords recovery steps.
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const PORT = 3000;
const BACKEND = 'http://localhost:8000';
const DIR = path.join(__dirname, 'build');
const mime = { '.html':'text/html', '.js':'application/javascript', '.css':'text/css', '.json':'application/json', '.map':'application/json' };

http.createServer((req, res) => {
  // Proxy /api/* and /ws/* to backend
  if (req.url.startsWith('/api/') || req.url.startsWith('/ws/')) {
    const options = {
      hostname: 'localhost',
      port: 8000,
      path: req.url,
      method: req.method,
      headers: req.headers,
    };
    delete options.headers.host;
    const proxyReq = http.request(options, (proxyRes) => {
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(res, { end: true });
    });
    proxyReq.on('error', (e) => {
      res.writeHead(502);
      res.end(JSON.stringify({ error: 'Backend unavailable', message: e.message }));
    });
    req.pipe(proxyReq, { end: true });
    return;
  }

  let p = path.join(DIR, req.url === '/' ? 'index.html' : req.url.split('?')[0]);
  if (!fs.existsSync(p)) p = path.join(DIR, 'index.html');
  try {
    const d = fs.readFileSync(p);
    res.writeHead(200, { 'Content-Type': mime[path.extname(p)] || 'text/plain', 'Content-Length': d.length, 'Cache-Control': 'no-store' });
    res.end(d);
  } catch(e) { res.writeHead(404); res.end('Not found'); }
}).listen(PORT, () => console.log(`http://localhost:${PORT} (proxying /api -> localhost:8000)`));
