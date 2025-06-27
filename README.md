# Receipt Generator

This project is an automatic professional invoice PDF generator for businesses and freelancers.

## What does this program do?
- Reads company, client, and service information from a `config.json` file.
- Generates professional PDF invoices (in English and French by default) with a detailed service table, bank details, and tax notes.
- Automatically fetches the EUR/USD exchange rate from the European Central Bank for the invoice date.
- Updates the sequential invoice number in the JSON config.
- Extracts and prints the generated PDF text for verification.

## Multilingual and Multi-currency Support
- By default, the script emits two PDF versions for each invoice: one in English and one in French (only fixed labels are translated).
- You can add support for other languages by extending the translation dictionaries in the code and calling the PDF generation function with the desired language code.
- The script currently fetches the EUR/USD exchange rate, but you can adapt it to use other exchange rates or sources by modifying the relevant section in the code.

## How does it work?
The main script is `script.py`. It uses `reportlab` for PDF generation, `requests` to fetch the exchange rate, and `PyPDF2` to extract text from PDFs.

## Installation
1. Clone this repository or download the files.
2. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration
Edit the `config.json` file to set your company, client, services, and bank details. Example:
```json
{
  "company": {
    "legal_name": "Your Company Name, Inc.",
    "business_name": "Your Business Name",
    "contact_name": "Your Name",
    "email": "your.email@example.com",
    "phone": "+1 555-555-5555",
    "address": "123 Main Street, City, Country",
    "siret": "COMPANY-ID"
  },
  ...
  "output_name": "Your Company Name"
}
```
- The `output_name` field defines the base name for the generated PDF files.
- List your services in the `services` array.
- Make sure the sum of all service prices matches the `amount_excl_tax` and `amount_incl_tax` fields.

## Usage
1. Ensure your `config.json` is correctly filled out.
2. Run the script:
   ```bash
   python script.py
   ```
3. The PDFs will be generated in the `invoices/` folder with names like:
   - `Your Company Name - June.pdf` (English)
   - `Your Company Name - June fr.pdf` (French)

## Notes
- The script always generates two PDFs: one in English and one in French by default.
- You can add other languages or currencies with small code changes.
- The invoice number is automatically incremented after each run.
- The exchange rate is fetched automatically for the emission date.

---
