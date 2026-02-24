import asyncio
from datetime import datetime, timezone  # Fixed: Added timezone import
from database import Session, Report, TelegramAccount, User
from account_manager import AccountManager
import json
import logging

logger = logging.getLogger(__name__)

class Reporter:
    def __init__(self):
        self.account_manager = AccountManager()
        self.session = Session()
    
    async def execute_report(self, report_id):
        """Execute a report using multiple accounts"""
        try:
            report = self.session.query(Report).filter_by(id=report_id).first()
            if not report or report.status != 'pending':
                return
            
            report.status = 'in_progress'
            self.session.commit()
            
            # Get available accounts
            accounts = await self.account_manager.get_available_accounts(limit=5)
            
            if not accounts:
                logger.warning(f"No available accounts to execute report {report_id}")
                report.status = 'failed'
                # Fixed: Replaced deprecated utcnow()
                report.completed_at = datetime.now(timezone.utc)
                self.session.commit()
                return
            
            results = []
            accounts_used = []
            
            for account in accounts:
                account.status = 'busy'
                self.session.commit()
                
                result = await self.account_manager.report_target(
                    account,
                    report.target_username or report.target_id,
                    report.category,
                    report.custom_text
                )
                
                results.append(result)
                accounts_used.append(account.phone_number)
                
                if result['status'] == 'success':
                    await asyncio.sleep(2)  # Rate limiting
                else:
                    logger.warning(f"Report failed for account {account.phone_number}: {result.get('reason', 'Unknown reason')}")
            
            # Update report status
            success_count = sum(1 for r in results if r['status'] == 'success')
            report.status = 'completed' if success_count > 0 else 'failed'
            # Fixed: Replaced deprecated utcnow()
            report.completed_at = datetime.now(timezone.utc)
            report.accounts_used = json.dumps(accounts_used)
            self.session.commit()
            
            logger.info(f"Report {report_id} completed with {success_count}/{len(accounts)} successful reports")
            
            # Deduct tokens from user (only if at least one report succeeded)
            if success_count > 0:
                user = self.session.query(User).filter_by(user_id=report.reported_by).first()
                if user and user.role != 'owner':
                    # Only deduct one token per report target, not per account used
                    user.tokens -= 1
                    logger.info(f"Deducted 1 token from user {user.user_id}. New balance: {user.tokens}")
                    self.session.commit()
            
        except Exception as e:
            logger.error(f"Error executing report {report_id}: {e}")
            self.session.rollback()
    
    async def bulk_report(self, targets, category, custom_text, user_id):
        """Report multiple targets"""
        try:
            user = self.session.query(User).filter_by(user_id=user_id).first()
            if not user:
                return {'status': 'error', 'message': 'User not found'}
            
            required_tokens = len(targets)
            if user.role != 'owner' and user.tokens < required_tokens:
                return {
                    'status': 'error', 
                    'message': f'Insufficient tokens. Required: {required_tokens}, Available: {user.tokens}'
                }
            
            report_ids = []
            successful_reports = 0
            failed_reports = 0
            
            for target in targets:
                try:
                    report = Report(
                        target_type=target['type'],
                        target_id=target.get('id'),
                        target_username=target.get('username'),
                        category=category,
                        custom_text=custom_text,
                        reported_by=user_id,
                        status='pending'
                    )
                    self.session.add(report)
                    self.session.commit()
                    report_ids.append(report.id)
                    
                    # Execute report
                    await self.execute_report(report.id)
                    
                    # Check if report was successful
                    updated_report = self.session.query(Report).filter_by(id=report.id).first()
                    if updated_report and updated_report.status == 'completed':
                        successful_reports += 1
                    else:
                        failed_reports += 1
                        
                except Exception as e:
                    logger.error(f"Error processing target {target}: {e}")
                    failed_reports += 1
            
            return {
                'status': 'success',
                'report_ids': report_ids,
                'summary': {
                    'total': len(targets),
                    'successful': successful_reports,
                    'failed': failed_reports
                }
            }
            
        except Exception as e:
            logger.error(f"Error in bulk_report: {e}")
            self.session.rollback()
            return {
                'status': 'error',
                'message': str(e)
            }