const express = require('express');
const jwt = require('jsonwebtoken');
const cors = require('cors');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

const app = express();
const PORT = Number(process.env.PORT || 3000);
const JWT_SECRET = process.env.NEWS_API_JWT_SECRET || process.env.JWT_SECRET;
const JWT_ISSUER = process.env.NEWS_API_ISSUER || 'trusted-news-backend';
const JWT_AUDIENCE = process.env.NEWS_API_AUDIENCE || 'site-news-api';

const ROOT_DIR = __dirname;
const DATA_DIR = path.join(ROOT_DIR, 'data');
const NEWS_FILE = path.join(DATA_DIR, 'news.json');

const DEFAULT_NEWS = [
  {
    id: 'seed-economy-1',
    title: 'Центральный банк сохранил ставку на уровне 18%',
    summary: 'Регулятор указал на устойчивое инфляционное давление и рост потребительского кредитования.',
    text: 'Регулятор указал на устойчивое инфляционное давление и рост потребительского кредитования, отложив снижение ставки как минимум до конца года.',
    category: 'economy',
    author: 'Редакция',
    publishedAt: '2026-09-01T14:32:00.000Z',
    url: '#'
  }
];

function ensureStorage() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  if (!fs.existsSync(NEWS_FILE)) {
    fs.writeFileSync(NEWS_FILE, JSON.stringify({ updatedAt: new Date().toISOString(), items: DEFAULT_NEWS }, null, 2));
  }
}

function normalizeCategory(value) {
  const category = String(value || 'economy').trim().toLowerCase();
  const allowed = ['economy', 'politics', 'tech', 'society', 'sport', 'culture'];
  return allowed.includes(category) ? category : 'economy';
}

function normalizeArticle(item, index = 0) {
  if (!item || typeof item !== 'object') return null;

  const title = String(item.title || '').trim();
  const text = String(item.text || item.summary || '').trim();
  if (!title || !text) return null;

  const category = normalizeCategory(item.category);
  const publishedAt = item.publishedAt ? new Date(item.publishedAt).toISOString() : new Date().toISOString();

  return {
    id: String(item.id || `${category}-${Date.now()}-${index}-${Math.random().toString(36).slice(2, 9)}`),
    title,
    summary: String(item.summary || text).slice(0, 220),
    text,
    category,
    author: String(item.author || 'Редакция').trim() || 'Редакция',
    publishedAt,
    url: String(item.url || '#').trim() || '#'
  };
}

function readNews() {
  ensureStorage();

  try {
    const raw = fs.readFileSync(NEWS_FILE, 'utf8');
    const parsed = JSON.parse(raw);
    const items = Array.isArray(parsed) ? parsed : Array.isArray(parsed.items) ? parsed.items : DEFAULT_NEWS;

    return items
      .map((item, index) => normalizeArticle(item, index))
      .filter(Boolean)
      .sort((a, b) => new Date(b.publishedAt) - new Date(a.publishedAt));
  } catch (error) {
    console.warn('News file unreadable, using defaults:', error.message);
    return [...DEFAULT_NEWS].sort((a, b) => new Date(b.publishedAt) - new Date(a.publishedAt));
  }
}

function saveNews(items) {
  const payload = {
    updatedAt: new Date().toISOString(),
    items
  };
  fs.writeFileSync(NEWS_FILE, JSON.stringify(payload, null, 2));
}

function verifyTrustedBackend(req, res, next) {
  if (!JWT_SECRET) {
    return res.status(500).json({
      error: 'missing_jwt_secret',
      message: 'Set NEWS_API_JWT_SECRET in the environment before starting the API.'
    });
  }

  const authHeader = req.headers.authorization || '';
  const token = authHeader.startsWith('Bearer ') ? authHeader.slice(7).trim() : null;

  if (!token) {
    return res.status(401).json({
      error: 'missing_token',
      message: 'Send Authorization: Bearer <jwt>'
    });
  }

  try {
    const payload = jwt.verify(token, JWT_SECRET, {
      issuer: JWT_ISSUER,
      audience: JWT_AUDIENCE,
      algorithms: ['HS256']
    });

    const scopes = Array.isArray(payload.scopes) ? payload.scopes : [];
    const hasWriteAccess = payload.role === 'news-backend' || payload.scope === 'news:write' || scopes.includes('news:write');

    if (!hasWriteAccess) {
      return res.status(403).json({
        error: 'forbidden_role',
        message: 'JWT is valid but the backend is not trusted for news writes.'
      });
    }

    req.backend = payload;
    return next();
  } catch (error) {
    return res.status(401).json({
      error: 'invalid_token',
      message: 'JWT handshake failed: token is expired, invalid or not trusted.',
      details: error.message
    });
  }
}

app.use(express.json({ limit: '1mb' }));
app.use(cors());

app.get('/api/health', (req, res) => {
  res.json({
    ok: true,
    service: 'kurs-news-api',
    issuer: JWT_ISSUER,
    audience: JWT_AUDIENCE,
    time: new Date().toISOString()
  });
});

app.get('/api/news', (req, res) => {
  res.json({
    items: readNews(),
    total: readNews().length
  });
});

app.post('/api/news', verifyTrustedBackend, (req, res) => {
  const incoming = Array.isArray(req.body)
    ? req.body
    : Array.isArray(req.body.items)
      ? req.body.items
      : [req.body];

  const normalized = incoming
    .map((item, index) => normalizeArticle(item, index))
    .filter(Boolean);

  if (!normalized.length) {
    return res.status(400).json({
      error: 'invalid_payload',
      message: 'Expected JSON with title/text/category or an array of such objects.'
    });
  }

  const existing = readNews();
  const merged = [...normalized, ...existing];
  const unique = new Map();

  for (const item of merged) {
    const key = `${item.category}:${item.title}:${item.publishedAt}`;
    if (!unique.has(key)) {
      unique.set(key, item);
    }
  }

  const sorted = Array.from(unique.values())
    .sort((a, b) => new Date(b.publishedAt) - new Date(a.publishedAt))
    .slice(0, 50);

  saveNews(sorted);

  return res.status(201).json({
    ok: true,
    accepted: normalized.length,
    total: sorted.length,
    items: sorted.slice(0, 10)
  });
});

app.use(express.static(ROOT_DIR, { index: 'index.html' }));

app.get('*', (req, res, next) => {
  if (req.path.startsWith('/api/')) return next();
  res.sendFile(path.join(ROOT_DIR, 'index.html'));
});

app.listen(PORT, () => {
  console.log(`News API is running on http://localhost:${PORT}`);
  console.log(`Trusted JWT issuer: ${JWT_ISSUER}`);
  console.log(`Trusted audience: ${JWT_AUDIENCE}`);
});