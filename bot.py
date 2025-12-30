import logging
import os
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# ==================== CONFIGURATION ====================
# Environment variable se token lo (Railway pe set karna hai)
BOT_TOKEN = os.environ.get('BOT_TOKEN', "8133268755:AAFzUs-OIjifWWV6N8hP4-VV2cya7QvOW3U")
ADMIN_CHAT_ID = 6254229187
CHANNEL_USERNAME = "@ReferEarnTesting"
CHANNEL_INVITE_LINK = "https://t.me/+Q5UF8V_NCxAzZDhl"

REFERRAL_BONUS = 2
MIN_WITHDRAWAL = 10
SPECIAL_BONUS_REFERRALS = 50
SPECIAL_BONUS_AMOUNT = 1000

# ==================== DATABASE SETUP ====================
conn = sqlite3.connect('/data/referral_bot.db', check_same_thread=False)  # Railway compatible
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    balance REAL DEFAULT 0,
    referrals INTEGER DEFAULT 0,
    is_verified INTEGER DEFAULT 0,
    referral_code TEXT UNIQUE,
    bonus_received INTEGER DEFAULT 0,
    join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    upi_id TEXT,
    amount REAL,
    status TEXT DEFAULT 'pending',
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (telegram_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inviter_id INTEGER,
    referred_id INTEGER,
    bonus_paid INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS bonuses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL,
    type TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (telegram_id)
)
''')
conn.commit()

# ==================== HELPER FUNCTIONS ====================
def generate_referral_code(user_id):
    import hashlib
    return hashlib.md5(f"REF_{user_id}_{datetime.now().timestamp()}".encode()).hexdigest()[:8]

def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
    user = cursor.fetchone()
    return user

def create_user(user_id, username):
    referral_code = generate_referral_code(user_id)
    cursor.execute('''
        INSERT OR IGNORE INTO users (telegram_id, username, referral_code) 
        VALUES (?, ?, ?)
    ''', (user_id, username, referral_code))
    conn.commit()
    return referral_code

def check_channel_membership(user_id, context):
    try:
        member = context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

def check_and_award_bonus(user_id):
    cursor.execute("SELECT referrals FROM users WHERE telegram_id = ?", (user_id,))
    user_data = cursor.fetchone()
    
    if user_data and user_data[0] >= SPECIAL_BONUS_REFERRALS:
        cursor.execute("SELECT bonus_received FROM users WHERE telegram_id = ?", (user_id,))
        bonus_received = cursor.fetchone()[0]
        
        if bonus_received == 0:
            cursor.execute("UPDATE users SET balance = balance + ?, bonus_received = 1 WHERE telegram_id = ?", 
                         (SPECIAL_BONUS_AMOUNT, user_id))
            cursor.execute("INSERT INTO bonuses (user_id, amount, type) VALUES (?, ?, '50_referrals')", 
                         (user_id, SPECIAL_BONUS_AMOUNT))
            conn.commit()
            return True
    return False

# ==================== BOT COMMANDS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or f"user_{user_id}"
    
    referral_code = create_user(user_id, username)
    
    if context.args:
        referrer_id = context.args[0]
        if referrer_id.isdigit():
            referrer_id = int(referrer_id)
            if referrer_id != user_id:
                cursor.execute("SELECT * FROM referrals WHERE referred_id = ?", (user_id,))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO referrals (inviter_id, referred_id) VALUES (?, ?)", 
                                 (referrer_id, user_id))
                    cursor.execute("UPDATE users SET referrals = referrals + 1, balance = balance + ? WHERE telegram_id = ?", 
                                 (REFERRAL_BONUS, referrer_id))
                    
                    bonus_awarded = check_and_award_bonus(referrer_id)
                    conn.commit()
                    
                    try:
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=f"🎉 **New Referral!**\n\n💰 **+₹{REFERRAL_BONUS} added!**\n📊 Total: {get_user(referrer_id)[3]}\n🎯 Target: {SPECIAL_BONUS_REFERRALS} for ₹{SPECIAL_BONUS_AMOUNT} bonus!"
                        )
                        
                        if bonus_awarded:
                            await context.bot.send_message(
                                chat_id=referrer_id,
                                text=f"🏆 **🎊 CONGRATULATIONS! 🎊**\n\n✅ **{SPECIAL_BONUS_REFERRALS} referrals completed!**\n💰 **₹{SPECIAL_BONUS_AMOUNT} BONUS added!**"
                            )
                    except:
                        pass
    
    is_member = check_channel_membership(user_id, context)
    
    if not is_member:
        keyboard = [
            [InlineKeyboardButton("✅ Join Channel", url=CHANNEL_INVITE_LINK)],
            [InlineKeyboardButton("🔁 I've Joined", callback_data="check_join")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🚀 **Welcome to Refer & Earn Bot!**\n\n💰 **Earn ₹{REFERRAL_BONUS} per referral**\n🏆 **Special: {SPECIAL_BONUS_REFERRALS} referrals = ₹{SPECIAL_BONUS_AMOUNT} BONUS!**\n\n📌 **Step 1:** Join channel\n📌 **Step 2:** Click 'I've Joined'\n⚠️ *Must join to use bot*",
            reply_markup=reply_markup
        )
        return
    
    cursor.execute("UPDATE users SET is_verified = 1 WHERE telegram_id = ?", (user_id,))
    conn.commit()
    
    user_data = get_user(user_id)
    referral_link = f"https://t.me/{(await context.bot.get_me()).username}?start={user_id}"
    referrals_count = user_data[3] if user_data else 0
    remaining = max(0, SPECIAL_BONUS_REFERRALS - referrals_count)
    
    await update.message.reply_text(
        f"🎉 **Welcome {username}!**\n\n💰 **Balance:** ₹{user_data[2] if user_data else 0:.2f}\n👥 **Referrals:** {referrals_count}\n🎁 **Per Referral:** ₹{REFERRAL_BONUS}\n\n🏆 **SPECIAL BONUS:**\n• {SPECIAL_BONUS_REFERRALS} referrals = ₹{SPECIAL_BONUS_AMOUNT} EXTRA!\n🎯 Remaining: {remaining} referrals\n\n📢 **Your Link:**\n`{referral_link}`\n\n📌 **Commands:**\n/balance - Check balance\n/withdraw - Withdraw money\n/referrals - See referrals\n/bonus - Bonus progress\n/help - Help"
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "check_join":
        user_id = query.from_user.id
        is_member = check_channel_membership(user_id, context)
        
        if is_member:
            cursor.execute("UPDATE users SET is_verified = 1 WHERE telegram_id = ?", (user_id,))
            conn.commit()
            
            user_data = get_user(user_id)
            referral_link = f"https://t.me/{(await context.bot.get_me()).username}?start={user_id}"
            referrals_count = user_data[3] if user_data else 0
            remaining = max(0, SPECIAL_BONUS_REFERRALS - referrals_count)
            
            await query.edit_message_text(
                f"✅ **Verified!**\n\n💰 **Balance:** ₹{user_data[2] if user_data else 0:.2f}\n👥 **Referrals:** {referrals_count}\n🎁 **Per Referral:** ₹{REFERRAL_BONUS}\n\n🏆 **Bonus:** {SPECIAL_BONUS_REFERRALS} refs = ₹{SPECIAL_BONUS_AMOUNT}\nRemaining: {remaining} refs\n\n📢 **Your Link:**\n`{referral_link}`"
            )
        else:
            await query.edit_message_text(
                f"❌ **Not joined yet!**\n\nJoin: {CHANNEL_INVITE_LINK}\nThen click 'I've Joined' again."
            )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    
    if not user_data or user_data[4] == 0:
        await update.message.reply_text(f"❌ **Verify first!**\nJoin: {CHANNEL_INVITE_LINK}\nThen /start")
        return
    
    referral_link = f"https://t.me/{(await context.bot.get_me()).username}?start={user_id}"
    referrals_count = user_data[3]
    remaining = max(0, SPECIAL_BONUS_REFERRALS - referrals_count)
    bonus_received = "✅ Yes" if user_data[6] == 1 else "❌ No"
    
    await update.message.reply_text(
        f"💰 **Balance:** ₹{user_data[2]:.2f}\n👥 **Referrals:** {referrals_count}\n🏆 **50 Ref Bonus:** {bonus_received}\n\n🎯 **BONUS:** {referrals_count}/{SPECIAL_BONUS_REFERRALS}\nRemaining: {remaining} refs\n\n📢 **Your Link:**\n`{referral_link}`"
    )

async def bonus_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    
    if not user_data or user_data[4] == 0:
        await update.message.reply_text("❌ Verify first!")
        return
    
    referrals_count = user_data[3]
    progress = min(100, (referrals_count / SPECIAL_BONUS_REFERRALS) * 100)
    remaining = max(0, SPECIAL_BONUS_REFERRALS - referrals_count)
    bars = int(progress / 10)
    progress_bar = "▓" * bars + "░" * (10 - bars)
    
    referral_link = f"https://t.me/{(await context.bot.get_me()).username}?start={user_id}"
    
    await update.message.reply_text(
        f"🏆 **BONUS PROGRESS**\n\n🎯 **Target:** {SPECIAL_BONUS_REFERRALS} = ₹{SPECIAL_BONUS_AMOUNT}\n\n📊 **Progress:**\n┌───────────────────────┐\n│ {progress_bar} │\n└───────────────────────┘\n📈 {referrals_count}/{SPECIAL_BONUS_REFERRALS} ({progress:.1f}%)\n\n📌 **Details:**\n• Done: {referrals_count}\n• Need: {remaining}\n• Per ref: ₹{REFERRAL_BONUS}\n\n📢 **Your Link:**\n`{referral_link}`"
    )

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    
    if not user_data or user_data[4] == 0:
        await update.message.reply_text(f"❌ **Verify first!**\nJoin: {CHANNEL_INVITE_LINK}")
        return
    
    balance_amount = user_data[2]
    if balance_amount < MIN_WITHDRAWAL:
        await update.message.reply_text(
            f"❌ **Min ₹{MIN_WITHDRAWAL}**\nYour: ₹{balance_amount:.2f}\n\n📢 Refer friends!\n• ₹{REFERRAL_BONUS}/referral\n• {SPECIAL_BONUS_REFERRALS} = ₹{SPECIAL_BONUS_AMOUNT} bonus!"
        )
        return
    
    await update.message.reply_text(
        f"💰 **Amount:** ₹{balance_amount:.2f}\n👥 **Referrals:** {user_data[3]}\n\n📱 **Enter UPI ID:**\n(Example: 1234567890@ybl)\n\n⚠️ *Correct UPI ID*"
    )
    
    context.user_data['waiting_for_upi'] = True

async def handle_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_upi'):
        upi_id = update.message.text.strip()
        user_id = update.effective_user.id
        user_data = get_user(user_id)
        
        if '@' not in upi_id or len(upi_id) < 5:
            await update.message.reply_text("❌ **Invalid UPI!**\nEnter valid UPI (e.g., 1234567890@ybl):")
            return
        
        amount = user_data[2]
        
        cursor.execute("UPDATE users SET balance = 0 WHERE telegram_id = ?", (user_id,))
        cursor.execute('INSERT INTO withdrawals (user_id, upi_id, amount, status) VALUES (?, ?, ?, "pending")', 
                     (user_id, upi_id, amount))
        conn.commit()
        
        cursor.execute("SELECT last_insert_rowid()")
        withdrawal_id = cursor.fetchone()[0]
        
        admin_message = (
            f"📥 **NEW WITHDRAWAL**\n\n"
            f"🆔 **ID:** `{withdrawal_id}`\n"
            f"👤 **User:** @{update.effective_user.username}\n"
            f"📱 **User ID:** `{user_id}`\n"
            f"💰 **Amount:** ₹{amount:.2f}\n"
            f"📧 **UPI:** `{upi_id}`\n"
            f"👥 **Referrals:** {user_data[3]}\n"
            f"🏆 **Bonus:** {'✅' if user_data[6] == 1 else '❌'}\n"
            f"🕒 **Time:** {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"✅ /approve_{withdrawal_id}\n"
            f"❌ /reject_{withdrawal_id}"
        )
        
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_message)
        
        await update.message.reply_text(
            f"✅ **Submitted!**\n\n💰 **Amount:** ₹{amount:.2f}\n📱 **UPI:** {upi_id}\n🆔 **ID:** {withdrawal_id}\n\n⏳ *24 hours processing*"
        )
        
        context.user_data['waiting_for_upi'] = False

async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    
    command = update.message.text
    if '_' in command:
        try:
            withdrawal_id = int(command.split('_')[1])
            
            cursor.execute('''
                SELECT w.*, u.telegram_id, u.username 
                FROM withdrawals w
                JOIN users u ON w.user_id = u.telegram_id
                WHERE w.id = ? AND w.status = 'pending'
            ''', (withdrawal_id,))
            withdrawal = cursor.fetchone()
            
            if not withdrawal:
                await update.message.reply_text(f"❌ WD#{withdrawal_id} not found!")
                return
            
            cursor.execute("UPDATE withdrawals SET status = 'approved' WHERE id = ?", (withdrawal_id,))
            conn.commit()
            
            try:
                await context.bot.send_message(
                    chat_id=withdrawal[1],
                    text=f"✅ **Approved!**\n\n💰 ₹{withdrawal[3]:.2f}\n📱 {withdrawal[2]}\n🆔 WD{withdrawal_id}\n\n*Money sent to UPI*"
                )
            except:
                pass
            
            await update.message.reply_text(f"✅ WD#{withdrawal_id} approved!\n@{withdrawal[6]}\n₹{withdrawal[3]}\n{withdrawal[2]}")
            
        except ValueError:
            await update.message.reply_text("❌ Invalid format!")

async def admin_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    
    command = update.message.text
    if '_' in command:
        try:
            withdrawal_id = int(command.split('_')[1])
            
            cursor.execute("SELECT * FROM withdrawals WHERE id = ? AND status = 'pending'", (withdrawal_id,))
            withdrawal = cursor.fetchone()
            
            if not withdrawal:
                await update.message.reply_text(f"❌ WD#{withdrawal_id} not found!")
                return
            
            cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", 
                         (withdrawal[3], withdrawal[1]))
            cursor.execute("UPDATE withdrawals SET status = 'rejected' WHERE id = ?", (withdrawal_id,))
            conn.commit()
            
            try:
                await context.bot.send_message(
                    chat_id=withdrawal[1],
                    text=f"❌ **Rejected!**\n\n💰 ₹{withdrawal[3]:.2f}\n📱 {withdrawal[2]}\n🆔 {withdrawal_id}\n\n*Balance returned*"
                )
            except:
                pass
            
            await update.message.reply_text(f"❌ WD#{withdrawal_id} rejected! Balance returned.")
            
        except ValueError:
            await update.message.reply_text("❌ Invalid format!")

async def referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    
    if not user_data or user_data[4] == 0:
        await update.message.reply_text("❌ Verify first!")
        return
    
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE inviter_id = ?", (user_id,))
    referral_count = cursor.fetchone()[0]
    
    remaining = max(0, SPECIAL_BONUS_REFERRALS - referral_count)
    referral_link = f"https://t.me/{(await context.bot.get_me()).username}?start={user_id}"
    
    await update.message.reply_text(
        f"👥 **Referrals:** {referral_count}\n💰 **Earned:** ₹{referral_count * REFERRAL_BONUS}\n🏆 **Bonus:** {'✅' if user_data[6] == 1 else '❌'}\n\n🎯 **BONUS:** {SPECIAL_BONUS_REFERRALS} refs = ₹{SPECIAL_BONUS_AMOUNT}\nRemaining: {remaining} refs\n\n📢 **Your Link:**\n`{referral_link}`"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 **Bot Help**\n\n"
        "1. **/start** - Start & get link\n"
        "2. **/balance** - Check balance\n"
        "3. **/bonus** - Bonus progress\n"
        "4. **/withdraw** - Withdraw (Min ₹10)\n"
        "5. **/referrals** - Check referrals\n\n"
        f"💰 **Earning:** ₹{REFERRAL_BONUS}/referral\n"
        f"🏆 **Bonus:** {SPECIAL_BONUS_REFERRALS} refs = ₹{SPECIAL_BONUS_AMOUNT}\n"
        f"📌 **Payment:** UPI within 24h\n\n"
        "❓ **Contact admin**"
    )

# ==================== MAIN FUNCTION ====================
def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    print("🚀 Starting Referral Bot...")
    print(f"🤖 Bot Token: {BOT_TOKEN[:10]}...")
    print(f"👑 Admin ID: {ADMIN_CHAT_ID}")
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("bonus", bonus_command))
    application.add_handler(CommandHandler("withdraw", withdraw))
    application.add_handler(CommandHandler("referrals", referrals))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("approve", admin_approve))
    application.add_handler(CommandHandler("reject", admin_reject))
    
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_upi))
    
    print("✅ Bot started successfully!")
    application.run_polling(allowed_updates=Update.ALL_UPDATES)

if __name__ == '__main__':
    main()
