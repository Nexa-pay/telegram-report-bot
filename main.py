import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from database import Session, User, Transaction
from account_manager import AccountManager
from reporter import Reporter
from config import BOT_TOKEN, OWNER_ID, REPORT_CATEGORIES, REPORT_TEMPLATES, DEFAULT_TOKENS, REPORT_COST
import asyncio
from datetime import datetime

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
    
    # Check if user exists
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
Welcome {user.first_name}!

ID: {user.id}
Tokens: {db_user.tokens}
Role: {db_user.role}
Reports Made: {db_user.reports_made}

Select an option below:
"""
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    db_user = session.query(User).filter_by(user_id=user_id).first()
    
    if query.data == 'stats':
        stats_text = f"""
📊 Your Statistics

User ID: {db_user.user_id}
Username: @{db_user.username or 'N/A'}
Tokens: {db_user.tokens}
Role: {db_user.role}
Reports Made: {db_user.reports_made}
Joined: {db_user.joined_date.strftime('%Y-%m-%d')}
Last Active: {db_user.last_active.strftime('%Y-%m-%d %H:%M')}
"""
        await query.edit_message_text(stats_text)
        
    elif query.data == 'report_menu':
        # Show report categories
        keyboard = []
        for key, value in REPORT_CATEGORIES.items():
            keyboard.append([InlineKeyboardButton(value, callback_data=f'report_cat_{key}')])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='back_to_main')])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Select report category:",
            reply_markup=reply_markup
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
            f"Category: {REPORT_CATEGORIES[category]}\n\n"
            f"Template: {REPORT_TEMPLATES[category]}\n\n"
            "Choose an option:",
            reply_markup=reply_markup
        )
        
    elif query.data == 'use_template':
        context.user_data['report_text'] = context.user_data['report_template']
        await query.edit_message_text(
            "Send me the username or ID of the target (user, group, or channel)\n"
            "You can send multiple by separating with commas or new lines."
        )
        context.user_data['awaiting_target'] = True
        
    elif query.data == 'custom_text':
        await query.edit_message_text(
            "Send me your custom report text:"
        )
        context.user_data['awaiting_custom_text'] = True
        
    elif query.data == 'buy_tokens':
        keyboard = [
            [InlineKeyboardButton("10 Tokens - $1", callback_data='buy_10')],
            [InlineKeyboardButton("50 Tokens - $4", callback_data='buy_50')],
            [InlineKeyboardButton("100 Tokens - $7", callback_data='buy_100')],
            [InlineKeyboardButton("500 Tokens - $30", callback_data='buy_500')],
            [InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "💰 Buy Tokens\n\n"
            f"Your current tokens: {db_user.tokens}\n"
            "Select package:",
            reply_markup=reply_markup
        )
        
    elif query.data.startswith('buy_'):
        amount = int(query.data.replace('buy_', ''))
        # Here you would integrate with payment gateway
        await query.edit_message_text(
            f"To purchase {amount} tokens, please contact @admin\n\n"
            "Payment integration coming soon!"
        )
        
    elif query.data == 'my_reports':
        reports = session.query(Report).filter_by(reported_by=user_id).order_by(Report.created_at.desc()).limit(10).all()
        
        if not reports:
            await query.edit_message_text("You haven't made any reports yet.")
            return
        
        text = "📋 Your Recent Reports:\n\n"
        for report in reports:
            text += f"ID: {report.id}\n"
            text += f"Target: {report.target_username or report.target_id}\n"
            text += f"Category: {report.category}\n"
            text += f"Status: {report.status}\n"
            text += f"Date: {report.created_at.strftime('%Y-%m-%d %H:%M')}\n"
            text += "-" * 20 + "\n"
        
        await query.edit_message_text(text)
        
    elif query.data == 'add_account':
        await query.edit_message_text(
            "📱 Add Telegram Account\n\n"
            "Please send me your phone number in international format:\n"
            "Example: +1234567890"
        )
        context.user_data['awaiting_phone'] = True
        
    elif query.data == 'admin_panel':
        if db_user.role not in ['owner', 'admin']:
            await query.edit_message_text("Access denied!")
            return
        
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
⚙️ Admin Panel

Statistics:
Total Users: {total_users}
Total Accounts: {total_accounts}
Active Accounts: {active_accounts}
Pending Reports: {pending_reports}
"""
        await query.edit_message_text(text, reply_markup=reply_markup)
        
    elif query.data == 'owner_panel':
        if db_user.role != 'owner':
            await query.edit_message_text("Access denied!")
            return
        
        keyboard = [
            [InlineKeyboardButton("💰 Add Tokens", callback_data='owner_add_tokens')],
            [InlineKeyboardButton("👑 Add Admin", callback_data='owner_add_admin')],
            [InlineKeyboardButton("📊 System Stats", callback_data='owner_stats')],
            [InlineKeyboardButton("⚙️ Settings", callback_data='owner_settings')],
            [InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text("👑 Owner Panel", reply_markup=reply_markup)
        
    elif query.data == 'back_to_main':
        await start(update, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if context.user_data.get('awaiting_phone'):
        # Handle phone number for account addition
        phone = text
        context.user_data['phone'] = phone
        context.user_data['awaiting_phone'] = False
        context.user_data['awaiting_code'] = True
        
        result = await account_manager.add_account(phone)
        
        if result['status'] == 'code_sent':
            await update.message.reply_text(
                "Verification code sent to your phone.\n"
                "Please enter the code:"
            )
        else:
            await update.message.reply_text(f"Error: {result.get('error', 'Unknown error')}")
            
    elif context.user_data.get('awaiting_code'):
        # Handle verification code
        code = text
        phone = context.user_data.get('phone')
        
        result = await account_manager.add_account(phone, code)
        
        if result['status'] == 'password_needed':
            context.user_data['awaiting_password'] = True
            await update.message.reply_text("This account has 2FA enabled. Please enter your password:")
        elif result['status'] == 'success':
            await update.message.reply_text("✅ Account added successfully!")
            context.user_data.clear()
        else:
            await update.message.reply_text(f"Error: {result.get('error', 'Unknown error')}")
            
    elif context.user_data.get('awaiting_password'):
        # Handle 2FA password
        password = text
        phone = context.user_data.get('phone')
        
        result = await account_manager.add_account(phone, password=password)
        
        if result['status'] == 'success':
            await update.message.reply_text("✅ Account added successfully!")
            context.user_data.clear()
        else:
            await update.message.reply_text(f"Error: {result.get('error', 'Unknown error')}")
            
    elif context.user_data.get('awaiting_custom_text'):
        # Handle custom report text
        context.user_data['report_text'] = text
        context.user_data['awaiting_custom_text'] = False
        context.user_data['awaiting_target'] = True
        await update.message.reply_text(
            "Send me the username or ID of the target (user, group, or channel)\n"
            "You can send multiple by separating with commas or new lines."
        )
        
    elif context.user_data.get('awaiting_target'):
        # Handle target(s) for reporting
        targets = []
        for line in text.split('\n'):
            for item in line.split(','):
                target = item.strip()
                if target:
                    target_type = 'user'
                    if target.startswith('@'):
                        target_type = 'channel'  # Could be group or channel
                    elif target.startswith('-100'):
                        target_type = 'channel'  # Telegram channel ID
                    
                    targets.append({
                        'type': target_type,
                        'username': target if target.startswith('@') else None,
                        'id': target if not target.startswith('@') else None
                    })
        
        if not targets:
            await update.message.reply_text("No valid targets found!")
            return
        
        # Check tokens
        db_user = session.query(User).filter_by(user_id=user_id).first()
        if db_user.role != 'owner' and db_user.tokens < len(targets):
            await update.message.reply_text(
                f"Insufficient tokens! You need {len(targets)} tokens but have {db_user.tokens}."
            )
            return
        
        # Send confirmation
        category = context.user_data.get('report_category')
        report_text = context.user_data.get('report_text')
        
        confirm_text = f"""
📝 Report Confirmation

Category: {REPORT_CATEGORIES.get(category, category)}
Targets: {len(targets)}
Cost: {len(targets) * REPORT_COST} tokens
Your tokens: {db_user.tokens}

Report Text:
{report_text}

Proceed with reporting?
"""
        keyboard = [
            [InlineKeyboardButton("✅ Yes, Proceed", callback_data='confirm_report')],
            [InlineKeyboardButton("❌ Cancel", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        context.user_data['targets'] = targets
        await update.message.reply_text(confirm_text, reply_markup=reply_markup)
        
    elif query.data == 'confirm_report':
        # Execute reports
        targets = context.user_data.get('targets', [])
        category = context.user_data.get('report_category')
        report_text = context.user_data.get('report_text')
        
        await query.edit_message_text("🔄 Processing reports... This may take a few minutes.")
        
        result = await reporter.bulk_report(targets, category, report_text, user_id)
        
        if result['status'] == 'success':
            success_count = len(result['report_ids'])
            await query.edit_message_text(
                f"✅ Successfully submitted {success_count} reports!\n"
                f"Report IDs: {', '.join(map(str, result['report_ids']))}"
            )
        else:
            await query.edit_message_text(f"❌ Error: {result['message']}")
        
        context.user_data.clear()

def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()