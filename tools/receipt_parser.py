import re
from typing import Dict, Any, Optional
from tools.vault import vault

PERSIAN_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_digits(text: str) -> str:
    """Converts Persian and Arabic-Indic numerals to standard ASCII digits."""
    return (text or "").translate(PERSIAN_DIGIT_MAP)


BANK_PATTERNS = {
    "BluBank (بلو بانک)": [r"بلو", r"blubank", r"6219\s*8619"],
    "Saman (بانک سامان)": [r"سامان", r"saman", r"6219\s*86"],
    "Mellat (بانک ملت)": [r"ملت", r"mellat", r"6104\s*33"],
    "Melli (بانک ملی)": [r"ملی", r"melli", r"6037\s*99"],
    "Pasargad (بانک پاسارگاد)": [r"پاسارگاد", r"pasargad", r"5022\s*29"],
    "Tejarat (بانک تجارت)": [r"تجارت", r"tejarat", r"5859\s*83"],
    "Saderat (بانک صادرات)": [r"صادرات", r"saderat", r"6037\s*69"],
    "Keshavarzi (بانک کشاورزی)": [r"کشاورزی", r"6037\s*70"],
    "Parsian (بانک پارسیان)": [r"پارسیان", r"6221\s*06"],
}

TRANSFER_TYPES = {
    "Card-to-Card (کارت به کارت)": [r"کارت به کارت", r"انتقال وجه کارت", r"card to card"],
    "Paya (پایا)": [r"پایا", r"paya", r"حواله پایا"],
    "Satna (ساتنا)": [r"ساتنا", r"satna", r"حواله ساتنا"],
    "Pol (پل)": [r"سامانه پل", r"انتقال پل"],
}


class IranianReceiptParser:
    """
    Phase 2.2: Financial Ledger & Iranian Bank Receipt Parser.
    Extracts:
    - Tracking code (کد رهگیری / شماره پیگیری / شماره مرجع)
    - Sender & receiver 16-digit card numbers (masked or full) or IBAN (شبا)
    - Amount & Currency (Toman / Rial)
    - Transfer type (کارت به کارت, پایا, ساتنا) & Bank name (بلو, سامان, ملت, ...)
    - Date & Time (Jalali 140x/xx/xx or Gregorian)
    """

    def parse_receipt_text(self, raw_text: str) -> Dict[str, Any]:
        text = normalize_digits(raw_text)

        # 1. Detect Bank Name
        detected_bank = "Unknown Bank"
        for bank_label, patterns in BANK_PATTERNS.items():
            if any(re.search(p, text, re.IGNORECASE) for p in patterns):
                detected_bank = bank_label
                break

        # 2. Detect Transfer Type
        detected_type = "Card-to-Card (کارت به کارت)"
        for t_label, patterns in TRANSFER_TYPES.items():
            if any(re.search(p, text, re.IGNORECASE) for p in patterns):
                detected_type = t_label
                break

        # 3. Extract Tracking Code (کد رهگیری / شماره پیگیری / شماره مرجع / کد پیگیری)
        tracking_code: Optional[str] = None
        tracking_patterns = [
            r"(?:کد\s*رهگیری|شماره\s*پیگیری|کد\s*پیگیری|شماره\s*مرجع|شماره\s*رسید|tracking\s*code|reference\s*no)[\s:：\-]*([0-9]{5,20})",
            r"\b([0-9]{8,16})\b"
        ]
        for pat in tracking_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                # Avoid matching 16-digit card numbers as tracking codes in fallback pattern
                if pat == tracking_patterns[1] and len(candidate) == 16 and candidate[:4] in (
                    "6037", "6104", "6219", "6221", "5022", "5859", "6274", "6280", "6393"
                ):
                    continue
                tracking_code = candidate
                break

        # 4. Extract Amount & Currency (Toman / Rial)
        amount = 0.0
        currency = "Toman"
        amount_patterns = [
            r"(?:مبلغ|amount)[\s:：]*([0-9][0-9,\.]{2,20})\s*(ریال|تومان|تومن|rial|toman)?",
            r"([0-9]{1,3}(?:,[0-9]{3})+)\s*(ریال|تومان|تومن|rial|toman)",
            r"([0-9]{4,15})\s*(ریال|تومان|تومن|rial|toman)"
        ]
        for pat in amount_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                num_str = m.group(1).replace(",", "").replace(".", "").strip()
                if num_str.isdigit():
                    amount = float(num_str)
                unit_raw = (m.group(2) or "").lower()
                if "ریال" in unit_raw or "rial" in unit_raw:
                    currency = "Rial"
                elif "تومان" in unit_raw or "تومن" in unit_raw or "toman" in unit_raw:
                    currency = "Toman"
                break

        # Also check global currency mention if not attached directly to number
        if currency == "Toman" and re.search(r"\bریال\b|\brial\b", text, re.IGNORECASE) and not re.search(
            r"تومان|تومن|toman", text, re.IGNORECASE
        ):
            currency = "Rial"

        # 5. Extract Card Numbers (full or masked like 6037-****-****-1234 or 6219861912345678)
        card_pattern = r"\b(?:\d{4}[\s\-]*){2}(?:\d{4}|[\*×xX]{4})[\s\-]*\d{4}\b|\b\d{6}[\*×xX]{6}\d{4}\b"
        cards = [re.sub(r"[\s\-]", "", c) for c in re.findall(card_pattern, text)]
        sender_card = cards[0] if len(cards) >= 1 else ""
        receiver_card = cards[1] if len(cards) >= 2 else ""

        # Check explicit sender/receiver labels
        sender_match = re.search(
            r"(?:مبدا|فرستنده|از\s*کارت|source)[\s:：]*([0-9\*×xX\-\s]{12,25})",
            text,
            re.IGNORECASE
        )
        receiver_match = re.search(
            r"(?:مقصد|گیرنده|به\s*کارت|destination)[\s:：]*([0-9\*×xX\-\s]{12,25})",
            text,
            re.IGNORECASE
        )
        if sender_match:
            sender_card = re.sub(r"[\s\-]", "", sender_match.group(1).strip())
        if receiver_match:
            receiver_card = re.sub(r"[\s\-]", "", receiver_match.group(1).strip())

        # 6. Extract Date/Time
        date_str = ""
        date_match = re.search(r"(\d{4}/\d{1,2}/\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)", text)
        if date_match:
            date_str = date_match.group(1).strip()

        return {
            "bank_name": detected_bank,
            "transfer_type": detected_type,
            "tracking_code": tracking_code,
            "amount": amount,
            "currency": currency,
            "amount_toman": round(amount / 10.0, 2) if currency == "Rial" else amount,
            "sender_card": sender_card,
            "receiver_card": receiver_card,
            "date": date_str,
        }

    def parse_and_record(
        self,
        raw_text: str,
        category: str = "income",
        project_slug: Optional[str] = None,
        receipt_path: Optional[str] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Parses an Iranian bank receipt and records it in the vault ledger with deduplication."""
        parsed = self.parse_receipt_text(raw_text)
        desc = description or f"{parsed['transfer_type']} via {parsed['bank_name']}"
        tx = vault.record_transaction(
            amount=parsed["amount"],
            currency=parsed["currency"],
            category=category,
            tracking_code=parsed["tracking_code"],
            sender_card=parsed["sender_card"],
            receiver_card=parsed["receiver_card"],
            bank_name=parsed["bank_name"],
            transfer_type=parsed["transfer_type"],
            date=parsed["date"],
            description=desc,
            receipt_path=receipt_path,
            project_slug=project_slug
        )
        return {
            "parsed": parsed,
            "transaction": tx,
            "duplicate": tx.get("duplicate", False)
        }


receipt_parser = IranianReceiptParser()
