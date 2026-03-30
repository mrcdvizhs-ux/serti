# Telegram-бот для генерации и управления PDF-сертификатами (OpenCart/ocStore 3)

Этот бот:
- создаёт сертификат через API модуля GiftCert PDF,
- отправляет PDF прямо в Telegram,
- по желанию отправляет на email (через модуль),
- показывает «Журнал» (последние записи) и действия под каждым сертификатом,
- умеет показать сертификат по коду (`/scan 123456`) и по deep-link (`/start gc_123456`),
- умеет отметить сертификат как **использованный** и **аннулировать**.

## 1) Что нужно подготовить в OpenCart
1) Установите модуль GiftCert PDF (ваш OCMOD ZIP).
2) В настройках модуля задайте **API токен** (любая длинная строка).
3) Очистите кеш модификаторов и обновите.

### API endpoints (используются ботом)
- POST: `index.php?route=extension/module/giftcert_pdf_api/create`
- GET:  `index.php?route=extension/module/giftcert_pdf_api/pdf&giftcert_id=123` (или `&code=123456`)
- GET:  `index.php?route=extension/module/giftcert_pdf_api/list`
- POST: `index.php?route=extension/module/giftcert_pdf_api/resend`
- POST: `index.php?route=extension/module/giftcert_pdf_api/annul`
- POST: `index.php?route=extension/module/giftcert_pdf_api/delete`
- GET:  `index.php?route=extension/module/giftcert_pdf_api/get&code=123456` (или `&giftcert_id=123`)
- POST: `index.php?route=extension/module/giftcert_pdf_api/use`

## 2) Настройка бота (long polling)

### Установка
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Переменные окружения
Бот читает переменные из файла:
- по умолчанию: `.env.example` (если есть),
- либо `.env`,
- либо можно явно указать файл: `ENV_FILE=.env.example python bot.py`.

Создайте файл `.env.example` или `.env` рядом с `bot.py`:

```ini
TG_BOT_TOKEN=123456789:AA...
TG_ADMIN_IDS=12345678,98765432
OC_BASE_URL=https://vrpoint-shop.by
OC_API_TOKEN=PASTE_LONG_RANDOM_TOKEN_FROM_MODULE_SETTINGS
SHEET_URL=https://docs.google.com/spreadsheets/d/.... (опционально)
```

### Запуск
```bash
python bot.py
```

## 3) Команды бота
- `/start` — меню (или `gc_123456` для показа сертификата по коду)
- `/new` — создать сертификат
- `/journal` — последние 10 записей + кнопки PDF/Email/Использовать/Аннулировать/Удалить
- `/pdf <code>` — получить PDF по коду
- `/scan <code>` — показать карточку сертификата по коду + действия
- `/sheet` — ссылка на Google-таблицу (если настроена)

## 4) Google Таблица (опционально)
Есть 2 варианта:
1) просто указать `SHEET_URL` — бот будет показывать кнопку на таблицу;
2) автообновлять таблицу через Apps Script (`google_apps_script.js`), который тянет данные из API `.../list`.
