import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
from download_10k import SP500Downloader

def download_sp500_companies():
    """Download S&P 500 companies data from Wikipedia."""
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
    print(f"Downloaded {len(df)} S&P 500 companies")
    return df

def main():
    # Create necessary directories
    os.makedirs('downloads', exist_ok=True)
    os.makedirs('filings', exist_ok=True)
    
    # Download S&P 500 companies if not exists
    if not os.path.exists('sp500_companies.csv'):
        print("Downloading S&P 500 companies...")
        companies_df = download_sp500_companies()
    else:
        companies_df = pd.read_csv('sp500_companies.csv')
    
    # Initialize downloader
    downloader = SP500Downloader()
    
    # Convert DataFrame to list of dictionaries
    companies = companies_df.to_dict('records')
    
    # Download filings for all companies
    print("Downloading 10-K filings...")
    results = downloader.download_all_filings(companies, years=5)
    
    print("\nDownload Results:")
    print(f"Successfully downloaded: {len(results['success'])} companies")
    print(f"Failed to download: {len(results['failed'])} companies")
    
    if results['failed']:
        print("\nFailed companies:")
        for ticker in results['failed']:
            print(f"- {ticker}")

if __name__ == "__main__":
    main() 