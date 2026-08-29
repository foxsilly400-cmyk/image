// 稳定网关：固定本地端口 6008，转发到当前 AutoDL 实例（换实例只改 current.json）
// 用法: node gateway.js  （或 start_gateway.bat）
// 管理:
//   http://127.0.0.1:6008/__status       查看当前目标
//   http://127.0.0.1:6008/__set?url=XXX  切换目标（会持久化到 current.json）
const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

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

function cors(headers) {
  return Object.assign({}, headers, {
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'POST, GET, OPTIONS',
    'access-control-allow-headers': 'content-type',
    'access-control-allow-private-network': 'true'
  });
}

const server = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://127.0.0.1');

  if (req.method === 'OPTIONS') {
    res.writeHead(204, cors({}));
    res.end();
    return;
  }

  // 实例复位：接收入口页提交的 ssh 信息 → 跑 reset_instance.py 全链路
  // （更新 app.py/target.json/current.json + git push + SSH 远端恢复）
  if (u.pathname === '/__instance' && req.method === 'POST') {
    let body = '';
    req.on('data', (c) => (body += c));
    req.on('end', () => {
      let text = '';
      try { text = (JSON.parse(body).text || '').trim(); } catch (e) { text = ''; }
      if (!text || !/^ssh\s+-p\s+\d+/.test(text)) {
        res.writeHead(400, cors({ 'content-type': 'text/plain; charset=utf-8' }));
        res.end('格式错误，示例:\n  ssh -p 25562 root@host 密码 https://公网:8443\n');
        return;
      }
      const script = path.join(__dirname, '..', '..', 'scripts', 'reset_instance.py');
      const dbg = 'ENVDBG PATH=' + (process.env.PATH || '').split(';').filter(x => /python/i.test(x)).join('|') + ' PROXY=' + (process.env.HTTP_PROXY || process.env.http_proxy || '') + ' HTTPS_PROXY=' + (process.env.HTTPS_PROXY || process.env.https_proxy || '') + ' CWD=' + process.cwd() + '\n';
      res.writeHead(200, cors({ 'content-type': 'text/plain; charset=utf-8' }));
      res.write(dbg);
      const py = spawn('python', [script, text], {
        windowsHide: true,
        env: Object.assign({}, process.env, { PYTHONIOENCODING: 'utf-8' })
      });
      py.stdout.on('data', (d) => res.write(d));
      py.stderr.on('data', (d) => res.write(d));
      py.on('close', (code) => { res.end('\n[exit ' + code + ']\n'); });
      py.on('error', (e) => { res.end('\n[spawn error] ' + e.message + '\n'); });
    });
    return;
  }

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
