import os
import logging
import time
import traceback
from typing import Optional, Dict, List, Tuple, Any
import re
from bs4 import BeautifulSoup
import pandas as pd
import requests
from datetime import datetime, timedelta
import json
import gzip
import random
from rate_limiter import sec_rate_limiter

class SP500Downloader:
    def __init__(self, base_dir: str = "downloads"):
        self.base_dir = base_dir
        self.edgar_base_url = "https://www.sec.gov/Archives/edgar/data"
        
        # Debug: Log all environment variables (excluding sensitive values)
        self.logger = logging.getLogger(__name__)
        self.logger.info("Checking environment variables...")
        self.logger.info(f"SEC_EMAIL is set: {'SEC_EMAIL' in os.environ}")
        self.logger.info(f"OPENAI_API_KEY is set: {'OPENAI_API_KEY' in os.environ}")
        
        self.email = os.getenv('SEC_EMAIL')
        if not self.email:
            raise ValueError("SEC_EMAIL environment variable not set")
        self.logger.info(f"Using SEC_EMAIL: {self.email[:3]}...{self.email[-3:]}")  # Only log first/last 3 chars
        
        self.headers = {
            'User-Agent': f'{self.email} Python/3.9 SEC EDGAR API',
            'Accept-Encoding': 'gzip, deflate',
            'Host': 'www.sec.gov',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
        }
        self.max_retries = 5
        self.retry_delay = 5  # Base delay between retries
        self.setup_logging()

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def make_sec_request(self, url: str) -> requests.Response:
        """Make a request to SEC EDGAR with proper rate limiting and retries."""
        for attempt in range(self.max_retries):
            try:
                # Use the rate limiter to ensure we don't exceed 10 requests per second
                sec_rate_limiter.wait_for_token()
                
                self.logger.info(f"Making request to {url} (attempt {attempt + 1}/{self.max_retries})")
                
                # Update headers for each request
                headers = {
                    'User-Agent': f'{self.email} Python/3.9 SEC EDGAR API',
                    'Accept-Encoding': 'gzip, deflate',
                    'Host': 'www.sec.gov',
                    'Accept': 'application/json',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Connection': 'keep-alive',
                    'Cache-Control': 'max-age=0',
                }
                
                response = requests.get(url, headers=headers)
                
                # Log response details
                self.logger.info(f"Response status: {response.status_code}")
                self.logger.info(f"Response headers: {dict(response.headers)}")
                
                # Check for rate limiting
                if response.status_code in [429, 403]:  # 429 is Too Many Requests, 403 is Forbidden (often used for rate limiting)
                    retry_after = response.headers.get('Retry-After')
                    if retry_after:
                        wait_time = int(retry_after)
                    else:
                        # Exponential backoff with jitter
                        wait_time = min(30, self.retry_delay * (2 ** attempt) + random.uniform(0, 1))
                    
                    self.logger.warning(f"Rate limited. Waiting {wait_time:.2f} seconds...")
                    time.sleep(wait_time)
                    continue
                
                # Check for other error status codes
                if response.status_code != 200:
                    self.logger.error(f"Request failed with status {response.status_code}")
                    self.logger.error(f"Response content: {response.text[:1000]}")  # Log first 1000 chars
                    if attempt < self.max_retries - 1:
                        # Exponential backoff with jitter
                        wait_time = min(30, self.retry_delay * (2 ** attempt) + random.uniform(0, 1))
                        self.logger.warning(f"Retrying in {wait_time:.2f} seconds...")
                        time.sleep(wait_time)
                        continue
                    else:
                        response.raise_for_status()
                
                return response
                
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Request error: {str(e)}")
                if attempt < self.max_retries - 1:
                    # Exponential backoff with jitter
                    wait_time = min(30, self.retry_delay * (2 ** attempt) + random.uniform(0, 1))
                    self.logger.warning(f"Retrying in {wait_time:.2f} seconds...")
                    time.sleep(wait_time)
                    continue
                raise

    def get_sp500_companies(self) -> pd.DataFrame:
        """Get S&P 500 companies data, downloading it if it doesn't exist."""
        try:
            if not os.path.exists('sp500_companies.csv'):
                self.logger.info("Downloading S&P 500 companies data...")
                url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
                response = requests.get(url)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find the first table
                table = soup.find('table', {'class': 'wikitable'})
                
                # Extract data
                data = []
                for row in table.find_all('tr')[1:]:  # Skip header row
                    cols = row.find_all('td')
                    if len(cols) >= 8:
                        symbol = cols[0].text.strip()
                        name = cols[1].text.strip()
                        sector = cols[3].text.strip()
                        cik = cols[7].text.strip()
                        data.append({
                            'symbol': symbol,
                            'name': name,
                            'sector': sector,
                            'cik': cik
                        })
                
                # Create DataFrame and save to CSV
                df = pd.DataFrame(data)
                df.to_csv('sp500_companies.csv', index=False)
                self.logger.info(f"Downloaded {len(df)} S&P 500 companies")
                return df
            else:
                df = pd.read_csv('sp500_companies.csv')
                return df
        except Exception as e:
            self.logger.error(f"Error getting S&P 500 companies: {e}")
            return pd.DataFrame()

    def get_company_cik(self, ticker: str) -> Optional[str]:
        try:
            ticker = ticker.upper()  # Normalize ticker to uppercase
            self.logger.info(f"Looking up CIK for ticker: {ticker}")
            
            # Special case for Apple
            if ticker == 'AAPL':
                return '0000320193'  # Apple's CIK number
                
            # Lazy load the S&P 500 companies data
            df = self.get_sp500_companies()
            company = df[df['symbol'].str.upper() == ticker]
            if not company.empty:
                cik = str(company['cik'].iloc[0]).zfill(10)
                self.logger.info(f"Found CIK for {ticker}: {cik}")
                return cik
            self.logger.warning(f"CIK not found for ticker: {ticker}")
            return None
        except Exception as e:
            self.logger.error(f"Error getting CIK for {ticker}: {e}")
            return None

    def get_master_idx_urls(self, years: int = 5) -> List[str]:
        """Get URLs for master index files for the last N years."""
        urls = []
        now = datetime.now()
        current_year = now.year
        current_qtr = (now.month - 1) // 3 + 1
        start_year = current_year - 4  # 5 years including current year
        self.logger.info(f"Getting master index URLs from {start_year} to {current_year}")
        for year in range(current_year, start_year - 1, -1):
            max_qtr = current_qtr if year == current_year else 4
            for qtr in range(max_qtr, 0, -1):
                url = f"https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{qtr}/master.idx"
                urls.append(url)
                self.logger.info(f"Added master index URL for {year} Q{qtr}: {url}")
        self.logger.info(f"Total master index URLs: {len(urls)}")
        return urls

    def download_master_idx(self, url: str) -> List[Dict]:
        """Download and parse master index file."""
        self.logger.info(f"Downloading master index from: {url}")
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            lines = response.text.splitlines()
            data_lines = lines[11:]
            filings = []
            for line in data_lines:
                try:
                    parts = line.strip().split('|')
                    if len(parts) != 5:
                        continue
                    cik, company_name, form_type, date_filed, filename = parts
                    filings.append({
                        'cik': cik,
                        'company_name': company_name,
                        'form_type': form_type,
                        'date_filed': date_filed,
                        'filename': filename
                    })
                except Exception as e:
                    self.logger.warning(f"Error parsing line in master index: {str(e)}")
                    continue
            return filings
        except Exception as e:
            self.logger.error(f"Error downloading master index from {url}: {str(e)}")
            return []

    def get_company_filings(self, cik: str, years: int = 5) -> List[Dict]:
        """Get the latest 10-K filings for a company."""
        try:
            self.logger.info(f"Getting 10-K filings for CIK {cik}")
            cik = cik.zfill(10)
            master_idx_urls = self.get_master_idx_urls(years)
            self.logger.info(f"Got {len(master_idx_urls)} master index URLs")
            all_filings = []
            for url in master_idx_urls:
                filings = self.download_master_idx(url)
                self.logger.info(f"Downloaded {len(filings)} filings from {url}")
                all_filings.extend(filings)
            self.logger.info(f"Total filings found: {len(all_filings)}")
            company_filings = [
                filing for filing in all_filings
                if filing['cik'].zfill(10) == cik and filing['form_type'] == '10-K'
            ]
            if not company_filings:
                self.logger.error(f"No 10-K filings found for CIK {cik}")
                return []
            company_filings.sort(key=lambda x: x['date_filed'], reverse=True)
            result = []
            for filing in company_filings[:years]:
                result.append({
                    'date': filing['date_filed'],
                    'url': f"https://www.sec.gov/Archives/{filing['filename']}",
                    'accession_number': filing['filename'].split('/')[-1].replace('.txt', '')
                })
            self.logger.info(f"Returning {len(result)} filings for CIK {cik}")
            return result
        except Exception as e:
            self.logger.error(f"Error getting company filings: {str(e)}")
            self.logger.error(traceback.format_exc())
            return []

    def download_filing(self, filing: Dict[str, str], sector: str, ticker: str) -> str:
        """Download a single filing and save it to the appropriate directory."""
        try:
            filing_date = datetime.strptime(filing['date'], '%Y-%m-%d')
            year = filing_date.year
            sector_dir = os.path.join(self.base_dir, sector)
            ticker_dir = os.path.join(sector_dir, ticker)
            year_dir = os.path.join(ticker_dir, str(year))
            os.makedirs(year_dir, exist_ok=True)
            self.logger.info(f"Created directory structure: {year_dir}")
            filing_url = filing['url']
            self.logger.info(f"Downloading filing from: {filing_url}")
            response = self.make_sec_request(filing_url)
            if response.status_code != 200:
                self.logger.error(f"Failed to download filing: {response.status_code}")
                return ""
            file_path = os.path.join(year_dir, f"{ticker}_{filing['date']}.txt")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(response.text)
            self.logger.info(f"Downloaded filing to {file_path}")
            return file_path
        except Exception as e:
            self.logger.error(f"Error downloading filing: {str(e)}")
            return ""

    def get_downloaded_filings(self, ticker: str, sector: str) -> List[Dict[str, Any]]:
        """Get list of downloaded filings for a ticker."""
        try:
            # Get the CIK number first
            cik = self.get_company_cik(ticker)
            if not cik:
                self.logger.error(f"Could not find CIK for {ticker}")
                return []

            # Get all filings for the ticker
            filings = self.get_company_filings(cik)
            if not filings:
                self.logger.warning(f"No filings found for {ticker}")
                return []
            
            # Download any missing filings
            downloaded_filings = []
            for filing in filings:
                if self.download_filing(filing, sector, ticker):
                    # Read the downloaded filing
                    year = filing['date'][:4]
                    filepath = os.path.join(self.base_dir, sector, ticker, year, f"{ticker}_{filing['date']}.txt")
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            downloaded_filings.append({
                                'date': filing['date'],
                                'content': content,
                                'accessionNumber': filing['accession_number']
                            })
                    except Exception as e:
                        self.logger.error(f"Error reading downloaded filing {filepath}: {str(e)}")
                        continue

            self.logger.info(f"Successfully downloaded {len(downloaded_filings)} filings for {ticker}")
            return downloaded_filings
            
        except Exception as e:
            self.logger.error(f"Error getting downloaded filings for {ticker}: {str(e)}")
            return []

    def _get_filings_from_dir(self, directory: str, ticker: str) -> List[Dict]:
        """Helper method to get filings from a specific directory."""
        filings = []
        try:
            ticker = ticker.upper()  # Normalize ticker to uppercase
            for file in os.listdir(directory):
                # Case-insensitive file matching
                if file.upper().startswith(f"{ticker}_") and (file.lower().endswith('.html') or file.lower().endswith('_10k_raw.html')):
                    self.logger.info(f"Found filing: {file}")
                    file_path = os.path.join(directory, file)
                    
                    # Extract date from filename (support YYYYMMDD and YYYY-MM-DD)
                    date_match = re.search(r'(\d{8}|\d{4}-\d{2}-\d{2})', file)
                    if not date_match:
                        self.logger.warning(f"Could not extract date from filename: {file}")
                        continue
                    
                    filing_date = date_match.group(1).replace('-', '')  # Normalize to YYYYMMDD
                    self.logger.info(f"Extracted date {filing_date} from filename {file}")
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            self.logger.info(f"Successfully read file {file} ({len(content)} bytes)")
                            filings.append({
                                'date': filing_date,
                                'content': content
                            })
                    except Exception as e:
                        self.logger.error(f"Error reading file {file}: {str(e)}")
                        continue
            
            return filings
        except Exception as e:
            self.logger.error(f"Error reading directory {directory}: {str(e)}")
            return []

    def extract_financial_metrics(self, filing_content: str) -> Dict:
        try:
            soup = BeautifulSoup(filing_content, 'html.parser')
            metrics = {
                'income_statement': {},
                'balance_sheet': {},
                'cash_flow': {}
            }
            return metrics
        except Exception as e:
            logging.error(f"Error extracting financial metrics: {e}")
            return {}

    def calculate_financial_ratios(self, income_stmt: dict, balance_sheet: dict, cash_flow: dict) -> dict:
        ratios = {}
        try:
            if income_stmt.get('net_income') and balance_sheet.get('total_assets'):
                ratios['roe'] = income_stmt['net_income'] / balance_sheet['total_assets']
            if income_stmt.get('net_income') and balance_sheet.get('shareholders_equity'):
                ratios['roe'] = income_stmt['net_income'] / balance_sheet['shareholders_equity']
            if income_stmt.get('operating_income') and balance_sheet.get('total_assets'):
                ratios['roa'] = income_stmt['operating_income'] / balance_sheet['total_assets']
            
            if balance_sheet.get('current_assets') and balance_sheet.get('current_liabilities'):
                ratios['current_ratio'] = balance_sheet['current_assets'] / balance_sheet['current_liabilities']
            if balance_sheet.get('cash') and balance_sheet.get('current_liabilities'):
                ratios['quick_ratio'] = balance_sheet['cash'] / balance_sheet['current_liabilities']
            
            if income_stmt.get('revenue') and balance_sheet.get('total_assets'):
                ratios['asset_turnover'] = income_stmt['revenue'] / balance_sheet['total_assets']
            if income_stmt.get('revenue') and balance_sheet.get('inventory'):
                ratios['inventory_turnover'] = income_stmt['revenue'] / balance_sheet['inventory']
            
            if balance_sheet.get('total_debt') and balance_sheet.get('total_assets'):
                ratios['debt_to_assets'] = balance_sheet['total_debt'] / balance_sheet['total_assets']
            if balance_sheet.get('total_debt') and balance_sheet.get('shareholders_equity'):
                ratios['debt_to_equity'] = balance_sheet['total_debt'] / balance_sheet['shareholders_equity']
            
            return ratios
        except Exception as e:
            self.logger.error(f"Error calculating financial ratios: {str(e)}")
            return {} 

    def get_company_info(self, ticker: str) -> Optional[Dict]:
        """Get company information from S&P 500 data."""
        try:
            ticker = ticker.upper()  # Normalize ticker to uppercase
            companies = self.get_sp500_companies()
            company = companies[companies['symbol'].str.upper() == ticker]
            if not company.empty:
                return {
                    'name': company['name'].iloc[0],
                    'sector': company['sector'].iloc[0],
                    'cik': str(company['cik'].iloc[0]).zfill(10)
                }
            return None
        except Exception as e:
            self.logger.error(f"Error getting company info: {str(e)}")
            return None 