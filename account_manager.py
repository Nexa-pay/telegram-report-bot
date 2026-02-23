from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from database import Session, TelegramAccount
import asyncio
import logging
from config import API_ID, API_HASH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AccountManager:
    def __init__(self):
        self.active_clients = {}
        self.session = Session()
        
    async def add_account(self, phone_number, verification_code=None, password=None):
        """Add a new Telegram account for reporting"""
        try:
            client = TelegramClient(f'sessions/{phone_number}', API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                if not verification_code:
                    await client.send_code_request(phone_number)
                    return {'status': 'code_sent', 'phone': phone_number}
                else:
                    try:
                        await client.sign_in(phone_number, verification_code)
                    except SessionPasswordNeededError:
                        if password:
                            await client.sign_in(password=password)
                        else:
                            return {'status': 'password_needed', 'phone': phone_number}
            
            # Save session
            session_string = client.session.save()
            account = TelegramAccount(
                phone_number=phone_number,
                session_string=session_string
            )
            self.session.add(account)
            self.session.commit()
            
            await client.disconnect()
            return {'status': 'success', 'phone': phone_number}
            
        except Exception as e:
            logger.error(f"Error adding account {phone_number}: {e}")
            return {'status': 'error', 'phone': phone_number, 'error': str(e)}
    
    async def get_available_accounts(self, limit=5):
        """Get available accounts for reporting"""
        accounts = self.session.query(TelegramAccount).filter_by(
            is_active=True, 
            status='available'
        ).limit(limit).all()
        return accounts
    
    async def report_target(self, account, target_username, category, custom_text):
        """Report a target using specific account"""
        try:
            client = TelegramClient(
                StringSession(account.session_string), 
                API_ID, 
                API_HASH
            )
            await client.connect()
            
            # Get the target entity
            try:
                if target_username.startswith('@'):
                    target_username = target_username[1:]
                entity = await client.get_entity(target_username)
            except:
                # Try as user ID
                try:
                    entity = await client.get_entity(int(target_username))
                except:
                    return {'status': 'failed', 'reason': 'target_not_found'}
            
            # Prepare report message
            report_text = f"Report Category: {category}\n\n{custom_text}\n\nThis content violates Telegram's Terms of Service."
            
            # Send report through Telegram's report system
            # Note: This is a simplified version. Actual implementation would use Telegram's report API
            result = await client.send_message(
                'Telegram',  # Telegram support
                f"/report {entity.id}\n{report_text}"
            )
            
            await client.disconnect()
            
            # Update account status
            account.status = 'available'
            account.reports_count += 1
            self.session.commit()
            
            return {'status': 'success'}
            
        except Exception as e:
            logger.error(f"Error reporting with account {account.phone_number}: {e}")
            account.status = 'available'
            self.session.commit()
            return {'status': 'failed', 'reason': str(e)}