from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from download_10k import SP500Downloader
from analyze_10k import TenKAnalyzer
import os
import logging
import traceback
import json
from typing import Dict, List, Optional
import socket
from config import *
import time
import concurrent.futures
import redis
from dotenv import load_dotenv
import pandas as pd
import requests
import random
from rate_limiter import sec_rate_limiter
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Debug: Log environment variable status
logger.info("Checking environment variables in app.py...")
logger.info(f"SEC_EMAIL is set: {'SEC_EMAIL' in os.environ}")
logger.info(f"OPENAI_API_KEY is set: {'OPENAI_API_KEY' in os.environ}")

logger.info("Initializing Flask app...")
app = Flask(__name__)
CORS(app)

logger.info("Initializing downloader and analyzer...")
# Initialize downloader and analyzer
downloader = SP500Downloader()
analyzer = TenKAnalyzer(downloader)

# Redis configuration with environment variables and defaults
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', '')

logger.info("Connecting to Redis...")
# Initialize Redis cache with error handling
try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True  # This ensures we get strings back instead of bytes
    )
    # Test the connection
    redis_client.ping()
    logger.info("Successfully connected to Redis")
except (redis.ConnectionError, Exception) as e:
    logger.warning(f"Redis connection failed: {str(e)}")
    logger.info("Using in-memory cache instead")
    redis_client = {}  # Fallback to in-memory cache

def get_cached_analysis(ticker: str, year: str) -> Optional[dict]:
    """Get cached analysis results for a ticker and year."""
    if isinstance(redis_client, dict):  # In-memory cache
        cache_key = f"analysis:{ticker}:{year}"
        return redis_client.get(cache_key)
    else:  # Redis cache
        cache_key = f"analysis:{ticker}:{year}"
        cached_data = redis_client.get(cache_key)
        if cached_data:
            return json.loads(cached_data)
    return None

def cache_analysis(ticker: str, year: str, analysis: dict):
    """Cache analysis results for a ticker and year."""
    cache_key = f"analysis:{ticker}:{year}"
    if isinstance(redis_client, dict):  # In-memory cache
        redis_client[cache_key] = analysis
    else:  # Redis cache
        redis_client.setex(cache_key, timedelta(hours=24), json.dumps(analysis))

def get_company_info(ticker: str) -> Optional[Dict]:
    """Get company information from S&P 500 data."""
    try:
        app.logger.info(f"Getting company info for {ticker}")
        
        # Check if the CSV file exists
        csv_path = 'sp500_companies.csv'
        if not os.path.exists(csv_path):
            app.logger.error(f"CSV file {csv_path} does not exist")
            return None
            
        # Read the CSV file
        try:
            companies = pd.read_csv(csv_path)
            app.logger.info(f"Successfully read CSV file with {len(companies)} companies")
        except Exception as e:
            app.logger.error(f"Error reading CSV file: {str(e)}")
            return None
            
        # Find the company
        company = companies[companies['symbol'] == ticker]
        if company.empty:
            app.logger.error(f"Company {ticker} not found in CSV file")
            return None
            
        # Extract company info
        company_info = {
            'name': company['name'].iloc[0],
            'sector': company['sector'].iloc[0],
            'cik': str(company['cik'].iloc[0]).zfill(10)
        }
        
        app.logger.info(f"Found company info for {ticker}: {company_info}")
        return company_info
        
    except Exception as e:
        app.logger.error(f"Error getting company info: {str(e)}")
        app.logger.error(traceback.format_exc())
        return None

def find_available_port(start_port: int = PORT, max_port: int = PORT + 10) -> int:
    """Find an available port to run the Flask app."""
    logger.info(f"Searching for available port between {start_port} and {max_port}")
    
    # First try the default port
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', start_port))
            logger.info(f"Successfully bound to default port {start_port}")
            return start_port
    except OSError:
        logger.info(f"Port {start_port} is in use, searching for alternative...")
    
    # Try alternative ports
    for port in range(start_port + 1, max_port + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                logger.info(f"Successfully bound to port {port}")
                return port
        except OSError:
            logger.debug(f"Port {port} is in use")
            continue
    
    # If no ports are available, try a random port
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))  # Let the OS choose a port
            port = s.getsockname()[1]
            logger.info(f"Successfully bound to random port {port}")
            return port
    except OSError as e:
        logger.error(f"Failed to bind to any port: {str(e)}")
        raise RuntimeError("No available ports found and random port allocation failed")

@app.route('/')
def index():
    return render_template('index.html', analyses=[])

@app.route('/api/analyses', methods=['GET'])
def get_analyses():
    """API endpoint to get list of available analyses."""
    try:
        analyses = []
        if os.path.exists(ANALYSIS_DIR):
            for file in os.listdir(ANALYSIS_DIR):
                if file.endswith('_analysis.txt'):
                    ticker = file.split('_')[0]
                    date = file.split('_')[1]
                    analyses.append({
                        'ticker': ticker,
                        'date': date
                    })
        
        return jsonify({
            'success': True,
            'analyses': analyses
        })
    except Exception as e:
        logger.error(f"Error getting analyses: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/view_analysis/<ticker>/<date>', methods=['GET'])
def view_analysis(ticker, date):
    """Display a summarized analysis and metrics for a pre-generated analysis file."""
    try:
        analysis_file = os.path.join('analysis', f"{ticker}_{date}_analysis.txt")
        if not os.path.exists(analysis_file):
            return jsonify({'error': 'Analysis not found'}), 404

        with open(analysis_file, 'r') as f:
            content = f.read()

        # Use TenKAnalyzer to clean and extract metrics/summary
        cleaned_content = analyzer.clean_html_content(content)
        metrics = analyzer.extract_financial_metrics(cleaned_content)
        summary = analyzer.generate_metrics_summary(metrics)

        return jsonify({
            'success': True,
            'ticker': ticker,
            'date': date,
            'summary': summary,
            'metrics': metrics,
            'content': content  # Optionally include raw content for reference
        })
    except Exception as e:
        logger.error(f"Error reading or analyzing analysis file: {str(e)}")
        return jsonify({'error': 'Failed to read or analyze analysis'}), 500

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.get_json()
        ticker = data.get('ticker', '').upper()
        if not ticker:
            return jsonify({'success': False, 'error': 'Ticker is required'}), 400
        logger.info(f"Received analysis request for ticker: {ticker}")
        result = analyzer.analyze_multiple_years(ticker)
        if 'error' in result:
            return jsonify({'success': False, 'error': result['error']}), 404
        return jsonify({'success': True, **result})
    except Exception as e:
        logger.error(f"Error in /analyze endpoint: {str(e)}")
        return jsonify({'success': False, 'error': f'Internal server error: {str(e)}'}), 500

def calculate_trends(metrics_by_year: Dict) -> Dict:
    """Calculate trends for key metrics across years."""
    trends = {}
    years = sorted(metrics_by_year.keys())
    
    if len(years) < 2:
        return trends
    
    # Calculate trends for each metric category
    for category in ['income_statement', 'balance_sheet', 'cash_flow', 'ratios']:
        trends[category] = {}
        metrics = set()
        
        # Collect all metrics across years
        for year in years:
            metrics.update(metrics_by_year[year].get(category, {}).keys())
        
        # Calculate trend for each metric
        for metric in metrics:
            values = []
            for year in years:
                value = metrics_by_year[year].get(category, {}).get(metric)
                if value is not None:
                    values.append(value)
            
            if len(values) >= 2:
                # Calculate year-over-year growth rates
                growth_rates = []
                for i in range(1, len(values)):
                    if values[i-1] != 0:  # Avoid division by zero
                        growth_rate = (values[i] - values[i-1]) / abs(values[i-1])
                        growth_rates.append(growth_rate)
                
                if growth_rates:
                    # Calculate average growth rate
                    avg_growth = sum(growth_rates) / len(growth_rates)
                    trends[category][metric] = {
                        'average_growth': avg_growth,
                        'latest_value': values[-1],
                        'year_ago_value': values[0],
                        'growth_rate': (values[-1] - values[0]) / abs(values[0]) if values[0] != 0 else None
                    }
    
    return trends

def get_sp500_companies() -> List[Dict]:
    """Get list of S&P 500 companies from CSV file."""
    try:
        with open('sp500_companies.csv', 'r') as f:
            # Skip header
            next(f)
            companies = []
            for line in f:
                symbol, name, sector, cik = line.strip().split(',')
                companies.append({
                    'symbol': symbol,
                    'name': name,
                    'sector': sector,
                    'cik': cik
                })
        return companies
    except Exception as e:
        logger.error(f"Error getting S&P 500 companies: {str(e)}")
        return []

def get_downloaded_filings(ticker: str, sector: str) -> List[Dict[str, str]]:
    """Get all downloaded filings for a ticker."""
    try:
        app.logger.info(f"Getting downloaded filings for {ticker} in sector {sector}")
        filings = []
        base_dir = "downloads"  # Match the base directory used in the downloader
        
        # Check if base directory exists
        if not os.path.exists(base_dir):
            app.logger.error(f"Base directory {base_dir} does not exist")
            return []
            
        sector_dir = os.path.join(base_dir, sector)
        if not os.path.exists(sector_dir):
            app.logger.error(f"Sector directory {sector_dir} does not exist")
            return []
            
        ticker_dir = os.path.join(sector_dir, ticker)
        if not os.path.exists(ticker_dir):
            app.logger.error(f"Ticker directory {ticker_dir} does not exist")
            return []
            
        app.logger.info(f"Found ticker directory: {ticker_dir}")
        
        # Get all year directories
        try:
            year_dirs = [d for d in os.listdir(ticker_dir) if os.path.isdir(os.path.join(ticker_dir, d))]
            app.logger.info(f"Found year directories for {ticker}: {year_dirs}")
        except Exception as e:
            app.logger.error(f"Error reading year directories: {str(e)}")
            return []
        
        # Sort year directories in descending order
        year_dirs.sort(reverse=True)
        
        # Get filings from each year directory
        for year in year_dirs:
            year_dir = os.path.join(ticker_dir, year)
            try:
                year_files = [f for f in os.listdir(year_dir) if f.endswith('.txt')]
                app.logger.info(f"Found {len(year_files)} files in {year} directory for {ticker}")
                
                for filename in year_files:
                    file_path = os.path.join(year_dir, filename)
                    # Extract date from filename (format: TICKER_YYYY-MM-DD.txt)
                    try:
                        date_str = filename.split('_')[1].replace('.txt', '')
                        app.logger.info(f"Processing file {filename} with date {date_str}")
                        
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if not content:
                                app.logger.warning(f"Empty content in file {file_path}")
                                continue
                                
                            filings.append({
                                'date': date_str,
                                'content': content,
                                'year': year
                            })
                            app.logger.info(f"Successfully added filing from {date_str} for {ticker}")
                    except Exception as e:
                        app.logger.error(f"Error processing file {file_path}: {str(e)}")
                        continue
            except Exception as e:
                app.logger.error(f"Error reading year directory {year_dir}: {str(e)}")
                continue
        
        # Sort filings by date in descending order
        filings.sort(key=lambda x: x['date'], reverse=True)
        app.logger.info(f"Total filings found for {ticker}: {len(filings)}")
        return filings
        
    except Exception as e:
        app.logger.error(f"Error getting downloaded filings: {str(e)}")
        app.logger.error(traceback.format_exc())
        return []

# Initialize required directories and files
def initialize_app():
    """Initialize required directories and files."""
    try:
        # Create downloads directory if it doesn't exist
        if not os.path.exists('downloads'):
            os.makedirs('downloads')
            app.logger.info("Created downloads directory")
            
        # Create analysis directory if it doesn't exist
        if not os.path.exists('analysis'):
            os.makedirs('analysis')
            app.logger.info("Created analysis directory")
            
        # Check if sp500_companies.csv exists
        if not os.path.exists('sp500_companies.csv'):
            app.logger.error("sp500_companies.csv not found")
            # Create a basic CSV file with headers
            with open('sp500_companies.csv', 'w') as f:
                f.write('symbol,name,sector,cik\n')
            app.logger.info("Created empty sp500_companies.csv")
            
        app.logger.info("App initialization completed")
    except Exception as e:
        app.logger.error(f"Error during app initialization: {str(e)}")
        app.logger.error(traceback.format_exc())

# Call initialization before starting the app
initialize_app()

if __name__ == '__main__':
    try:
        logger.info("Finding available port...")
        port = find_available_port()
        logger.info(f"Starting Flask app on port {port}")
        
        # Set up error handlers
        @app.errorhandler(404)
        def not_found_error(error):
            return jsonify({'error': 'Resource not found'}), 404

        @app.errorhandler(500)
        def internal_error(error):
            logger.error(f"Internal server error: {str(error)}")
            return jsonify({'error': 'Internal server error'}), 500

        @app.errorhandler(Exception)
        def unhandled_exception(e):
            logger.error(f"Unhandled exception: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return jsonify({'error': 'An unexpected error occurred'}), 500
        
        # Start the app with proper error handling
        app.run(
            host='127.0.0.1',
            port=port,
            debug=DEBUG,
            use_reloader=False  # Disable reloader to prevent duplicate processes
        )
    except Exception as e:
        logger.error(f"Failed to start Flask app: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise 