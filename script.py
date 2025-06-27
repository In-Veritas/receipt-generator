import json
import os
from datetime import datetime, date, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Table, TableStyle
from PyPDF2 import PdfReader
import textwrap
import requests
import xml.etree.ElementTree as ET
import re

CONFIG_FILE = 'config.json'
PDF_OUTPUT_DIR = 'invoices'

# New color scheme
PRIMARY_BLUE = colors.HexColor('#2196f3')  # vibrant blue
LIGHT_BLUE_BG = colors.HexColor('#e3f2fd')  # very light blue
LIGHT_GREY = colors.HexColor('#b0bec5')
DARK_GREY = colors.HexColor('#444444')

ECB_API = 'https://api.exchangerate.host/2024-12-16?base=EUR&symbols=USD'


def read_config():
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def write_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def generate_invoice_id(date_str, number):
    # Format: N° #DD-MM-YYYY-XX
    date_fmt = datetime.strptime(date_str, "%d/%m/%Y").strftime("%d-%m-%Y")
    return f"N° #{date_fmt}-{number:02d}"

def fetch_and_update_exchange_rate(config, emission_date):
    invoice_date = datetime.strptime(emission_date, "%d/%m/%Y").date()
    today = date.today()
    url = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
    try:
        response = requests.get(url)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        ns = {'gesmes': 'http://www.gesmes.org/xml/2002-08-01', 'def': 'http://www.ecb.int/vocabulary/2002-08-01/eurofxref'}
        date_to_rate = {}
        for cube in root.findall('.//def:Cube[@time]', ns):
            cube_date = cube.attrib['time']
            usd_cube = cube.find("def:Cube[@currency='USD']", ns)
            if usd_cube is not None:
                date_to_rate[cube_date] = float(usd_cube.attrib['rate'])
        invoice_date_str = invoice_date.strftime('%Y-%m-%d')
        if invoice_date_str in date_to_rate:
            rate = date_to_rate[invoice_date_str]
            config['exchange_rate_note'] = (
                f"Applied exchange rate: EUR/USD ({rate:.4f}), according to the ECB for {invoice_date_str}"
            )
            config['exchange_rate'] = rate
        else:
            available_dates = sorted([d for d in date_to_rate.keys() if d <= invoice_date_str])
            if available_dates:
                fallback_date = available_dates[-1]
                rate = date_to_rate[fallback_date]
                config['exchange_rate_note'] = (
                    f"Applied exchange rate: EUR/USD ({rate:.4f}), according to the ECB for {fallback_date} (latest available before invoice date {invoice_date_str})"
                )
                config['exchange_rate'] = rate
            else:
                latest_date = sorted(date_to_rate.keys())[-1]
                rate = date_to_rate[latest_date]
                config['exchange_rate_note'] = (
                    f"Applied exchange rate: EUR/USD ({rate:.4f}), according to the ECB for {latest_date} (no rate available for or before invoice date {invoice_date_str})"
                )
                config['exchange_rate'] = rate
    except Exception as e:
        config['exchange_rate_note'] = f"Could not fetch exchange rate from ECB. {str(e)}"
        config['exchange_rate'] = None
    return config

def draw_box(c, x, y, w, h, label=None):
    c.setStrokeColor(LIGHT_GREY)
    c.setLineWidth(1)
    c.roundRect(x, y, w, h, 6, stroke=1, fill=0)
    if label:
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(DARK_GREY)
        c.drawString(x + 8, y + h - 18, label)
    c.setFillColor(colors.black)

def draw_wrapped_text(c, text, x, y, max_width, font_name, font_size, line_gap):
    c.setFont(font_name, font_size)
    lines = []
    for line in text.split('\n'):
        lines.extend(textwrap.wrap(line, width=int(max_width / (font_size * 0.55))))
    for i, l in enumerate(lines):
        c.drawString(x, y - i * line_gap, l)
    return y - len(lines) * line_gap, len(lines)

def wrap_table_cell(text, col_width, font_size):
    # Helper to wrap text for table cells
    return '\n'.join(textwrap.wrap(str(text), width=int(col_width / (font_size * 0.55))))

def create_invoice_pdf(config, invoice_id, output_path, emission_date, lang='en'):
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    margin = 30
    y = height - margin

    # French/English labels
    labels = {
        'en': {
            'invoice': 'Invoice',
            'emitted_at': 'Emitted at',
            'due_date': 'Due date',
            'company': 'Company',
            'bill_to': 'Bill to',
            'payment_term': 'Payment term:',
            'payment_methods': 'Payment method:',
            'amount_excl_tax': 'Amount excl. tax:',
            'vat': 'VAT:',
            'amount_incl_tax': 'Amount incl. tax:',
            'bank_details': 'Bank Account Details',
            'description': 'Description',
            'unit': 'Unit',
            'quantity': 'Quantity',
            'unit_price': 'Unit price',
            'vat_col': 'VAT',
            'total': 'Total',
            'total_incl_tax': 'Total incl. tax',
            'client': 'Client',
            'vat_note': 'VAT not applicable – art. 259-1 of the French Tax Code.',
            'exchange_rate_note': config.get('exchange_rate_note', ''),
            'account_holder': 'Account holder',
            'routing_number': 'Routing number (ABA)',
            'account_number': 'Account number',
            'account_type': 'Account type',
            'bank': 'Bank',
            'bank_address': 'Bank address',
            'account_address': 'Account address',
        },
        'fr': {
            'invoice': 'Facture',
            'emitted_at': 'Émis le',
            'due_date': "Date d'échéance",
            'company': 'Société',
            'bill_to': 'Client',
            'payment_term': 'Délai de paiement :',
            'payment_methods': 'Modes de paiement :',
            'amount_excl_tax': 'Montant HT :',
            'vat': 'TVA :',
            'amount_incl_tax': 'Montant TTC :',
            'bank_details': 'Coordonnées bancaires',
            'description': 'Description',
            'unit': 'Unité',
            'quantity': 'Quantité',
            'unit_price': 'Prix unitaire',
            'vat_col': 'TVA',
            'total': 'Total',
            'total_incl_tax': 'Total TTC',
            'client': 'Client',
            'vat_note': 'TVA non applicable – art. 259-1 du Code général des impôts.',
            'exchange_rate_note': '',  # Will be set below
            'account_holder': 'Titulaire du compte',
            'routing_number': 'Code de routage (ABA)',
            'account_number': 'Numéro de compte',
            'account_type': 'Type de compte',
            'bank': 'Banque',
            'bank_address': 'Adresse de la banque',
            'account_address': 'Adresse du compte',
        }
    }[lang]

    # Translate exchange_rate_note for French
    if lang == 'fr':
        note = config.get('exchange_rate_note', '')
        match = re.match(r'Applied exchange rate: EUR/USD \(([^)]+)\), according to the ECB for (\d{4}-\d{2}-\d{2})', note)
        if match:
            rate, date_str = match.groups()
            labels['exchange_rate_note'] = f"Taux de change appliqué : EUR/USD ({rate}), selon la BCE pour le {date_str}"
        else:
            labels['exchange_rate_note'] = note

    # Calculate due date from emission_date + due_days
    due_days = config.get('invoice', {}).get('due_days', 0)
    emission_dt = datetime.strptime(emission_date, '%d/%m/%Y')
    due_dt = emission_dt + timedelta(days=due_days)
    due_date_str = due_dt.strftime('%d/%m/%Y')

    # Border
    c.setStrokeColor(PRIMARY_BLUE)
    c.setLineWidth(2)
    c.rect(margin/2, margin/2, width - margin, height - margin, stroke=1, fill=0)

    # Header with extra top spacing
    y -= 20
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(PRIMARY_BLUE)
    c.drawString(margin, y, labels['invoice'])
    y -= 32

    # Invoice Info Block (ID, Emitted at, Due date) - vertical layout
    block_height = 60
    c.setFillColor(LIGHT_BLUE_BG)
    c.roundRect(margin, y - block_height + 8, width - 2*margin, block_height, 6, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin + 12, y - 12, f"{invoice_id}")
    c.setFont("Helvetica", 10)
    c.setFillColor(DARK_GREY)
    c.drawString(margin + 12, y - 30, f"{labels['emitted_at']}: {emission_date}")
    c.drawString(margin + 12, y - 48, f"{labels['due_date']}: {due_date_str}")
    y -= block_height + 10

    # Sender/Receiver boxes
    box_height = 190  # Increased height for more bottom spacing
    box_width = (width - 2*margin - 40) / 2
    line_gap = 18
    text_x_pad = 18  # More space from label
    text_y_start = y - 22
    # Supplier (was From)
    draw_box(c, margin, y - box_height, box_width, box_height, label=labels['company'])
    y_sender = text_y_start - line_gap  # Start one line below the label
    c.setFont("Helvetica-Bold", 11)
    y_sender, _ = draw_wrapped_text(c, config['company']['legal_name'], margin + text_x_pad, y_sender, box_width - 2*text_x_pad, "Helvetica-Bold", 11, line_gap)
    c.setFont("Helvetica", 10)
    y_sender, _ = draw_wrapped_text(c, config['company']['business_name'], margin + text_x_pad, y_sender, box_width - 2*text_x_pad, "Helvetica", 10, line_gap)
    y_sender, _ = draw_wrapped_text(c, config['company']['contact_name'], margin + text_x_pad, y_sender, box_width - 2*text_x_pad, "Helvetica", 10, line_gap)
    y_sender, _ = draw_wrapped_text(c, config['company']['email'], margin + text_x_pad, y_sender, box_width - 2*text_x_pad, "Helvetica", 10, line_gap)
    y_sender, _ = draw_wrapped_text(c, config['company']['phone'], margin + text_x_pad, y_sender, box_width - 2*text_x_pad, "Helvetica", 10, line_gap)
    y_sender, _ = draw_wrapped_text(c, config['company']['address'], margin + text_x_pad, y_sender, box_width - 2*text_x_pad, "Helvetica", 10, line_gap)
    y_sender, _ = draw_wrapped_text(c, f"SIRET: {config['company']['siret']}", margin + text_x_pad, y_sender, box_width - 2*text_x_pad, "Helvetica", 10, line_gap)
    # Customer (was To)
    draw_box(c, margin + box_width + 40, y - box_height, box_width, box_height, label=labels['bill_to'])
    y_receiver = text_y_start - line_gap  # Start one line below the label
    c.setFont("Helvetica-Bold", 11)
    y_receiver, _ = draw_wrapped_text(c, config['receiver']['name'], margin + box_width + 40 + text_x_pad, y_receiver, box_width - 2*text_x_pad, "Helvetica-Bold", 11, line_gap)
    c.setFont("Helvetica", 10)
    y_receiver, _ = draw_wrapped_text(c, config['receiver']['address'], margin + box_width + 40 + text_x_pad, y_receiver, box_width - 2*text_x_pad, "Helvetica", 10, line_gap)
    y -= box_height + 30  # Move table upwards

    # Table column widths and font size (remove Details column, keep centered)
    col_widths = [18, 120, 40, 40, 60, 45, 60, 70]  # Remove details column, widen Description
    table_font_size_header = 9
    table_font_size = 8

    data = [["#", labels['description'], labels['unit'], labels['quantity'], labels['unit_price'], labels['vat_col'], labels['total'], labels['total_incl_tax']]]
    services = config.get('services', [])
    for i, service in enumerate(services, 1):
        desc_col = wrap_table_cell(service.get('description', ''), col_widths[1], table_font_size)
        unit = service.get('unit', 'Month')
        quantity = service.get('quantity', 1)
        unit_price = service.get('amount_usd', 0.0)
        vat = unit_price * quantity * 0.0  # Set VAT logic as needed
        total = unit_price * quantity
        total_incl_tax = total + vat
        data.append([
            str(i),
            desc_col,
            unit,
            str(quantity),
            f"${unit_price:,.2f}",
            f"${vat:,.2f}",
            f"${total:,.2f}",
            f"${total_incl_tax:,.2f}"
        ])
    # Calculate row heights for wrapped text
    row_heights = [20]
    for row in data[1:]:
        desc_lines = row[1].count('\n') + 1
        row_height = desc_lines * (table_font_size + 3) + 10
        row_heights.append(row_height)
    table = Table(data, colWidths=col_widths, rowHeights=row_heights)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), LIGHT_BLUE_BG),
        ('TEXTCOLOR', (0, 0), (-1, 0), PRIMARY_BLUE),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), table_font_size_header),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, LIGHT_GREY),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), table_font_size),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
    ]))
    # Multi-page table logic
    available_height = y - (margin + 200)  # leave space for at least one section below
    table_x = margin
    table_y = y
    # Split the table if needed
    table_parts = table.split(width - 2*margin, available_height)
    for idx, part in enumerate(table_parts):
        if idx > 0:
            c.showPage()
            # Redraw border on new page
            c.setStrokeColor(PRIMARY_BLUE)
            c.setLineWidth(2)
            c.rect(margin/2, margin/2, width - margin, height - margin, stroke=1, fill=0)
            table_y = height - margin
        part.wrapOn(c, width, height)
        part.drawOn(c, table_x, table_y - part._height)
        table_y -= part._height
    y = table_y - 32  # y after the last table part

    # Payment and Tax Info Section - Dynamically sized
    vat_note_lines = textwrap.wrap(config.get('vat_note', ''), width=int((width - 2*margin - 36) / (10 * 0.55)))
    exch_note_lines = textwrap.wrap(config.get('exchange_rate_note', ''), width=int((width - 2*margin - 36) / (10 * 0.55)))
    n_lines = 5 + len(vat_note_lines) + len(exch_note_lines)
    section_height = n_lines * 16 + 24  # lines + padding (no header)
    section_y = y - section_height + 20
    # If not enough space, start a new page
    if section_y < margin + 100:
        c.showPage()
        c.setStrokeColor(PRIMARY_BLUE)
        c.setLineWidth(2)
        c.rect(margin/2, margin/2, width - margin, height - margin, stroke=1, fill=0)
        y = height - margin - 32
        section_y = y - section_height + 20
    c.setFillColor(LIGHT_BLUE_BG)
    c.roundRect(margin, section_y, width - 2*margin, section_height, 8, fill=1, stroke=0)
    c.setFillColor(colors.black)
    text_y = section_y + section_height - 16  # 16px padding from the top
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin + 18, text_y, labels['payment_term'])
    c.setFont("Helvetica", 10)
    due_days = config.get('invoice', {}).get('due_days', 0)
    if lang == 'fr':
        payment_term_value = f' {due_days} jours'
    else:
        payment_term_value = f' {due_days} days'
    c.drawString(margin + 120, text_y, payment_term_value)
    text_y -= 16
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin + 18, text_y, labels['payment_methods'])
    c.setFont("Helvetica", 10)
    payment_methods_value = config.get('payment_methods', '')
    if lang == 'fr' and payment_methods_value.strip().lower() == 'transfer':
        payment_methods_value = ' Virement'
    elif lang == 'fr':
        payment_methods_value = ' ' + payment_methods_value
    elif lang == 'en':
        payment_methods_value = ' ' + payment_methods_value
    c.drawString(margin + 120, text_y, payment_methods_value)
    text_y -= 16
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin + 18, text_y, labels['amount_excl_tax'])
    c.setFont("Helvetica", 10)
    amount_excl_tax_value = f"${config.get('amount_excl_tax', 0):,.2f}"
    if lang == 'fr':
        amount_excl_tax_value = ' ' + amount_excl_tax_value
    c.drawString(margin + 120, text_y, amount_excl_tax_value)
    text_y -= 16
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin + 18, text_y, labels['vat'])
    c.setFont("Helvetica", 10)
    vat_value = f"${config.get('vat', 0):,.2f}"
    if lang == 'fr':
        vat_value = ' ' + vat_value
    c.drawString(margin + 120, text_y, vat_value)
    text_y -= 16
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin + 18, text_y, labels['amount_incl_tax'])
    c.setFont("Helvetica", 10)
    amount_incl_tax_value = f"${config.get('amount_incl_tax', 0):,.2f}"
    if lang == 'fr':
        amount_incl_tax_value = ' ' + amount_incl_tax_value
    c.drawString(margin + 120, text_y, amount_incl_tax_value)
    text_y -= 20
    c.setFont("Helvetica", 10)
    # VAT note and exchange rate note: always use French in French PDF
    vat_note = labels['vat_note'] if lang == 'fr' else config.get('vat_note', '')
    exch_note = labels['exchange_rate_note'] if lang == 'fr' else config.get('exchange_rate_note', '')
    for line in textwrap.wrap(vat_note, width=int((width - 2*margin - 36) / (10 * 0.55))):
        c.drawString(margin + 18, text_y, line)
        text_y -= 14
    for line in textwrap.wrap(exch_note, width=int((width - 2*margin - 36) / (10 * 0.55))):
        c.drawString(margin + 18, text_y, line)
        text_y -= 14
    y = section_y - 32

    # Bank Account Details Section - Discrete and lower
    # If not enough space, start a new page
    if y < margin + 100:
        c.showPage()
        c.setStrokeColor(PRIMARY_BLUE)
        c.setLineWidth(2)
        c.rect(margin/2, margin/2, width - margin, height - margin, stroke=1, fill=0)
        y = height - margin - 32
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(LIGHT_GREY)
    c.drawString(margin, y, labels['bank_details'])
    c.setFillColor(DARK_GREY)
    y -= 14
    bank = config.get('bank_details', {})
    c.setFont("Helvetica", 9)
    y, _ = draw_wrapped_text(c, f"{labels['account_holder']}: {bank.get('account_holder', '')}", margin, y, width - 2*margin, "Helvetica", 9, 11)
    y, _ = draw_wrapped_text(c, f"{labels['routing_number']}: {bank.get('routing_number', '')}", margin, y, width - 2*margin, "Helvetica", 9, 11)
    y, _ = draw_wrapped_text(c, f"{labels['account_number']}: {bank.get('account_number', '')}", margin, y, width - 2*margin, "Helvetica", 9, 11)
    y, _ = draw_wrapped_text(c, f"{labels['account_type']}: {bank.get('account_type', '')}", margin, y, width - 2*margin, "Helvetica", 9, 11)
    y, _ = draw_wrapped_text(c, f"{labels['bank']}: {bank.get('bank', '')}", margin, y, width - 2*margin, "Helvetica", 9, 11)
    y, _ = draw_wrapped_text(c, f"{labels['bank_address']}: {bank.get('bank_address', '')}", margin, y, width - 2*margin, "Helvetica", 9, 11)
    y, _ = draw_wrapped_text(c, f"{labels['account_address']}: {bank.get('account_address', '')}", margin, y, width - 2*margin, "Helvetica", 9, 11)
    y -= 20

    # Footer
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(colors.HexColor('#888888'))
    c.setFillColor(colors.black)
    c.save()

def extract_text_from_pdf(pdf_path):
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def main():
    config = read_config()
    # Check that the sum of service prices matches the total in the JSON
    services = config.get('services', [])
    total_services = sum(service.get('amount_usd', 0.0) * service.get('quantity', 1) for service in services)
    if round(total_services, 2) != round(config.get('amount_excl_tax', 0.0), 2):
        raise ValueError(f"Sum of service prices (${total_services:,.2f}) does not match amount_excl_tax (${config.get('amount_excl_tax', 0.0):,.2f}) in config.json.")
    # Generate invoice number and ID
    invoice_number = config['invoice']['last_invoice_number'] + 1
    today = date.today()
    today_str = today.strftime('%d/%m/%Y')
    invoice_id = generate_invoice_id(today_str, invoice_number)
    # Update exchange rate in config (pass today_str as emission date)
    config = fetch_and_update_exchange_rate(config, today_str)
    # Prepare output directory
    os.makedirs(PDF_OUTPUT_DIR, exist_ok=True)

    # --- Custom filename logic ---
    nome = config.get('output_name', 'Nicolas')
    meses_en = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    mes_en = meses_en[today.month - 1]

    # PDF em inglês
    pdf_filename = f"{nome} - {mes_en}.pdf"
    pdf_path = os.path.join(PDF_OUTPUT_DIR, pdf_filename)
    create_invoice_pdf(config, invoice_id, pdf_path, today_str, lang='en')
    # PDF em francês (mas mês em inglês)
    pdf_filename_fr = f"{nome} - {mes_en} fr.pdf"
    pdf_path_fr = os.path.join(PDF_OUTPUT_DIR, pdf_filename_fr)
    create_invoice_pdf(config, invoice_id, pdf_path_fr, today_str, lang='fr')
    print(f"Invoice generated: {pdf_path}")
    print(f"Invoice generated (French): {pdf_path_fr}")
    # Update config
    config['invoice']['last_invoice_number'] = invoice_number
    write_config(config)
    # Extract and print PDF text
    print("\nExtracted PDF text:")
    print(extract_text_from_pdf(pdf_path))

if __name__ == "__main__":
    main()
