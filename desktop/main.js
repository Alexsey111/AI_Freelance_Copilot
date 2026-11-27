// Окно программы: поднимает ядро на Python, ждёт готовности и показывает интерфейс.
//
// Ядро (FastAPI + SQLite) остаётся отдельным процессом: так его можно проверить без окна,
// перезапустить отдельно и показать на защите как самостоятельную часть. Окно — оболочка,
// которая не содержит бизнес-логики.

const { app, BrowserWindow, shell, Menu, dialog } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const net = require('net');
const http = require('http');

const SELFTEST = process.argv.includes('--selftest');
const SMOKE = process.argv.includes('--smoke');
const SMOKE_OUT = (() => {
  const i = process.argv.indexOf('--smoke-out');
  if (i > -1 && process.argv[i + 1]) return path.resolve(process.argv[i + 1]);
  return path.join(app.getPath('temp'), 'freelance-copilot.png');
})();

const ROOT = path.resolve(__dirname, '..');
const PYTHON = process.env.FREELANCE_PYTHON || path.join(ROOT, '.venv', 'Scripts', 'python.exe');

const TRACE_FILE = path.join(process.env.TEMP || '.', 'fc-trace.log');
function trace(message) {
  try {
    fs.appendFileSync(TRACE_FILE, `${new Date().toISOString()} ${message}
`);
  } catch (_) {
    /* трассировка не должна мешать работе */
  }
}
trace('module loaded, args=' + process.argv.slice(1).join(' '));

let backend = null;
let baseUrl = null;
let win = null;

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

function ping(url) {
  return new Promise((resolve) => {
    const req = http.get(`${url}/api/v1/health`, { timeout: 1500 }, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForBackend(url, timeoutMs = 60000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (await ping(url)) return true;
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

async function startBackend() {
  const port = await freePort();
  trace('startBackend port=' + port);
  baseUrl = `http://127.0.0.1:${port}`;
  const args = ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(port), '--log-level', 'warning'];
  trace('spawn ' + PYTHON + ' ' + args.join(' '));
  backend = spawn(PYTHON, args, { cwd: ROOT, windowsHide: true });
  backend.on('error', (error) => trace('spawn error: ' + error.message));

  const logFile = path.join(app.getPath('userData'), 'backend.log');
  const append = (chunk) => {
    try {
      fs.appendFileSync(logFile, chunk);
    } catch (_) {
      /* лог недоступен — не повод падать */
    }
  };
  backend.stdout.on('data', append);
  backend.stderr.on('data', append);
  backend.on('exit', (code) => append(`\n[backend exited ${code}]\n`));

  trace('waiting backend...');
  const ready = await waitForBackend(baseUrl);
  trace('backend ready=' + ready);
  if (!ready) {
    throw new Error(
      `Ядро не ответило за 60 секунд. Проверьте, что установлен Python и зависимости в .venv.\nЛог: ${logFile}`
    );
  }
  return baseUrl;
}

function loadWindowState() {
  const file = path.join(app.getPath('userData'), 'window.json');
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (_) {
    return { width: 1180, height: 820 };
  }
}

function saveWindowState(browserWindow) {
  const file = path.join(app.getPath('userData'), 'window.json');
  const bounds = browserWindow.getNormalBounds();
  try {
    fs.writeFileSync(file, JSON.stringify({ ...bounds, maximized: browserWindow.isMaximized() }));
  } catch (_) {
    /* состояние окна не критично */
  }
}

function routeExternalLinks(browserWindow) {
  browserWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  browserWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('file://') && !url.startsWith(baseUrl || '')) {
      event.preventDefault();
      if (/^https?:/.test(url)) shell.openExternal(url);
    }
  });
}

async function createWindow() {
  const state = loadWindowState();
  win = new BrowserWindow({
    width: state.width || 1180,
    height: state.height || 820,
    x: state.x,
    y: state.y,
    minWidth: 940,
    minHeight: 640,
    show: false,
    backgroundColor: '#0f1420',
    title: 'AI Freelance Copilot',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      // Скрытое окно тормозит таймеры страницы: без этого проверка ждёт setTimeout минутами.
      backgroundThrottling: false,
    },
  });

  routeExternalLinks(win);
  if (state.maximized) win.maximize();

  await win.loadFile(path.join(__dirname, 'ui', 'index.html'), {
    search: `?api=${encodeURIComponent(baseUrl)}`,
  });

  win.once('ready-to-show', () => win.show());
  win.on('close', () => saveWindowState(win));
  return win;
}

// --- Селф-тест: проходит по экранам и проверяет, что данные пришли из ядра ---

async function selftest() {
  const checks = [];
  const expect = (name, ok, detail = '') => checks.push({ name, ok, detail });

  const evaluate = async (script) => {
    if (win.webContents.isLoading()) {
      await new Promise((r) => win.webContents.once('did-finish-load', r));
    }
    try {
      return await win.webContents.executeJavaScript(script, true);
    } catch (error) {
      trace(`evaluate failed: ${script.slice(0, 60)} -> ${error.message}`);
      throw error;
    }
  };

  win.showInactive();
  await new Promise((r) => setTimeout(r, 500));
  trace('selftest started, page title=' + (await evaluate('document.title')));

  const profile = await evaluate('window.selftest.profile()');
  expect('профиль загружен', Boolean(profile && profile.name), JSON.stringify(profile && profile.skills));
  expect('навыки на экране', Array.isArray(profile.skills) && profile.skills.length > 0);

  const catalog = await evaluate('window.selftest.catalog()');
  const catalogSkills = (catalog || []).reduce((sum, group) => sum + group.skills.length, 0);
  expect(
    'справочник навыков не только для разработчика',
    catalogSkills >= 100 && (catalog || []).length >= 8,
    `навыков ${catalogSkills} в ${(catalog || []).length} профессиях`
  );
  expect(
    'в справочнике есть не-ИТ профессии',
    (catalog || []).some((group) => group.key === 'text') &&
      (catalog || []).some((group) => group.key === 'design')
  );

  const norms = await evaluate('window.selftest.norms()');
  expect('нормы времени пришли', norms.length >= 5, `норм: ${norms.length}`);

  const settings = await evaluate('window.selftest.settings()');
  expect('правила пришли', settings.length >= 10, `правил: ${settings.length}`);
  expect(
    'правила с русскими подписями',
    settings.every((item) => item.label && item.label !== item.key)
  );

  const workload = await evaluate('window.selftest.workload()');
  expect('загрузка недели посчитана', typeof workload.capacity_hours === 'number', `ёмкость ${workload.capacity_hours}`);

  const queue = await evaluate('window.selftest.queue()');
  expect('очередь проверки отвечает', typeof queue.total === 'number', `в очереди ${queue.total}`);

  const runs = await evaluate('window.selftest.runs()');
  expect('прогоны отвечают', Array.isArray(runs));

  const orders = await evaluate('window.selftest.orders()');
  expect(
    'заказы по выбранным площадкам видны',
    orders && typeof orders.total === 'number',
    orders ? `заказов ${orders.total}` : ''
  );

  const shortlist = await evaluate('window.selftest.shortlist()');
  expect(
    'подборка под профиль строится',
    Array.isArray(shortlist),
    Array.isArray(shortlist) ? `в подборке ${shortlist.length}` : ''
  );

  const platforms = await evaluate('window.selftest.platforms()');
  const flru = (platforms || []).find((item) => item.key === 'flru');
  expect(
    'тарифы площадок загружены',
    (platforms || []).length >= 7 && Boolean(flru) && flru.best_price === 50,
    flru ? `FL.ru: ${flru.best_price} ₽ за попытку, площадок ${platforms.length}` : ''
  );

  const funnel = await evaluate('window.selftest.funnel()');
  expect(
    'воронка откликов считается',
    Boolean(funnel) && typeof funnel.sent === 'number',
    funnel ? `откликов ${funnel.sent}` : ''
  );

  // Переключение экранов: каждый таб должен отрисоваться без ошибок.
  for (const tab of [
    'profile',
    'orders',
    'norms',
    'workload',
    'settings',
    'queue',
    'platforms',
    'responses',
    'runs',
  ]) {
    const ok = await evaluate(`window.selftest.show('${tab}')`);
    expect(`экран «${tab}» открывается`, Boolean(ok));
  }

  const failed = checks.filter((c) => !c.ok);
  for (const c of checks) {
    const line = `${c.ok ? 'OK  ' : 'FAIL'} ${c.name}${c.detail ? ' — ' + c.detail : ''}`;
    console.log(line);
    trace(line);
  }
  if (failed.length) {
    console.log('SELFTEST_FAIL');
    trace('SELFTEST_FAIL');
    app.exit(1);
    return 1;
  }
  console.log('SELFTEST_OK');
  trace('SELFTEST_OK');
  return 0;
}

async function smoke() {
  // Никакой подписки на did-finish-load: к этому моменту страница уже загружена,
  // и ожидание события, которое никогда не придёт, вешает проверку навсегда.
  // Скрытое окно не рисуется, и capturePage() на нём ждёт вечно. Показываем окно и
  // ставим сторожевой таймер: лучше провал с сообщением, чем молчаливое зависание.
  win.showInactive();
  await new Promise((r) => setTimeout(r, 1500));
  const tabIndex = process.argv.indexOf('--smoke-tab');
  if (tabIndex > -1 && process.argv[tabIndex + 1]) {
    const tab = process.argv[tabIndex + 1];
    await win.webContents.executeJavaScript(`window.selftest.show('${tab}')`, true);
    trace('smoke: tab ' + tab);
    await new Promise((r) => setTimeout(r, 700));
  }
  trace('smoke: capturing');
  const image = await Promise.race([
    win.webContents.capturePage(),
    new Promise((_, reject) => setTimeout(() => reject(new Error('capturePage timeout')), 15000)),
  ]);
  fs.mkdirSync(path.dirname(SMOKE_OUT), { recursive: true });
  fs.writeFileSync(SMOKE_OUT, image.toPNG());
  trace('smoke: saved ' + SMOKE_OUT + ' size=' + image.toPNG().length);
  console.log(`SMOKE_OK ${SMOKE_OUT}`);
}

// --- Запуск ---

if (SELFTEST || SMOKE) {
  // Сервисный прогон не должен зависеть от открытого окна у владельца.
  app.setPath('userData', path.join(app.getPath('temp'), `freelance-copilot-${process.pid}`));
}

if (!SELFTEST && !SMOKE && !app.requestSingleInstanceLock()) {
  app.quit();
} else {
  trace('before whenReady');
  app.whenReady().then(async () => {
    trace('whenReady');
    Menu.setApplicationMenu(null);
    try {
      await startBackend();
      trace('createWindow');
      await createWindow();
      trace('window loaded');
    } catch (error) {
      // В сервисном прогоне диалог недопустим: он ждёт нажатия кнопки и подвешивает проверку.
      console.log(`START_FAIL ${error.message || error}`);
      if (SELFTEST || SMOKE) {
        app.exit(2);
        return;
      }
      dialog.showErrorBox('Не удалось запустить программу', String(error.message || error));
      app.exit(2);
      return;
    }

    if (SELFTEST) {
      try {
        const code = await selftest();
        app.exit(code);
      } catch (error) {
        console.log(`SELFTEST_FAIL ${error.message}`);
        trace(`SELFTEST_FAIL ${error.stack || error.message}`);
        app.exit(2);
      }
      return;
    }

    if (SMOKE) {
      try {
        await smoke();
        app.exit(0);
      } catch (error) {
        console.log(`SMOKE_FAIL ${error.message}`);
        app.exit(2);
      }
    }
  });

  app.on('window-all-closed', () => app.quit());
  app.on('will-quit', () => {
    if (backend && !backend.killed) backend.kill();
  });
}
