import os
import sys
import glob
import uuid
import shutil
import asyncio
import logging
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

app = Flask(__name__)
dp = Dispatcher()

TEMP_DIR = "/tmp/telegram_bot"

def get_main_keyboard():
    kb = [
        [KeyboardButton(text="📝 Fayl yaratish")],
        [KeyboardButton(text="🗑 Tozalash / Qayta boshlash")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_format_inline_keyboard(filename: str):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📄 Word (.docx)", callback_data=f"fmt_docx:{filename}"),
                InlineKeyboardButton(text="📕 PDF (.pdf)", callback_data=f"fmt_pdf:{filename}"),
            ],
            [
                InlineKeyboardButton(text="📦 Word + PDF (Ikkalasi)", callback_data=f"fmt_both:{filename}")
            ]
        ]
    )
    return kb

def get_user_images(user_id: int) -> list[str]:
    user_dir = os.path.join(TEMP_DIR, str(user_id))
    if not os.path.exists(user_dir):
        return []
    files = sorted(glob.glob(os.path.join(user_dir, "img_*")))
    return files

def clean_user_temp(user_id: int):
    user_dir = os.path.join(TEMP_DIR, str(user_id))
    if os.path.exists(user_dir):
        shutil.rmtree(user_dir, ignore_errors=True)

def set_waiting_for_name(user_id: int):
    user_dir = os.path.join(TEMP_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    marker = os.path.join(user_dir, "WAITING_NAME")
    with open(marker, "w") as f:
        f.write("1")

def clear_waiting_for_name(user_id: int):
    user_dir = os.path.join(TEMP_DIR, str(user_id))
    marker = os.path.join(user_dir, "WAITING_NAME")
    if os.path.exists(marker):
        try:
            os.remove(marker)
        except Exception:
            pass

def sanitize_filename(filename: str) -> str:
    import re
    clean_name = re.sub(r'[\\/*?:"<>|]', "", filename).strip()
    return clean_name if clean_name else "Hujjat"

# Handlers

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    clean_user_temp(user_id)
    
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
    clean_user_temp(user_id)
    await message.answer("🔄 Barcha yuborilgan rasmlar tozalandi. Yangi rasmlarni yuborishingiz mumkin.", reply_markup=get_main_keyboard())

@dp.message(F.photo)
async def handle_photo(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    user_dir = os.path.join(TEMP_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    images = get_user_images(user_id)

    photo = message.photo[-1]
    unique_id = uuid.uuid4().hex[:8]
    file_path = os.path.join(user_dir, f"img_{len(images) + 1:04d}_{unique_id}.jpg")
    
    await bot.download(photo, destination=file_path)
    current_images = get_user_images(user_id)

    await message.answer(
        f"✅ Rasm qabul qilindi. Jami: **{len(current_images)}** ta rasm.\n\n"
        "Rasmlar tugagan bo'lsa **'📝 Fayl yaratish'** tugmasini bosing.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@dp.message(F.document)
async def handle_document_image(message: types.Message, bot: Bot):
    doc = message.document
    mime_type = doc.mime_type or ""
    
    if not (mime_type.startswith("image/") or doc.file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.heic'))):
        await message.answer("⚠️ Iltimos, faqat rasm fayllarini yuboring!")
        return

    user_id = message.from_user.id
    user_dir = os.path.join(TEMP_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    images = get_user_images(user_id)

    ext = os.path.splitext(doc.file_name)[1] or ".jpg"
    unique_id = uuid.uuid4().hex[:8]
    file_path = os.path.join(user_dir, f"img_{len(images) + 1:04d}_{unique_id}{ext}")
    
    await bot.download(doc, destination=file_path)
    current_images = get_user_images(user_id)

    await message.answer(
        f"✅ Fayl rasm sifatida qabul qilindi. Jami: **{len(current_images)}** ta rasm.",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text.in_({"📝 Fayl yaratish", "📝 Word fayl yaratish"}))
async def process_create_request(message: types.Message):
    user_id = message.from_user.id
    images = get_user_images(user_id)

    if not images:
        await message.answer("⚠️ Hali hech qanday rasm yubormadingiz! Iltimos, avval rasmlarni yuboring.")
        return

    # Nom kiritish kutilayotgani belgilanadi
    set_waiting_for_name(user_id)

    prompt_text = (
        f"📊 Jami **{len(images)}** ta rasm yig'ildi.\n\n"
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
    data_parts = callback.data.split(":", 1)
    fmt_choice = data_parts[0].replace("fmt_", "")
    filename = sanitize_filename(data_parts[1]) if len(data_parts) > 1 else "Hujjat"

    user_id = callback.from_user.id
    images = get_user_images(user_id)

    if not images:
        await callback.message.answer("❌ Rasmlar topilmadi. Iltimos, rasmlarni qaytadan yuboring.")
        await callback.answer()
        return

    status_msg = await callback.message.answer("⏳ Fayllar shakllantirilmoqda va markazga tekislanmoqda, iltimos kuting...")
    user_dir = os.path.join(TEMP_DIR, str(user_id))

    try:
        if fmt_choice in ("docx", "both"):
            docx_path = os.path.join(user_dir, f"{filename}.docx")
            create_word_from_images(images, docx_path)
            doc_file = FSInputFile(docx_path, filename=f"{filename}.docx")
            await bot.send_document(
                chat_id=callback.message.chat.id,
                document=doc_file,
                caption=f"📄 **{filename}.docx** faylingiz tayyor! (Jami {len(images)} ta rasm)",
                parse_mode="Markdown"
            )

        if fmt_choice in ("pdf", "both"):
            pdf_path = os.path.join(user_dir, f"{filename}.pdf")
            create_pdf_from_images(images, pdf_path)
            pdf_file = FSInputFile(pdf_path, filename=f"{filename}.pdf")
            await bot.send_document(
                chat_id=callback.message.chat.id,
                document=pdf_file,
                caption=f"📕 **{filename}.pdf** faylingiz tayyor! (Jami {len(images)} ta rasm)",
                parse_mode="Markdown"
            )

    except Exception as e:
        await callback.message.answer(f"❌ Fayl yaratishda xatolik yuz berdi: {e}")
    finally:
        clean_user_temp(user_id)
        try:
            await status_msg.delete()
        except Exception:
            pass
        await callback.message.answer("Yangi fayl yaratish uchun rasmlar yuborishingiz mumkin.", reply_markup=get_main_keyboard())
        await callback.answer()

@dp.message(F.text)
async def handle_custom_name(message: types.Message):
    user_id = message.from_user.id
    images = get_user_images(user_id)
    
    if images:
        clear_waiting_for_name(user_id)
        custom_name = sanitize_filename(message.text)
        await message.answer(
            f"✏️ Fayl nomi qabul qilindi: **{custom_name}**\n\n"
            "📌 Endi qaysi formatda saqlashni xohlaysiz?",
            parse_mode="Markdown",
            reply_markup=get_format_inline_keyboard(custom_name)
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
    """Keep-Alive Cron & Health-check endpoint to keep Vercel function warm"""
    return jsonify({
        "status": "ok",
        "warm": True,
        "bot": "active",
        "message": "Bot Server is Running on Vercel Serverless!"
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
