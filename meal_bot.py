import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Protection
import json
import hashlib
import os
from datetime import datetime

# تنظیمات لاگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# فایل‌ها
EXCEL_FILE = "meal_plan.xlsx"
USERS_FILE = "users.json"
LOG_FILE = "change_log.txt"
MENU_FILE = "daily_menus.json"
EXCEL_PASSWORD = "MealPlanner2024!@#"

# States برای ConversationHandler
(LOGIN_USERNAME, LOGIN_PASSWORD, ADD_USER_USERNAME, ADD_USER_FULLNAME, 
 ADD_USER_PASSWORD, CHANGE_PASSWORD_CURRENT, CHANGE_PASSWORD_NEW, 
 CHANGE_PASSWORD_CONFIRM, SELECT_WEEK, SELECT_DAY, EDIT_USER_SELECT,
 EDIT_USER_WEEK, EDIT_USER_DAY) = range(13)

# ذخیره وضعیت کاربران
user_sessions = {}

def hash_password(password):
    """رمزنگاری رمز عبور"""
    return hashlib.sha256(password.encode()).hexdigest()

def initialize_files():
    """ایجاد فایل‌های اولیه"""
    if not os.path.exists(USERS_FILE):
        default_users = {
            "admin": {
                "password": hash_password("admin123"),
                "is_admin": True,
                "full_name": "مدیر سیستم",
                "telegram_id": None
            }
        }
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_users, f, ensure_ascii=False, indent=2)
    
    if not os.path.exists(MENU_FILE):
        default_menu = {
            f"week_{w+1}": {
                f"day_{d+1}": {"meals": [], "desserts": []}
                for d in range(5)
            }
            for w in range(4)
        }
        with open(MENU_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_menu, f, ensure_ascii=False, indent=2)
    
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.write("=== گزارش تغییرات برنامه غذایی ===\n")
            f.write(f"تاریخ ایجاد: {datetime.now().strftime('%Y/%m/%d - %H:%M:%S')}\n")
            f.write("="*50 + "\n\n")
    
    if not os.path.exists(EXCEL_FILE):
        create_excel()

def create_excel():
    """ایجاد فایل اکسل"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "برنامه غذایی"
    ws.sheet_view.rightToLeft = True
    
    ws['A1'] = "نام و نام خانوادگی"
    days = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه']
    col = 2
    
    for week in range(4):
        for day in days:
            ws.cell(row=1, column=col, value=f"{day} - هفته {week+1}")
            ws.cell(row=2, column=col, value="غذا")
            ws.cell(row=2, column=col+1, value="دسر")
            col += 2
    
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    
    for row in [1, 2]:
        for cell in ws[row]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
    
    ws.column_dimensions['A'].width = 25
    for col in range(2, ws.max_column + 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 15
    
    wb.save(EXCEL_FILE)
    protect_excel()

def protect_excel():
    """قفل کردن اکسل"""
    try:
        wb = openpyxl.load_workbook(EXCEL_FILE)
        ws = wb.active
        for row in ws.iter_rows():
            for cell in row:
                cell.protection = Protection(locked=True, hidden=False)
        ws.protection.sheet = True
        ws.protection.password = EXCEL_PASSWORD
        wb.save(EXCEL_FILE)
    except Exception as e:
        logger.error(f"خطا در قفل کردن: {e}")

def unprotect_excel():
    """باز کردن قفل اکسل"""
    try:
        wb = openpyxl.load_workbook(EXCEL_FILE)
        ws = wb.active
        ws.protection.sheet = False
        ws.protection.password = ''
        wb.save(EXCEL_FILE)
        wb = openpyxl.load_workbook(EXCEL_FILE)
        ws = wb.active
        return wb, ws
    except Exception as e:
        logger.error(f"خطا در باز کردن قفل: {e}")
        return None, None

def log_change(user_fullname):
    """ثبت در لاگ"""
    timestamp = datetime.now().strftime('%Y/%m/%d - %H:%M:%S')
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"کاربر: {user_fullname}\n")
        f.write(f"زمان تغییر: {timestamp}\n")
        f.write("-"*50 + "\n")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ربات"""
    telegram_id = update.effective_user.id
    
    # بررسی اگر کاربر لاگین کرده
    if telegram_id in user_sessions:
        await show_main_menu(update, context)
        return
    
    keyboard = [
        [KeyboardButton("🔐 ورود به سیستم")],
        [KeyboardButton("👁️ مشاهده برنامه غذایی")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "🍽️ *به سیستم مدیریت برنامه غذایی خوش آمدید*\n\n"
        "لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def login_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع فرآیند ورود"""
    await update.message.reply_text(
        "🔐 *ورود به سیستم*\n\n"
        "لطفاً نام کاربری خود را وارد کنید:\n\n"
        "نام کاربری و رمز پیش‌فرض ادمین:\n"
        "`admin` / `admin123`",
        parse_mode='Markdown'
    )
    return LOGIN_USERNAME

async def login_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت نام کاربری"""
    context.user_data['login_username'] = update.message.text.strip()
    await update.message.reply_text("🔑 حالا رمز عبور خود را وارد کنید:")
    return LOGIN_PASSWORD

async def login_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بررسی رمز عبور و ورود"""
    username = context.user_data['login_username']
    password = update.message.text
    telegram_id = update.effective_user.id
    
    # حذف پیام رمز عبور
    await update.message.delete()
    
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        users = json.load(f)
    
    if username in users and users[username]['password'] == hash_password(password):
        # ذخیره telegram_id
        users[username]['telegram_id'] = telegram_id
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        
        # ذخیره session
        user_sessions[telegram_id] = {
            'username': username,
            'is_admin': users[username].get('is_admin', False),
            'full_name': users[username]['full_name']
        }
        
        await update.message.reply_text(
            f"✅ خوش آمدید {users[username]['full_name']}!\n\n"
            "از منوی زیر استفاده کنید:"
        )
        await show_main_menu(update, context)
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ نام کاربری یا رمز عبور اشتباه است.\n\n"
            "دوباره امتحان کنید یا /cancel برای لغو"
        )
        return LOGIN_USERNAME

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش منوی اصلی"""
    telegram_id = update.effective_user.id
    
    if telegram_id not in user_sessions:
        await start(update, context)
        return
    
    session = user_sessions[telegram_id]
    
    if session['is_admin']:
        keyboard = [
            [KeyboardButton("➕ افزودن کاربر"), KeyboardButton("👥 لیست کاربران")],
            [KeyboardButton("🍽️ مدیریت منوی غذایی"), KeyboardButton("✏️ ویرایش غذای کاربران")],
            [KeyboardButton("👁️ مشاهده برنامه"), KeyboardButton("📋 گزارش تغییرات")],
            [KeyboardButton("🔑 تغییر رمز عبور"), KeyboardButton("🚪 خروج")]
        ]
    else:
        keyboard = [
            [KeyboardButton("🍽️ انتخاب غذاهای من")],
            [KeyboardButton("👁️ مشاهده برنامه")],
            [KeyboardButton("🔑 تغییر رمز عبور"), KeyboardButton("🚪 خروج")]
        ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    message = f"🏠 *منوی اصلی*\n\n" \
              f"👤 {session['full_name']}\n" \
              f"{'👑 مدیر سیستم' if session['is_admin'] else '👤 کاربر'}"
    
    if update.message:
        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await update.callback_query.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)

async def view_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مشاهده برنامه غذایی"""
    try:
        wb = openpyxl.load_workbook(EXCEL_FILE)
        ws = wb.active
        
        message = "📅 *برنامه غذایی*\n\n"
        
        # خواندن هدرها و داده‌ها
        for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=min(ws.max_row, 12)), 1):
            line = []
            for cell in row:
                value = str(cell.value if cell.value else "-")
                line.append(value[:15])
            
            if row_idx <= 2:
                message += "`" + " | ".join(line) + "`\n"
                if row_idx == 2:
                    message += "─" * 50 + "\n"
            else:
                message += " | ".join(line) + "\n"
        
        if ws.max_row > 12:
            message += f"\n... و {ws.max_row - 12} سطر دیگر"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در خواندن فایل: {str(e)}")

async def add_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع افزودن کاربر"""
    telegram_id = update.effective_user.id
    if telegram_id not in user_sessions or not user_sessions[telegram_id]['is_admin']:
        await update.message.reply_text("⛔ شما دسترسی ندارید!")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "➕ *افزودن کاربر جدید*\n\n"
        "نام کاربری را وارد کنید:\n"
        "(فقط حروف انگلیسی و اعداد)",
        parse_mode='Markdown'
    )
    return ADD_USER_USERNAME

async def add_user_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت نام کاربری"""
    username = update.message.text.strip()
    
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        users = json.load(f)
    
    if username in users:
        await update.message.reply_text("❌ این نام کاربری قبلاً ثبت شده است. دوباره امتحان کنید:")
        return ADD_USER_USERNAME
    
    context.user_data['new_username'] = username
    await update.message.reply_text("✅ نام و نام خانوادگی را وارد کنید:")
    return ADD_USER_FULLNAME

async def add_user_fullname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت نام کامل"""
    context.user_data['new_fullname'] = update.message.text.strip()
    await update.message.reply_text("🔑 رمز عبور را وارد کنید (حداقل 4 کاراکتر):")
    return ADD_USER_PASSWORD

async def add_user_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ذخیره کاربر جدید"""
    password = update.message.text
    await update.message.delete()
    
    if len(password) < 4:
        await update.message.reply_text("❌ رمز عبور باید حداقل 4 کاراکتر باشد. دوباره وارد کنید:")
        return ADD_USER_PASSWORD
    
    username = context.user_data['new_username']
    fullname = context.user_data['new_fullname']
    
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        users = json.load(f)
    
    users[username] = {
        "password": hash_password(password),
        "is_admin": False,
        "full_name": fullname,
        "telegram_id": None
    }
    
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    
    # افزودن به اکسل
    wb, ws = unprotect_excel()
    if wb and ws:
        row = 3
        while ws.cell(row=row, column=1).value:
            row += 1
        ws.cell(row=row, column=1, value=fullname)
        wb.save(EXCEL_FILE)
        protect_excel()
    
    await update.message.reply_text(
        f"✅ کاربر {fullname} با موفقیت اضافه شد!\n\n"
        f"نام کاربری: `{username}`\n"
        f"رمز عبور: ||{password}||\n\n"
        "این اطلاعات را به کاربر بدهید.",
        parse_mode='Markdown'
    )
    
    context.user_data.clear()
    return ConversationHandler.END

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لیست کاربران"""
    telegram_id = update.effective_user.id
    if telegram_id not in user_sessions or not user_sessions[telegram_id]['is_admin']:
        await update.message.reply_text("⛔ شما دسترسی ندارید!")
        return
    
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        users = json.load(f)
    
    message = "👥 *لیست کاربران:*\n\n"
    for username, data in users.items():
        role = "👑 ادمین" if data.get('is_admin') else "👤 کاربر"
        status = "🟢 متصل" if data.get('telegram_id') else "⚪ هنوز وارد نشده"
        message += f"{role} {data['full_name']}\n"
        message += f"   نام کاربری: `{username}`\n"
        message += f"   وضعیت: {status}\n\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def manage_menu_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع مدیریت منو"""
    telegram_id = update.effective_user.id
    if telegram_id not in user_sessions or not user_sessions[telegram_id]['is_admin']:
        await update.message.reply_text("⛔ شما دسترسی ندارید!")
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton("هفته 1", callback_data="menu_week_1")],
        [InlineKeyboardButton("هفته 2", callback_data="menu_week_2")],
        [InlineKeyboardButton("هفته 3", callback_data="menu_week_3")],
        [InlineKeyboardButton("هفته 4", callback_data="menu_week_4")],
        [InlineKeyboardButton("❌ انصراف", callback_data="menu_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🍽️ *مدیریت منوی غذایی*\n\n"
        "کدام هفته را میخواهید مدیریت کنید؟",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    return SELECT_WEEK

async def menu_select_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتخاب هفته"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "menu_cancel":
        await query.edit_message_text("❌ لغو شد.")
        return ConversationHandler.END
    
    week = query.data.split('_')[2]
    context.user_data['selected_week'] = week
    
    keyboard = [
        [InlineKeyboardButton("شنبه", callback_data="menu_day_1")],
        [InlineKeyboardButton("یکشنبه", callback_data="menu_day_2")],
        [InlineKeyboardButton("دوشنبه", callback_data="menu_day_3")],
        [InlineKeyboardButton("سه‌شنبه", callback_data="menu_day_4")],
        [InlineKeyboardButton("چهارشنبه", callback_data="menu_day_5")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📅 هفته {week}\n\n"
        "کدام روز را میخواهید مدیریت کنید؟",
        reply_markup=reply_markup
    )
    return SELECT_DAY

async def menu_select_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش منوی روز و امکان ویرایش"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "menu_back":
        return await manage_menu_start(update, context)
    
    day = query.data.split('_')[2]
    week = context.user_data['selected_week']
    context.user_data['selected_day'] = day
    
    with open(MENU_FILE, 'r', encoding='utf-8') as f:
        menu_data = json.load(f)
    
    day_menu = menu_data[f'week_{week}'][f'day_{day}']
    
    days_name = {1: "شنبه", 2: "یکشنبه", 3: "دوشنبه", 4: "سه‌شنبه", 5: "چهارشنبه"}
    
    message = f"📅 *هفته {week} - {days_name[int(day)]}*\n\n"
    message += "🍽️ *غذاها:*\n"
    if day_menu['meals']:
        for meal in day_menu['meals']:
            message += f"  • {meal}\n"
    else:
        message += "  هیچ غذایی تعریف نشده\n"
    
    message += "\n🍰 *دسرها:*\n"
    if day_menu['desserts']:
        for dessert in day_menu['desserts']:
            message += f"  • {dessert}\n"
    else:
        message += "  هیچ دسری تعریف نشده\n"
    
    message += "\n➕ برای افزودن، نام غذا یا دسر را بفرستید:\n"
    message += "`غذا: نام_غذا`\n"
    message += "`دسر: نام_دسر`\n\n"
    message += "یا از دکمه‌های زیر استفاده کنید:"
    
    keyboard = [
        [InlineKeyboardButton("🗑️ پاک کردن غذا", callback_data=f"delete_meal_{week}_{day}")],
        [InlineKeyboardButton("🗑️ پاک کردن دسر", callback_data=f"delete_dessert_{week}_{day}")],
        [InlineKeyboardButton("✅ اتمام", callback_data="menu_done")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    return SELECT_DAY

async def handle_menu_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت پیام برای افزودن غذا/دسر"""
    telegram_id = update.effective_user.id
    if telegram_id not in user_sessions or not user_sessions[telegram_id]['is_admin']:
        return
    
    text = update.message.text.strip()
    
    if not text.startswith(('غذا:', 'دسر:')):
        return
    
    if 'selected_week' not in context.user_data or 'selected_day' not in context.user_data:
        await update.message.reply_text("❌ لطفاً ابتدا روز را از منو انتخاب کنید.")
        return
    
    week = context.user_data['selected_week']
    day = context.user_data['selected_day']
    
    with open(MENU_FILE, 'r', encoding='utf-8') as f:
        menu_data = json.load(f)
    
    if text.startswith('غذا:'):
        item_name = text.replace('غذا:', '').strip()
        menu_data[f'week_{week}'][f'day_{day}']['meals'].append(item_name)
        item_type = "غذا"
    else:
        item_name = text.replace('دسر:', '').strip()
        menu_data[f'week_{week}'][f'day_{day}']['desserts'].append(item_name)
        item_type = "دسر"
    
    with open(MENU_FILE, 'w', encoding='utf-8') as f:
        json.dump(menu_data, f, ensure_ascii=False, indent=2)
    
    await update.message.reply_text(f"✅ {item_type} «{item_name}» اضافه شد!")

async def delete_menu_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف غذا یا دسر"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    item_type = parts[1]  # meal or dessert
    week = parts[2]
    day = parts[3]
    
    with open(MENU_FILE, 'r', encoding='utf-8') as f:
        menu_data = json.load(f)
    
    items = menu_data[f'week_{week}'][f'day_{day}']['meals' if item_type == 'meal' else 'desserts']
    
    if not items:
        await query.answer("❌ هیچ موردی برای حذف وجود ندارد!", show_alert=True)
        return SELECT_DAY
    
    keyboard = []
    for idx, item in enumerate(items):
        keyboard.append([InlineKeyboardButton(f"🗑️ {item}", callback_data=f"confirm_delete_{item_type}_{week}_{day}_{idx}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"menu_day_{day}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"کدام مورد را میخواهید حذف کنید؟",
        reply_markup=reply_markup
    )
    return SELECT_DAY

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأیید حذف"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    item_type = parts[2]
    week = parts[3]
    day = parts[4]
    idx = int(parts[5])
    
    with open(MENU_FILE, 'r', encoding='utf-8') as f:
        menu_data = json.load(f)
    
    key = 'meals' if item_type == 'meal' else 'desserts'
    deleted_item = menu_data[f'week_{week}'][f'day_{day}'][key].pop(idx)
    
    with open(MENU_FILE, 'w', encoding='utf-8') as f:
        json.dump(menu_data, f, ensure_ascii=False, indent=2)
    
    await query.answer(f"✅ {deleted_item} حذف شد!", show_alert=True)
    
    # بازگشت به منوی روز
    context.user_data['selected_week'] = week
    context.user_data['selected_day'] = day
    
    # ساختن query جدید
    query.data = f"menu_day_{day}"
    await menu_select_day(update, context)
    return SELECT_DAY

async def edit_user_meals_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ویرایش غذای کاربران توسط ادمین"""
    telegram_id = update.effective_user.id
    if telegram_id not in user_sessions or not user_sessions[telegram_id]['is_admin']:
        await update.message.reply_text("⛔ شما دسترسی ندارید!")
        return ConversationHandler.END
    
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        users = json.load(f)
    
    keyboard = []
    for username, data in users.items():
        if not data.get('is_admin'):
            keyboard.append([InlineKeyboardButton(
                data['full_name'], 
                callback_data=f"edituser_{username}"
            )])
    
    keyboard.append([InlineKeyboardButton("❌ انصراف", callback_data="edituser_cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "✏️ *ویرایش غذای کاربران*\n\n"
        "کاربر مورد نظر را انتخاب کنید:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    return EDIT_USER_SELECT

async def edit_user_select_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتخاب کاربر برای ویرایش"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "edituser_cancel":
        await query.edit_message_text("❌ لغو شد.")
        return ConversationHandler.END
    
    username = query.data.split('_')[1]
    context.user_data['edit_username'] = username
    
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        users = json.load(f)
    full_name = users[username]['full_name']
    
    keyboard = [
        [InlineKeyboardButton("هفته 1", callback_data="edituser_week_1")],
        [InlineKeyboardButton("هفته 2", callback_data="edituser_week_2")],
        [InlineKeyboardButton("هفته 3", callback_data="edituser_week_3")],
        [InlineKeyboardButton("هفته 4", callback_data="edituser_week_4")],
        [InlineKeyboardButton("❌ انصراف", callback_data="edituser_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✏️ ویرایش غذای *{full_name}*\n\n"
        "کدام هفته را میخواهید ویرایش کنید؟",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    return EDIT_USER_WEEK

async def edit_user_select_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتخاب هفته برای ویرایش غذای کاربر"""
    query = update.callback_query
    await query.answer()
    
    week = query.data.split('_')[2]
    context.user_data['edit_week'] = week
    
    # Ensure username is set (for regular users editing their own meals)
    telegram_id = update.effective_user.id
    if telegram_id in user_sessions and 'edit_username' not in context.user_data:
        context.user_data['edit_username'] = user_sessions[telegram_id]['username']
    
    keyboard = [
        [InlineKeyboardButton("شنبه", callback_data="edituser_day_1")],
        [InlineKeyboardButton("یکشنبه", callback_data="edituser_day_2")],
        [InlineKeyboardButton("دوشنبه", callback_data="edituser_day_3")],
        [InlineKeyboardButton("سه‌شنبه", callback_data="edituser_day_4")],
        [InlineKeyboardButton("چهارشنبه", callback_data="edituser_day_5")],
        [InlineKeyboardButton("✅ اتمام", callback_data="edituser_done")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📅 هفته {week}\n\n"
        "کدام روز را میخواهید ویرایش کنید؟",
        reply_markup=reply_markup
    )
    return EDIT_USER_DAY

async def edit_user_select_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتخاب و ویرایش غذا/دسر روز خاص برای کاربر"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "edituser_done":
        await query.edit_message_text("✅ ویرایش تمام شد!")
        return ConversationHandler.END
    
    day = query.data.split('_')[2]
    week = context.user_data.get('edit_week')
    username = context.user_data.get('edit_username')
    
    # Safety check: Ensure username exists
    telegram_id = update.effective_user.id
    if not username and telegram_id in user_sessions:
        username = user_sessions[telegram_id]['username']
        context.user_data['edit_username'] = username
    
    if not username:
        await query.answer("❌ خطا: نام کاربری یافت نشد. لطفاً دوباره وارد شوید.", show_alert=True)
        return ConversationHandler.END
    
    if not week:
        await query.answer("❌ خطا: هفته انتخاب نشده است.", show_alert=True)
        return ConversationHandler.END
    
    context.user_data['edit_day'] = day
    
    # خواندن منوی این روز
    with open(MENU_FILE, 'r', encoding='utf-8') as f:
        menu_data = json.load(f)
    
    day_menu = menu_data[f'week_{week}'][f'day_{day}']
    
    if not day_menu['meals'] and not day_menu['desserts']:
        await query.answer("❌ منوی این روز تعریف نشده است!", show_alert=True)
        return EDIT_USER_DAY
    
    # خواندن انتخاب فعلی کاربر
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        users = json.load(f)
    full_name = users[username]['full_name']
    
    wb = openpyxl.load_workbook(EXCEL_FILE)
    ws = wb.active
    
    user_row = None
    for row in range(3, ws.max_row + 2):
        if ws.cell(row=row, column=1).value == full_name:
            user_row = row
            break
    
    if not user_row:
        await query.answer("❌ کاربر در اکسل یافت نشد!", show_alert=True)
        return EDIT_USER_DAY
    
    # محاسبه ستون
    day_idx = int(day) - 1
    week_idx = int(week) - 1
    col = 2 + (week_idx * 10) + (day_idx * 2)
    
    current_meal = ws.cell(row=user_row, column=col).value or "-"
    current_dessert = ws.cell(row=user_row, column=col+1).value or "-"
    
    days_name = {1: "شنبه", 2: "یکشنبه", 3: "دوشنبه", 4: "سه‌شنبه", 5: "چهارشنبه"}
    
    message = f"✏️ *ویرایش غذای {full_name}*\n"
    message += f"📅 هفته {week} - {days_name[int(day)]}\n\n"
    message += f"🍽️ غذای فعلی: {current_meal}\n"
    message += f"🍰 دسر فعلی: {current_dessert}\n\n"
    message += "غذا یا دسر جدید را انتخاب کنید:"
    
    keyboard = []
    
    # غذاها
    if day_menu['meals']:
        keyboard.append([InlineKeyboardButton("── 🍽️ غذاها ──", callback_data="ignore")])
        for meal in day_menu['meals']:
            keyboard.append([InlineKeyboardButton(
                f"{'✓ ' if meal == current_meal else ''}{meal}",
                callback_data=f"setmeal_{week}_{day}_{meal}"
            )])
    
    # دسرها
    if day_menu['desserts']:
        keyboard.append([InlineKeyboardButton("── 🍰 دسرها ──", callback_data="ignore")])
        for dessert in day_menu['desserts']:
            keyboard.append([InlineKeyboardButton(
                f"{'✓ ' if dessert == current_dessert else ''}{dessert}",
                callback_data=f"setdessert_{week}_{day}_{dessert}"
            )])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"edituser_week_{week}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    return EDIT_USER_DAY

async def set_user_meal_dessert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم غذا یا دسر کاربر"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "ignore":
        return EDIT_USER_DAY
    
    parts = query.data.split('_')
    item_type = parts[0]  # setmeal or setdessert
    week = parts[1]
    day = parts[2]
    item_value = '_'.join(parts[3:])
    
    username = context.user_data.get('edit_username')
    
    # Safety check: Ensure username exists
    telegram_id = update.effective_user.id
    if not username and telegram_id in user_sessions:
        username = user_sessions[telegram_id]['username']
        context.user_data['edit_username'] = username
    
    if not username:
        await query.answer("❌ خطا: نام کاربری یافت نشد. لطفاً دوباره وارد شوید.", show_alert=True)
        return ConversationHandler.END
    
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        users = json.load(f)
    full_name = users[username]['full_name']
    
    # باز کردن قفل و ویرایش
    wb, ws = unprotect_excel()
    if not wb or not ws:
        await query.answer("❌ خطا در باز کردن فایل!", show_alert=True)
        return EDIT_USER_DAY
    
    user_row = None
    for row in range(3, ws.max_row + 2):
        if ws.cell(row=row, column=1).value == full_name:
            user_row = row
            break
    
    day_idx = int(day) - 1
    week_idx = int(week) - 1
    col = 2 + (week_idx * 10) + (day_idx * 2)
    
    if item_type == "setmeal":
        ws.cell(row=user_row, column=col, value=item_value)
    else:  # setdessert
        ws.cell(row=user_row, column=col+1, value=item_value)
    
    wb.save(EXCEL_FILE)
    protect_excel()
    
    # ثبت در لاگ
    if telegram_id in user_sessions:
        if user_sessions[telegram_id]['is_admin']:
            admin_name = user_sessions[telegram_id]['full_name']
            log_change(f"{admin_name} (ویرایش برای {full_name})")
        else:
            log_change(full_name)
    else:
        log_change(full_name)
    
    await query.answer(f"✅ {'غذا' if item_type == 'setmeal' else 'دسر'} ذخیره شد!", show_alert=True)
    
    # بازگشت به همان روز
    context.user_data['edit_week'] = week
    query.data = f"edituser_day_{day}"
    await edit_user_select_day(update, context)
    return EDIT_USER_DAY

async def my_meals_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع انتخاب غذای خود کاربر"""
    telegram_id = update.effective_user.id
    if telegram_id not in user_sessions:
        await update.message.reply_text("⛔ لطفاً ابتدا وارد شوید!")
        return ConversationHandler.END
    
    # IMPORTANT: Set username for editing
    context.user_data['edit_username'] = user_sessions[telegram_id]['username']
    
    keyboard = [
        [InlineKeyboardButton("هفته 1", callback_data="edituser_week_1")],
        [InlineKeyboardButton("هفته 2", callback_data="edituser_week_2")],
        [InlineKeyboardButton("هفته 3", callback_data="edituser_week_3")],
        [InlineKeyboardButton("هفته 4", callback_data="edituser_week_4")],
        [InlineKeyboardButton("❌ انصراف", callback_data="edituser_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🍽️ *انتخاب غذاهای من*\n\n"
        "کدام هفته را میخواهید ویرایش کنید؟",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    return EDIT_USER_WEEK

async def change_password_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع تغییر رمز عبور"""
    telegram_id = update.effective_user.id
    if telegram_id not in user_sessions:
        await update.message.reply_text("⛔ لطفاً ابتدا وارد شوید!")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "🔑 *تغییر رمز عبور*\n\n"
        "رمز عبور فعلی خود را وارد کنید:",
        parse_mode='Markdown'
    )
    return CHANGE_PASSWORD_CURRENT

async def change_password_current(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بررسی رمز فعلی"""
    telegram_id = update.effective_user.id
    current_password = update.message.text
    
    await update.message.delete()
    
    username = user_sessions[telegram_id]['username']
    
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        users = json.load(f)
    
    if users[username]['password'] != hash_password(current_password):
        await update.message.reply_text("❌ رمز عبور فعلی اشتباه است. دوباره امتحان کنید:")
        return CHANGE_PASSWORD_CURRENT
    
    await update.message.reply_text("✅ رمز عبور جدید را وارد کنید (حداقل 4 کاراکتر):")
    return CHANGE_PASSWORD_NEW

async def change_password_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت رمز جدید"""
    new_password = update.message.text
    await update.message.delete()
    
    if len(new_password) < 4:
        await update.message.reply_text("❌ رمز عبور باید حداقل 4 کاراکتر باشد. دوباره وارد کنید:")
        return CHANGE_PASSWORD_NEW
    
    context.user_data['new_password'] = new_password
    await update.message.reply_text("🔁 رمز عبور جدید را دوباره وارد کنید:")
    return CHANGE_PASSWORD_CONFIRM

async def change_password_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأیید و ذخیره رمز جدید"""
    confirm_password = update.message.text
    await update.message.delete()
    
    if confirm_password != context.user_data['new_password']:
        await update.message.reply_text("❌ رمزهای عبور مطابقت ندارند. دوباره رمز جدید را وارد کنید:")
        return CHANGE_PASSWORD_NEW
    
    telegram_id = update.effective_user.id
    username = user_sessions[telegram_id]['username']
    
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        users = json.load(f)
    
    users[username]['password'] = hash_password(confirm_password)
    
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    
    await update.message.reply_text("✅ رمز عبور با موفقیت تغییر کرد!")
    
    context.user_data.clear()
    return ConversationHandler.END

async def view_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مشاهده گزارش تغییرات"""
    telegram_id = update.effective_user.id
    if telegram_id not in user_sessions or not user_sessions[telegram_id]['is_admin']:
        await update.message.reply_text("⛔ شما دسترسی ندارید!")
        return
    
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            log_content = f.read()
        
        # ارسال به صورت فایل اگر طولانی است
        if len(log_content) > 3000:
            with open(LOG_FILE, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename="change_log.txt",
                    caption="📋 گزارش تغییرات"
                )
        else:
            await update.message.reply_text(f"📋 *گزارش تغییرات:*\n\n```\n{log_content}\n```", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ فایل لاگ یافت نشد!")

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """خروج از سیستم"""
    telegram_id = update.effective_user.id
    if telegram_id in user_sessions:
        del user_sessions[telegram_id]
    
    await update.message.reply_text("👋 با موفقیت خارج شدید!")
    await start(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو عملیات"""
    await update.message.reply_text("❌ عملیات لغو شد.")
    context.user_data.clear()
    return ConversationHandler.END

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت پیام‌های متنی"""
    text = update.message.text
    
    if text == "🔐 ورود به سیستم":
        return await login_start(update, context)
    elif text == "👁️ مشاهده برنامه غذایی":
        return await view_schedule(update, context)
    elif text == "➕ افزودن کاربر":
        return await add_user_start(update, context)
    elif text == "👥 لیست کاربران":
        return await list_users(update, context)
    elif text == "🍽️ مدیریت منوی غذایی":
        return await manage_menu_start(update, context)
    elif text == "✏️ ویرایش غذای کاربران":
        return await edit_user_meals_start(update, context)
    elif text == "🍽️ انتخاب غذاهای من":
        return await my_meals_start(update, context)
    elif text == "📋 گزارش تغییرات":
        return await view_log(update, context)
    elif text == "🔑 تغییر رمز عبور":
        return await change_password_start(update, context)
    elif text == "🚪 خروج":
        return await logout(update, context)
    elif text.startswith(('غذا:', 'دسر:')):
        return await handle_menu_message(update, context)

def main():
    """راه‌اندازی ربات"""
    initialize_files()
    
    # توکن ربات را اینجا قرار دهید
    TOKEN = "YOUR_BOT_TOKEN_HERE"
    
    application = Application.builder().token(TOKEN).build()
    
    # Handler ورود
    login_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔐 ورود به سیستم$"), login_start)],
        states={
            LOGIN_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_username)],
            LOGIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_password)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Handler افزودن کاربر
    add_user_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ افزودن کاربر$"), add_user_start)],
        states={
            ADD_USER_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_username)],
            ADD_USER_FULLNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_fullname)],
            ADD_USER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_password)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Handler مدیریت منو
    menu_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🍽️ مدیریت منوی غذایی$"), manage_menu_start)],
        states={
            SELECT_WEEK: [CallbackQueryHandler(menu_select_week, pattern="^menu_week_")],
            SELECT_DAY: [
                CallbackQueryHandler(menu_select_day, pattern="^menu_day_"),
                CallbackQueryHandler(delete_menu_item, pattern="^delete_(meal|dessert)_"),
                CallbackQueryHandler(confirm_delete, pattern="^confirm_delete_"),
                CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^menu_done$"),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^menu_cancel$")
        ],
    )
    
    # Handler ویرایش غذای کاربران توسط ادمین
    edit_user_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^✏️ ویرایش غذای کاربران$"), edit_user_meals_start)],
        states={
            EDIT_USER_SELECT: [CallbackQueryHandler(edit_user_select_user, pattern="^edituser_")],
            EDIT_USER_WEEK: [CallbackQueryHandler(edit_user_select_week, pattern="^edituser_week_")],
            EDIT_USER_DAY: [
                CallbackQueryHandler(edit_user_select_day, pattern="^edituser_day_"),
                CallbackQueryHandler(set_user_meal_dessert, pattern="^(setmeal|setdessert)_"),
                CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^edituser_done$"),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^edituser_cancel$")
        ],
    )
    
    # Handler انتخاب غذای خودم
    my_meals_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🍽️ انتخاب غذاهای من$"), my_meals_start)],
        states={
            EDIT_USER_WEEK: [CallbackQueryHandler(edit_user_select_week, pattern="^edituser_week_")],
            EDIT_USER_DAY: [
                CallbackQueryHandler(edit_user_select_day, pattern="^edituser_day_"),
                CallbackQueryHandler(set_user_meal_dessert, pattern="^(setmeal|setdessert)_"),
                CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^edituser_done$"),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^edituser_cancel$")
        ],
    )
    
    # Handler تغییر رمز
    change_pass_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔑 تغییر رمز عبور$"), change_password_start)],
        states={
            CHANGE_PASSWORD_CURRENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_password_current)],
            CHANGE_PASSWORD_NEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_password_new)],
            CHANGE_PASSWORD_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_password_confirm)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # اضافه کردن handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(login_handler)
    application.add_handler(add_user_handler)
    application.add_handler(menu_handler)
    application.add_handler(edit_user_handler)
    application.add_handler(my_meals_handler)
    application.add_handler(change_pass_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.Regex("^(غذا:|دسر:)"), handle_menu_message))
    
    # شروع ربات
    print("🤖 ربات در حال اجرا است...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
