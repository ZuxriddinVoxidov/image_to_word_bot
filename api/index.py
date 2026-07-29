import os
import sys
import uuid
import shutil
import asyncio
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
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

load_dotenv()
# Ushbu bot uchun maxsus token (hech qanday tashqi muhit o'zgaruvchisi aralasha olmaydi)
BOT_TOKEN = "8907229755:AAGQP5_Q7TEXEdj5vzPmUJfhK0oACIF1XmU"

app = Flask(__name__)
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher(storage=MemoryStorage())

# Vercel /tmp papkasi
TEMP_DIR = "/tmp/telegram_bot"

# FSM Holatlari
class ImageToWordStates(StatesGroup):
    collecting_images = State()
    waiting_for_filename = State()
    waiting_for_format = State()

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

def clean_user_temp(user_id: int):
    user_dir = os.path.join(TEMP_DIR, str(user_id))
    if os.path.exists(user_dir):
        shutil.rmtree(user_dir, ignore_errors=True)

def sanitize_filename(filename: str) -> str:
    import re
    clean_name = re.sub(r'[\\/*?:"<>|]', "", filename).strip()
    return clean_name if clean_name else "Hujjat"

# Handlers
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    await state.clear()
    clean_user_temp(user_id)
    
    welcome_text = (
        "👋 **Assalomu alaykum!**\n\n"
        "Men siz yuborgan rasmlarni tartib bilan va o'rtaga tekislab **Word (.docx)** yoki **PDF (.pdf)** fayliga joylab beraman.\n\n"
        "📸 Cheklanmagan miqdorda rasmlarni yuborishingiz mumkin.\n"
        "Tayyor bo'lgach **'📝 Fayl yaratish'** tugmasini bosing!"
    )
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())
    await state.set_state(ImageToWordStates.collecting_images)

@dp.message(Command("cancel"))
@dp.message(F.text == "🗑 Tozalash / Qayta boshlash")
async def process_clear(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    await state.clear()
    clean_user_temp(user_id)
    await message.answer("🔄 Barcha yuborilgan rasmlar tozalandi. Yangi rasmlarni yuborishingiz mumkin.", reply_markup=get_main_keyboard())
    await state.set_state(ImageToWordStates.collecting_images)

@dp.message(ImageToWordStates.collecting_images, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_dir = os.path.join(TEMP_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    data = await state.get_data()
    images = data.get("images", [])

    photo = message.photo[-1]
    unique_id = uuid.uuid4().hex[:8]
    file_path = os.path.join(user_dir, f"img_{len(images) + 1:04d}_{unique_id}.jpg")
    
    await bot.download(photo, destination=file_path)
    images.append(file_path)

    await state.update_data(images=images)
    await message.answer(f"✅ Rasm qabul qilindi. Jami: **{len(images)}** ta rasm.", parse_mode="Markdown")

@dp.message(ImageToWordStates.collecting_images, F.document)
async def handle_document_image(message: types.Message, state: FSMContext):
    doc = message.document
    mime_type = doc.mime_type or ""
    
    if not (mime_type.startswith("image/") or doc.file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.heic'))):
        await message.answer("⚠️ Iltimos, faqat rasm fayllarini yuboring!")
        return

    user_id = message.from_user.id
    user_dir = os.path.join(TEMP_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    data = await state.get_data()
    images = data.get("images", [])

    ext = os.path.splitext(doc.file_name)[1] or ".jpg"
    unique_id = uuid.uuid4().hex[:8]
    file_path = os.path.join(user_dir, f"img_{len(images) + 1:04d}_{unique_id}{ext}")
    
    await bot.download(doc, destination=file_path)
    images.append(file_path)

    await state.update_data(images=images)
    await message.answer(f"✅ Fayl rasm sifatida qabul qilindi. Jami: **{len(images)}** ta rasm.", parse_mode="Markdown")

@dp.message(ImageToWordStates.collecting_images, F.text.in_({"📝 Fayl yaratish", "📝 Word fayl yaratish"}))
async def process_create_request(message: types.Message, state: FSMContext):
    data = await state.get_data()
    images = data.get("images", [])

    if not images:
        await message.answer("⚠️ Hali hech qanday rasm yubormadingiz! Iltimos, avval rasmlarni yuboring.")
        return

    await message.answer(
        f"📊 Jami **{len(images)}** ta rasm yig'ildi.\n\n"
        "✏️ Iltimos, faylingiz uchun **nom** kiriting (masalan: `Mening_Hujjatim`):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(ImageToWordStates.waiting_for_filename)

@dp.message(ImageToWordStates.waiting_for_filename, F.text)
async def process_filename(message: types.Message, state: FSMContext):
    raw_name = message.text
    clean_name = sanitize_filename(raw_name)
    
    await state.update_data(filename=clean_name)
    await message.answer(
        f"📁 Fayl nomi: **{clean_name}**\n\n"
        "📌 Qaysi formatda saqlashni xohlaysiz?",
        parse_mode="Markdown",
        reply_markup=get_format_inline_keyboard()
    )
    await state.set_state(ImageToWordStates.waiting_for_format)

@dp.callback_query(ImageToWordStates.waiting_for_format, F.data.startswith("fmt_"))
async def process_format_choice(callback: types.CallbackQuery, state: FSMContext):
    fmt_choice = callback.data.replace("fmt_", "")
    user_id = callback.from_user.id

    data = await state.get_data()
    images = data.get("images", [])
    clean_name = data.get("filename", "Hujjat")

    if not images:
        await callback.message.answer("❌ Xatolik yuz berdi. Rasmlar topilmadi. Qaytadan `/start` bosing.")
        await state.clear()
        await callback.answer()
        return

    status_msg = await callback.message.answer("⏳ Fayllar shakllantirilmoqda, iltimos kuting...")

    user_dir = os.path.join(TEMP_DIR, str(user_id))

    try:
        if fmt_choice in ("docx", "both"):
            docx_path = os.path.join(user_dir, f"{clean_name}.docx")
            create_word_from_images(images, docx_path)
            doc_file = FSInputFile(docx_path, filename=f"{clean_name}.docx")
            await bot.send_document(
                chat_id=callback.message.chat.id,
                document=doc_file,
                caption=f"📄 **{clean_name}.docx** faylingiz tayyor!",
                parse_mode="Markdown"
            )

        if fmt_choice in ("pdf", "both"):
            pdf_path = os.path.join(user_dir, f"{clean_name}.pdf")
            create_pdf_from_images(images, pdf_path)
            pdf_file = FSInputFile(pdf_path, filename=f"{clean_name}.pdf")
            await bot.send_document(
                chat_id=callback.message.chat.id,
                document=pdf_file,
                caption=f"📕 **{clean_name}.pdf** faylingiz tayyor!",
                parse_mode="Markdown"
            )

    except Exception as e:
        await callback.message.answer(f"❌ Fayl yaratishda xatolik: {e}")
    finally:
        clean_user_temp(user_id)
        await state.clear()
        await callback.message.answer("Yangi fayl yaratish uchun rasmlar yuborishingiz mumkin.", reply_markup=get_main_keyboard())
        await state.set_state(ImageToWordStates.collecting_images)
        await callback.answer()

# Flask Webhook Endpoints for Vercel
@app.route("/", methods=["GET"])
def home():
    return "Bot Server is Running on Vercel Serverless!"

@app.route("/api/webhook", methods=["POST"])
def webhook():
    if not bot:
        return jsonify({"error": "BOT_TOKEN missing"}), 500
    
    update = Update.model_validate(request.get_json(force=True), context={"bot": bot})
    asyncio.run(dp.feed_update(bot, update))
    return "OK", 200

@app.route("/api/set_webhook", methods=["GET"])
def set_webhook():
    host_url = request.host_url.replace("http://", "https://")
    webhook_url = f"{host_url}api/webhook"
    
    async def _set():
        return await bot.set_webhook(webhook_url)
    
    res = asyncio.run(_set())
    return jsonify({"success": res, "webhook_url": webhook_url})
