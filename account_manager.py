from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession
from database import Session, TelegramAccount
import asyncio
import logging
import os
from config import API_ID, API_HASH

# Create sessions directory if it doesn't exist
SESSIONS_DIR = 'sessions'
os.makedirs(SESSIONS_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AccountManager:
    def __init__(self):
        self.active_clients = {}
        self.session = Session()
        # Store phone_code_hash temporarily
        self.phone_code_hashes = {}
        
    async def add_account(self, phone_number, verification_code=None, password=None, phone_code_hash=None):
        """Add a new Telegram account for reporting"""
        try:
            # Use file-based session for initial authentication
            session_path = os.path.join(SESSIONS_DIR, phone_number.replace('+', ''))
            client = TelegramClient(session_path, API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                if not verification_code:
                    # First step: Request code
                    result = await client.send_code_request(phone_number)
                    # Store the phone_code_hash
                    self.phone_code_hashes[phone_number] = result.phone_code_hash
                    await client.disconnect()
                    return {
                        'status': 'code_sent', 
                        'phone': phone_number,
                        'phone_code_hash': result.phone_code_hash
                    }
                else:
                    # Second step: Sign in with code
                    try:
                        # Get the stored phone_code_hash
                        stored_hash = phone_code_hash or self.phone_code_hashes.get(phone_number)
                        
                        if not stored_hash:
                            return {'status': 'error', 'message': 'Missing phone_code_hash. Please start over.'}
                        
                        await client.sign_in(
                            phone_number, 
                            code=verification_code,
                            phone_code_hash=stored_hash
                        )
                    except SessionPasswordNeededError:
                        # 2FA enabled
                        if password:
                            await client.sign_in(password=password)
                        else:
                            await client.disconnect()
                            return {
                                'status': 'password_needed', 
                                'phone': phone_number,
                                'phone_code_hash': stored_hash
                            }
            
            # Get the session string for database storage
            session_string = StringSession.save(client.session)
            
            # Save to database
            account = TelegramAccount(
                phone_number=phone_number,
                session_string=session_string,
                is_active=True,
                status='available'
            )
            self.session.add(account)
            self.session.commit()
            
            await client.disconnect()
            
            # Remove the file-based session
            if os.path.exists(session_path + '.session'):
                os.remove(session_path + '.session')
            
            # Clear stored hash
            if phone_number in self.phone_code_hashes:
                del self.phone_code_hashes[phone_number]
            
            logger.info(f"Successfully added account: {phone_number}")
            return {'status': 'success', 'phone': phone_number}
            
        except Exception as e:
            logger.error(f"Error adding account {phone_number}: {e}")
            return {'status': 'error', 'phone': phone_number, 'error': str(e)}
    
    async def get_available_accounts(self, limit=5):
        """Get available accounts for reporting"""
        try:
            accounts = self.session.query(TelegramAccount).filter_by(
                is_active=True, 
                status='available'
            ).limit(limit).all()
            return accounts
        except Exception as e:
            logger.error(f"Error getting available accounts: {e}")
            return []
    
    async def report_target(self, account, target_username, category, custom_text):
        """Report a target using specific account"""
        client = None
        try:
            # Create client from session string
            client = TelegramClient(
                StringSession(account.session_string), 
                API_ID, 
                API_HASH
            )
            await client.connect()
            
            # Check if client is authorized
            if not await client.is_user_authorized():
                account.is_active = False
                self.session.commit()
                return {'status': 'failed', 'reason': 'account_not_authorized'}
            
            # Get the target entity
            try:
                # Clean up username
                if target_username and isinstance(target_username, str):
                    if target_username.startswith('@'):
                        target_username = target_username[1:]
                
                # Try to get entity
                try:
                    if target_username and target_username.strip():
                        entity = await client.get_entity(target_username)
                    else:
                        return {'status': 'failed', 'reason': 'invalid_target'}
                except ValueError:
                    # Try as integer ID
                    try:
                        entity = await client.get_entity(int(target_username))
                    except:
                        return {'status': 'failed', 'reason': 'target_not_found'}
                
            except Exception as e:
                logger.error(f"Error getting entity: {e}")
                return {'status': 'failed', 'reason': f'target_not_found: {str(e)}'}
            
            # Prepare report message
            report_text = f"""
I am reporting this {"channel" if getattr(entity, 'broadcast', False) else "group" if getattr(entity, 'megagroup', False) else "user"} for violating Telegram's Terms of Service.

Category: {category}
Details: {custom_text}

This content is illegal and should be removed immediately.
"""
            
            # Try different reporting methods
            report_sent = False
            
            # Method 1: Send to Telegram's report bot
            try:
                await client.send_message(
                    '@SpamBot',
                    f'/report {target_username}'
                )
                report_sent = True
            except:
                pass
            
            # Method 2: Send to Telegram support
            if not report_sent:
                try:
                    await client.send_message(
                        'Telegram',
                        f"Report about {target_username}\n\n{report_text}"
                    )
                    report_sent = True
                except:
                    pass
            
            await client.disconnect()
            
            if report_sent:
                # Update account status
                account.status = 'available'
                account.reports_count += 1
                self.session.commit()
                logger.info(f"Successfully reported {target_username} with account {account.phone_number}")
                return {'status': 'success'}
            else:
                return {'status': 'failed', 'reason': 'report_methods_failed'}
            
        except Exception as e:
            logger.error(f"Error reporting with account {account.phone_number}: {e}")
            if client:
                try:
                    await client.disconnect()
                except:
                    pass
            
            # Reset account status
            try:
                account.status = 'available'
                self.session.commit()
            except:
                pass
            
            return {'status': 'failed', 'reason': str(e)}
    
    async def check_account_status(self, account_id):
        """Check if an account is still valid"""
        account = self.session.query(TelegramAccount).filter_by(id=account_id).first()
        if not account:
            return {'status': 'error', 'reason': 'account_not_found'}
        
        try:
            client = TelegramClient(
                StringSession(account.session_string),
                API_ID,
                API_HASH
            )
            await client.connect()
            
            if await client.is_user_authorized():
                await client.disconnect()
                return {'status': 'active'}
            else:
                account.is_active = False
                self.session.commit()
                await client.disconnect()
                return {'status': 'inactive'}
                
        except Exception as e:
            logger.error(f"Error checking account {account.phone_number}: {e}")
            return {'status': 'error', 'reason': str(e)}
    
    async def remove_account(self, account_id):
        """Remove an account from the system"""
        try:
            account = self.session.query(TelegramAccount).filter_by(id=account_id).first()
            if account:
                self.session.delete(account)
                self.session.commit()
                return {'status': 'success'}
            return {'status': 'error', 'reason': 'account_not_found'}
        except Exception as e:
            logger.error(f"Error removing account: {e}")
            return {'status': 'error', 'reason': str(e)}
    
    async def get_account_stats(self):
        """Get statistics about all accounts"""
        try:
            total = self.session.query(TelegramAccount).count()
            active = self.session.query(TelegramAccount).filter_by(is_active=True).count()
            available = self.session.query(TelegramAccount).filter_by(status='available', is_active=True).count()
            banned = self.session.query(TelegramAccount).filter_by(is_active=False).count()
            
            return {
                'total': total,
                'active': active,
                'available': available,
                'banned': banned
            }
        except Exception as e:
            logger.error(f"Error getting account stats: {e}")
            return {
                'total': 0,
                'active': 0,
                'available': 0,
                'banned': 0
            }