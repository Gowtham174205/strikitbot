"""
Unit tests for the redesigned STRIKIT PDF invoices and reports.
Checks that all 5 PDF generators run without exceptions and write valid PDF structures.
"""
import os
from datetime import datetime, timedelta
import pytest

from app.services.pdf_generator import (
    generate_revenue_report,
    generate_platform_report,
    generate_subscription_invoice,
    generate_booking_invoice,
    generate_refund_invoice
)

# Mock classes for test environment
class MockOwner:
    def __init__(self):
        self.id = 99
        self.name = "Test Owner"
        self.mobile = "919999999999"
        self.turfName = "Test Turf Arena"
        self.location = "Test Location Road, Chennai"
        self.gst = "33GSTIN1234A1Z1"
        self.msme = "UDYAM-TN-00-12345"

class MockSlot:
    def __init__(self):
        self.date = "2026-06-20"
        self.timeSlot = "08:00 PM"
        self.owner = MockOwner()

class MockBooking:
    def __init__(self):
        self.id = 7777
        self.slot = MockSlot()
        self.teamName = "Test FC"
        self.captainName = "Cap Test"
        self.captainPhone = "919999999998"
        self.totalPaidPaise = 105000
        self.ownerSharePaise = 100000
        self.platformFeePaise = 5000
        self.sport = "Football"
        self.paymentStatus = "VERIFIED"
        self.confirmedAt = datetime.utcnow()

class MockJoinRequest:
    def __init__(self):
        self.playerName = "Joiner Test"
        self.status = "ACCEPTED"


def test_pdf_generators(tmp_path):
    # Set output directory to temporary pytest path
    output_dir = str(tmp_path)
    
    owner = MockOwner()
    booking = MockBooking()
    join_request = MockJoinRequest()
    
    # 1. Owner Revenue Report
    rev_path = generate_revenue_report(owner, [booking], output_dir)
    assert os.path.exists(rev_path)
    assert os.path.getsize(rev_path) > 0
    # PDF magic signature checks
    with open(rev_path, "rb") as f:
        signature = f.read(4)
        assert signature == b"%PDF"
        
    # 2. Platform Report
    plat_path = generate_platform_report([booking], [join_request], output_dir)
    assert os.path.exists(plat_path)
    assert os.path.getsize(plat_path) > 0
    with open(plat_path, "rb") as f:
        assert f.read(4) == b"%PDF"
        
    # 3. Subscription Invoice
    sub_path = generate_subscription_invoice(
        owner=owner,
        invoice_num="SUB-TEST-123",
        amount_paise=69900,
        date_paid=datetime.utcnow(),
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow() + timedelta(days=30),
        output_dir=output_dir
    )
    assert os.path.exists(sub_path)
    assert os.path.getsize(sub_path) > 0
    with open(sub_path, "rb") as f:
        assert f.read(4) == b"%PDF"
        
    # 4. Booking Invoice
    book_path = generate_booking_invoice(booking, output_dir)
    assert os.path.exists(book_path)
    assert os.path.getsize(book_path) > 0
    with open(book_path, "rb") as f:
        assert f.read(4) == b"%PDF"
        
    # 5. Refund Invoice
    ref_path = generate_refund_invoice(
        booking=booking,
        refund_amount_paise=84000,
        refund_percentage=80,
        refund_date=datetime.utcnow(),
        txn_ref="ref_12345678",
        output_dir=output_dir
    )
    assert os.path.exists(ref_path)
    assert os.path.getsize(ref_path) > 0
    with open(ref_path, "rb") as f:
        assert f.read(4) == b"%PDF"
