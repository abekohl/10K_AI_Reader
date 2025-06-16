import os
import json
import logging
import time
import traceback
import re
import random
import tempfile
import shutil
from typing import Optional, Tuple, List, Dict, Any
from bs4 import BeautifulSoup
import openai
from download_10k import SP500Downloader

class TenKAnalyzer:
    def __init__(self, downloader: SP500Downloader, base_dir: str = "downloads"):
        self.downloader = downloader
        self.base_dir = base_dir
        self.output_dir = "analysis"
        self.deployment_name = "gpt-4"
        self.rate_limit_delay = 1  # seconds between API calls
        self.last_api_call = 0
        
        # Create output directory if it doesn't exist
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        self.setup_logging()
        self.setup_openai()

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
    def setup_openai(self):
        openai.api_key = os.getenv('OPENAI_API_KEY')
        if not openai.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")

    def clean_html_content(self, html_content: str) -> str:
        """Clean and extract text content from HTML."""
        try:
            self.logger.info("Starting HTML content cleaning")
            
            if not html_content:
                self.logger.warning("Empty HTML content received")
                return ""
                
            self.logger.info(f"Original content length: {len(html_content)}")
            
            # Parse HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text content
            text = soup.get_text()
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            # Remove excessive whitespace
            text = re.sub(r'\s+', ' ', text)
            
            # Remove empty lines
            text = '\n'.join(line for line in text.splitlines() if line.strip())
            
            self.logger.info(f"Cleaned HTML content. Length: {len(text)}")
            
            if not text:
                self.logger.warning("No text content extracted after cleaning")
                return ""
                
            return text
            
        except Exception as e:
            self.logger.error(f"Error cleaning HTML content: {str(e)}")
            self.logger.error(traceback.format_exc())
            return ""

    def get_filing_year(self, filename: str) -> Optional[int]:
        """Extract the filing year from the filename."""
        try:
            # First try to get year from filename
            year_match = re.search(r'20\d{2}', filename)
            if year_match:
                return int(year_match.group())
            return None
        except Exception:
            return None

    def find_company_path(self, ticker: str) -> Optional[str]:
        """Find the company directory path for a given ticker."""
        try:
            # Look through all sector directories
            for sector in os.listdir(self.base_dir):
                sector_path = os.path.join(self.base_dir, sector)
                if os.path.isdir(sector_path):
                    # Look for files matching the ticker directly in the sector directory
                    for file in os.listdir(sector_path):
                        if file.startswith(f"{ticker}_") and (file.endswith('.html') or file.endswith('_10K_raw.html')):
                                    return sector_path
            return None
        except Exception as e:
            print(f"Error finding company path for {ticker}: {str(e)}")
            return None

    def get_latest_filing(self, company_path: str, ticker: str) -> Optional[Tuple[str, str]]:
        """Get the latest 10-K filing for a company."""
        try:
            # Look for files with .html suffix
            filings = []
            for file in os.listdir(company_path):
                if file.startswith(f"{ticker}_") and (file.endswith('.html') or file.endswith('_10K_raw.html')):
                    # Extract date from filename
                    date_str = file.split('_')[1].split('.')[0]
                    filings.append((date_str, file))
            
            if not filings:
                print(f"No valid 10-K files found for {ticker}")
                return None

            # Sort by date and get the latest
            latest = sorted(filings, reverse=True)[0]
            print(f"Found latest filing: {latest[1]}")
            
            # Read the file content
            with open(os.path.join(company_path, latest[1]), 'r', encoding='utf-8') as f:
                content = f.read()
            
            return latest[0], content
        except Exception as e:
            print(f"Error getting latest filing for {ticker}: {str(e)}")
            return None

    def respect_rate_limit(self):
        """Ensure we don't exceed rate limits."""
        elapsed = time.time() - self.last_api_call
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_api_call = time.time()

    def analyze_filing(self, filing_path: str) -> str:
        """Analyze a single 10-K filing and return cleaned content."""
        try:
            with open(filing_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Clean the HTML content
            cleaned_content = self.clean_html_content(content)
            return cleaned_content
            
        except Exception as e:
            self.logger.error(f"Error analyzing filing {filing_path}: {str(e)}")
            return ""

    def analyze_multiple_years(self, ticker: str, years: int = 5) -> Dict:
        """Analyze multiple years of 10-K filings for a company."""
        try:
            self.logger.info(f"Starting analysis for {ticker}")
            
            # Get company info
            company_info = self.downloader.get_company_info(ticker)
            if not company_info:
                self.logger.error(f"Could not find company info for {ticker}")
                return {'error': f'Company {ticker} not found in S&P 500'}
            
            # Get filings
            filings = self.downloader.get_company_filings(company_info['cik'], years)
            if not filings:
                self.logger.error(f"No filings found for {ticker}")
                return {'error': f'No filings found for {ticker}'}
            
            analyses = []
            for filing in filings:
                # Download the filing
                self.logger.info(f"Downloading filing for {ticker} on {filing['date']}")
                filing_path = self.downloader.download_filing(
                    filing=filing,
                    sector=company_info['sector'],
                    ticker=ticker
                )
                if not filing_path:
                    self.logger.error(f"Failed to download filing for {ticker} on {filing['date']}")
                    continue
                self.logger.info(f"Downloaded filing to {filing_path}")
                
                # Read and analyze the filing
                with open(filing_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if not content:
                    self.logger.error(f"Empty filing content for {ticker} on {filing['date']}")
                    continue
                
                # Clean the content
                cleaned_content = self.clean_html_content(content)
                if not cleaned_content:
                    self.logger.error(f"Failed to clean content for {ticker} on {filing['date']}")
                    continue
                
                self.logger.info(f"Content length before cleaning: {len(content)}")
                self.logger.info(f"Content length after cleaning: {len(cleaned_content)}")
                self.logger.info(f"First 500 characters of cleaned content: {cleaned_content[:500]}")
                
                # Extract financial metrics
                metrics = self.extract_financial_metrics(cleaned_content)
                
                # Get filing year from the filing date
                filing_year = filing['date'].split('-')[0]
                
                # Generate detailed summary
                summary = self.generate_detailed_summary(cleaned_content, metrics, filing_year)
                
                analyses.append({
                    'year': filing_year,
                    'filing_date': filing['date'],
                    'metrics': metrics,
                    'summary': summary
                })
            
            # Return the analysis results
            return {
                'ticker': ticker,
                'company_name': company_info['name'],
                'sector': company_info['sector'],
                'analyses': analyses
            }
            
        except Exception as e:
            self.logger.error(f"Error in analyze_multiple_years: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {'error': f'Error analyzing {ticker}: {str(e)}'}

    def extract_financial_metrics(self, content: str) -> Dict:
        """Extract key financial metrics from the content."""
        try:
            metrics = {}
            self.logger.info("Starting financial metrics extraction")

            # Revenue
            revenue_patterns = [
                r'(?:revenue|sales|net sales).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)',
                r'(?:total revenue|total sales).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)',
                r'(?:consolidated revenue|consolidated sales).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)'
            ]
            for pattern in revenue_patterns:
                revenue_match = re.search(pattern, content, re.IGNORECASE)
                if revenue_match:
                    metrics['revenue'] = self._parse_currency(revenue_match.group(1))
                    self.logger.info(f"Found revenue: {metrics['revenue']}")
                    break

            # Gross Profit and Margin
            gross_profit_patterns = [
                r'(?:gross profit).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)',
                r'(?:gross income).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)',
                r'(?:gross earnings).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)'
            ]
            for pattern in gross_profit_patterns:
                gross_profit_match = re.search(pattern, content, re.IGNORECASE)
                if gross_profit_match:
                    metrics['gross_profit'] = self._parse_currency(gross_profit_match.group(1))
                    if metrics.get('revenue'):
                        metrics['gross_margin'] = metrics['gross_profit'] / metrics['revenue']
                        self.logger.info(f"Found gross profit: {metrics['gross_profit']} and margin: {metrics['gross_margin']}")
                    break

            # Operating Income (EBIT)
            operating_income_patterns = [
                r'(?:operating income|operating profit|EBIT).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)',
                r'(?:income from operations).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)',
                r'(?:operating earnings).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)'
            ]
            for pattern in operating_income_patterns:
                operating_income_match = re.search(pattern, content, re.IGNORECASE)
                if operating_income_match:
                    metrics['operating_income'] = self._parse_currency(operating_income_match.group(1))
                    self.logger.info(f"Found operating income: {metrics['operating_income']}")
                    break

            # Net Income
            net_income_patterns = [
                r'(?:net income|net earnings|net profit).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)',
                r'(?:net loss).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)',
                r'(?:consolidated net income).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)'
            ]
            for pattern in net_income_patterns:
                net_income_match = re.search(pattern, content, re.IGNORECASE)
                if net_income_match:
                    value = self._parse_currency(net_income_match.group(1))
                    # If it's a loss, make it negative
                    if 'loss' in net_income_match.group(0).lower():
                        value = -value
                    metrics['net_income'] = value
                    self.logger.info(f"Found net income: {metrics['net_income']}")
                    break

            # EPS
            eps_patterns = [
                r'(?:earnings per share|EPS).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)',
                r'(?:basic earnings per share).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)',
                r'(?:diluted earnings per share).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)'
            ]
            for pattern in eps_patterns:
                eps_match = re.search(pattern, content, re.IGNORECASE)
                if eps_match:
                    metrics['eps'] = self._parse_currency(eps_match.group(1))
                    self.logger.info(f"Found EPS: {metrics['eps']}")
                    break

            # Free Cash Flow
            fcf_patterns = [
                r'(?:free cash flow|FCF).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)',
                r'(?:operating cash flow).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)',
                r'(?:net cash provided by operating activities).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)'
            ]
            for pattern in fcf_patterns:
                fcf_match = re.search(pattern, content, re.IGNORECASE)
                if fcf_match:
                    metrics['free_cash_flow'] = self._parse_currency(fcf_match.group(1))
                    self.logger.info(f"Found free cash flow: {metrics['free_cash_flow']}")
                    break

            # Total Assets (for ROA)
            assets_patterns = [
                r'(?:total assets).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)',
                r'(?:consolidated total assets).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)',
                r'(?:total assets at end of period).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)'
            ]
            for pattern in assets_patterns:
                assets_match = re.search(pattern, content, re.IGNORECASE)
                if assets_match:
                    metrics['total_assets'] = self._parse_currency(assets_match.group(1))
                    self.logger.info(f"Found total assets: {metrics['total_assets']}")
                    break

            # Total Equity (for ROE)
            equity_patterns = [
                r'(?:total equity|shareholders equity|stockholders equity).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)',
                r'(?:total stockholders equity).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)',
                r'(?:total shareholders equity).*?(\$?\d+(?:,\d{3})*(?:\.\d+)?)'
            ]
            for pattern in equity_patterns:
                equity_match = re.search(pattern, content, re.IGNORECASE)
                if equity_match:
                    metrics['total_equity'] = self._parse_currency(equity_match.group(1))
                    self.logger.info(f"Found total equity: {metrics['total_equity']}")
                    break

            # Calculate ROE and ROA
            if metrics.get('net_income'):
                if metrics.get('total_equity'):
                    metrics['roe'] = metrics['net_income'] / metrics['total_equity']
                    self.logger.info(f"Calculated ROE: {metrics['roe']}")
                if metrics.get('total_assets'):
                    metrics['roa'] = metrics['net_income'] / metrics['total_assets']
                    self.logger.info(f"Calculated ROA: {metrics['roa']}")

            self.logger.info(f"Extracted {len(metrics)} metrics: {list(metrics.keys())}")
            return metrics

        except Exception as e:
            self.logger.error(f"Error extracting financial metrics: {str(e)}")
            self.logger.error(traceback.format_exc())
            return {}

    def _parse_currency(self, value_str: str) -> float:
        """Parse currency string to float."""
        try:
            # Remove currency symbols and commas
            value_str = value_str.replace('$', '').replace(',', '')
            # Convert to float
            return float(value_str)
        except Exception as e:
            self.logger.error(f"Error parsing currency value: {str(e)}")
            return 0.0

    def generate_detailed_summary(self, content: str, metrics: Dict, year: str = None) -> str:
        """Generate a detailed summary of the filing content with metrics analysis."""
        try:
            self.logger.info(f"Generating summary for year {year}")
            self.logger.info(f"Content length: {len(content)}")
            self.logger.info(f"Number of metrics: {len(metrics)}")
            
            # Respect rate limits
            self.respect_rate_limit()
            
            # Check if OpenAI API key is set
            if not os.getenv('OPENAI_API_KEY'):
                self.logger.error("OpenAI API key not set")
                return "Error: OpenAI API key not configured"
            
            # Prepare the content for analysis
            analysis_prompt = f"""Please provide a comprehensive analysis of the company's performance, focusing on:

1. Business Performance:
   - Revenue growth and trends
   - Gross profit and margin analysis
   - Operating income performance
   - Net income and profitability

2. Financial Health:
   - Cash flow generation and management
   - Return on equity and assets
   - Debt levels and management
   - Working capital efficiency

3. Strategic Initiatives:
   - Key business developments
   - Market position and competitive advantages
   - R&D and innovation efforts
   - Growth opportunities and challenges

4. Risk Factors:
   - Key operational risks
   - Market and competitive risks
   - Regulatory and compliance risks
   - Financial risks

Please provide specific insights and analysis rather than just listing metrics. Focus on the implications of the numbers and their impact on the company's future prospects.

Content:
{content[:4000]}

Key Metrics:
{json.dumps(metrics, indent=2)}"""

            self.logger.info("Sending request to OpenAI API")
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You are a financial analyst providing a detailed analysis of 10-K filings. Focus on key performance indicators and their implications."},
                        {"role": "user", "content": analysis_prompt}
                    ],
                    max_tokens=2000,
                    temperature=0.7
                )
                
                summary = response.choices[0].message.content
                self.logger.info(f"Successfully generated summary of length {len(summary)}")
                return summary
                
            except openai.error.RateLimitError as e:
                self.logger.error(f"OpenAI rate limit exceeded: {str(e)}")
                return "Error: Rate limit exceeded. Please try again later."
            except openai.error.APIError as e:
                self.logger.error(f"OpenAI API error: {str(e)}")
                return "Error: API request failed. Please try again later."
            except Exception as e:
                self.logger.error(f"Unexpected error during OpenAI API call: {str(e)}")
                self.logger.error(traceback.format_exc())
                return "Error: Failed to generate summary. Please try again later."
            
        except Exception as e:
            self.logger.error(f"Error in generate_detailed_summary: {str(e)}")
            self.logger.error(traceback.format_exc())
            return "Error generating detailed summary."

    def analyze_company(self, ticker: str, sector: str) -> List[Dict]:
        """Analyze all available filings for a company."""
        company_dir = os.path.join(self.base_dir, sector, ticker)
        if not os.path.exists(company_dir):
            self.logger.warning(f"No filings found for {ticker} in sector {sector}")
            return []
        
        analyses = []
        for filing_date in os.listdir(company_dir):
            filing_dir = os.path.join(company_dir, filing_date)
            if os.path.isdir(filing_dir):
                filing_path = os.path.join(filing_dir, f"{ticker}_{filing_date}_10K.html")
                if os.path.exists(filing_path):
                    analysis = self.analyze_filing(filing_path)
                    if analysis:
                        analyses.append({
                            'ticker': ticker,
                            'date': filing_date,
                            'content': analysis
                        })
        
        return self.analyze_multiple_years(ticker)

    def analyze_all_companies(self, companies: List[Dict]) -> Dict[str, List[Dict]]:
        """Analyze filings for all companies."""
        results = {}
        
        for company in companies:
            ticker = company['symbol']
            sector = company['sector']
            
            self.logger.info(f"Analyzing filings for {ticker} in sector {sector}")
            analyses = self.analyze_company(ticker, sector)
            
            if analyses:
                results[ticker] = analyses
            else:
                self.logger.warning(f"No analyses generated for {ticker}")
        
        return results

    def analyze_specific_ticker(self, ticker: str) -> None:
        """Analyze a specific ticker's latest 10-K filing."""
        try:
            print(f"\nLooking for {ticker} filings...")
            # Find the company directory
            company_path = self.find_company_path(ticker)
            if not company_path:
                print(f"Could not find directory for ticker {ticker}")
                return

            print(f"Found company directory: {company_path}")
            # Get the latest filing
            latest_filing = self.get_latest_filing(company_path, ticker)
            if not latest_filing:
                print(f"Could not find any 10-K filings for {ticker}")
                return

            filing_year, filing_content = latest_filing
            print(f"Found latest filing from {filing_year}")

            # Analyze the filing
            analysis = self.analyze_filing(filing_content)
            if analysis:
                # Save the analysis
                output_file = os.path.join(self.output_dir, f"{ticker}_{filing_year}_analysis.txt")
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(analysis)
                print(f"\nAnalysis completed for {ticker}. Results saved to {output_file}")
            else:
                print(f"Failed to analyze {ticker}")

        except Exception as e:
            print(f"Error analyzing {ticker}: {str(e)}")
            return

    def analyze_all_companies(self) -> None:
        """Analyze all companies in the downloads directory."""
        logging.info("Starting analysis of all companies...")
        
        # Get all sector directories
        for sector in os.listdir(self.base_dir):
            sector_path = os.path.join(self.base_dir, sector)
            if not os.path.isdir(sector_path):
                continue
            
            logging.info(f"\nProcessing sector: {sector}")
            
            # Get all files in the sector directory
            files = os.listdir(sector_path)
            # Extract unique tickers from filenames
            tickers = set()
            for file in files:
                if file.endswith('.html') or file.endswith('_10K_raw.html'):
                    ticker = file.split('_')[0]
                    tickers.add(ticker)
            
            # Process each unique ticker
            for ticker in sorted(tickers):
                try:
                    logging.info(f"\nAnalyzing {ticker}...")
                    self.analyze_specific_ticker(ticker)
                    # Add a small delay between companies to respect rate limits
                    time.sleep(self.rate_limit_delay)
                except Exception as e:
                    logging.error(f"Error processing {ticker}: {str(e)}")
                    traceback.print_exc()
                    continue
        
        logging.info("Completed analysis of all companies.")

    def calculate_trends(self, analyses: List[Dict]) -> Dict:
        """Calculate trends for key metrics across years."""
        trends = {}
        years = sorted([a['year'] for a in analyses])
        if len(years) < 2:
            return trends
        for category in ['income_statement', 'balance_sheet', 'cash_flow', 'ratios']:
            trends[category] = {}
            metrics = set()
            for analysis in analyses:
                metrics.update(analysis['metrics'].get(category, {}).keys())
            for metric in metrics:
                values = []
                for year in years:
                    for analysis in analyses:
                        if analysis['year'] == year:
                            value = analysis['metrics'].get(category, {}).get(metric)
                            if value is not None:
                                values.append(value)
                if len(values) >= 2:
                    growth_rates = []
                    for i in range(1, len(values)):
                        if values[i-1] != 0:
                            growth_rate = (values[i] - values[i-1]) / abs(values[i-1])
                            growth_rates.append(growth_rate)
                    if growth_rates:
                        avg_growth = sum(growth_rates) / len(growth_rates)
                        trends[category][metric] = {
                            'average_growth': avg_growth,
                            'latest_value': values[-1],
                            'year_ago_value': values[0],
                            'growth_rate': (values[-1] - values[0]) / abs(values[0]) if values[0] != 0 else None
                        }
        return trends

def main():
    analyzer = TenKAnalyzer()
    analyzer.analyze_all_companies()

if __name__ == "__main__":
    main() 