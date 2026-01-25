import os
import aiohttp
import asyncio
import mimetypes
from telegram import Bot as TelegramBot
from config import TELEGRAM_PRICES_BOT_TOKEN, BALE_PRICES_BOT_TOKEN
from prices.models import PriceListFile
from bale import Bot, InputFile
from asgiref.sync import sync_to_async

# مسیر ذخیره فایل ها
MEDIA_DIR = "media/pricelists/"

# تابع اصلی همگام سازی فایل ها بین تلگرام و بله
async def sync_files_between_telegram_and_bale():
    telegram_bot = TelegramBot(token=TELEGRAM_PRICES_BOT_TOKEN)
    bale_bot = Bot(token=BALE_PRICES_BOT_TOKEN)
    price_files = await sync_to_async(list)(PriceListFile.objects.filter(telegram_file_id__isnull=False))
    chat_id = 78486032  # مقدار عددی ادمین یا کانال بله
    for pf in price_files:
        # دانلود فایل از تلگرام (کاملاً async)
        file_obj = await telegram_bot.get_file(pf.telegram_file_id)
        # پیدا کردن فرمت فایل
        price_title = await sync_to_async(lambda: pf.price_list.title)()
        file_url = file_obj.file_path if hasattr(file_obj, 'file_path') else None
        ext = None
        if file_url:
            ext = os.path.splitext(file_url)[1]
        if not ext:
            mime_type, ext_guess = mimetypes.guess_type(price_title)
            ext = ext_guess if ext_guess else '.dat'
        # شماره‌گذاری فایل‌ها برای هر لیست قیمت
        file_count = await sync_to_async(lambda: pf.price_list.files.count())()
        file_index = list(await sync_to_async(lambda: list(pf.price_list.files.order_by('id').values_list('id', flat=True)))()).index(pf.id) + 1
        safe_title = price_title.replace('/', '_').replace(' ', '_')
        file_path = os.path.join(MEDIA_DIR, f"{safe_title}_{file_index}{ext}")
        byte_data = await file_obj.download_as_bytearray()
        with open(file_path, "wb") as out_file:
            out_file.write(byte_data)
        # آپلود فایل به بله
        with open(file_path, "rb") as f:
            file_bytes = f.read()
            bale_input_file = InputFile(file_bytes)
            caption = price_title
            try:
                msg = await bale_bot.send_document(chat_id=chat_id, document=bale_input_file, caption=caption)
                pf.bale_file_id = msg.document.file_id if hasattr(msg, 'document') and hasattr(msg.document, 'file_id') else None
                await sync_to_async(pf.save)()
                print(f"فایل {pf.telegram_file_id} به بله منتقل شد و bale_file_id ذخیره شد.")
            except Exception as e:
                print(f"خطا در ارسال فایل به بله: {e}")

# نحوه اجرا:
# import asyncio
# asyncio.run(sync_files_between_telegram_and_bale())
