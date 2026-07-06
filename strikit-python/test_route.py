import requests
import json
import base64
import os
import sys

# Load env since we bypass fastAPI
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.config import settings

url = "https://api.razorpay.com/v2/accounts"
auth = base64.b64encode(f"{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}".encode()).decode()

payload = {
    "email": "test2@strikit.in",
    "phone": "9876543212",
    "legal_business_name": "Test Turf",
    "business_type": "individual",
    "contact_name": "Test Owner",
    "profile": {
        "category": "sports",
        "subcategory": "sports_complex",
        "addresses": {
            "registered": {
                "street1": "Test Street",
                "city": "Chennai",
                "state": "TN",
                "postal_code": "600001",
                "country": "IN"
            }
        }
    }
}
headers = {
  'Content-Type': 'application/json',
  'Authorization': f'Basic {auth}'
}

response = requests.post(url, headers=headers, data=json.dumps(payload))
print("V2 STATUS:", response.status_code)
print(response.text)

# Also test beta/accounts
url_beta = "https://api.razorpay.com/beta/accounts"
payload_beta = {
    "name": "Test Turf",
    "email": "test3@strikit.in",
    "tnc_accepted": True,
    "account_details": {
        "business_name": "Test Turf",
        "business_type": "individual"
    }
}
response_beta = requests.post(url_beta, headers=headers, data=json.dumps(payload_beta))
print("BETA STATUS:", response_beta.status_code)
print(response_beta.text)

