import asyncio
from app.config import settings
import razorpay

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

try:
    account = client.account.create({
      "name": "Test Account Name",
      "email": "test@strikit.in",
      "tnc_accepted": True,
      "account_details": {
        "business_name": "Test Account Name",
        "business_type": "individual"
      }
    })
    print("SUCCESS")
    print(account)
except Exception as e:
    print("ERROR")
    print(e)
