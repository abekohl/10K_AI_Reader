# 10-K AI Reader

An AI-powered tool for analyzing SEC 10-K filings, providing financial metrics and insights for S&P 500 companies.

## Features

- Download and analyze 10-K filings from SEC EDGAR
- Extract key financial metrics
- Generate AI-powered summaries using GPT-4
- Compare multiple years of data
- Modern web interface with responsive design

## Prerequisites

- Python 3.8 or higher
- Redis server (optional, for caching)
- SEC EDGAR access credentials
- OpenAI API key

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/10K_AI_Reader.git
cd 10K_AI_Reader
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
Create a `.env` file in the project root with:
```
SEC_EMAIL=your.email@example.com
OPENAI_API_KEY=your_openai_api_key
```

## Usage

1. Start the Flask application:
```bash
python app.py
```

2. Open your browser and navigate to `http://localhost:8080`

3. Enter a stock ticker (e.g., AAPL) and click "Analyze"

## Project Structure

- `app.py` - Main Flask application
- `analyze_10k.py` - 10-K analysis engine
- `download_10k.py` - SEC EDGAR filing downloader
- `templates/` - Frontend templates
- `static/` - Static assets
- `config.py` - Configuration settings

## Dependencies

- Flask - Web framework
- OpenAI - AI analysis
- BeautifulSoup4 - HTML parsing
- Redis - Caching (optional)
- Bootstrap - Frontend styling
- Marked.js - Markdown rendering

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- SEC EDGAR for providing filing data
- OpenAI for GPT-4 API
- S&P 500 companies data 