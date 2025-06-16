import os
from dotenv import load_dotenv
from pathlib import Path

# Get the absolute path to the .env file
env_path = Path(__file__).parent / '.env'

# Load environment variables from .env file
load_dotenv(dotenv_path=env_path)

# API Keys
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable not set")

# SEC API Configuration
SEC_EMAIL = os.getenv('SEC_EMAIL')
if not SEC_EMAIL:
    raise ValueError("SEC_EMAIL environment variable not set")

SEC_USER_AGENT = f'{SEC_EMAIL} Python/3.9 SEC EDGAR API'

# Application Configuration
DEBUG = True
PORT = 8080
HOST = '0.0.0.0'

# File Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')
ANALYSIS_DIR = os.path.join(BASE_DIR, 'analysis')

# Create necessary directories
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(ANALYSIS_DIR, exist_ok=True) 