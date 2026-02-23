import asyncio
from datetime import datetime
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
        report = self.session.query(Report).filter_by(id=report_id).first()
        if not report or report.status != 'pending':
            return
        
        report.status = 'in_progress'
        self.session.commit()
        
        # Get available accounts
        accounts = await self.account_manager.get_available_accounts(limit=5)
        
        if not accounts:
            report.status = 'failed'
            report.completed_at = datetime.utcnow()
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
        
        # Update report status
        report.status = 'completed' if any(r['status'] == 'success' for r in results) else 'failed'
        report.completed_at = datetime.utcnow()
        report.accounts_used = json.dumps(accounts_used)
        self.session.commit()
        
        # Deduct tokens from user
        user = self.session.query(User).filter_by(user_id=report.reported_by).first()
        if user and user.role != 'owner':
            user.tokens -= 1
            self.session.commit()
    
    async def bulk_report(self, targets, category, custom_text, user_id):
        """Report multiple targets"""
        user = self.session.query(User).filter_by(user_id=user_id).first()
        if not user:
            return {'status': 'error', 'message': 'User not found'}
        
        if user.role != 'owner' and user.tokens < len(targets):
            return {'status': 'error', 'message': 'Insufficient tokens'}
        
        report_ids = []
        for target in targets:
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
        
        return {'status': 'success', 'report_ids': report_ids}