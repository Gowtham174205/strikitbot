"""
PDF Generator — ReportLab-based PDF reports for owners and platform admin.
Uses paise-to-rupees conversion for display. All internal values in paise.
Designed to enterprise SaaS quality with Montserrat and Inter fonts.
"""
import os
import logging
from datetime import datetime
from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage

logger = logging.getLogger(__name__)

# ── Dynamic Font Registration with Helvetica Fallbacks ──
FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

try:
    # Resolve absolute paths for fonts
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    font_path_regular = os.path.join(base_dir, "static", "fonts", "Inter-Regular.ttf")
    font_path_bold = os.path.join(base_dir, "static", "fonts", "Montserrat-Bold.ttf")

    if os.path.exists(font_path_regular):
        pdfmetrics.registerFont(TTFont("Inter", font_path_regular))
        FONT_REGULAR = "Inter"
    else:
        logger.warning(f"Inter font not found at {font_path_regular}, falling back to Helvetica")

    if os.path.exists(font_path_bold):
        pdfmetrics.registerFont(TTFont("Montserrat-Bold", font_path_bold))
        FONT_BOLD = "Montserrat-Bold"
    else:
        logger.warning(f"Montserrat font not found at {font_path_bold}, falling back to Helvetica-Bold")

except Exception as e:
    logger.error(f"Failed to register custom fonts: {e}")


# ── Two-Pass Canvas for Page Numbering, Watermark, & Footer ──
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages):
        self.saveState()

        # 1. Top Green Accent Strip
        self.setFillColor(colors.HexColor("#10B981"))
        self.rect(0, 782, 612, 10, fill=1, stroke=0)

        # 2. Watermark "STRIKIT" in center of the page
        self.setFillColor(colors.HexColor("#10B981"))
        self.setFillAlpha(0.04)  # Subtle 4% opacity
        self.setFont(FONT_BOLD, 68)
        self.translate(306, 396)
        self.rotate(45)
        self.drawCentredString(0, 0, "STRIKIT")
        self.restoreState()

        # 3. Footer Branded Bar
        self.saveState()
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.75)
        self.line(40, 50, 572, 50)

        self.setFont(FONT_BOLD, 8.5)
        self.setFillColor(colors.HexColor("#10B981"))
        self.drawString(40, 35, "Powered by STRIKIT")

        self.setFont(FONT_REGULAR, 8.5)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(140, 35, "•   Ultimate Sports Network")

        self.drawRightString(572, 35, "www.strikit.in")

        # Page Numbering
        page_num_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(572, 22, page_num_str)
        self.restoreState()


# ── Shared Layout Helpers ──

def _get_styles():
    """Get customized styles safely to avoid duplicate name errors."""
    styles = getSampleStyleSheet()
    custom_styles = {}

    custom_styles["Body"] = ParagraphStyle(
        name="StrikitBody",
        fontName=FONT_REGULAR,
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#334155")
    )
    custom_styles["BodyBold"] = ParagraphStyle(
        name="StrikitBodyBold",
        fontName=FONT_BOLD,
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#1E293B")
    )
    custom_styles["Title"] = ParagraphStyle(
        name="StrikitTitle",
        fontName=FONT_BOLD,
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#1E293B")
    )
    custom_styles["Subtitle"] = ParagraphStyle(
        name="StrikitSubtitle",
        fontName=FONT_REGULAR,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#64748B")
    )
    custom_styles["Heading"] = ParagraphStyle(
        name="StrikitHeading",
        fontName=FONT_BOLD,
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#1E293B")
    )
    custom_styles["SectionHeader"] = ParagraphStyle(
        name="StrikitSectionHeader",
        fontName=FONT_BOLD,
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#0F172A")
    )

    return custom_styles


def _get_logo_flowable(width=110):
    """Retrieve STRIKIT logo and maintain aspect ratio."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logo_path = os.path.join(base_dir, "logo.jpg")
    if os.path.exists(logo_path):
        try:
            with PILImage.open(logo_path) as img:
                w, h = img.size
                ratio = h / w
            return Image(logo_path, width=width, height=width * ratio)
        except Exception as e:
            logger.error(f"Error loading logo image: {e}")
    return None


def create_header_grid(title, doc_id_label=None, doc_id_value=None, status=None, status_color=None):
    """Generates standard dual-column branding header block."""
    logo = _get_logo_flowable()
    company_info = [
        Paragraph("STRIKIT NETWORK", ParagraphStyle("CompanyTitle", fontName=FONT_BOLD, fontSize=11, leading=13, textColor=colors.HexColor("#065F46"))),
        Paragraph("Ultimate Sports Network", ParagraphStyle("CompanySub", fontName=FONT_REGULAR, fontSize=8, leading=10, textColor=colors.HexColor("#64748B"))),
    ]
    left_flow = []
    if logo:
        left_flow.append(logo)
        left_flow.append(Spacer(1, 4))
    left_flow.extend(company_info)

    right_flow = [
        Paragraph(title.upper(), ParagraphStyle("DocTitle", fontName=FONT_BOLD, fontSize=15, leading=18, textColor=colors.HexColor("#1E293B"), alignment=2)),
        Spacer(1, 4),
    ]
    if doc_id_label and doc_id_value:
        right_flow.append(Paragraph(f"<b>{doc_id_label}:</b> {doc_id_value}", ParagraphStyle("DocId", fontName=FONT_REGULAR, fontSize=8.5, leading=11, textColor=colors.HexColor("#475569"), alignment=2)))

    right_flow.append(Paragraph(f"<b>Date:</b> {datetime.utcnow().strftime('%d %b %Y')}", ParagraphStyle("DocDate", fontName=FONT_REGULAR, fontSize=8.5, leading=11, textColor=colors.HexColor("#475569"), alignment=2)))

    if status:
        bg = "#ECFDF5" if status_color == "green" else "#FEF2F2" if status_color == "red" else "#FFFBEB"
        border = "#A7F3D0" if status_color == "green" else "#FCA5A5" if status_color == "red" else "#FDE68A"
        text_color = "#047857" if status_color == "green" else "#B91C1C" if status_color == "red" else "#D97706"

        status_para = Paragraph(status.upper(), ParagraphStyle("StatusTxt", fontName=FONT_BOLD, fontSize=8, leading=9, textColor=colors.HexColor(text_color), alignment=1))

        status_badge = Table([[status_para]], colWidths=[100])
        status_badge.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor(bg)),
            ('BOX', (0,0), (-1,-1), 0.75, colors.HexColor(border)),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ]))

        badge_align_table = Table([["", status_badge]], colWidths=[150, 100])
        badge_align_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        right_flow.append(badge_align_table)

    t = Table([[left_flow, right_flow]], colWidths=[250, 252])
    t.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    return t


def create_kpi_cards(cards_data):
    """Side-by-side KPI Summary metrics cards."""
    row = []
    for card in cards_data:
        label_style = ParagraphStyle(
            name=f"KPILabel_{card['label'][:6]}",
            fontName=FONT_REGULAR,
            fontSize=7.5,
            leading=9,
            textColor=colors.HexColor("#64748B" if not card.get("highlight") else "#047857")
        )
        val_style = ParagraphStyle(
            name=f"KPIVal_{card['label'][:6]}",
            fontName=FONT_BOLD,
            fontSize=14,
            leading=16,
            textColor=colors.HexColor("#0F172A" if not card.get("highlight") else "#065F46")
        )
        sub_style = ParagraphStyle(
            name=f"KPISub_{card['label'][:6]}",
            fontName=FONT_REGULAR,
            fontSize=7,
            leading=8.5,
            textColor=colors.HexColor("#475569" if not card.get("highlight") else "#047857")
        )

        cell_flowables = [
            Paragraph(card["label"].upper(), label_style),
            Spacer(1, 4),
            Paragraph(card["value"], val_style)
        ]
        if card.get("subtext"):
            cell_flowables.append(Spacer(1, 3))
            cell_flowables.append(Paragraph(card["subtext"], sub_style))

        bg = "#ECFDF5" if card.get("highlight") else "#F8FAFC"
        border = "#A7F3D0" if card.get("highlight") else "#E2E8F0"

        card_table = Table([[cell_flowables]], colWidths=[114])
        card_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor(bg)),
            ('BOX', (0,0), (-1,-1), 0.75, colors.HexColor(border)),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ]))
        row.append(card_table)

    wrapper_data = []
    col_widths = []
    if len(row) == 4:
        wrapper_data = [[row[0], "", row[1], "", row[2], "", row[3]]]
        col_widths = [118, 10, 118, 10, 118, 10, 118]
    else:
        wrapper_data = [[row[0], "", row[1], "", row[2]]]
        col_widths = [160, 11, 160, 11, 160]

    wrapper = Table(wrapper_data, colWidths=col_widths)
    wrapper.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    return wrapper


def create_meta_card(left_details: list, right_details: list):
    """Clean card grid for customer details / billing metadata."""
    left_content = []
    right_content = []

    style_label = ParagraphStyle("MetaLabel", fontName=FONT_BOLD, fontSize=8, leading=10, textColor=colors.HexColor("#64748B"))
    style_val = ParagraphStyle("MetaVal", fontName=FONT_REGULAR, fontSize=8.5, leading=11, textColor=colors.HexColor("#1E293B"))

    for label, val in left_details:
        left_content.append(Paragraph(f"<b>{label}:</b>", style_label))
        left_content.append(Paragraph(str(val), style_val))
        left_content.append(Spacer(1, 4))

    for label, val in right_details:
        right_content.append(Paragraph(f"<b>{label}:</b>", style_label))
        right_content.append(Paragraph(str(val), style_val))
        right_content.append(Spacer(1, 4))

    grid = Table([[left_content, right_content]], colWidths=[238, 238])
    grid.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))

    card = Table([[grid]], colWidths=[496])
    card.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
        ('BOX', (0,0), (-1,-1), 0.75, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
    ]))
    return card


def make_invoice_table(headers, rows, col_widths):
    """Unified tabular formatting with alternating row colors."""
    header_paras = [Paragraph(f"<b>{h}</b>", ParagraphStyle(f"Header_{h[:4]}", fontName=FONT_BOLD, fontSize=8, leading=9, textColor=colors.white)) for h in headers]
    table_data = [header_paras] + rows
    t = Table(table_data, colWidths=col_widths)

    style_commands = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E293B")),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('TOPPADDING', (0,0), (-1,0), 6),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,1), (-1,-1), 5),
        ('TOPPADDING', (0,1), (-1,-1), 5),
    ]

    for i in range(1, len(table_data)):
        if i % 2 == 0:
            style_commands.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor("#F8FAFC")))
        style_commands.append(('LINEBELOW', (0, i), (-1, i), 0.5, colors.HexColor("#E2E8F0")))

    t.setStyle(TableStyle(style_commands))
    return t


def _get_qr_flowable(booking_id):
    """Dynamic QR code generation embedded inside the document."""
    try:
        import qrcode
        qr_url = f"https://www.strikit.in/verify-booking/{booking_id}"
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=1,
        )
        qr.add_data(qr_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        import tempfile
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        temp_file_name = temp_file.name
        temp_file.close()

        img.save(temp_file_name)
        return Image(temp_file_name, width=80, height=80)
    except Exception as e:
        logger.error(f"Failed to generate QR code flowable: {e}")
        return None


# ── Core PDF Generators ──

def generate_revenue_report(owner, bookings: list, output_dir: str) -> str:
    """Generate turf owner revenue report PDF."""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"report_{getattr(owner, 'id', '0')}_{int(datetime.utcnow().timestamp())}.pdf"
    filepath = os.path.join(output_dir, filename)

    doc = SimpleDocTemplate(filepath, pagesize=LETTER, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=60)
    story = []

    # 1. Header Branded Grid
    owner_id = getattr(owner, "id", "N/A")
    story.append(create_header_grid("Turf Revenue Report", "Owner ID", str(owner_id)))
    story.append(Spacer(1, 15))

    # 2. Metadata Panel
    left_meta = [
        ("Turf Name", getattr(owner, "turfName", "N/A")),
        ("Owner Name", getattr(owner, "name", "N/A")),
        ("Mobile", getattr(owner, "mobile", "N/A")),
    ]
    right_meta = [
        ("GSTIN", getattr(owner, "gst", "N/A") or "N/A"),
        ("MSME Udyam", getattr(owner, "msme", "N/A") or "N/A"),
        ("Location", getattr(owner, "location", "N/A")[:45] + "..."),
    ]
    story.append(create_meta_card(left_meta, right_meta))
    story.append(Spacer(1, 15))

    # 3. Metrics Summary Cards
    from app.services.amount_service import paise_to_rupees
    total_bookings = len(bookings)
    gross_paise = sum(b.totalPaidPaise for b in bookings)
    fees_paise = sum(b.platformFeePaise for b in bookings)
    
    # Calculate refund summary
    refund_paise = sum(b.totalPaidPaise for b in bookings if getattr(b, "paymentStatus", "") == "REFUNDED")
    net_paise = gross_paise - fees_paise - refund_paise
    if net_paise < 0:
        net_paise = 0

    kpis = [
        {"label": "Total Bookings", "value": str(total_bookings)},
        {"label": "Gross Revenue", "value": f"INR {paise_to_rupees(gross_paise)}"},
        {"label": "Refund Amount", "value": f"INR {paise_to_rupees(refund_paise)}"},
        {"label": "Net Earnings", "value": f"INR {paise_to_rupees(net_paise)}", "highlight": True, "subtext": "Excluding platform fees"}
    ]
    story.append(create_kpi_cards(kpis))
    story.append(Spacer(1, 20))

    # 4. Alternating Row Table
    story.append(Paragraph("Detailed Transactions", ParagraphStyle("TxTitle", fontName=FONT_BOLD, fontSize=9.5, leading=12, textColor=colors.HexColor("#0F172A"))))
    story.append(Spacer(1, 8))

    headers = ["Date", "Slot Time", "Team / Captain", "Gross Paid", "Status", "Earning"]
    col_widths = [75, 75, 146, 70, 70, 60]

    rows = []
    cell_style = ParagraphStyle("RowCell", fontName=FONT_REGULAR, fontSize=8, leading=10, textColor=colors.HexColor("#334155"))
    cell_style_bold = ParagraphStyle("RowCellBold", fontName=FONT_BOLD, fontSize=8, leading=10, textColor=colors.HexColor("#0F172A"))

    for b in bookings:
        slot = getattr(b, "slot", None)
        slot_date = getattr(slot, "date", getattr(b, "_slot_date", "N/A"))
        slot_time = getattr(slot, "timeSlot", getattr(b, "_slot_time", "N/A"))
        
        team_cap = f"{b.teamName[:18]}\n({b.captainName[:15]})"
        status = getattr(b, "paymentStatus", "N/A")
        
        # Net Earning on row (Earning = total paid - platform fee, unless refunded)
        net_earning_paise = b.totalPaidPaise - b.platformFeePaise if status != "REFUNDED" else 0
        if net_earning_paise < 0:
            net_earning_paise = 0

        rows.append([
            Paragraph(str(slot_date), cell_style),
            Paragraph(str(slot_time), cell_style),
            Paragraph(team_cap.replace("\n", "<br/>"), cell_style),
            Paragraph(f"₹{paise_to_rupees(b.totalPaidPaise)}", cell_style),
            Paragraph(status, cell_style_bold),
            Paragraph(f"₹{paise_to_rupees(net_earning_paise)}", cell_style_bold)
        ])

    if not rows:
        rows.append([Paragraph("No bookings recorded in this period.", cell_style), "", "", "", "", ""])

    story.append(make_invoice_table(headers, rows, col_widths))

    doc.build(story, canvasmaker=NumberedCanvas)
    return filepath


def generate_platform_report(bookings: list, join_requests: list, output_dir: str) -> str:
    """Generate consolidated monthly platform report PDF."""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"platform_report_{int(datetime.utcnow().timestamp())}.pdf"
    filepath = os.path.join(output_dir, filename)

    doc = SimpleDocTemplate(filepath, pagesize=LETTER, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=60)
    story = []

    story.append(create_header_grid("Platform Monthly Report", "Period", datetime.utcnow().strftime("%B %Y")))
    story.append(Spacer(1, 15))

    # 1. Platform KPI Metrics Cards
    from app.services.amount_service import paise_to_rupees, PLATFORM_BOOKING_FEE_PAISE, PLATFORM_JOIN_FEE_PAISE
    total_bookings = len(bookings)
    booking_fees = total_bookings * PLATFORM_BOOKING_FEE_PAISE
    
    accepted_joins = [j for j in join_requests if getattr(j, "status", "") == "ACCEPTED"]
    total_joins = len(accepted_joins)
    join_fees = total_joins * PLATFORM_JOIN_FEE_PAISE
    
    net_platform_revenue = booking_fees + join_fees

    kpis = [
        {"label": "Total Bookings", "value": str(total_bookings), "subtext": f"₹{paise_to_rupees(PLATFORM_BOOKING_FEE_PAISE)} per booking"},
        {"label": "Booking Fees", "value": f"INR {paise_to_rupees(booking_fees)}"},
        {"label": "Single Player Joins", "value": f"INR {paise_to_rupees(join_fees)}", "subtext": f"{total_joins} players joined"},
        {"label": "Platform Revenue", "value": f"INR {paise_to_rupees(net_platform_revenue)}", "highlight": True, "subtext": "Booking + Join Fees"}
    ]
    story.append(create_kpi_cards(kpis))
    story.append(Spacer(1, 20))

    # 2. Transaction Breakdown Table
    story.append(Paragraph("Consolidated Transactions Breakdown", ParagraphStyle("TxPlatformTitle", fontName=FONT_BOLD, fontSize=9.5, leading=12, textColor=colors.HexColor("#0F172A"))))
    story.append(Spacer(1, 8))

    headers = ["Turf / Owner", "Transaction Type", "Details", "Booking Amount", "Platform Fee"]
    col_widths = [136, 100, 130, 80, 50]

    rows = []
    cell_style = ParagraphStyle("PlatCell", fontName=FONT_REGULAR, fontSize=8, leading=10, textColor=colors.HexColor("#334155"))
    cell_style_bold = ParagraphStyle("PlatCellBold", fontName=FONT_BOLD, fontSize=8, leading=10, textColor=colors.HexColor("#0F172A"))

    # Render bookings
    for b in bookings:
        slot = getattr(b, "slot", None)
        owner_name = getattr(slot.owner, "turfName", "Unknown Turf") if slot and getattr(slot, "owner", None) else "Unknown Turf"
        slot_str = f"{getattr(slot, 'date', 'N/A')} @ {getattr(slot, 'timeSlot', 'N/A')}"
        rows.append([
            Paragraph(owner_name, cell_style_bold),
            Paragraph("Team Booking", cell_style),
            Paragraph(slot_str, cell_style),
            Paragraph(f"₹{paise_to_rupees(b.totalPaidPaise)}", cell_style),
            Paragraph(f"₹{paise_to_rupees(PLATFORM_BOOKING_FEE_PAISE)}", cell_style_bold)
        ])

    # Render join requests
    for j in accepted_joins:
        booking = getattr(j, "booking", None)
        slot = getattr(booking, "slot", None) if booking else None
        owner_name = getattr(slot.owner, "turfName", "Unknown Turf") if slot and getattr(slot, "owner", None) else "Unknown Turf"
        rows.append([
            Paragraph(owner_name, cell_style_bold),
            Paragraph("Player Join", cell_style),
            Paragraph(f"Player: {j.playerName[:20]}", cell_style),
            Paragraph("N/A", cell_style),
            Paragraph(f"₹{paise_to_rupees(PLATFORM_JOIN_FEE_PAISE)}", cell_style_bold)
        ])

    if not rows:
        rows.append([Paragraph("No transactions recorded.", cell_style), "", "", "", ""])

    story.append(make_invoice_table(headers, rows, col_widths))

    doc.build(story, canvasmaker=NumberedCanvas)
    return filepath


def generate_subscription_invoice(owner, invoice_num: str, amount_paise: int, date_paid: datetime, start_date: datetime, end_date: datetime, output_dir: str) -> str:
    """Generate professional B2B subscription invoice PDF."""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"subscription_invoice_{invoice_num}_{int(datetime.utcnow().timestamp())}.pdf"
    filepath = os.path.join(output_dir, filename)

    doc = SimpleDocTemplate(filepath, pagesize=LETTER, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=60)
    story = []

    story.append(create_header_grid("Subscription Invoice", "Invoice No", invoice_num, "PAID", "green"))
    story.append(Spacer(1, 15))

    # Metadata card
    owner_name = getattr(owner, "name", "N/A")
    turf_name = getattr(owner, "turfName", "N/A")
    owner_mobile = getattr(owner, "mobile", "N/A")
    owner_gst = getattr(owner, "gst", "N/A") or "N/A"

    left_meta = [
        ("Customer Name", owner_name),
        ("Turf Name", turf_name),
        ("Mobile Number", owner_mobile)
    ]
    right_meta = [
        ("Customer GSTIN", owner_gst),
        ("Billing Period", f"{start_date.strftime('%d %b %Y')} - {end_date.strftime('%d %b %Y')}"),
        ("Date of Payment", date_paid.strftime('%d %b %Y %I:%M %p'))
    ]
    story.append(create_meta_card(left_meta, right_meta))
    story.append(Spacer(1, 15))

    # Invoice Details Table
    headers = ["Subscription Item", "Duration", "Start Date", "End Date", "Total Paid"]
    col_widths = [196, 70, 80, 80, 70]

    from app.services.amount_service import paise_to_rupees
    cell_style = ParagraphStyle("SubInvoiceCell", fontName=FONT_REGULAR, fontSize=8.5, leading=11, textColor=colors.HexColor("#334155"))
    cell_style_bold = ParagraphStyle("SubInvoiceCellBold", fontName=FONT_BOLD, fontSize=8.5, leading=11, textColor=colors.HexColor("#0F172A"))

    row_data = [
        Paragraph("STRIKIT Ultimate Sports Network — Monthly Bot Subscription", cell_style_bold),
        Paragraph("30 Days", cell_style),
        Paragraph(start_date.strftime('%d %b %Y'), cell_style),
        Paragraph(end_date.strftime('%d %b %Y'), cell_style),
        Paragraph(f"₹{paise_to_rupees(amount_paise)}", cell_style_bold)
    ]
    story.append(make_invoice_table(headers, [row_data], col_widths))
    story.append(Spacer(1, 15))

    # Tax breakdown summary cards
    # If GST is available, we display CGST (9%) and SGST (9%), otherwise we show tax excluded
    has_gst = owner_gst != "N/A"
    total_paid_rupees = amount_paise / 100.0
    
    if has_gst:
        base_amount = total_paid_rupees / 1.18
        tax_amount = total_paid_rupees - base_amount
        cgst = tax_amount / 2.0
        sgst = tax_amount / 2.0
        
        base_str = f"₹{base_amount:.2f}"
        tax_str = f"₹{tax_amount:.2f} (18% GST)"
        cgst_str = f"CGST (9%): ₹{cgst:.2f}\nSGST (9%): ₹{sgst:.2f}"
    else:
        base_str = f"₹{total_paid_rupees:.2f}"
        tax_str = "₹0.00 (Exempt)"
        cgst_str = "N/A"

    kpis = [
        {"label": "Subtotal", "value": base_str},
        {"label": "GST Tax Breakdown", "value": tax_str, "subtext": cgst_str.replace("\n", "<br/>")},
        {"label": "Total Paid Amount", "value": f"INR {total_paid_rupees:.2f}", "highlight": True, "subtext": "Recurring Subscription"}
    ]
    story.append(create_kpi_cards(kpis))

    doc.build(story, canvasmaker=NumberedCanvas)
    return filepath


def generate_booking_invoice(booking, output_dir: str) -> str:
    """Generate player booking invoice/receipt PDF with QR verification code."""
    os.makedirs(output_dir, exist_ok=True)
    booking_id = getattr(booking, "id", 0)
    filename = f"booking_receipt_{booking_id}_{int(datetime.utcnow().timestamp())}.pdf"
    filepath = os.path.join(output_dir, filename)

    doc = SimpleDocTemplate(filepath, pagesize=LETTER, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=60)
    story = []

    story.append(create_header_grid("Booking Receipt", "Booking ID", f"STK-{booking_id}", "PAID", "green"))
    story.append(Spacer(1, 15))

    # Metadata details
    slot = getattr(booking, "slot", None)
    slot_date = getattr(slot, "date", getattr(booking, "_slot_date", "N/A"))
    slot_time = getattr(slot, "timeSlot", getattr(booking, "_slot_time", "N/A"))
    owner = getattr(slot, "owner", None) if slot else None
    turf_name = getattr(owner, "turfName", "Unknown Turf") if owner else "Unknown Turf"

    left_meta = [
        ("Turf Location Name", turf_name),
        ("Sport / Category", getattr(booking, "sport", "N/A") or "N/A"),
        ("Booking Date / Time", f"{slot_date} @ {slot_time}")
    ]
    right_meta = [
        ("Captain Name", getattr(booking, "captainName", "N/A")),
        ("Phone Number", getattr(booking, "captainPhone", "N/A")),
        ("Confirmed At", getattr(booking, "confirmedAt", datetime.utcnow()).strftime('%d %b %Y %I:%M %p'))
    ]
    story.append(create_meta_card(left_meta, right_meta))
    story.append(Spacer(1, 15))

    # Payment split details table
    headers = ["Description", "Turf Share", "Platform Booking Fee", "Total Paid"]
    col_widths = [226, 90, 90, 90]

    from app.services.amount_service import paise_to_rupees
    cell_style = ParagraphStyle("BookCell", fontName=FONT_REGULAR, fontSize=8.5, leading=11, textColor=colors.HexColor("#334155"))
    cell_style_bold = ParagraphStyle("BookCellBold", fontName=FONT_BOLD, fontSize=8.5, leading=11, textColor=colors.HexColor("#0F172A"))

    row_data = [
        Paragraph(f"STRIKIT Booking reservation for slot: {slot_date} {slot_time}", cell_style_bold),
        Paragraph(f"₹{paise_to_rupees(booking.ownerSharePaise)}", cell_style),
        Paragraph(f"₹{paise_to_rupees(booking.platformFeePaise)}", cell_style),
        Paragraph(f"₹{paise_to_rupees(booking.totalPaidPaise)}", cell_style_bold)
    ]
    story.append(make_invoice_table(headers, [row_data], col_widths))
    story.append(Spacer(1, 15))

    # QR Code + Summary breakdown layout side-by-side
    qr = _get_qr_flowable(booking_id)
    
    breakdown_flow = []
    lbl_style = ParagraphStyle("BrkLabel", fontName=FONT_REGULAR, fontSize=8, leading=10, textColor=colors.HexColor("#64748B"))
    val_style = ParagraphStyle("BrkVal", fontName=FONT_BOLD, fontSize=8.5, leading=11, textColor=colors.HexColor("#1E293B"))
    total_val_style = ParagraphStyle("BrkTotalVal", fontName=FONT_BOLD, fontSize=12, leading=14, textColor=colors.HexColor("#047857"))
    
    breakdown_flow.append(Paragraph("<b>Turf Share Amount:</b>", lbl_style))
    breakdown_flow.append(Paragraph(f"₹{paise_to_rupees(booking.ownerSharePaise)}", val_style))
    breakdown_flow.append(Spacer(1, 4))
    
    breakdown_flow.append(Paragraph("<b>STRIKIT Platform Fee:</b>", lbl_style))
    breakdown_flow.append(Paragraph(f"₹{paise_to_rupees(booking.platformFeePaise)}", val_style))
    breakdown_flow.append(Spacer(1, 4))
    
    breakdown_flow.append(Paragraph("<b>Total Amount Paid (INR):</b>", lbl_style))
    breakdown_flow.append(Paragraph(f"₹{paise_to_rupees(booking.totalPaidPaise)}", total_val_style))

    breakdown_card = Table([[breakdown_flow]], colWidths=[200])
    breakdown_card.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#ECFDF5")),
        ('BOX', (0,0), (-1,-1), 0.75, colors.HexColor("#A7F3D0")),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
    ]))

    qr_block = []
    if qr:
        qr_block.append(qr)
        qr_block.append(Spacer(1, 4))
        qr_block.append(Paragraph("<font size=7 color='#64748B'>Scan QR to verify booking status</font>", ParagraphStyle("QrLbl", fontName=FONT_REGULAR, fontSize=7, leading=8, alignment=1)))

    bottom_grid = Table([[qr_block, "", breakdown_card]], colWidths=[110, 186, 200])
    bottom_grid.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    
    story.append(bottom_grid)

    doc.build(story, canvasmaker=NumberedCanvas)
    return filepath


def generate_refund_invoice(booking, refund_amount_paise: int, refund_percentage: int, refund_date: datetime, txn_ref: str, output_dir: str) -> str:
    """Generate credit note/refund invoice PDF."""
    os.makedirs(output_dir, exist_ok=True)
    booking_id = getattr(booking, "id", 0)
    filename = f"refund_receipt_{booking_id}_{int(datetime.utcnow().timestamp())}.pdf"
    filepath = os.path.join(output_dir, filename)

    doc = SimpleDocTemplate(filepath, pagesize=LETTER, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=60)
    story = []

    story.append(create_header_grid("Refund Receipt", "Credit Note No", f"REF-{booking_id}", "REFUNDED", "red"))
    story.append(Spacer(1, 15))

    slot = getattr(booking, "slot", None)
    slot_date = getattr(slot, "date", getattr(booking, "_slot_date", "N/A"))
    slot_time = getattr(slot, "timeSlot", getattr(booking, "_slot_time", "N/A"))
    owner = getattr(slot, "owner", None) if slot else None
    turf_name = getattr(owner, "turfName", "Unknown Turf") if owner else "Unknown Turf"

    left_meta = [
        ("Original Booking ID", f"STK-{booking_id}"),
        ("Turf Name", turf_name),
        ("Captain Name", getattr(booking, "captainName", "N/A"))
    ]
    right_meta = [
        ("Original Booking Date", f"{slot_date} @ {slot_time}"),
        ("Refund Processing Date", refund_date.strftime('%d %b %Y %I:%M %p')),
        ("Transaction Reference", txn_ref or "N/A")
    ]
    story.append(create_meta_card(left_meta, right_meta))
    story.append(Spacer(1, 15))

    # Refund table details
    headers = ["Item Description", "Original Paid Amount", "Refund Policy Apply", "Net Refunded Amount"]
    col_widths = [226, 90, 90, 90]

    from app.services.amount_service import paise_to_rupees
    cell_style = ParagraphStyle("RefCell", fontName=FONT_REGULAR, fontSize=8.5, leading=11, textColor=colors.HexColor("#334155"))
    cell_style_bold = ParagraphStyle("RefCellBold", fontName=FONT_BOLD, fontSize=8.5, leading=11, textColor=colors.HexColor("#1E293B"))
    cell_style_alert = ParagraphStyle("RefCellAlert", fontName=FONT_BOLD, fontSize=8.5, leading=11, textColor=colors.HexColor("#B91C1C"))

    row_data = [
        Paragraph(f"Refund credit note for reservation: {slot_date} {slot_time}", cell_style_bold),
        Paragraph(f"₹{paise_to_rupees(booking.totalPaidPaise)}", cell_style),
        Paragraph(f"{refund_percentage}% Refund", cell_style),
        Paragraph(f"₹{paise_to_rupees(refund_amount_paise)}", cell_style_alert)
    ]
    story.append(make_invoice_table(headers, [row_data], col_widths))
    story.append(Spacer(1, 15))

    # Card detailing refund status
    lbl_style = ParagraphStyle("RefCardLbl", fontName=FONT_REGULAR, fontSize=8, leading=10, textColor=colors.HexColor("#7F1D1D"))
    val_style = ParagraphStyle("RefCardVal", fontName=FONT_BOLD, fontSize=11, leading=13, textColor=colors.HexColor("#991B1B"))
    
    card_flow = [
        Paragraph("<b>Refund Status:</b>", lbl_style),
        Paragraph("REFUNDED SUCCESSFUL", val_style),
        Spacer(1, 4),
        Paragraph("The amount has been credited back to your original source of payment according to banking standards (typically 5-7 business days).", ParagraphStyle("RefCardDesc", fontName=FONT_REGULAR, fontSize=8, leading=11, textColor=colors.HexColor("#991B1B")))
    ]
    
    refund_card = Table([[card_flow]], colWidths=[496])
    refund_card.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FEF2F2")),
        ('BOX', (0,0), (-1,-1), 0.75, colors.HexColor("#FCA5A5")),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(refund_card)

    doc.build(story, canvasmaker=NumberedCanvas)
    return filepath
