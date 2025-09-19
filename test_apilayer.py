#!/usr/bin/env python3
"""
APILayer Key Verification Script
Test your APILayer API key: Nf3TEW6egIY2sfOg5mlBqVBsOu22Ngj5
"""

import requests
import json

API_KEY = "Nf3TEW6egIY2sfOg5mlBqVBsOu22Ngj5"

def test_apilayer_services():
    """Test different APILayer services to see what's available with your key."""
    
    headers = {
        'apikey': API_KEY,
        'User-Agent': 'OSINT-Portal/1.0'
    }
    
    # Test different services
    services = [
        {
            "name": "Account Info",
            "url": "https://api.apilayer.com/user/account",
            "description": "Check account status and available credits"
        },
        {
            "name": "Number Verification",
            "url": "https://api.apilayer.com/number_verification/validate",
            "params": {"number": "919876543210"},
            "description": "Phone number validation service"
        },
        {
            "name": "Phone Validator",
            "url": "https://api.apilayer.com/phone_validator/validate", 
            "params": {"number": "919876543210"},
            "description": "Advanced phone validation"
        },
        {
            "name": "Numverify via APILayer",
            "url": "https://api.apilayer.com/numverify/validate",
            "params": {"number": "919876543210"},
            "description": "Numverify service through APILayer"
        }
    ]
    
    print(f"🔑 Testing APILayer Key: {API_KEY[:8]}...")
    print("=" * 60)
    
    working_services = []
    
    for service in services:
        print(f"\n📡 Testing: {service['name']}")
        print(f"   Description: {service['description']}")
        
        try:
            params = service.get('params', {})
            response = requests.get(service['url'], headers=headers, params=params, timeout=15)
            
            print(f"   Status Code: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"   ✅ SUCCESS! Response: {json.dumps(data, indent=2)[:200]}...")
                    working_services.append(service['name'])
                except:
                    print(f"   ✅ SUCCESS! Raw response: {response.text[:200]}...")
                    working_services.append(service['name'])
                    
            elif response.status_code == 401:
                print(f"   ❌ UNAUTHORIZED - Invalid API key")
            elif response.status_code == 403:
                print(f"   ❌ FORBIDDEN - Service not subscribed")
            elif response.status_code == 429:
                print(f"   ⚠️  RATE LIMITED - Too many requests")
            else:
                print(f"   ❌ ERROR: {response.status_code} - {response.text[:100]}")
                
        except requests.exceptions.Timeout:
            print(f"   ⏰ TIMEOUT - Service took too long to respond")
        except requests.exceptions.ConnectionError:
            print(f"   🌐 CONNECTION ERROR - Cannot reach APILayer")
        except Exception as e:
            print(f"   💥 UNEXPECTED ERROR: {str(e)}")
    
    print("\n" + "=" * 60)
    print("📊 SUMMARY:")
    print(f"   API Key: {API_KEY[:8]}...{API_KEY[-4:]}")
    
    if working_services:
        print(f"   ✅ Working Services: {', '.join(working_services)}")
        print(f"   🎉 Your APILayer key is WORKING!")
        return True
    else:
        print(f"   ❌ No working services found")
        print(f"   💡 Possible issues:")
        print(f"      - API key might be invalid")
        print(f"      - No services subscribed")
        print(f"      - Account might be suspended")
        print(f"      - Network connectivity issues")
        return False

if __name__ == "__main__":
    test_apilayer_services()
