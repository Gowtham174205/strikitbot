import PDFDocument from 'pdfkit';
import fs from 'fs';
import path from 'path';

/**
 * Helper to draw a top accent bar on the PDF page
 */
function drawAccentBar(doc) {
  doc.rect(0, 0, 612, 12).fill('#10b981');
}

/**
 * Helper to draw a professional footer branding at the bottom of the page
 */
function drawFooterBranding(doc, yPosition = 740) {
  // Divider line
  doc
    .moveTo(50, yPosition)
    .lineTo(562, yPosition)
    .strokeColor('#cbd5e1')
    .lineWidth(0.5)
    .stroke();

  // "Powered by STRIKIT" brand text
  doc
    .fontSize(9)
    .font('Helvetica-Bold')
    .fillColor('#10b981')
    .text('Powered by STRIKIT', 50, yPosition + 10, { align: 'center' });

  // Developer Support note
  doc
    .font('Helvetica')
    .fillColor('#64748b')
    .fontSize(8)
    .text('Thank you for partnering with STRIKIT! For support, contact STRIKIT developer.', 50, yPosition + 22, { align: 'center' });
}

/**
 * Generates an Owner Revenue Report PDF
 * @param {Object} owner - Owner details
 * @param {Array} bookings - List of bookings
 * @param {String} outputDir - Directory to save PDF
 * @returns {String} Absolute path to the generated PDF
 */
export function generateRevenueReport(owner, bookings, outputDir) {
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  const filename = `report_${owner.id}_${Date.now()}.pdf`;
  const filePath = path.join(outputDir, filename);

  const doc = new PDFDocument({ margin: 50, size: 'LETTER' });
  const writeStream = fs.createWriteStream(filePath);
  doc.pipe(writeStream);

  // Draw accent bar on page 1
  drawAccentBar(doc);

  // Logo Image (right header)
  const logoPath = path.join(process.cwd(), 'src', 'logo.jpg');
  if (fs.existsSync(logoPath)) {
    doc.image(logoPath, 440, 25, { width: 120 });
  }

  // Header Title
  doc
    .fillColor('#10b981')
    .font('Helvetica-Bold')
    .fontSize(22)
    .text('STRIKIT', 50, 30)
    .fillColor('#64748b')
    .font('Helvetica')
    .fontSize(9)
    .text('Automating Turf Bookings & Connecting Players', 50, 56);

  doc
    .fillColor('#1e293b')
    .font('Helvetica-Bold')
    .fontSize(14)
    .text('TURF REVENUE REPORT', 50, 90);

  // Metadata Card
  const metaY = 112;
  doc.rect(50, metaY, 512, 85).fill('#f8fafc');
  doc.rect(50, metaY, 512, 85).strokeColor('#cbd5e1').lineWidth(0.5).stroke();

  doc.fillColor('#1e293b').fontSize(9);

  // Left Column Metadata
  doc
    .font('Helvetica-Bold').text('Turf Name:', 65, metaY + 12)
    .font('Helvetica').text(owner.turfName, 135, metaY + 12)
    .font('Helvetica-Bold').text('Owner Name:', 65, metaY + 30)
    .font('Helvetica').text(owner.name, 135, metaY + 30)
    .font('Helvetica-Bold').text('Mobile:', 65, metaY + 48)
    .font('Helvetica').text(owner.mobile, 135, metaY + 48)
    .font('Helvetica-Bold').text('Location:', 65, metaY + 66)
    .font('Helvetica').text(owner.location.substring(0, 50), 135, metaY + 66);

  // Right Column Metadata
  doc
    .font('Helvetica-Bold').text('Date Generated:', 320, metaY + 12)
    .font('Helvetica').text(new Date().toLocaleDateString(), 420, metaY + 12)
    .font('Helvetica-Bold').text('GSTIN:', 320, metaY + 30)
    .font('Helvetica').text(owner.gst || 'N/A', 420, metaY + 30)
    .font('Helvetica-Bold').text('MSME Udyam:', 320, metaY + 48)
    .font('Helvetica').text(owner.msme || 'N/A', 420, metaY + 48);

  // Metrics summary
  const totalBookings = bookings.length;
  const grossRevenue = bookings.reduce((sum, b) => sum + b.amountPaid, 0);
  const platformFees = totalBookings * 30; // ₹30 per booking
  const netEarnings = grossRevenue - platformFees;

  // Draw 3 Metrics Cards
  const cardY = 212;
  const cardWidth = 160;
  const cardHeight = 55;
  const gap = 16;

  // Card 1: Total Bookings
  doc.rect(50, cardY, cardWidth, cardHeight).fill('#f1f5f9');
  doc.rect(50, cardY, cardWidth, cardHeight).strokeColor('#cbd5e1').lineWidth(0.5).stroke();
  doc.fillColor('#64748b').font('Helvetica').fontSize(8).text('TOTAL BOOKINGS', 60, cardY + 10);
  doc.fillColor('#0f172a').font('Helvetica-Bold').fontSize(16).text(totalBookings.toString(), 60, cardY + 24);

  // Card 2: Gross Revenue
  doc.rect(50 + cardWidth + gap, cardY, cardWidth, cardHeight).fill('#f1f5f9');
  doc.rect(50 + cardWidth + gap, cardY, cardWidth, cardHeight).strokeColor('#cbd5e1').lineWidth(0.5).stroke();
  doc.fillColor('#64748b').font('Helvetica').fontSize(8).text('GROSS REVENUE', 50 + cardWidth + gap + 10, cardY + 10);
  doc.fillColor('#0f172a').font('Helvetica-Bold').fontSize(16).text(`INR ${grossRevenue.toFixed(2)}`, 50 + cardWidth + gap + 10, cardY + 24);

  // Card 3: Net Turf Earnings (Green Highlighted)
  doc.rect(50 + (cardWidth + gap) * 2, cardY, cardWidth, cardHeight).fill('#ecfdf5');
  doc.rect(50 + (cardWidth + gap) * 2, cardY, cardWidth, cardHeight).strokeColor('#a7f3d0').lineWidth(0.5).stroke();
  doc.fillColor('#047857').font('Helvetica-Bold').fontSize(8).text('NET TURF EARNINGS', 50 + (cardWidth + gap) * 2 + 10, cardY + 10);
  doc.fillColor('#065f46').font('Helvetica-Bold').fontSize(16).text(`INR ${netEarnings.toFixed(2)}`, 50 + (cardWidth + gap) * 2 + 10, cardY + 24);

  // Bookings Detailed Table Headers
  const tableTop = 290;
  
  // Shaded header bar
  doc.rect(50, tableTop, 512, 20).fill('#1e293b');
  doc.fillColor('#ffffff').font('Helvetica-Bold').fontSize(8.5);
  doc
    .text('Date', 60, tableTop + 6)
    .text('Time Slot', 140, tableTop + 6)
    .text('Team Name', 230, tableTop + 6)
    .text('Captain Name', 350, tableTop + 6)
    .text('Amount Paid', 470, tableTop + 6);

  // Booking rows
  let y = tableTop + 20;
  let isRowEven = false;

  bookings.forEach((booking) => {
    // Page overflow handler
    if (y > 700) {
      drawFooterBranding(doc, 735);
      doc.addPage();
      drawAccentBar(doc);
      y = 45; // top of new page
      
      // Reprint headers on new page
      doc.rect(50, y, 512, 20).fill('#1e293b');
      doc.fillColor('#ffffff').font('Helvetica-Bold').fontSize(8.5);
      doc
        .text('Date', 60, y + 6)
        .text('Time Slot', 140, y + 6)
        .text('Team Name', 230, y + 6)
        .text('Captain Name', 350, y + 6)
        .text('Amount Paid', 470, y + 6);
      y += 20;
    }

    // Row Background Shading
    doc.rect(50, y, 512, 20).fill(isRowEven ? '#f8fafc' : '#ffffff');

    // Row Data
    doc
      .font('Helvetica')
      .fontSize(8)
      .fillColor('#334155')
      .text(booking.slot.date, 60, y + 6)
      .text(booking.slot.timeSlot, 140, y + 6)
      .text(booking.teamName.substring(0, 20), 230, y + 6)
      .text(booking.captainName.substring(0, 20), 350, y + 6)
      .text(`INR ${booking.amountPaid.toFixed(2)}`, 470, y + 6);

    // Bottom cell border line
    doc
      .moveTo(50, y + 20)
      .lineTo(562, y + 20)
      .strokeColor('#e2e8f0')
      .lineWidth(0.5)
      .stroke();

    y += 20;
    isRowEven = !isRowEven;
  });

  // Footer branding at bottom of page
  drawFooterBranding(doc, 735);

  doc.end();
  return filePath;
}

/**
 * Generates a Consolidated Platform Report PDF for STRIKIT admin
 * @param {Array} bookings - List of all bookings
 * @param {Array} joinRequests - List of accepted join requests
 * @param {String} outputDir - Directory to save PDF
 * @returns {Promise<String>} Absolute path to the generated PDF
 */
export function generatePlatformReport(bookings, joinRequests, outputDir) {
  return new Promise((resolve, reject) => {
    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }

    const filename = `platform_report_${Date.now()}.pdf`;
    const filePath = path.join(outputDir, filename);

    const doc = new PDFDocument({ margin: 50, size: 'LETTER' });
    const writeStream = fs.createWriteStream(filePath);

    writeStream.on('finish', () => {
      resolve(filePath);
    });

    writeStream.on('error', (err) => {
      reject(err);
    });

    doc.pipe(writeStream);

    // Draw accent bar on page 1
    drawAccentBar(doc);

    // Logo Image (right header)
    const logoPath = path.join(process.cwd(), 'src', 'logo.jpg');
    if (fs.existsSync(logoPath)) {
      doc.image(logoPath, 440, 25, { width: 120 });
    }

    // Header Title
    doc
      .fillColor('#10b981')
      .font('Helvetica-Bold')
      .fontSize(22)
      .text('STRIKIT CENTRAL NETWORK', 50, 30)
      .fillColor('#64748b')
      .font('Helvetica')
      .fontSize(9)
      .text('Consolidated Monthly Platform Revenue & Analytics', 50, 56);

    doc
      .fillColor('#1e293b')
      .font('Helvetica-Bold')
      .fontSize(14)
      .text('MONTHLY PLATFORM EARNINGS REPORT', 50, 90);

    // Metadata Card
    const metaY = 112;
    doc.rect(50, metaY, 512, 70).fill('#f8fafc');
    doc.rect(50, metaY, 512, 70).strokeColor('#cbd5e1').lineWidth(0.5).stroke();

    doc.fillColor('#1e293b').fontSize(9);

    // Left Column Metadata
    doc
      .font('Helvetica-Bold').text('Date Generated:', 65, metaY + 15)
      .font('Helvetica').text(new Date().toLocaleDateString(), 165, metaY + 15)
      .font('Helvetica-Bold').text('Report Period:', 65, metaY + 35)
      .font('Helvetica').text('Current Month-End Summary', 165, metaY + 35);

    // Platform Metrics
    const totalBookings = bookings.length;
    const bookingFeesCollected = totalBookings * 30; // ₹30 per booking
    const totalJoins = joinRequests.filter(j => j.status === 'ACCEPTED').length;
    const joinFeesCollected = totalJoins * 9; // ₹9 per join request
    const netPlatformRevenue = bookingFeesCollected + joinFeesCollected;

    // Draw 3 Metrics Cards
    const cardY = 200;
    const cardWidth = 160;
    const cardHeight = 55;
    const gap = 16;

    // Card 1: Team Bookings Fees
    doc.rect(50, cardY, cardWidth, cardHeight).fill('#f1f5f9');
    doc.rect(50, cardY, cardWidth, cardHeight).strokeColor('#cbd5e1').lineWidth(0.5).stroke();
    doc.fillColor('#64748b').font('Helvetica').fontSize(7.5).text('TEAM BOOKING FEES (INR 30)', 57, cardY + 10);
    doc.fillColor('#0f172a').font('Helvetica-Bold').fontSize(13).text(`INR ${bookingFeesCollected.toFixed(2)}`, 57, cardY + 24)
       .font('Helvetica').fontSize(8.5).fillColor('#475569').text(`(${totalBookings} bookings)`, 57, cardY + 40);

    // Card 2: Single Player Join Fees
    doc.rect(50 + cardWidth + gap, cardY, cardWidth, cardHeight).fill('#f1f5f9');
    doc.rect(50 + cardWidth + gap, cardY, cardWidth, cardHeight).strokeColor('#cbd5e1').lineWidth(0.5).stroke();
    doc.fillColor('#64748b').font('Helvetica').fontSize(7.5).text('PLAYER JOIN FEES (INR 9)', 50 + cardWidth + gap + 10, cardY + 10);
    doc.fillColor('#0f172a').font('Helvetica-Bold').fontSize(13).text(`INR ${joinFeesCollected.toFixed(2)}`, 50 + cardWidth + gap + 10, cardY + 24)
       .font('Helvetica').fontSize(8.5).fillColor('#475569').text(`(${totalJoins} joins)`, 50 + cardWidth + gap + 10, cardY + 40);

    // Card 3: Total Net Platform Revenue (Green Highlighted)
    doc.rect(50 + (cardWidth + gap) * 2, cardY, cardWidth, cardHeight).fill('#ecfdf5');
    doc.rect(50 + (cardWidth + gap) * 2, cardY, cardWidth, cardHeight).strokeColor('#a7f3d0').lineWidth(0.5).stroke();
    doc.fillColor('#047857').font('Helvetica-Bold').fontSize(7.5).text('NET PLATFORM REVENUE', 50 + (cardWidth + gap) * 2 + 10, cardY + 10);
    doc.fillColor('#065f46').font('Helvetica-Bold').fontSize(13).text(`INR ${netPlatformRevenue.toFixed(2)}`, 50 + (cardWidth + gap) * 2 + 10, cardY + 24)
       .font('Helvetica').fontSize(8.5).fillColor('#047857').text('Platform Total', 50 + (cardWidth + gap) * 2 + 10, cardY + 40);

    // Bookings breakdown section headers
    const tableTop = 275;
    
    // Shaded header bar
    doc.rect(50, tableTop, 512, 20).fill('#1e293b');
    doc.fillColor('#ffffff').font('Helvetica-Bold').fontSize(8.5);
    doc
      .text('Turf / Owner Name', 60, tableTop + 6)
      .text('Transaction Type', 200, tableTop + 6)
      .text('Details', 320, tableTop + 6)
      .text('Platform Fee', 470, tableTop + 6);

    let y = tableTop + 20;
    let isRowEven = false;

    // Helper to print a table row
    const printRow = (ownerName, type, details, amount) => {
      if (y > 700) {
        drawFooterBranding(doc, 735);
        doc.addPage();
        drawAccentBar(doc);
        y = 45;

        // Reprint headers on new page
        doc.rect(50, y, 512, 20).fill('#1e293b');
        doc.fillColor('#ffffff').font('Helvetica-Bold').fontSize(8.5);
        doc
          .text('Turf / Owner Name', 60, y + 6)
          .text('Transaction Type', 200, y + 6)
          .text('Details', 320, y + 6)
          .text('Platform Fee', 470, y + 6);
        y += 20;
      }

      doc.rect(50, y, 512, 20).fill(isRowEven ? '#f8fafc' : '#ffffff');

      doc
        .font('Helvetica')
        .fontSize(8)
        .fillColor('#334155')
        .text(ownerName.substring(0, 24), 60, y + 6)
        .text(type, 200, y + 6)
        .text(details.substring(0, 26), 320, y + 6)
        .text(amount, 470, y + 6);

      doc
        .moveTo(50, y + 20)
        .lineTo(562, y + 20)
        .strokeColor('#e2e8f0')
        .lineWidth(0.5)
        .stroke();

      y += 20;
      isRowEven = !isRowEven;
    };

    // Render bookings
    bookings.forEach(b => {
      const ownerName = b.slot.owner ? b.slot.owner.turfName : 'Unknown Turf';
      printRow(ownerName, 'Team Booking', `${b.slot.date} @ ${b.slot.timeSlot}`, 'INR 30.00');
    });

    // Render joins
    joinRequests.filter(j => j.status === 'ACCEPTED').forEach(j => {
      const ownerName = j.booking?.slot?.owner ? j.booking.slot.owner.turfName : 'Unknown Turf';
      printRow(ownerName, 'Single Player Join', `Player: ${j.playerName}`, 'INR 9.00');
    });

    // Footer branding at bottom of page
    drawFooterBranding(doc, 735);

    doc.end();
  });
}
