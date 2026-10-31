"""Manufacturer name normalization.

Upstream labels differ ("CHEVY" vs "Chevrolet", "MERCEDES" vs "Mercedes-Benz").
A normalization that loses the original label is unacceptable for provenance, so
the raw label is always preserved on the source record; only the canonical entity
is normalized here.
"""

from __future__ import annotations

import re

from .keys import slug_key

# alias (upper-case) -> canonical display name
ALIASES: dict[str, str] = {
    "ACURA": "Acura",
    "ALFA ROMEO": "Alfa Romeo",
    "ALFAROMEO": "Alfa Romeo",
    "AUDI": "Audi",
    "BMW": "BMW",
    "BUICK": "Buick",
    "BYD": "BYD",
    "CADILLAC": "Cadillac",
    "CHEVROLET": "Chevrolet",
    "CHEVY": "Chevrolet",
    "CHEV": "Chevrolet",
    "CHRYSLER": "Chrysler",
    "CITROEN": "Citroën",
    "DACIA": "Dacia",
    "DODGE": "Dodge",
    "FIAT": "Fiat",
    "FORD": "Ford",
    "GEO": "Geo",
    "GM": "General Motors",
    "GMC": "GMC",
    "HONDA": "Honda",
    "HYUNDAI": "Hyundai",
    "INFINITI": "Infiniti",
    "ISUZU": "Isuzu",
    "JAGUAR": "Jaguar",
    "JEEP": "Jeep",
    "KIA": "Kia",
    "LANDROVER": "Land Rover",
    "LAND ROVER": "Land Rover",
    "LEXUS": "Lexus",
    "LINCOLN": "Lincoln",
    "MAZDA": "Mazda",
    "MERCEDES": "Mercedes-Benz",
    "MERCEDES BENZ": "Mercedes-Benz",
    "MERCEDES-BENZ": "Mercedes-Benz",
    "MERCURY": "Mercury",
    "MINI": "MINI",
    "MITSUBISHI": "Mitsubishi",
    "NISSAN": "Nissan",
    "OLDSMOBILE": "Oldsmobile",
    "OPEL": "Opel",
    "PEUGEOT": "Peugeot",
    "PLYMOUTH": "Plymouth",
    "PONTIAC": "Pontiac",
    "PORSCHE": "Porsche",
    "RAM": "Ram",
    "RENAULT": "Renault",
    "RIVIAN": "Rivian",
    "SAAB": "Saab",
    "SATURN": "Saturn",
    "SEAT": "SEAT",
    "SKODA": "Škoda",
    "SUBARU": "Subaru",
    "SUZUKI": "Suzuki",
    "TESLA": "Tesla",
    "TOYOTA": "Toyota",
    "VAUXHALL": "Vauxhall",
    "VOLKSWAGEN": "Volkswagen",
    "VW": "Volkswagen",
    "VOLVO": "Volvo",
    "VOYAH": "Voyah",
}

# labels that must never become a real manufacturer entity
NON_MANUFACTURERS = {
    "GENERIC": "generic",
    "SAEJ2012.2002": "generic",
    "SAE J2012": "generic",
    "OTHER": "other",
    "UNKNOWN": "unknown",
    "ANY": "any",
}


def canonical_manufacturer(label: str | None) -> str | None:
    """Return the canonical display name, or None for non-manufacturer labels."""
    if not label:
        return None
    key = re.sub(r"\s+", " ", str(label)).strip().upper()
    if key in NON_MANUFACTURERS:
        return None
    if key in ALIASES:
        return ALIASES[key]
    cleaned = re.sub(r"\s+", " ", str(label)).strip()
    return cleaned.title() if cleaned.isupper() else cleaned


def manufacturer_slug(name: str) -> str:
    return slug_key(name)
