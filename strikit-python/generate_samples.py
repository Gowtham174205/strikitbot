"""
Utility script to generate sample PDFs for all 5 document types
and send them directly to the configured Telegram chat.
"""
import os
import asyncio
from datetime import datetime, timedelta

# Setup paths so we can import app modules
import sys
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from app.services.pdf_generator import (
    generate_revenue_report,
    generate_platform_report,
    generate_subscription_invoice,
    generate_booking_invoice,
    generate_refund_invoice
)
from app.services.telegram_service import send_platform_report

# Mock Classes to avoid DB connection issues (greenlet error)
class MockOwner:
    def __init__(self):
        self.id = 12
        self.name = "Gowtham P"
        self.mobile = "918940095659"
        self.turfName = "STRIKIT Arena Elite"
        self.location = "Strikit Sports Hub, ECR Road, Chennai, Tamil Nadu - 600119"
        self.gst = "33AAAAA1111A1Z1"
        self.msme = "UDYAM-TN-01-0001234"
        self.subscriptionActive = True
        self.subscriptionExpiry = datetime.utcnow() + timedelta(days=20)

class MockSlot:
    def __init__(self, owner, date="2026-06-15", timeSlot="06:00 PM"):
        self.owner = owner
        self.date = date
        self.timeSlot = timeSlot

class MockBooking:
    def __init__(self, id, slot, teamName, captainName, captainPhone, totalPaidPaise, ownerSharePaise, platformFeePaise, sport="Football (5v5)", paymentStatus="VERIFIED"):
        self.id = id
        self.slot = slot
        self.teamName = teamName
        self.captainName = captainName
        self.captainPhone = captainPhone
        self.totalPaidPaise = totalPaidPaise
        self.ownerSharePaise = ownerSharePaise
        self.platformFeePaise = platformFeePaise
        self.sport = sport
        self.paymentStatus = paymentStatus
        self.confirmedAt = datetime.utcnow() - timedelta(hours=2)
        self.createdAt = datetime.utcnow() - timedelta(days=1)

class MockJoinRequest:
    def __init__(self, playerName, status="ACCEPTED"):
        self.playerName = playerName
        self.status = status
        self.createdAt = datetime.utcnow()


async def main():
    print("Initializing Mock Data for STRIKIT Enterprise PDF Redesign Samples...")
    owner = MockOwner()
    
    # Create slots
    slot1 = MockSlot(owner, "2026-06-15", "06:00 PM")
    slot2 = MockSlot(owner, "2026-06-15", "07:00 PM")
    slot3 = MockSlot(owner, "2026-06-16", "08:00 AM")
    
    # Create bookings (ALL money in paise)
    booking1 = MockBooking(1001, slot1, "Galacticos FC", "Sanjay Kumar", "919876543210", 125000, 120000, 5000, "Football (5v5)", "VERIFIED")
    booking2 = MockBooking(1002, slot2, "Thunderbolts", "Rajesh Pillai", "918889997777", 105000, 100000, 5000, "Cricket (7v7)", "VERIFIED")
    booking3 = MockBooking(1003, slot3, "Weekend Warriors", "Arun Prasath", "917776665555", 105000, 100000, 5000, "Football (5v5)", "REFUNDED")
    
    bookings_list = [booking1, booking2, booking3]
    
    # Create join requests
    joins_list = [
        MockJoinRequest("Vijay Raghavan", "ACCEPTED"),
        MockJoinRequest("Dinesh Karthik", "ACCEPTED")
    ]
    
    output_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate the 5 sample PDFs
    print("\nGenerating PDF Samples...")
    
    print("1. Owner Revenue Report...")
    rev_path = generate_revenue_report(owner, bookings_list, output_dir)
    print(f"   Saved to {rev_path}")
    
    print("2. Platform Earnings Report...")
    plat_path = generate_platform_report(bookings_list, joins_list, output_dir)
    print(f"   Saved to {plat_path}")
    
    print("3. Subscription Invoice...")
    # ₹699.00 = 69900 paise
    sub_path = generate_subscription_invoice(
        owner=owner,
        invoice_num="SUB-2026-1049",
        amount_paise=69900,
        date_paid=datetime.utcnow() - timedelta(days=2),
        start_date=datetime.utcnow() - timedelta(days=2),
        end_date=datetime.utcnow() + timedelta(days=28),
        output_dir=output_dir
    )
    print(f"   Saved to {sub_path}")
    
    print("4. Booking Invoice...")
    book_path = generate_booking_invoice(booking1, output_dir)
    print(f"   Saved to {book_path}")
    
    print("5. Refund Invoice...")
    # 80% refund of ₹1050.00 = ₹840.00 (84000 paise)
    ref_path = generate_refund_invoice(
        booking=booking3,
        refund_amount_paise=84000,
        refund_percentage=80,
        refund_date=datetime.utcnow(),
        txn_ref="pay_Rzp1234567Ref",
        output_dir=output_dir
    )
    print(f"   Saved to {ref_path}")
    
    print("\nSending PDFs to Telegram Chat...")
    
    pdf_files = [
        (rev_path, "📊 *STRIKIT Owner Revenue Report* (Redesigned SaaS Premium Style)"),
        (plat_path, "📈 *STRIKIT Platform Earnings Report* (Redesigned Central Network Style)"),
        (sub_path, "🧾 *STRIKIT Subscription Invoice* (Redesigned Enterprise B2B Style)"),
        (book_path, "🎫 *STRIKIT Player Booking Invoice* (Redesigned with Verification QR Code)"),
        (ref_path, "💸 *STRIKIT Refund Credit Note* (Redesigned Refund Receipt)")
    ]
    
    for path, caption in pdf_files:
        print(f"Sending {os.path.basename(path)}...")
        res = await send_platform_report(path, caption)
        if res.get("ok"):
            print(f"   Sent successfully! Message ID: {res.get('result', {}).get('message_id')}")
        else:
            print(f"   Failed to send to Telegram: {res.get('error') or res}")
            
    print("\nSample generation & Telegram dispatch complete!")

if __name__ == "__main__":
    asyncio.run(main())
