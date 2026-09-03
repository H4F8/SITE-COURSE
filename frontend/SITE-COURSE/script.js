// ============ ЗАГРУЗКА НОВОСТЕЙ ИЗ БЭКЕНДА ============
let allArticles = [];
let currentCategoryFilter = 'all';

async function loadNewsFromAPI() {
  const feedEl = document.getElementById('liveNewsGrid');
  if (!feedEl) return;

  try {
    const res = await fetch('/news?limit=50');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const articles = await res.json();
    allArticles = Array.isArray(articles) ? articles : [];

    if (!allArticles.length) {
      feedEl.innerHTML = `
        <article class="card economy">
          <span class="tag economy">Ожидание</span>
          <h4>Новостей пока нет</h4>
          <p>Планировщик автоматически парсит RSS-ленты каждые 20 минут. Подождите немного или запустите вручную.</p>
          <div class="meta"><button onclick="triggerManualAnalysis()" style="background:#1a1a1a;color:#fff;border:1px solid #333;padding:6px 16px;border-radius:4px;cursor:pointer;">🔄 Запустить сейчас</button></div>
        </article>
      `;
      return;
    }

    renderNewsCards(allArticles, feedEl);
  } catch (error) {
    console.warn('Could not load news feed:', error);
    feedEl.innerHTML = `
      <article class="card economy">
        <span class="tag economy">⚠️ Ошибка</span>
        <h4>Сервер новостей недоступен</h4>
        <p>Проверьте, запущен ли бэкенд: python3 run.py</p>
        <div class="meta">API должен быть доступен по адресу http://localhost:8000</div>
      </article>
    `;
  }
}

function renderNewsCards(articles, container) {
  const filtered = currentCategoryFilter === 'all' 
    ? articles 
    : articles.filter(a => normalizeCategory(a.ai_category) === currentCategoryFilter);

  const items = filtered.slice(0, 12);

  if (!items.length) {
    container.innerHTML = `
      <article class="card economy">
        <span class="tag economy">Фильтр</span>
        <h4>Нет новостей в этой категории</h4>
        <p>Попробуйте выбрать другую рубрику.</p>
      </article>
    `;
    return;
  }

  container.innerHTML = items.map((item) => {
    const category = normalizeCategory(item.ai_category);
    const title = escapeHtml(item.title || 'Без названия');
    const summary = escapeHtml(item.ai_summary || item.summary || '');
    const source = escapeHtml(item.source || 'Неизвестный источник');
    const publishedAt = formatDate(item.published);
    const sentiment = item.sentiment || 'neutral';
    const trustScore = item.trust_score !== undefined && item.trust_score !== null ? Math.round(item.trust_score * 100) : null;
    const imageUrl = item.image_url ? `/images/proxy?url=${encodeURIComponent(item.image_url)}` : null;

    const sentimentColors = {
      positive: '#5FD8A6',
      negative: '#FF6B6B',
      neutral: '#FFCF6E'
    };
    const sentimentLabels = {
      positive: '📈 Позитивная',
      negative: '📉 Негативная',
      neutral: '➖ Нейтральная'
    };

    return `
      <article class="card ${category}" onclick="window.location.href='/news/${item.id}/page'" style="cursor:pointer;">
        ${imageUrl ? `<div style="width:100%;height:140px;overflow:hidden;border-radius:8px 8px 0 0;margin:-16px -16px 12px -16px;background:#1a1a1a;"><img src="${imageUrl}" alt="" style="width:100%;height:100%;object-fit:cover;" loading="lazy" onerror="this.style.display='none'"></div>` : ''}
        <span class="tag ${category}">${categoryLabel(category)}</span>
        <h4>${title}</h4>
        <p>${summary || 'Нет краткого описания'}</p>
        <div class="meta" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:4px;">
          <span>${publishedAt} · ${source}</span>
          <span style="display:flex;align-items:center;gap:6px;">
            <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${sentimentColors[sentiment] || '#888'};" title="${sentimentLabels[sentiment] || 'Неизвестно'}"></span>
            ${trustScore !== null ? `<span style="font-size:11px;color:#888;">Доверие ${trustScore}%</span>` : ''}
          </span>
        </div>
      </article>
    `;
  }).join('');
}

// ============ ОТКРЫТИЕ МОДАЛЬНОГО ОКНА С АНАЛИЗОМ ============
async function openArticleModal(articleId) {
  const article = allArticles.find(a => a.id === articleId);
  if (!article) return;

  const modal = document.createElement('div');
  modal.id = 'articleModal';
  modal.style.cssText = `
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0.8); z-index: 9999;
    display: flex; align-items: center; justify-content: center;
    padding: 20px; backdrop-filter: blur(4px);
    animation: fadeIn 0.2s ease;
  `;

  const sentimentLabels = {
    positive: '📈 Позитивная',
    negative: '📉 Негативная',
    neutral: '➖ Нейтральная'
  };

  let deepAnalysis = article;
  let hasDeepAnalysis = false;

  // Если есть ai_summary, значит анализ уже был сделан
  if (article.ai_summary && article.ai_category) {
    hasDeepAnalysis = true;
  } else {
    // Пытаемся получить глубокий анализ в реальном времени
    try {
      const res = await fetch('/ai/deep-analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: article.title,
          content: article.summary || article.ai_summary || ''
        })
      });
      if (res.ok) {
        const analysis = await res.json();
        deepAnalysis = { ...article, ...analysis };
        hasDeepAnalysis = true;
      }
    } catch (e) {
      console.warn('Deep analysis failed:', e);
    }
  }

  modal.innerHTML = `
    <div style="
      background: #0d0d0d; max-width: 700px; width: 100%; max-height: 90vh;
      border-radius: 16px; padding: 32px; overflow-y: auto;
      border: 1px solid #2a2a2a; position: relative;
      color: #e0e0e0; font-family: 'IBM Plex Sans', sans-serif;
    ">
      <button onclick="document.getElementById('articleModal').remove()" style="
        position: sticky; top: 0; float: right;
        background: none; border: none; color: #666;
        font-size: 28px; cursor: pointer; z-index: 10;
        line-height: 1;
      ">×</button>

      <span class="tag ${normalizeCategory(deepAnalysis.ai_category)}" style="font-size:14px;">${categoryLabel(normalizeCategory(deepAnalysis.ai_category))}</span>
      <h2 style="font-size:26px;margin:12px 0 8px;font-weight:700;line-height:1.2;color:#fff;">${escapeHtml(deepAnalysis.title)}</h2>
      <div style="color:#888;font-size:14px;margin-bottom:16px;">${formatDate(deepAnalysis.published)} · ${escapeHtml(deepAnalysis.source)}</div>

      ${hasDeepAnalysis ? `
        <div style="background:#1a1a1a;border-radius:10px;padding:16px;margin:12px 0;">
          <h4 style="color:#fff;margin:0 0 6px;">📝 Краткое содержание</h4>
          <p style="margin:0;line-height:1.6;">${escapeHtml(deepAnalysis.ai_summary || deepAnalysis.summary || 'Нет данных')}</p>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0;">
          <div style="background:#1a1a1a;border-radius:10px;padding:14px;">
            <div style="color:#888;font-size:12px;">КАТЕГОРИЯ</div>
            <div style="font-weight:600;">${categoryLabel(normalizeCategory(deepAnalysis.ai_category))}</div>
          </div>
          <div style="background:#1a1a1a;border-radius:10px;padding:14px;">
            <div style="color:#888;font-size:12px;">ТОНАЛЬНОСТЬ</div>
            <div style="font-weight:600;">${sentimentLabels[deepAnalysis.sentiment] || 'Неизвестно'}</div>
          </div>
          ${deepAnalysis.trust_score !== undefined && deepAnalysis.trust_score !== null ? `
          <div style="background:#1a1a1a;border-radius:10px;padding:14px;">
            <div style="color:#888;font-size:12px;">ДОСТОВЕРНОСТЬ</div>
            <div style="font-weight:600;">${Math.round(deepAnalysis.trust_score * 100)}% ${deepAnalysis.is_factual ? '✅' : '⚠️'}</div>
          </div>
          ` : ''}
          ${deepAnalysis.detected_errors && deepAnalysis.detected_errors.length ? `
          <div style="background:#1a1a1a;border-radius:10px;padding:14px;">
            <div style="color:#888;font-size:12px;">ОБНАРУЖЕННЫЕ ОШИБКИ</div>
            <div style="font-weight:600;color:#FF6B6B;">${deepAnalysis.detected_errors.length}</div>
          </div>
          ` : ''}
        </div>

        ${deepAnalysis.ai_keywords && deepAnalysis.ai_keywords.length ? `
        <div style="background:#1a1a1a;border-radius:10px;padding:14px;margin:8px 0;">
          <div style="color:#888;font-size:12px;">КЛЮЧЕВЫЕ СЛОВА</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:4px;">
            ${deepAnalysis.ai_keywords.map(k => `<span style="background:#2a2a2a;padding:4px 12px;border-radius:20px;font-size:13px;">${escapeHtml(k)}</span>`).join('')}
          </div>
        </div>
        ` : ''}

        ${deepAnalysis.fact_checks && deepAnalysis.fact_checks.length ? `
        <div style="background:#1a1a1a;border-radius:10px;padding:14px;margin:8px 0;">
          <div style="color:#888;font-size:12px;">🔍 ФАКТЫ ДЛЯ ПРОВЕРКИ</div>
          <ul style="margin:6px 0 0;padding-left:20px;">
            ${deepAnalysis.fact_checks.map(f => `<li style="margin:4px 0;">${escapeHtml(f)}</li>`).join('')}
          </ul>
        </div>
        ` : ''}

        ${deepAnalysis.recommendations && deepAnalysis.recommendations.length ? `
        <div style="background:#1a1a1a;border-radius:10px;padding:14px;margin:8px 0;">
          <div style="color:#888;font-size:12px;">💡 РЕКОМЕНДАЦИИ</div>
          <ul style="margin:6px 0 0;padding-left:20px;">
            ${deepAnalysis.recommendations.map(r => `<li style="margin:4px 0;">${escapeHtml(r)}</li>`).join('')}
          </ul>
        </div>
        ` : ''}
      ` : `
        <div style="background:#1a1a1a;border-radius:10px;padding:20px;text-align:center;color:#888;">
          <p style="margin:0;">⏳ Анализ новости выполняется...</p>
          <p style="margin:4px 0 0;font-size:13px;">Это займёт несколько секунд</p>
        </div>
      `}

      <div style="margin-top:16px;padding-top:16px;border-top:1px solid #2a2a2a;display:flex;gap:12px;flex-wrap:wrap;">
        <a href="${escapeHtml(deepAnalysis.link)}" target="_blank" style="color:#7FC7FF;text-decoration:none;font-size:14px;">🔗 Читать оригинал →</a>
        ${deepAnalysis.sources && deepAnalysis.sources.length ? `
          <span style="color:#666;font-size:13px;">📚 ${deepAnalysis.sources.length} источников</span>
        ` : ''}
      </div>
    </div>
  `;

  document.body.appendChild(modal);

  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.remove();
  });
}

// ============ ФИЛЬТРАЦИЯ ПО КАТЕГОРИЯМ ============
document.addEventListener('DOMContentLoaded', () => {
  const navLinks = document.querySelectorAll('.catnav a');
  navLinks.forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const category = link.dataset.c || 'all';
      currentCategoryFilter = category;
      
      navLinks.forEach(l => l.style.color = '');
      link.style.color = '#fff';

      const feedEl = document.getElementById('liveNewsGrid');
      renderNewsCards(allArticles, feedEl);
    });
  });
});

// ============ РУЧНОЙ ЗАПУСК АНАЛИЗА ============
async function triggerManualAnalysis() {
  try {
    const res = await fetch('/ai/scheduler/trigger', { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      alert(`✅ Анализ запущен! Найдено ${data.result?.new_articles || 0} новых статей.`);
      setTimeout(() => loadNewsFromAPI(), 3000);
    } else {
      alert('❌ Не удалось запустить анализ.');
    }
  } catch (e) {
    alert('❌ Ошибка подключения к серверу.');
  }
}

// ============ ЗАГРУЗКА СТАТУСА ПЛАНИРОВЩИКА ============
async function loadSchedulerStatus() {
  try {
    const res = await fetch('/ai/scheduler/status');
    if (res.ok) {
      const data = await res.json();
      const statusEl = document.getElementById('schedulerStatus');
      if (statusEl) {
        statusEl.textContent = data.running ? '🟢 Активен' : '🔴 Остановлен';
        statusEl.style.color = data.running ? '#5FD8A6' : '#FF6B6B';
      }
    }
  } catch (e) {
    // Игнорируем
  }
}

// ============ ОБНОВЛЕНИЕ КОЛОНКИ ГЕРОЯ ============
function updateHeroWithTopNews(articles) {
  if (!articles || !articles.length) return;
  const top = articles[0];
  const heroTitle = document.querySelector('.hero h1 a');
  const heroDek = document.querySelector('.hero .dek');
  const heroTag = document.querySelector('.hero .tag');
  const heroMeta = document.querySelector('.hero .hero-meta');
  
  if (heroTitle) heroTitle.textContent = top.title;
  if (heroDek) heroDek.textContent = top.ai_summary || top.summary || '';
  if (heroTag) {
    heroTag.textContent = (top.ai_category ? categoryLabel(normalizeCategory(top.ai_category)) : 'Главное') + ' · Главное';
    heroTag.className = `tag ${normalizeCategory(top.ai_category)}`;
  }
  if (heroMeta) {
    const time = top.published ? formatDate(top.published) : '';
    heroMeta.innerHTML = `<span>${time}</span><span>${top.source || 'Редакция'}</span>`;
  }
}

// ============ ИНИЦИАЛИЗАЦИЯ ============
document.addEventListener('DOMContentLoaded', async () => {
  await loadNewsFromAPI();
  
  if (allArticles.length) {
    updateHeroWithTopNews(allArticles);
  }
  
  await loadSchedulerStatus();
  
  setInterval(() => {
    loadNewsFromAPI();
    loadSchedulerStatus();
  }, 60000);
});

function normalizeCategory(value) {
  const category = String(value || 'economy').trim().toLowerCase();
  return ['economy', 'politics', 'tech', 'society', 'sport', 'culture'].includes(category) ? category : 'economy';
}

function categoryLabel(category) {
  const map = {
    economy: 'Экономика',
    politics: 'Политика',
    tech: 'Технологии',
    society: 'Общество',
    sport: 'Спорт',
    culture: 'Культура'
  };
  return map[category] || 'Экономика';
}

function formatDate(value) {
  if (!value) return 'сегодня';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'сегодня';

  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}


// live clock
const clockEl = document.getElementById('clock');
const dateEl = document.getElementById('fullDate');
const months = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];
const days = ['воскресенье','понедельник','вторник','среда','четверг','пятница','суббота'];

function tick(){
  const now = new Date();
  const hh = String(now.getHours()).padStart(2,'0');
  const mm = String(now.getMinutes()).padStart(2,'0');
  const ss = String(now.getSeconds()).padStart(2,'0');
  clockEl.textContent = `${hh}:${mm}:${ss}`;
  dateEl.textContent = `${days[now.getDay()]}, ${now.getDate()} ${months[now.getMonth()]}`;
}
tick();
setInterval(tick, 1000);

// ticker headlines (duplicated for seamless loop)
const headlines = [
  'Центральный банк сохранил ключевую ставку на уровне 18%',
  'Крупный ритейлер объявил о выходе на биржу',
  'Стартап привлёк раунд на разработку чипов для ИИ',
  'Сборная вышла в полуфинал после победы в дополнительное время',
  'Правительство внесло в парламент проект бюджета на три года',
  'Городская галерея открыла выставку архитектурных утопий XX века'
];
const track = document.getElementById('tickerTrack');
const loopContent = [...headlines, ...headlines].map(h => `<span>${h}</span>`).join('');
track.innerHTML = loopContent;

// ============ LIVE MARKET DATA ============
// Real public APIs only, with a fallback chain per metric in case the
// primary source doesn't respond (network/CORS/rate-limit). Whichever
// source actually answers is what gets shown, and the caption says which
// one it was. If nothing answers, the field says "нет данных" — never a
// made-up number.

function setMkt(prefix, valueText, deltaText, isUp){
  const el = document.getElementById('mkt-' + prefix);
  if (!el) return;
  el.querySelector('.num').textContent = valueText;
  const deltaEl = el.querySelector('.delta');
  deltaEl.textContent = deltaText || '';
  deltaEl.classList.toggle('up', !!isUp);
  deltaEl.classList.toggle('down', isUp === false);
}
function setMktError(prefix){
  const el = document.getElementById('mkt-' + prefix);
  if (!el) return;
  el.querySelector('.num').textContent = 'нет данных';
  el.querySelector('.delta').textContent = '';
}
function setMktLabel(prefix, label){
  const el = document.getElementById('mkt-' + prefix);
  if (!el) return;
  el.querySelector('.name').textContent = label;
}
function fmtRub(n){
  return n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtPct(n){
  const sign = n >= 0 ? '▲' : '▼';
  return sign + Math.abs(n).toFixed(2).replace('.', ',') + '%';
}

const sourcesUsed = {};

// --- USD/RUB & EUR/RUB ---
// Primary: cbr-xml-daily.ru, a mirror that republishes the Bank of Russia's
// own official daily rates (cbr.ru itself blocks cross-origin browser
// requests, so it can't be fetched directly from here).
// Fallback: open.er-api.com, a general free market-rate API — not the
// central bank, but a real live source if the mirror doesn't answer.
async function loadRubPairs(){
  try{
    const res = await fetch('https://www.cbr-xml-daily.ru/daily_json.js');
    if (!res.ok) throw new Error('cbr mirror http ' + res.status);
    const data = await res.json();
    const usd = data.Valute.USD, eur = data.Valute.EUR;
    const usdDelta = (usd.Value - usd.Previous) / usd.Previous * 100;
    const eurDelta = (eur.Value - eur.Previous) / eur.Previous * 100;
    setMkt('usd', fmtRub(usd.Value), fmtPct(usdDelta), usdDelta >= 0);
    setMkt('eur', fmtRub(eur.Value), fmtPct(eurDelta), eurDelta >= 0);
    setMktLabel('usd', 'USD / RUB · ЦБ РФ');
    setMktLabel('eur', 'EUR / RUB · ЦБ РФ');
    sourcesUsed.rub = `USD/EUR — официальный курс ЦБ РФ на ${data.Date.slice(0,10).split('-').reverse().join('.')} (через зеркало cbr-xml-daily.ru)`;
    return;
  } catch(e){
    console.error('CBR mirror failed, trying fallback', e);
  }
  try{
    const [usdRes, eurRes] = await Promise.all([
      fetch('https://open.er-api.com/v6/latest/USD'),
      fetch('https://open.er-api.com/v6/latest/EUR')
    ]);
    if (!usdRes.ok || !eurRes.ok) throw new Error('er-api http error');
    const usdData = await usdRes.json();
    const eurData = await eurRes.json();
    setMkt('usd', fmtRub(usdData.rates.RUB), '');
    setMkt('eur', fmtRub(eurData.rates.RUB), '');
    setMktLabel('usd', 'USD / RUB · рыночный курс');
    setMktLabel('eur', 'EUR / RUB · рыночный курс');
    sourcesUsed.rub = 'USD/EUR — рыночный курс, open.er-api.com (запасной источник, курс ЦБ РФ был недоступен)';
  } catch(e){
    console.error('RUB fallback failed too', e);
    setMktError('usd');
    setMktError('eur');
    sourcesUsed.rub = 'USD/EUR — источники недоступны';
  }
}

// --- MOEX Russia Index ---
// Official Moscow Exchange ISS API. Field names differ slightly depending
// on whether the market is open, so several are tried before giving up.
async function loadMOEX(){
  try{
    const url = 'https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX.json?iss.meta=off';
    const res = await fetch(url);
    if (!res.ok) throw new Error('moex http ' + res.status);
    const data = await res.json();
    const cols = data.marketdata.columns;
    const row = data.marketdata.data[0];
    if (!row) throw new Error('moex: no row');
    const pick = (...names) => {
      for (const n of names){
        const i = cols.indexOf(n);
        if (i !== -1 && row[i] != null) return row[i];
      }
      return null;
    };
    const last = pick('LASTVALUE', 'CURRENTVALUE', 'OPEN');
    const pct = pick('LASTTOPREVPRICE', 'CHANGE');
    if (last == null) throw new Error('moex: no value in any known column');
    setMkt('moex', last.toLocaleString('ru-RU', { maximumFractionDigits: 2 }), pct != null ? fmtPct(pct) : '', pct != null ? pct >= 0 : undefined);
    sourcesUsed.moex = 'Индекс МосБиржи — официальный MOEX ISS API (iss.moex.com)';
  } catch(e){
    console.error('MOEX fetch failed', e);
    setMktError('moex');
    sourcesUsed.moex = 'Индекс МосБиржи — источник недоступен';
  }
}

// --- BTC/USD ---
// Primary: CoinGecko public API. Fallback: Coinbase's public spot-price
// endpoint (no 24h change, just the current price).
async function loadBTC(){
  try{
    const url = 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true';
    const res = await fetch(url);
    if (!res.ok) throw new Error('coingecko http ' + res.status);
    const data = await res.json();
    const price = data.bitcoin.usd;
    const change = data.bitcoin.usd_24h_change;
    setMkt('btc', Math.round(price).toLocaleString('ru-RU'), change != null ? fmtPct(change) : '', change != null ? change >= 0 : undefined);
    sourcesUsed.btc = 'BTC/USD — CoinGecko API (api.coingecko.com)';
    return;
  } catch(e){
    console.error('CoinGecko failed, trying fallback', e);
  }
  try{
    const res = await fetch('https://api.coinbase.com/v2/prices/BTC-USD/spot');
    if (!res.ok) throw new Error('coinbase http ' + res.status);
    const data = await res.json();
    setMkt('btc', Math.round(parseFloat(data.data.amount)).toLocaleString('ru-RU'), '');
    sourcesUsed.btc = 'BTC/USD — Coinbase Spot Price API (запасной источник)';
  } catch(e){
    console.error('BTC fallback failed too', e);
    setMktError('btc');
    sourcesUsed.btc = 'BTC/USD — источники недоступны';
  }
}

async function refreshMarkets(){
  const sourceEl = document.getElementById('mktSource');
  await Promise.all([loadRubPairs(), loadMOEX(), loadBTC()]);
  const now = new Date();
  const stamp = String(now.getHours()).padStart(2,'0') + ':' + String(now.getMinutes()).padStart(2,'0') + ':' + String(now.getSeconds()).padStart(2,'0');
  sourceEl.innerHTML = `Обновлено ${stamp} · ${sourcesUsed.rub} · ${sourcesUsed.moex} · ${sourcesUsed.btc}`;
}

refreshMarkets();
setInterval(refreshMarkets, 60000);