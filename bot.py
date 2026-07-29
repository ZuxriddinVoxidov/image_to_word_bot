import asyncio
import os
import re
import sys
import uuid
import shutil
import logging
from dotenv import load_dotenv

# Windows konsolida UTF-8 chiqarishni ta'minlash
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

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
)

from file_builder import create_word_from_images, create_pdf_from_images

# Logging sozlash
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Foydalanuvchilar uchun parallelizm to'siqlari (Race condition oldini olish uchun)
user_locks: dict[int, asyncio.Lock] = {}

def get_user_lock(user_id: int) -> asyncio.Lock:
    if user_id not in user_locks:
        user_locks[user_id] = asyncio.Lock()
    return user_locks[user_id]

# FSM Holatlari
class ImageToWordStates(StatesGroup):
    collecting_images = State()
    waiting_for_filename = State()
    waiting_for_format = State()

# Klaviatura tugmalari
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

TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")

def clean_user_temp(user_id: int):
    """Foydalanuvchi vaqtinchalik rasmlar papkasini tozalaydi."""
    user_dir = os.path.join(TEMP_DIR, str(user_id))
    if os.path.exists(user_dir):
        shutil.rmtree(user_dir, ignore_errors=True)

def sanitize_filename(filename: str) -> str:
    """Fayl nomidagi taqiqlangan belgilarni tozalaydi."""
    clean_name = re.sub(r'[\\/*?:"<>|]', "", filename).strip()
    return clean_name if clean_name else "Hujjat"

# Bot va Dispatcher obyektlari
dp = Dispatcher(storage=MemoryStorage())

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with get_user_lock(user_id):
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
    async with get_user_lock(user_id):
        await state.clear()
        clean_user_temp(user_id)
    await message.answer("🔄 Barcha yuborilgan rasmlar tozalandi. Yangi rasmlarni yuborishingiz mumkin.", reply_markup=get_main_keyboard())
    await state.set_state(ImageToWordStates.collecting_images)

@dp.message(ImageToWordStates.collecting_images, F.photo)
async def handle_photo(message: types.Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    lock = get_user_lock(user_id)

    async with lock:
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
        total_count = len(images)

    await message.answer(f"✅ Rasm qabul qilindi. Jami: **{total_count}** ta rasm.", parse_mode="Markdown")

@dp.message(ImageToWordStates.collecting_images, F.document)
async def handle_document_image(message: types.Message, state: FSMContext, bot: Bot):
    doc = message.document
    mime_type = doc.mime_type or ""
    
    if not (mime_type.startswith("image/") or doc.file_name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.heic'))):
        await message.answer("⚠️ Iltimos, faqat rasm fayllarini yuboring!")
        return

    user_id = message.from_user.id
    lock = get_user_lock(user_id)

    async with lock:
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
        total_count = len(images)

    await message.answer(f"✅ Fayl rasm sifatida qabul qilindi. Jami: **{total_count}** ta rasm.", parse_mode="Markdown")

@dp.message(ImageToWordStates.collecting_images, F.text.in_({"📝 Fayl yaratish", "📝 Word fayl yaratish"}))
async def process_create_request(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with get_user_lock(user_id):
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
async def process_format_choice(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    fmt_choice = callback.data.replace("fmt_", "")
    user_id = callback.from_user.id
    lock = get_user_lock(user_id)

    async with lock:
        data = await state.get_data()
        images = data.get("images", [])
        clean_name = data.get("filename", "Hujjat")

    if not images:
        await callback.message.answer("❌ Xatolik yuz berdi. Rasmlar topilmadi. Qaytadan `/start` bosing.")
        await state.clear()
        await callback.answer()
        return

    await callback.message.edit_text("⏳ Fayllar shakllantirilmoqda va markazga tekislanmoqda, iltimos kuting...")

    user_dir = os.path.join(TEMP_DIR, str(user_id))

    try:
        if fmt_choice in ("docx", "both"):
            docx_path = os.path.join(user_dir, f"{clean_name}.docx")
            await asyncio.to_thread(create_word_from_images, images, docx_path)
            doc_file = FSInputFile(docx_path, filename=f"{clean_name}.docx")
            await bot.send_document(
                chat_id=callback.message.chat.id,
                document=doc_file,
                caption=f"📄 **{clean_name}.docx** faylingiz tayyor! (Jami {len(images)} ta rasm)",
                parse_mode="Markdown"
            )

        if fmt_choice in ("pdf", "both"):
            pdf_path = os.path.join(user_dir, f"{clean_name}.pdf")
            await asyncio.to_thread(create_pdf_from_images, images, pdf_path)
            pdf_file = FSInputFile(pdf_path, filename=f"{clean_name}.pdf")
            await bot.send_document(
                chat_id=callback.message.chat.id,
                document=pdf_file,
                caption=f"📕 **{clean_name}.pdf** faylingiz tayyor! (Jami {len(images)} ta rasm)",
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"Fayl yaratishda xatolik: {e}")
        await callback.message.answer(f"❌ Fayl yaratishda xatolik yuz berdi: {e}")
    finally:
        async with lock:
            clean_user_temp(user_id)
            await state.clear()
        await callback.message.answer("Yangi fayl yaratish uchun rasmlar yuborishingiz mumkin.", reply_markup=get_main_keyboard())
        await state.set_state(ImageToWordStates.collecting_images)
        await callback.answer()

async def main():
    if not BOT_TOKEN:
        print("❌ XATOLIK: .env faylida BOT_TOKEN topilmadi!")
        return

    bot = Bot(token=BOT_TOKEN)
    print("[+] Bot muvaffaqiyatli ishga tushdi va xabarlarni kutmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
