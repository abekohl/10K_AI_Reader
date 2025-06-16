import requests
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_sec_connection():
    # Test URL (company tickers)
    url = "https://www.sec.gov/files/company_tickers.json"
    
    # Headers required by SEC
    headers = {
        'User-Agent': f'{os.getenv("SEC_EMAIL")} Python/3.9 SEC EDGAR API',
        'Accept-Encoding': 'gzip, deflate',
        'Host': 'www.sec.gov',
        'Accept': 'application/json'
    }
    
    logger.info("Testing SEC API connection...")
    logger.info(f"Using headers: {headers}")
    
    try:
        response = requests.get(url, headers=headers)
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response headers: {response.headers}")
        
        if response.status_code == 200:
            logger.info("Successfully connected to SEC API!")
            logger.info(f"Response content preview: {response.text[:500]}")
        else:
            logger.error(f"Failed to connect. Status code: {response.status_code}")
            logger.error(f"Response content: {response.text}")
            
    except Exception as e:
        logger.error(f"Error connecting to SEC API: {str(e)}")

if __name__ == "__main__":
    test_sec_connection() 