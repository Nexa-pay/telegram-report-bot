#!/usr/bin/env python3
"""
Telegram Report Bot - Auto reporting for channels, groups, and users
Can be deployed on Railway.app
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)

import config

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
REPORT_TYPE, REPORT_TARGET, REPORT_REASON, REPORT_DETAILS, CONFIRMATION = range(5)

# Report types
REPORT_TYPES = {
    'user': '👤 User',
    'group': '👥 Group',
    'channel': '📢 Channel'
}

# User cooldown tracking
user_cooldowns: Dict[int, datetime] = {}

class ReportBot:
    def __init__(self):
        self.application = None
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a welcome message when /start is issued."""
        user = update.effective_user
        welcome_msg = (
            f"👋 Hello {user.first_name}!\n\n"
            "Welcome to the Telegram Report Bot. This bot helps you report:\n"
            "• Suspicious users\n"
            "• Problematic groups\n"
            "• Violating channels\n\n"
            "Please use /report to start a new report.\n"
            "Use /help to see all available commands."
        )
        await update.message.reply_text(welcome_msg)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a help message."""
        help_text = (
            "📚 **Available Commands:**\n\n"
            "/start - Start the bot\n"
            "/help - Show this help message\n"
            "/report - Report a user, group, or channel\n"
            "/myreports - View your recent reports\n"
            "/cancel - Cancel current operation\n\n"
            "**How to Report:**\n"
            "1. Use /report command\n"
            "2. Select what you want to report\n"
            "3. Provide the username or link\n"
            "4. Choose a reason\n"
            "5. Add additional details\n"
            "6. Confirm your report\n\n"
            "All reports are reviewed by our team."
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def report_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start the report conversation."""
        user_id = update.effective_user.id
        
        # Check cooldown
        if user_id in user_cooldowns:
            cooldown_end = user_cooldowns[user_id]
            if datetime.now() < cooldown_end:
                remaining = (cooldown_end - datetime.now()).seconds
                await update.message.reply_text(
                    f"⏰ Please wait {remaining} seconds before creating another report."
                )
                return ConversationHandler.END
        
        # Create inline keyboard for report types
        keyboard = [
            [InlineKeyboardButton(REPORT_TYPES['user'], callback_data='type_user')],
            [InlineKeyboardButton(REPORT_TYPES['group'], callback_data='type_group')],
            [InlineKeyboardButton(REPORT_TYPES['channel'], callback_data='type_channel')],
            [InlineKeyboardButton('❌ Cancel', callback_data='cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🔍 **What would you like to report?**\n\n"
            "Please select one of the options below:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return REPORT_TYPE

    async def report_type_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle report type selection."""
        query = update.callback_query
        await query.answer()
        
        if query.data == 'cancel':
            await query.edit_message_text("❌ Report cancelled.")
            return ConversationHandler.END
        
        # Store report type in context
        report_type = query.data.replace('type_', '')
        context.user_data['report_type'] = report_type
        
        await query.edit_message_text(
            f"📝 You selected: **{REPORT_TYPES[report_type]}**\n\n"
            f"Please send the username or invite link of the {report_type} you want to report.\n\n"
            f"Examples:\n"
            f"• Username: @username\n"
            f"• Link: https://t.me/username\n"
            f"• Group link: https://t.me/+abc123...",
            parse_mode='Markdown'
        )
        
        return REPORT_TARGET

    async def report_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Store the target username/link."""
        target = update.message.text.strip()
        
        # Validate target format
        if not self.validate_target(target):
            await update.message.reply_text(
                "❌ Invalid format. Please provide a valid username or Telegram link.\n\n"
                "Examples:\n"
                "• @username\n"
                "• https://t.me/username\n"
                "• https://t.me/+abc123..."
            )
            return REPORT_TARGET
        
        context.user_data['report_target'] = target
        
        # Create keyboard for report reasons
        reasons = {
            'spam': '📧 Spam',
            'scam': '💰 Scam/Fraud',
            'harassment': '⚠️ Harassment',
            'illegal': '🚫 Illegal Content',
            'impersonation': '👤 Impersonation',
            'other': '📌 Other'
        }
        
        keyboard = [
            [InlineKeyboardButton(reason, callback_data=f'reason_{key}')]
            for key, reason in reasons.items()
        ]
        keyboard.append([InlineKeyboardButton('❌ Cancel', callback_data='cancel')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ **Select a reason for your report:**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return REPORT_REASON

    async def report_reason_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle reason selection."""
        query = update.callback_query
        await query.answer()
        
        if query.data == 'cancel':
            await query.edit_message_text("❌ Report cancelled.")
            return ConversationHandler.END
        
        reason = query.data.replace('reason_', '')
        context.user_data['report_reason'] = reason
        
        await query.edit_message_text(
            "📝 **Please provide additional details:**\n\n"
            "Include any relevant information that might help us investigate this report.\n"
            f"Maximum {config.MAX_REPORT_LENGTH} characters.\n\n"
            "Send /skip to continue without additional details.",
            parse_mode='Markdown'
        )
        
        return REPORT_DETAILS

    async def report_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Store additional details."""
        details = update.message.text.strip()
        
        if len(details) > config.MAX_REPORT_LENGTH:
            await update.message.reply_text(
                f"❌ Details too long. Maximum {config.MAX_REPORT_LENGTH} characters allowed.\n"
                "Please try again or use /skip to continue without details."
            )
            return REPORT_DETAILS
        
        context.user_data['report_details'] = details
        return await self.confirm_report(update, context)

    async def skip_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Skip additional details."""
        context.user_data['report_details'] = "No additional details provided."
        return await self.confirm_report(update, context)

    async def confirm_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Show report summary for confirmation."""
        user_data = context.user_data
        
        summary = (
            "📋 **Please confirm your report:**\n\n"
            f"**Type:** {REPORT_TYPES[user_data['report_type']]}\n"
            f"**Target:** {user_data['report_target']}\n"
            f"**Reason:** {user_data['report_reason'].capitalize()}\n"
            f"**Details:** {user_data['report_details'][:200]}"
        )
        
        keyboard = [
            [
                InlineKeyboardButton('✅ Confirm', callback_data='confirm'),
                InlineKeyboardButton('❌ Cancel', callback_data='cancel')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Handle both message and callback query contexts
        if update.message:
            await update.message.reply_text(summary, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.callback_query.edit_message_text(summary, reply_markup=reply_markup, parse_mode='Markdown')
        
        return CONFIRMATION

    async def confirmation_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle report confirmation."""
        query = update.callback_query
        await query.answer()
        
        if query.data == 'cancel':
            await query.edit_message_text("❌ Report cancelled.")
            return ConversationHandler.END
        
        # Save the report
        await self.save_report(update, context)
        
        # Set cooldown
        user_id = update.effective_user.id
        user_cooldowns[user_id] = datetime.now() + timedelta(seconds=config.REPORT_COOLDOWN)
        
        await query.edit_message_text(
            "✅ **Report submitted successfully!**\n\n"
            "Thank you for helping keep Telegram safe. Our team will review your report.\n"
            "You can use /report to submit another report.",
            parse_mode='Markdown'
        )
        
        # Clear user data
        context.user_data.clear()
        
        return ConversationHandler.END

    async def save_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Save report to database and forward to admin channel."""
        user_data = context.user_data
        user = update.effective_user
        
        report_text = (
            f"🚨 **NEW REPORT**\n\n"
            f"**Report ID:** #{datetime.now().strftime('%Y%m%d%H%M%S')}\n"
            f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"**Reporter:** {user.full_name} (ID: `{user.id}`)\n"
            f"**Type:** {REPORT_TYPES[user_data['report_type']]}\n"
            f"**Target:** {user_data['report_target']}\n"
            f"**Reason:** {user_data['report_reason'].capitalize()}\n"
            f"**Details:** {user_data['report_details']}\n"
        )
        
        # Send to report channel if configured
        if config.REPORT_CHANNEL_ID:
            try:
                await context.bot.send_message(
                    chat_id=config.REPORT_CHANNEL_ID,
                    text=report_text,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to send report to channel: {e}")
        
        # Send to admins
        for admin_id in config.ADMIN_IDS:
            try:
                # Add action buttons for admins
                keyboard = [
                    [
                        InlineKeyboardButton('✅ Resolve', callback_data=f'resolve_{user.id}'),
                        InlineKeyboardButton('❌ Reject', callback_data=f'reject_{user.id}')
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=report_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to send report to admin {admin_id}: {e}")

    async def my_reports(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show user's recent reports."""
        # This is a placeholder - implement database query for actual report history
        await update.message.reply_text(
            "📊 Your recent reports feature will be available soon.\n"
            "This would show your last 5 reports and their status."
        )

    async def admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle admin actions on reports."""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith('resolve'):
            await query.edit_message_text(
                query.message.text + "\n\n✅ **Report resolved by admin**",
                parse_mode='Markdown'
            )
        elif query.data.startswith('reject'):
            await query.edit_message_text(
                query.message.text + "\n\n❌ **Report rejected by admin**",
                parse_mode='Markdown'
            )

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel the conversation."""
        await update.message.reply_text(
            "❌ Operation cancelled. Use /report to start a new report."
        )
        return ConversationHandler.END

    def validate_target(self, target: str) -> bool:
        """Validate report target format."""
        patterns = [
            r'^@\w{5,32}$',  # Username format
            r'^https?://t\.me/[\w\+]+/?$',  # Telegram link
            r'^https?://t\.me/\+[\w]+$',  # Private group invite
        ]
        
        return any(re.match(pattern, target) for pattern in patterns)

    def setup(self):
        """Set up the bot application and handlers."""
        # Create application
        self.application = Application.builder().token(config.BOT_TOKEN).build()

        # Conversation handler for reporting
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('report', self.report_command)],
            states={
                REPORT_TYPE: [CallbackQueryHandler(self.report_type_callback, pattern='^(type_|cancel)')],
                REPORT_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.report_target)],
                REPORT_REASON: [CallbackQueryHandler(self.report_reason_callback, pattern='^(reason_|cancel)')],
                REPORT_DETAILS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.report_details),
                    CommandHandler('skip', self.skip_details)
                ],
                CONFIRMATION: [CallbackQueryHandler(self.confirmation_callback, pattern='^(confirm|cancel)$')],
            },
            fallbacks=[CommandHandler('cancel', self.cancel)],
        )

        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("myreports", self.my_reports))
        self.application.add_handler(conv_handler)
        self.application.add_handler(CallbackQueryHandler(self.admin_callback, pattern='^(resolve|reject)'))

    async def run(self):
        """Run the bot."""
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        logger.info("Bot started. Press Ctrl+C to stop.")
        
        # Keep the bot running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopping bot...")
        finally:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

def main():
    """Main function to run the bot."""
    bot = ReportBot()
    bot.setup()
    
    # Run the bot
    asyncio.run(bot.run())

if __name__ == '__main__':
    main()