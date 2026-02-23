import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
OWNER_ID = int(os.getenv('OWNER_ID', '0'))
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///bot.db')

# Report Categories
REPORT_CATEGORIES = {
    'child_abuse': 'Child abuse',
    'violence': 'Violence',
    'illegal_goods': 'Illegal goods and services',
    'illegal_adult': 'Illegal adult content',
    'personal_data': 'Personal data sharing',
    'scam_fraud': 'Scam or fraud',
    'copyright': 'Copyright infringement',
    'spam': 'Spam',
    'pornography': 'Pornography',
    'illegal_sexual': 'Illegal sexual services',
    'animal_abuse': 'Animal abuse',
    'non_consensual': 'Non-consensual sexual imagery',
    'other_illegal': 'Other illegal sexual content'
}

# Report Templates
REPORT_TEMPLATES = {
    'child_abuse': "This channel/group is sharing content involving child abuse and exploitation.",
    'violence': "This channel promotes and shares violent content and hate speech.",
    'illegal_goods': "This group is involved in trading illegal goods and services.",
    'illegal_adult': "This channel is sharing illegal adult content without proper age verification.",
    'personal_data': "This group is sharing personal data and private information without consent.",
    'scam_fraud': "This is a scam/fraud channel attempting to deceive users.",
    'copyright': "This channel is sharing copyrighted content without authorization.",
    'spam': "This channel is spreading spam and unsolicited messages.",
    'pornography': "This channel is sharing pornographic content without age restrictions.",
    'illegal_sexual': "This group is promoting illegal sexual services.",
    'animal_abuse': "This channel contains content showing animal abuse.",
    'non_consensual': "This group shares non-consensual intimate imagery.",
    'other_illegal': "This channel contains illegal sexual content violating Telegram's terms."
}

# Token System
DEFAULT_TOKENS = 10
REPORT_COST = 1