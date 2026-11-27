/* Логика окна: только запросы к ядру и отрисовка. Никаких правил отбора здесь нет. */

const API = (window.desktop && window.desktop.apiBase) || 'http://127.0.0.1:8000';

const state = {
  catalog: [],
  platforms: [],
  platformsChecked: '',
  platformsWarning: '',
  orders: [],
  ordersTotal: 0,
  shortlist: [],
  shortlistNote: '',
  responses: [],
  funnel: null,
  profile: null,
  norms: [],
  settings: [],
  workload: null,
  queue: { items: [], total: 0 },
  runs: [],
  skills: [],
};

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(`${API}/api/v1${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) {
      /* тело не JSON — оставляем код */
    }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

function setStatus(text, isError = false) {
  const el = $('status');
  el.textContent = text;
  el.classList.toggle('error', isError);
}

function note(id, text, isError = false) {
  const el = $(id);
  el.textContent = text;
  el.classList.toggle('error', isError);
}

// --- Экраны ---

function show(tab) {
  document.querySelectorAll('.tab-panel').forEach((panel) => {
    panel.classList.toggle('active', panel.id === `tab-${tab}`);
  });
  document.querySelectorAll('.tabs button').forEach((button) => {
    button.classList.toggle('active', button.dataset.tab === tab);
  });
  return true;
}

document.querySelectorAll('.tabs button').forEach((button) => {
  button.addEventListener('click', () => show(button.dataset.tab));
});

// --- Профиль ---

function renderSkills() {
  const box = $('skills-box');
  box.innerHTML = '';
  state.skills.forEach((skill, index) => {
    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.innerHTML = `<span></span><button title="Убрать">×</button>`;
    chip.querySelector('span').textContent = skill;
    chip.querySelector('button').addEventListener('click', () => {
      state.skills.splice(index, 1);
      renderSkills();
    });
    box.appendChild(chip);
  });
}

function renderProfile() {
  const profile = state.profile || {};
  const prefs = profile.preferences || {};
  $('profile-name').value = profile.name || '';
  $('profile-summary').value = profile.summary || '';
  $('profile-experience').value = profile.experience || '';
  $('profile-budget').value = prefs.min_budget_rub ?? prefs.min_budget ?? '';
  $('profile-rate').value = prefs.rate_rub_per_hour ?? '';
  // Часы берём из правил, если в профиле их ещё не задавали: пустое поле выглядит как ошибка.
  const ruleHours = (state.settings.find((item) => item.key === 'available_hours_per_week') || {}).value;
  $('profile-hours').value = prefs.hours_per_week ?? ruleHours ?? '';
  state.skills = [...(profile.skills || [])];
  renderSkills();
  renderCatalog();
}

$('skill-input').addEventListener('keydown', (event) => {
  if (event.key !== 'Enter') return;
  event.preventDefault();
  const value = event.target.value.trim();
  if (!value) return;
  if (!state.skills.some((skill) => skill.toLowerCase() === value.toLowerCase())) {
    state.skills.push(value);
    renderSkills();
  }
  event.target.value = '';
});

$('save-profile').addEventListener('click', async () => {
  if (!state.profile) return;
  const preferences = { ...(state.profile.preferences || {}) };
  const budget = Number($('profile-budget').value);
  const rate = Number($('profile-rate').value);
  const hours = Number($('profile-hours').value);
  if (Number.isFinite(budget) && budget > 0) preferences.min_budget_rub = budget;
  if (Number.isFinite(rate) && rate > 0) preferences.rate_rub_per_hour = rate;
  if (Number.isFinite(hours) && hours > 0) preferences.hours_per_week = hours;

  try {
    state.profile = await api(`/profiles/${state.profile.id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        name: $('profile-name').value,
        summary: $('profile-summary').value,
        experience: $('profile-experience').value,
        skills: state.skills,
        preferences,
      }),
    });
    renderProfile();
    note('profile-note', 'Сохранено');
  } catch (error) {
    note('profile-note', `Не сохранено: ${error.message}`, true);
  }
});

// --- Справочник навыков ---

function renderCatalog() {
  const box = $('catalog');
  const query = ($('catalog-search').value || '').trim().toLowerCase();
  box.innerHTML = '';
  let shown = 0;
  state.catalog.forEach((group) => {
    const skills = query
      ? group.skills.filter((skill) => skill.toLowerCase().includes(query))
      : group.skills;
    if (!skills.length) return;
    const block = document.createElement('div');
    block.className = 'catalog-group';
    block.innerHTML = '<span class="catalog-title"></span><div class="catalog-items"></div>';
    block.querySelector('.catalog-title').textContent = group.title;
    const items = block.querySelector('.catalog-items');
    skills.forEach((skill) => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'skill-chip';
      chip.textContent = skill;
      if (state.skills.some((own) => own.toLowerCase() === skill.toLowerCase())) {
        chip.classList.add('picked');
      }
      chip.addEventListener('click', () => {
        if (!state.skills.some((own) => own.toLowerCase() === skill.toLowerCase())) {
          state.skills.push(skill);
          renderSkills();
          renderCatalog();
          note('profile-note', `Добавлено: ${skill} — не забудьте сохранить профиль`);
        }
      });
      items.appendChild(chip);
      shown += 1;
    });
    box.appendChild(block);
  });
  if (!shown) {
    box.innerHTML = '<p class="empty">Ничего не нашлось — впишите навык вручную выше</p>';
  }
}

$('catalog-search').addEventListener('input', renderCatalog);

// --- Нормы времени ---

function renderNorms() {
  const body = $('norms-table').querySelector('tbody');
  body.innerHTML = '';
  state.norms.forEach((norm) => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td><strong></strong><div class="sub"></div></td>
      <td><input type="number" min="0.5" step="0.5" class="hours-input"></td>
      <td class="keywords"></td>
      <td><button class="ghost">Сохранить</button></td>`;
    row.querySelector('strong').textContent = norm.title;
    row.querySelector('.sub').textContent = norm.task_kind;
    row.querySelector('.hours-input').value = norm.hours;
    row.querySelector('.keywords').textContent = norm.keywords.join(', ');
    row.querySelector('button').addEventListener('click', async () => {
      const hours = Number(row.querySelector('.hours-input').value);
      try {
        const updated = await api(`/time-norms/${norm.task_kind}`, {
          method: 'PUT',
          body: JSON.stringify({ hours }),
        });
        Object.assign(norm, updated);
        setStatus(`Норма «${updated.title}» — ${updated.hours} ч`);
      } catch (error) {
        setStatus(`Не сохранено: ${error.message}`, true);
      }
    });
    body.appendChild(row);
  });
}

$('estimate-run').addEventListener('click', async () => {
  const title = $('estimate-title').value.trim();
  if (!title) {
    note('estimate-note', 'Введите заголовок заказа', true);
    return;
  }
  try {
    const answer = await api('/time-norms/estimate', {
      method: 'POST',
      body: JSON.stringify({ title, description: $('estimate-desc').value }),
    });
    note(
      'estimate-note',
      answer.hours ? `${answer.hours} ч — ${answer.reason}` : answer.reason,
      !answer.hours
    );
  } catch (error) {
    note('estimate-note', error.message, true);
  }
});

// --- Загрузка недели ---

function renderWorkload() {
  const load = state.workload;
  if (!load) return;
  $('workload-cards').innerHTML = `
    <div class="card"><span>занято</span><strong>${load.booked_hours} ч</strong></div>
    <div class="card"><span>свободно</span><strong>${load.free_hours} ч</strong></div>
    <div class="card"><span>ёмкость недели</span><strong>${load.capacity_hours} ч</strong></div>
    <div class="card"><span>заказов в работе</span><strong>${load.orders}</strong></div>
    <div class="card"><span>сумма</span><strong>${load.money.toLocaleString('ru-RU')} ₽</strong></div>`;
  $('load-fill').style.width = `${Math.round(load.load_share * 100)}%`;
  const body = $('workload-table').querySelector('tbody');
  body.innerHTML = '';
  if (!load.rows.length) {
    body.innerHTML = '<tr><td colspan="4" class="empty">Пока нет заказов в работе — загрузка нулевая</td></tr>';
    return;
  }
  load.rows.forEach((row) => {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td></td><td></td><td></td><td></td>';
    tr.children[0].textContent = row.title;
    tr.children[1].textContent = row.orders;
    tr.children[2].textContent = `${row.hours} ч`;
    tr.children[3].textContent = row.money.toLocaleString('ru-RU');
    body.appendChild(tr);
  });
}

// --- Правила ---

const SOURCE_LABEL = { 'настройка': 'изменено вами', 'окружение': 'задано при установке', 'по умолчанию': 'по умолчанию' };

function renderSettings() {
  const box = $('settings-list');
  box.innerHTML = '';
  state.settings.forEach((item) => {
    const row = document.createElement('div');
    row.className = 'rule';
    const choices = item.choices.length
      ? `<select class="rule-input">${item.choices
          .map((choice) => `<option value="${choice}" ${choice === item.value ? 'selected' : ''}>${choice}</option>`)
          .join('')}</select>`
      : `<input class="rule-input" type="text" value="${item.value ?? ''}" placeholder="не задано" />`;
    row.innerHTML = `
      <div class="rule-head">
        <strong></strong><span class="badge">${SOURCE_LABEL[item.source] || item.source}</span>
      </div>
      <p class="rule-help"></p>
      <div class="rule-body">
        ${choices}<span class="unit">${item.unit || ''}</span>
        <button class="primary small">Сохранить</button>
        <button class="ghost small">Сбросить</button>
      </div>`;
    row.querySelector('strong').textContent = item.label;
    row.querySelector('.rule-help').textContent = item.help;
    const input = row.querySelector('.rule-input');
    const save = row.querySelector('.primary');
    const reset = row.querySelector('.ghost');
    save.addEventListener('click', async () => {
      try {
        const updated = await api(`/settings/${item.key}`, {
          method: 'PUT',
          body: JSON.stringify({ value: String(input.value).trim(), changed_by: 'окно программы' }),
        });
        Object.assign(item, updated);
        renderSettings();
        setStatus(`«${updated.label}» — ${updated.value ?? 'пусто'}`);
      } catch (error) {
        setStatus(`Не сохранено: ${error.message}`, true);
      }
    });
    reset.addEventListener('click', async () => {
      try {
        const updated = await api(`/settings/${item.key}`, { method: 'DELETE' });
        Object.assign(item, updated);
        renderSettings();
        setStatus(`«${updated.label}» — возвращено по умолчанию`);
      } catch (error) {
        setStatus(`Не сброшено: ${error.message}`, true);
      }
    });
    box.appendChild(row);
  });
}

// --- Очередь ---

function renderQueue() {
  const box = $('queue-list');
  box.innerHTML = '';
  if (!state.queue.items.length) {
    box.innerHTML = '<p class="empty">Очередь пуста: всё разобрано</p>';
    return;
  }
  state.queue.items.forEach((item) => {
    const card = document.createElement('div');
    card.className = 'queue-item';
    card.innerHTML = `
      <div class="queue-head">
        <strong></strong>
        <span class="badge">${item.recommendation || '—'}</span>
      </div>
      <p class="reason"></p>
      <div class="queue-actions">
        <button class="primary small">Подтвердить</button>
        <button class="ghost small">Отклонить</button>
      </div>`;
    card.querySelector('strong').textContent = item.order_title;
    card.querySelector('.reason').textContent = item.review_reason || 'причина не указана';
    const decide = async (decision) => {
      try {
        await api(`/analyses/${item.analysis_id}/review`, {
          method: 'POST',
          body: JSON.stringify({ decision, comment: 'решение принято в окне программы' }),
        });
        card.remove();
        setStatus(decision === 'approved' ? 'Подтверждено' : 'Отклонено');
      } catch (error) {
        setStatus(`Не удалось: ${error.message}`, true);
      }
    };
    card.querySelector('.primary').addEventListener('click', () => decide('approved'));
    card.querySelector('.ghost').addEventListener('click', () => decide('rejected'));
    box.appendChild(card);
  });
}

// --- Заказы: какие площадки показываем ---

function enabledKeys() {
  return state.platforms.filter((item) => item.enabled).map((item) => item.key);
}

function platformPriceLabel(item) {
  if (item.status === 'blocked') return 'недоступна из России';
  if (item.best_price != null) return money(item.best_price, item.best_price_currency);
  if (item.subscription && item.subscription.length) {
    return `подписка ${money(item.subscription[0].price, item.subscription[0].currency)}`;
  }
  if (item.free_per_month) return `${item.free_per_month} в месяц`;
  return 'цена в кабинете';
}

function renderPlatformPicker() {
  const box = $('platform-picker');
  box.innerHTML = '';
  state.platforms.forEach((item) => {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'skill-chip' + (item.enabled ? ' picked' : '');
    chip.textContent = `${item.title} · ${platformPriceLabel(item)}`;
    chip.title = item.paid_warning || '';
    chip.addEventListener('click', async () => {
      chip.disabled = true;
      try {
        await api(`/platforms/${item.key}/enabled`, {
          method: 'PUT',
          body: JSON.stringify({ enabled: !item.enabled }),
        });
        await refreshPlatforms();
        await refreshOrders();
      } catch (error) {
        note('orders-warning', error.message, true);
      } finally {
        chip.disabled = false;
      }
    });
    box.appendChild(chip);
  });
}

function renderOrders() {
  $('orders-warning').textContent = state.platformsWarning || '';
  $('orders-total').textContent = state.ordersTotal
    ? `Всего заказов по выбранным площадкам: ${state.ordersTotal}`
    : 'По выбранным площадкам заказов нет';
  const body = $('orders-table').querySelector('tbody');
  body.innerHTML = '';
  if (!state.orders.length) {
    body.innerHTML = '<tr><td colspan="4" class="empty">Пусто — включите площадку или добавьте заказ</td></tr>';
    return;
  }
  state.orders.forEach((order) => {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td></td><td></td><td></td><td></td>';
    tr.children[0].textContent = `#${order.id} ${order.title}`;
    tr.children[1].textContent = order.source === 'manual' ? 'ручной ввод' : order.source;
    const low = order.budget_min != null ? order.budget_min : null;
    const high = order.budget_max != null ? order.budget_max : null;
    tr.children[2].textContent =
      low != null && high != null && low !== high
        ? `${low.toLocaleString('ru-RU')}–${high.toLocaleString('ru-RU')} ₽`
        : low != null || high != null
          ? `${(low ?? high).toLocaleString('ru-RU')} ₽`
          : 'не указан';
    tr.children[3].textContent = order.status;
    body.appendChild(tr);
  });
}

async function refreshPlatforms() {
  const payload = await api('/platforms');
  state.platforms = payload.platforms;
  state.platformsWarning = payload.paid_warning || '';
  state.platformsChecked = payload.checked_at;
  renderPlatformPicker();
  renderPlatforms();
}

function renderShortlist() {
  $('shortlist-note').textContent = state.shortlistNote;
  const box = $('shortlist-list');
  box.innerHTML = '';
  if (!state.shortlist.length) {
    box.innerHTML = '<p class="empty">Подходящих заказов нет — нажмите «Обновить ленту»</p>';
    return;
  }
  state.shortlist.forEach((fit) => {
    const card = document.createElement('div');
    card.className = 'catalog-group';
    card.innerHTML = '<span class="catalog-title plain"></span><p class="platform-line"></p>';
    card.querySelector('.catalog-title').textContent =
      `${fit.verdict_label} · #${fit.order_id} ${fit.title}`;
    card.querySelector('.platform-line').textContent = fit.reasons.join('; ');
    box.appendChild(card);
  });
}

async function refreshShortlist() {
  const payload = await api('/orders/shortlist?limit=8');
  state.shortlist = payload.items;
  state.shortlistNote = `${payload.note} Посмотрено заказов: ${payload.considered}, навыки: ${
    payload.skills.join(', ') || 'не заданы'
  }, порог бюджета: ${payload.min_budget_rub.toLocaleString('ru-RU')} ₽.`;
  renderShortlist();
}

$('refresh-feed').addEventListener('click', async () => {
  note('refresh-note', 'Собираю ленту…');
  try {
    const result = await api('/sources/refresh', {
      method: 'POST',
      body: JSON.stringify({ source: 'all', pages: 1, limit: 30 }),
    });
    const parts = result.items.map((item) =>
      item.available
        ? `${item.source}: новых ${item.created}, обновлено ${item.updated}`
        : `${item.source}: недоступно`
    );
    note('refresh-note', parts.join(' · '));
    await refreshPlatforms();
    await refreshOrders();
    await refreshShortlist();
  } catch (error) {
    note('refresh-note', error.message, true);
  }
});

async function refreshOrders() {
  // «manual» — заказы без площадки (ручной ввод, неизвестный парсер). Их не теряем:
  // выключенная площадка означает «не работаю с ней», а не «удали мои заказы».
  const keys = [...enabledKeys(), 'manual'];
  if (!keys.length) {
    state.orders = [];
    state.ordersTotal = 0;
    renderOrders();
    return;
  }
  const payload = await api(`/orders?page_size=50&platforms=${keys.join(',')}`);
  state.orders = payload.items;
  state.ordersTotal = payload.total;
  renderOrders();
}

// --- Площадки ---

function money(value, currency) {
  if (value == null) return '—';
  if (currency === 'USD') return '$' + value.toLocaleString('ru-RU');
  return value.toLocaleString('ru-RU') + ' ₽';
}

function renderPlatforms() {
  $('platforms-checked').textContent = state.platformsChecked
    ? `Проверено: ${state.platformsChecked}. Источник указан у каждой площадки.`
    : '';
  const box = $('platforms-list');
  box.innerHTML = '';
  state.platforms.forEach((item) => {
    const card = document.createElement('div');
    card.className = 'catalog-group';
    card.innerHTML = `
      <span class="catalog-title"></span>
      <p class="platform-line"></p>
      <p class="platform-line free"></p>
      <div class="catalog-items"></div>
      <p class="platform-line caveat"></p>`;
    card.querySelector('.catalog-title').textContent = `${item.title} — ${item.status_label}`;
    card.querySelector('.platform-line').textContent =
      item.best_price != null
        ? `Попытка: ${money(item.best_price, item.best_price_currency)}` +
          (item.best_price_title ? ` · ${item.best_price_title}` : '')
        : 'Цена попытки видна только в кабинете';
    card.querySelector('.free').textContent = item.free_per_month
      ? `Бесплатно: ${item.free_per_month} в месяц. ${item.free_note}`
      : item.free_note;
    const offers = card.querySelector('.catalog-items');
    [...item.packages, ...item.subscription].forEach((offer) => {
      const chip = document.createElement('span');
      chip.className = 'skill-chip picked';
      chip.textContent = `${offer.title} — ${money(offer.price, offer.currency)}` +
        (offer.note ? ` · ${offer.note}` : '');
      offers.appendChild(chip);
    });
    item.extra.forEach((row) => {
      const chip = document.createElement('span');
      chip.className = 'skill-chip';
      chip.textContent = `${row.title}: ${row.price} ${row.unit}`;
      offers.appendChild(chip);
    });
    const caveat = card.querySelector('.caveat');
    caveat.textContent = item.caveat || '';
    const source = document.createElement('a');
    source.href = item.source;
    source.className = 'source-link';
    source.textContent = 'источник цен';
    caveat.appendChild(source);
    box.appendChild(card);
  });
}

// --- Отклики ---

function renderResponses() {
  const stats = state.funnel;
  if (stats) {
    const costPerHire =
      stats.cost_per_hire != null ? `${stats.cost_per_hire.toLocaleString('ru-RU')} ₽` : 'наймов не было';
    $('funnel-cards').innerHTML = `
      <div class="card"><span>откликов</span><strong>${stats.sent}</strong></div>
      <div class="card"><span>ответили</span><strong>${stats.replied}</strong></div>
      <div class="card"><span>найм</span><strong>${stats.hired}</strong></div>
      <div class="card"><span>потрачено на отклики</span><strong>${stats.cost.toLocaleString('ru-RU')} ₽</strong></div>
      <div class="card"><span>цена найма</span><strong>${costPerHire}</strong></div>`;
  }
  const body = $('responses-table').querySelector('tbody');
  body.innerHTML = '';
  if (!state.responses.length) {
    body.innerHTML = '<tr><td colspan="5" class="empty">Откликов ещё не было</td></tr>';
    return;
  }
  state.responses.forEach((item) => {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td></td><td></td><td></td><td></td><td></td>';
    tr.children[0].textContent = `#${item.order_id} ${item.order_title}`;
    tr.children[1].textContent = item.platform;
    tr.children[2].textContent = (item.sent_at || '').replace('T', ' ').slice(0, 16);
    tr.children[3].textContent = item.cost_rub != null ? `${item.cost_rub} ₽` : '—';
    tr.children[4].textContent = item.status_label;
    body.appendChild(tr);
  });
}

$('response-add').addEventListener('click', async () => {
  const orderId = Number($('response-order').value);
  if (!orderId) {
    note('response-note', 'Укажите номер заказа', true);
    return;
  }
  const cost = Number($('response-cost').value);
  try {
    await api('/responses', {
      method: 'POST',
      body: JSON.stringify({
        order_id: orderId,
        platform: $('response-platform').value || 'manual',
        cost_rub: Number.isFinite(cost) && cost > 0 ? cost : null,
        status: 'sent',
      }),
    });
    await refreshResponses();
    note('response-note', 'Записано');
  } catch (error) {
    note('response-note', error.message, true);
  }
});

function fillPlatformSelect() {
  const select = $('response-platform');
  state.platforms.forEach((item) => {
    const option = document.createElement('option');
    option.value = item.key;
    option.textContent =
      item.best_price != null
        ? `${item.title} (${money(item.best_price, item.best_price_currency)} за попытку)`
        : item.title;
    option.dataset.cost = item.best_price != null ? String(item.best_price) : '';
    select.appendChild(option);
  });
  select.addEventListener('change', () => {
    const chosen = select.selectedOptions[0];
    if (chosen && chosen.dataset.cost) {
      $('response-cost').value = chosen.dataset.cost;
    }
  });
}

async function refreshResponses() {
  const [responses, funnel] = await Promise.all([api('/responses'), api('/responses/funnel')]);
  state.responses = responses;
  state.funnel = funnel;
  renderResponses();
}

// --- Прогоны ---

function renderRuns() {
  const body = $('runs-table').querySelector('tbody');
  body.innerHTML = '';
  if (!state.runs.length) {
    body.innerHTML = '<tr><td colspan="8" class="empty">Прогонов ещё не было</td></tr>';
    return;
  }
  state.runs.forEach((run) => {
    const tr = document.createElement('tr');
    const tokens = run.tokens_in != null || run.tokens_out != null
      ? `${run.tokens_in ?? 0} / ${run.tokens_out ?? 0}`
      : 'нет данных';
    tr.innerHTML = '<td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>';
    const cells = [
      run.id,
      run.kind,
      run.model || '—',
      run.orders_total,
      run.review_share != null ? `${Math.round(run.review_share * 100)}%` : '—',
      tokens,
      run.cost_rub_text || 'цена не задана',
      (run.started_at || '').replace('T', ' ').slice(0, 16),
    ];
    cells.forEach((value, index) => {
      tr.children[index].textContent = value;
    });
    body.appendChild(tr);
  });
}

// --- Загрузка данных ---

async function loadAll() {
  setStatus('загружаю данные…');
  try {
    const [catalog, platforms, profile, norms, settings, workload, queue, runs, responses, funnel] =
      await Promise.all([
        api('/time-norms/skills-catalog'),
        api('/platforms'),
      api('/profiles/active'),
      api('/time-norms'),
      api('/settings'),
      api('/time-norms/workload'),
      api('/review-queue?review_status=pending&page_size=50'),
        api('/runs'),
        api('/responses'),
        api('/responses/funnel'),
      ]);
    state.catalog = catalog.professions;
    state.platforms = platforms.platforms;
    state.platformsChecked = platforms.checked_at;
    state.platformsWarning = platforms.paid_warning || '';
    fillPlatformSelect();
    Object.assign(state, { profile, norms, settings, workload, queue, runs, responses, funnel });
    renderProfile();
    renderCatalog();
    renderNorms();
    renderWorkload();
    renderSettings();
    renderQueue();
    renderPlatformPicker();
    renderPlatforms();
    renderResponses();
    renderRuns();
    await refreshOrders();
    await refreshShortlist();
    setStatus('готово');
  } catch (error) {
    setStatus(`Ядро не отвечает: ${error.message}`, true);
  }
}

loadAll();

// --- Хук для самопроверки из main.js ---

window.selftest = {
  catalog: () => state.catalog,
  profile: () => state.profile,
  norms: () => state.norms,
  settings: () => state.settings,
  workload: () => state.workload || { capacity_hours: null },
  queue: () => state.queue || { total: null },
  funnel: () => state.funnel,
  platforms: () => state.platforms,
  orders: () => ({ items: state.orders, total: state.ordersTotal }),
  shortlist: () => state.shortlist,
  runs: () => state.runs,
  show,
};
