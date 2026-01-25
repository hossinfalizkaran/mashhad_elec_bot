import os
import django
import logging
import json
from datetime import datetime, timezone
from asgiref.sync import sync_to_async
from config import BALE_PRICES_BOT_TOKEN, CHANNEL_ID, BOT_USERNAME
from bale import Bot, CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton, MenuKeyboardMarkup, MenuKeyboardButton

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()
from prices.models import PriceList, PriceListFile, BaleUser

DATA_DIR = "data"
USER_STATES_FILE = os.path.join(DATA_DIR, "user_states.json")
PAGE_SIZE_USER = 21
PAGE_SIZE_ADMIN = 9

client = Bot(token=BALE_PRICES_BOT_TOKEN)

# --- توابع کمکی دیتابیس ---
@sync_to_async
def save_bale_user_info(user):
    BaleUser.objects.update_or_create(user_id=user.id, defaults={'first_name': user.first_name, 'username': user.username})

@sync_to_async
def get_all_files_from_db():
    items = PriceList.objects.all().order_by('-rank')
    result = []
    for item in items:
        result.append({
            "caption": item.title,
            "file_ids": list(item.files.values_list('bale_file_id', flat=True)),
            "timestamp": item.updated_at.isoformat(),
            "id": item.id
        })
    return result

@sync_to_async
def db_add_price_list(title, file_ids):
    p = PriceList.objects.create(title=title)
    for f_id in file_ids:
        PriceListFile.objects.create(price_list=p, bale_file_id=f_id, file_type='document')

@sync_to_async
def db_edit_caption_by_id(price_list_id, new_caption):
    try:
        item = PriceList.objects.get(id=price_list_id)
        item.title = new_caption
        item.save()
    except PriceList.DoesNotExist:
        pass

@sync_to_async
def db_replace_files_by_id(price_list_id, new_file_ids):
    try:
        item = PriceList.objects.get(id=price_list_id)
        item.files.all().delete()
        for f_id in new_file_ids:
            PriceListFile.objects.create(price_list=item, bale_file_id=f_id, file_type='document')
    except PriceList.DoesNotExist:
        pass

@sync_to_async
def db_get_all_bale_user_ids(exclude_admins=False):
    qs = BaleUser.objects.all()
    return list(qs.values_list('user_id', flat=True))

# --- مدیریت وضعیت کاربر ---
def ensure_files():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(USER_STATES_FILE):
        with open(USER_STATES_FILE, "w") as f:
            json.dump([], f)

def get_user_state(user_id):
    try:
        with open(USER_STATES_FILE, "r") as f:
            states = json.load(f)
        return next((s for s in states if s["user_id"] == str(user_id)), None)
    except:
        return None

def set_user_state(user_id, state=None, **kwargs):
    ensure_files()
    try:
        with open(USER_STATES_FILE, "r") as f:
            states = json.load(f)
    except:
        states = []
    states = [s for s in states if s["user_id"] != str(user_id)]
    if state or kwargs:
        st = {"user_id": str(user_id)}
        if state:
            st["state"] = state
        st.update(kwargs)
        states.append(st)
    with open(USER_STATES_FILE, "w") as f:
        json.dump(states, f)

def clear_user_state(user_id):
    set_user_state(user_id)

def escape_html(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def admin_menu():
    kb = MenuKeyboardMarkup()
    kb.add(MenuKeyboardButton("➕ افزودن لیست قیمت"))
    kb.add(MenuKeyboardButton("📋 نمایش لیست‌ها"))
    kb.add(MenuKeyboardButton("🔎 جستجو در لیست‌ها"))
    kb.add(MenuKeyboardButton("📄 دریافت فایل کاربران"))
    kb.add(MenuKeyboardButton("👥 تعداد اعضا"))
    kb.add(MenuKeyboardButton("🚫 حذف کاربر"))
    kb.add(MenuKeyboardButton("✉️ ارسال پیام به همه کاربران"))
    kb.add(MenuKeyboardButton("⏪ بازگشت به منوی اصلی"))
    return kb

def user_menu():
    kb = MenuKeyboardMarkup()
    kb.add(MenuKeyboardButton("📋 نمایش لیست قیمت‌ها"))
    return kb

def file_pagination_keyboard(files, page, total_pages, is_admin=False, search_mode=False):
    kb = InlineKeyboardMarkup()
    for idx, f in enumerate(files):
        caption = f["caption"][:20] + ("..." if len(f["caption"]) > 20 else "")
        kb.add(InlineKeyboardButton(caption, callback_data=f"show_{page}_{f['id']}"))
    if page > 0:
        kb.add(InlineKeyboardButton("⬅️ قبلی", callback_data=f"page_{page-1}"))
    if page < total_pages-1:
        kb.add(InlineKeyboardButton("بعدی ➡️", callback_data=f"page_{page+1}"))
    return kb

def cancel_inline():
    return InlineKeyboardMarkup().add(InlineKeyboardButton("لغو", callback_data="cancel"))

def get_page_size(is_admin):
    return PAGE_SIZE_ADMIN if is_admin else PAGE_SIZE_USER

# --- رویدادهای بات بله ---
@client.event
async def on_ready():
    print(client.user, "is Ready!")

@client.event
async def on_message(message: Message):
    user_id = str(message.author.id)
    first_name = message.author.first_name
    username = getattr(message.author, 'username', '')
    await save_bale_user_info(message.author)
    if message.content == "/start":
        reply_markup = InlineKeyboardMarkup()
        reply_markup.add(InlineKeyboardButton(text="📋 نمایش لیست قیمت‌ها", callback_data="show_price_lists"))
        reply_markup.add(InlineKeyboardButton(text="🔎 جستجو در لیست‌ها", callback_data="search_price_lists"))
        await message.reply(
            f"سلام {first_name}! به ربات لیست قیمت بله خوش آمدید.",
            components=reply_markup
        )
    elif message.content == "/keyboard":
        await message.reply(
            f"سلام {first_name}! منوی اصلی:",
            components=user_menu()
        )
    elif message.content == "📋 نمایش لیست قیمت‌ها":
        price_lists = await get_all_files_from_db()
        kb = InlineKeyboardMarkup()
        for pl in price_lists:
            kb.add(InlineKeyboardButton(text=pl["caption"], callback_data=f"show_0_{pl['id']}"))
        await message.reply("لیست قیمت‌های موجود:", components=kb)
    elif message.content == "🔎 جستجو در لیست‌ها":
        set_user_state(user_id, state="search")
        await message.reply("عبارت مورد نظر برای جستجو را ارسال کنید:")
    elif get_user_state(user_id) and get_user_state(user_id).get("state") == "search":
        query = message.content.strip()
        price_lists = await get_all_files_from_db()
        results = [pl for pl in price_lists if query in pl["caption"]]
        if results:
            kb = InlineKeyboardMarkup()
            for pl in results:
                kb.add(InlineKeyboardButton(text=pl["caption"], callback_data=f"show_0_{pl['id']}"))
            await message.reply(f"نتایج جستجو برای '{query}':", components=kb)
        else:
            await message.reply("نتیجه‌ای یافت نشد.")
        clear_user_state(user_id)

@client.event
async def on_callback(callback: CallbackQuery):
    data = callback.data
    user_id = str(callback.message.author.id)
    state = get_user_state(user_id)
    is_admin = False  # اگر نیاز به تشخیص ادمین دارید، اینجا اضافه کنید
    files = await get_all_files_from_db()
    page = state.get("page", 0) if state else 0
    if data == "show_price_lists":
        kb = InlineKeyboardMarkup()
        for pl in files:
            kb.add(InlineKeyboardButton(text=pl["caption"], callback_data=f"show_0_{pl['id']}"))
        await callback.message.reply("لیست قیمت‌های موجود:", components=kb)
    elif data == "search_price_lists":
        set_user_state(user_id, state="search")
        await callback.message.reply("عبارت مورد نظر برای جستجو را ارسال کنید:")
    elif data.startswith("show_"):
        page_, price_id = map(int, data.split("_")[1:])
        file = next((f for f in files if f["id"] == price_id), None)
        if file:
            for fid in file["file_ids"]:
                await callback.message.reply(f"[فایل] {file['caption']}")
    elif data.startswith("page_"):
        page = int(data.split("_")[1])
        set_user_state(user_id, state.get("state"), page=page)
        await callback.message.reply(f"صفحه {page+1}")
    elif data == "cancel":
        clear_user_state(user_id)
        await callback.message.reply("عملیات لغو شد.")

client.run()