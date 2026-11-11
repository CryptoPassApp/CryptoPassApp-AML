# 🛡️ CryptoPassApp — P2P Security · AML Wallet Scanner · Web3 Trust Pass (TON)

Turnkey-проект: Telegram Mini App + Bot для проверки TON-кошельков на AML-риски,
генерации Web3 Trust Passport и оценки контрагента перед P2P-сделкой.

**Три продукта в одном боте:**
1. 🛡️ **AML Wallet Scanner** — проверка кошелька на «грязные» транзакции, миксеры, санкционные связи
2. 🪪 **Web3 Trust Passport** — цифровой паспорт кошелька с Trust Score 0–100 и радаром репутации
3. 🔍 **P2P Security Radar** — поведенческие паттерны и флаги риска контрагента

Витрина (Mini App) работает автономно на GitHub Pages в **Demo Mode** (без бэкенда),
полный режим — ботом + API из Docker.

---

## Стек

- **Бот:** Python 3.11 · aiogram 3.x · FSM
- **API:** FastAPI · uvicorn · SQLAlchemy 2 async · aiosqlite (SQLite)
- **Блокчейн:** TonAPI v2 (`https://tonapi.io`) — без ключа для базовых запросов
- **Платежи:** Telegram Stars (XTR)
- **Фронтенд:** один файл `static/index.html` · TailwindCSS CDN · Vanilla JS · Telegram WebApp SDK
- **Деплой:** Docker + docker-compose

## Структура

```
cryptopassapp/
├── bot/                  # Telegram-бот (aiogram 3)
│   ├── handlers/         # start, scanner, passport, subscription, admin, language
│   ├── services/         # ton_api, aml_engine, trust_score, passport_generator, stars_payment
│   ├── locales/          # ru.json, en.json
│   ├── config.py         # Pydantic Settings (.env)
│   ├── database.py       # async engine + session (SQLite, WAL)
│   ├── keyboards.py      # inline-клавиатуры
│   └── middleware.py     # AuthMiddleware — авто-регистрация пользователей
├── api/                  # FastAPI
│   ├── routes/           # scan, passport, user, admin, demo
│   ├── dependencies.py   # валидация WebApp initData (HMAC-SHA256), admin-токен
│   └── main.py           # app + CORS + static
├── static/index.html     # ВЕСЬ фронтенд Mini App (SPA, 5 экранов)
├── data/                 # SQLite-база + blocklists.json (создаётся автоматически)
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Быстрый старт (локально)

```bash
cd cryptopassapp
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # заполни BOT_TOKEN, ADMIN_IDS, MINI_APP_URL, API_SECRET_KEY

# 1) API (порт 8000, раздаёт и static/index.html)
uvicorn api.main:app --reload

# 2) Бот (в отдельном терминале)
python -m bot.main
```

Мини-ап сразу можно открыть: `http://localhost:8000/` — без Telegram-контекста
включается **Demo Mode** (3 пресета: Clean / Medium / Critical).

## Деплой через Docker

```bash
cp .env.example .env   # заполнить!
docker compose up -d --build
```

Поднимаются два сервиса: `bot` (polling) и `api` (uvicorn :8000, том `./data`).
Фронтенд для GitHub Pages: просто скопируй `static/index.html` в репозиторий Pages —
он автономно работает в Demo Mode.

## Настройка Mini App в BotFather

1. `/newapp` → выбери бота → URL: `https://<твой-домен>/` (или GitHub Pages URL)
2. Кнопка меню бота уже настроена через `WebAppInfo(MINI_APP_URL)` из `.env`

## Переменные окружения (.env)

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | токен из @BotFather |
| `ADMIN_IDS` | Telegram ID админов через запятую (доступ к /admin) |
| `MINI_APP_URL` | публичный URL Mini App (кнопка в боте) |
| `API_SECRET_KEY` | секрет для `/api/admin/*` (заголовок `X-Admin-Token`) |
| `TON_API_KEY` | опционально, для повышенных лимитов TonAPI |
| `DATABASE_URL` | по умолчанию `sqlite+aiosqlite:///./data/cryptopass.db` |
| `DEMO_MODE` | флаг демо-режима (для витрины) |

## API

| Метод | Путь | Auth | Описание |
|---|---|---|---|
| POST | `/api/scan` | initData | Скан кошелька (лимиты FREE/PRO) |
| GET | `/api/scan/{address}` | initData | Последний результат скана |
| GET | `/api/passport/{address}` | initData | Trust Passport (PRO) |
| GET | `/api/user/me` | initData | Профиль и лимиты |
| POST | `/api/user/language` | initData | Смена языка |
| GET | `/api/user/history` | initData | История сканов (PRO) |
| POST | `/api/user/invoice` | initData | Ссылка на оплату Stars |
| GET | `/api/demo/{preset}` | — | Demo-данные: clean / medium / critical |
| GET | `/api/admin/stats` | X-Admin-Token | Статистика |
| POST | `/api/admin/broadcast` | X-Admin-Token | Рассылка |
| POST | `/api/admin/grant_pro` | X-Admin-Token | Выдать PRO вручную |

Auth `initData` = заголовок `X-Telegram-Init-Data` с подписанной строкой из
`Telegram.WebApp.initData` (проверяется HMAC-SHA256, как в официальной документации).

## AML-движок

`bot/services/aml_engine.py` — эвристический скоринг по флагам:

| Флаг | Очки |
|---|---|
| mixer_interaction | +35 |
| sanctioned_address | +50 |
| p2p_fraud_pattern | +30 |
| high_velocity | +15 |
| new_wallet | +10 |
| darknet_exposure | +45 |
| rug_pull_interaction | +25 |
| exchange_only | −10 |
| old_wallet_clean | −15 |

Уровни: 0–20 clean · 21–40 low · 41–60 medium · 61–80 high · 81–100 critical.
Trust Score = 100 − Risk Score.

Списки адресов лежат в `data/blocklists.json` (ключи: `mixers`, `sanctioned`,
`darknet`, `rugpulls`, `exchanges`) — пополняются без пересборки.

## Тарифы (Telegram Stars)

| Тариф | Цена | Лимит |
|---|---|---|
| FREE | 0 | 3 скана/день, без паспорта/истории |
| PRO месяц | 150 ⭐ | 50 сканов/день + все функции |
| PRO год | 999 ⭐ | безлимит + все функции |

## Команды бота

`/start` — меню с кнопкой Mini App · `/passport` — Trust Passport ·
`/pro` — тарифы и оплата Stars · `/lang` — RU/EN · `/admin` — панель админа (ADMIN_IDS)

## Лицензия и дисклеймер

Код поставляется как есть. Оценки риска — эвристические и не являются
финансовой или юридической рекомендацией.
