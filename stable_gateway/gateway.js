// 稳定网关：固定本地端口 6008，转发到当前 AutoDL 实例（换实例只改 current.json）
// 用法: node gateway.js  （或 start_gateway.bat）
// 管理:
//   http://127.0.0.1:6008/__status       查看当前目标
//   http://127.0.0.1:6008/__set?url=XXX  切换目标（会持久化到 current.json）
const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');

const PORT = 6008;
const CONFIG = path.join(__dirname, 'current.json');

function load() {
  try {
    return JSON.parse(fs.readFileSync(CONFIG, 'utf8'));
  } catch (e) {
    return { target: '' };
  }
}
let cfg = load();

function save() {
  fs.writeFileSync(CONFIG, JSON.stringify(cfg, null, 2));
}

const server = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://127.0.0.1');

  if (u.pathname === '/__status') {
    res.writeHead(200, { 'content-type': 'text/plain; charset=utf-8' });
    res.end('stable gateway :6008 -> ' + (cfg.target || '(未配置)') + '\n');
    return;
  }
  if (u.pathname === '/__set') {
    const t = u.searchParams.get('url');
    if (t && /^https?:\/\//.test(t)) {
      cfg.target = t;
      save();
      res.writeHead(200, { 'content-type': 'text/plain; charset=utf-8' });
      res.end('OK -> ' + t + '\n');
    } else {
      res.writeHead(400, { 'content-type': 'text/plain; charset=utf-8' });
      res.end('bad url, use /__set?url=https://...\n');
    }
    return;
  }

  if (!cfg.target) {
    res.writeHead(503, { 'content-type': 'text/plain; charset=utf-8' });
    res.end('stable gateway: 未配置目标实例，先用 /__set?url=... 设置\n');
    return;
  }

  const target = new URL(cfg.target);
  const mod = target.protocol === 'https:' ? https : http;
  const headers = Object.assign({}, req.headers, { host: target.host });
  const preq = mod.request(
    {
      hostname: target.hostname,
      port: target.port || (target.protocol === 'https:' ? 443 : 80),
      path: req.url,
      method: req.method,
      headers,
    },
    (pres) => {
      res.writeHead(pres.statusCode, pres.headers);
      pres.pipe(res);
    }
  );
  preq.on('error', (e) => {
    res.writeHead(502, { 'content-type': 'text/plain; charset=utf-8' });
    res.end('stable gateway: 上游不可达 (' + e.message + ')\n当前目标: ' + cfg.target + '\n');
  });
  req.pipe(preq);
});

server.listen(PORT, '0.0.0.0', () => {
  console.log('stable gateway listening on 0.0.0.0:' + PORT + ' -> ' + (cfg.target || '(未配置)'));
});
