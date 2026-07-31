#!/usr/bin/env python3
"""
Generate production-ready patient Excel file for Medication Adherence Dashboard.
Creates Data/patients.xlsx with configurable row count (default 500).
Uses runtime_paths so it works from project root or next to the executable.
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
from pathlib import Path

import pandas as pd

# Add project root to path when run as script
try:
    from runtime_paths import get_app_dir
except ImportError:
    get_app_dir = lambda: Path(__file__).resolve().parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Production-ready column order matching utils.REQUIRED_EXCEL_COLUMNS (+ EventDate for trends)
EXCEL_COLUMNS = [
    "Member ID",
    "Patient Name",
    "Adherence Percentage",
    "Adeherence Percentage",
    "PDC Percentage",
    "Refill Days",
    "Patient Contact",
    "Patient EmailID",
    "City",
    "Medication Name",
    "EventDate",
    "NotificationSentOn",
    "NotificationSentAt",
    "NotificationStatus",
    "NotificationChannel",
    "NotificationMessageId",
    "RoutedToClinicianOn",
    "RoutedToClinicianNote",
    "AppreciationSentOn",
    "RiskScore",
    "RiskLabel",
    "ClinicianAssigned",
    "EscalationReason",
    "LastUpdated",
]

# Cities for pharmacy lookup (must match pharmacy.PHARMACY_BY_CITY keys or use default)
CITIES = [
    "New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia", "San Antonio",
    "San Diego", "Dallas", "San Jose", "Austin", "Jacksonville", "Fort Worth", "Columbus",
    "Charlotte", "Seattle", "Denver", "Boston", "Mumbai", "Delhi", "Bangalore", "Hyderabad",
    "Chennai", "Kolkata", "Pune",
]

# Realistic first names (diverse, production-style)
FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Lisa", "Daniel", "Nancy",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
    "Kenneth", "Dorothy", "Kevin", "Carol", "Brian", "Amanda", "George", "Melissa",
    "Timothy", "Deborah", "Ronald", "Stephanie", "Edward", "Rebecca", "Jason", "Sharon",
    "Jeffrey", "Laura", "Ryan", "Cynthia", "Jacob", "Kathleen", "Gary", "Amy",
    "Nicholas", "Angela", "Eric", "Shirley", "Jonathan", "Anna", "Stephen", "Brenda",
    "Larry", "Pamela", "Justin", "Emma", "Scott", "Nicole", "Brandon", "Helen",
    "Benjamin", "Samantha", "Samuel", "Katherine", "Raymond", "Christine", "Gregory", "Debra",
    "Frank", "Rachel", "Alexander", "Catherine", "Patrick", "Carolyn", "Jack", "Janet",
    "Dennis", "Ruth", "Jerry", "Maria", "Tyler", "Heather", "Aaron", "Diane",
    "Jose", "Virginia", "Adam", "Julie", "Nathan", "Joyce", "Zachary", "Victoria",
    "Henry", "Olivia", "Douglas", "Kelly", "Peter", "Lauren", "Kyle", "Christina",
    "Noah", "Joan", "Ethan", "Evelyn", "Jeremy", "Judith", "Walter", "Megan",
    "Christian", "Andrea", "Keith", "Cheryl", "Roger", "Hannah", "Terry", "Jacqueline",
    "Austin", "Martha", "Sean", "Gloria", "Gerald", "Teresa", "Carl", "Ann",
    "Dylan", "Sara", "Harold", "Madison", "Jordan", "Frances", "Jesse", "Kathryn",
]

# Realistic last names
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
    "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen",
    "Hill", "Flores", "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera",
    "Campbell", "Mitchell", "Carter", "Roberts", "Chen", "Patel", "Turner", "Phillips",
    "Evans", "Parker", "Edwards", "Collins", "Stewart", "Morris", "Murphy", "Cook",
    "Rogers", "Morgan", "Peterson", "Cooper", "Reed", "Bailey", "Bell", "Gomez",
    "Kelly", "Howard", "Ward", "Cox", "Diaz", "Richardson", "Wood", "Watson",
    "Brooks", "Bennett", "Gray", "James", "Reyes", "Cruz", "Hughes", "Price",
    "Myers", "Long", "Foster", "Sanders", "Ross", "Morales", "Powell", "Sullivan",
    "Russell", "Ortiz", "Jenkins", "Gutierrez", "Perry", "Butler", "Barnes", "Fisher",
    "Henderson", "Coleman", "Simmons", "Patterson", "Jordan", "Reynolds", "Hamilton",
    "Graham", "Kim", "Gonzales", "Alexander", "Ramos", "Wallace", "Griffin", "West",
    "Cole", "Hayes", "Chavez", "Gibson", "Bryant", "Ellis", "Stevens", "Murray",
    "Ford", "Marshall", "Owens", "McDonald", "Harrison", "Ruiz", "Kennedy", "Wells",
]

# Common medications for chronic conditions (adherence use case)
MEDICATIONS = [
    "Lisinopril 10mg", "Metformin 500mg", "Atorvastatin 20mg", "Amlodipine 5mg",
    "Omeprazole 20mg", "Losartan 50mg", "Gabapentin 300mg", "Sertraline 50mg",
    "Metoprolol 25mg", "Pantoprazole 40mg", "Albuterol HFA", "Levothyroxine 50mcg",
    "Hydrochlorothiazide 25mg", "Furosemide 40mg", "Insulin Glargine", "Empagliflozin 10mg",
    "Dulaglutide 0.75mg", "Apotex Metformin 850mg", "Rosuvastatin 10mg", "Tramadol 50mg",
    "Duloxetine 60mg", "Pregabalin 75mg", "Warfarin 5mg", "Apixaban 5mg",
    "Clopidogrel 75mg", "Montelukast 10mg", "Fluticasone 250mcg", "Tiotropium 18mcg",
    "Alogliptin 25mg", "Canagliflozin 100mg", "Sitagliptin 100mg", "Glimepiride 2mg",
    "Prednisone 5mg", "Meloxicam 15mg", "Escitalopram 10mg", "Bupropion XL 150mg",
]


def _random_phone() -> str:
    area = random.randint(201, 989)
    if area in (555, 958, 959):
        area = random.randint(201, 700)
    mid = random.randint(200, 999)
    end = random.randint(1000, 9999)
    return f"+1-{area}-{mid}-{end}"


def _email_from_name(first: str, last: str, i: int) -> str:
    base = f"{first.lower()}.{last.lower()}"
    if random.random() < 0.3:
        base = f"{first.lower()}{last.lower()[0]}{i}"
    domain = random.choice(["gmail.com", "yahoo.com", "outlook.com", "patientmail.org", "healthcare.com"])
    return f"{base}@{domain}"


def _adherence_for_distribution(rng: random.Random) -> float:
    """Roughly 20% low (<50), 35% medium (50-79), 45% high (80+)."""
    r = rng.random()
    if r < 0.20:
        return round(rng.uniform(15, 49), 1)
    if r < 0.55:
        return round(rng.uniform(50, 79), 1)
    return round(rng.uniform(80, 99), 1)


def _refill_days_for_distribution(rng: random.Random) -> int | None:
    """Some missing, some < 7 (high-risk), rest 7–90."""
    if rng.random() < 0.05:
        return None  # missing
    r = rng.random()
    if r < 0.18:
        return rng.randint(0, 6)   # refill due soon
    return rng.randint(7, 90)


def generate_patient_rows(
    n: int,
    seed: int | None = None,
    months: int = 4,
    notif_date_start: pd.Timestamp | None = None,
    notif_date_end: pd.Timestamp | None = None,
) -> list[dict]:
    """Generate n patients with production-ready data. Each patient gets `months` rows: current month plus previous months (EventDate per month) for trend charts and reporting.
    If notif_date_start and notif_date_end are set, notification sent dates are chosen at random in [start, end]; otherwise last 30 days."""
    rng = random.Random(seed)
    rows = []
    used_names = set()
    now = pd.Timestamp.now()
    use_notif_range = notif_date_start is not None and notif_date_end is not None
    for i in range(1, n + 1):
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        key = f"{first} {last}"
        if key in used_names:
            last = last + f" {rng.randint(1,99)}"
        used_names.add(f"{first} {last}")
        name = f"{first} {last}"
        city = rng.choice(CITIES)
        contact = _random_phone()
        email = _email_from_name(first, last, i)
        medication = rng.choice(MEDICATIONS)
        member_id = f"MBR{i:05d}"
        # One notification state per patient (use on current-month row only)
        notif_sent = rng.random() < 0.12
        if notif_sent:
            if use_notif_range:
                start_ts = notif_date_start.value
                end_ts = notif_date_end.value
                random_ts = rng.randint(int(start_ts), int(end_ts))
                notif_on = pd.Timestamp(random_ts, unit="ns")
                notif_at = notif_on
            else:
                days_ago = rng.randint(1, 30)
                notif_on = now - pd.Timedelta(days=days_ago)
                notif_at = notif_on
            notif_status = rng.choice(["Sent", "Sent", "Queued", "Acknowledledged"])
            notif_channel = rng.choice(["SMS", "Email", "Pushover", ""])
            notif_msg_id = f"msg_{rng.randint(10000, 99999)}" if notif_channel else ""
        else:
            notif_on = pd.NaT
            notif_at = pd.NaT
            notif_status = ""
            notif_channel = ""
            notif_msg_id = ""
        for month_offset in range(months):
            # EventDate = first day of that month (or a random day in month for variety)
            month_start = (now.replace(day=1) - pd.offsets.MonthBegin(1) * month_offset)
            if month_offset == 0:
                event_date = now - pd.Timedelta(days=rng.randint(0, min(28, now.day)))
            else:
                month_end = (month_start + pd.offsets.MonthEnd(0))
                event_date = month_start + pd.Timedelta(days=rng.randint(0, min(28, month_end.day - 1)))
            adherence = _adherence_for_distribution(rng)
            refill_days = _refill_days_for_distribution(rng)
            risk_score = min(100, max(0, round(100 - adherence + rng.uniform(-5, 10), 1)))
            risk_label = "High" if risk_score >= 70 else ("Medium" if risk_score >= 40 else "Low")
            # Notification columns only on current month row
            use_notif = (month_offset == 0 and notif_sent)
            row = {
                "Member ID": member_id,
                "Patient Name": name,
                "Adherence Percentage": adherence,
                "Adeherence Percentage": adherence,
                "PDC Percentage": adherence,
                "Refill Days": refill_days if refill_days is not None else pd.NA,
                "Patient Contact": contact,
                "Patient EmailID": email,
                "City": city,
                "Medication Name": medication,
                "EventDate": event_date,
                "NotificationSentOn": notif_on if use_notif else pd.NaT,
                "NotificationSentAt": notif_at if use_notif else pd.NaT,
                "NotificationStatus": notif_status if use_notif else "",
                "NotificationChannel": notif_channel if use_notif else "",
                "NotificationMessageId": notif_msg_id if use_notif else "",
                "RoutedToClinicianOn": pd.NaT,
                "RoutedToClinicianNote": "",
                "AppreciationSentOn": pd.NaT,
                "RiskScore": risk_score,
                "RiskLabel": risk_label,
                "ClinicianAssigned": "",
                "EscalationReason": "",
                "LastUpdated": now,
            }
            rows.append(row)
    return rows


def write_excel(path: Path, rows: list[dict], backup: bool = True) -> None:
    """Write rows to Excel; optionally backup existing file."""
    path = path.resolve()
    if path.exists() and backup:
        backup_path = path.parent / f"{path.stem}_backup_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}{path.suffix}"
        try:
            import shutil
            shutil.copy2(path, backup_path)
            logger.info("Backed up existing file to %s", backup_path.name)
        except OSError as e:
            logger.warning("Could not create backup: %s", e)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=EXCEL_COLUMNS)
    df.to_excel(path, index=False, engine="openpyxl")
    logger.info("Wrote %d rows to %s", len(df), path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate production patient Excel for Medication Adherence Dashboard")
    parser.add_argument("-n", "--rows", type=int, default=None, help="Number of patients. Each gets --months rows. Ignored if --total-rows is set.")
    parser.add_argument("--total-rows", type=int, default=None, help="Total number of data rows (e.g. 500). Patients = total-rows // months.")
    parser.add_argument("-m", "--months", type=int, default=4, help="Months of history per patient (default: 4)")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output path (default: Data/patients.xlsx in app dir)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--no-backup", action="store_true", help="Do not backup existing file")
    parser.add_argument("--notification-from-last-month", action="store_true", help="Set notification sent dates from 1st of last month to today")
    args = parser.parse_args()
    if args.months < 1 or args.months > 24:
        logger.error("--months must be between 1 and 24")
        return 1
    if args.total_rows is not None:
        if args.total_rows < 1 or args.total_rows > 500_000:
            logger.error("--total-rows must be between 1 and 500000")
            return 1
        n_patients = max(1, args.total_rows // args.months)
        total = n_patients * args.months
        logger.info("Generating %d rows (%d patients x %d months)", total, n_patients, args.months)
    else:
        n_patients = args.rows if args.rows is not None else 500
        if n_patients < 1 or n_patients > 50_000:
            logger.error("--rows must be between 1 and 50000 (or use --total-rows)")
            return 1
    notif_start = notif_end = None
    if args.notification_from_last_month:
        now = pd.Timestamp.now()
        notif_start = (now.replace(day=1) - pd.offsets.MonthBegin(1)).normalize()
        notif_end = now
        logger.info("Notification dates in range [%s, %s]", notif_start.date(), notif_end.date())
    out = args.output
    if out is None:
        out = get_app_dir() / "Data" / "patients.xlsx"
    out = Path(out)
    try:
        rows = generate_patient_rows(
            n_patients,
            seed=args.seed,
            months=args.months,
            notif_date_start=notif_start,
            notif_date_end=notif_end,
        )
        write_excel(out, rows, backup=not args.no_backup)
        return 0
    except Exception as e:
        logger.exception("Failed to generate Excel: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
