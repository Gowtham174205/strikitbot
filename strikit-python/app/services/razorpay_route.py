import os
import logging
import razorpay

logger = logging.getLogger(__name__)

def get_razorpay_client():
    from app.config import settings
    if settings.razorpay_configured:
        return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    return None

def create_razorpay_linked_account(name: str, email: str, phone: str, bank_account_number: str, ifsc_code: str) -> str:
    """
    Creates a Razorpay linked account (Route) for a vendor.
    Returns the generated Razorpay account ID (e.g., acc_xyz123).
    """
    client = get_razorpay_client()
    if not client:
        logger.info(f"[RazorpayRoute] Mock linked account creation for {name}")
        return f"acc_mock_{hash(name) % 100000}"

    try:
        # Razorpay v2 Accounts API Payload for Route
        account_data = {
            "name": name,
            "email": email,
            "contact_name": name,
            "phone": phone,
            "type": "route",
            "legal_business_name": name,
            "profile": {
                "category": "sports",
                "subcategory": "sports_facility_providers",
                "addresses": {
                    "registered": {
                        "street1": "Not Provided",
                        "city": "Not Provided",
                        "state": "Not Provided",
                        "postal_code": "000000",
                        "country": "IN"
                    }
                }
            },
            "bank_account": {
                "ifsc_code": ifsc_code,
                "account_number": bank_account_number,
                "beneficiary_name": name
            }
        }
        
        response = client.account.create(data=account_data)
        
        account_id = response.get("id")
        if not account_id:
            raise ValueError("Account ID not found in Razorpay response.")
            
        logger.info(f"[RazorpayRoute] Successfully created linked account: {account_id}")
        return account_id
        
    except Exception as e:
        logger.error(f"[RazorpayRoute] Unexpected error creating linked account for {email}: {str(e)}")
        raise

def create_split_payment_order(total_order_amount_inr: float, vendor_account_id: str, vendor_transfer_amount_inr: float) -> dict:
    """
    Creates a Razorpay order with Route split payment (transfers).
    This function is strictly isolated as requested by the architect.
    """
    client = get_razorpay_client()
    if not client:
        logger.info(f"[RazorpayRoute] Mock split payment order created for total {total_order_amount_inr}")
        return {"id": f"order_mock_{hash(vendor_account_id) % 100000}"}

    try:
        # Convert INR to paise
        total_order_amount_paise = int(total_order_amount_inr * 100)
        vendor_transfer_amount_paise = int(vendor_transfer_amount_inr * 100)
        
        if vendor_transfer_amount_paise > total_order_amount_paise:
            raise ValueError("Transfer amount cannot exceed total order amount.")
            
        order_data = {
            "amount": total_order_amount_paise,
            "currency": "INR",
            "transfers": [
                {
                    "account": vendor_account_id,
                    "amount": vendor_transfer_amount_paise,
                    "currency": "INR",
                    "notes": {
                        "type": "vendor_payout"
                    },
                    "linked_account_notes": ["type"],
                    "on_hold": 0 # Set to 1 if you want to hold funds until fulfillment
                }
            ]
        }
        
        order = client.order.create(data=order_data)
        
        logger.info(f"[RazorpayRoute] Successfully created split payment order: {order.get('id')}")
        return order
        
    except Exception as e:
        logger.error(f"[RazorpayRoute] Unexpected error creating split payment order: {str(e)}")
        raise
