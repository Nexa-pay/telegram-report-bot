import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id]
REPORT_CHANNEL_ID = os.getenv('REPORT_CHANNEL_ID')  # Channel where reports will be sent

# MongoDB Configuration (Optional - for storing reports)
MONGODB_URI = os.getenv('MONGODB_URI', '')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'telegram_reports')

# Bot Settings
MAX_REPORT_LENGTH = 1000
REPORT_COOLDOWN = 60  # Seconds between reports from same user