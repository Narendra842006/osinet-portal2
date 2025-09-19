# 🔒 HaveIBeenPwned API Integration Setup

## Current Status: **SIMULATION MODE**
The email investigation currently uses **realistic simulation data** because no HIBP API key is configured.

## How to Enable Real HIBP Data

### 1. Get API Key
- Visit: https://haveibeenpwned.com/API/Key
- Purchase API key (approximately $3.50/month)
- API provides real-time breach data for millions of email addresses

### 2. Configure API Key

**Option A: Environment Variable (Recommended)**
```bash
# Windows
set HIBP_API_KEY=your_actual_hibp_api_key_here

# Linux/Mac
export HIBP_API_KEY=your_actual_hibp_api_key_here
```

**Option B: Direct Code Modification**
```python
# In app.py, line ~175
HIBP_API_KEY = "your_actual_hibp_api_key_here"
```

### 3. Restart Application
```bash
python app.py
```

## Current Simulation Features

✅ **Realistic Breach Patterns**: Based on actual HIBP breach statistics  
✅ **Domain-Based Risk Assessment**: Gmail, Yahoo, corporate, educational domains  
✅ **Smart Pattern Recognition**: Test emails, disposable domains, secure providers  
✅ **Comprehensive Risk Scoring**: Trust scores, recommendations, security analysis  

## Real API Benefits

🔍 **Real Breach Data**: Actual breaches from HIBP database  
📊 **Accurate Statistics**: Precise breach counts and dates  
🎯 **Paste Monitoring**: Real data from paste sites  
⚡ **Live Updates**: Latest breach information  

## Demo Emails to Test

- `test@gmail.com` - Simulates multiple breaches
- `user@example.edu` - Clean educational domain
- `temp@10minutemail.com` - High risk disposable email
- `secure@protonmail.com` - Security-focused provider

The simulation provides excellent demonstration of capabilities while maintaining privacy and avoiding API costs.
