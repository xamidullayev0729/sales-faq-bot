# Railway'ga deploy qilish — qadamma-qadam

## 1. Kodni GitHub'ga joylashtiring
Railway odatda GitHub repodan deploy qiladi.
```bash
git init
git add .
git commit -m "Initial commit"
```
Keyin GitHub'da yangi repo yarating va push qiling.

## 2. Railway'da yangi loyiha
1. https://railway.app ga kiring, GitHub bilan login qiling.
2. **New Project → Deploy from GitHub repo** → shu repongizni tanlang.
3. Railway avtomatik `requirements.txt`ni ko'rib, Python muhitini o'rnatadi va
   `Procfile`dagi `worker: python bot.py` buyrug'ini ishga tushiradi.

## 3. Environment Variables qo'shish
Railway loyihasida **Variables** bo'limiga o'ting va `.env.example`dagi
qiymatlarni kiriting:
- `BOT_TOKEN`
- `ADMIN_CHAT_ID`
- `GEMINI_API_KEY`
- `GEMINI_MODEL` (ixtiyoriy)
- `DB_PATH=/data/bot.db` (pastdagi 4-qadamni qarang)

## 4. Doimiy disk (Volume) ulash — MUHIM
SQLite baza faylini yo'qotmaslik uchun:
1. Loyiha sahifasida **+ New → Volume** tugmasini bosing.
2. Mount path sifatida `/data` yozing.
3. Xizmatingizga ulang (Attach to service).
4. `DB_PATH` environment variable qiymatini `/data/bot.db` qilib qo'ying
   (yuqoridagi 3-qadamda ko'rsatilgan).

Bu bo'lmasa, har safar Railway konteynerni qayta ishga tushirganda yoki
qayta deploy qilganda (masalan yangi kod push qilinganda) `bot.db` fayli
va undagi barcha FAQ/pauza holatlari o'chib ketadi.

## 5. "Worker" turi — web port kerak emas
Bu bot Telegram'ga long-polling orqali ulanadi, HTTP server emas. Railway
ba'zan avtomatik "web" xizmat deb hisoblab, port kutishi mumkin. Agar
Railway build loglarida portni kutayotgani haqida xabar chiqsa yoki
xizmat "unhealthy" deb ko'rinsa:
- Settings → **Deploy** bo'limida start command'ni aniq
  `python bot.py` qilib qo'ying,
- Health check'ni o'chirib qo'ying (Settings → Health Check → None),
  chunki bu bot HTTP so'rovlariga javob bermaydi.

## 6. Ishga tushirish
Deploy tugagach, **Deployments** bo'limida loglarni tekshiring — quyidagi
qator ko'rinishi kerak:
```
Bot ishga tushdi (polling)...
```
Shundan so'ng Telegram'da botga `/start` yozib sinab ko'ring.

## 7. Yangilanishlarni chiqarish
Kodga o'zgartirish kiritganingizda, shunchaki GitHub'ga push qiling —
Railway avtomatik qayta deploy qiladi (agar auto-deploy yoqilgan bo'lsa).

---

### Tez-tez uchraydigan xatolar
- **`KeyError: 'BOT_TOKEN'`** — Variables bo'limida BOT_TOKEN kiritilmagan.
- **Bot javob bermayapti** — loglarda xatolikni tekshiring; ADMIN_CHAT_ID
  noto'g'ri bo'lishi mumkin (u raqam bo'lishi kerak, `@username` emas).
- **FAQ bazasi har safar bo'shab qolayapti** — Volume ulanmagan yoki
  DB_PATH `/data/bot.db`ga to'g'ri sozlanmagan (4-qadam).
