# Sotuv FAQ boti

## Mahalliy sinov (kompyuteringizda)

1. Python 3.11+ o'rnatilgan bo'lishi kerak.
2. Kutubxonalarni o'rnating:
   ```
   pip install -r requirements.txt
   ```
3. `.env.example` faylini nusxalab `.env` deb nomlang, ichiga:
   - `BOT_TOKEN` — BotFather'dan olgan tokeningiz
   - `ADMIN_CHAT_ID` — sizning shaxsiy Telegram ID'ingiz (bilmasangiz,
     Telegram'da @userinfobot ga yozing, u sizga ID'ingizni aytadi)
4. Ishga tushiring:
   ```
   python bot.py
   ```
5. Telegram'da botingizga yozing — FAQ'dagi 3 ta namuna savolni sinab
   ko'ring (masalan "ish vaqtingiz qachon"), keyin FAQ'da yo'q biror
   savol yozing — sizga (admin) xabar kelishi kerak.

## Railway'ga joylash

1. Shu papkani GitHub repo'ga yuklang.
2. Railway'da "New Project" -> "Deploy from GitHub repo" orqali shu
   repo'ni tanlang.
3. Railway loyihangizda **Variables** bo'limiga kirib, `BOT_TOKEN` va
   `ADMIN_CHAT_ID`ni qo'shing (`.env` fayli Railway'ga yuklanmaydi,
   shuning uchun bu qadam shart).
4. Railway avtomatik ravishda `requirements.txt`ni o'rnatib, `python
   bot.py` orqali botni ishga tushiradi.
5. Ma'lumotlar bazasi (`bot.db`) doimiy saqlanishi uchun Railway'da
   **Volume** qo'shing va uni loyiha papkasiga (masalan `/app`) ulang —
   aks holda har deploy'da FAQ'ga o'rganilgan javoblar o'chib ketishi
   mumkin.

## FAQ ro'yxatini to'ldirish

Hozircha `bot.py` ichidagi `SEED_FAQ` ro'yxatida 3 ta namuna savol bor.
FAQ ro'yxatingiz tayyor bo'lgach, menga yuboring — men buni to'g'ridan-
to'g'ri bazaga yuklaydigan qulay usul (masalan alohida `faq.json` fayl)
qo'shib beraman, shunda `bot.py` faylini o'zgartirmasdan yangi savol-
javob qo'shishingiz mumkin bo'ladi.
