import os
import sqlite3
import time
import json
import re
import random
import dns.resolver
import csv
import io
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template, request, jsonify, g, Response
import requests

# For PDF generation
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

app = Flask(__name__)

# --- Config ---
PLATFORMS = {
    "GitHub": "https://github.com/{username}",
    "Twitter/X": "https://twitter.com/{username}",
    "Instagram": "https://www.instagram.com/{username}",
    "Reddit": "https://www.reddit.com/user/{username}",
    "LinkedIn": "https://www.linkedin.com/in/{username}",
    "StackOverflow": "https://stackoverflow.com/users/{username}"
}
HEADERS = {"User-Agent": "OSINT-Portal-Demo/1.0"}
TIMEOUT = 6
MAX_WORKERS = 6
CACHE_TTL = 60  # seconds for demo caching

# --- Simple in-memory cache: username -> (timestamp, result_json) ---
_cache = {}

# --- DB helpers ---
DB_PATH = "history.db"

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()
    c.execute(
        "CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, result_json TEXT, checked_at DATETIME)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS watchlist (id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT UNIQUE, item_type TEXT, added_at DATETIME, last_checked DATETIME)"
    )
    db.commit()
    db.close()

def save_history(username, result_json):
    db = get_db()
    db.execute(
        "INSERT INTO history (username, result_json, checked_at) VALUES (?, ?, ?)",
        (username, json.dumps(result_json), datetime.utcnow().isoformat()),
    )
    db.commit()

def fetch_history(limit=10):
    db = get_db()
    cur = db.execute("SELECT username, result_json, checked_at FROM history ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    out = []
    for r in rows:
        result_data = json.loads(r["result_json"])
        
        out.append({
            "username": r["username"],
            "result": result_data,
            "checked_at": r["checked_at"]
        })
    return out

# --- Watchlist Management ---
def add_to_watchlist(item, item_type=None):
    """Add item to watchlist."""
    if not item_type:
        # Auto-detect type
        if is_valid_email(item):
            item_type = "email"
        elif is_possible_ip(item):
            item_type = "ip"
        elif is_possible_phone(item):
            item_type = "phone"
        elif is_likely_name(item):
            item_type = "name"
        else:
            item_type = "username"
    
    db = get_db()
    try:
        db.execute(
            "INSERT INTO watchlist (item, item_type, added_at) VALUES (?, ?, ?)",
            (item, item_type, datetime.utcnow().isoformat())
        )
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Item already in watchlist

def remove_from_watchlist(item):
    """Remove item from watchlist."""
    db = get_db()
    db.execute("DELETE FROM watchlist WHERE item = ?", (item,))
    db.commit()

def fetch_watchlist():
    """Get all watchlist items."""
    db = get_db()
    rows = db.execute("SELECT * FROM watchlist ORDER BY added_at DESC").fetchall()
    return [dict(r) for r in rows]

def update_watchlist_check(item):
    """Update last checked time for watchlist item."""
    db = get_db()
    db.execute(
        "UPDATE watchlist SET last_checked = ? WHERE item = ?",
        (datetime.utcnow().isoformat(), item)
    )
    db.commit()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

# --- network check ---
def check_profile(platform_name, url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        exists = 200 <= resp.status_code < 400
        # Log for debugging
        if resp.status_code >= 400:
            print(f"DEBUG: {platform_name} returned {resp.status_code} for {url}")
    except requests.RequestException as e:
        print(f"DEBUG: {platform_name} failed with error: {str(e)}")
        exists = False
    return platform_name, url, exists

def run_checks(username):
    # caching
    now = time.time()
    cache_entry = _cache.get(username)
    if cache_entry and now - cache_entry[0] < CACHE_TTL:
        return cache_entry[1]

    # build tasks and results
    results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(check_profile, name, pattern.format(username=username)): name for name, pattern in PLATFORMS.items()}
        for fut in as_completed(futures):
            name, url, exists = fut.result()
            results[name] = {"url": url, "exists": exists}
    # save to cache
    _cache[username] = (now, results)
    return results

# --- Enhanced Phone Investigation with Multiple APIs ---
NUMVERIFY_KEY = os.environ.get("NUMVERIFY_KEY") or "4327590af2793f3032b85d9ff79f8315"

# Additional API keys
PHONEAPI_KEY = os.environ.get("PHONEAPI_KEY") or None  # phoneapi.com requires payment
APILAYER_KEY = os.environ.get("APILAYER_KEY") or "Nf3TEW6egIY2sfOg5mlBqVBsOu22Ngj5"  # Your APILayer key
TRUECALLER_KEY = os.environ.get("TRUECALLER_KEY") or None  # TrueCaller API (expensive)

def is_possible_phone(val):
    """Simple phone detection — at least 7 digits."""
    if not val:
        return False
    digits = re.sub(r"\D", "", val)
    return len(digits) >= 7

def is_possible_ip(val):
    """Simple IP address detection."""
    if not val:
        return False
    # Check for IPv4 pattern
    ipv4_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    # Check for IPv6 pattern (simplified)
    ipv6_pattern = r'^(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$|^::1$|^::$'
    
    return bool(re.match(ipv4_pattern, val) or re.match(ipv6_pattern, val))

def check_phone_number_enhanced(number):
    """Enhanced phone number validation using multiple APIs and OSINT sources."""
    try:
        # Clean the number
        clean_number = re.sub(r"[^\d+]", "", number)
        
        if not clean_number:
            return {"ok": False, "error": "Invalid phone number format"}
        
        # Remove + if present for API call
        if clean_number.startswith('+'):
            clean_number = clean_number[1:]
        
        # Check length (should be 7-15 digits)
        if len(clean_number) < 7 or len(clean_number) > 15:
            return {"ok": False, "error": "Phone number should be 7-15 digits"}
        
        # Initialize comprehensive phone data
        phone_result = {
            "number": number,
            "clean_number": clean_number,
            "international_format": f"+{clean_number}",
            "validation_sources": [],
            "carrier_info": {},
            "location_info": {},
            "social_media_links": [],
            "risk_assessment": {},
            "additional_data": {}
        }
        
        # Try multiple validation sources
        validation_results = []
        
        # 1. Numverify API (Primary)
        numverify_result = try_numverify_api(clean_number)
        if numverify_result["success"]:
            validation_results.append(numverify_result)
            phone_result["validation_sources"].append("Numverify")
        
        # 2. APILayer Phone Validator (Your API key)
        apilayer_result = try_apilayer_api(clean_number)
        if apilayer_result["success"]:
            validation_results.append(apilayer_result)
            phone_result["validation_sources"].append("APILayer")
        
        # 3. Enhanced local validation with carrier detection
        local_result = get_comprehensive_phone_info(clean_number, number)
        validation_results.append(local_result)
        phone_result["validation_sources"].append("Local Database")
        
        # 3. OSINT Framework inspired checks
        osint_data = get_phone_osint_data(clean_number)
        if osint_data:
            phone_result["additional_data"].update(osint_data)
            phone_result["validation_sources"].append("OSINT Sources")
        
        # 4. Social Media Association Checks
        social_data = check_phone_social_media(clean_number)
        if social_data:
            phone_result["social_media_links"] = social_data
            phone_result["validation_sources"].append("Social Media Scan")
        
        # 5. Risk Assessment
        risk_data = assess_phone_risk(clean_number, validation_results)
        phone_result["risk_assessment"] = risk_data
        
        # Merge all validation data
        if validation_results:
            # Combine data from multiple sources
            best_result = merge_phone_validation_results(validation_results)
            phone_result.update(best_result)
            
            return {"ok": True, "data": phone_result}
        else:
            return {"ok": False, "error": "No validation data available"}
        
    except Exception as e:
        return {"ok": False, "error": f"Enhanced validation error: {str(e)}"}

def try_numverify_api(clean_number):
    """Try Numverify API with enhanced error handling."""
    try:
        if NUMVERIFY_KEY and NUMVERIFY_KEY != "your_api_key_here":
            url = f"http://apilayer.net/api/validate"
            params = {
                'access_key': NUMVERIFY_KEY,
                'number': clean_number,
                'country_code': '',
                'format': 1
            }
            
            print(f"Trying Numverify API with key: {NUMVERIFY_KEY[:8]}...")
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('valid'):
                    return {"success": True, "source": "numverify", "data": data}
                elif data.get('success') == False and 'error' in data:
                    print(f"Numverify API Error: {data['error']}")
            
    except Exception as e:
        print(f"Numverify API failed: {e}")
    
    return {"success": False, "source": "numverify", "error": "API unavailable"}

def try_apilayer_api(clean_number):
    """Try APILayer Phone Validator API with your key - simplified version."""
    try:
        if APILAYER_KEY and APILAYER_KEY != "your_api_key_here":
            
            print(f"Testing APILayer API with key: {APILAYER_KEY[:8]}...")
            
            # Simple test - try the most common APILayer endpoint
            headers = {'apikey': APILAYER_KEY}
            
            # First, test account access
            try:
                account_response = requests.get("https://api.apilayer.com/user/account", headers=headers, timeout=10)
                print(f"Account check: Status {account_response.status_code}")
                
                if account_response.status_code == 401:
                    print("❌ APILayer: Invalid API Key")
                    return {"success": False, "source": "apilayer", "error": "Invalid API key"}
                elif account_response.status_code == 200:
                    print("✅ APILayer: Valid API Key")
                    account_data = account_response.json()
                    print(f"Account info: {account_data}")
                
            except Exception as e:
                print(f"Account check failed: {e}")
            
            # Now try phone validation with the most likely endpoint
            phone_url = "https://api.apilayer.com/number_verification/validate"
            params = {"number": clean_number}
            
            try:
                response = requests.get(phone_url, headers=headers, params=params, timeout=10)
                print(f"Phone validation: Status {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"Phone response: {data}")
                    
                    # Check if the response indicates a valid number
                    if data.get('valid') == True or data.get('success') == True:
                        normalized_data = {
                            "valid": True,
                            "number": data.get('number', clean_number),
                            "local_format": data.get('local_format', clean_number),
                            "international_format": data.get('international_format', f"+{clean_number}"),
                            "country_code": data.get('country_code', 'Unknown'),
                            "country_name": data.get('country_name', 'Unknown'),
                            "location": data.get('location', 'Unknown'),
                            "carrier": data.get('carrier', 'Unknown'),
                            "line_type": data.get('line_type', 'Unknown'),
                            "api_source": "APILayer Number Verification"
                        }
                        return {"success": True, "source": "apilayer", "data": normalized_data}
                    else:
                        print(f"APILayer: Number not valid according to response")
                        
                elif response.status_code == 403:
                    print("❌ APILayer: Service not subscribed (403 Forbidden)")
                    return {"success": False, "source": "apilayer", "error": "Service not subscribed"}
                else:
                    print(f"❌ APILayer: Error {response.status_code}: {response.text[:100]}")
                    
            except Exception as e:
                print(f"Phone validation request failed: {e}")
                
    except Exception as e:
        print(f"APILayer API completely failed: {e}")
    
    return {"success": False, "source": "apilayer", "error": "API unavailable"}

def get_comprehensive_phone_info(clean_number, original_number):
    """Comprehensive phone analysis with enhanced carrier and location detection."""
    phone_data = {
        "valid": True,
        "number": original_number,
        "local_format": clean_number,
        "international_format": f"+{clean_number}",
        "source": "comprehensive_local"
    }
    
    # Enhanced Indian number detection with detailed carrier info
    if clean_number.startswith('91') and len(clean_number) == 12:
        phone_data.update({
            "country_code": "IN",
            "country_name": "India",
            "location": get_india_detailed_location(clean_number),
            "carrier": get_india_carrier_comprehensive(clean_number),
            "line_type": "Mobile",
            "circle": get_telecom_circle(clean_number),
            "operator_type": get_operator_type(clean_number)
        })
    elif clean_number.startswith('1') and len(clean_number) == 11:
        phone_data.update({
            "country_code": "US",
            "country_name": "United States/Canada", 
            "location": get_us_detailed_location(clean_number),
            "carrier": get_us_carrier_info(clean_number),
            "line_type": "Mobile" if is_mobile_us(clean_number) else "Landline",
            "area_code": clean_number[1:4],
            "exchange": clean_number[4:7]
        })
    elif clean_number.startswith('44'):
        phone_data.update({
            "country_code": "GB",
            "country_name": "United Kingdom",
            "location": get_uk_location(clean_number),
            "carrier": get_uk_carrier(clean_number),
            "line_type": "Mobile" if clean_number.startswith('447') else "Landline"
        })
    else:
        # International number detection
        country_info = detect_country_from_number(clean_number)
        phone_data.update(country_info)
    
    return {"success": True, "source": "comprehensive_local", "data": phone_data}

def get_phone_osint_data(clean_number):
    """OSINT Framework inspired phone number intelligence gathering."""
    osint_data = {}
    
    try:
        # Generate search URLs for manual OSINT (inspired by OSINT Framework)
        search_urls = {
            "truecaller_search": f"https://www.truecaller.com/search/in/{clean_number}",
            "whocalld_search": f"https://whocalld.com/+{clean_number}",
            "phonevalidator": f"https://www.phonevalidator.com/index.aspx?number={clean_number}",
            "freecarrierlookup": f"https://freecarrierlookup.com/{clean_number}",
            "google_search": f"https://www.google.com/search?q=\"{clean_number}\"",
            "facebook_search": f"https://www.facebook.com/search/people/?q={clean_number}",
            "linkedin_search": f"https://www.linkedin.com/search/results/people/?keywords={clean_number}",
            "telegram_search": f"https://t.me/{clean_number}",
            "whatsapp_check": f"https://wa.me/{clean_number}"
        }
        
        osint_data["search_urls"] = search_urls
        
        # Phone number format analysis
        osint_data["format_analysis"] = analyze_phone_format(clean_number)
        
        # Possible variations for search
        osint_data["search_variations"] = generate_phone_variations(clean_number)
        
        # Time zone information
        osint_data["timezone_info"] = get_timezone_from_phone(clean_number)
        
        return osint_data
        
    except Exception as e:
        print(f"OSINT data gathering failed: {e}")
        return {}

def check_phone_social_media(clean_number):
    """Check for social media associations (simulated for demo)."""
    social_platforms = []
    
    try:
        # Simulate social media checks (in real implementation, use APIs)
        platforms_to_check = [
            {"name": "WhatsApp", "url": f"https://wa.me/{clean_number}", "likely": True},
            {"name": "Telegram", "url": f"https://t.me/{clean_number}", "likely": False},
            {"name": "Viber", "url": "#", "likely": False},
            {"name": "Signal", "url": "#", "likely": False}
        ]
        
        for platform in platforms_to_check:
            if clean_number.startswith('91'):  # Indian numbers more likely on WhatsApp
                platform["likely"] = platform["name"] == "WhatsApp"
            social_platforms.append(platform)
        
        return social_platforms
        
    except Exception as e:
        print(f"Social media check failed: {e}")
        return []

def assess_phone_risk(clean_number, validation_results):
    """Assess potential risks associated with the phone number."""
    risk_data = {
        "risk_level": "Low",
        "risk_factors": [],
        "trust_score": 85,
        "recommendations": []
    }
    
    try:
        # Check for common spam/scam patterns
        if is_potential_spam_number(clean_number):
            risk_data["risk_factors"].append("Potential spam number pattern")
            risk_data["trust_score"] -= 20
        
        # Check validation consistency
        if len(validation_results) > 1:
            consistency = check_validation_consistency(validation_results)
            if not consistency:
                risk_data["risk_factors"].append("Inconsistent validation results")
                risk_data["trust_score"] -= 15
        
        # Determine overall risk level
        if risk_data["trust_score"] < 50:
            risk_data["risk_level"] = "High"
        elif risk_data["trust_score"] < 75:
            risk_data["risk_level"] = "Medium"
        
        # Generate recommendations
        if risk_data["risk_level"] != "Low":
            risk_data["recommendations"].append("Verify through additional sources")
            risk_data["recommendations"].append("Exercise caution in communications")
        
        return risk_data
        
    except Exception as e:
        print(f"Risk assessment failed: {e}")
        return {"risk_level": "Unknown", "trust_score": 50}

def merge_phone_validation_results(results):
    """Merge data from multiple validation sources."""
    merged_data = {}
    
    try:
        for result in results:
            if result.get("success") and "data" in result:
                data = result["data"]
                # Merge non-conflicting data
                for key, value in data.items():
                    if key not in merged_data or merged_data[key] in ["Unknown", None, ""]:
                        merged_data[key] = value
        
        return merged_data
        
    except Exception as e:
        print(f"Result merging failed: {e}")
        return {}

# Enhanced helper functions for comprehensive phone analysis

def get_india_detailed_location(number):
    """Get detailed location information for Indian numbers."""
    if len(number) >= 5:
        series = number[2:5]  # First 3 digits after country code
        
        # Enhanced location mapping based on mobile series
        location_map = {
            # Major metro areas
            '991': 'Delhi NCR', '992': 'Delhi NCR', '993': 'Delhi NCR',
            '981': 'Kolkata, West Bengal', '982': 'Kolkata, West Bengal', 
            '971': 'Mumbai, Maharashtra', '972': 'Mumbai, Maharashtra', '973': 'Mumbai, Maharashtra',
            '974': 'Mumbai, Maharashtra', '975': 'Mumbai, Maharashtra',
            '980': 'Chennai, Tamil Nadu', '984': 'Chennai, Tamil Nadu',
            '990': 'Bangalore, Karnataka', '991': 'Bangalore, Karnataka',
            
            # State-wise mapping
            '944': 'Kerala', '945': 'Kerala', '946': 'Kerala', '947': 'Kerala', '948': 'Kerala', '949': 'Kerala',
            '961': 'Karnataka', '962': 'Karnataka', '963': 'Karnataka', '964': 'Karnataka', '965': 'Karnataka',
            '966': 'Karnataka', '967': 'Karnataka', '968': 'Karnataka', '969': 'Karnataka',
            '951': 'Rajasthan', '952': 'Rajasthan', '953': 'Rajasthan', '954': 'Rajasthan',
            '941': 'Tamil Nadu', '942': 'Tamil Nadu', '943': 'Tamil Nadu',
            '931': 'Haryana', '932': 'Haryana', '933': 'Haryana', '934': 'Haryana',
            '921': 'Punjab', '922': 'Punjab', '923': 'Punjab', '924': 'Punjab', '925': 'Punjab',
            '911': 'Uttar Pradesh', '912': 'Uttar Pradesh', '913': 'Uttar Pradesh', '914': 'Uttar Pradesh',
            '901': 'Andhra Pradesh', '902': 'Andhra Pradesh', '903': 'Andhra Pradesh', '904': 'Andhra Pradesh',
            '851': 'Bihar', '852': 'Bihar', '853': 'Bihar', '854': 'Bihar', '855': 'Bihar',
            '861': 'Odisha', '862': 'Odisha', '863': 'Odisha', '864': 'Odisha', '865': 'Odisha',
            '871': 'Assam', '872': 'Assam', '873': 'Assam', '874': 'Assam', '875': 'Assam',
            '881': 'West Bengal', '882': 'West Bengal', '883': 'West Bengal', '884': 'West Bengal'
        }
        
        return location_map.get(series, f"India (Series: {series})")
    
    return "India"

def get_india_carrier_comprehensive(number):
    """Comprehensive Indian carrier detection with latest data."""
    if len(number) >= 5:
        series = number[2:5]
        
        # Updated carrier mapping (2024-2025 data)
        carrier_map = {
            # Jio (Reliance)
            '991': 'Reliance Jio', '701': 'Reliance Jio', '702': 'Reliance Jio', '703': 'Reliance Jio',
            '704': 'Reliance Jio', '705': 'Reliance Jio', '706': 'Reliance Jio', '707': 'Reliance Jio',
            '708': 'Reliance Jio', '709': 'Reliance Jio',
            
            # Airtel
            '991': 'Bharti Airtel', '701': 'Bharti Airtel', '810': 'Bharti Airtel', '811': 'Bharti Airtel',
            '812': 'Bharti Airtel', '813': 'Bharti Airtel', '814': 'Bharti Airtel', '815': 'Bharti Airtel',
            '816': 'Bharti Airtel', '817': 'Bharti Airtel', '818': 'Bharti Airtel', '819': 'Bharti Airtel',
            
            # Vi (Vodafone Idea)
            '991': 'Vi (Vodafone Idea)', '701': 'Vi (Vodafone Idea)', '820': 'Vi (Vodafone Idea)',
            '821': 'Vi (Vodafone Idea)', '822': 'Vi (Vodafone Idea)', '823': 'Vi (Vodafone Idea)',
            '824': 'Vi (Vodafone Idea)', '825': 'Vi (Vodafone Idea)', '826': 'Vi (Vodafone Idea)',
            
            # BSNL
            '944': 'BSNL', '945': 'BSNL', '946': 'BSNL', '947': 'BSNL',
            
            # Regional operators
            '954': 'Rajasthan - Local Operator', '951': 'Rajasthan - Local Operator'
        }
        
        return carrier_map.get(series, f"Indian Mobile Operator (Series: {series})")
    
    return "Indian Mobile Operator"

def get_telecom_circle(number):
    """Get Indian telecom circle information."""
    if len(number) >= 5:
        series = number[2:5]
        
        circle_map = {
            '991': 'Delhi', '992': 'Delhi', '993': 'Delhi',
            '981': 'Kolkata', '982': 'Kolkata',
            '971': 'Mumbai', '972': 'Mumbai', '973': 'Mumbai',
            '944': 'Kerala', '945': 'Kerala', '946': 'Kerala',
            '961': 'Karnataka', '962': 'Karnataka', '963': 'Karnataka',
            '951': 'Rajasthan', '952': 'Rajasthan',
            '941': 'Tamil Nadu', '942': 'Tamil Nadu', '943': 'Tamil Nadu',
            '931': 'Haryana', '932': 'Haryana',
            '921': 'Punjab', '922': 'Punjab', '923': 'Punjab'
        }
        
        return circle_map.get(series, "All India")
    
    return "Unknown"

def get_operator_type(number):
    """Determine if operator is GSM/CDMA/4G etc."""
    if len(number) >= 3:
        prefix = number[2:5]
        
        # Most modern Indian operators are 4G/5G
        if prefix.startswith('7') or prefix.startswith('8') or prefix.startswith('9'):
            return "4G/5G (GSM)"
        else:
            return "GSM"
    
    return "Unknown"

def detect_country_from_number(clean_number):
    """Detect country from international number."""
    country_codes = {
        '1': {'code': 'US/CA', 'name': 'United States/Canada'},
        '44': {'code': 'GB', 'name': 'United Kingdom'},
        '49': {'code': 'DE', 'name': 'Germany'},
        '33': {'code': 'FR', 'name': 'France'},
        '39': {'code': 'IT', 'name': 'Italy'},
        '34': {'code': 'ES', 'name': 'Spain'},
        '86': {'code': 'CN', 'name': 'China'},
        '81': {'code': 'JP', 'name': 'Japan'},
        '82': {'code': 'KR', 'name': 'South Korea'},
        '61': {'code': 'AU', 'name': 'Australia'},
        '7': {'code': 'RU', 'name': 'Russia'},
        '55': {'code': 'BR', 'name': 'Brazil'},
        '52': {'code': 'MX', 'name': 'Mexico'},
        '27': {'code': 'ZA', 'name': 'South Africa'},
        '20': {'code': 'EG', 'name': 'Egypt'},
        '971': {'code': 'AE', 'name': 'UAE'},
        '966': {'code': 'SA', 'name': 'Saudi Arabia'},
        '65': {'code': 'SG', 'name': 'Singapore'},
        '60': {'code': 'MY', 'name': 'Malaysia'},
        '66': {'code': 'TH', 'name': 'Thailand'}
    }
    
    for code, info in country_codes.items():
        if clean_number.startswith(code):
            return {
                "country_code": info['code'],
                "country_name": info['name'],
                "location": info['name'],
                "carrier": f"{info['name']} Carrier",
                "line_type": "International"
            }
    
    return {
        "country_code": "Unknown",
        "country_name": "International",
        "location": "Unknown",
        "carrier": "Unknown International Carrier",
        "line_type": "International"
    }

def analyze_phone_format(clean_number):
    """Analyze phone number format for additional insights."""
    analysis = {
        "length": len(clean_number),
        "type": "Unknown",
        "pattern": "",
        "is_mobile": False,
        "is_landline": False,
        "is_tollfree": False,
        "is_premium": False
    }
    
    try:
        if clean_number.startswith('91'):
            analysis["type"] = "Indian"
            analysis["is_mobile"] = True
            analysis["pattern"] = f"91-{clean_number[2:7]}-{clean_number[7:]}"
        elif clean_number.startswith('1'):
            analysis["type"] = "NANP (US/CA)"
            analysis["pattern"] = f"1-{clean_number[1:4]}-{clean_number[4:7]}-{clean_number[7:]}"
            analysis["is_mobile"] = True  # Most NANP numbers can be mobile
        elif clean_number.startswith('800') or clean_number.startswith('1800'):
            analysis["is_tollfree"] = True
            analysis["type"] = "Toll-free"
        
        return analysis
        
    except Exception as e:
        return analysis

def generate_phone_variations(clean_number):
    """Generate common variations of the phone number for OSINT searches."""
    variations = []
    
    try:
        # Original formats
        variations.append(clean_number)
        variations.append(f"+{clean_number}")
        
        if clean_number.startswith('91') and len(clean_number) == 12:
            # Indian number variations
            mobile = clean_number[2:]
            variations.extend([
                mobile,
                f"0{mobile}",
                f"+91 {mobile[:5]} {mobile[5:]}",
                f"91-{mobile[:5]}-{mobile[5:]}",
                f"{mobile[:5]} {mobile[5:]}",
                f"{mobile[:5]}-{mobile[5:]}"
            ])
        elif clean_number.startswith('1') and len(clean_number) == 11:
            # US/Canada number variations
            area = clean_number[1:4]
            exchange = clean_number[4:7]
            number = clean_number[7:]
            variations.extend([
                f"({area}) {exchange}-{number}",
                f"{area}-{exchange}-{number}",
                f"{area}.{exchange}.{number}",
                f"{area} {exchange} {number}"
            ])
        
        return list(set(variations))  # Remove duplicates
        
    except Exception as e:
        return [clean_number]

def get_timezone_from_phone(clean_number):
    """Get timezone information based on phone number."""
    try:
        if clean_number.startswith('91'):
            return {"timezone": "IST (UTC+5:30)", "country": "India"}
        elif clean_number.startswith('1'):
            # US/Canada - multiple timezones
            area_code = clean_number[1:4] if len(clean_number) > 3 else ""
            return {"timezone": "Multiple (UTC-8 to UTC-4)", "country": "US/Canada", "area_code": area_code}
        elif clean_number.startswith('44'):
            return {"timezone": "GMT/BST (UTC+0/+1)", "country": "UK"}
        else:
            return {"timezone": "Unknown", "country": "International"}
    except:
        return {"timezone": "Unknown"}

def is_potential_spam_number(clean_number):
    """Check if number matches common spam patterns."""
    spam_patterns = [
        r'^91(9999|8888|7777|6666|5555)',  # Repetitive patterns
        r'^1(800|888|877|866|855)',        # US toll-free (often used for telemarketing)
        r'^91(00000|11111|22222)',         # Sequential patterns
    ]
    
    for pattern in spam_patterns:
        if re.match(pattern, clean_number):
            return True
    
    return False

def check_validation_consistency(results):
    """Check if validation results are consistent across sources."""
    try:
        carrier_names = []
        countries = []
        
        for result in results:
            if result.get("success") and "data" in result:
                data = result["data"]
                if "carrier" in data:
                    carrier_names.append(data["carrier"])
                if "country_name" in data:
                    countries.append(data["country_name"])
        
        # Check for major inconsistencies
        unique_countries = set(countries)
        if len(unique_countries) > 1:
            return False
        
        return True
        
    except:
        return True  # Assume consistent if we can't check

# Additional helper functions for other countries
def get_us_detailed_location(number):
    """Get detailed US location from area code."""
    if len(number) >= 4:
        area_code = number[1:4]
        
        # Major US area codes
        area_code_map = {
            '212': 'New York, NY', '213': 'Los Angeles, CA', '214': 'Dallas, TX',
            '215': 'Philadelphia, PA', '216': 'Cleveland, OH', '217': 'Springfield, IL',
            '301': 'Maryland', '302': 'Delaware', '303': 'Denver, CO',
            '404': 'Atlanta, GA', '405': 'Oklahoma City, OK', '406': 'Montana',
            '407': 'Orlando, FL', '408': 'San Jose, CA', '409': 'Texas',
            '410': 'Baltimore, MD', '412': 'Pittsburgh, PA', '413': 'Massachusetts',
            '414': 'Milwaukee, WI', '415': 'San Francisco, CA', '416': 'Toronto, ON',
            '417': 'Missouri', '418': 'Quebec, QC', '419': 'Toledo, OH',
            '502': 'Louisville, KY', '503': 'Portland, OR', '504': 'New Orleans, LA',
            '505': 'New Mexico', '506': 'New Brunswick', '507': 'Minnesota',
            '508': 'Massachusetts', '509': 'Spokane, WA', '510': 'Oakland, CA',
            '512': 'Austin, TX', '513': 'Cincinnati, OH', '514': 'Montreal, QC',
            '515': 'Des Moines, IA', '516': 'Long Island, NY', '517': 'Lansing, MI',
            '518': 'Albany, NY', '519': 'Ontario, ON'
        }
        
        return area_code_map.get(area_code, f"US/Canada (Area: {area_code})")
    
    return "United States/Canada"

def get_us_carrier_info(number):
    """Get US carrier information (simplified)."""
    # In real implementation, would use carrier lookup APIs
    return "US Mobile Carrier"

def get_uk_location(number):
    """Get UK location from number."""
    if number.startswith('447'):
        return "UK Mobile"
    elif number.startswith('442'):
        return "London, UK"
    else:
        return "United Kingdom"

def get_uk_carrier(number):
    """Get UK carrier information."""
    return "UK Mobile Operator"

def is_mobile_us(number):
    """Check if US number is likely mobile."""
    # Simplified - in reality, US mobile vs landline is complex
    return True  # Most numbers are mobile these days

def get_enhanced_phone_info_v2(clean_number, original_number):
    """Enhanced phone validation with better Indian carrier detection."""
    
    phone_data = {
        "valid": True,
        "number": original_number,
        "local_format": clean_number,
        "international_format": f"+{clean_number}",
    }
    
    # Enhanced Indian number detection
    if clean_number.startswith('91') and len(clean_number) == 12:
        phone_data.update({
            "country_code": "IN",
            "country_name": "India",
            "location": get_india_state_from_number(clean_number),
            "carrier": get_india_carrier_accurate(clean_number),
            "line_type": "Mobile"
        })
    elif clean_number.startswith('1') and len(clean_number) == 11:
        phone_data.update({
            "country_code": "US",
            "country_name": "United States/Canada", 
            "location": get_us_location(clean_number),
            "carrier": "North American Carrier",
            "line_type": "Mobile" if is_mobile_us(clean_number) else "Landline"
        })
    elif clean_number.startswith('44'):
        phone_data.update({
            "country_code": "GB",
            "country_name": "United Kingdom",
            "location": "UK",
            "carrier": "UK Carrier",
            "line_type": "Mobile" if clean_number.startswith('447') else "Landline"
        })
    else:
        phone_data.update({
            "country_code": "Unknown",
            "country_name": "International",
            "location": "Unknown",
            "carrier": "Unknown Carrier", 
            "line_type": "Unknown"
        })
    
    return phone_data

def get_india_carrier_accurate(number):
    """Accurate Indian carrier detection based on actual operator series."""
    # For Indian mobile: 91XXXXXXXXXX (12 digits total)
    # The carrier is determined by digits 3-4 (after country code 91)
    
    if len(number) >= 5:
        # Get the first two digits after country code
        series = number[2:4]  # Position 2-3 in the string
        
        # Airtel India series
        airtel_series = ['91', '92', '93', '94', '95', '96', '97', '98', '99']
        # Jio series  
        jio_series = ['60', '61', '62', '63', '64', '65', '66', '67', '68', '69', 
                      '70', '71', '72', '73', '74', '75', '76', '77', '78', '79']
        # Vodafone/VI series
        vi_series = ['84', '85', '86', '87', '88', '89', '90']
        # BSNL series
        bsnl_series = ['80', '81', '82', '83']
        
        if series in airtel_series:
            return "Airtel India"
        elif series in jio_series:
            return "Reliance Jio"
        elif series in vi_series:
            return "Vodafone Idea (VI)"
        elif series in bsnl_series:
            return "BSNL"
        else:
            return f"Indian Mobile Operator (Series: {series})"
    
    return "Indian Mobile Operator"

def get_india_state_from_number(number):
    """Get Indian state based on number patterns (simplified)."""
    if len(number) >= 7:
        # Use the mobile subscriber number pattern
        area_pattern = number[2:5]
        
        # Andhra Pradesh / Telangana common area codes
        ap_patterns = ['903', '904', '905', '906', '907', '908', '909', 
                       '933', '934', '935', '936', '937', '938', '939',
                       '703', '704', '705']
        
        # Karnataka patterns
        kar_patterns = ['900', '901', '902', '910', '911', '912', '913',
                        '700', '701', '702']
        
        # Tamil Nadu patterns  
        tn_patterns = ['914', '915', '916', '917', '918', '919',
                       '944', '945', '946', '947', '948', '949']
        
        if area_pattern in ap_patterns:
            return "Andhra Pradesh / Telangana"
        elif area_pattern in kar_patterns:
            return "Karnataka"
        elif area_pattern in tn_patterns:
            return "Tamil Nadu"
        else:
            return "India"
    
    return "India"

def get_enhanced_phone_info(clean_number, original_number):
    """Enhanced local phone validation with carrier detection."""
    
    # Country and carrier mapping (basic database)
    phone_data = {
        "valid": True,
        "number": original_number,
        "local_format": clean_number,
        "international_format": f"+{clean_number}",
    }
    
    # Enhanced country detection with carrier info
    if clean_number.startswith('91'):
        phone_data.update({
            "country_code": "IN",
            "country_name": "India",
            "location": get_india_location(clean_number),
            "carrier": get_india_carrier(clean_number),
            "line_type": "Mobile" if is_mobile_india(clean_number) else "Landline"
        })
    elif clean_number.startswith('1'):
        phone_data.update({
            "country_code": "US",
            "country_name": "United States/Canada", 
            "location": get_us_location(clean_number),
            "carrier": get_us_carrier(clean_number),
            "line_type": "Mobile" if is_mobile_us(clean_number) else "Landline"
        })
    elif clean_number.startswith('44'):
        phone_data.update({
            "country_code": "GB",
            "country_name": "United Kingdom",
            "location": "UK Region",
            "carrier": "UK Carrier",
            "line_type": "Mobile" if clean_number.startswith('447') else "Landline"
        })
    elif clean_number.startswith('33'):
        phone_data.update({
            "country_code": "FR", 
            "country_name": "France",
            "location": "France",
            "carrier": "French Carrier",
            "line_type": "Mobile" if clean_number.startswith('336') or clean_number.startswith('337') else "Landline"
        })
    else:
        phone_data.update({
            "country_code": "Unknown",
            "country_name": "Unknown Country",
            "location": "Unknown",
            "carrier": "Unknown Carrier", 
            "line_type": "Unknown"
        })
    
    return phone_data

def get_india_location(number):
    """Get Indian state/region based on number pattern."""
    if number.startswith('9170') or number.startswith('9180'):
        return "Delhi/NCR"
    elif number.startswith('9122'):
        return "Mumbai, Maharashtra"
    elif number.startswith('9180'):
        return "Bangalore, Karnataka"  
    elif number.startswith('9144'):
        return "Chennai, Tamil Nadu"
    elif number.startswith('9133'):
        return "Kolkata, West Bengal"
    elif number.startswith('9140'):
        return "Hyderabad, Telangana"
    else:
        return "India"

def get_india_carrier(number):
    """Detect Indian mobile carrier based on number patterns."""
    # Indian mobile number patterns (simplified)
    if number[2:4] in ['70', '80', '81', '82', '83']:
        return "Jio"
    elif number[2:4] in ['90', '91', '92', '93', '94', '95']:
        return "Airtel" 
    elif number[2:4] in ['98', '99']:
        return "Vodafone/VI"
    elif number[2:4] in ['84', '85']:
        return "BSNL"
    else:
        return "Indian Mobile Carrier"

def is_mobile_india(number):
    """Check if Indian number is mobile."""
    return len(number) == 12 and number[2] in ['6', '7', '8', '9']

def get_us_location(number):
    """Get US location based on area code."""
    if len(number) >= 4:
        area_code = number[1:4]
        us_area_codes = {
            '212': 'New York, NY', '213': 'Los Angeles, CA', '415': 'San Francisco, CA',
            '312': 'Chicago, IL', '617': 'Boston, MA', '713': 'Houston, TX',
            '305': 'Miami, FL', '206': 'Seattle, WA', '702': 'Las Vegas, NV'
        }
        return us_area_codes.get(area_code, f"USA (Area Code: {area_code})")
    return "United States"

def get_us_carrier(number):
    """Basic US carrier detection."""
    return "US Mobile Carrier"

def is_mobile_us(number):
    """Basic mobile detection for US numbers."""
    return len(number) == 11

# --- Enhanced Social Media OSINT Functions ---
def analyze_profile_picture(url):
    """Analyze profile picture for reverse image search (simulation)."""
    return {
        "reverse_search_urls": [
            f"https://www.google.com/searchbyimage?image_url={url}",
            f"https://yandex.com/images/search?rpt=imageview&url={url}",
            f"https://tineye.com/search/?url={url}"
        ],
        "note": "Demo - Use real reverse image search APIs for live data"
    }

def detect_account_age(platform, username):
    """Estimate account creation date (simulation)."""
    # Real implementation would use platform APIs or scraping
    import random
    from datetime import datetime, timedelta
    
    # Simulate account ages for demo
    days_old = random.randint(30, 3650)  # 1 month to 10 years
    creation_date = datetime.now() - timedelta(days=days_old)
    
    return {
        "estimated_creation": creation_date.strftime("%Y-%m-%d"),
        "estimated_age_days": days_old,
        "confidence": "low",
        "note": "Demo simulation - Use real platform APIs for accurate data"
    }

def cross_platform_correlation(username):
    """Find potential correlations across platforms."""
    correlations = []
    
    # Simulate finding similar usernames or patterns
    username_lower = username.lower()
    
    # Check for common patterns
    if any(char.isdigit() for char in username):
        correlations.append({
            "pattern": "numeric_suffix",
            "description": f"Username contains numbers, check variations like {username}1, {username}2",
            "suggestions": [f"{username}1", f"{username}2", f"{username}123"]
        })
    
    if len(username) < 8:
        correlations.append({
            "pattern": "short_username",
            "description": "Short username, likely taken early or premium account",
            "suggestions": [f"{username}_", f"{username}official", f"the{username}"]
        })
    
    if '_' in username or '.' in username:
        base_name = username.replace('_', '').replace('.', '')
        correlations.append({
            "pattern": "separator_usage",
            "description": "Uses separators, check versions without separators",
            "suggestions": [base_name, username.replace('_', '.'), username.replace('.', '_')]
        })
    
    return correlations

def enhanced_social_media_check(username):
    """Enhanced social media investigation with advanced features."""
    # Get basic platform results
    basic_results = run_checks(username)
    
    # Add enhanced analysis for each found platform
    enhanced_results = {}
    
    for platform, info in basic_results.items():
        enhanced_info = info.copy()
        
        if info["exists"]:
            # Add account age estimation
            enhanced_info["account_age"] = detect_account_age(platform, username)
            
            # Add profile picture analysis (simulated)
            profile_pic_url = f"{info['url']}/photo.jpg"  # Simulated URL
            enhanced_info["profile_analysis"] = analyze_profile_picture(profile_pic_url)
            
            # Add follower analysis simulation
            enhanced_info["engagement_metrics"] = {
                "estimated_followers": random.randint(10, 50000),
                "estimated_following": random.randint(50, 2000),
                "activity_level": random.choice(["Low", "Medium", "High"]),
                "note": "Demo simulation - Use real APIs for accurate metrics"
            }
        
        enhanced_results[platform] = enhanced_info
    
    # Add cross-platform correlation analysis
    correlations = cross_platform_correlation(username)
    
    return {
        "username": username,
        "platform_results": enhanced_results,
        "cross_platform_analysis": correlations,
        "investigation_summary": {
            "platforms_found": len([p for p in enhanced_results.values() if p["exists"]]),
            "total_platforms_checked": len(enhanced_results),
            "correlation_patterns": len(correlations)
        }
    }

# --- Email Investigation Configuration ---
# HaveIBeenPwned API Configuration
HIBP_API_KEY = os.environ.get("HIBP_API_KEY") or None  # Get from https://haveibeenpwned.com/API/Key

# --- Enhanced Email Investigation with Multiple Sources ---
def is_valid_ip(ip):
    """Check if IP address format is valid (IPv4 or IPv6)."""
    import ipaddress
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False

def is_private_ip(ip):
    """Check if IP address is private/internal."""
    import ipaddress
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.is_private
    except ValueError:
        return False

def is_valid_email(email):
    """Check if email format is valid."""
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_pattern, email) is not None

def check_email_investigation_enhanced(email):
    """Enhanced comprehensive email investigation using multiple OSINT sources."""
    try:
        if not is_valid_email(email):
            return {"ok": False, "error": "Invalid email format"}
        
        # Split email into local and domain parts
        local_part, domain = email.split('@')
        
        # Initialize comprehensive email investigation result
        email_result = {
            "email": email,
            "local_part": local_part,
            "domain": domain,
            "validation_sources": [],
            "domain_analysis": {},
            "breach_intelligence": {},
            "social_media_presence": {},
            "osint_search_urls": {},
            "risk_assessment": {},
            "professional_analysis": {},
            "additional_intelligence": {}
        }
        
        # 1. Enhanced Domain Analysis
        domain_analysis = get_enhanced_domain_analysis(domain)
        email_result["domain_analysis"] = domain_analysis
        email_result["validation_sources"].append("Domain Analysis")
        
        # 2. Comprehensive Breach Intelligence
        breach_intel = get_comprehensive_breach_intelligence(email)
        email_result["breach_intelligence"] = breach_intel
        email_result["validation_sources"].append("Breach Intelligence")
        
        # 3. Enhanced Social Media Detection
        social_presence = get_enhanced_social_media_presence(email, local_part)
        email_result["social_media_presence"] = social_presence
        email_result["validation_sources"].append("Social Media Analysis")
        
        # 4. OSINT Framework Search URLs
        osint_urls = generate_email_osint_urls(email, local_part, domain)
        email_result["osint_search_urls"] = osint_urls
        email_result["validation_sources"].append("OSINT Search URLs")
        
        # 5. Professional Analysis
        professional_analysis = get_professional_email_analysis(email, domain)
        email_result["professional_analysis"] = professional_analysis
        email_result["validation_sources"].append("Professional Analysis")
        
        # 6. Risk Assessment
        risk_assessment = assess_email_risk(email, domain, breach_intel, social_presence)
        email_result["risk_assessment"] = risk_assessment
        email_result["validation_sources"].append("Risk Assessment")
        
        # 7. Additional Intelligence
        additional_intel = get_additional_email_intelligence(email, local_part, domain)
        email_result["additional_intelligence"] = additional_intel
        
        return {"ok": True, "data": email_result}
        
    except Exception as e:
        return {"ok": False, "error": f"Enhanced email investigation error: {str(e)}"}

def check_ip_investigation_enhanced(ip):
    """Comprehensive IP address investigation using OSINT techniques."""
    try:
        if not is_valid_ip(ip):
            return {"ok": False, "error": "Invalid IP address format"}
        
        # Initialize comprehensive IP investigation result
        ip_result = {
            "ip": ip,
            "is_private": is_private_ip(ip),
            "geolocation": {},
            "network_info": {},
            "security_analysis": {},
            "reverse_dns": {},
            "reputation": {},
            "open_ports": {},
            "osint_search_urls": {},
            "threat_intelligence": {},
            "additional_info": {}
        }
        
        # Skip investigation for private IPs
        if ip_result["is_private"]:
            ip_result["network_info"] = {
                "type": "Private/Internal IP",
                "description": "This is a private IP address used in internal networks"
            }
            return {"ok": True, "data": ip_result}
        
        # 1. Geolocation Analysis
        geolocation_info = get_ip_geolocation(ip)
        ip_result["geolocation"] = geolocation_info
        
        # 2. Network Information
        network_info = get_ip_network_info(ip)
        ip_result["network_info"] = network_info
        
        # 3. Reverse DNS Lookup
        reverse_dns_info = get_reverse_dns(ip)
        ip_result["reverse_dns"] = reverse_dns_info
        
        # 4. Security Analysis
        security_analysis = analyze_ip_security(ip)
        ip_result["security_analysis"] = security_analysis
        
        # 5. Reputation Check
        reputation_info = check_ip_reputation(ip)
        ip_result["reputation"] = reputation_info
        
        # 6. OSINT Search URLs
        osint_urls = generate_ip_osint_urls(ip)
        ip_result["osint_search_urls"] = osint_urls
        
        # 7. Threat Intelligence
        threat_intel = get_ip_threat_intelligence(ip)
        ip_result["threat_intelligence"] = threat_intel
        
        # 8. Additional Information
        additional_info = get_additional_ip_info(ip)
        ip_result["additional_info"] = additional_info
        
        return {"ok": True, "data": ip_result}
        
    except Exception as e:
        return {"ok": False, "error": f"IP investigation error: {str(e)}"}

def get_ip_geolocation(ip):
    """Get IP geolocation information using free services."""
    try:
        # Simulate geolocation data (in real implementation, you'd use free APIs like ipapi.co)
        geolocation_data = {
            "country": "Unknown",
            "country_code": "N/A",
            "region": "Unknown", 
            "city": "Unknown",
            "latitude": 0.0,
            "longitude": 0.0,
            "timezone": "Unknown",
            "isp": "Unknown",
            "organization": "Unknown",
            "asn": "Unknown",
            "source": "Simulated Data"
        }
        
        # Enhanced simulation based on IP patterns
        if ip.startswith("8.8."):
            geolocation_data.update({
                "country": "United States",
                "country_code": "US", 
                "region": "California",
                "city": "Mountain View",
                "isp": "Google LLC",
                "organization": "Google Public DNS",
                "asn": "AS15169"
            })
        elif ip.startswith("1.1."):
            geolocation_data.update({
                "country": "United States",
                "country_code": "US",
                "region": "California", 
                "city": "San Francisco",
                "isp": "Cloudflare Inc",
                "organization": "Cloudflare DNS",
                "asn": "AS13335"
            })
        elif ip.startswith("208.67."):
            geolocation_data.update({
                "country": "United States",
                "country_code": "US",
                "region": "California",
                "city": "San Francisco", 
                "isp": "Cisco Systems",
                "organization": "OpenDNS",
                "asn": "AS36692"
            })
        
        return geolocation_data
        
    except Exception as e:
        return {"error": f"Geolocation lookup failed: {str(e)}"}

def get_ip_network_info(ip):
    """Get network information for IP address."""
    try:
        import ipaddress
        ip_obj = ipaddress.ip_address(ip)
        
        network_info = {
            "ip_version": f"IPv{ip_obj.version}",
            "is_global": ip_obj.is_global,
            "is_private": ip_obj.is_private,
            "is_multicast": ip_obj.is_multicast,
            "is_reserved": ip_obj.is_reserved,
            "is_loopback": ip_obj.is_loopback,
            "network_class": get_ip_class(ip),
            "binary_representation": format(int(ip_obj), '032b') if ip_obj.version == 4 else "IPv6 Binary Too Long"
        }
        
        return network_info
        
    except Exception as e:
        return {"error": f"Network info lookup failed: {str(e)}"}

def get_reverse_dns(ip):
    """Perform reverse DNS lookup."""
    try:
        import socket
        try:
            hostname = socket.gethostbyaddr(ip)[0]
            return {
                "hostname": hostname,
                "has_reverse_dns": True,
                "ptr_record": hostname
            }
        except socket.herror:
            return {
                "hostname": "No reverse DNS",
                "has_reverse_dns": False,
                "ptr_record": None
            }
    except Exception as e:
        return {"error": f"Reverse DNS lookup failed: {str(e)}"}

def analyze_ip_security(ip):
    """Analyze IP for security indicators."""
    try:
        security_info = {
            "is_tor_exit": False,
            "is_proxy": False,
            "is_vpn": False,
            "is_hosting": False,
            "is_datacenter": False,
            "security_score": 0,
            "risk_level": "Low"
        }
        
        # Enhanced analysis based on IP patterns and common knowledge
        if ip.startswith(("8.8.", "1.1.", "208.67.")):
            security_info.update({
                "is_hosting": False,
                "is_datacenter": True,
                "security_score": 10,
                "risk_level": "Very Low"
            })
        
        # Check for common datacenter ranges (simplified)
        datacenter_ranges = ["192.168.", "10.", "172.16.", "172.17.", "172.18."]
        if any(ip.startswith(range_) for range_ in datacenter_ranges):
            security_info["is_datacenter"] = True
            security_info["security_score"] = 5
            
        return security_info
        
    except Exception as e:
        return {"error": f"Security analysis failed: {str(e)}"}

def check_ip_reputation(ip):
    """Check IP reputation using various indicators."""
    try:
        reputation_info = {
            "reputation_score": 50,  # Neutral score
            "reputation_status": "Clean",
            "blacklist_status": [],
            "whitelist_status": [],
            "threat_categories": [],
            "confidence_level": "Medium"
        }
        
        # Enhanced reputation based on known good IPs
        if ip.startswith(("8.8.", "1.1.", "208.67.")):
            reputation_info.update({
                "reputation_score": 95,
                "reputation_status": "Excellent",
                "whitelist_status": ["Google DNS", "Cloudflare DNS", "OpenDNS"],
                "confidence_level": "High"
            })
        
        return reputation_info
        
    except Exception as e:
        return {"error": f"Reputation check failed: {str(e)}"}

def generate_ip_osint_urls(ip):
    """Generate OSINT investigation URLs for IP address."""
    osint_urls = {
        "shodan": f"https://www.shodan.io/host/{ip}",
        "virustotal": f"https://www.virustotal.com/gui/ip-address/{ip}",
        "censys": f"https://search.censys.io/hosts/{ip}",
        "abuseipdb": f"https://www.abuseipdb.com/check/{ip}",
        "ipinfo": f"https://ipinfo.io/{ip}",
        "whois": f"https://whois.net/ip/{ip}",
        "arin": f"https://whois.arin.net/rest/ip/{ip}",
        "dnslytics": f"https://dnslytics.com/ip/{ip}",
        "securitytrails": f"https://securitytrails.com/list/ip/{ip}",
        "urlvoid": f"https://www.urlvoid.com/ip/{ip}",
        "robtex": f"https://www.robtex.com/ip-lookup/{ip}",
        "threatcrowd": f"https://www.threatcrowd.org/ip.php?ip={ip}",
        "hybrid_analysis": f"https://www.hybrid-analysis.com/search?query={ip}",
        "google_search": f"https://www.google.com/search?q={ip}",
        "bing_search": f"https://www.bing.com/search?q={ip}"
    }
    
    return osint_urls

def get_ip_threat_intelligence(ip):
    """Get threat intelligence information for IP."""
    try:
        threat_intel = {
            "threat_level": "Low",
            "malware_families": [],
            "attack_types": [],
            "last_seen_malicious": None,
            "campaigns": [],
            "threat_actors": [],
            "confidence": "Medium"
        }
        
        # Enhanced threat intel for known good IPs
        if ip.startswith(("8.8.", "1.1.", "208.67.")):
            threat_intel.update({
                "threat_level": "None",
                "confidence": "High"
            })
        
        return threat_intel
        
    except Exception as e:
        return {"error": f"Threat intelligence lookup failed: {str(e)}"}

def get_additional_ip_info(ip):
    """Get additional IP information."""
    try:
        additional_info = {
            "registration_date": "Unknown",
            "last_updated": "Unknown", 
            "registrar": "Unknown",
            "country_threat_level": "Low",
            "economic_sanctions": False,
            "notes": "No additional notes"
        }
        
        # Enhanced info for known IPs
        if ip.startswith("8.8."):
            additional_info.update({
                "registrar": "Google Inc.",
                "notes": "Google Public DNS Service",
                "country_threat_level": "Very Low"
            })
        elif ip.startswith("1.1."):
            additional_info.update({
                "registrar": "Cloudflare Inc.",
                "notes": "Cloudflare Public DNS Service", 
                "country_threat_level": "Very Low"
            })
        
        return additional_info
        
    except Exception as e:
        return {"error": f"Additional info lookup failed: {str(e)}"}

def get_ip_class(ip):
    """Determine IP address class."""
    try:
        first_octet = int(ip.split('.')[0])
        if 1 <= first_octet <= 126:
            return "Class A"
        elif 128 <= first_octet <= 191:
            return "Class B" 
        elif 192 <= first_octet <= 223:
            return "Class C"
        elif 224 <= first_octet <= 239:
            return "Class D (Multicast)"
        elif 240 <= first_octet <= 255:
            return "Class E (Reserved)"
        else:
            return "Unknown"
    except:
        return "Unknown"

def get_enhanced_domain_analysis(domain):
    """Enhanced domain analysis with multiple data points."""
    try:
        domain_info = {
            "domain": domain,
            "mx_records": [],
            "has_mail_service": False,
            "domain_reputation": "Unknown",
            "is_disposable": is_disposable_email_enhanced(domain),
            "is_educational": is_educational_domain(domain),
            "is_government": is_government_domain(domain),
            "is_corporate": is_corporate_domain(domain),
            "provider_type": get_email_provider_type(domain),
            "security_features": analyze_domain_security(domain)
        }
        
        # Enhanced disposable email detection
        if domain_info["is_disposable"]:
            domain_info["domain_reputation"] = "Disposable/Temporary"
        elif domain_info["is_educational"]:
            domain_info["domain_reputation"] = "Educational Institution"
        elif domain_info["is_government"]:
            domain_info["domain_reputation"] = "Government"
        elif domain_info["is_corporate"]:
            domain_info["domain_reputation"] = "Corporate"
        else:
            domain_info["domain_reputation"] = "Personal/Unknown"
        
        # Try to get MX records (simplified for demo)
        try:
            import socket
            domain_info["has_mail_service"] = True  # Assume true if domain exists
        except:
            domain_info["has_mail_service"] = False
        
        return domain_info
        
    except Exception as e:
        return {"domain": domain, "error": str(e)}

def get_comprehensive_breach_intelligence(email):
    """Comprehensive breach intelligence gathering (Simulation Mode - HIBP API key required for real data)."""
    try:
        breach_intel = {
            "email_hash": hash_email_md5(email),
            "sha1_hash": hash_email_sha1(email),
            "estimated_breach_risk": "Unknown",
            "breach_sources": [],
            "breach_count": 0,
            "hibp_check_url": f"https://haveibeenpwned.com/account/{email}",
            "dehashed_search_url": f"https://www.dehashed.com/search?query={email}",
            "breach_analysis": "Simulation Mode - HIBP API key required for real data",
            "paste_count": 0,
            "last_breach_date": None,
            "simulation_mode": True
        }
        
        # Use simulated breach data (realistic patterns)
        hibp_result = check_hibp_breaches(email)
        if hibp_result["success"]:
            breach_intel["breach_sources"] = hibp_result["breaches"]
            breach_intel["breach_count"] = len(hibp_result["breaches"])
            breach_intel["paste_count"] = hibp_result.get("paste_count", 0)
            breach_intel["last_breach_date"] = hibp_result.get("last_breach_date")
            breach_intel["simulation_mode"] = hibp_result.get("simulation_mode", True)
            
            # Determine risk level based on simulated breach count
            if breach_intel["breach_count"] == 0:
                breach_intel["estimated_breach_risk"] = "Low"
                breach_intel["breach_analysis"] = "No simulated breaches found - Clean profile"
            elif breach_intel["breach_count"] <= 2:
                breach_intel["estimated_breach_risk"] = "Medium" 
                breach_intel["breach_analysis"] = "Moderate simulated breach exposure"
            elif breach_intel["breach_count"] <= 5:
                breach_intel["estimated_breach_risk"] = "High"
                breach_intel["breach_analysis"] = "High simulated breach exposure - Multiple incidents"
            else:
                breach_intel["estimated_breach_risk"] = "Critical"
                breach_intel["breach_analysis"] = "Critical simulated breach exposure - Extensive compromise"
        else:
            # Fallback to domain-based estimation if simulation fails
            domain = email.split('@')[1].lower()
            
            if domain in ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']:
                breach_intel["estimated_breach_risk"] = "Medium"
                breach_intel["breach_sources"] = ["Simulation failed - Common provider pattern"]
                breach_intel["breach_analysis"] = "Common email provider - Moderate risk pattern"
            elif domain.endswith('.edu'):
                breach_intel["estimated_breach_risk"] = "Low"
                breach_intel["breach_sources"] = ["Simulation failed - Educational domain pattern"]
                breach_intel["breach_analysis"] = "Educational domain - Low risk pattern"
            elif is_disposable_email_enhanced(domain):
                breach_intel["estimated_breach_risk"] = "High"
                breach_intel["breach_sources"] = ["Simulation failed - Disposable email pattern"]
                breach_intel["breach_analysis"] = "Disposable email - High risk pattern"
            else:
                breach_intel["estimated_breach_risk"] = "Low-Medium"
                breach_intel["breach_sources"] = ["Simulation failed - Custom domain pattern"]
                breach_intel["breach_analysis"] = "Custom domain - Low-medium risk pattern"
        
        return breach_intel
        
    except Exception as e:
        return {"error": str(e), "simulation_mode": True}

def check_hibp_breaches(email):
    """Check HaveIBeenPwned for email breaches (real API if key provided, simulation otherwise)."""
    try:
        # Check if we have a real HIBP API key
        if HIBP_API_KEY and HIBP_API_KEY != "your_hibp_api_key_here":
            return check_hibp_real_api(email)
        else:
            return check_hibp_simulation(email)
        
    except Exception as e:
        return {
            "success": False, 
            "error": f"HIBP check error: {str(e)}", 
            "breaches": [],
            "simulation_mode": True
        }

def check_hibp_real_api(email):
    """Use real HaveIBeenPwned API with provided key."""
    try:
        api_url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}"
        
        headers = {
            'User-Agent': 'OSINT-Portal-Investigation-Tool',
            'hibp-api-key': HIBP_API_KEY
        }
        
        response = requests.get(api_url, headers=headers, timeout=10)
        
        result = {
            "success": False,
            "breaches": [],
            "paste_count": 0,
            "last_breach_date": None,
            "error": None,
            "simulation_mode": False
        }
        
        if response.status_code == 200:
            breaches_data = response.json()
            result["success"] = True
            
            # Extract breach information
            breach_names = []
            latest_date = None
            
            for breach in breaches_data:
                breach_name = breach.get('Name', 'Unknown')
                breach_date = breach.get('BreachDate', '')
                breach_names.append(f"{breach_name} ({breach_date})")
                
                if breach_date and (not latest_date or breach_date > latest_date):
                    latest_date = breach_date
            
            result["breaches"] = breach_names
            result["last_breach_date"] = latest_date
            
        elif response.status_code == 404:
            result["success"] = True
            result["breaches"] = []
            
        elif response.status_code == 429:
            result["error"] = "Rate limit exceeded - try again later"
            
        else:
            result["error"] = f"API returned status {response.status_code}"
        
        # Check for pastes
        try:
            paste_url = f"https://haveibeenpwned.com/api/v3/pasteaccount/{email}"
            paste_response = requests.get(paste_url, headers=headers, timeout=5)
            
            if paste_response.status_code == 200:
                pastes_data = paste_response.json()
                result["paste_count"] = len(pastes_data) if pastes_data else 0
            elif paste_response.status_code == 404:
                result["paste_count"] = 0
                
        except:
            pass
        
        return result
        
    except Exception as e:
        return {"success": False, "error": f"Real API error: {str(e)}", "breaches": [], "simulation_mode": False}

def check_hibp_simulation(email):
    """Simulate HaveIBeenPwned breach checking with realistic patterns."""
    try:
        result = {
            "success": True,
            "breaches": [],
            "paste_count": 0,
            "last_breach_date": None,
            "error": None,
            "simulation_mode": True
        }
        
        # Simulate realistic breach data based on email patterns
        domain = email.split('@')[1].lower()
        local_part = email.split('@')[0].lower()
        
        # Simulate breach likelihood based on domain and patterns
        if domain in ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']:
            # Common providers - higher chance of being in major breaches
            if 'test' in local_part or 'demo' in local_part:
                result["breaches"] = [
                    "Adobe (2013-10-01)",
                    "LinkedIn (2012-05-05)",
                    "Dropbox (2012-07-01)"
                ]
                result["last_breach_date"] = "2013-10-01"
                result["paste_count"] = 2
            elif len(local_part) > 8:  # Longer emails more likely to be in breaches
                result["breaches"] = [
                    "Facebook (2019-04-01)",
                    "Twitter (2022-01-01)"
                ]
                result["last_breach_date"] = "2022-01-01"
                result["paste_count"] = 1
            else:
                result["breaches"] = ["Collection #1 (2019-01-01)"]
                result["last_breach_date"] = "2019-01-01"
                result["paste_count"] = 0
                
        elif domain.endswith('.edu'):
            # Educational domains - usually fewer breaches
            result["breaches"] = []
            result["paste_count"] = 0
            
        elif is_disposable_email_enhanced(domain):
            # Disposable emails - often in spam databases
            result["breaches"] = [
                "Spam Database (2023-01-01)",
                "Marketing Lists (2023-06-01)",
                "Bot Networks (2024-01-01)"
            ]
            result["last_breach_date"] = "2024-01-01"
            result["paste_count"] = 5
            
        elif domain in ['protonmail.com', 'tutanota.com']:
            # Security-focused providers - usually clean
            result["breaches"] = []
            result["paste_count"] = 0
            
        else:
            # Corporate/custom domains - moderate risk
            if 'admin' in local_part or 'test' in local_part:
                result["breaches"] = ["Corporate Breach Simulation (2022-06-01)"]
                result["last_breach_date"] = "2022-06-01"
                result["paste_count"] = 1
            else:
                result["breaches"] = []
                result["paste_count"] = 0
        
        return result
        
    except Exception as e:
        return {
            "success": False, 
            "error": f"Simulation error: {str(e)}", 
            "breaches": [],
            "simulation_mode": True
        }

def get_enhanced_social_media_presence(email, local_part):
    """Enhanced social media presence detection."""
    try:
        social_presence = {
            "gravatar": check_gravatar_presence(email),
            "platform_likely_presence": {},
            "username_variations": generate_username_from_email(local_part),
            "social_search_urls": {}
        }
        
        # Generate likely social media usernames from email
        username_variations = social_presence["username_variations"]
        
        # Check platform likelihood
        platforms = {
            "Facebook": {"likely": True, "confidence": "Medium"},
            "LinkedIn": {"likely": True, "confidence": "High"},
            "Twitter": {"likely": True, "confidence": "Medium"},
            "Instagram": {"likely": True, "confidence": "Medium"},
            "GitHub": {"likely": local_part not in ['admin', 'info', 'contact'], "confidence": "Low"},
            "Reddit": {"likely": True, "confidence": "Low"},
            "YouTube": {"likely": True, "confidence": "Medium"}
        }
        
        social_presence["platform_likely_presence"] = platforms
        
        # Generate social media search URLs
        for username in username_variations[:3]:  # Top 3 variations
            social_presence["social_search_urls"][username] = {
                "facebook": f"https://www.facebook.com/search/people/?q={username}",
                "linkedin": f"https://www.linkedin.com/search/results/people/?keywords={username}",
                "twitter": f"https://twitter.com/search?q={username}",
                "instagram": f"https://www.instagram.com/{username}",
                "github": f"https://github.com/{username}",
                "reddit": f"https://www.reddit.com/user/{username}"
            }
        
        return social_presence
        
    except Exception as e:
        return {"error": str(e)}

def generate_email_osint_urls(email, local_part, domain):
    """Generate comprehensive OSINT search URLs for email investigation."""
    try:
        osint_urls = {
            "email_search": {
                "google": f"https://www.google.com/search?q=\"{email}\"",
                "bing": f"https://www.bing.com/search?q=\"{email}\"",
                "yandex": f"https://yandex.com/search/?text=\"{email}\"",
                "duckduckgo": f"https://duckduckgo.com/?q=\"{email}\""
            },
            "breach_check": {
                "haveibeenpwned": f"https://haveibeenpwned.com/account/{email}",
                "dehashed": f"https://www.dehashed.com/search?query={email}",
                "leakcheck": f"https://leakcheck.net/",
                "scylla": f"https://scylla.so/search?q={email}"
            },
            "social_media": {
                "facebook_email": f"https://www.facebook.com/login/identify/?ctx=recover&ars=facebook_login",
                "linkedin_search": f"https://www.linkedin.com/search/results/people/?keywords={email}",
                "twitter_search": f"https://twitter.com/search?q=\"{email}\"",
                "instagram_search": f"https://www.instagram.com/accounts/password/reset/"
            },
            "domain_analysis": {
                "whois": f"https://whois.net/whois/{domain}",
                "mxtoolbox": f"https://mxtoolbox.com/domain/{domain}",
                "securitytrails": f"https://securitytrails.com/domain/{domain}",
                "domaintools": f"https://whois.domaintools.com/{domain}"
            },
            "reputation_check": {
                "virustotal": f"https://www.virustotal.com/gui/domain/{domain}",
                "urlvoid": f"https://www.urlvoid.com/scan/{domain}",
                "talos": f"https://talosintelligence.com/reputation_center/lookup?search={domain}"
            }
        }
        
        return osint_urls
        
    except Exception as e:
        return {"error": str(e)}

def get_professional_email_analysis(email, domain):
    """Analyze professional aspects of the email."""
    try:
        analysis = {
            "is_personal_provider": is_personal_email_provider(domain),
            "is_corporate": is_corporate_domain(domain),
            "is_educational": is_educational_domain(domain),
            "is_government": is_government_domain(domain),
            "likely_role": determine_email_role(email.split('@')[0]),
            "business_likelihood": "Unknown",
            "contact_type": "Unknown"
        }
        
        # Determine business likelihood
        if analysis["is_corporate"] or analysis["is_educational"] or analysis["is_government"]:
            analysis["business_likelihood"] = "High"
        elif analysis["is_personal_provider"]:
            analysis["business_likelihood"] = "Low"
        else:
            analysis["business_likelihood"] = "Medium"
        
        # Determine contact type
        local_part = email.split('@')[0].lower()
        if local_part in ['admin', 'administrator', 'root', 'webmaster']:
            analysis["contact_type"] = "Administrative"
        elif local_part in ['info', 'contact', 'hello', 'support']:
            analysis["contact_type"] = "General Contact"
        elif local_part in ['sales', 'marketing', 'business']:
            analysis["contact_type"] = "Business"
        elif local_part in ['hr', 'jobs', 'careers', 'recruitment']:
            analysis["contact_type"] = "Human Resources"
        else:
            analysis["contact_type"] = "Personal/Individual"
        
        return analysis
        
    except Exception as e:
        return {"error": str(e)}

def assess_email_risk(email, domain, breach_intel, social_presence):
    """Assess risk associated with the email address using real breach data."""
    try:
        risk_factors = []
        trust_score = 85
        
        # Check for disposable email
        if is_disposable_email_enhanced(domain):
            risk_factors.append("Disposable/temporary email service")
            trust_score -= 30
        
        # Check real breach risk from HIBP
        breach_count = breach_intel.get("breach_count", 0)
        paste_count = breach_intel.get("paste_count", 0)
        
        if breach_count >= 5:
            risk_factors.append(f"Critical breach exposure ({breach_count} breaches)")
            trust_score -= 35
        elif breach_count >= 3:
            risk_factors.append(f"High breach exposure ({breach_count} breaches)")
            trust_score -= 25
        elif breach_count >= 1:
            risk_factors.append(f"Medium breach exposure ({breach_count} breaches)")
            trust_score -= 15
        
        # Check paste exposure
        if paste_count > 0:
            risk_factors.append(f"Found in {paste_count} data pastes")
            trust_score -= 10
        
        # Check social media presence (lack of presence can be suspicious)
        gravatar_found = social_presence.get("gravatar", {}).get("found", False)
        if not gravatar_found:
            risk_factors.append("No Gravatar profile (limited online presence)")
            trust_score -= 5
        
        # Check for suspicious local part patterns
        local_part = email.split('@')[0].lower()
        if len(local_part) < 3:
            risk_factors.append("Very short email address")
            trust_score -= 10
        elif local_part.isdigit():
            risk_factors.append("Numeric-only email address")
            trust_score -= 15
        
        # Check for recent breaches
        last_breach = breach_intel.get("last_breach_date")
        if last_breach:
            try:
                from datetime import datetime
                breach_year = int(last_breach.split('-')[0])
                current_year = datetime.now().year
                if current_year - breach_year <= 2:
                    risk_factors.append("Recent breach exposure (within 2 years)")
                    trust_score -= 10
            except:
                pass
        
        # Determine overall risk level
        if trust_score >= 80:
            risk_level = "Low"
        elif trust_score >= 60:
            risk_level = "Medium"
        elif trust_score >= 40:
            risk_level = "High" 
        else:
            risk_level = "Critical"
        
        recommendations = []
        if risk_level != "Low":
            recommendations.append("Verify through additional sources")
            recommendations.append("Check for recent activity")
        if breach_count > 0:
            recommendations.append("User should change passwords immediately")
            recommendations.append("Enable 2FA on all associated accounts")
        if "Disposable" in str(risk_factors):
            recommendations.append("Consider blocking disposable emails")
        if paste_count > 0:
            recommendations.append("Email may be publicly exposed in data dumps")
        
        return {
            "risk_level": risk_level,
            "trust_score": max(0, trust_score),  # Don't go below 0
            "risk_factors": risk_factors,
            "recommendations": recommendations,
            "breach_summary": {
                "total_breaches": breach_count,
                "paste_exposures": paste_count,
                "last_breach": last_breach
            }
        }
        
    except Exception as e:
        return {"error": str(e)}

def get_additional_email_intelligence(email, local_part, domain):
    """Gather additional intelligence about the email."""
    try:
        intelligence = {
            "email_variations": generate_email_variations(local_part, domain),
            "related_domains": get_related_domains(domain),
            "timezone_estimate": estimate_timezone_from_domain(domain),
            "language_indicators": detect_language_indicators(email),
            "pattern_analysis": analyze_email_patterns(local_part)
        }
        
        return intelligence
        
    except Exception as e:
        return {"error": str(e)}

# Enhanced helper functions for email investigation

def is_disposable_email_enhanced(domain):
    """Enhanced disposable email detection."""
    disposable_domains = [
        '10minutemail.com', 'guerrillamail.com', 'mailinator.com',
        'tempmail.org', 'throwaway.email', 'temp-mail.org', 'yopmail.com',
        'maildrop.cc', 'sharklasers.com', 'guerrillamailblock.com',
        'trbvm.com', 'tmailinator.com', 'spambox.us', 'mailnator.com',
        'trashmail.com', 'dispostable.com', '20minutemail.it'
    ]
    
    # Check for common disposable patterns
    disposable_patterns = [
        r'.*temp.*mail.*', r'.*disposable.*', r'.*trash.*mail.*',
        r'.*10minute.*', r'.*guerrilla.*', r'.*mailinator.*'
    ]
    
    domain_lower = domain.lower()
    
    # Direct match check
    if domain_lower in disposable_domains:
        return True
    
    # Pattern matching
    for pattern in disposable_patterns:
        if re.match(pattern, domain_lower):
            return True
    
    return False

def is_educational_domain(domain):
    """Check if domain is educational."""
    edu_patterns = ['.edu', '.ac.', '.university', '.college']
    domain_lower = domain.lower()
    return any(pattern in domain_lower for pattern in edu_patterns)

def is_government_domain(domain):
    """Check if domain is government."""
    gov_patterns = ['.gov', '.mil', '.government']
    domain_lower = domain.lower()
    return any(pattern in domain_lower for pattern in gov_patterns)

def is_corporate_domain(domain):
    """Check if domain appears to be corporate."""
    personal_providers = [
        'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
        'aol.com', 'icloud.com', 'live.com', 'msn.com', 'mail.com',
        'protonmail.com', 'tutanota.com'
    ]
    return domain.lower() not in personal_providers and not is_disposable_email_enhanced(domain)

def is_personal_email_provider(domain):
    """Check if domain is a personal email provider."""
    personal_providers = [
        'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
        'aol.com', 'icloud.com', 'live.com', 'msn.com', 'mail.com',
        'protonmail.com', 'tutanota.com', 'zoho.com'
    ]
    return domain.lower() in personal_providers

def get_email_provider_type(domain):
    """Determine the type of email provider."""
    if is_personal_email_provider(domain):
        return "Personal Provider"
    elif is_educational_domain(domain):
        return "Educational"
    elif is_government_domain(domain):
        return "Government"
    elif is_disposable_email_enhanced(domain):
        return "Disposable/Temporary"
    else:
        return "Corporate/Custom"

def analyze_domain_security(domain):
    """Analyze domain security features."""
    # This would integrate with real security analysis APIs in production
    return {
        "https_supported": "Unknown",
        "security_headers": "Unknown",
        "ssl_grade": "Unknown",
        "reputation_score": "Unknown"
    }

def check_gravatar_presence(email):
    """Check if email has a Gravatar profile."""
    try:
        gravatar_url = f"https://www.gravatar.com/avatar/{hash_email_md5(email)}?d=404"
        response = requests.get(gravatar_url, timeout=5)
        return {
            "found": response.status_code == 200,
            "profile_url": f"https://www.gravatar.com/avatar/{hash_email_md5(email)}" if response.status_code == 200 else None,
            "hash": hash_email_md5(email)
        }
    except:
        return {"found": False, "profile_url": None, "hash": hash_email_md5(email)}

def generate_username_from_email(local_part):
    """Generate likely usernames from email local part."""
    variations = [local_part]
    
    # Remove common separators and numbers
    clean_part = re.sub(r'[._-]', '', local_part)
    if clean_part != local_part:
        variations.append(clean_part)
    
    # Remove trailing numbers
    no_numbers = re.sub(r'\d+$', '', local_part)
    if no_numbers != local_part and len(no_numbers) > 2:
        variations.append(no_numbers)
    
    # Add variations with common separators
    if '.' in local_part:
        variations.append(local_part.replace('.', ''))
        variations.append(local_part.replace('.', '_'))
    
    return list(set(variations))[:5]  # Limit to 5 variations

def hash_email_sha1(email):
    """Create SHA1 hash of email."""
    import hashlib
    return hashlib.sha1(email.lower().strip().encode()).hexdigest()

def determine_email_role(local_part):
    """Determine the likely role/purpose of the email."""
    local_lower = local_part.lower()
    
    role_patterns = {
        "Administrative": ['admin', 'administrator', 'root', 'webmaster', 'postmaster'],
        "Support": ['support', 'help', 'helpdesk', 'service'],
        "Sales/Marketing": ['sales', 'marketing', 'promo', 'offers', 'deals'],
        "Contact": ['info', 'contact', 'hello', 'general'],
        "HR/Recruitment": ['hr', 'jobs', 'careers', 'recruitment', 'hiring'],
        "Technical": ['dev', 'developer', 'tech', 'it', 'engineering'],
        "Executive": ['ceo', 'cto', 'cfo', 'director', 'manager'],
        "No-Reply": ['noreply', 'no-reply', 'donotreply', 'automated']
    }
    
    for role, patterns in role_patterns.items():
        if any(pattern in local_lower for pattern in patterns):
            return role
    
    return "Personal/Individual"

def generate_email_variations(local_part, domain):
    """Generate common variations of the email address."""
    variations = []
    
    # Original
    variations.append(f"{local_part}@{domain}")
    
    # With/without dots
    if '.' in local_part:
        no_dots = local_part.replace('.', '')
        variations.append(f"{no_dots}@{domain}")
    else:
        # Add dots in common positions
        if len(local_part) > 4:
            with_dot = local_part[:len(local_part)//2] + '.' + local_part[len(local_part)//2:]
            variations.append(f"{with_dot}@{domain}")
    
    # With numbers
    for i in range(1, 10):
        variations.append(f"{local_part}{i}@{domain}")
    
    # With underscores
    if '.' in local_part:
        with_underscore = local_part.replace('.', '_')
        variations.append(f"{with_underscore}@{domain}")
    
    return variations[:10]  # Limit to 10 variations

def get_related_domains(domain):
    """Get related domains (subdomains, similar domains)."""
    # This would use real domain intelligence APIs in production
    base_domain = domain.split('.')[-2] if '.' in domain else domain
    
    common_subdomains = ['www', 'mail', 'email', 'smtp', 'pop', 'imap', 'webmail']
    related = [f"{sub}.{domain}" for sub in common_subdomains]
    
    # Add common variations
    if domain.startswith('www.'):
        related.append(domain[4:])
    else:
        related.append(f"www.{domain}")
    
    return related[:5]

def estimate_timezone_from_domain(domain):
    """Estimate timezone based on domain TLD."""
    tld_timezones = {
        '.in': 'IST (UTC+5:30)',
        '.uk': 'GMT/BST (UTC+0/+1)',
        '.de': 'CET (UTC+1)',
        '.jp': 'JST (UTC+9)',
        '.au': 'AEST (UTC+10)',
        '.ca': 'Multiple (UTC-8 to UTC-3:30)',
        '.us': 'Multiple (UTC-10 to UTC-4)',
        '.com': 'Global (Multiple)',
        '.org': 'Global (Multiple)',
        '.net': 'Global (Multiple)'
    }
    
    for tld, timezone in tld_timezones.items():
        if domain.endswith(tld):
            return timezone
    
    return 'Unknown'

def detect_language_indicators(email):
    """Detect language indicators from email address."""
    # Simple detection based on character patterns
    local_part = email.split('@')[0].lower()
    
    if re.search(r'[àáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ]', local_part):
        return "European Language Characters"
    elif re.search(r'[а-яё]', local_part):
        return "Cyrillic Characters (Russian/Eastern European)"
    elif re.search(r'[\u4e00-\u9fff]', local_part):
        return "Chinese Characters"
    elif re.search(r'[\u3040-\u309f\u30a0-\u30ff]', local_part):
        return "Japanese Characters"
    else:
        return "Latin Characters (English/International)"

def analyze_email_patterns(local_part):
    """Analyze patterns in the email local part."""
    analysis = {
        "length": len(local_part),
        "has_numbers": bool(re.search(r'\d', local_part)),
        "has_separators": bool(re.search(r'[._-]', local_part)),
        "pattern_type": "Unknown",
        "complexity": "Low"
    }
    
    # Determine pattern type
    if re.match(r'^[a-zA-Z]+\.[a-zA-Z]+$', local_part):
        analysis["pattern_type"] = "FirstName.LastName"
        analysis["complexity"] = "Medium"
    elif re.match(r'^[a-zA-Z]+_[a-zA-Z]+$', local_part):
        analysis["pattern_type"] = "FirstName_LastName"
        analysis["complexity"] = "Medium"
    elif re.match(r'^[a-zA-Z]+\d+$', local_part):
        analysis["pattern_type"] = "Name + Numbers"
        analysis["complexity"] = "Medium"
    elif local_part.isalpha():
        analysis["pattern_type"] = "Letters Only"
        analysis["complexity"] = "Low"
    elif local_part.isdigit():
        analysis["pattern_type"] = "Numbers Only"
        analysis["complexity"] = "Low"
    else:
        analysis["pattern_type"] = "Mixed/Complex"
        analysis["complexity"] = "High"
    
    return analysis

def check_domain_info(domain):
    """Check domain information and MX records."""
    try:
        domain_info = {
            "domain": domain,
            "mx_records": [],
            "has_mx": False,
            "domain_age": "Unknown",
            "registrar": "Unknown"
        }
        
        # Check MX records
        try:
            mx_records = dns.resolver.resolve(domain, 'MX')
            domain_info["mx_records"] = [str(mx) for mx in mx_records]
            domain_info["has_mx"] = True
        except:
            domain_info["has_mx"] = False
        
        # Classify domain type
        if domain.lower() in ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'aol.com']:
            domain_info["type"] = "Personal Email Provider"
        elif domain.lower() in ['company.com', 'organization.org', 'business.net']:
            domain_info["type"] = "Corporate Domain"
        else:
            domain_info["type"] = "Custom Domain"
        
        return domain_info
        
    except Exception as e:
        return {"domain": domain, "error": str(e)}

def check_email_social_media(email):
    """Check if email is associated with social media accounts."""
    social_results = {}
    
    # List of platforms that might leak email information
    platforms = {
        "Gravatar": f"https://www.gravatar.com/avatar/{hash_email_md5(email)}?d=404",
        "GitHub": None,  # GitHub doesn't expose emails directly
        "Skype": None,   # Skype search limited
    }
    
    # Check Gravatar (most reliable)
    try:
        gravatar_url = platforms["Gravatar"]
        response = requests.get(gravatar_url, timeout=5)
        social_results["Gravatar"] = {
            "found": response.status_code == 200,
            "url": f"https://www.gravatar.com/avatar/{hash_email_md5(email)}" if response.status_code == 200 else None
        }
    except:
        social_results["Gravatar"] = {"found": False, "url": None}
    
    return social_results

def hash_email_md5(email):
    """Create MD5 hash of email for Gravatar."""
    import hashlib
    return hashlib.md5(email.lower().strip().encode()).hexdigest()

def check_email_breaches(email):
    """Check if email appears in known data breaches (simulation)."""
    # Note: Real implementation would use HaveIBeenPwned API
    # For demo purposes, we'll simulate some results
    
    breach_info = {
        "checked": True,
        "breach_count": 0,
        "breaches": [],
        "note": "Demo simulation - Use HaveIBeenPwned API for real data"
    }
    
    # Simulate some breach data for common domains
    common_breaches = ["LinkedIn 2021", "Facebook 2019", "Adobe 2013"]
    
    if any(provider in email.lower() for provider in ['gmail', 'yahoo', 'hotmail']):
        # Simulate that common email providers might have some exposure
        breach_info["breach_count"] = len(common_breaches)
        breach_info["breaches"] = common_breaches
    
    return breach_info

def is_disposable_email(domain):
    """Check if domain is a disposable/temporary email service."""
    disposable_domains = [
        '10minutemail.com', 'guerrillamail.com', 'mailinator.com',
        'tempmail.org', 'throwaway.email', 'temp-mail.org'
    ]
    return domain.lower() in disposable_domains

def is_professional_email(domain):
    """Determine if email appears to be professional/corporate."""
    personal_providers = [
        'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
        'aol.com', 'icloud.com', 'live.com', 'msn.com'
    ]
    return domain.lower() not in personal_providers

# --- Name-Based Investigation Functions ---
def generate_name_variations(full_name):
    """Generate common variations of a name for OSINT searches."""
    if not full_name or len(full_name.strip()) < 2:
        return []
    
    name_parts = [part.strip() for part in full_name.strip().split() if part.strip()]
    if len(name_parts) < 2:
        return [full_name.strip()]
    
    variations = []
    first_name = name_parts[0]
    last_name = name_parts[-1]
    
    # Basic variations
    variations.extend([
        full_name,
        f"{first_name} {last_name}",
        f"{last_name}, {first_name}",
        f"{first_name}.{last_name}",
        f"{first_name}_{last_name}",
        f"{first_name[0]}.{last_name}",
        f"{first_name}{last_name}",
    ])
    
    # Middle name variations if available
    if len(name_parts) > 2:
        middle = name_parts[1]
        variations.extend([
            f"{first_name} {middle[0]}. {last_name}",
            f"{first_name} {middle} {last_name}",
            f"{first_name}.{middle[0]}.{last_name}",
        ])
    
    # Remove duplicates while preserving order
    seen = set()
    unique_variations = []
    for var in variations:
        if var.lower() not in seen:
            seen.add(var.lower())
            unique_variations.append(var)
    
    return unique_variations[:10]  # Limit to 10 variations

def check_professional_networks(name):
    """Check professional networks for name presence."""
    variations = generate_name_variations(name)
    results = {
        "LinkedIn": {"found": False, "profiles": [], "note": "Demo simulation"},
        "AngelList": {"found": False, "profiles": [], "note": "Demo simulation"},
        "Crunchbase": {"found": False, "profiles": [], "note": "Demo simulation"},
        "ResearchGate": {"found": False, "profiles": [], "note": "Demo simulation"}
    }
    
    # Simulate finding profiles for common names
    common_names = ["john smith", "jane doe", "mike johnson", "sarah wilson"]
    if any(common in name.lower() for common in common_names):
        results["LinkedIn"]["found"] = True
        results["LinkedIn"]["profiles"] = [f"linkedin.com/in/{name.lower().replace(' ', '-')}"]
        
        results["AngelList"]["found"] = True
        results["AngelList"]["profiles"] = [f"angel.co/u/{name.lower().replace(' ', '-')}"]
    
    return results

def check_public_records(name):
    """Simulate public records search."""
    variations = generate_name_variations(name)
    
    results = {
        "voter_records": {"found": False, "note": "Demo - Real APIs: VoterDB, Whitepages"},
        "property_records": {"found": False, "note": "Demo - Real APIs: PropertyShark, Zillow"},
        "court_records": {"found": False, "note": "Demo - Real APIs: CourtListener, PACER"},
        "business_filings": {"found": False, "note": "Demo - Real APIs: OpenCorporates"},
        "variations_checked": len(variations),
        "name_variations": variations[:5]  # Show first 5 variations
    }
    
    # Simulate some results for demonstration
    if len(name.split()) >= 2:
        results["voter_records"]["found"] = True
        results["property_records"]["found"] = True
    
    return results

def check_name_investigation(name):
    """Comprehensive name-based OSINT investigation."""
    if not name or len(name.strip()) < 2:
        return {
            "ok": False,
            "error": "Name must be at least 2 characters long"
        }
    
    try:
        # Generate name variations
        variations = generate_name_variations(name)
        
        # Check professional networks
        professional_networks = check_professional_networks(name)
        
        # Check public records
        public_records = check_public_records(name)
        
        # Social media username suggestions
        username_suggestions = []
        first_name = name.split()[0].lower() if name.split() else name.lower()
        last_name = name.split()[-1].lower() if len(name.split()) > 1 else ""
        
        if last_name:
            username_suggestions.extend([
                f"{first_name}{last_name}",
                f"{first_name}.{last_name}",
                f"{first_name}_{last_name}",
                f"{first_name}{last_name}123",
                f"{first_name[0]}{last_name}",
            ])
        else:
            username_suggestions.extend([
                f"{first_name}",
                f"{first_name}123", 
                f"{first_name}_official",
                f"the{first_name}",
            ])
        
        return {
            "ok": True,
            "data": {
                "name": name,
                "variations": variations,
                "professional_networks": professional_networks,
                "public_records": public_records,
                "username_suggestions": username_suggestions[:8],
                "investigation_note": "Name-based OSINT investigation completed"
            }
        }
        
    except Exception as e:
        return {
            "ok": False,
            "error": f"Name investigation failed: {str(e)}"
        }

def is_likely_name(text):
    """Detect if input text appears to be a person's name."""
    if not text or len(text.strip()) < 2:
        return False
    
    # Basic name pattern: 2+ words, mostly alphabetic, reasonable length
    words = text.strip().split()
    if len(words) < 2 or len(words) > 5:
        return False
    
    # Check if all words are mostly alphabetic (allow apostrophes, hyphens)
    for word in words:
        if not re.match(r"^[a-zA-Z\-'\.]+$", word):
            return False
        if len(word) < 1 or len(word) > 20:
            return False
    
    # Total length check
    if len(text) > 50:
        return False
    
    return True

# --- Routes ---
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/email-enhanced", methods=["POST"])
def api_email_enhanced():
    """Enhanced email investigation endpoint."""
    data = request.get_json() or {}
    email = (data.get("email") or "").strip()
    
    if not email:
        return jsonify({"error": "Email address required"}), 400

    try:
        result = check_email_investigation_enhanced(email)
        if result["ok"]:
            save_history(email, result["data"])
            return jsonify(result["data"])
        else:
            return jsonify({"error": result["error"]}), 400
            
    except Exception as e:
        app.logger.error("Enhanced email investigation failed for '%s': %s", email, e)
        return jsonify({"error": f"Investigation failed: {str(e)}"}), 500

@app.route("/api/phone-enhanced", methods=["POST"])
def api_phone_enhanced():
    """Enhanced phone investigation endpoint with multiple data sources."""
    data = request.get_json() or {}
    phone_number = data.get("phone", "").strip()
    
    if not phone_number:
        return jsonify({"error": "Phone number required"}), 400
    
    try:
        # Use enhanced phone validation
        result = check_phone_number_enhanced(phone_number)
        
        if result["ok"]:
            # Save data directly to history  
            save_history(phone_number, result["data"])
            
            return jsonify({
                "success": True,
                "data": result["data"],
                "message": "Enhanced phone investigation completed"
            })
        else:
            return jsonify({
                "success": False,
                "error": result["error"]
            }), 400
            
    except Exception as e:
        return jsonify({"error": f"Enhanced phone investigation failed: {str(e)}"}), 500

@app.route("/api/ip-enhanced", methods=["POST"])
def api_ip_enhanced():
    """Enhanced IP address investigation endpoint."""
    data = request.get_json() or {}
    ip_address = (data.get("ip") or "").strip()
    
    if not ip_address:
        return jsonify({"error": "IP address required"}), 400

    try:
        result = check_ip_investigation_enhanced(ip_address)
        if result["ok"]:
            save_history(ip_address, result["data"])
            return jsonify(result["data"])
        else:
            return jsonify({"error": result["error"]}), 400
            
    except Exception as e:
        app.logger.error("Enhanced IP investigation failed for '%s': %s", ip_address, e)
        return jsonify({"error": f"Investigation failed: {str(e)}"}), 500

@app.route("/api/test-apilayer", methods=["GET"])
def test_apilayer():
    """Test APILayer API key and available services."""
    if not APILAYER_KEY or APILAYER_KEY == "your_api_key_here":
        return jsonify({"error": "No APILayer key configured"}), 400
    
    test_results = []
    
    # Test different APILayer services
    services = [
        {"name": "Account Info", "url": "https://api.apilayer.com/user/account", "method": "GET"},
        {"name": "Number Verification", "url": "https://api.apilayer.com/number_verification/validate", "method": "GET", "params": {"number": "919876543210"}},
        {"name": "Phone Validator", "url": "https://api.apilayer.com/phone_validator/validate", "method": "GET", "params": {"number": "919876543210"}},
        {"name": "Numverify", "url": "https://api.apilayer.com/numverify/validate", "method": "GET", "params": {"number": "919876543210"}},
    ]
    
    headers = {'apikey': APILAYER_KEY}
    
    for service in services:
        try:
            if service["method"] == "GET":
                params = service.get("params", {})
                response = requests.get(service["url"], headers=headers, params=params, timeout=10)
            
            result = {
                "service": service["name"],
                "status_code": response.status_code,
                "accessible": response.status_code == 200,
                "error": None
            }
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    result["sample_response"] = data
                except:
                    result["response_text"] = response.text[:200]
            elif response.status_code == 401:
                result["error"] = "Unauthorized - Invalid API key"
            elif response.status_code == 403:
                result["error"] = "Forbidden - Service not subscribed"
            elif response.status_code == 429:
                result["error"] = "Rate limit exceeded"
            else:
                result["error"] = f"HTTP {response.status_code}: {response.text[:100]}"
            
            test_results.append(result)
            
        except Exception as e:
            test_results.append({
                "service": service["name"],
                "status_code": None,
                "accessible": False,
                "error": str(e)
            })
    
    return jsonify({
        "api_key": f"{APILAYER_KEY[:8]}...",
        "test_results": test_results
    })

@app.route("/api/phone-config", methods=["GET"])
def api_phone_config():
    """Get phone investigation configuration and available APIs."""
    config = {
        "available_apis": {
            "numverify": {
                "status": "active" if NUMVERIFY_KEY and NUMVERIFY_KEY != "demo_key" else "demo",
                "description": "Phone validation and carrier detection (WORKING)",
                "features": ["validation", "carrier", "location", "line_type"],
                "cost": "Free tier available"
            },
            "phoneapi": {
                "status": "not_configured",
                "description": "PhoneNumberAPI.com integration (NOT CONFIGURED)",
                "features": ["validation", "spam_detection", "social_media"],
                "signup_url": "https://phoneapi.com",
                "cost": "$0.01 per lookup"
            },
            "apilayer": {
                "status": "active" if APILAYER_KEY and APILAYER_KEY != "your_api_key_here" else "not_configured", 
                "description": "APILayer Phone Validator (YOUR KEY ACTIVE)",
                "features": ["advanced_validation", "risk_assessment", "carrier_detection"],
                "cost": "$0.005 per request"
            },
            "truecaller": {
                "status": "not_available",
                "description": "TrueCaller API (ENTERPRISE ONLY)",
                "features": ["caller_id", "spam_detection", "business_info"],
                "note": "Not publicly available - enterprise partnerships only"
            },
            "local_database": {
                "status": "active",
                "description": "Comprehensive local phone analysis (WORKING)",
                "features": ["carrier_detection", "location_mapping", "format_analysis"],
                "cost": "Free"
            }
        },
        "supported_countries": ["India", "United States", "Canada", "United Kingdom", "International"],
        "investigation_features": [
            "Phone validation",
            "Carrier identification", 
            "Location detection",
            "Social media association",
            "Risk assessment",
            "OSINT search URLs",
            "Format variations",
            "Timezone information"
        ]
    }
    
    return jsonify(config)

def api_check():
    data = request.get_json() or {}
    # accept either 'value' or 'username' for backward compatibility
    raw = (data.get("value") or data.get("username") or "").strip()
    if not raw:
        return jsonify({"error": "value required"}), 400

    # Email detection
    if is_valid_email(raw):
        email_res = check_email_investigation_enhanced(raw)
        result = {"type": "email", "email_check": email_res}
        try:
            save_history(raw, result)
        except Exception:
            pass
        return jsonify(result)

    # Phone detection
    elif is_possible_phone(raw):
        phone_res = check_phone_number_enhanced(raw)
        result = {"type": "phone", "phone_check": phone_res}
        try:
            save_history(raw, result)
        except Exception:
            pass
        return jsonify(result)

    # Name detection (person's name)
    elif is_likely_name(raw):
        name_res = check_name_investigation(raw)
        result = {"type": "name", "name_check": name_res}
        try:
            save_history(raw, result)
        except Exception:
            pass
        return jsonify(result)

    # Otherwise treat as username
    else:
        results = run_checks(raw)
        # Maintain backward compatibility with frontend
        response = {"username": raw, "results": results}
        try:
            save_history(raw, {"type": "username", "username_results": results})
        except Exception:
            pass
        return jsonify(response)

@app.route("/api/history", methods=["GET"])
def api_history():
    try:
        h = fetch_history(limit=10)
    except Exception as e:
        app.logger.warning("Failed to fetch history: %s", e)
        h = []
    return jsonify({"history": h})

@app.route("/api/check", methods=["POST"])
def api_check():
    """Main investigation endpoint that handles all types of searches."""
    data = request.get_json() or {}
    raw = (data.get("username") or "").strip()
    if not raw:
        return jsonify({"error": "Input required"}), 400

    try:
        # Determine what type of input this is and investigate accordingly
        if is_valid_email(raw):
            # Enhanced email investigation
            email_res = check_email_investigation_enhanced(raw)
            if email_res["ok"]:
                # Save consistent structure to history
                history_data = {
                    "type": "email",
                    "email_check": {"ok": True, "data": email_res["data"]}
                }
                save_history(raw, history_data)
                return jsonify({
                    "type": "email",
                    "email_check": {"ok": True, "data": email_res["data"]},
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                # Email investigation failed
                history_data = {
                    "type": "email",
                    "email_check": email_res
                }
                save_history(raw, history_data)
                return jsonify({
                    "type": "email",
                    "email_check": email_res,
                    "timestamp": datetime.utcnow().isoformat()
                })
        elif is_possible_ip(raw):
            # Enhanced IP investigation
            ip_res = check_ip_investigation_enhanced(raw)
            if ip_res["ok"]:
                # Save consistent structure to history
                history_data = {
                    "type": "ip",
                    "ip_check": {"ok": True, "data": ip_res["data"]}
                }
                save_history(raw, history_data)
                return jsonify({
                    "type": "ip",
                    "ip_check": {"ok": True, "data": ip_res["data"]},
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                # IP investigation failed
                history_data = {
                    "type": "ip",
                    "ip_check": ip_res
                }
                save_history(raw, history_data)
                return jsonify({
                    "type": "ip",
                    "ip_check": ip_res,
                    "timestamp": datetime.utcnow().isoformat()
                })
        elif is_possible_phone(raw):
            # Enhanced phone investigation
            phone_res = check_phone_number_enhanced(raw)
            if phone_res["ok"]:
                # Save consistent structure to history
                history_data = {
                    "type": "phone", 
                    "phone_check": phone_res
                }
                save_history(raw, history_data)
                return jsonify({
                    "type": "phone", 
                    "phone_check": phone_res,
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                # Phone investigation failed
                history_data = {
                    "type": "phone",
                    "phone_check": phone_res
                }
                save_history(raw, history_data)
                return jsonify({
                    "type": "phone",
                    "phone_check": phone_res,
                    "timestamp": datetime.utcnow().isoformat()
                })
        elif is_likely_name(raw):
            # Name investigation
            name_res = check_name_investigation(raw)
            # Save consistent structure to history
            history_data = {
                "type": "name",
                "name_check": name_res
            }
            save_history(raw, history_data)
            return jsonify({
                "type": "name",
                "name_check": name_res,
                "timestamp": datetime.utcnow().isoformat()
            })
        else:
            # Username investigation
            username_results = run_checks(raw)
            # Save consistent structure to history
            history_data = {
                "type": "username",
                "username_results": username_results
            }
            save_history(raw, history_data)
            return jsonify({
                "type": "username",
                "username_results": username_results,
                "timestamp": datetime.utcnow().isoformat()
            })
            
    except Exception as e:
        app.logger.error("Investigation failed for '%s': %s", raw, e)
        return jsonify({"error": f"Investigation failed: {str(e)}"}), 500

@app.route("/api/enhanced-username", methods=["POST"])
def api_enhanced_username():
    """Enhanced username investigation with advanced social media analysis."""
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    if not username:
        return jsonify({"error": "username required"}), 400
    
    try:
        enhanced_results = enhanced_social_media_check(username)
        result = {"type": "enhanced_username", "enhanced_check": enhanced_results}
        try:
            save_history(username, result)
        except Exception:
            pass
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Enhanced investigation failed: {str(e)}"}), 500

@app.route("/api/bulk-search", methods=["POST"])
def api_bulk_search():
    """Bulk search multiple usernames/emails/phones."""
    data = request.get_json() or {}
    items = data.get("items", [])
    search_type = data.get("type", "auto")  # auto, username, email, phone, name
    
    if not items or len(items) > 50:  # Limit to 50 items for demo
        return jsonify({"error": "Provide 1-50 items to search"}), 400
    
    results = []
    
    try:
        for item in items:
            item = item.strip()
            if not item:
                continue
                
            try:
                # Determine search type automatically or use specified type
                if search_type == "auto":
                    if is_valid_email(item):
                        search_result = check_email_investigation_enhanced(item)
                        result_type = "email"
                    elif is_possible_phone(item):
                        search_result = check_phone_number_enhanced(item)
                        result_type = "phone"
                    elif is_likely_name(item):
                        search_result = check_name_investigation(item)
                        result_type = "name"
                    else:
                        search_result = run_checks(item)
                        result_type = "username"
                else:
                    # Use specified type
                    if search_type == "email":
                        search_result = check_email_investigation_enhanced(item)
                        result_type = "email"
                    elif search_type == "phone":
                        search_result = check_phone_number_enhanced(item)
                        result_type = "phone"
                    elif search_type == "name":
                        search_result = check_name_investigation(item)
                        result_type = "name"
                    elif search_type == "username":
                        search_result = run_checks(item)
                        result_type = "username"
                    else:
                        search_result = {"error": "Invalid search type"}
                        result_type = "error"
                
                results.append({
                    "item": item,
                    "type": result_type,
                    "result": search_result,
                    "status": "success" if not isinstance(search_result, dict) or search_result.get("ok", True) else "error"
                })
                
            except Exception as e:
                results.append({
                    "item": item,
                    "type": "error",
                    "result": {"error": str(e)},
                    "status": "error"
                })
        
        # Save bulk search to history
        try:
            bulk_summary = {
                "type": "bulk_search",
                "items_count": len(items),
                "results_count": len(results),
                "successful": len([r for r in results if r["status"] == "success"]),
                "failed": len([r for r in results if r["status"] == "error"])
            }
            save_history(f"Bulk search ({len(items)} items)", bulk_summary)
        except Exception:
            pass
        
        return jsonify({
            "bulk_results": results,
            "summary": {
                "total_items": len(items),
                "successful": len([r for r in results if r["status"] == "success"]),
                "failed": len([r for r in results if r["status"] == "error"]),
                "search_type": search_type
            }
        })
        
    except Exception as e:
        return jsonify({"error": f"Bulk search failed: {str(e)}"}), 500

@app.route("/api/export", methods=["POST"])
def api_export():
    """Export search results in CSV or JSON format."""
    data = request.get_json() or {}
    export_format = data.get("format", "json").lower()
    search_results = data.get("results", [])
    
    if not search_results:
        return jsonify({"error": "No results to export"}), 400
    
    if export_format not in ["json", "csv"]:
        return jsonify({"error": "Format must be 'json' or 'csv'"}), 400
    
    try:
        if export_format == "json":
            export_data = {
                "export_timestamp": datetime.now().isoformat(),
                "total_results": len(search_results),
                "results": search_results
            }
            return jsonify(export_data)
        
        elif export_format == "csv":
            # Flatten results for CSV export
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # CSV Headers
            headers = ["Item", "Type", "Status", "Details"]
            writer.writerow(headers)
            
            # CSV Rows
            for result in search_results:
                item = result.get("item", "")
                result_type = result.get("type", "")
                status = result.get("status", "")
                
                # Flatten details based on type
                details = ""
                result_data = result.get("result", {})
                
                if result_type == "username":
                    found_platforms = [platform for platform, info in result_data.items() if info.get("exists")]
                    details = f"Found on: {', '.join(found_platforms)}" if found_platforms else "Not found on any platform"
                elif result_type == "email":
                    if result_data.get("ok"):
                        email_data = result_data.get("data", {})
                        details = f"Valid: {email_data.get('domain', 'Unknown domain')}, Professional: {email_data.get('professional', False)}"
                    else:
                        details = result_data.get("error", "Validation failed")
                elif result_type == "phone":
                    if result_data.get("ok") and result_data.get("data", {}).get("valid"):
                        phone_data = result_data.get("data", {})
                        details = f"Valid: {phone_data.get('carrier', 'Unknown')}, {phone_data.get('location', 'Unknown')}"
                    else:
                        details = result_data.get("error", "Validation failed")
                elif result_type == "name":
                    if result_data.get("ok"):
                        name_data = result_data.get("data", {})
                        variations_count = len(name_data.get("variations", []))
                        details = f"Variations: {variations_count}, Records checked"
                    else:
                        details = result_data.get("error", "Investigation failed")
                else:
                    details = str(result_data)
                
                writer.writerow([item, result_type, status, details])
            
            csv_content = output.getvalue()
            output.close()
            
            return {
                "csv_data": csv_content,
                "filename": f"osint_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            }, 200, {"Content-Type": "text/plain"}
    
    except Exception as e:
        return jsonify({"error": f"Export failed: {str(e)}"}), 500

@app.route("/api/export-result", methods=["POST"])
def api_export_result():
    """Export a single investigation result in JSON, CSV, or PDF format."""
    data = request.get_json() or {}
    export_format = data.get("format", "json").lower()
    result_data = data.get("result_data", {})
    investigation_type = data.get("type", "unknown")
    target = data.get("target", "unknown")
    
    if not result_data:
        return jsonify({"error": "No result data to export"}), 400
    
    if export_format not in ["json", "csv", "pdf"]:
        return jsonify({"error": "Format must be 'json', 'csv', or 'pdf'"}), 400
    
    if export_format == "pdf" and not PDF_AVAILABLE:
        return jsonify({"error": "PDF export not available. Install reportlab: pip install reportlab"}), 400
    
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if export_format == "json":
            export_data = {
                "export_timestamp": datetime.now().isoformat(),
                "investigation_type": investigation_type,
                "target": target,
                "result_data": result_data
            }
            
            filename = f"osint_{investigation_type}_{target}_{timestamp}.json"
            return Response(
                json.dumps(export_data, indent=2),
                mimetype='application/json',
                headers={'Content-Disposition': f'attachment; filename={filename}'}
            )
        
        elif export_format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            
            # CSV Headers
            writer.writerow(["Field", "Value", "Type"])
            writer.writerow(["Export Timestamp", datetime.now().isoformat(), "metadata"])
            writer.writerow(["Investigation Type", investigation_type, "metadata"])
            writer.writerow(["Target", target, "metadata"])
            writer.writerow([])  # Empty row for separation
            
            # Flatten the result data
            def flatten_dict(obj, parent_key='', sep='_'):
                items = []
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        new_key = f"{parent_key}{sep}{k}" if parent_key else k
                        if isinstance(v, dict):
                            items.extend(flatten_dict(v, new_key, sep=sep).items())
                        elif isinstance(v, list):
                            items.append((new_key, ', '.join(map(str, v))))
                        else:
                            items.append((new_key, str(v) if v is not None else ''))
                return dict(items)
            
            flattened = flatten_dict(result_data)
            for key, value in flattened.items():
                if value and value != 'Unknown' and value != 'N/A':
                    writer.writerow([key.replace('_', ' ').title(), value, "data"])
            
            csv_content = output.getvalue()
            output.close()
            
            filename = f"osint_{investigation_type}_{target}_{timestamp}.csv"
            return Response(
                csv_content,
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment; filename={filename}'}
            )
        
        elif export_format == "pdf":
            # Create PDF
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []
            
            # Title
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=18,
                spaceAfter=30,
                textColor=colors.darkblue
            )
            story.append(Paragraph(f"OSINT Investigation Report", title_style))
            story.append(Spacer(1, 12))
            
            # Metadata
            story.append(Paragraph(f"<b>Investigation Type:</b> {investigation_type.title()}", styles['Normal']))
            story.append(Paragraph(f"<b>Target:</b> {target}", styles['Normal']))
            story.append(Paragraph(f"<b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}", styles['Normal']))
            story.append(Spacer(1, 20))
            
            # Results based on investigation type
            if investigation_type == "ip":
                story.extend(create_ip_pdf_content(result_data, styles))
            elif investigation_type == "email":
                story.extend(create_email_pdf_content(result_data, styles))
            elif investigation_type == "phone":
                story.extend(create_phone_pdf_content(result_data, styles))
            elif investigation_type == "name":
                story.extend(create_name_pdf_content(result_data, styles))
            elif investigation_type == "username":
                story.extend(create_username_pdf_content(result_data, styles))
            else:
                # Generic format
                story.extend(create_generic_pdf_content(result_data, styles))
            
            doc.build(story)
            pdf_content = buffer.getvalue()
            buffer.close()
            
            filename = f"osint_{investigation_type}_{target}_{timestamp}.pdf"
            return Response(
                pdf_content,
                mimetype='application/pdf',
                headers={'Content-Disposition': f'attachment; filename={filename}'}
            )
    
    except Exception as e:
        return jsonify({"error": f"Export failed: {str(e)}"}), 500

@app.route("/api/debug/pdf-status", methods=["GET"])
def debug_pdf_status():
    """Debug endpoint to check PDF availability."""
    try:
        from reportlab.lib.pagesizes import A4
        test_import = True
    except ImportError as e:
        test_import = False
        
    return jsonify({
        "PDF_AVAILABLE": PDF_AVAILABLE,
        "test_import": test_import,
        "message": "PDF functionality check"
    })
    
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if export_format == "json":
            export_data = {
                "export_timestamp": datetime.now().isoformat(),
                "investigation_type": investigation_type,
                "target": target,
                "result_data": result_data
            }
            
            filename = f"osint_{investigation_type}_{target}_{timestamp}.json"
            return Response(
                json.dumps(export_data, indent=2),
                mimetype='application/json',
                headers={'Content-Disposition': f'attachment; filename={filename}'}
            )
        
        elif export_format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            
            # CSV Headers
            writer.writerow(["Field", "Value", "Type"])
            writer.writerow(["Export Timestamp", datetime.now().isoformat(), "metadata"])
            writer.writerow(["Investigation Type", investigation_type, "metadata"])
            writer.writerow(["Target", target, "metadata"])
            writer.writerow([])  # Empty row for separation
            
            # Flatten the result data
            def flatten_dict(obj, parent_key='', sep='_'):
                items = []
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        new_key = f"{parent_key}{sep}{k}" if parent_key else k
                        if isinstance(v, dict):
                            items.extend(flatten_dict(v, new_key, sep=sep).items())
                        elif isinstance(v, list):
                            items.append((new_key, ', '.join(map(str, v))))
                        else:
                            items.append((new_key, str(v) if v is not None else ''))
                return dict(items)
            
            flattened = flatten_dict(result_data)
            for key, value in flattened.items():
                if value and value != 'Unknown' and value != 'N/A':
                    writer.writerow([key.replace('_', ' ').title(), value, "data"])
            
            csv_content = output.getvalue()
            output.close()
            
            filename = f"osint_{investigation_type}_{target}_{timestamp}.csv"
            return Response(
                csv_content,
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment; filename={filename}'}
            )
        
        elif export_format == "pdf":
            # Create PDF
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []
            
            # Title
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=18,
                spaceAfter=30,
                textColor=colors.darkblue
            )
            story.append(Paragraph(f"OSINT Investigation Report", title_style))
            story.append(Spacer(1, 12))
            
            # Metadata
            story.append(Paragraph(f"<b>Investigation Type:</b> {investigation_type.title()}", styles['Normal']))
            story.append(Paragraph(f"<b>Target:</b> {target}", styles['Normal']))
            story.append(Paragraph(f"<b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}", styles['Normal']))
            story.append(Spacer(1, 20))
            
            # Results based on investigation type
            if investigation_type == "ip":
                story.extend(create_ip_pdf_content(result_data, styles))
            elif investigation_type == "email":
                story.extend(create_email_pdf_content(result_data, styles))
            elif investigation_type == "phone":
                story.extend(create_phone_pdf_content(result_data, styles))
            elif investigation_type == "name":
                story.extend(create_name_pdf_content(result_data, styles))
            elif investigation_type == "username":
                story.extend(create_username_pdf_content(result_data, styles))
            else:
                # Generic format
                story.extend(create_generic_pdf_content(result_data, styles))
            
            doc.build(story)
            pdf_content = buffer.getvalue()
            buffer.close()
            
            filename = f"osint_{investigation_type}_{target}_{timestamp}.pdf"
            return Response(
                pdf_content,
                mimetype='application/pdf',
                headers={'Content-Disposition': f'attachment; filename={filename}'}
            )
    
    except Exception as e:
        return jsonify({"error": f"Export failed: {str(e)}"}), 500

def create_ip_pdf_content(data, styles):
    """Create PDF content for IP investigation."""
    story = []
    
    # Overview
    story.append(Paragraph("IP Address Investigation", styles['Heading2']))
    story.append(Paragraph(f"<b>IP Address:</b> {data.get('ip', 'Unknown')}", styles['Normal']))
    story.append(Paragraph(f"<b>Type:</b> {'Private/Internal' if data.get('is_private') else 'Public'}", styles['Normal']))
    story.append(Spacer(1, 12))
    
    # Geolocation
    if data.get('geolocation'):
        geo = data['geolocation']
        story.append(Paragraph("Geolocation Information", styles['Heading3']))
        if geo.get('country'):
            story.append(Paragraph(f"<b>Country:</b> {geo.get('country')} ({geo.get('country_code', 'N/A')})", styles['Normal']))
        if geo.get('city'):
            story.append(Paragraph(f"<b>Location:</b> {geo.get('city')}, {geo.get('region', 'Unknown')}", styles['Normal']))
        if geo.get('isp'):
            story.append(Paragraph(f"<b>ISP:</b> {geo.get('isp')}", styles['Normal']))
        if geo.get('organization'):
            story.append(Paragraph(f"<b>Organization:</b> {geo.get('organization')}", styles['Normal']))
        story.append(Spacer(1, 12))
    
    # Network Info
    if data.get('network_info'):
        net = data['network_info']
        story.append(Paragraph("Network Information", styles['Heading3']))
        story.append(Paragraph(f"<b>IP Version:</b> {net.get('ip_version', 'Unknown')}", styles['Normal']))
        story.append(Paragraph(f"<b>Network Class:</b> {net.get('network_class', 'Unknown')}", styles['Normal']))
        story.append(Spacer(1, 12))
    
    # Security Analysis
    if data.get('security_analysis'):
        sec = data['security_analysis']
        story.append(Paragraph("Security Analysis", styles['Heading3']))
        story.append(Paragraph(f"<b>Risk Level:</b> {sec.get('risk_level', 'Unknown')}", styles['Normal']))
        story.append(Paragraph(f"<b>Security Score:</b> {sec.get('security_score', 'N/A')}/100", styles['Normal']))
        story.append(Spacer(1, 12))
    
    return story

def create_email_pdf_content(data, styles):
    """Create PDF content for email investigation."""
    story = []
    
    story.append(Paragraph("Email Investigation", styles['Heading2']))
    story.append(Paragraph(f"<b>Email:</b> {data.get('email', 'Unknown')}", styles['Normal']))
    story.append(Paragraph(f"<b>Domain:</b> {data.get('domain', 'Unknown')}", styles['Normal']))
    story.append(Spacer(1, 12))
    
    # Domain Analysis
    if data.get('domain_analysis'):
        domain = data['domain_analysis']
        story.append(Paragraph("Domain Analysis", styles['Heading3']))
        story.append(Paragraph(f"<b>Provider Type:</b> {domain.get('provider_type', 'Unknown')}", styles['Normal']))
        story.append(Paragraph(f"<b>Reputation:</b> {domain.get('domain_reputation', 'Unknown')}", styles['Normal']))
        story.append(Spacer(1, 12))
    
    # Breach Intelligence
    if data.get('breach_intelligence'):
        breach = data['breach_intelligence']
        story.append(Paragraph("Breach Intelligence", styles['Heading3']))
        story.append(Paragraph(f"<b>Breaches Found:</b> {len(breach.get('known_breaches', []))}", styles['Normal']))
        story.append(Spacer(1, 12))
    
    return story

def create_phone_pdf_content(data, styles):
    """Create PDF content for phone investigation."""
    story = []
    
    story.append(Paragraph("Phone Investigation", styles['Heading2']))
    story.append(Paragraph(f"<b>Phone Number:</b> {data.get('number', 'Unknown')}", styles['Normal']))
    story.append(Paragraph(f"<b>Valid:</b> {'Yes' if data.get('valid') else 'No'}", styles['Normal']))
    story.append(Spacer(1, 12))
    
    if data.get('carrier'):
        story.append(Paragraph(f"<b>Carrier:</b> {data.get('carrier')}", styles['Normal']))
    if data.get('location'):
        story.append(Paragraph(f"<b>Location:</b> {data.get('location')}", styles['Normal']))
    if data.get('line_type'):
        story.append(Paragraph(f"<b>Line Type:</b> {data.get('line_type')}", styles['Normal']))
    
    story.append(Spacer(1, 12))
    return story

def create_name_pdf_content(data, styles):
    """Create PDF content for name investigation."""
    story = []
    
    story.append(Paragraph("Name Investigation", styles['Heading2']))
    story.append(Paragraph(f"<b>Name:</b> {data.get('name', 'Unknown')}", styles['Normal']))
    
    if data.get('variations'):
        story.append(Paragraph(f"<b>Variations Found:</b> {len(data['variations'])}", styles['Normal']))
    
    story.append(Spacer(1, 12))
    return story

def create_username_pdf_content(data, styles):
    """Create PDF content for username investigation."""
    story = []
    
    story.append(Paragraph("Username Investigation", styles['Heading2']))
    
    found_platforms = []
    not_found_platforms = []
    
    for platform, info in data.items():
        if isinstance(info, dict) and 'exists' in info:
            if info['exists']:
                found_platforms.append(platform)
            else:
                not_found_platforms.append(platform)
    
    story.append(Paragraph(f"<b>Platforms Found:</b> {len(found_platforms)}", styles['Normal']))
    story.append(Paragraph(f"<b>Platforms Checked:</b> {len(found_platforms) + len(not_found_platforms)}", styles['Normal']))
    story.append(Spacer(1, 12))
    
    if found_platforms:
        story.append(Paragraph("Found On:", styles['Heading3']))
        for platform in found_platforms:
            story.append(Paragraph(f"• {platform}", styles['Normal']))
        story.append(Spacer(1, 12))
    
    return story

def create_generic_pdf_content(data, styles):
    """Create generic PDF content for unknown investigation types."""
    story = []
    
    story.append(Paragraph("Investigation Results", styles['Heading2']))
    
    def add_dict_to_story(obj, level=0):
        for key, value in obj.items():
            if isinstance(value, dict):
                story.append(Paragraph(f"{'  ' * level}<b>{key.replace('_', ' ').title()}:</b>", styles['Normal']))
                add_dict_to_story(value, level + 1)
            elif isinstance(value, list):
                story.append(Paragraph(f"{'  ' * level}<b>{key.replace('_', ' ').title()}:</b> {', '.join(map(str, value))}", styles['Normal']))
            else:
                if value and str(value) not in ['Unknown', 'N/A', 'None']:
                    story.append(Paragraph(f"{'  ' * level}<b>{key.replace('_', ' ').title()}:</b> {value}", styles['Normal']))
    
    if isinstance(data, dict):
        add_dict_to_story(data)
    else:
        story.append(Paragraph(f"Result: {data}", styles['Normal']))
    
    return story

@app.route("/api/watchlist", methods=["GET"])
def api_get_watchlist():
    """Get all watchlist items."""
    try:
        watchlist = fetch_watchlist()
        return jsonify({"watchlist": watchlist})
    except Exception as e:
        return jsonify({"error": f"Failed to fetch watchlist: {str(e)}"}), 500

@app.route("/api/watchlist", methods=["POST"])
def api_add_watchlist():
    """Add item to watchlist."""
    data = request.get_json() or {}
    item = (data.get("item") or "").strip()
    item_type = data.get("type")
    
    if not item:
        return jsonify({"error": "Item required"}), 400
    
    try:
        success = add_to_watchlist(item, item_type)
        if success:
            return jsonify({"message": "Added to watchlist", "item": item})
        else:
            return jsonify({"error": "Item already in watchlist"}), 409
    except Exception as e:
        return jsonify({"error": f"Failed to add to watchlist: {str(e)}"}), 500

@app.route("/api/watchlist/<item>", methods=["DELETE"])
def api_remove_watchlist(item):
    """Remove item from watchlist."""
    try:
        remove_from_watchlist(item)
        return jsonify({"message": "Removed from watchlist"})
    except Exception as e:
        return jsonify({"error": f"Failed to remove from watchlist: {str(e)}"}), 500

@app.route("/api/watchlist/monitor", methods=["POST"])
def api_monitor_watchlist():
    """Monitor all watchlist items."""
    try:
        watchlist = fetch_watchlist()
        results = []
        
        for item_data in watchlist:
            item = item_data["item"]
            item_type = item_data["item_type"]
            
            try:
                # Perform investigation based on type
                if item_type == "email":
                    result = check_email_investigation_enhanced(item)
                elif item_type == "phone":
                    result = check_phone_number_enhanced(item)
                elif item_type == "name":
                    result = check_name_investigation(item)
                else:  # username
                    result = run_checks(item)
                
                # Update last checked time
                update_watchlist_check(item)
                
                results.append({
                    "item": item,
                    "type": item_type,
                    "result": result,
                    "status": "success"
                })
                
            except Exception as e:
                results.append({
                    "item": item,
                    "type": item_type,
                    "result": {"error": str(e)},
                    "status": "error"
                })
        
        return jsonify({
            "monitor_results": results,
            "summary": {
                "total_items": len(watchlist),
                "successful": len([r for r in results if r["status"] == "success"]),
                "failed": len([r for r in results if r["status"] == "error"])
            }
        })
        
    except Exception as e:
        return jsonify({"error": f"Watchlist monitoring failed: {str(e)}"}), 500

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
