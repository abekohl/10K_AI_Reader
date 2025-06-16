from download_10k import SP500Downloader
import logging

def test_sec_access():
    """Test SEC access with various endpoints."""
    downloader = SP500Downloader()
    
    # Test endpoints
    endpoints = [
        "https://www.sec.gov/files/company_tickers.json",  # Simple endpoint
        "https://data.sec.gov/submissions/CIK0000320193.json",  # Company data
        "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-10k-2023.htm"  # Direct filing
    ]
    
    print("\nTesting SEC access with the following configuration:")
    print(f"Email: {downloader.email}")
    print(f"User-Agent: {downloader.sec_headers['User-Agent']}")
    print("\nTesting endpoints:")
    
    for endpoint in endpoints:
        print(f"\nTrying endpoint: {endpoint}")
        try:
            response = downloader.make_sec_request(endpoint)
            print(f"Success! Status code: {response.status_code}")
            print(f"Content type: {response.headers.get('Content-Type')}")
            print(f"Content length: {len(response.content)} bytes")
        except Exception as e:
            print(f"Failed: {str(e)}")

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    test_sec_access() 