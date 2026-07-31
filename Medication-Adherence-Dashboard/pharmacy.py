"""
Nearest pharmacy lookup by city for agent-generated messages.
Uses static map first; can fetch real-time from OpenStreetMap when city not in list.
"""
from __future__ import annotations

import os
from typing import Any

# City (normalized lower) -> nearest pharmacy details (name, address, phone, opening_hours, source)
PHARMACY_BY_CITY: dict[str, dict[str, str]] = {
    "new york": {"name": "CVS Pharmacy", "address": "123 Main St, New York, NY 10001", "phone": "+1-212-555-0100", "opening_hours": "", "source": "CVS"},
    "los angeles": {"name": "Walgreens", "address": "456 Oak Ave, Los Angeles, CA 90001", "phone": "+1-310-555-0200", "opening_hours": "", "source": "Walgreens"},
    "chicago": {"name": "Walmart Pharmacy", "address": "789 State St, Chicago, IL 60601", "phone": "+1-312-555-0300", "opening_hours": "", "source": "Walmart"},
    "houston": {"name": "CVS Pharmacy", "address": "321 Houston Ave, Houston, TX 77001", "phone": "+1-713-555-0400", "opening_hours": "", "source": "CVS"},
    "phoenix": {"name": "Walgreens", "address": "654 Central Ave, Phoenix, AZ 85001", "phone": "+1-602-555-0500", "opening_hours": "", "source": "Walgreens"},
    "philadelphia": {"name": "Rite Aid", "address": "987 Market St, Philadelphia, PA 19101", "phone": "+1-215-555-0600", "opening_hours": "", "source": "Rite Aid"},
    "san antonio": {"name": "H-E-B Pharmacy", "address": "147 River Walk, San Antonio, TX 78205", "phone": "+1-210-555-0700", "opening_hours": "", "source": "H-E-B"},
    "san diego": {"name": "CVS Pharmacy", "address": "258 Harbor Dr, San Diego, CA 92101", "phone": "+1-619-555-0800", "opening_hours": "", "source": "CVS"},
    "dallas": {"name": "Walgreens", "address": "369 Commerce St, Dallas, TX 75201", "phone": "+1-214-555-0900", "opening_hours": "", "source": "Walgreens"},
    "san jose": {"name": "Safeway Pharmacy", "address": "741 First St, San Jose, CA 95101", "phone": "+1-408-555-1000", "opening_hours": "", "source": "Safeway"},
    "austin": {"name": "H-E-B Pharmacy", "address": "852 Congress Ave, Austin, TX 78701", "phone": "+1-512-555-1100", "opening_hours": "", "source": "H-E-B"},
    "jacksonville": {"name": "Winn-Dixie Pharmacy", "address": "963 Bay St, Jacksonville, FL 32202", "phone": "+1-904-555-1200", "opening_hours": "", "source": "Winn-Dixie"},
    "fort worth": {"name": "CVS Pharmacy", "address": "159 Sundance Sq, Fort Worth, TX 76102", "phone": "+1-817-555-1300", "opening_hours": "", "source": "CVS"},
    "columbus": {"name": "Kroger Pharmacy", "address": "357 High St, Columbus, OH 43215", "phone": "+1-614-555-1400", "opening_hours": "", "source": "Kroger"},
    "charlotte": {"name": "Harris Teeter Pharmacy", "address": "456 Tryon St, Charlotte, NC 28202", "phone": "+1-704-555-1500", "opening_hours": "", "source": "Harris Teeter"},
    "seattle": {"name": "Bartell Drugs", "address": "258 Pike St, Seattle, WA 98101", "phone": "+1-206-555-1600", "opening_hours": "", "source": "Bartell Drugs"},
    "denver": {"name": "Walgreens", "address": "159 16th St, Denver, CO 80202", "phone": "+1-303-555-1700", "opening_hours": "", "source": "Walgreens"},
    "boston": {"name": "CVS Pharmacy", "address": "753 Boylston St, Boston, MA 02116", "phone": "+1-617-555-1800", "opening_hours": "", "source": "CVS"},
    "mumbai": {"name": "Apollo Pharmacy", "address": "Andheri West, Mumbai 400058", "phone": "+91-22-5555-1900", "opening_hours": "", "source": "Apollo Pharmacy"},
    "delhi": {"name": "Medplus Pharmacy", "address": "Connaught Place, New Delhi 110001", "phone": "+91-11-5555-2000", "opening_hours": "", "source": "MedPlus"},
    "bangalore": {"name": "Apollo Pharmacy", "address": "MG Road, Bengaluru 560001", "phone": "+91-80-5555-2100", "opening_hours": "", "source": "Apollo Pharmacy"},
    "hyderabad": {"name": "Medplus Pharmacy", "address": "Banjara Hills, Hyderabad 500034", "phone": "+91-40-5555-2200", "opening_hours": "", "source": "MedPlus"},
    "chennai": {"name": "Apollo Pharmacy", "address": "T Nagar, Chennai 600017", "phone": "+91-44-5555-2300", "opening_hours": "", "source": "Apollo Pharmacy"},
    "kolkata": {"name": "Apollo Pharmacy", "address": "Park Street, Kolkata 700016", "phone": "+91-33-5555-2400", "opening_hours": "", "source": "Apollo Pharmacy"},
    "pune": {
        "name": "MedPlus India",
        "address": "Shop No 4, Shriram Jyoti CHS, Erandwane, Pune, Maharashtra 411004",
        "phone": "020 2542 3466",
        "opening_hours": "07:00 AM – 11:00 PM (All days)",
        "source": "MedPlus India",
    },
    # More US cities (including Virginia) so more patients match
    "richmond": {"name": "CVS Pharmacy", "address": "100 E Main St, Richmond, VA 23219", "phone": "+1-804-555-2500", "opening_hours": "8:00 AM – 10:00 PM", "source": "CVS"},
    "virginia beach": {"name": "Walgreens", "address": "4500 Virginia Beach Blvd, Virginia Beach, VA 23462", "phone": "+1-757-555-2600", "opening_hours": "8:00 AM – 10:00 PM", "source": "Walgreens"},
    "norfolk": {"name": "CVS Pharmacy", "address": "200 Granby St, Norfolk, VA 23510", "phone": "+1-757-555-2700", "opening_hours": "8:00 AM – 9:00 PM", "source": "CVS"},
    "virginia": {"name": "CVS Pharmacy", "address": "100 E Main St, Richmond, VA 23219", "phone": "+1-804-555-2500", "opening_hours": "8:00 AM – 10:00 PM", "source": "CVS"},
    "albuquerque": {"name": "Walgreens", "address": "300 Central Ave NW, Albuquerque, NM 87102", "phone": "+1-505-555-2800", "opening_hours": "", "source": "Walgreens"},
    "tucson": {"name": "CVS Pharmacy", "address": "100 N Stone Ave, Tucson, AZ 85701", "phone": "+1-520-555-2900", "opening_hours": "", "source": "CVS"},
    "el paso": {"name": "Walgreens", "address": "200 E San Antonio Ave, El Paso, TX 79901", "phone": "+1-915-555-3000", "opening_hours": "", "source": "Walgreens"},
    "nashville": {"name": "Walgreens", "address": "200 Broadway, Nashville, TN 37201", "phone": "+1-615-555-3100", "opening_hours": "", "source": "Walgreens"},
    "detroit": {"name": "CVS Pharmacy", "address": "100 Woodward Ave, Detroit, MI 48226", "phone": "+1-313-555-3200", "opening_hours": "", "source": "CVS"},
    "portland": {"name": "Walgreens", "address": "300 SW Broadway, Portland, OR 97205", "phone": "+1-503-555-3300", "opening_hours": "", "source": "Walgreens"},
    "las vegas": {"name": "CVS Pharmacy", "address": "200 Las Vegas Blvd S, Las Vegas, NV 89101", "phone": "+1-702-555-3400", "opening_hours": "", "source": "CVS"},
    "sacramento": {"name": "Walgreens", "address": "400 Capitol Mall, Sacramento, CA 95814", "phone": "+1-916-555-3500", "opening_hours": "", "source": "Walgreens"},
}

DEFAULT_PHARMACY = {"name": "Your local pharmacy", "address": "Contact your healthcare provider for the nearest location.", "phone": "", "opening_hours": "", "source": ""}


def _normalize_city(city: str | None) -> str | None:
    """Normalize city for lookup: strip, lower, and try first part if 'City, State' format."""
    if not city:
        return None
    s = str(city).strip()
    if not s or s.lower() in ("nan", "none", "n/a", "na"):
        return None
    s = s.lower()
    # If "City, State" or "City, Country", use city part
    if "," in s:
        s = s.split(",")[0].strip()
    return s if s else None


def _fetch_pharmacy_osm(city: str) -> dict[str, str] | None:
    """Fetch a pharmacy near the given city using OpenStreetMap Nominatim + Overpass (no API key). Returns None on failure."""
    if not city or len(city) < 2:
        return None
    try:
        import urllib.request
        import urllib.parse
        import json
        # 1) Geocode city to lat/lon
        query = urllib.parse.quote(f"{city}, USA")
        url_geo = f"https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1"
        req = urllib.request.Request(url_geo, headers={"User-Agent": "MedicationAdherenceDashboard/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        if not data:
            query_in = urllib.parse.quote(city)
            url_geo = f"https://nominatim.openstreetmap.org/search?q={query_in}&format=json&limit=1"
            req = urllib.request.Request(url_geo, headers={"User-Agent": "MedicationAdherenceDashboard/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
        if not data:
            return None
        lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
        # 2) Overpass: pharmacy within ~5km
        overpass = f'[out:json];node["amenity"="pharmacy"](around:5000,{lat},{lon});out body 1;'
        url_over = "https://overpass-api.de/api/interpreter"
        req = urllib.request.Request(url_over, data=overpass.encode(), method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            osm = json.loads(resp.read().decode())
        if not osm.get("elements"):
            return None
        el = osm["elements"][0]
        tags = el.get("tags", {})
        name = (tags.get("name") or tags.get("brand") or "Pharmacy").strip()
        addr_parts = [
            tags.get("addr:street"),
            tags.get("addr:city"),
            tags.get("addr:state"),
            tags.get("addr:postcode"),
        ]
        address = ", ".join(p for p in addr_parts if p) or (tags.get("addr:full") or f"Near {city}")
        phone = tags.get("phone") or tags.get("contact:phone") or ""
        return {
            "name": name,
            "address": address,
            "phone": phone.strip(),
            "opening_hours": (tags.get("opening_hours") or "").strip() or "-",
            "source": "OpenStreetMap",
        }
    except Exception:
        return None


def get_pharmacy_for_city(city: str | None) -> dict[str, str]:
    """Return nearest pharmacy details for the given city. Uses static map first; if not found, tries real-time OpenStreetMap lookup (when PHARMACY_USE_OSM=1)."""
    key = _normalize_city(city)
    if not key:
        return DEFAULT_PHARMACY.copy()
    # 1) Static lookup
    if key in PHARMACY_BY_CITY:
        return PHARMACY_BY_CITY[key].copy()
    # 2) Real-time lookup via OpenStreetMap when city not in static list (set PHARMACY_USE_OSM=0 to disable)
    if os.getenv("PHARMACY_USE_OSM", "1").strip() not in ("0", "false", "no"):
        live = _fetch_pharmacy_osm(key)
        if live:
            return live
    return DEFAULT_PHARMACY.copy()


def format_pharmacy_for_message(pharmacy: dict[str, str]) -> str:
    """Format pharmacy details for inclusion in SMS/email (short, one line preferred)."""
    name = pharmacy.get("name", "").strip()
    phone = pharmacy.get("phone", "").strip()
    if not name:
        return "Contact your healthcare provider for the nearest pharmacy."
    if phone:
        return f"Nearest pharmacy: {name}, Tel: {phone}"
    return f"Nearest pharmacy: {name}"


def format_pharmacy_table(pharmacy: dict[str, str]) -> str:
    """Format nearest pharmacy details as a table (Pharmacy Name | Address | Phone | Opening Hours | Source)."""
    name = pharmacy.get("name", "").strip() or "-"
    address = pharmacy.get("address", "").strip() or "-"
    phone = pharmacy.get("phone", "").strip() or "-"
    opening_hours = pharmacy.get("opening_hours", "").strip() or "-"
    source = pharmacy.get("source", "").strip() or "-"
    # Build a simple text table (readable in SMS, email, and UI)
    header = "Pharmacy Name | Address | Phone | Opening Hours | Source"
    separator = "-" * 20 + " | " + "-" * 30 + " | " + "-" * 14 + " | " + "-" * 25 + " | " + "-" * 12
    row = f"{name} | {address} | {phone} | {opening_hours} | {source}"
    return f"Nearest pharmacy (by city):\n{header}\n{separator}\n{row}"
