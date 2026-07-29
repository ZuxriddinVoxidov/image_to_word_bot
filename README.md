# Image to Word Telegram Bot

Ushbu bot foydalanuvchilar tomonidan yuborilgan rasmlarni qabul qilib, ularni avtomatik ravishda chiroylik va tartibli qilib **Microsoft Word (.docx)** formatidagi hujjatga joylab beradi.

## 🚀 O'rnatish va Ishga Tushirish Yo'riqnomasi

### 1. Kutubxonalarni o'rnatish
Terminal yoki Komandalar satrida (CMD) ushbu buyruqni bajaring:
```bash
pip install -r requirements.txt
```

### 2. Telegram Bot Token olish va sozlash
1. Telegramda [@BotFather](https://t.me/BotFather) botiga kiring va `/newbot` buyrug'i orqali yangi bot yarating.
2. Bot bergan **API Token**ni oling.
3. Loyiha papkasida `.env` nomli fayl yarating (yoki `.env.example` nomini `.env` ga o'zgartiring) va ichiga tokeningizni joylang:
```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyZ
```

### 3. Botni ishga tushirish
```bash
python bot.py
```

## 📱 Botdan foydalanish:
1. Botga `/start` bosiladi.
2. Rasmlar yuboriladi (birma-bir yoki guruhlab, Photo yoki Document formatida).
3. **📝 Word fayl yaratish** tugmasi bosiladi.
4. Hujjat nomi kiritiladi (masalan: `Mening_Rasmlarim`).
5. Bot tayyor `.docx` hujjatini yuboradi!
