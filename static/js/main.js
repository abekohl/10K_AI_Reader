document.addEventListener('DOMContentLoaded', function() {
    const analyzeBtn = document.getElementById('analyze-btn');
    const tickerInput = document.getElementById('ticker');
    const loadingDiv = document.getElementById('loading');
    const errorDiv = document.getElementById('error');
    const resultDiv = document.getElementById('result');
    const analysisContent = document.getElementById('analysis-content');
    const copyBtn = document.getElementById('copy-btn');

    analyzeBtn.addEventListener('click', async function() {
        const ticker = tickerInput.value.trim();
        if (!ticker) {
            showError('Please enter a ticker symbol');
            return;
        }

        // Reset UI
        hideError();
        showLoading();
        hideResult();

        console.log('Starting analysis for', ticker);

        try {
            const response = await fetch('/api/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ ticker })
            });

            console.log('Response status:', response.status);
            const data = await response.json();
            console.log('Received data:', data);

            if (!response.ok) {
                throw new Error(data.error || 'Failed to analyze company');
            }

            // Display company info
            const companyInfo = document.createElement('div');
            companyInfo.innerHTML = `
                <h3>${data.company_name} (${ticker})</h3>
                <p class="text-muted">Sector: ${data.sector}</p>
            `;
            
            // Create metrics table
            const metricsTable = createMetricsTable(data.metrics_by_year, data.trends);
            
            // Display analyses for each year
            const analysesDiv = document.createElement('div');
            analysesDiv.className = 'analyses mt-4';
            
            data.analyses.forEach(yearAnalysis => {
                const yearDiv = document.createElement('div');
                yearDiv.className = 'year-analysis mb-4';
                yearDiv.innerHTML = `
                    <h4>Analysis for ${yearAnalysis.year}</h4>
                    <div class="analysis-text">${yearAnalysis.analysis}</div>
                `;
                analysesDiv.appendChild(yearDiv);
            });
            
            // Clear and update the content
            analysisContent.innerHTML = '';
            analysisContent.appendChild(companyInfo);
            analysisContent.appendChild(metricsTable);
            analysisContent.appendChild(analysesDiv);
            
            showResult();
        } catch (error) {
            console.error('Error:', error);
            showError(error.message);
        } finally {
            hideLoading();
        }
    });

    function createMetricsTable(metricsByYear, trends) {
        const table = document.createElement('table');
        table.className = 'table table-bordered table-hover metrics-table mt-4';
        
        // Create header row with years
        const years = Object.keys(metricsByYear).sort();
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        headerRow.innerHTML = '<th>Metric</th>' + years.map(year => `<th>${year}</th>`).join('') + '<th>Trend</th>';
        thead.appendChild(headerRow);
        table.appendChild(thead);
        
        // Create rows for each metric
        const tbody = document.createElement('tbody');
        const metricGroups = {
            'Income Statement': ['revenue', 'operating_income', 'net_income', 'ebitda'],
            'Balance Sheet': ['total_assets', 'total_liabilities', 'shareholders_equity', 'book_value_per_share'],
            'Cash Flow': ['operating_cash_flow', 'capital_expenditures'],
            'Ratios': ['roe', 'roic', 'interest_coverage']
        };
        
        for (const [group, metrics] of Object.entries(metricGroups)) {
            // Add group header
            const groupRow = document.createElement('tr');
            groupRow.className = 'table-secondary';
            groupRow.innerHTML = `<th colspan="${years.length + 2}">${group}</th>`;
            tbody.appendChild(groupRow);
            
            // Add metric rows
            metrics.forEach(metric => {
                if (trends[metric]) {
                    const row = document.createElement('tr');
                    const metricName = metric.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
                    
                    // Add metric name
                    row.innerHTML = `<td>${metricName}</td>`;
                    
                    // Add values for each year
                    years.forEach(year => {
                        const value = getMetricValue(metricsByYear[year], metric);
                        row.innerHTML += `<td>${formatValue(value)}</td>`;
                    });
                    
                    // Add trend
                    const trend = trends[metric];
                    const trendClass = getTrendClass(trend.trend);
                    const avgGrowth = trend.avg_growth_rate ? `${trend.avg_growth_rate.toFixed(2)}%` : 'N/A';
                    row.innerHTML += `
                        <td class="${trendClass}">
                            ${trend.trend.charAt(0).toUpperCase() + trend.trend.slice(1)}
                            <br>
                            <small>Avg Growth: ${avgGrowth}</small>
                        </td>
                    `;
                    
                    tbody.appendChild(row);
                }
            });
        }
        
        table.appendChild(tbody);
        return table;
    }

    function getMetricValue(yearMetrics, metric) {
        if (!yearMetrics) return null;
        
        for (const section of ['income_statement', 'balance_sheet', 'cash_flow', 'ratios']) {
            if (yearMetrics[section] && yearMetrics[section][metric] !== undefined) {
                return yearMetrics[section][metric];
            }
        }
        return null;
    }

    function formatValue(value) {
        if (value === null || value === undefined) return 'N/A';
        
        // Format as currency for large numbers
        if (Math.abs(value) >= 1000000) {
            return new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD',
                minimumFractionDigits: 0,
                maximumFractionDigits: 0,
                notation: 'compact',
                compactDisplay: 'short'
            }).format(value);
        }
        
        // Format as percentage for ratios
        if (Math.abs(value) < 100) {
            return value.toFixed(2) + '%';
        }
        
        // Default number formatting
        return new Intl.NumberFormat('en-US').format(value);
    }

    function getTrendClass(trend) {
        switch (trend) {
            case 'increasing':
                return 'text-success';
            case 'decreasing':
                return 'text-danger';
            default:
                return 'text-warning';
        }
    }

    // Handle copy button
    copyBtn.addEventListener('click', function() {
        const text = analysisContent.textContent;
        navigator.clipboard.writeText(text).then(function() {
            const originalText = copyBtn.innerHTML;
            copyBtn.innerHTML = '<i class="fas fa-check me-1"></i>Copied!';
            setTimeout(() => {
                copyBtn.innerHTML = originalText;
            }, 2000);
        }).catch(function() {
            showError('Failed to copy text');
        });
    });

    // Handle Enter key in ticker input
    tickerInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            analyzeBtn.click();
        }
    });

    function showLoading() {
        loadingDiv.classList.remove('d-none');
        analyzeBtn.disabled = true;
    }

    function hideLoading() {
        loadingDiv.classList.add('d-none');
        analyzeBtn.disabled = false;
    }

    function showError(message) {
        errorDiv.textContent = message;
        errorDiv.classList.remove('d-none');
    }

    function hideError() {
        errorDiv.classList.add('d-none');
    }

    function showResult() {
        resultDiv.classList.remove('d-none');
    }

    function hideResult() {
        resultDiv.classList.add('d-none');
    }
}); 