import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from database import Session, User, TelegramAccount, Report, Transaction
from account_manager import AccountManager
from reporter import Reporter
from config import BOT_TOKEN, OWNER_ID, REPORT_CATEGORIES, REPORT_TEMPLATES, DEFAULT_TOKENS, REPORT_COST
import asyncio
from datetime import datetime, timezone  # Fixed: Added timezone import
from sqlalchemy import text

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize components
session = Session()
account_manager = AccountManager()
reporter = Reporter()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    
    try:
        # Check if user exists with proper error handling
        db_user = session.query(User).filter_by(user_id=user.id).first()
        
        if not db_user:
            role = 'owner' if user.id == OWNER_ID else 'user'
            db_user = User(
                user_id=user.id,
                username=user.username,
                tokens=999999 if role == 'owner' else DEFAULT_TOKENS,
                role=role
            )
            session.add(db_user)
            session.commit()
            logger.info(f"New user registered: {user.id} - {user.username} - Role: {role}")
        
        # Update last active - Fixed deprecated utcnow()
        db_user.last_active = datetime.now(timezone.utc)
        session.commit()
        
    except Exception as e:
        logger.error(f"Database error in start: {e}")
        session.rollback()
        await update.message.reply_text("❌ Database error. Please try again later.")
        return
    
    # Create main menu
    keyboard = [
        [InlineKeyboardButton("📊 My Stats", callback_data='stats')],
        [InlineKeyboardButton("📝 Report", callback_data='report_menu')],
        [InlineKeyboardButton("💰 Buy Tokens", callback_data='buy_tokens')],
        [InlineKeyboardButton("👥 My Reports", callback_data='my_reports')],
        [InlineKeyboardButton("📱 Add Account", callback_data='add_account')]
    ]
    
    if db_user.role in ['owner', 'admin']:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data='admin_panel')])
    if db_user.role == 'owner':
        keyboard.append([InlineKeyboardButton("👑 Owner Panel", callback_data='owner_panel')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = f"""
🌟 **Welcome {user.first_name}!** 🌟

━━━━━━━━━━━━━━━━━━━━━
📋 **Your Information**
━━━━━━━━━━━━━━━━━━━━━
🆔 ID: `{user.id}`
💰 Tokens: `{db_user.tokens}`
👤 Role: `{db_user.role}`
📊 Reports Made: `{db_user.reports_made}`
━━━━━━━━━━━━━━━━━━━━━

Select an option below:
"""
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    try:
        db_user = session.query(User).filter_by(user_id=user_id).first()
        
        if not db_user:
            await query.edit_message_text("❌ User not found. Please use /start to register.")
            return
        
        # Update last active - Fixed deprecated utcnow()
        db_user.last_active = datetime.now(timezone.utc)
        session.commit()
        
    except Exception as e:
        logger.error(f"Database error in button_handler: {e}")
        session.rollback()
        await query.edit_message_text("❌ Database error. Please try again.")
        return
    
    if query.data == 'stats':
        # Format dates properly
        joined_date = db_user.joined_date.strftime('%Y-%m-%d') if db_user.joined_date else 'N/A'
        last_active = db_user.last_active.strftime('%Y-%m-%d %H:%M') if db_user.last_active else 'N/A'
        
        stats_text = f"""
📊 **Your Statistics**

━━━━━━━━━━━━━━━━━━━━━
🆔 User ID: `{db_user.user_id}`
👤 Username: @{db_user.username or 'N/A'}
💰 Tokens: `{db_user.tokens}`
👑 Role: `{db_user.role}`
📊 Reports Made: `{db_user.reports_made}`
📅 Joined: `{joined_date}`
⏰ Last Active: `{last_active}`
━━━━━━━━━━━━━━━━━━━━━
"""
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    elif query.data == 'report_menu':
        # Show report categories
        keyboard = []
        for key, value in REPORT_CATEGORIES.items():
            keyboard.append([InlineKeyboardButton(value, callback_data=f'report_cat_{key}')])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='back_to_main')])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📝 **Select Report Category**\n\nChoose the type of violation:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    elif query.data.startswith('report_cat_'):
        category = query.data.replace('report_cat_', '')
        context.user_data['report_category'] = category
        context.user_data['report_template'] = REPORT_TEMPLATES.get(category, "")
        
        keyboard = [
            [InlineKeyboardButton("📝 Use Template", callback_data='use_template')],
            [InlineKeyboardButton("✏️ Custom Text", callback_data='custom_text')],
            [InlineKeyboardButton("🔙 Back", callback_data='report_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📋 **Category:** {REPORT_CATEGORIES[category]}\n\n"
            f"**Template:**\n`{REPORT_TEMPLATES[category]}`\n\n"
            "Choose an option:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    elif query.data == 'use_template':
        context.user_data['report_text'] = context.user_data['report_template']
        await query.edit_message_text(
            "📝 **Send Target Information**\n\n"
            "Please send me the username(s) or ID(s) of the target(s) to report.\n"
            "You can send multiple by separating with commas or new lines.\n\n"
            "**Examples:**\n"
            "• `@spam_channel`\n"
            "• `-1001234567890`\n"
            "• `@user1, @user2, @user3`"
        )
        context.user_data['awaiting_target'] = True
        
    elif query.data == 'custom_text':
        await query.edit_message_text(
            "✏️ **Send Custom Report Text**\n\n"
            "Please write your custom report message.\n"
            "Be detailed and specific about the violation:"
        )
        context.user_data['awaiting_custom_text'] = True
        
    elif query.data == 'buy_tokens':
        keyboard = [
            [InlineKeyboardButton("🔟 10 Tokens - $1", callback_data='buy_10')],
            [InlineKeyboardButton("5️⃣0️⃣ 50 Tokens - $4", callback_data='buy_50')],
            [InlineKeyboardButton("1️⃣0️⃣0️⃣ 100 Tokens - $7", callback_data='buy_100')],
            [InlineKeyboardButton("5️⃣0️⃣0️⃣ 500 Tokens - $30", callback_data='buy_500')],
            [InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"💰 **Buy Tokens**\n\n"
            f"Your current tokens: `{db_user.tokens}`\n\n"
            "Select a package:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    elif query.data.startswith('buy_'):
        amount = int(query.data.replace('buy_', ''))
        # Here you would integrate with payment gateway
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"💳 **Purchase {amount} Tokens**\n\n"
            f"To purchase {amount} tokens, please contact @admin\n\n"
            "Payment integration coming soon!\n\n"
            "For now, tokens can be added by admins only.",
            reply_markup=reply_markup
        )
        
    elif query.data == 'my_reports':
        try:
            reports = session.query(Report).filter_by(reported_by=user_id).order_by(Report.created_at.desc()).limit(10).all()
            
            if not reports:
                keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("📭 You haven't made any reports yet.", reply_markup=reply_markup)
                return
            
            text = "📋 **Your Recent Reports:**\n\n"
            for report in reports:
                status_emoji = "✅" if report.status == 'completed' else "⏳" if report.status == 'pending' else "❌"
                created_date = report.created_at.strftime('%Y-%m-%d %H:%M') if report.created_at else 'N/A'
                text += f"{status_emoji} **ID:** `{report.id}`\n"
                text += f"   **Target:** `{report.target_username or report.target_id}`\n"
                text += f"   **Category:** {report.category}\n"
                text += f"   **Status:** {report.status}\n"
                text += f"   **Date:** {created_date}\n"
                text += "━━━━━━━━━━━━━━━━━━━━━\n"
            
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error fetching reports: {e}")
            session.rollback()
            await query.edit_message_text("❌ Error fetching reports. Please try again.")
        
    elif query.data == 'add_account':
        await query.edit_message_text(
            "📱 **Add Telegram Account**\n\n"
            "Please send me your phone number in international format:\n\n"
            "**Example:** `+1234567890`\n\n"
            "⚠️ This account will be used for reporting content."
        )
        context.user_data['awaiting_phone'] = True
        
    elif query.data == 'resend_code':
        # Handle code resend
        phone = context.user_data.get('phone')
        if phone:
            await query.edit_message_text("🔄 **Cleaning up and resending verification code...**\nThis may take a few seconds...")
            
            # Cancel any existing login attempt
            await account_manager.cancel_login(phone)
            
            # Small delay to ensure cleanup
            await asyncio.sleep(2)
            
            result = await account_manager.resend_code(phone)
            if result['status'] == 'code_sent':
                context.user_data['awaiting_code'] = True
                await query.edit_message_text(
                    "📱 **New Verification Code Sent!**\n\n"
                    "Please enter the new 5-digit code:\n"
                    "**Example:** `12345`\n\n"
                    "⏰ **Note:** Code expires in 2 minutes.\n\n"
                    "⚠️ **Important:** Make sure to use this new code immediately."
                )
            elif result['status'] == 'flood_wait':
                wait_time = result.get('wait_time', 60)
                keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    f"⏳ **Too Many Attempts**\n\n"
                    f"Please wait {wait_time} seconds before trying again.",
                    reply_markup=reply_markup
                )
            else:
                keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    f"❌ **Error:** {result.get('error', 'Failed to resend code')}\n\n"
                    "Please try again with /start",
                    reply_markup=reply_markup
                )
        else:
            await query.edit_message_text("❌ Session expired. Please start over with /start")
            context.user_data.clear()
        
    elif query.data == 'admin_panel':
        if db_user.role not in ['owner', 'admin']:
            await query.edit_message_text("⛔ **Access Denied!**\n\nYou don't have permission to access this panel.")
            return
        
        try:
            total_users = session.query(User).count()
            total_accounts = session.query(TelegramAccount).count()
            active_accounts = session.query(TelegramAccount).filter_by(is_active=True).count()
            pending_reports = session.query(Report).filter_by(status='pending').count()
            
            keyboard = [
                [InlineKeyboardButton("👥 Users", callback_data='admin_users')],
                [InlineKeyboardButton("📱 Accounts", callback_data='admin_accounts')],
                [InlineKeyboardButton("📊 Reports", callback_data='admin_reports')],
                [InlineKeyboardButton("💰 Give Tokens", callback_data='admin_give_tokens')],
                [InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            text = f"""
⚙️ **Admin Panel**

━━━━━━━━━━━━━━━━━━━━━
📊 **Statistics**
━━━━━━━━━━━━━━━━━━━━━
👥 Total Users: `{total_users}`
📱 Total Accounts: `{total_accounts}`
✅ Active Accounts: `{active_accounts}`
⏳ Pending Reports: `{pending_reports}`
━━━━━━━━━━━━━━━━━━━━━
"""
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in admin_panel: {e}")
            session.rollback()
            await query.edit_message_text("❌ Error loading admin panel. Please try again.")
    
    # ADMIN PANEL SUBMENUS
    elif query.data == 'admin_users':
        if db_user.role not in ['owner', 'admin']:
            await query.edit_message_text("⛔ Access Denied!")
            return
        
        try:
            users = session.query(User).order_by(User.joined_date.desc()).limit(10).all()
            text = "👥 **Recent Users:**\n\n"
            for user in users:
                text += f"🆔 `{user.user_id}` | @{user.username or 'N/A'} | {user.role} | {user.tokens} tokens\n"
            
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='admin_panel')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in admin_users: {e}")
            session.rollback()
            await query.edit_message_text("❌ Error loading users. Please try again.")
    
    elif query.data == 'admin_accounts':
        if db_user.role not in ['owner', 'admin']:
            await query.edit_message_text("⛔ Access Denied!")
            return
        
        try:
            accounts = session.query(TelegramAccount).limit(10).all()
            text = "📱 **Telegram Accounts:**\n\n"
            for acc in accounts:
                status_emoji = "✅" if acc.is_active else "❌"
                text += f"{status_emoji} `{acc.phone_number}` | Reports: {acc.reports_count} | Status: {acc.status}\n"
            
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='admin_panel')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in admin_accounts: {e}")
            session.rollback()
            await query.edit_message_text("❌ Error loading accounts. Please try again.")
    
    elif query.data == 'admin_reports':
        if db_user.role not in ['owner', 'admin']:
            await query.edit_message_text("⛔ Access Denied!")
            return
        
        try:
            reports = session.query(Report).order_by(Report.created_at.desc()).limit(10).all()
            text = "📊 **Recent Reports:**\n\n"
            for report in reports:
                status_emoji = "✅" if report.status == 'completed' else "⏳" if report.status == 'pending' else "❌"
                text += f"{status_emoji} ID: `{report.id}` | Target: {report.target_username or report.target_id} | Status: {report.status}\n"
            
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='admin_panel')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in admin_reports: {e}")
            session.rollback()
            await query.edit_message_text("❌ Error loading reports. Please try again.")
    
    elif query.data == 'admin_give_tokens':
        if db_user.role not in ['owner', 'admin']:
            await query.edit_message_text("⛔ Access Denied!")
            return
        
        await query.edit_message_text(
            "💰 **Give Tokens to User**\n\n"
            "Please send the user ID and amount in this format:\n"
            "`USER_ID AMOUNT`\n\n"
            "Example: `123456789 50`"
        )
        context.user_data['awaiting_token_gift'] = True
    
    # OWNER PANEL
    elif query.data == 'owner_panel':
        if db_user.role != 'owner':
            await query.edit_message_text("⛔ **Access Denied!**\n\nThis panel is for owner only.")
            return
        
        keyboard = [
            [InlineKeyboardButton("💰 Add Tokens", callback_data='owner_add_tokens')],
            [InlineKeyboardButton("👑 Add Admin", callback_data='owner_add_admin')],
            [InlineKeyboardButton("📊 System Stats", callback_data='owner_stats')],
            [InlineKeyboardButton("⚙️ Settings", callback_data='owner_settings')],
            [InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text("👑 **Owner Panel**", reply_markup=reply_markup, parse_mode='Markdown')
    
    # OWNER PANEL SUBMENUS
    elif query.data == 'owner_add_tokens':
        if db_user.role != 'owner':
            await query.edit_message_text("⛔ Access Denied!")
            return
        
        await query.edit_message_text(
            "💰 **Add Tokens to User**\n\n"
            "Please send the user ID and amount in this format:\n"
            "`USER_ID AMOUNT`\n\n"
            "Example: `123456789 1000`"
        )
        context.user_data['awaiting_owner_token_add'] = True
    
    elif query.data == 'owner_add_admin':
        if db_user.role != 'owner':
            await query.edit_message_text("⛔ Access Denied!")
            return
        
        await query.edit_message_text(
            "👑 **Add Admin**\n\n"
            "Please send the user ID to make admin:\n"
            "Example: `123456789`"
        )
        context.user_data['awaiting_admin_add'] = True
    
    elif query.data == 'owner_stats':
        if db_user.role != 'owner':
            await query.edit_message_text("⛔ Access Denied!")
            return
        
        try:
            total_users = session.query(User).count()
            total_accounts = session.query(TelegramAccount).count()
            total_reports = session.query(Report).count()
            pending_reports = session.query(Report).filter_by(status='pending').count()
            completed_reports = session.query(Report).filter_by(status='completed').count()
            
            # Get account stats
            account_stats = await account_manager.get_account_stats()
            
            text = f"""
📊 **System Statistics**

━━━━━━━━━━━━━━━━━━━━━
👥 **Users:** `{total_users}`
📱 **Accounts:** `{total_accounts}`
   ├─ Active: `{account_stats['active']}`
   ├─ Available: `{account_stats['available']}`
   └─ Banned: `{account_stats['banned']}`

📋 **Reports:** `{total_reports}`
   ├─ Pending: `{pending_reports}`
   └─ Completed: `{completed_reports}`
━━━━━━━━━━━━━━━━━━━━━
"""
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='owner_panel')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in owner_stats: {e}")
            session.rollback()
            await query.edit_message_text("❌ Error loading statistics. Please try again.")
    
    elif query.data == 'owner_settings':
        if db_user.role != 'owner':
            await query.edit_message_text("⛔ Access Denied!")
            return
        
        text = f"""
⚙️ **Bot Settings**

━━━━━━━━━━━━━━━━━━━━━
💰 Default Tokens: `{DEFAULT_TOKENS}`
💳 Report Cost: `{REPORT_COST}` token
👑 Owner ID: `{OWNER_ID}`
━━━━━━━━━━━━━━━━━━━━━

Settings can be changed in config.py
"""
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='owner_panel')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    # REPORT CONFIRMATION
    elif query.data == 'confirm_report':
        # Execute reports
        targets = context.user_data.get('targets', [])
        category = context.user_data.get('report_category')
        report_text = context.user_data.get('report_text')
        
        if not targets or not category or not report_text:
            await query.edit_message_text("❌ Missing report information. Please start over.")
            context.user_data.clear()
            return
        
        await query.edit_message_text("🔄 **Processing reports...**\nThis may take a few minutes.")
        
        result = await reporter.bulk_report(targets, category, report_text, user_id)
        
        if result['status'] == 'success':
            success_count = len(result['report_ids'])
            keyboard = [[InlineKeyboardButton("🔙 Back to Main", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"✅ **Successfully submitted {success_count} reports!**\n\n"
                f"**Report IDs:**\n`{', '.join(map(str, result['report_ids']))}`",
                reply_markup=reply_markup
            )
            
            # Update user's report count
            try:
                db_user.reports_made += success_count
                session.commit()
            except Exception as e:
                logger.error(f"Error updating report count: {e}")
                session.rollback()
        else:
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"❌ **Error:** {result['message']}",
                reply_markup=reply_markup
            )
        
        context.user_data.clear()
    
    # BACK TO MAIN
    elif query.data == 'back_to_main':
        # Clear user data to avoid confusion
        context.user_data.clear()
        
        # Get fresh user data
        try:
            db_user = session.query(User).filter_by(user_id=user_id).first()
            if not db_user:
                await query.edit_message_text("❌ User not found. Please use /start to register.")
                return
            
            # Create main menu
            keyboard = [
                [InlineKeyboardButton("📊 My Stats", callback_data='stats')],
                [InlineKeyboardButton("📝 Report", callback_data='report_menu')],
                [InlineKeyboardButton("💰 Buy Tokens", callback_data='buy_tokens')],
                [InlineKeyboardButton("👥 My Reports", callback_data='my_reports')],
                [InlineKeyboardButton("📱 Add Account", callback_data='add_account')]
            ]
            
            if db_user.role in ['owner', 'admin']:
                keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data='admin_panel')])
            if db_user.role == 'owner':
                keyboard.append([InlineKeyboardButton("👑 Owner Panel", callback_data='owner_panel')])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"🌟 **Welcome back!** 🌟\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 **Tokens:** `{db_user.tokens}`\n"
                f"👤 **Role:** `{db_user.role}`\n"
                f"📊 **Reports:** `{db_user.reports_made}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Select an option below:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error in back_to_main: {e}")
            session.rollback()
            await query.edit_message_text("❌ Error loading main menu. Please use /start")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Handle token gifting from admin
    if context.user_data.get('awaiting_token_gift'):
        try:
            parts = text.split()
            if len(parts) != 2:
                await update.message.reply_text("❌ Invalid format! Use: `USER_ID AMOUNT`")
                return
            
            target_user_id = int(parts[0])
            amount = int(parts[1])
            
            target_user = session.query(User).filter_by(user_id=target_user_id).first()
            if not target_user:
                await update.message.reply_text("❌ User not found!")
                return
            
            target_user.tokens += amount
            session.commit()
            
            await update.message.reply_text(
                f"✅ Added {amount} tokens to user {target_user_id}\n"
                f"New balance: {target_user.tokens} tokens"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Invalid amount! Please enter a number.")
        except Exception as e:
            logger.error(f"Error in token gift: {e}")
            session.rollback()
            await update.message.reply_text(f"❌ Error: {str(e)}")
        
        context.user_data.clear()
        return
    
    # Handle owner adding tokens
    elif context.user_data.get('awaiting_owner_token_add'):
        try:
            parts = text.split()
            if len(parts) != 2:
                await update.message.reply_text("❌ Invalid format! Use: `USER_ID AMOUNT`")
                return
            
            target_user_id = int(parts[0])
            amount = int(parts[1])
            
            target_user = session.query(User).filter_by(user_id=target_user_id).first()
            if not target_user:
                # Create user if doesn't exist
                target_user = User(
                    user_id=target_user_id,
                    username=f"user_{target_user_id}",
                    tokens=amount,
                    role='user'
                )
                session.add(target_user)
                await update.message.reply_text(f"✅ Created new user and added {amount} tokens")
            else:
                target_user.tokens += amount
                await update.message.reply_text(
                    f"✅ Added {amount} tokens to user {target_user_id}\n"
                    f"New balance: {target_user.tokens} tokens"
                )
            
            session.commit()
            
        except ValueError:
            await update.message.reply_text("❌ Invalid amount! Please enter a number.")
        except Exception as e:
            logger.error(f"Error in owner token add: {e}")
            session.rollback()
            await update.message.reply_text(f"❌ Error: {str(e)}")
        
        context.user_data.clear()
        return
    
    # Handle owner adding admin
    elif context.user_data.get('awaiting_admin_add'):
        try:
            target_user_id = int(text.strip())
            
            target_user = session.query(User).filter_by(user_id=target_user_id).first()
            if not target_user:
                await update.message.reply_text("❌ User not found!")
                return
            
            target_user.role = 'admin'
            session.commit()
            
            await update.message.reply_text(
                f"✅ User {target_user_id} is now an admin!"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID! Please enter a number.")
        except Exception as e:
            logger.error(f"Error in admin add: {e}")
            session.rollback()
            await update.message.reply_text(f"❌ Error: {str(e)}")
        
        context.user_data.clear()
        return
    
    # Handle phone number for account addition
    if context.user_data.get('awaiting_phone'):
        phone = text.strip()
        
        # Validate phone number format
        if not phone.startswith('+'):
            await update.message.reply_text(
                "❌ **Invalid Phone Number**\n\n"
                "Phone number must be in international format starting with +\n"
                "**Example:** `+1234567890`"
            )
            return
            
        context.user_data['phone'] = phone
        context.user_data['awaiting_phone'] = False
        context.user_data['awaiting_code'] = True
        
        await update.message.chat.send_action(action='typing')
        
        result = await account_manager.add_account(phone)
        
        if result['status'] == 'code_sent':
            await update.message.reply_text(
                "📱 **Verification Code Sent!**\n\n"
                "Please enter the 5-digit code you received:\n"
                "**Example:** `12345`\n\n"
                "⏰ **Note:** Code expires in 2 minutes."
            )
        elif result['status'] == 'flood_wait':
            wait_time = result.get('wait_time', 60)
            await update.message.reply_text(
                f"⏳ **Too Many Attempts**\n\n"
                f"Please wait {wait_time} seconds before trying again.\n"
                f"Your phone number: `{phone}`"
            )
            context.user_data.clear()
        else:
            await update.message.reply_text(
                f"❌ **Error:** {result.get('error', 'Unknown error')}\n\n"
                "Please check your phone number and try again."
            )
            context.user_data.clear()
    
    # Handle verification code
    elif context.user_data.get('awaiting_code'):
        code = text.strip()
        phone = context.user_data.get('phone')
        
        # Validate code format (should be digits)
        if not code.isdigit() or len(code) != 5:
            await update.message.reply_text(
                "❌ **Invalid Code**\n\n"
                "Please enter a valid 5-digit verification code.\n"
                "**Example:** `12345`"
            )
            return
        
        await update.message.chat.send_action(action='typing')
        
        result = await account_manager.add_account(
            phone, 
            verification_code=code
        )
        
        if result['status'] == 'password_needed':
            context.user_data['awaiting_password'] = True
            await update.message.reply_text(
                "🔐 **Two-Step Verification Enabled**\n\n"
                "Please enter your account password:"
            )
        elif result['status'] == 'code_expired':
            # Code expired - offer to resend
            keyboard = [
                [InlineKeyboardButton("🔄 Resend Code", callback_data='resend_code')],
                [InlineKeyboardButton("❌ Cancel", callback_data='back_to_main')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "⏰ **Verification Code Expired**\n\n"
                "The code you entered has expired. Codes are valid for 2 minutes only.\n\n"
                "Would you like a new code?",
                reply_markup=reply_markup
            )
        elif result['status'] == 'code_invalid':
            await update.message.reply_text(
                "❌ **Invalid Code**\n\n"
                "The code you entered is incorrect. Please try again:"
            )
        elif result['status'] == 'flood_wait':
            wait_time = result.get('wait_time', 60)
            await update.message.reply_text(
                f"⏳ **Too Many Attempts**\n\n"
                f"Please wait {wait_time} seconds before trying again."
            )
        elif result['status'] == 'success':
            await update.message.reply_text(
                "✅ **Account Added Successfully!**\n\n"
                "You can now use this account for reporting."
            )
            context.user_data.clear()
        else:
            await update.message.reply_text(
                f"❌ **Error:** {result.get('error', 'Unknown error')}\n\n"
                "Please try again with /start"
            )
            context.user_data.clear()
    
    # Handle 2FA password
    elif context.user_data.get('awaiting_password'):
        password = text
        phone = context.user_data.get('phone')
        
        await update.message.chat.send_action(action='typing')
        
        result = await account_manager.add_account(
            phone, 
            password=password
        )
        
        if result['status'] == 'success':
            await update.message.reply_text(
                "✅ **Account Added Successfully!**\n\n"
                "You can now use this account for reporting."
            )
            context.user_data.clear()
        elif result['status'] == 'password_error':
            # Keep the session alive for retry
            await update.message.reply_text(
                "❌ **Incorrect Password**\n\n"
                "The password you entered is incorrect. Please try again:"
            )
            # Don't clear context - stay in password mode
        elif result['status'] == 'flood_wait':
            wait_time = result.get('wait_time', 60)
            await update.message.reply_text(
                f"⏳ **Too Many Attempts**\n\n"
                f"Please wait {wait_time} seconds before trying again."
            )
            context.user_data.clear()
        else:
            await update.message.reply_text(
                f"❌ **Error:** {result.get('error', 'Unknown error')}\n\n"
                "Please try again with /start"
            )
            context.user_data.clear()
    
    # Handle custom report text
    elif context.user_data.get('awaiting_custom_text'):
        context.user_data['report_text'] = text
        context.user_data['awaiting_custom_text'] = False
        context.user_data['awaiting_target'] = True
        await update.message.reply_text(
            "📝 **Send Target Information**\n\n"
            "Please send me the username(s) or ID(s) of the target(s) to report.\n"
            "You can send multiple by separating with commas or new lines.\n\n"
            "**Examples:**\n"
            "• `@spam_channel`\n"
            "• `-1001234567890`\n"
            "• `@user1, @user2, @user3`"
        )
    
    # Handle target(s) for reporting
    elif context.user_data.get('awaiting_target'):
        targets = []
        lines = text.split('\n')
        for line in lines:
            items = line.split(',')
            for item in items:
                target = item.strip()
                if target:
                    # Determine target type
                    if target.startswith('@'):
                        target_type = 'channel'
                    elif target.startswith('-100'):
                        target_type = 'channel'
                    elif target.isdigit():
                        target_type = 'user'
                    else:
                        target_type = 'user'
                    
                    targets.append({
                        'type': target_type,
                        'username': target if target.startswith('@') else None,
                        'id': target if not target.startswith('@') else None
                    })
        
        if not targets:
            await update.message.reply_text("❌ No valid targets found! Please try again.")
            return
        
        # Check tokens
        try:
            db_user = session.query(User).filter_by(user_id=user_id).first()
            if not db_user:
                await update.message.reply_text("❌ User not found. Please use /start to register.")
                return
            
            required_tokens = len(targets) * REPORT_COST
            if db_user.role != 'owner' and db_user.tokens < required_tokens:
                await update.message.reply_text(
                    f"❌ **Insufficient Tokens!**\n\n"
                    f"Required: `{required_tokens}` tokens\n"
                    f"Your balance: `{db_user.tokens}` tokens\n\n"
                    f"Please purchase more tokens from the menu."
                )
                return
            
            # Send confirmation
            category = context.user_data.get('report_category')
            report_text = context.user_data.get('report_text')
            
            if not category or not report_text:
                await update.message.reply_text("❌ Missing report information. Please start over.")
                context.user_data.clear()
                return
            
            # Format targets list for display
            targets_display = "\n".join([f"• `{t.get('username') or t.get('id')}`" for t in targets[:5]])
            if len(targets) > 5:
                targets_display += f"\n• ... and {len(targets) - 5} more"
            
            confirm_text = f"""
📝 **Report Confirmation**

━━━━━━━━━━━━━━━━━━━━━
📋 **Category:** `{REPORT_CATEGORIES.get(category, category)}`
🎯 **Targets:** `{len(targets)}`
{targets_display}
💰 **Cost:** `{required_tokens}` tokens
💳 **Your Balance:** `{db_user.tokens}` tokens
━━━━━━━━━━━━━━━━━━━━━

**Report Text:**
`{report_text[:200]}{'...' if len(report_text) > 200 else ''}`

Proceed with reporting?
"""
            keyboard = [
                [
                    InlineKeyboardButton("✅ Yes, Proceed", callback_data='confirm_report'),
                    InlineKeyboardButton("❌ Cancel", callback_data='back_to_main')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            context.user_data['targets'] = targets
            await update.message.reply_text(confirm_text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in target handling: {e}")
            session.rollback()
            await update.message.reply_text("❌ Error processing request. Please try again.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")
    
    # Rollback database session on error
    try:
        session.rollback()
    except:
        pass
    
    try:
        if update and update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                "❌ An error occurred. Please try again or use /start"
            )
        elif update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ An error occurred. Please try again later or use /start"
            )
    except:
        pass

def main():
    """Start the bot"""
    try:
        # Create application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Add error handler
        application.add_error_handler(error_handler)
        
        logger.info("🤖 Bot started successfully!")
        logger.info(f"Bot Token: {BOT_TOKEN[:10]}...")
        logger.info(f"Owner ID: {OWNER_ID}")
        
        # Start bot
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

if __name__ == '__main__':
    main()