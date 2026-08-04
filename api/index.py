import os
import sys
import json
import glob
import uuid
import shutil
import asyncio
import logging
import urllib.request
from flask import Flask, request, jsonify

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    FSInputFile,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Update,
)

# Root papkani sys.path ga qo'shish
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from file_builder import create_word_from_images, create_pdf_from_images

BOT_TOKEN = "8907229755:AAGQP5_Q7TEXEdj5vzPmUJfhK0oACIF1XmU"
SUPABASE_URL = "https://hwwsbwvvlkqqwbjemwhz.supabase.co/rest/v1/bot_image_sessions"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh3d3Nid3Z2bGtxcXdiamVtd2h6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI3NzQwMTUsImV4cCI6MjA4ODM1MDAxNX0.6BSjsEgHxhbTp7V9xa03ae66YXNj3rKwb16U1NkDijI"

app = Flask(__name__)
dp = Dispatcher()
TEMP_DIR = "/tmp/telegram_bot"

# --- Supabase Persistent Session Management ---

def supabase_request(endpoint_suffix="", data=None, method="GET"):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }
    url = f"{SUPABASE_URL}{endpoint_suffix}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode()
            return json.loads(content) if content else {}
    except Exception as e:
        logging.error(f"Supabase error ({method} {url}): {e}")
        return None

def get_user_session(user_id: int) -> dict:
    res = supabase_request(f"?user_id=eq.{user_id}")
    if res and isinstance(res, list) and len(res) > 0:
        return res[0]
    return {"user_id": user_id, "file_ids": [], "waiting_name": False, "pending_name": "Hujjat"}

def add_file_to_session(user_id: int, file_id: str) -> int:
    sess = get_user_session(user_id)
    files = sess.get("file_ids") or []
    if file_id not in files:
        files.append(file_id)
    payload = {
        "user_id": user_id,
        "file_ids": files,
        "waiting_name": sess.get("waiting_name", False),
        "pending_name": sess.get("pending_name", "Hujjat")
    }
    supabase_request(data=payload, method="POST")
    return len(files)

def set_user_waiting_name(user_id: int, waiting: bool):
    sess = get_user_session(user_id)
    payload = {
        "user_id": user_id,
        "file_ids": sess.get("file_ids", []),
        "waiting_name": waiting,
        "pending_name": sess.get("pending_name", "Hujjat")
    }
    supabase_request(data=payload, method="POST")

def set_user_pending_name(user_id: int, name: str):
    sess = get_user_session(user_id)
    payload = {
        "user_id": user_id,
        "file_ids": sess.get("file_ids", []),
        "waiting_name": False,
        "pending_name": name
    }
    supabase_request(data=payload, method="POST")

def clear_user_session(user_id: int):
    supabase_request(f"?user_id=eq.{user_id}", method="DELETE")

def sanitize_filename(filename: str) -> str:
    import re
    clean_name = re.sub(r'[\\/*?:"<>|]', "", filename).strip()
    return clean_name if clean_name else "Hujjat"

# --- Keyboards ---

def get_main_keyboard():
    kb = [
        [KeyboardButton(text="📝 Fayl yaratish")],
        [KeyboardButton(text="🗑 Tozalash / Qayta boshlash")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_format_inline_keyboard():
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📄 Word (.docx)", callback_data="fmt_docx"),
                InlineKeyboardButton(text="📕 PDF (.pdf)", callback_data="fmt_pdf"),
            ],
            [
                InlineKeyboardButton(text="📦 Word + PDF (Ikkalasi)", callback_data="fmt_both")
            ]
        ]
    )
    return kb

# --- Handlers ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    clear_user_session(user_id)
    
    welcome_text = (
        "👋 **Assalomu alaykum!**\n\n"
        "Men siz yuborgan rasmlarni tartib bilan va o'rtaga tekislab **Word (.docx)** yoki **PDF (.pdf)** fayliga joylab beraman.\n\n"
        "📸 Rasmlarni birma-bir yoki guruhlab yuboring.\n"
        "Tayyor bo'lgach **'📝 Fayl yaratish'** tugmasini bosing!"
    )
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(Command("cancel"))
@dp.message(F.text == "🗑 Tozalash / Qayta boshlash")
async def process_clear(message: types.Message):
    user_id = message.from_user.id
    clear_user_session(user_id)
    await message.answer("🔄 Barcha yuborilgan rasmlar tozalandi. Yangi rasmlarni yuborishingiz mumkin.", reply_markup=get_main_keyboard())

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    photo = message.photo[-1]
    total_count = add_file_to_session(user_id, photo.file_id)

    await message.answer(
        f"✅ Rasm qabul qilindi. Jami: **{total_count}** ta rasm.\n\n"
        "Rasmlar tugagan bo'lsa **'📝 Fayl yaratish'** tugmasini bosing.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@dp.message(F.document)
async def handle_document_image(message: types.Message):
    doc = message.document
    mime_type = doc.mime_type or ""
    
    if not (mime_type.startswith("image/") or doc.file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.heic'))):
        await message.answer("⚠️ Iltimos, faqat rasm fayllarini yuboring!")
        return

    user_id = message.from_user.id
    total_count = add_file_to_session(user_id, doc.file_id)

    await message.answer(
        f"✅ Fayl rasm sifatida qabul qilindi. Jami: **{total_count}** ta rasm.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text.in_({"📝 Fayl yaratish", "📝 Word fayl yaratish"}))
async def process_create_request(message: types.Message):
    user_id = message.from_user.id
    sess = get_user_session(user_id)
    file_ids = sess.get("file_ids") or []

    if not file_ids:
        await message.answer("⚠️ Hali hech qanday rasm yubormadingiz! Iltimos, avval rasmlarni yuboring.")
        return

    set_user_waiting_name(user_id, True)

    prompt_text = (
        f"📊 Jami **{len(file_ids)}** ta rasm yig'ildi.\n\n"
        "✏️ **Ushbu faylni nima deb nomlaymiz?**\n"
        "Iltimos, fayl nomini matn shaklida yozib yuboring (masalan: `Mening_Hujjatim`):"
    )
    await message.answer(
        prompt_text,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.callback_query(F.data.startswith("fmt_"))
async def process_format_choice(callback: types.CallbackQuery, bot: Bot):
    fmt_choice = callback.data.replace("fmt_", "")
    user_id = callback.from_user.id

    sess = get_user_session(user_id)
    file_ids = sess.get("file_ids") or []
    clean_name = sanitize_filename(sess.get("pending_name") or "Hujjat")

    if not file_ids:
        await callback.message.answer("❌ Rasmlar topilmadi yoki seans yakunlangan. Iltimos, rasmlarni qaytadan yuboring.")
        await callback.answer()
        return

    status_msg = await callback.message.answer("⏳ Rasmlar yuklab olinmoqda va fayl shakllantirilmoqda, iltimos kuting...")
    user_dir = os.path.join(TEMP_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    try:
        # Telegram serveridan rasmlarni vaqtincha yuklab olish
        local_images = []
        for idx, fid in enumerate(file_ids):
            tg_file = await bot.get_file(fid)
            ext = os.path.splitext(tg_file.file_path)[1] or ".jpg"
            local_path = os.path.join(user_dir, f"img_{idx + 1:04d}_{uuid.uuid4().hex[:6]}{ext}")
            await bot.download_file(tg_file.file_path, local_path)
            local_images.append(local_path)

        if fmt_choice in ("docx", "both"):
            docx_path = os.path.join(user_dir, f"{clean_name}.docx")
            create_word_from_images(local_images, docx_path)
            doc_file = FSInputFile(docx_path, filename=f"{clean_name}.docx")
            await bot.send_document(
                chat_id=callback.message.chat.id,
                document=doc_file,
                caption=f"📄 **{clean_name}.docx** faylingiz tayyor! (Jami {len(local_images)} ta rasm)",
                parse_mode="Markdown"
            )

        if fmt_choice in ("pdf", "both"):
            pdf_path = os.path.join(user_dir, f"{clean_name}.pdf")
            create_pdf_from_images(local_images, pdf_path)
            pdf_file = FSInputFile(pdf_path, filename=f"{clean_name}.pdf")
            await bot.send_document(
                chat_id=callback.message.chat.id,
                document=pdf_file,
                caption=f"📕 **{clean_name}.pdf** faylingiz tayyor! (Jami {len(local_images)} ta rasm)",
                parse_mode="Markdown"
            )

    except Exception as e:
        logging.error(f"Fayl yaratishda xatolik: {e}")
        await callback.message.answer(f"❌ Fayl yaratishda xatolik yuz berdi: {e}")
    finally:
        clear_user_session(user_id)
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir, ignore_errors=True)
        try:
            await status_msg.delete()
        except Exception:
            pass
        await callback.message.answer("Yangi fayl yaratish uchun rasmlar yuborishingiz mumkin.", reply_markup=get_main_keyboard())
        await callback.answer()

@dp.message(F.text)
async def handle_custom_name(message: types.Message):
    user_id = message.from_user.id
    sess = get_user_session(user_id)
    file_ids = sess.get("file_ids") or []

    if file_ids:
        custom_name = sanitize_filename(message.text)
        set_user_pending_name(user_id, custom_name)
        await message.answer(
            f"✏️ Fayl nomi qabul qilindi: **{custom_name}**\n\n"
            "📌 Endi qaysi formatda saqlashni xohlaysiz?",
            parse_mode="Markdown",
            reply_markup=get_format_inline_keyboard()
        )
    else:
        await message.answer(
            "📸 Iltimos, avval rasmlarni yuboring!",
            reply_markup=get_main_keyboard()
        )

# Flask Endpoints
@app.route("/", methods=["GET"])
@app.route("/ping", methods=["GET"])
@app.route("/api/ping", methods=["GET"])
def ping():
    return jsonify({
        "status": "ok",
        "warm": True,
        "bot": "active",
        "message": "Bot Server is Running on Vercel Serverless with Cloud Sessions!"
    }), 200

async def handle_webhook_request(req_data):
    async with Bot(token=BOT_TOKEN) as bot:
        update = Update.model_validate(req_data, context={"bot": bot})
        await dp.feed_update(bot, update)

@app.route("/api/webhook", methods=["POST"])
def webhook():
    try:
        req_data = request.get_json(force=True)
        if not req_data:
            return "OK", 200
        asyncio.run(handle_webhook_request(req_data))
    except Exception as e:
        logging.error(f"Webhook processing error: {e}")
    return "OK", 200

@app.route("/api/set_webhook", methods=["GET"])
def set_webhook():
    host_url = request.host_url.replace("http://", "https://")
    webhook_url = f"{host_url}api/webhook"
    
    async def _set():
        async with Bot(token=BOT_TOKEN) as bot:
            return await bot.set_webhook(webhook_url)
    
    res = asyncio.run(_set())
    return jsonify({"success": res, "webhook_url": webhook_url})
