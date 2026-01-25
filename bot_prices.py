import os
import django
import logging
import json
from datetime import datetime, timezone
from asgiref.sync import sync_to_async
from config import PRICES_BOT_TOKEN, PRICES_ADMINS, CHANNEL_ID, BOT_USERNAME

# --- اتصال به جنگو ---
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()
from prices.models import PriceList, PriceListFile, BotUser
# --- پایان اتصال ---

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import asyncio

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

TOKEN = PRICES_BOT_TOKEN
ADMINS = PRICES_ADMINS
DATA_DIR = "data"
USER_STATES_FILE = os.path.join(DATA_DIR, "user_states.json")
CHANNEL_ID = CHANNEL_ID
BOT_USERNAME = BOT_USERNAME
PAGE_SIZE_USER = 21
PAGE_SIZE_ADMIN = 9

# --- توابع کمکی دیتابیس (جایگزین توابع JSON) ---
@sync_to_async
def save_user_info(user):
    BotUser.objects.update_or_create(user_id=user.id, defaults={'first_name': user.first_name, 'username': user.username})

@sync_to_async
def get_all_files_from_db():
    items = PriceList.objects.all().order_by('-rank')
    result = []
    for item in items:
        result.append({
            "caption": item.title,
            "file_ids": list(item.files.values_list('telegram_file_id', flat=True)),
            "timestamp": item.updated_at.isoformat(),
            "id": item.id
        })
    return result

@sync_to_async
def db_add_price_list(title, file_ids):
    print(f"[LOG] db_add_price_list called with title={title}, file_ids={file_ids}")
    p = PriceList.objects.create(title=title)
    for f_id in file_ids:
        f_type = 'photo' if f_id.startswith('AgAC') else 'document'
        PriceListFile.objects.create(price_list=p, telegram_file_id=f_id, file_type=f_type)

@sync_to_async
def db_get_users_count():
    return BotUser.objects.count()

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
            f_type = 'photo' if f_id.startswith('AgAC') else 'document'
            PriceListFile.objects.create(price_list=item, telegram_file_id=f_id, file_type=f_type)
    except PriceList.DoesNotExist:
        pass

@sync_to_async
def db_log_event(user, event_type, event_detail=""):
    from prices.models import Log
    Log.objects.create(
        user_id=user.id,
        first_name=user.first_name,
        username=user.username,
        event_type=event_type,
        event_detail=event_detail
    )

@sync_to_async
def db_get_all_user_ids(exclude_admins=False):
    from prices.models import BotUser
    qs = BotUser.objects.all()
    if exclude_admins:
        qs = qs.exclude(user_id__in=ADMINS)
    return list(qs.values_list('user_id', flat=True))

async def log_event(user, event_type, event_detail=""):
    await db_log_event(user, event_type, event_detail)

async def notify_users(context: ContextTypes.DEFAULT_TYPE, caption: str):
    user_ids = await db_get_all_user_ids(exclude_admins=True)
    for user_id in user_ids:
        try:
            text = f"📢 لیست قیمت جدید «{caption}» به‌روزرسانی شد!\nبرای مشاهده به ربات {BOT_USERNAME} مراجعه کنید."
            await context.bot.send_message(chat_id=user_id, text=text)
        except Exception as e:
            logging.error(f"Error notifying user {user_id}: {e}")

# --- توابع مدیریت وضعیت ---
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

@sync_to_async
def db_get_all_users():
    """دریافت تمام کاربران از دیتابیس"""
    users = BotUser.objects.all().values_list('user_id', flat=True)
    return [{"user_id": uid} for uid in users]

def admin_menu():
    kb = [
        [KeyboardButton("➕ افزودن لیست قیمت"), KeyboardButton("📋 نمایش لیست‌ها")],
        [KeyboardButton("🔎 جستجو در لیست‌ها"), KeyboardButton("📄 دریافت فایل کاربران")],
        [KeyboardButton("👥 تعداد اعضا"), KeyboardButton("🚫 حذف کاربر")],
        [KeyboardButton("✉️ ارسال پیام به همه کاربران")],
        [KeyboardButton("⏪ بازگشت به منوی اصلی")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def user_menu():
    kb = [
        [KeyboardButton("📋 نمایش لیست قیمت‌ها")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def file_pagination_keyboard(files, page, total_pages, is_admin=False, search_mode=False):
    kb = []
    if is_admin:
        for idx, f in enumerate(files):
            caption = f["caption"][:20] + ("..." if len(f["caption"]) > 20 else "")
            price_id = f.get("id") if f.get("id") else None
            if search_mode:
                row = [
                    InlineKeyboardButton(caption, callback_data=f"searchshow_{price_id}_admin"),
                    InlineKeyboardButton("✏️", callback_data=f"searcheditcap_{price_id}_admin"),
                    InlineKeyboardButton("🔄", callback_data=f"searchreplace_{price_id}_admin"),
                    InlineKeyboardButton("🗑️", callback_data=f"searchdel_{price_id}_admin"),
                    InlineKeyboardButton("📢", callback_data=f"searchpub_{price_id}_admin"),
                ]
            else:
                row = [
                    InlineKeyboardButton(caption, callback_data=f"show_{page}_{price_id}"),
                    InlineKeyboardButton("✏️", callback_data=f"editcap_{page}_{price_id}"),
                    InlineKeyboardButton("🔄", callback_data=f"replace_{page}_{price_id}"),
                    InlineKeyboardButton("🗑️", callback_data=f"del_{page}_{price_id}"),
                    InlineKeyboardButton("📢", callback_data=f"pub_{page}_{price_id}"),
                ]
            kb.append(row)
    else:
        row = []
        for idx, f in enumerate(files):
            caption = f["caption"][:20] + ("..." if len(f["caption"]) > 20 else "")
            if search_mode:
                row.append(InlineKeyboardButton(caption, callback_data=f"searchshow_{idx}_user"))
            else:
                row.append(InlineKeyboardButton(caption, callback_data=f"show_{page}_{f['id']}"))
            if (idx + 1) % 3 == 0:
                kb.append(row)
                row = []
        if row:
            kb.append(row)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"page_{page-1}"))
    if page < total_pages-1:
        nav.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"page_{page+1}"))
    if nav:
        kb.append(nav)
    return InlineKeyboardMarkup(kb)

def cancel_inline():
    return InlineKeyboardMarkup([[InlineKeyboardButton("لغو", callback_data="cancel")]])

def get_page_size(is_admin):
    return PAGE_SIZE_ADMIN if is_admin else PAGE_SIZE_USER

async def send_user_file(message):
    try:
        with open(USERS_FILE, "rb") as f:
            await message.reply_document(document=f, filename="users.json", caption="فایل کاربران (users.json)")
    except Exception as e:
        logging.error(f"Error sending users file: {e}")
        await message.reply_text("ارسال فایل کاربران با خطا مواجه شد.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    is_admin = user_id in ADMINS
    clear_user_state(user_id)
    await save_user_info(user)
    await log_event(user, "start")
    if is_admin:
        await update.message.reply_text(
"""🎉 به ربات لاوان الکتریک خوش آمدید! 🎉

این ربات مخصوص مدیریت و ارسال جدیدترین لیست‌های قیمت تجهیزات برق صنعتی، روشنایی و انواع سیم و کابل است.

با استفاده از منو می‌توانید لیست جدید اضافه کنید، لیست‌ها را ببینید یا جستجو کنید و برای کاربران ارسال نمایید.

آدرس ربات جهت معرفی: {bot}
""".format(bot=BOT_USERNAME),
            reply_markup=admin_menu()
        )
    else:
        await update.message.reply_text(
f"""🎉 به ربات لاوان الکتریک خوش آمدید! 🎉

🔌 جدیدترین لیست قیمت تجهیزات برق صنعتی، روشنایی و کابل یکجا اینجاست!

✅ با زدن دکمه «📋 نمایش لیست قیمت‌ها» همه لیست‌ها برای شما آماده می‌شود.
🔎 نام هر محصول را بنویسید تا همان لحظه لیست مرتبط را پیدا کنید.

⚡️ هر روز، هر ساعت لیست‌ها آپدیت می‌شوند تا همیشه یک قدم جلوتر باشید!
👈 ربات را به دوستان و همکاران خود معرفی کنید: {BOT_USERNAME}
""",
            reply_markup=user_menu()
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    is_admin = user_id in ADMINS
    msg = update.message.text if update.message else ""
    state = get_user_state(user_id)
    state_val = state["state"] if state and "state" in state else None
    await save_user_info(user)

    if msg == "⏪ بازگشت به منوی اصلی":
        clear_user_state(user_id)
        await start(update, context)
        return

    if is_admin:
        await handle_admin(update, context, msg, state_val, update)
    else:
        if msg == "📋 نمایش لیست قیمت‌ها":
            set_user_state(user_id, "view_user", page=0)
            await log_event(user, "show_price_list")
            await show_file_list(update, context, page=0, is_admin=False)
            return
        # لاگ جستجوی کاربر
        if msg:
            await log_event(user, "search", msg.strip())
        search_term = msg.strip().lower()
        files = await get_all_files_from_db()
        matched = [f for f in files if search_term in f["caption"].lower()]
        if not matched:
            await update.message.reply_text(
f"""❗️ هیچ لیست قیمتی پیدا نشد.

برای مشاهده همه لیست‌ها روی دکمه «📋 نمایش لیست قیمت‌ها» بزنید یا محصول دیگری را جستجو کنید.

آدرس ربات: {BOT_USERNAME}"""
            , reply_markup=user_menu())
            clear_user_state(user_id)
        else:
            set_user_state(user_id, "search_result_user", search_results=matched)
            kb = file_pagination_keyboard(matched, 0, 1, is_admin=False, search_mode=True)
            await update.message.reply_text(
f"""نتایج جستجو برای شما آماده شد! روی لیست دلخواه کلیک کنید.

آدرس ربات برای معرفی به دوستان: {BOT_USERNAME}
""", reply_markup=kb)

async def handle_admin(update, context, msg, state_val, update_obj):
    user = update_obj.effective_user
    user_id = user.id
    if msg == "➕ افزودن لیست قیمت":
        set_user_state(user_id, "await_file", files=[], caption="")
        await update_obj.message.reply_text("لطفاً عکس یا سند لیست قیمت را ارسال کنید:", reply_markup=cancel_inline())
    elif msg == "📋 نمایش لیست‌ها":
        set_user_state(user_id, "view_admin", page=0)
        await log_event(user, "show_price_list")
        await show_file_list(update_obj, context, page=0, is_admin=True)
    elif msg == "🔎 جستجو در لیست‌ها":
        set_user_state(user_id, "await_admin_search")
        await update_obj.message.reply_text("نام یا بخشی از نام لیست قیمت را وارد کنید:", reply_markup=cancel_inline())
    elif msg == "👥 تعداد اعضا":
        count = await db_get_users_count(context)
        await update_obj.message.reply_text(f"تعداد کل اعضای ثبت‌شده در ربات: {count} نفر.", reply_markup=admin_menu())
    elif msg == "📄 دریافت فایل کاربران":
        if os.path.exists(USERS_FILE):
            await send_user_file(update_obj.message)
            await update_obj.message.reply_text("✅ فایل کاربران برای شما ارسال شد.", reply_markup=admin_menu())
        else:
            await update_obj.message.reply_text("فایل کاربران پیدا نشد.", reply_markup=admin_menu())
    elif msg == "🚫 حذف کاربر":
        set_user_state(user_id, "await_remove_user")
        await update_obj.message.reply_text("لطفاً آیدی عددی کاربری که می‌خواهید حذف کنید را وارد کنید:", reply_markup=cancel_inline())
    elif msg == "✉️ ارسال پیام به همه کاربران":
        set_user_state(user_id, "await_broadcast")
        await update_obj.message.reply_text("لطفاً پیام مورد نظر را بنویسید یا لغو کنید:", reply_markup=cancel_inline())
        # جلوگیری از اجرای همزمان چند استخراج
    elif state_val == "await_broadcast":
        if msg == "لغو":
            clear_user_state(user_id)
            await update_obj.message.reply_text("ارسال پیام لغو شد.", reply_markup=admin_menu())
            return
        user_ids = await db_get_all_user_ids(exclude_admins=True)
        sent_count = 0
        await update_obj.message.reply_text(f"⏳ در حال ارسال پیام به {len(user_ids)} کاربر...")
        for uid in user_ids:
            try:
                await context.bot.send_message(chat_id=uid, text=msg)
                sent_count += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                logging.warning(f"Failed to send to {uid}: {e}")
        clear_user_state(user_id)
        await update_obj.message.reply_text(f"✅ پیام به {sent_count} نفر ارسال شد.", reply_markup=admin_menu())
    elif state_val == "await_remove_user":
        uid_to_remove = msg.strip()
        users = read_json(USERS_FILE)
        if any(u["user_id"] == uid_to_remove for u in users):
            users = [u for u in users if u["user_id"] != uid_to_remove]
            write_json(USERS_FILE, users)
            await update_obj.message.reply_text(f"کاربر با آیدی {uid_to_remove} حذف شد.", reply_markup=admin_menu())
        else:
            await update_obj.message.reply_text(f"کاربری با آیدی {uid_to_remove} پیدا نشد.", reply_markup=admin_menu())
        clear_user_state(user_id)
    elif state_val == "await_admin_search":
        search_term = msg.strip().lower()
        await log_event(user, "search", msg.strip())
        files = await get_all_files_from_db()
        matched = [f for f in files if search_term in f["caption"].lower()]
        if not matched:
            await update_obj.message.reply_text("هیچ لیست قیمتی یافت نشد.", reply_markup=admin_menu())
            clear_user_state(user_id)
        else:
            set_user_state(user_id, "search_result_admin", search_results=matched)
            kb = file_pagination_keyboard(matched, 0, 1, is_admin=True, search_mode=True)
            await update_obj.message.reply_text("نتایج جستجو:", reply_markup=kb)
    elif state_val == "await_file":
        files = get_user_state(user_id).get("files", [])
        if update_obj.message.photo or update_obj.message.document:
            file_id = update_obj.message.photo[-1].file_id if update_obj.message.photo else update_obj.message.document.file_id
            files.append(file_id)
            set_user_state(user_id, "await_file", files=files)
            await update_obj.message.reply_text("فایل دریافت شد. اگر فایل دیگری هست بفرستید یا تایید کنید.", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("تایید و ادامه", callback_data="confirm_upload")],
                [InlineKeyboardButton("لغو", callback_data="cancel")]
            ]))
        else:
            await update_obj.message.reply_text("فقط عکس یا سند ارسال کنید.", reply_markup=cancel_inline())
    elif state_val == "await_caption":
        files = get_user_state(user_id).get("files", [])
        if not files:
            await update_obj.message.reply_text("هیچ فایلی ارسال نشده است.", reply_markup=admin_menu())
            clear_user_state(user_id)
            return
        caption = msg[:50]
        await db_add_price_list(caption, files)
        clear_user_state(user_id)
        await update_obj.message.reply_text(
            f"✅ لیست قیمت جدید با موفقیت اضافه شد!\nاین لیست برای همه کاربران ربات {BOT_USERNAME} قابل دسترسی است.\nحتماً ربات را به همکاران خود معرفی کنید: {BOT_USERNAME}",
            reply_markup=admin_menu())
        await notify_users(context, caption)
    elif state_val == "await_editcap":
        edit_mode = get_user_state(user_id).get("edit_mode")
        edit_id = get_user_state(user_id).get("edit_id")
        if edit_id is not None:
            await db_edit_caption_by_id(edit_id, msg[:50])
            await update_obj.message.reply_text("عنوان با موفقیت ویرایش شد.", reply_markup=admin_menu())
        else:
            await update_obj.message.reply_text("خطا: لیست قیمت مورد نظر پیدا نشد.", reply_markup=admin_menu())
        clear_user_state(user_id)
    elif state_val == "await_replacefile":
        replace_mode = get_user_state(user_id).get("replace_mode")
        replace_id = get_user_state(user_id).get("replace_id")
        replace_files = get_user_state(user_id).get("replace_files", [])
        if update_obj.message.photo or update_obj.message.document:
            file_id = update_obj.message.photo[-1].file_id if update_obj.message.photo else update_obj.message.document.file_id
            replace_files.append(file_id)
            set_user_state(user_id, "await_replacefile", replace_id=replace_id, replace_files=replace_files, replace_mode=replace_mode, search_results=get_user_state(user_id).get("search_results", []))
            await update_obj.message.reply_text("فایل دریافت شد. اگر فایل دیگری هست بفرستید یا تایید کنید.", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("تایید و ادامه", callback_data="confirm_replace")],
                [InlineKeyboardButton("لغو", callback_data="cancel")]
            ]))
        else:
            await update_obj.message.reply_text("فقط عکس یا سند ارسال کنید.", reply_markup=cancel_inline())
    else:
        await update_obj.message.reply_text("دستور نامعتبر!", reply_markup=admin_menu())

async def show_file_list(update, context, page, is_admin):
    user = update.effective_user
    files = await get_all_files_from_db()
    page_size = get_page_size(is_admin)
    total = len(files)
    total_pages = (total + page_size - 1) // page_size
    files_this_page = files[page*page_size:(page+1)*page_size]
    if not files_this_page:
        await update.effective_message.reply_text("لیست قیمت وجود ندارد.", reply_markup=admin_menu() if is_admin else user_menu())
        return
    kb = file_pagination_keyboard(files_this_page, page, total_pages, is_admin)
    await update.effective_message.reply_text(
f"""نمایش لیست قیمت‌ها ({page+1} از {total_pages})

آدرس ربات برای معرفی: {BOT_USERNAME}
""", reply_markup=kb
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    is_admin = user_id in ADMINS
    data = update.callback_query.data
    state = get_user_state(user_id)
    state_val = state["state"] if state and "state" in state else None

    files = await get_all_files_from_db()
    page = state.get("page", 0) if state else 0

    # حذف کاربر توسط ادمین با دکمه (در آینده اگر لیست دکمه‌ای ساختید)
    if data.startswith("removeuser_"):
        uid = data.split("_")[1]
        users = read_json(USERS_FILE)
        users = [u for u in users if u["user_id"] != uid]
        write_json(USERS_FILE, users)
        await update.callback_query.message.reply_text(f"کاربر با آیدی {uid} حذف شد.", reply_markup=admin_menu())
        clear_user_state(user_id)
        return

    # سرچ نتایج کاربر عادی
    if data.startswith("searchshow_") and data.endswith("_user"):
        idx = int(data.split("_")[1])
        search_results = state.get("search_results", [])
        if 0 <= idx < len(search_results):
            file = search_results[idx]
            await log_event(user, "price_click", file["caption"])
            for fid in file["file_ids"]:
                if fid.startswith("AgAC"):
                    await update.callback_query.message.reply_photo(photo=fid, caption=file["caption"])
                else:
                    await update.callback_query.message.reply_document(document=fid, caption=file["caption"])
        return

    # سرچ نتایج ادمین: نمایش
    if data.startswith("searchshow_") and data.endswith("_admin"):
        price_id = int(data.split("_")[1])
        search_results = state.get("search_results", [])
        file = next((f for f in search_results if f["id"] == price_id), None)
        if file:
            await log_event(user, "price_click", file["caption"])
            for fid in file["file_ids"]:
                if fid.startswith("AgAC"):
                    await update.callback_query.message.reply_photo(photo=fid, caption=file["caption"])
                else:
                    await update.callback_query.message.reply_document(document=fid, caption=file["caption"])
        return

    # سرچ نتایج ادمین: ویرایش نام
    if data.startswith("searcheditcap_") and data.endswith("_admin"):
        price_id = int(data.split("_")[1])
        search_results = state.get("search_results", [])
        file = next((f for f in search_results if f["id"] == price_id), None)
        if file:
            list_name = file["caption"]
            set_user_state(user_id, "await_editcap", edit_id=price_id, edit_mode="search", search_results=search_results)
            await update.callback_query.message.reply_text(f"شما در حال تغییر نام لیست قیمت {list_name} هستید.\nعنوان جدید را وارد کنید:", reply_markup=cancel_inline())
        return

    # سرچ نتایج ادمین: حذف
    if data.startswith("searchdel_") and data.endswith("_admin"):
        price_id = int(data.split("_")[1])
        search_results = state.get("search_results", [])
        file = next((f for f in search_results if f["id"] == price_id), None)
        if file:
            list_name = file["caption"]
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("تایید حذف", callback_data=f"searchconfirmdel_{price_id}_admin")],
                [InlineKeyboardButton("لغو", callback_data="cancel")]
            ])
            await update.callback_query.message.reply_text(f"شما در حال حذف لیست قیمت {list_name} هستید.\nآیا مطمئن هستید؟", reply_markup=kb)
        return

    if data.startswith("searchconfirmdel_") and data.endswith("_admin"):
        price_id = int(data.split("_")[1])
        try:
            item = await sync_to_async(PriceList.objects.get)(id=price_id)
            list_name = item.title
            await sync_to_async(item.delete)()
            await update.callback_query.message.reply_text(
f"""فایل از لیست حذف شد.

آدرس ربات برای معرفی: {BOT_USERNAME}
""", reply_markup=admin_menu())
        except PriceList.DoesNotExist:
            await update.callback_query.message.reply_text("فایل در فایل‌های اصلی پیدا نشد.", reply_markup=admin_menu())
        clear_user_state(user_id)
        return

    # سرچ نتایج ادمین: انتشار
    if data.startswith("searchpub_") and data.endswith("_admin"):
        price_id = int(data.split("_")[1])
        search_results = state.get("search_results", [])
        file = next((f for f in search_results if f["id"] == price_id), None)
        if file:
            cap = escape_html(file["caption"])
            post_caption = f"""💡 <b>لاوان الکتریک - لیست قیمت: {cap}</b> 💡\n\n📋 <b>دریافت جدیدترین لیست‌های قیمت تجهیزات برق صنعتی، روشنایی و کابل در ربات لاوان الکتریک:</b>\n{BOT_USERNAME}\n\n👈 این ربات را به دوستان و همکاران خود معرفی کنید!\n"""
            for fid in file["file_ids"]:
                if fid.startswith("AgAC"):
                    await context.bot.send_photo(chat_id=CHANNEL_ID, photo=fid, caption=post_caption, parse_mode="HTML")
                else:
                    await context.bot.send_document(chat_id=CHANNEL_ID, document=fid, caption=post_caption, parse_mode="HTML")
            await update.callback_query.message.reply_text("در کانال منتشر شد.", reply_markup=admin_menu())
        return

    # سرچ نتایج ادمین: جایگزینی فایل
    if data.startswith("searchreplace_") and data.endswith("_admin"):
        price_id = int(data.split("_")[1])
        search_results = state.get("search_results", [])
        file = next((f for f in search_results if f["id"] == price_id), None)
        if file:
            list_name = file["caption"]
            set_user_state(user_id, "await_replacefile", replace_id=price_id, replace_mode="search", replace_files=[], search_results=search_results)
            await update.callback_query.message.reply_text(f"شما در حال جایگزینی فایل‌های لیست قیمت {list_name} هستید.\nفایل‌های جدید (عکس یا سند) را یکی‌یکی ارسال کنید و در پایان تایید و ادامه را بزنید.", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("تایید و ادامه", callback_data="confirm_replace")],
                [InlineKeyboardButton("لغو", callback_data="cancel")]
            ]))
        return

    # تایید جایگزینی فایل (در نتایج سرچ یا کل)
    if is_admin and data == "confirm_replace":
        replace_mode = state.get("replace_mode")
        replace_id = state.get("replace_id")
        replace_files = state.get("replace_files", [])
        if replace_id and replace_files:
            await db_replace_files_by_id(replace_id, replace_files)
            price_obj = await sync_to_async(PriceList.objects.get)(id=replace_id)
            await update.callback_query.message.reply_text("فایل(ها) با موفقیت جایگزین شد.", reply_markup=admin_menu())
            await notify_users(context, price_obj.title)
        clear_user_state(user_id)
        return

    if data == "cancel":
        clear_user_state(user_id)
        await update.callback_query.message.reply_text("عملیات لغو شد.", reply_markup=admin_menu() if is_admin else user_menu())
        return

    if data == "confirm_upload" and is_admin:
        files_list = get_user_state(user_id).get("files", [])
        if not files_list:
            await update.callback_query.message.reply_text("هیچ فایلی آپلود نشده.", reply_markup=admin_menu())
            return
        set_user_state(user_id, "await_caption", files=files_list)
        await update.callback_query.message.reply_text("عنوان/توضیح لیست قیمت را وارد کنید:", reply_markup=cancel_inline())
        return

    if data.startswith("page_"):
        page = int(data.split("_")[1])
        set_user_state(user_id, state_val, page=page)
        await show_file_list(update, context, page, is_admin)
        return

    if data.startswith("show_"):
        page_, price_id = map(int, data.split("_")[1:])
        if is_admin:
            file = next((f for f in files if f["id"] == price_id), None)
        else:
            page_size = get_page_size(False)
            files_this_page = files[page_*page_size:(page_+1)*page_size]
            file = next((f for f in files_this_page if f["id"] == price_id), None)
        if file:
            await log_event(user, "price_click", file["caption"])
            for fid in file["file_ids"]:
                if fid.startswith("AgAC"):
                    await update.callback_query.message.reply_photo(photo=fid, caption=file["caption"])
                else:
                    await update.callback_query.message.reply_document(document=fid, caption=file["caption"])
        return

    # ویرایش نام از لیست اصلی
    if is_admin and data.startswith("editcap_"):
        page_, price_id = map(int, data.split("_")[1:])
        file = next((f for f in files if f["id"] == price_id), None)
        if file:
            list_name = file["caption"]
            set_user_state(user_id, "await_editcap", edit_id=price_id, edit_mode="main")
            await update.callback_query.message.reply_text(f"شما در حال تغییر نام لیست قیمت {list_name} هستید.\nعنوان جدید را وارد کنید:", reply_markup=cancel_inline())
        return

    # جایگزینی فایل از لیست اصلی
    if is_admin and data.startswith("replace_"):
        page_, price_id = map(int, data.split("_")[1:])
        file = next((f for f in files if f["id"] == price_id), None)
        if file:
            list_name = file["caption"]
            set_user_state(user_id, "await_replacefile", replace_id=price_id, replace_mode="main", replace_files=[])
            await update.callback_query.message.reply_text(f"شما در حال جایگزینی فایل‌های لیست قیمت {list_name} هستید.\nفایل‌های جدید (عکس یا سند) را یکی‌یکی ارسال کنید و در پایان تایید و ادامه را بزنید.", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("تایید و ادامه", callback_data="confirm_replace")],
                [InlineKeyboardButton("لغو", callback_data="cancel")]
            ]))
        return

    # حذف از لیست اصلی
    if is_admin and data.startswith("del_"):
        page_, price_id = map(int, data.split("_")[1:])
        file = next((f for f in files if f["id"] == price_id), None)
        if file:
            list_name = file["caption"]
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("تایید حذف", callback_data=f"confirmdel_{price_id}")],
                [InlineKeyboardButton("لغو", callback_data="cancel")]
            ])
            await update.callback_query.message.reply_text(f"شما در حال حذف لیست قیمت {list_name} هستید.\nآیا مطمئن هستید؟", reply_markup=kb)
        return

    if is_admin and data.startswith("confirmdel_"):
        price_id = int(data.split("_")[1])
        try:
            item = await sync_to_async(PriceList.objects.get)(id=price_id)
            list_name = item.title
            await sync_to_async(item.delete)()
            await update.callback_query.message.reply_text(
                f"لیست قیمت {list_name} با موفقیت حذف شد.\n\nآدرس ربات برای معرفی: {BOT_USERNAME}", reply_markup=admin_menu())
        except PriceList.DoesNotExist:
            await update.callback_query.message.reply_text("لیست قیمت مورد نظر پیدا نشد.", reply_markup=admin_menu())
        clear_user_state(user_id)
        return

    if is_admin and data.startswith("pub_"):
        page_, price_id = map(int, data.split("_")[1:])
        file = next((f for f in files if f["id"] == price_id), None)
        if file:
            cap = escape_html(file["caption"])
            post_caption = f"""💡 <b>لاوان الکتریک - لیست قیمت: {cap}</b> 💡\n\n📋 <b>دریافت جدیدترین لیست‌های قیمت تجهیزات برق صنعتی، روشنایی و کابل در ربات لاوان الکتریک:</b>\n{BOT_USERNAME}\n\n👈 این ربات را به دوستان و همکاران خود معرفی کنید!\n"""
            for fid in file["file_ids"]:
                if fid.startswith("AgAC"):
                    await context.bot.send_photo(chat_id=CHANNEL_ID, photo=fid, caption=post_caption, parse_mode="HTML")
                else:
                    await context.bot.send_document(chat_id=CHANNEL_ID, document=fid, caption=post_caption, parse_mode="HTML")
            await update.callback_query.message.reply_text("در کانال منتشر شد.", reply_markup=admin_menu())
        return

async def send_message_to_all_users(context: ContextTypes.DEFAULT_TYPE, text: str, exclude_admins=True):
    user_ids = await db_get_all_user_ids(exclude_admins=exclude_admins)
    sent_count = 0
    for user_id in user_ids:
        try:
            await context.bot.send_message(chat_id=user_id, text=text)
            sent_count += 1
            await asyncio.sleep(0.05)  # جلوگیری از فلود
        except Exception as e:
            logging.warning(f"Failed to send to {user_id}: {e}")
    return sent_count

async def db_get_users_count(context: ContextTypes.DEFAULT_TYPE):
    try:
        chat = await context.bot.get_chat(CHANNEL_ID)
        if hasattr(chat, 'member_count'):
            return chat.member_count
        return await context.bot.get_chat_members_count(CHANNEL_ID)
    except Exception as e:
        logging.warning(f"Failed to get members count from Telegram: {e}")
        return await sync_to_async(BotUser.objects.count)()

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.Document.ALL, handle_message))
    app.add_handler(CallbackQueryHandler(callback_handler))
    print("Bot started.")
    app.run_polling()

if __name__ == "__main__":
    main()