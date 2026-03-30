#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import io
import json
import asyncio
import logging
import requests

from dotenv import load_dotenv, find_dotenv

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ---------------------------
# Logging
# ---------------------------
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("giftcert_bot")

# ---------------------------
# Non-admin scan text (ONLY for scan/deeplink)
# ---------------------------
NON_ADMIN_SCAN_TEXT = (
    "Чтобы воспользоваться 🎁 Подарочным сертификатом, приглашаем вас в нашу виртуальную арену VRPOINT.BY 🕶✨\n"
    "Забронировать услугу можно на сайте: https://vrpoint.by 🌐\n\n"
    "📍 Наши адреса в Минске:\n"
    "• Я. Коласа, 37\n"
    "• Маяковского, 6 (ТЦ «Червенский»)\n\n"
    "📞 Телефон для связи: +375291419921\n\n"
    "До встречи в VR 🚀🎮"
)

# ---------------------------
# Load env
# Priority:
# 1) ENV_FILE (if set)
# 2) .env.example
# 3) .env
# ---------------------------
env_file = (os.getenv("ENV_FILE") or "").strip()
dotenv_path = None
if env_file:
    dotenv_path = find_dotenv(env_file) or env_file
else:
    dotenv_path = find_dotenv(".env.example") or find_dotenv(".env")

if dotenv_path and os.path.exists(dotenv_path):
    load_dotenv(dotenv_path, override=False)
    logger.info("Loaded env from: %s", dotenv_path)
else:
    logger.warning("No env file found. Provide env vars via OS or add .env.example/.env рядом с bot.py")

TG_BOT_TOKEN = (os.getenv("TG_BOT_TOKEN") or "").strip()
TG_ADMIN_IDS = {
    int(x.strip())
    for x in (os.getenv("TG_ADMIN_IDS") or "").split(",")
    if x.strip().isdigit()
}

OC_BASE_URL_RAW = (os.getenv("OC_BASE_URL") or "").strip()
OC_BASE_URL = OC_BASE_URL_RAW.rstrip("/")
OC_API_TOKEN = (os.getenv("OC_API_TOKEN") or "").strip()
SHEET_URL = (os.getenv("SHEET_URL") or "").strip()

# API endpoints
API_CREATE = (OC_BASE_URL + "/" if OC_BASE_URL else "") + "index.php?route=extension/module/giftcert_pdf_api/create"
API_PDF    = (OC_BASE_URL + "/" if OC_BASE_URL else "") + "index.php?route=extension/module/giftcert_pdf_api/pdf"
API_LIST   = (OC_BASE_URL + "/" if OC_BASE_URL else "") + "index.php?route=extension/module/giftcert_pdf_api/list"
API_RESEND = (OC_BASE_URL + "/" if OC_BASE_URL else "") + "index.php?route=extension/module/giftcert_pdf_api/resend"
API_ANNUL  = (OC_BASE_URL + "/" if OC_BASE_URL else "") + "index.php?route=extension/module/giftcert_pdf_api/annul"
API_DELETE = (OC_BASE_URL + "/" if OC_BASE_URL else "") + "index.php?route=extension/module/giftcert_pdf_api/delete"
API_GET    = (OC_BASE_URL + "/" if OC_BASE_URL else "") + "index.php?route=extension/module/giftcert_pdf_api/get"
API_USE    = (OC_BASE_URL + "/" if OC_BASE_URL else "") + "index.php?route=extension/module/giftcert_pdf_api/use"

# Conversation states
AMOUNT, RECIPIENT_NAME, DONOR_FIRST, DONOR_LAST, RECIPIENT_EMAIL, ACTION = range(6)

# ---------------------------
# Helpers
# ---------------------------
def is_admin(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else 0
    # если список админов пуст — пускаем всех
    return (not TG_ADMIN_IDS) or (uid in TG_ADMIN_IDS)

def api_headers():
    return {"X-Giftcert-Token": OC_API_TOKEN, "Content-Type": "application/json"}

def safe_json(resp: requests.Response) -> dict:
    try:
        return resp.json()
    except Exception:
        return {"success": False, "error": f"Bad response: {resp.status_code}", "raw": resp.text}

def api_create(payload: dict) -> dict:
    try:
        r = requests.post(API_CREATE, headers=api_headers(), data=json.dumps(payload), timeout=40)
        return safe_json(r)
    except requests.RequestException as e:
        return {"success": False, "error": f"Network error: {e}"}

def api_list(params: dict) -> dict:
    try:
        r = requests.get(API_LIST, headers={"X-Giftcert-Token": OC_API_TOKEN}, params=params, timeout=40)
        return safe_json(r)
    except requests.RequestException as e:
        return {"success": False, "error": f"Network error: {e}"}

def api_post(url: str, payload: dict) -> dict:
    try:
        r = requests.post(url, headers=api_headers(), data=json.dumps(payload), timeout=40)
        return safe_json(r)
    except requests.RequestException as e:
        return {"success": False, "error": f"Network error: {e}"}

def api_get(giftcert_id: int = 0, code: str = "") -> dict:
    params = {}
    if giftcert_id:
        params["giftcert_id"] = int(giftcert_id)
    if code:
        params["code"] = str(code)
    try:
        r = requests.get(API_GET, headers={"X-Giftcert-Token": OC_API_TOKEN}, params=params, timeout=40)
        return safe_json(r)
    except requests.RequestException as e:
        return {"success": False, "error": f"Network error: {e}"}

def api_use(giftcert_id: int = 0, code: str = "", note: str = "Использован через Telegram") -> dict:
    payload = {"note": note}
    if giftcert_id:
        payload["giftcert_id"] = int(giftcert_id)
    if code:
        payload["code"] = str(code)
    try:
        r = requests.post(API_USE, headers=api_headers(), data=json.dumps(payload), timeout=40)
        return safe_json(r)
    except requests.RequestException as e:
        return {"success": False, "error": f"Network error: {e}"}

def api_download_pdf(giftcert_id: int = 0, code: str = "") -> bytes:
    params = {}
    if giftcert_id:
        params["giftcert_id"] = int(giftcert_id)
    if code:
        params["code"] = str(code)
    try:
        r = requests.get(API_PDF, headers={"X-Giftcert-Token": OC_API_TOKEN}, params=params, timeout=60)
    except requests.RequestException as e:
        raise RuntimeError(f"Network error: {e}") from e

    if r.status_code != 200:
        raise RuntimeError(f"PDF download failed: {r.status_code} {r.text[:200]}")
    return r.content

# ---- Formatting helpers (HTML) ----
def esc_html(s: str) -> str:
    s = "" if s is None else str(s)
    return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def status_emoji(status: str) -> str:
    s = (status or "").lower()
    if s == "used":
        return "♻️"
    if s == "annulled":
        return "🚫"
    if "error" in s:
        return "⚠️"
    return "✅"

def status_label(status: str) -> str:
    s = (status or "").lower()
    if s == "used":
        return "Использован"
    if s == "annulled":
        return "Аннулирован"
    if s == "sent":
        return "Отправлен"
    if s == "manual":
        return "Создан вручную"
    if s == "send_error":
        return "Ошибка отправки"
    return status or "—"

def format_cert(cert: dict) -> str:
    gid = cert.get("giftcert_id", "")
    code = cert.get("code", "")
    amount = cert.get("amount", "")
    st = cert.get("status", "")
    src = cert.get("source") or "—"

    lines = []
    lines.append("🎟 <b>Сертификат</b>")
    lines.append(f"ID: <b>{esc_html(gid)}</b>")
    lines.append(f"Код: <b>{esc_html(code)}</b>")
    lines.append(f"Сумма: <b>{esc_html(amount)} BYN</b>")
    lines.append(f"Статус: {status_emoji(st)} <b>{esc_html(status_label(st))}</b>")
    lines.append(f"Источник: <code>{esc_html(src)}</code>")

    rn = (cert.get("recipient_name") or "").strip()
    reml = (cert.get("recipient_email") or "").strip()
    if rn or reml:
        lines.append(f"Получатель: <b>{esc_html(rn or '—')}</b> — {esc_html(reml or '—')}")

    donor = ((cert.get("lastname") or "") + " " + (cert.get("firstname") or "")).strip()
    if donor:
        lines.append(f"Даритель: <b>{esc_html(donor)}</b>")

    for k, title in [("created_at","Создан"),("sent_at","Отправлен"),("used_at","Использован"),("annulled_at","Аннулирован")]:
        v = (cert.get(k) or "").strip()
        if v:
            lines.append(f"{title}: <code>{esc_html(v)}</code>")

    oid = int(cert.get("order_id") or 0)
    if oid:
        lines.append(f"Заказ: <code>#{oid}</code>")

    return "\n".join(lines)

def build_cert_keyboard(cert: dict) -> InlineKeyboardMarkup:
    gid = int(cert.get("giftcert_id") or 0)
    st = (cert.get("status") or "").lower()

    rows = [
        [
            InlineKeyboardButton("📄 PDF", callback_data=f"pdf:{gid}"),
            InlineKeyboardButton("✉️ Email", callback_data=f"email:{gid}"),
        ]
    ]

    if st not in ("used", "annulled"):
        rows.append([
            InlineKeyboardButton("✅ Использовать", callback_data=f"use:{gid}"),
            InlineKeyboardButton("🚫 Аннулировать", callback_data=f"annul:{gid}"),
        ])

    rows.append([InlineKeyboardButton("🗑 Удалить", callback_data=f"del:{gid}")])

    return InlineKeyboardMarkup(rows)

async def fetch_cert_by_id(giftcert_id: int):
    resp = api_get(giftcert_id=giftcert_id)
    if not resp.get("success"):
        return None, (resp.get("error") or resp.get("message") or resp.get("raw") or "Не найден.")
    return (resp.get("cert") or {}), ""

async def show_cert_by_code(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    resp = api_get(code=code)
    if not resp.get("success"):
        msg = resp.get("error") or resp.get("message") or resp.get("raw") or "Сертификат не найден."
        await update.message.reply_text(f"❌ Сертификат не найден.\nКод: {code}\n\n{str(msg)[:300]}")
        return
    cert = resp.get("cert") or {}
    await update.message.reply_text(format_cert(cert), reply_markup=build_cert_keyboard(cert), parse_mode="HTML")


# ---------------------------
# Commands / Handlers
# ---------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Требование:
    - НЕ админ должен получать приглашение ТОЛЬКО при скане кода (deep-link /start gc_XXXX).
    - В остальных случаях не-админу ничего не показываем (можно оставить "Доступ ограничен").
    """

    # deep-link: /start gc_123456
    payload = ""
    if getattr(context, "args", None) and context.args:
        payload = (context.args[0] or "").strip()

    # Если пришли по ссылке/QR с кодом (это и есть "сканирование")
    if payload:
        code = ""
        if payload.startswith(("gc_", "gc-")):
            code = "".join(ch for ch in payload[3:] if ch.isdigit())
        else:
            code = "".join(ch for ch in payload if ch.isdigit())

        if code and (not is_admin(update)):
            # ✅ Только здесь показываем текст не-админу
            await update.message.reply_text(NON_ADMIN_SCAN_TEXT, disable_web_page_preview=False)
            return

        if code:
            # ✅ Админу показываем карточку сертификата
            await show_cert_by_code(update, context, code)
            return

    # /start без кода
    if not is_admin(update):
        await update.message.reply_text("Доступ ограничен.")
        return

    kb = [
        ["➕ Создать сертификат", "📒 Журнал"],
    ]
    if SHEET_URL:
        kb.append(["🔗 Открыть Google-таблицу"])

    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
    )

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    text = (update.message.text or "").strip()
    if text == "➕ Создать сертификат":
        return await new_cmd(update, context)
    if text == "📒 Журнал":
        return await journal_cmd(update, context)
    if text == "🔗 Открыть Google-таблицу" and SHEET_URL:
        return await sheet_cmd(update, context)

async def sheet_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Доступ ограничен.")
        return
    if not SHEET_URL:
        await update.message.reply_text("Ссылка на таблицу не настроена.")
        return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Открыть журнал", url=SHEET_URL)]])
    await update.message.reply_text("Журнал сертификатов:", reply_markup=kb)

async def new_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Доступ ограничен.")
        return ConversationHandler.END

    context.user_data.clear()
    await update.message.reply_text(
        "Введите сумму (BYN), только цифры. Например: 70\n\n/cancel — отмена",
        reply_markup=ReplyKeyboardRemove(),
    )
    return AMOUNT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if update.message:
        await update.message.reply_text("Отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def on_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = (update.message.text or "").strip()
    if not s.isdigit() or int(s) <= 0:
        await update.message.reply_text("Нужно число > 0. Пример: 70")
        return AMOUNT
    context.user_data["amount"] = int(s)
    await update.message.reply_text("Имя получателя (опционально). Или напишите '-' чтобы пропустить.")
    return RECIPIENT_NAME

async def on_recipient_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = (update.message.text or "").strip()
    context.user_data["recipient_name"] = "" if s == "-" else s
    await update.message.reply_text("Имя дарителя (опционально). Или '-' чтобы пропустить.")
    return DONOR_FIRST

async def on_donor_first(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = (update.message.text or "").strip()
    context.user_data["firstname"] = "" if s == "-" else s
    await update.message.reply_text("Фамилия дарителя (опционально). Или '-' чтобы пропустить.")
    return DONOR_LAST

async def on_donor_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = (update.message.text or "").strip()
    context.user_data["lastname"] = "" if s == "-" else s
    await update.message.reply_text("Email получателя (опционально). Или '-' чтобы пропустить.")
    return RECIPIENT_EMAIL

async def on_recipient_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = (update.message.text or "").strip()
    context.user_data["recipient_email"] = "" if s == "-" else s

    amount = context.user_data.get("amount")
    recipient_name = context.user_data.get("recipient_name", "")
    firstname = context.user_data.get("firstname", "")
    lastname = context.user_data.get("lastname", "")
    recipient_email = context.user_data.get("recipient_email", "")

    summary = (
        f"Проверьте данные:\n"
        f"• Сумма: {amount} BYN\n"
        f"• Получатель: {recipient_name or '—'}\n"
        f"• Даритель: {(firstname + ' ' + lastname).strip() or '—'}\n"
        f"• Email: {recipient_email or '—'}\n\n"
        "Как отправить?"
    )
    kb = ReplyKeyboardMarkup(
        [["📄 PDF в Telegram", "✉️ На email"], ["❌ Отмена"]],
        resize_keyboard=True,
    )
    await update.message.reply_text(summary, reply_markup=kb)
    return ACTION

async def on_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text == "❌ Отмена":
        return await cancel(update, context)

    send_email = (text == "✉️ На email")
    payload = {
        "amount": context.user_data.get("amount", 0),
        "recipient_name": context.user_data.get("recipient_name", ""),
        "firstname": context.user_data.get("firstname", ""),
        "lastname": context.user_data.get("lastname", ""),
        "recipient_email": context.user_data.get("recipient_email", ""),
        "send_email": bool(send_email),
        # если ваш API поддерживает — можно добавить:
        # "source": "telegram",
    }

    if send_email and not payload["recipient_email"]:
        await update.message.reply_text("Вы выбрали email, но email не указан. Введите email или выберите PDF в Telegram.")
        return ACTION

    await update.message.reply_text("Генерирую сертификат…")

    resp = api_create(payload)
    if not resp.get("success"):
        await update.message.reply_text(f"Ошибка API: {resp.get('error')}\n{str(resp.get('raw',''))[:500]}")
        return ConversationHandler.END

    giftcert_id = int(resp.get("giftcert_id") or 0)
    code = resp.get("code", "")
    amount = resp.get("amount", payload["amount"])

    try:
        pdf_bytes = api_download_pdf(giftcert_id=giftcert_id)
        bio = io.BytesIO(pdf_bytes)
        bio.name = f"Certificate_{code or giftcert_id}.pdf"
        caption = f"Сертификат создан ✅\nКод: {code}\nСумма: {amount} BYN\nИсточник: telegram"
        await update.message.reply_document(document=bio, caption=caption)
    except Exception as e:
        await update.message.reply_text(f"Создан, но не смог отправить PDF: {e}")

    if SHEET_URL:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📒 Журнал (Google Таблица)", url=SHEET_URL)]])
        await update.message.reply_text("Журнал:", reply_markup=kb)

    await update.message.reply_text("Готово.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def journal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Доступ ограничен.")
        return

    resp = api_list({"start": 0, "limit": 10})
    if not resp.get("success"):
        await update.message.reply_text(f"Ошибка API: {resp.get('error')}")
        return

    rows = resp.get("rows", [])
    if not rows:
        await update.message.reply_text("Журнал пуст.")
        return

    await update.message.reply_text("Последние сертификаты (действия под каждым):")

    for r in rows:
        await update.message.reply_text(
            format_cert(r),
            reply_markup=build_cert_keyboard(r),
            parse_mode="HTML",
        )

    if SHEET_URL:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Открыть Google-таблицу", url=SHEET_URL)]])
        await update.message.reply_text("Дополнительно:", reply_markup=kb)

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /scan 123456 — считаем "сканированием".
    Требование: НЕ админ при скане получает ТОЛЬКО текст приглашения.
    Админ получает карточку сертификата.
    """
    if not context.args:
        await update.message.reply_text("Использование: /scan 123456")
        return
    code = "".join(ch for ch in context.args[0] if ch.isdigit())
    if not code:
        await update.message.reply_text("Нужен числовой код.")
        return

    if not is_admin(update):
        await update.message.reply_text(NON_ADMIN_SCAN_TEXT, disable_web_page_preview=False)
        return

    await show_cert_by_code(update, context, code)

async def pdf_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Доступ ограничен.")
        return

    if not context.args:
        await update.message.reply_text("Использование: /pdf 12345 (где 12345 — код сертификата)")
        return

    code = "".join(ch for ch in context.args[0] if ch.isdigit())
    if not code:
        await update.message.reply_text("Нужен числовой код.")
        return

    try:
        pdf_bytes = api_download_pdf(code=code)
        bio = io.BytesIO(pdf_bytes)
        bio.name = f"Certificate_{code}.pdf"
        await update.message.reply_document(document=bio, caption=f"PDF по коду {code}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        if update.callback_query:
            await update.callback_query.answer("Доступ ограничен.", show_alert=True)
        return

    q = update.callback_query
    if not q or not q.data:
        return

    try:
        action, gid_s = q.data.split(":", 1)
        gid = int(gid_s)
    except Exception:
        await q.answer("Некорректная команда.", show_alert=True)
        return

    # Confirm delete
    if action == "del":
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Да, удалить", callback_data=f"del_yes:{gid}"),
                InlineKeyboardButton("↩️ Отмена", callback_data=f"del_no:{gid}"),
            ]
        ])
        await q.answer()
        await q.message.reply_text(f"Удалить сертификат #{gid}? Код станет доступен снова.", reply_markup=kb)
        return

    if action == "del_no":
        await q.answer("Ок, не удаляю.")
        return

    if action == "del_yes":
        await q.answer("Удаляю…")
        resp = api_post(API_DELETE, {"giftcert_id": gid, "confirm": True})
        if not resp.get("success"):
            err = resp.get("error") or resp.get("message") or resp.get("raw","")
            await q.message.reply_text(f"❌ Ошибка удаления: {str(err)[:300]}")
        else:
            await q.message.reply_text(f"Удалён ✅ (сертификат #{gid}). Код стал доступен снова.")
        return

    if action == "pdf":
        await q.answer("Готовлю PDF…")
        try:
            pdf_bytes = api_download_pdf(giftcert_id=gid)
            bio = io.BytesIO(pdf_bytes)
            bio.name = f"Certificate_{gid}.pdf"
            await q.message.reply_document(document=bio, caption=f"PDF сертификата #{gid}")
        except Exception as e:
            await q.message.reply_text(f"Ошибка PDF: {e}")
        return

    if action == "email":
        await q.answer("Отправляю email…")
        resp = api_post(API_RESEND, {"giftcert_id": gid})
        if not resp.get("success"):
            err = resp.get("error") or resp.get("message") or resp.get("raw","")
            await q.message.reply_text(f"❌ Ошибка отправки: {str(err)[:300]}")
        else:
            await q.message.reply_text(f"Email отправлен ✅ (сертификат #{gid})")
        return

    if action == "use":
        await q.answer("Отмечаю как использованный…")
        resp = api_use(giftcert_id=gid, note="Использован через Telegram")
        if not resp.get("success"):
            err = resp.get("error") or resp.get("message") or resp.get("raw","")
            await q.message.reply_text(f"❌ Не получилось: {str(err)[:300]}")
            return
        cert, _ = await fetch_cert_by_id(gid)
        if cert:
            await q.message.reply_text(format_cert(cert), reply_markup=build_cert_keyboard(cert), parse_mode="HTML")
        else:
            await q.message.reply_text("Готово ✅")
        return

    if action == "annul":
        await q.answer("Аннулирую…")
        resp = api_post(API_ANNUL, {"giftcert_id": gid, "reason": "Аннулирован через Telegram"})
        if not resp.get("success"):
            err = resp.get("error") or resp.get("message") or resp.get("raw","")
            await q.message.reply_text(f"❌ Ошибка: {str(err)[:300]}")
            return
        cert, _ = await fetch_cert_by_id(gid)
        if cert:
            await q.message.reply_text(format_cert(cert), reply_markup=build_cert_keyboard(cert), parse_mode="HTML")
        else:
            await q.message.reply_text(f"🚫 Аннулирован ✅ (сертификат #{gid})")
        return

    await q.answer("Неизвестное действие.", show_alert=True)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled error: %s", context.error)

# ---------------------------
# Main
# ---------------------------
def main():
    if not TG_BOT_TOKEN:
        raise SystemExit("TG_BOT_TOKEN is required")

    if not OC_API_TOKEN:
        raise SystemExit("OC_API_TOKEN is required")

    if not OC_BASE_URL.startswith("http"):
        raise SystemExit("OC_BASE_URL is required (https://...)")

    if "your-domain" in OC_BASE_URL:
        raise SystemExit("OC_BASE_URL выглядит как шаблон (your-domain). Укажи реальный домен в .env.example/.env")

    app = Application.builder().token(TG_BOT_TOKEN).build()

    # Conversation: new certificate
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("new", new_cmd),
            MessageHandler(filters.Regex(r"^➕ Создать сертификат$"), new_cmd),
        ],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_amount)],
            RECIPIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_recipient_name)],
            DONOR_FIRST: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_donor_first)],
            DONOR_LAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_donor_last)],
            RECIPIENT_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_recipient_email)],
            ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_action)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex(r"^❌ Отмена$"), cancel),
        ],
        allow_reentry=True,
    )

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("journal", journal_cmd))
    app.add_handler(CommandHandler("sheet", sheet_cmd))
    app.add_handler(CommandHandler("pdf", pdf_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_router))
    app.add_error_handler(error_handler)

    # ✅ Workaround для Python 3.14: создать loop, чтобы PTB не падал
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    logger.info("Bot is starting polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()