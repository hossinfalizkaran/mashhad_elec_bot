import os
import django
import asyncio
import random
from django.db.models import Q
from asgiref.sync import sync_to_async

# --- تنظیمات اولیه جنگو ---
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from catalog.models import Business, ClaimRequest
from config import CATALOG_BOT_TOKEN, CATALOG_ADMIN_ID # وارد شده از فایل config.py

# --- تنظیمات تلگرام ---
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton as AioInlineKeyboardButton

bot = Bot(token=CATALOG_BOT_TOKEN)
dp = Dispatcher()

PAGE_SIZE = 10

# --- وضعیت‌های FSM ---
class BotStates(StatesGroup):
    waiting_for_verify_code = State()
    waiting_for_edit_value = State()
    admin_waiting_for_search = State()
    admin_waiting_for_edit_field = State()
    admin_waiting_for_edit_value = State()
    admin_waiting_for_new_biz = State()
    user_waiting_for_claim_info = State()
    user_waiting_for_new_biz = State()
    user_waiting_for_claim_method = State()
    user_waiting_for_claim_code = State()

# --- توابع کمکی دیتابیس (Async) ---
@sync_to_async
def get_user_business(user_id):
    return Business.objects.filter(owner_telegram_id=user_id).first()

@sync_to_async
def search_biz(query):
    return list(Business.objects.filter(
        Q(shop_name__icontains=query) | 
        Q(management__icontains=query) | 
        Q(activity__icontains=query)
    ).order_by('-rank', 'shop_name')[:10])

@sync_to_async
def create_claim_and_get_code(b_id, u_id, u_name, f_name):
    # چک کردن برای جلوگیری از ثبت مالکیت تکراری اگر از قبل تایید شده
    biz = Business.objects.get(id=b_id)
    if biz.owner_telegram_id:
        return None, None
    
    code = str(random.randint(10000, 99999))
    ClaimRequest.objects.create(
        business=biz, 
        telegram_id=u_id, 
        username=u_name, 
        full_name=f_name, 
        verification_code=code,
        status='pending'
    )
    return code, biz.shop_name

@sync_to_async
def final_verify(u_id, code):
    try:
        # جستجوی درخواستی که این کد را دارد و هنوز استفاده نشده
        req = ClaimRequest.objects.get(verification_code=code, status='pending')
        biz = req.business
        biz.owner_telegram_id = u_id
        biz.is_verified = True
        biz.save()
        req.status = 'completed'
        req.save()
        return biz.shop_name
    except:
        return None

@sync_to_async
def update_biz_field(u_id, field, value):
    biz = Business.objects.get(owner_telegram_id=u_id)
    # اگر کلمه "خالی" فرستاد، فیلد پاک شود
    if value.strip() in ['خالی', 'empty', '-']:
        value = ""
    setattr(biz, field, value)
    biz.save()
    return biz.shop_name

@sync_to_async
def get_all_businesses():
    items = Business.objects.all().order_by('-rank', 'shop_name')
    result = []
    for item in items:
        result.append({
            "id": item.id,
            "shop_name": item.shop_name,
            "management": item.management,
            "activity": item.activity,
        })
    return result

# --- منوی اصلی کاربر عادی ---
def user_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 نمایش کسب‌وکارها")
    builder.button(text="🔎 جستجو")
    builder.button(text="❓ راهنما")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)

# --- صفحه‌بندی و دکمه‌های اینلاین ---
def business_pagination_keyboard(businesses, page, total_pages):
    kb = InlineKeyboardBuilder()
    for idx, b in enumerate(businesses):
        kb.button(text=b["shop_name"][:20], callback_data=f"show_{page}_{b['id']}")
    nav = []
    if page > 0:
        nav.append(AioInlineKeyboardButton(text="⬅️ قبلی", callback_data=f"page_{page-1}"))
    if page < total_pages-1:
        nav.append(AioInlineKeyboardButton(text="بعدی ➡️", callback_data=f"page_{page+1}"))
    if nav:
        kb.row(*nav)
    return kb.as_markup()

# --- ساخت منوی اصلی ---
async def main_menu_markup(user_id):
    builder = ReplyKeyboardBuilder()
    builder.button(text="🔍 جستجو")
    
    # اگر کاربر مالک کسب و کاری باشد، دکمه مدیریت را ببیند
    biz = await get_user_business(user_id)
    if biz:
        builder.button(text="⚙️ مدیریت کسب‌وکار من")
    
    builder.button(text="❓ راهنما")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)

# --- ادمین: منوی مدیریت ---
ADMIN_IDS = [int(CATALOG_ADMIN_ID)] if isinstance(CATALOG_ADMIN_ID, int) else [int(i) for i in CATALOG_ADMIN_ID]

def is_admin(user_id):
    return user_id in ADMIN_IDS

@dp.message(Command("admin"))
async def admin_menu(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("دسترسی فقط برای ادمین.")
        return
    kb = ReplyKeyboardBuilder()
    kb.button(text="🔎 جستجوی کسب‌وکار")
    kb.button(text="➕ افزودن کسب‌وکار جدید")
    kb.button(text="👤 مدیریت مالکیت")
    kb.button(text="❌ خروج از پنل ادمین")
    kb.adjust(1)
    await message.answer("پنل مدیریت فعال شد:", reply_markup=kb.as_markup(resize_keyboard=True))

@dp.message(lambda m: is_admin(m.from_user.id) and m.text == "🔎 جستجوی کسب‌وکار")
async def admin_search_biz(message: types.Message, state: FSMContext):
    await state.set_state(BotStates.admin_waiting_for_search)
    await message.answer("نام یا زمینه فعالیت کسب‌وکار را وارد کنید:")

@dp.message(BotStates.admin_waiting_for_search)
async def admin_do_search(message: types.Message, state: FSMContext):
    results = await search_biz(message.text)
    if not results:
        await message.answer("موردی یافت نشد.")
        await state.clear()
        return
    kb = InlineKeyboardBuilder()
    for b in results:
        kb.button(text=b.shop_name, callback_data=f"admin_edit_{b.id}")
    kb.adjust(1)
    await message.answer("نتایج جستجو (برای ویرایش کلیک کنید):", reply_markup=kb.as_markup())
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("admin_edit_"))
async def admin_edit_biz(cb: types.CallbackQuery, state: FSMContext):
    biz_id = int(cb.data.split("_")[2])
    biz = await sync_to_async(Business.objects.get)(id=biz_id)
    await state.update_data(biz_id=biz_id)
    kb = InlineKeyboardBuilder()
    fields = [
        ("shop_name", "نام"), ("management", "مدیر"), ("address", "آدرس"),
        ("landline", "تلفن ثابت"), ("mobile", "همراه"), ("activity", "فعالیت")
    ]
    for f, n in fields:
        kb.button(text=f"ویرایش {n}", callback_data=f"admin_editfield_{f}")
    kb.button(text="حذف کسب‌وکار", callback_data=f"admin_delete_{biz_id}")
    kb.button(text="مدیریت مالکیت", callback_data=f"admin_owner_{biz_id}")
    kb.adjust(2)
    await cb.message.answer(f"✏️ ویرایش کسب‌وکار:\n🏪 {biz.shop_name}", reply_markup=kb.as_markup())
    await cb.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_editfield_"))
async def admin_edit_field(cb: types.CallbackQuery, state: FSMContext):
    field = cb.data.split("_")[2]
    data = await state.get_data()
    await state.update_data(edit_field=field)
    await cb.message.answer(f"مقدار جدید برای {field} را وارد کنید:")
    await state.set_state(BotStates.admin_waiting_for_edit_value)
    await cb.answer()

@dp.message(BotStates.admin_waiting_for_edit_value)
async def admin_save_edit(message: types.Message, state: FSMContext):
    data = await state.get_data()
    biz_id = data.get("biz_id")
    field = data.get("edit_field")
    biz = await sync_to_async(Business.objects.get)(id=biz_id)
    setattr(biz, field, message.text)
    biz.save()
    await message.answer("✅ ویرایش انجام شد.")
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("admin_delete_"))
async def admin_delete_biz(cb: types.CallbackQuery, state: FSMContext):
    biz_id = int(cb.data.split("_")[2])
    await sync_to_async(Business.objects.get(id=biz_id).delete)()
    await cb.message.answer("کسب‌وکار حذف شد.")
    await cb.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_owner_"))
async def admin_owner_menu(cb: types.CallbackQuery, state: FSMContext):
    biz_id = int(cb.data.split("_")[2])
    biz = await sync_to_async(Business.objects.get)(id=biz_id)
    kb = InlineKeyboardBuilder()
    kb.button(text="دادن مالکیت به کاربر", callback_data=f"admin_setowner_{biz_id}")
    kb.button(text="حذف مالکیت از کاربر", callback_data=f"admin_removeowner_{biz_id}")
    kb.adjust(1)
    await cb.message.answer(f"مدیریت مالکیت برای {biz.shop_name}", reply_markup=kb.as_markup())
    await cb.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_setowner_"))
async def admin_set_owner(cb: types.CallbackQuery, state: FSMContext):
    biz_id = int(cb.data.split("_")[2])
    await state.update_data(biz_id=biz_id)
    await cb.message.answer("آیدی عددی کاربر را وارد کنید:")
    await state.set_state(BotStates.admin_waiting_for_edit_field)
    await cb.answer()

@dp.message(BotStates.admin_waiting_for_edit_field)
async def admin_save_owner(message: types.Message, state: FSMContext):
    data = await state.get_data()
    biz_id = data.get("biz_id")
    user_id = int(message.text.strip())
    biz = await sync_to_async(Business.objects.get)(id=biz_id)
    biz.owner_telegram_id = user_id
    biz.is_verified = True
    biz.save()
    await message.answer("مالکیت به کاربر داده شد.")
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("admin_removeowner_"))
async def admin_remove_owner(cb: types.CallbackQuery, state: FSMContext):
    biz_id = int(cb.data.split("_")[2])
    biz = await sync_to_async(Business.objects.get)(id=biz_id)
    biz.owner_telegram_id = None
    biz.is_verified = False
    biz.save()
    await cb.message.answer("مالکیت حذف شد.")
    await cb.answer()

@dp.message(lambda m: is_admin(m.from_user.id) and m.text == "➕ افزودن کسب‌وکار جدید")
async def admin_add_biz(message: types.Message, state: FSMContext):
    await message.answer("نام کسب‌وکار جدید را وارد کنید:")
    await state.set_state(BotStates.admin_waiting_for_new_biz)

@dp.message(BotStates.admin_waiting_for_new_biz)
async def admin_save_new_biz(message: types.Message, state: FSMContext):
    name = message.text.strip()
    biz = await sync_to_async(Business.objects.create)(shop_name=name)
    await message.answer(f"کسب‌وکار جدید با نام {name} ثبت شد.")
    await state.clear()

# --- هندلرهای دستورات ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"سلام {message.from_user.full_name} عزیز\nبه سامانه جستجوی همکاران برق مشهد خوش آمدید.\nنام فروشگاه یا زمینه فعالیت را بنویسید:",
        reply_markup=user_menu()
    )

@dp.message(Command("cancel"))
@dp.message(F.text == "❌ انصراف")
async def cancel_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("عملیات لغو شد. به منوی اصلی برگشتیم.", 
                         reply_markup=user_menu())

@dp.message(F.text == "❓ راهنما")
async def help_msg(message: types.Message):
    guide = (
        "💡 نحوه کار با بات:\n"
        "1- هر متنی بفرستید در نام و فعالیت فروشگاه‌ها جستجو می‌شود.\n"
        "2- با کلیک روی جزئیات، آدرس و تلفن را ببینید.\n"
        "3- اگر همکار هستید، دکمه 'ادعا' را بزنید تا کد تایید برایتان صادر شود.\n"
        "4- پس از دریافت کد از مدیریت، دستور /verify را بزنید."
    )
    await message.answer(guide)

# --- هندلر پیام کاربر عادی ---
@dp.message(lambda m: not m.text.startswith('/') and m.text not in ["❌ انصراف", "❓ راهنما", "⚙️ مدیریت کسب‌وکار من"])
async def handle_user_message(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text == "📋 نمایش کسب‌وکارها":
        await show_business_list(message, page=0)
    elif text == "🔎 جستجو":
        await message.answer("نام یا زمینه فعالیت را بنویسید:", reply_markup=user_menu())
    else:
        # سرچ
        results = await search_biz(text)
        if not results:
            await message.answer("موردی یافت نشد.", reply_markup=user_menu())
            return
        kb = InlineKeyboardBuilder()
        for b in results:
            kb.button(text=b.shop_name, callback_data=f"show_search_{b.id}")
        kb.adjust(1)
        await message.answer("نتایج جستجو:", reply_markup=kb.as_markup())

# --- نمایش لیست با صفحه‌بندی ---
async def show_business_list(message, page=0):
    all_biz = await get_all_businesses()
    total_pages = (len(all_biz) + PAGE_SIZE - 1) // PAGE_SIZE
    biz_this_page = all_biz[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
    if not biz_this_page:
        await message.answer("کسب‌وکاری وجود ندارد.", reply_markup=user_menu()); return
    kb = business_pagination_keyboard(biz_this_page, page, total_pages)
    await message.answer(f"صفحه {page+1} از {total_pages}", reply_markup=kb)

# --- هندلر callback برای نمایش جزئیات و صفحه‌بندی ---
@dp.callback_query(lambda c: c.data.startswith("show_"))
async def show_business_detail(cb: types.CallbackQuery):
    parts = cb.data.split("_")
    if parts[1] == "search":
        biz_id = int(parts[2])
    else:
        biz_id = int(parts[2])
    biz = await sync_to_async(Business.objects.get)(id=biz_id)
    text = (
        f"🏪 {biz.shop_name}\n"
        f"👤 مدیر: {biz.management or '---'}\n"
        f"📍 آدرس: {biz.address or '---'}\n"
        f"📞 ثابت: {biz.landline or '---'}\n"
        f"📱 همراه: {biz.mobile or '---'}\n"
        f"⚙️ فعالیت: {biz.activity or '---'}"
    )
    await cb.message.answer(text, reply_markup=user_menu())
    await cb.answer()

@dp.callback_query(lambda c: c.data.startswith("page_"))
async def paginate_business(cb: types.CallbackQuery):
    page = int(cb.data.split("_")[1])
    await show_business_list(cb.message, page)
    await cb.answer()

# --- فرایند ورود کد تایید ---

@dp.message(Command("verify"))
async def start_v(message: types.Message, state: FSMContext):
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ انصراف")
    await message.answer("🔢 لطفا کد تایید ۵ رقمی دریافتی را وارد کنید:", 
                         reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(BotStates.waiting_for_verify_code)

@dp.message(BotStates.waiting_for_verify_code)
async def check_v(message: types.Message, state: FSMContext):
    if message.text == "❌ انصراف":
        await cancel_handler(message, state)
        return

    input_code = message.text.strip()
    shop = await final_verify(message.from_user.id, input_code)
    
    if shop:
        await message.answer(f"✅ تایید شد! شما اکنون مالک مدیریت فروشگاه «{shop}» هستید.", 
                             reply_markup=user_menu())
        await state.clear()
    else:
        # در هر صورت استیت را پاک میکنیم تا کاربر قفل نشود
        await state.clear()
        await message.answer("❌ کد وارد شده اشتباه یا منقضی شده است.\nمیتوانید مجدد جستجو کنید یا کد صحیح را با /verify بزنید.",
                             reply_markup=user_menu())

# --- پنل مدیریت مالک ---

@dp.message(F.text == "⚙️ مدیریت کسب‌وکار من")
async def owner_panel(message: types.Message):
    biz = await get_user_business(message.from_user.id)
    if not biz:
        await message.answer("⚠️ شما هنوز کسب‌وکاری را ثبت نکرده‌اید.")
        return

    kb = InlineKeyboardBuilder()
    fields = [
        ('shop_name','ویرایش نام'),('management','ویرایش مدیر'),
        ('address','ویرایش آدرس'),('landline','تلفن ثابت'),
        ('mobile','تلفن همراه'),('activity','زمینه فعالیت')
    ]
    for f_code, n in fields:
        kb.button(text=n, callback_data=f"editfield_{f_code}")
    kb.adjust(2)
    
    status = "✅ تایید شده" if biz.is_verified else "⏳ در انتظار"
    await message.answer(f"🛠 مدیریت کسب‌وکار: {biz.shop_name}\nوضعیت: {status}\n\nکدام بخش را ویرایش می‌کنید؟", 
                         reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("editfield_"))
async def ask_value(cb: types.CallbackQuery, state: FSMContext):
    field = cb.data.split("_")[1]
    await state.update_data(f=field)
    
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ انصراف")
    
    await cb.message.answer(f"🔸 لطفا مقدار جدید را ارسال کنید:\n(برای پاک کردن، کلمه 'خالی' را بفرستید)", 
                            reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(BotStates.waiting_for_edit_value)
    await cb.answer()

@dp.message(BotStates.waiting_for_edit_value)
async def do_edit(message: types.Message, state: FSMContext):
    if message.text == "❌ انصراف":
        await cancel_handler(message, state)
        return

    data = await state.get_data()
    shop = await update_biz_field(message.from_user.id, data['f'], message.text)
    await state.clear()
    await message.answer(f"✅ اطلاعات «{shop}» بروزرسانی شد.", 
                         reply_markup=user_menu())

# --- جستجو و نمایش نتایج ---

@dp.message(lambda m: not m.text.startswith('/'))
async def handle_search(message: types.Message, state: FSMContext):
    # اگر کاربر در وضعیتی (مثل انتظار برای کد) بود، سرچ اجرا نشود
    if await state.get_state() is not None:
        return

    res = await search_biz(message.text)
    if not res:
        await message.answer("🔍 متاسفانه موردی یافت نشد.")
        return

    for item in res:
        kb = InlineKeyboardBuilder()
        kb.button(text="📍 مشاهده جزئیات", callback_data=f"info_{item.id}")
        await message.answer(f"🏪 {item.shop_name}\n👤 مدیر: {item.management or '---'}", 
                             reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("info_"))
async def show_info(cb: types.CallbackQuery):
    biz_id = cb.data.split("_")[1]
    biz = await sync_to_async(Business.objects.get)(id=biz_id)
    
    text = (
        f"🏪 **{biz.shop_name}**\n"
        f"👤 مدیریت: {biz.management or '---'}\n"
        f"📍 آدرس: {biz.address or '---'}\n"
        f"📞 ثابت: `{biz.landline or '---'}`\n"
        f"📱 همراه: `{biz.mobile or '---'}`\n"
        f"⚙️ فعالیت: {biz.activity or '---'}"
    )
    
    kb = InlineKeyboardBuilder()
    # اگر کسب و کار صاحب نداشته باشد، دکمه ادعا نشان داده شود
    if not biz.owner_telegram_id:
        kb.button(text="🙋‍♂️ این کسب‌ و کار متعلق به من است", callback_data=f"claim_{biz.id}")
    
    await cb.message.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    await cb.answer()

@dp.callback_query(lambda c: c.data.startswith("claim_"))
async def process_claim(cb: types.CallbackQuery, state: FSMContext):
    kb = InlineKeyboardBuilder()
    kb.button(text="ارسال اطلاعات به ادمین", callback_data=f"claim_method_admin_{cb.data.split('_')[1]}")
    kb.button(text="دریافت کد تایید", callback_data=f"claim_method_code_{cb.data.split('_')[1]}")
    kb.button(text="تماس با ادمین", callback_data=f"claim_method_contact_{cb.data.split('_')[1]}")
    kb.adjust(1)
    await cb.message.answer("روش ادعای مالکیت را انتخاب کنید:", reply_markup=kb.as_markup())
    await cb.answer()

@dp.callback_query(lambda c: c.data.startswith("claim_method_admin_"))
async def claim_method_admin(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(biz_id=cb.data.split('_')[-1])
    await cb.message.answer("لطفا اطلاعات خود را (نام، شماره تماس و توضیح) بنویسید تا برای ادمین ارسال شود:")
    await state.set_state(BotStates.user_waiting_for_claim_info)
    await cb.answer()

@dp.message(BotStates.user_waiting_for_claim_info)
async def user_send_claim_info(message: types.Message, state: FSMContext):
    data = await state.get_data()
    biz_id = data.get("biz_id")
    info = message.text
    await bot.send_message(CATALOG_ADMIN_ID, f"درخواست مالکیت کسب‌وکار {biz_id} توسط کاربر:\n{info}")
    await message.answer("درخواست شما برای ادمین ارسال شد. منتظر تماس باشید.")
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("claim_method_code_"))
async def claim_method_code(cb: types.CallbackQuery, state: FSMContext):
    u_id = cb.from_user.id
    u_name = cb.from_user.username
    f_name = cb.from_user.full_name
    biz_id = cb.data.split('_')[-1]
    code, s_name = await create_claim_and_get_code(biz_id, u_id, u_name, f_name)
    if code:
        admin_text = (
            f"🚨 درخواست ادعای مالکیت جدید\n\n"
            f"🏪 کسب‌وکار: {s_name}\n"
            f"👤 کاربر: {f_name}\n"
            f"🆔 یوزرنیم: @{u_name}\n"
            f"🔢 کد تایید برای ارسال به کاربر: `{code}`"
        )
        await bot.send_message(CATALOG_ADMIN_ID, admin_text, parse_mode="Markdown")
        await cb.message.answer(
            "✅ درخواست شما ثبت و برای مدیریت ارسال شد.\nپس از احراز هویت توسط مدیریت، کد تایید را دریافت و با دستور /verify وارد کنید.")
    else:
        await cb.message.answer("⚠️ این کسب‌وکار قبلاً توسط شخص دیگری ادعا شده یا در حال بررسی است.")
    await cb.answer()

@dp.callback_query(lambda c: c.data.startswith("claim_method_contact_"))
async def claim_method_contact(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer(f"برای احراز هویت با ادمین تماس بگیرید: @{CATALOG_ADMIN_ID}")
    await cb.answer()

@dp.message(lambda m: m.text == "➕ ثبت کسب‌وکار جدید")
async def user_add_biz(message: types.Message, state: FSMContext):
    await message.answer("نام کسب‌وکار جدید را وارد کنید:")
    await state.set_state(BotStates.user_waiting_for_new_biz)

@dp.message(BotStates.user_waiting_for_new_biz)
async def user_save_new_biz(message: types.Message, state: FSMContext):
    name = message.text.strip()
    # سه روش ادعا را به کاربر نشان بده
    kb = InlineKeyboardBuilder()
    kb.button(text="ارسال اطلاعات به ادمین", callback_data=f"claim_method_admin_new_{name}")
    kb.button(text="دریافت کد تایید", callback_data=f"claim_method_code_new_{name}")
    kb.button(text="تماس با ادمین", callback_data=f"claim_method_contact_new_{name}")
    kb.adjust(1)
    await message.answer("روش ثبت و مالکیت را انتخاب کنید:", reply_markup=kb.as_markup())
    await state.clear()

# --- شروع به کار بات ---
async def main():
    print("Bot is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped.")