const http = require('http');
const fs = require('fs');
const path = require('path');
const PORT = 3000;
const DIR = path.join(__dirname, 'build');
const mime = { '.html':'text/html', '.js':'application/javascript', '.css':'text/css', '.json':'application/json', '.map':'application/json' };
http.createServer((req, res) => {
  let p = path.join(DIR, req.url === '/' ? 'index.html' : req.url.split('?')[0]);
  if (!fs.existsSync(p)) p = path.join(DIR, 'index.html');
  try {
    const d = fs.readFileSync(p);
    res.writeHead(200, { 'Content-Type': mime[path.extname(p)] || 'text/plain', 'Content-Length': d.length, 'Cache-Control': 'no-store' });
    res.end(d);
  } catch(e) { res.writeHead(404); res.end('Not found'); }
}).listen(PORT, () => console.log(`http://localhost:${PORT}`));
