from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError, 
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    FloodWaitError,
    PhoneNumberBannedError,
    PhoneNumberInvalidError
)
from telethon.sessions import StringSession
from database import Session, TelegramAccount
import asyncio
import logging
import os
import time
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
        # Store login attempts to track expiration
        self.login_attempts = {}
        
    async def add_account(self, phone_number, verification_code=None, password=None, phone_code_hash=None):
        """Add a new Telegram account for reporting with improved error handling"""
        try:
            # Check if there's an existing login attempt that expired
            if phone_number in self.login_attempts:
                attempt_time = self.login_attempts[phone_number].get('timestamp', 0)
                if time.time() - attempt_time > 120:  # 2 minutes
                    # Login attempt expired, remove it
                    del self.login_attempts[phone_number]
                    if phone_number in self.phone_code_hashes:
                        del self.phone_code_hashes[phone_number]
            
            # Use file-based session for initial authentication
            session_path = os.path.join(SESSIONS_DIR, phone_number.replace('+', ''))
            client = TelegramClient(session_path, API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                if not verification_code:
                    # First step: Request code
                    try:
                        logger.info(f"Sending code request to {phone_number}")
                        result = await client.send_code_request(phone_number)
                        
                        # Store the phone_code_hash
                        self.phone_code_hashes[phone_number] = result.phone_code_hash
                        self.login_attempts[phone_number] = {
                            'timestamp': time.time(),
                            'phone_code_hash': result.phone_code_hash
                        }
                        
                        await client.disconnect()
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
                        
                else:
                    # Second step: Sign in with code
                    try:
                        logger.info(f"Attempting to sign in {phone_number} with code")
                        
                        # Get the stored phone_code_hash
                        stored_hash = phone_code_hash or self.phone_code_hashes.get(phone_number)
                        
                        if not stored_hash:
                            return {
                                'status': 'error', 
                                'message': 'Missing phone_code_hash. Please start over.',
                                'phone': phone_number
                            }
                        
                        # Check if code expired (older than 2 minutes)
                        if phone_number in self.login_attempts:
                            attempt_time = self.login_attempts[phone_number].get('timestamp', 0)
                            if time.time() - attempt_time > 120:
                                # Clean up expired attempt
                                del self.login_attempts[phone_number]
                                if phone_number in self.phone_code_hashes:
                                    del self.phone_code_hashes[phone_number]
                                await client.disconnect()
                                return {
                                    'status': 'code_expired',
                                    'phone': phone_number,
                                    'message': 'Verification code expired. Please start over.'
                                }
                        
                        try:
                            await client.sign_in(
                                phone_number, 
                                code=verification_code,
                                phone_code_hash=stored_hash
                            )
                            
                        except PhoneCodeExpiredError:
                            logger.warning(f"Code expired for {phone_number}")
                            # Clean up expired attempt
                            if phone_number in self.login_attempts:
                                del self.login_attempts[phone_number]
                            if phone_number in self.phone_code_hashes:
                                del self.phone_code_hashes[phone_number]
                            await client.disconnect()
                            return {
                                'status': 'code_expired',
                                'phone': phone_number,
                                'message': 'Verification code expired. Please start over with a new code.'
                            }
                            
                        except PhoneCodeInvalidError:
                            logger.warning(f"Invalid code for {phone_number}")
                            await client.disconnect()
                            return {
                                'status': 'code_invalid',
                                'phone': phone_number,
                                'message': 'Invalid verification code. Please try again.'
                            }
                            
                        except SessionPasswordNeededError:
                            # 2FA enabled
                            logger.info(f"2FA required for {phone_number}")
                            if password:
                                try:
                                    await client.sign_in(password=password)
                                except Exception as e:
                                    await client.disconnect()
                                    return {
                                        'status': 'password_error',
                                        'phone': phone_number,
                                        'error': str(e)
                                    }
                            else:
                                await client.disconnect()
                                return {
                                    'status': 'password_needed', 
                                    'phone': phone_number,
                                    'phone_code_hash': stored_hash,
                                    'message': 'This account has 2FA enabled. Please enter your password.'
                                }
                            
                    except FloodWaitError as e:
                        wait_time = e.seconds
                        logger.warning(f"Flood wait during sign in for {phone_number}: {wait_time} seconds")
                        await client.disconnect()
                        return {
                            'status': 'flood_wait',
                            'phone': phone_number,
                            'wait_time': wait_time,
                            'message': f'Too many attempts. Please wait {wait_time} seconds.'
                        }
                        
                    except Exception as e:
                        logger.error(f"Error during sign in for {phone_number}: {e}")
                        await client.disconnect()
                        return {
                            'status': 'error',
                            'phone': phone_number,
                            'error': str(e)
                        }
            
            # If we get here, we're successfully authorized
            try:
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
                
                logger.info(f"Successfully added account: {phone_number}")
                
                # Clean up stored data
                if phone_number in self.phone_code_hashes:
                    del self.phone_code_hashes[phone_number]
                if phone_number in self.login_attempts:
                    del self.login_attempts[phone_number]
                
                # Remove the file-based session
                session_file = session_path + '.session'
                if os.path.exists(session_file):
                    os.remove(session_file)
                
                return {
                    'status': 'success', 
                    'phone': phone_number,
                    'message': 'Account added successfully!'
                }
                
            except Exception as e:
                logger.error(f"Error saving account {phone_number} to database: {e}")
                return {
                    'status': 'error',
                    'phone': phone_number,
                    'error': f'Database error: {str(e)}'
                }
            finally:
                await client.disconnect()
            
        except Exception as e:
            logger.error(f"Unexpected error adding account {phone_number}: {e}")
            return {
                'status': 'error', 
                'phone': phone_number, 
                'error': str(e)
            }
    
    async def resend_code(self, phone_number):
        """Resend verification code"""
        try:
            # Clean up old attempt
            if phone_number in self.phone_code_hashes:
                del self.phone_code_hashes[phone_number]
            if phone_number in self.login_attempts:
                del self.login_attempts[phone_number]
            
            # Request new code
            session_path = os.path.join(SESSIONS_DIR, phone_number.replace('+', ''))
            client = TelegramClient(session_path, API_ID, API_HASH)
            await client.connect()
            
            result = await client.send_code_request(phone_number)
            
            # Store new phone_code_hash
            self.phone_code_hashes[phone_number] = result.phone_code_hash
            self.login_attempts[phone_number] = {
                'timestamp': time.time(),
                'phone_code_hash': result.phone_code_hash
            }
            
            await client.disconnect()
            
            return {
                'status': 'code_sent',
                'phone': phone_number,
                'phone_code_hash': result.phone_code_hash,
                'message': 'New verification code sent.'
            }
            
        except Exception as e:
            logger.error(f"Error resending code to {phone_number}: {e}")
            return {
                'status': 'error',
                'phone': phone_number,
                'error': str(e)
            }
    
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