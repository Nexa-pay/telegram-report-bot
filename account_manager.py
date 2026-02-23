from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError, 
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    FloodWaitError,
    PhoneNumberInvalidError,
    PasswordHashInvalidError,
    PhoneCodeHashEmptyError
)
from telethon.sessions import StringSession
from database import Session, TelegramAccount
import logging
import os
import time
import asyncio
from config import API_ID, API_HASH

# Create sessions directory if it doesn't exist
SESSIONS_DIR = 'sessions'
os.makedirs(SESSIONS_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AccountManager:
    def __init__(self):
        self.session = Session()
        # Store active clients and their data
        self.active_sessions = {}  # phone -> {client, phone_code_hash, created_at}
        
    async def add_account(self, phone_number, verification_code=None, password=None):
        """Add a new Telegram account for reporting"""
        try:
            # Clean phone number
            clean_phone = phone_number.replace('+', '')
            session_path = os.path.join(SESSIONS_DIR, clean_phone)
            session_file = session_path + '.session'
            
            # Remove old session file if it exists
            if os.path.exists(session_file):
                os.remove(session_file)
                logger.info(f"Removed old session file for {phone_number}")
            
            # Create new client
            client = TelegramClient(session_path, API_ID, API_HASH)
            await client.connect()
            
            # Check if already authorized
            if await client.is_user_authorized():
                # Already authorized, save session
                return await self._save_authorized_client(client, phone_number, session_file)
            
            # Step 1: Send code
            if verification_code is None and password is None:
                try:
                    logger.info(f"Sending code request to {phone_number}")
                    
                    # Send code request
                    result = await client.send_code_request(phone_number)
                    
                    # Store client and hash in active sessions
                    self.active_sessions[phone_number] = {
                        'client': client,
                        'phone_code_hash': result.phone_code_hash,
                        'created_at': time.time()
                    }
                    
                    logger.info(f"Code sent successfully to {phone_number}")
                    
                    return {
                        'status': 'code_sent',
                        'phone': phone_number,
                        'phone_code_hash': result.phone_code_hash,
                        'message': 'Verification code sent. Please enter it within 2 minutes.'
                    }
                    
                except FloodWaitError as e:
                    wait_time = e.seconds
                    logger.warning(f"Flood wait for {phone_number}: {wait_time} seconds")
                    await client.disconnect()
                    return {
                        'status': 'flood_wait',
                        'phone': phone_number,
                        'wait_time': wait_time,
                        'message': f'Too many attempts. Please wait {wait_time} seconds.'
                    }
                    
                except PhoneNumberInvalidError:
                    await client.disconnect()
                    return {
                        'status': 'error',
                        'phone': phone_number,
                        'error': 'Invalid phone number format. Use international format: +1234567890'
                    }
                    
                except Exception as e:
                    await client.disconnect()
                    logger.error(f"Error sending code to {phone_number}: {e}")
                    return {
                        'status': 'error',
                        'phone': phone_number,
                        'error': str(e)
                    }
            
            # Step 2: Verify code
            elif verification_code and password is None:
                # Get stored session data
                session_data = self.active_sessions.get(phone_number)
                
                if not session_data:
                    return {
                        'status': 'error',
                        'phone': phone_number,
                        'error': 'Session expired. Please start over.'
                    }
                
                client = session_data['client']
                phone_code_hash = session_data['phone_code_hash']
                created_at = session_data['created_at']
                
                # Check if code expired (2 minutes)
                if time.time() - created_at > 120:
                    # Clean up expired session
                    await client.disconnect()
                    del self.active_sessions[phone_number]
                    if os.path.exists(session_file):
                        os.remove(session_file)
                    return {
                        'status': 'code_expired',
                        'phone': phone_number,
                        'message': 'Verification code expired. Please request a new code.'
                    }
                
                try:
                    logger.info(f"Attempting to sign in {phone_number} with code")
                    
                    # Try to sign in with code
                    await client.sign_in(
                        phone_number,
                        code=verification_code,
                        phone_code_hash=phone_code_hash
                    )
                    
                    # If successful and no 2FA, save session
                    logger.info(f"Code sign in successful for {phone_number}")
                    return await self._save_authorized_client(client, phone_number, session_file)
                    
                except SessionPasswordNeededError:
                    # 2FA required - keep session alive
                    logger.info(f"2FA required for {phone_number}")
                    
                    # Update timestamp to keep session alive
                    session_data['created_at'] = time.time()
                    
                    return {
                        'status': 'password_needed',
                        'phone': phone_number,
                        'message': 'This account has 2FA enabled. Please enter your password.'
                    }
                    
                except PhoneCodeExpiredError:
                    logger.warning(f"Code expired for {phone_number}")
                    await client.disconnect()
                    del self.active_sessions[phone_number]
                    if os.path.exists(session_file):
                        os.remove(session_file)
                    return {
                        'status': 'code_expired',
                        'phone': phone_number,
                        'message': 'Verification code expired. Please request a new code.'
                    }
                    
                except PhoneCodeInvalidError:
                    logger.warning(f"Invalid code for {phone_number}")
                    return {
                        'status': 'code_invalid',
                        'phone': phone_number,
                        'message': 'Invalid verification code. Please try again.'
                    }
                    
                except Exception as e:
                    logger.error(f"Error during code verification: {e}")
                    await client.disconnect()
                    del self.active_sessions[phone_number]
                    return {
                        'status': 'error',
                        'phone': phone_number,
                        'error': str(e)
                    }
            
            # Step 3: Enter password (2FA)
            elif password:
                # Get stored session data
                session_data = self.active_sessions.get(phone_number)
                
                if not session_data:
                    return {
                        'status': 'error',
                        'phone': phone_number,
                        'error': 'Session expired. Please start over.'
                    }
                
                client = session_data['client']
                
                # Check if client is still connected
                if not client.is_connected():
                    logger.warning(f"Client disconnected for {phone_number}, reconnecting...")
                    await client.connect()
                
                try:
                    logger.info(f"Attempting to sign in {phone_number} with password")
                    
                    # Try to sign in with password
                    await client.sign_in(password=password)
                    
                    # If successful, save session
                    logger.info(f"Password sign in successful for {phone_number}")
                    return await self._save_authorized_client(client, phone_number, session_file)
                    
                except PasswordHashInvalidError:
                    logger.warning(f"Invalid password for {phone_number}")
                    return {
                        'status': 'password_error',
                        'phone': phone_number,
                        'error': 'Invalid password'
                    }
                    
                except FloodWaitError as e:
                    wait_time = e.seconds
                    logger.warning(f"Flood wait during password for {phone_number}: {wait_time} seconds")
                    return {
                        'status': 'flood_wait',
                        'phone': phone_number,
                        'wait_time': wait_time,
                        'message': f'Too many attempts. Please wait {wait_time} seconds.'
                    }
                    
                except Exception as e:
                    logger.error(f"Error during password verification: {e}")
                    return {
                        'status': 'password_error',
                        'phone': phone_number,
                        'error': str(e)
                    }
            
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {
                'status': 'error',
                'phone': phone_number,
                'error': str(e)
            }
    
    async def _save_authorized_client(self, client, phone_number, session_file):
        """Save an authorized client to database"""
        try:
            # Get session string
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
            
            logger.info(f"Successfully added account: {phone_number}")
            
            # Clean up
            await client.disconnect()
            
            # Remove from active sessions
            if phone_number in self.active_sessions:
                del self.active_sessions[phone_number]
            
            # Remove session file
            if os.path.exists(session_file):
                os.remove(session_file)
            
            return {
                'status': 'success',
                'phone': phone_number,
                'message': 'Account added successfully!'
            }
            
        except Exception as e:
            logger.error(f"Error saving account: {e}")
            await client.disconnect()
            return {
                'status': 'error',
                'phone': phone_number,
                'error': f'Database error: {str(e)}'
            }
    
    async def resend_code(self, phone_number):
        """Resend verification code"""
        try:
            # Clean up existing session for this phone
            if phone_number in self.active_sessions:
                try:
                    await self.active_sessions[phone_number]['client'].disconnect()
                except:
                    pass
                del self.active_sessions[phone_number]
            
            # Remove session file
            clean_phone = phone_number.replace('+', '')
            session_file = os.path.join(SESSIONS_DIR, clean_phone) + '.session'
            if os.path.exists(session_file):
                os.remove(session_file)
            
            # Wait a bit to ensure cleanup
            await asyncio.sleep(2)
            
            # Create new client
            session_path = os.path.join(SESSIONS_DIR, clean_phone)
            client = TelegramClient(session_path, API_ID, API_HASH)
            await client.connect()
            
            # Send new code
            result = await client.send_code_request(phone_number)
            
            # Store in active sessions
            self.active_sessions[phone_number] = {
                'client': client,
                'phone_code_hash': result.phone_code_hash,
                'created_at': time.time()
            }
            
            logger.info(f"New code sent to {phone_number}")
            
            return {
                'status': 'code_sent',
                'phone': phone_number,
                'phone_code_hash': result.phone_code_hash,
                'message': 'New verification code sent. Please enter it within 2 minutes.'
            }
            
        except FloodWaitError as e:
            wait_time = e.seconds
            logger.warning(f"Flood wait for {phone_number}: {wait_time} seconds")
            return {
                'status': 'flood_wait',
                'phone': phone_number,
                'wait_time': wait_time,
                'message': f'Too many attempts. Please wait {wait_time} seconds.'
            }
            
        except Exception as e:
            logger.error(f"Error resending code: {e}")
            return {
                'status': 'error',
                'phone': phone_number,
                'error': str(e)
            }
    
    async def cancel_login(self, phone_number):
        """Cancel an ongoing login attempt"""
        try:
            if phone_number in self.active_sessions:
                try:
                    await self.active_sessions[phone_number]['client'].disconnect()
                except:
                    pass
                del self.active_sessions[phone_number]
            
            # Remove session file
            clean_phone = phone_number.replace('+', '')
            session_file = os.path.join(SESSIONS_DIR, clean_phone) + '.session'
            if os.path.exists(session_file):
                os.remove(session_file)
            
            logger.info(f"Cancelled login for {phone_number}")
            return {'status': 'success'}
            
        except Exception as e:
            logger.error(f"Error cancelling login: {e}")
            return {'status': 'error', 'error': str(e)}
    
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
                if target_username.startswith('@'):
                    target_username = target_username[1:]
                
                try:
                    entity = await client.get_entity(target_username)
                except ValueError:
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
            
            # Method 1: Send to @SpamBot
            try:
                await client.send_message('@SpamBot', f'/report {target_username}')
                report_sent = True
                logger.info(f"Reported via @SpamBot: {target_username}")
            except Exception as e:
                logger.error(f"Error reporting via @SpamBot: {e}")
            
            # Method 2: Send to Telegram support
            if not report_sent:
                try:
                    await client.send_message('Telegram', f"Report about {target_username}\n\n{report_text}")
                    report_sent = True
                    logger.info(f"Reported via Telegram support: {target_username}")
                except Exception as e:
                    logger.error(f"Error reporting via Telegram support: {e}")
            
            await client.disconnect()
            
            if report_sent:
                account.status = 'available'
                account.reports_count += 1
                self.session.commit()
                return {'status': 'success'}
            else:
                return {'status': 'failed', 'reason': 'report_methods_failed'}
            
        except Exception as e:
            logger.error(f"Error reporting: {e}")
            if client:
                await client.disconnect()
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
            client = TelegramClient(StringSession(account.session_string), API_ID, API_HASH)
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
            logger.error(f"Error checking account: {e}")
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