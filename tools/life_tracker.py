import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from tools.vault import vault
from tools.receipt_parser import normalize_digits

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


# Standard clinical reference intervals for adult lab biomarkers (CBC, Vitamins, Thyroid, Metabolic)
BIOMARKER_REFERENCE_RANGES: Dict[str, Dict[str, Any]] = {
    "WBC": {"category": "CBC", "min": 4.0, "max": 10.5, "unit": "10^3/uL", "aliases": [r"\bwbc\b", r"white blood cell"]},
    "RBC": {"category": "CBC", "min": 4.2, "max": 5.9, "unit": "10^6/uL", "aliases": [r"\brbc\b", r"red blood cell"]},
    "Hemoglobin": {"category": "CBC", "min": 13.5, "max": 17.5, "unit": "g/dL", "aliases": [r"\bhgb\b", r"\bhb\b", r"hemoglobin"]},
    "Hematocrit": {"category": "CBC", "min": 40.0, "max": 52.0, "unit": "%", "aliases": [r"\bhct\b", r"hematocrit"]},
    "Platelets": {"category": "CBC", "min": 150.0, "max": 450.0, "unit": "10^3/uL", "aliases": [r"\bplt\b", r"platelets"]},
    "Vitamin D": {"category": "Vitamins", "min": 30.0, "max": 100.0, "unit": "ng/mL", "aliases": [r"vitamin\s*d\b", r"25-oh\s*vit\s*d", r"ویتامین\s*دی"]},
    "Vitamin B12": {"category": "Vitamins", "min": 200.0, "max": 900.0, "unit": "pg/mL", "aliases": [r"vitamin\s*b12", r"\bb12\b", r"ویتامین\s*b12"]},
    "Ferritin": {"category": "Vitamins", "min": 30.0, "max": 400.0, "unit": "ng/mL", "aliases": [r"\bferritin\b", r"فریتین"]},
    "TSH": {"category": "Thyroid", "min": 0.4, "max": 4.5, "unit": "mIU/L", "aliases": [r"\btsh\b", r"thyroid stimulating"]},
    "Free T4": {"category": "Thyroid", "min": 0.8, "max": 1.8, "unit": "ng/dL", "aliases": [r"free\s*t4", r"\bft4\b"]},
    "Free T3": {"category": "Thyroid", "min": 2.3, "max": 4.2, "unit": "pg/mL", "aliases": [r"free\s*t3", r"\bft3\b"]},
    "FBS": {"category": "Metabolic", "min": 70.0, "max": 99.0, "unit": "mg/dL", "aliases": [r"\bfbs\b", r"fasting blood sugar", r"قند\s*خون\s*ناشتا"]},
    "HbA1c": {"category": "Metabolic", "min": 4.0, "max": 5.6, "unit": "%", "aliases": [r"\bhba1c\b", r"\ba1c\b"]},
    "LDL": {"category": "Lipids", "min": 0.0, "max": 100.0, "unit": "mg/dL", "aliases": [r"\bldl\b", r"ldl-c"]},
    "HDL": {"category": "Lipids", "min": 40.0, "max": 100.0, "unit": "mg/dL", "aliases": [r"\bhdl\b", r"hdl-c"]},
    "Triglycerides": {"category": "Lipids", "min": 0.0, "max": 150.0, "unit": "mg/dL", "aliases": [r"triglycerides", r"\btg\b", r"تری\s*گلیسیرید"]},
}


class MedicalLabAndBioTracker:
    """
    Phase 6.1 & 6.2: Medical Lab Report Parser & Daily Bio-Logging.
    - Extracts blood test / lab report PDFs and text (CBC, vitamins, thyroid, metabolic)
      into structured SQLite `medical_lab_results` with automatic out-of-range (`LOW` / `HIGH`) flags.
    - Parses natural language voice/text bio logs for sleep hours, caffeine, headaches, workouts, and energy.
    """

    def extract_text_from_pdf(self, pdf_path: Path) -> str:
        if not pdf_path.exists() or not HAS_PYPDF:
            return ""
        try:
            reader = pypdf.PdfReader(str(pdf_path))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(pages)
        except Exception:
            return ""

    def parse_and_store_lab_report(
        self,
        raw_text: str,
        lab_date: str = "",
        source_file: str = ""
    ) -> Dict[str, Any]:
        """
        Parses medical lab biomarkers from text/PDF content, compares against clinical reference intervals,
        flags out-of-range values (`LOW`, `NORMAL`, `HIGH`), and stores them in SQLite.
        """
        text = normalize_digits(raw_text)
        extracted: List[Dict[str, Any]] = []
        flagged: List[Dict[str, Any]] = []

        for marker_name, meta in BIOMARKER_REFERENCE_RANGES.items():
            for alias_pat in meta["aliases"]:
                # Match biomarker label followed by a numeric value on the same line
                pattern = rf"(?:{alias_pat})[^\n\d\-]*([0-9]+(?:\.[0-9]+)?)"
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    val = float(m.group(1))
                    rec = vault.record_lab_result(
                        test_category=meta["category"],
                        biomarker=marker_name,
                        value=val,
                        unit=meta["unit"],
                        reference_min=meta["min"],
                        reference_max=meta["max"],
                        lab_date=lab_date,
                        source_file=source_file
                    )
                    extracted.append(rec)
                    if rec["flag"] != "NORMAL":
                        flagged.append(rec)
                    break

        return {
            "total_extracted": len(extracted),
            "flagged_count": len(flagged),
            "results": extracted,
            "out_of_range": flagged
        }

    def parse_and_log_bio_note(self, text: str) -> List[Dict[str, Any]]:
        """
        Phase 6.2: Daily Bio-Logging from voice notes or text.
        Detects sleep hours, caffeine, headaches, workouts, and energy levels.
        """
        norm = normalize_digits(text).lower()
        logged: List[Dict[str, Any]] = []

        # 1. Sleep hours (e.g. "7.5 hours sleep", "۷ ساعت خوابیدم")
        sleep_m = re.search(
            r"([0-9]+(?:\.[0-9]+)?)\s*(?:ساعت\s*خواب|hours?\s*(?:of\s*)?sleep|خوابیدم)|(?:sleep|خواب)[\s:：]*([0-9]+(?:\.[0-9]+)?)",
            norm
        )
        if sleep_m:
            hrs = sleep_m.group(1) or sleep_m.group(2)
            logged.append(vault.log_health_or_habit("bio", "sleep_hours", hrs, unit="hours", notes=text))

        # 2. Caffeine (e.g. "2 coffees", "۲ تا قهوه", "200mg caffeine")
        caf_m = re.search(
            r"([0-9]+)\s*(?:تا\s*)?(?:قهوه|اسپرسو|coffee|espresso|caffeine)",
            norm
        )
        if caf_m:
            logged.append(vault.log_health_or_habit("bio", "caffeine", caf_m.group(1), unit="servings", notes=text))

        # 3. Headache (e.g. "سردرد", "headache")
        if any(w in norm for w in ("سردرد", "میگرن", "headache", "migraine")):
            sev_m = re.search(r"(?:شدت|severity|level)\s*([0-9]{1,2})", norm)
            sev = sev_m.group(1) if sev_m else "moderate"
            logged.append(vault.log_health_or_habit("symptom", "headache", sev, unit="severity", notes=text))

        # 4. Workout / Exercise (e.g. "45 min workout", "۴۵ دقیقه ورزش", "باشگاه")
        work_m = re.search(r"([0-9]+)\s*(?:دقیقه|min|minutes?)\s*(?:ورزش|تمرین|باشگاه|پیاده‌روی|workout|gym|run)", norm)
        if work_m:
            logged.append(vault.log_health_or_habit("habit", "workout", work_m.group(1), unit="minutes", notes=text))
        elif any(w in norm for w in ("باشگاه رفتم", "ورزش کردم", "worked out", "gym session")):
            logged.append(vault.log_health_or_habit("habit", "workout", "completed", unit="session", notes=text))

        # If no specific pattern matched, log as general bio reflection
        if not logged and text.strip():
            logged.append(vault.log_health_or_habit("bio", "general_note", text.strip()[:200], notes=text))

        return logged


life_tracker = MedicalLabAndBioTracker()
