"""
PDF Generator — ReportLab-based PDF reports for owners and platform admin.
Uses paise-to-rupees conversion for display. All internal values in paise.
"""
import os
from datetime import datetime
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas


def _draw_accent_bar(c: canvas.Canvas, width=612):
    c.setFillColor(HexColor("#10b981"))
    c.rect(0, 780, width, 12, fill=1, stroke=0)


def _draw_footer(c: canvas.Canvas, y=50):
    c.setStrokeColor(HexColor("#cbd5e1"))
    c.setLineWidth(0.5)
    c.line(50, y + 20, 562, y + 20)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(HexColor("#10b981"))
    c.drawCentredString(306, y + 8, "Powered by STRIKIT")
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#64748b"))
    c.drawCentredString(306, y - 4, "Thank you for partnering with STRIKIT! For support, contact STRIKIT developer.")


def generate_revenue_report(owner, bookings: list, output_dir: str) -> str:
    """Generate owner revenue report PDF. Returns file path."""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"report_{owner.id}_{int(datetime.utcnow().timestamp())}.pdf"
    filepath = os.path.join(output_dir, filename)

    c = canvas.Canvas(filepath, pagesize=LETTER)
    w, h = LETTER

    _draw_accent_bar(c)

    # Header
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(HexColor("#10b981"))
    c.drawString(50, 750, "STRIKIT")
    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor("#64748b"))
    c.drawString(50, 736, "Automating Turf Bookings & Connecting Players")

    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(HexColor("#1e293b"))
    c.drawString(50, 710, "TURF REVENUE REPORT")

    # Metadata
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(HexColor("#1e293b"))
    y = 685
    c.drawString(65, y, "Turf Name:")
    c.setFont("Helvetica", 9)
    c.drawString(135, y, str(owner.turfName))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(65, y - 15, "Owner:")
    c.setFont("Helvetica", 9)
    c.drawString(135, y - 15, str(owner.name))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(65, y - 30, "Date:")
    c.setFont("Helvetica", 9)
    c.drawString(135, y - 30, datetime.utcnow().strftime("%d %b %Y"))

    # Metrics
    total_bookings = len(bookings)
    from app.services.amount_service import paise_to_rupees
    gross_paise = sum(b.totalPaidPaise for b in bookings)
    fees_paise = sum(b.platformFeePaise for b in bookings)
    net_paise = gross_paise - fees_paise

    y = 620
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#64748b"))
    c.drawString(60, y, "TOTAL BOOKINGS")
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(HexColor("#0f172a"))
    c.drawString(60, y - 14, str(total_bookings))

    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#64748b"))
    c.drawString(220, y, "GROSS REVENUE")
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(HexColor("#0f172a"))
    c.drawString(220, y - 14, f"INR {paise_to_rupees(gross_paise)}")

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(HexColor("#047857"))
    c.drawString(400, y, "NET TURF EARNINGS")
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(HexColor("#065f46"))
    c.drawString(400, y - 14, f"INR {paise_to_rupees(net_paise)}")

    # Table header
    y = 575
    c.setFillColor(HexColor("#1e293b"))
    c.rect(50, y, 512, 18, fill=1, stroke=0)
    c.setFillColor(HexColor("#ffffff"))
    c.setFont("Helvetica-Bold", 8)
    c.drawString(60, y + 5, "Date")
    c.drawString(140, y + 5, "Time Slot")
    c.drawString(240, y + 5, "Team")
    c.drawString(360, y + 5, "Captain")
    c.drawString(470, y + 5, "Amount")

    y -= 18
    for i, b in enumerate(bookings):
        if y < 60:
            _draw_footer(c)
            c.showPage()
            _draw_accent_bar(c)
            y = 750

        if i % 2 == 0:
            c.setFillColor(HexColor("#f8fafc"))
            c.rect(50, y, 512, 18, fill=1, stroke=0)

        c.setFillColor(HexColor("#334155"))
        c.setFont("Helvetica", 8)
        slot_date = getattr(b, '_slot_date', 'N/A')
        slot_time = getattr(b, '_slot_time', 'N/A')
        c.drawString(60, y + 5, str(slot_date))
        c.drawString(140, y + 5, str(slot_time))
        c.drawString(240, y + 5, str(b.teamName)[:20])
        c.drawString(360, y + 5, str(b.captainName)[:20])
        c.drawString(470, y + 5, f"INR {paise_to_rupees(b.totalPaidPaise)}")
        y -= 18

    _draw_footer(c)
    c.save()
    return filepath


def generate_platform_report(bookings: list, join_requests: list, output_dir: str) -> str:
    """Generate consolidated platform report PDF. Returns file path."""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"platform_report_{int(datetime.utcnow().timestamp())}.pdf"
    filepath = os.path.join(output_dir, filename)

    from app.services.amount_service import paise_to_rupees, PLATFORM_BOOKING_FEE_PAISE, PLATFORM_JOIN_FEE_PAISE

    c = canvas.Canvas(filepath, pagesize=LETTER)
    _draw_accent_bar(c)

    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(HexColor("#10b981"))
    c.drawString(50, 750, "STRIKIT CENTRAL NETWORK")
    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor("#64748b"))
    c.drawString(50, 736, "Consolidated Monthly Platform Revenue & Analytics")

    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(HexColor("#1e293b"))
    c.drawString(50, 710, "MONTHLY PLATFORM EARNINGS REPORT")

    # Metrics
    total_bookings = len(bookings)
    booking_fees = total_bookings * PLATFORM_BOOKING_FEE_PAISE
    total_joins = len([j for j in join_requests if getattr(j, 'status', '') == 'ACCEPTED'])
    join_fees = total_joins * PLATFORM_JOIN_FEE_PAISE
    net_revenue = booking_fees + join_fees

    y = 660
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#64748b"))
    c.drawString(60, y, f"BOOKING FEES (₹{paise_to_rupees(PLATFORM_BOOKING_FEE_PAISE)} each)")
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(HexColor("#0f172a"))
    c.drawString(60, y - 14, f"INR {paise_to_rupees(booking_fees)}")
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#475569"))
    c.drawString(60, y - 28, f"({total_bookings} bookings)")

    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#64748b"))
    c.drawString(220, y, f"JOIN FEES (₹{paise_to_rupees(PLATFORM_JOIN_FEE_PAISE)} each)")
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(HexColor("#0f172a"))
    c.drawString(220, y - 14, f"INR {paise_to_rupees(join_fees)}")
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#475569"))
    c.drawString(220, y - 28, f"({total_joins} joins)")

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(HexColor("#047857"))
    c.drawString(400, y, "NET PLATFORM REVENUE")
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(HexColor("#065f46"))
    c.drawString(400, y - 14, f"INR {paise_to_rupees(net_revenue)}")

    _draw_footer(c)
    c.save()
    return filepath
