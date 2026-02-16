#!/usr/bin/env python3
"""
Extract NDDF pricing information for specified medications.

The script reads the flat-files delivered with the NDDF Plus dataset and
generates a JSON report containing:
    - The latest WAC (WHN) unit price per NDC
    - The latest WAC package price per NDC
    - A derived price-per-day using provided dose/frequency assumptions

It filters results to oral tablet dosage forms for the requested strengths.
"""

from __future__ import annotations

import os
import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

# Set NDDF_ROOT in environment to your NDDF Plus "Descriptive and Pricing" data directory
ROOT = Path(os.environ.get("NDDF_ROOT", "./nddf_data"))

MEDNAMES_DIR = ROOT / "NDDF MEDNAMES 3.0"
BASICS_DIR = ROOT / "NDDF BASICS 3.0"
GENERIC_DIR = BASICS_DIR / "Generic Formulation and Ingredient"
PACKAGED_DIR = BASICS_DIR / "Packaged Product"
PRICING_DIR = BASICS_DIR / "Pricing"

RMIID1_MED = MEDNAMES_DIR / "RMIID1_MED"
RMINDC1_NDC_MEDID = MEDNAMES_DIR / "RMINDC1_NDC_MEDID"
RPEIGR0_GCNSEQNO_RT_RELATION = GENERIC_DIR / "RPEIGR0_GCNSEQNO_RT_RELATION"
RPEIRM0_RT_MSTR = GENERIC_DIR / "RPEIRM0_RT_MSTR"
RPEINR0_NDC_RT_RELATION = PACKAGED_DIR / "RPEINR0_NDC_RT_RELATION"
RNDC14_NDC_MSTR = PACKAGED_DIR / "RNDC14_NDC_MSTR"
RNP3_NDC_PRICE = PRICING_DIR / "RNP3_NDC_PRICE"
RNPTYPD0_NDC_PRICE_TYPE_DESC = PRICING_DIR / "RNPTYPD0_NDC_PRICE_TYPE_DESC"


DATE_FMT = "%Y%m%d"
WHN_UNIT = "09"
WHN_PKG = "10"


def read_pipe_file(path: Path) -> Iterable[List[str]]:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            yield line.rstrip("\n").split("|")


@dataclass
class FrequencyInfo:
    label: str
    daily_units: Decimal
    note: Optional[str] = None


@dataclass
class MedicationTarget:
    key: str
    med_desc: str
    display_name: str
    generic_or_brand: str
    frequency: FrequencyInfo
    medid: Optional[str] = None
    gcn_seqno: Optional[str] = None
    generic_medid: Optional[str] = None
    ndcs: Set[str] = field(default_factory=set)


TARGETS: List[MedicationTarget] = [
    MedicationTarget(
        key="atorvastatin_generic",
        med_desc="atorvastatin 80 mg tablet",
        display_name="atorvastatin 80 mg tablet",
        generic_or_brand="Generic",
        frequency=FrequencyInfo("QPM", Decimal("1")),
    ),
    MedicationTarget(
        key="atorvastatin_brand",
        med_desc="Lipitor 80 mg tablet",
        display_name="Lipitor 80 mg tablet",
        generic_or_brand="Brand",
        frequency=FrequencyInfo("QPM", Decimal("1")),
    ),
    MedicationTarget(
        key="carvedilol_generic",
        med_desc="carvedilol 6.25 mg tablet",
        display_name="carvedilol 6.25 mg tablet",
        generic_or_brand="Generic",
        frequency=FrequencyInfo("BID with meals", Decimal("2")),
    ),
    MedicationTarget(
        key="carvedilol_brand",
        med_desc="Coreg 6.25 mg tablet",
        display_name="Coreg 6.25 mg tablet",
        generic_or_brand="Brand",
        frequency=FrequencyInfo("BID with meals", Decimal("2")),
    ),
    MedicationTarget(
        key="clopidogrel_generic",
        med_desc="clopidogrel 75 mg tablet",
        display_name="clopidogrel 75 mg tablet",
        generic_or_brand="Generic",
        frequency=FrequencyInfo("Daily", Decimal("1")),
    ),
    MedicationTarget(
        key="clopidogrel_brand",
        med_desc="Plavix 75 mg tablet",
        display_name="Plavix 75 mg tablet",
        generic_or_brand="Brand",
        frequency=FrequencyInfo("Daily", Decimal("1")),
    ),
    MedicationTarget(
        key="fenofibrate_generic",
        med_desc="fenofibrate 160 mg tablet",
        display_name="fenofibrate 160 mg tablet",
        generic_or_brand="Generic",
        frequency=FrequencyInfo("Daily with dinner", Decimal("1")),
    ),
    MedicationTarget(
        key="fenofibrate_brand",
        med_desc="Lofibra 160 mg tablet",
        display_name="Lofibra 160 mg tablet",
        generic_or_brand="Brand",
        frequency=FrequencyInfo("Daily with dinner", Decimal("1")),
    ),
    MedicationTarget(
        key="lisinopril_generic",
        med_desc="lisinopril 10 mg tablet",
        display_name="lisinopril 10 mg tablet",
        generic_or_brand="Generic",
        frequency=FrequencyInfo("Daily", Decimal("1")),
    ),
    MedicationTarget(
        key="lisinopril_prinivil",
        med_desc="Prinivil 10 mg tablet",
        display_name="Prinivil 10 mg tablet",
        generic_or_brand="Brand",
        frequency=FrequencyInfo("Daily", Decimal("1")),
    ),
    MedicationTarget(
        key="lisinopril_zestril",
        med_desc="Zestril 10 mg tablet",
        display_name="Zestril 10 mg tablet",
        generic_or_brand="Brand",
        frequency=FrequencyInfo("Daily", Decimal("1")),
    ),
    MedicationTarget(
        key="pantoprazole_generic",
        med_desc="pantoprazole 40 mg tablet,delayed release",
        display_name="pantoprazole 40 mg tablet, delayed release",
        generic_or_brand="Generic",
        frequency=FrequencyInfo("QAM AC", Decimal("1")),
    ),
    MedicationTarget(
        key="pantoprazole_brand",
        med_desc="Protonix 40 mg tablet,delayed release",
        display_name="Protonix 40 mg tablet, delayed release",
        generic_or_brand="Brand",
        frequency=FrequencyInfo("QAM AC", Decimal("1")),
    ),
    MedicationTarget(
        key="spironolactone_generic",
        med_desc="spironolactone 25 mg tablet",
        display_name="spironolactone 25 mg tablet",
        generic_or_brand="Generic",
        frequency=FrequencyInfo("Daily", Decimal("0.5"), note="12.5 mg daily dose assumed as 0.5 of a 25 mg tablet"),
    ),
    MedicationTarget(
        key="spironolactone_brand",
        med_desc="Aldactone 25 mg tablet",
        display_name="Aldactone 25 mg tablet",
        generic_or_brand="Brand",
        frequency=FrequencyInfo("Daily", Decimal("0.5"), note="12.5 mg daily dose assumed as 0.5 of a 25 mg tablet"),
    ),
]


def populate_med_metadata(targets: List[MedicationTarget]) -> None:
    lookup = {t.med_desc.lower(): t for t in targets}
    for row in read_pipe_file(RMIID1_MED):
        if len(row) < 20:
            continue
        medid, _, strength, strength_uom, med_desc, gcn_seqno, *_middle, med_status_cd, generic_medid = row
        key = med_desc.strip().lower()
        target = lookup.get(key)
        if not target:
            continue
        target.medid = medid.lstrip("0") or "0"
        target.gcn_seqno = gcn_seqno.lstrip("0") or "0"
        target.generic_medid = generic_medid.lstrip("0") or None


def collect_target_ndcs(targets: List[MedicationTarget]) -> Set[str]:
    medid_to_target: Dict[str, MedicationTarget] = {}
    for target in targets:
        if target.medid:
            medid_to_target[target.medid] = target

    target_ndcs: Set[str] = set()
    for row in read_pipe_file(RMINDC1_NDC_MEDID):
        if len(row) < 2:
            continue
        ndc, medid = row[0], row[1].lstrip("0") or "0"
        target = medid_to_target.get(medid)
        if target:
            target.ndcs.add(ndc)
            target_ndcs.add(ndc)
    return target_ndcs


def parse_routes() -> Dict[str, Set[str]]:
    routes: Dict[str, Set[str]] = defaultdict(set)
    rt_desc: Dict[str, str] = {}

    for row in read_pipe_file(RPEIRM0_RT_MSTR):
        if len(row) < 3:
            continue
        rt_id, short_desc = row[0], row[1]
        if short_desc:
            rt_desc[rt_id] = short_desc.strip().upper()

    for row in read_pipe_file(RPEINR0_NDC_RT_RELATION):
        if len(row) < 3:
            continue
        ndc, parent_rt_id, clinical_rt_id = row[:3]
        for rt_id in (parent_rt_id, clinical_rt_id):
            desc = rt_desc.get(rt_id)
            if desc:
                routes[ndc].add(desc)
    return routes


def is_oral_route(route_values: Set[str]) -> bool:
    if not route_values:
        return True
    normalized = {value.upper() for value in route_values}
    oral_tokens = {"ORAL", "PO", "PER OS"}
    if normalized.intersection(oral_tokens):
        return True
    return any("ORAL" in value for value in normalized)


def load_ndc_attributes(ndcs: Set[str]) -> Dict[str, Dict[str, str]]:
    attrs: Dict[str, Dict[str, str]] = {}
    for row in read_pipe_file(RNDC14_NDC_MSTR):
        if len(row) < 40:
            continue
        ndc = row[0]
        if ndc not in ndcs:
            continue
        record = {
            "LBLRID": row[1],
            "GCN_SEQNO": row[2],
            "PS": row[3],
            "DF": row[4],
            "LN": row[6],
            "BN": row[7],
            "DADDNC": row[11],
            "DUPDC": row[12],
            "OBSDTEC": row[26],
            "HCFA_UNIT": row[39] if len(row) > 39 else "",
        }
        attrs[ndc] = record
    return attrs


def parse_price_types() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for code, desc in read_pipe_file(RNPTYPD0_NDC_PRICE_TYPE_DESC):
        mapping[code] = desc
    return mapping


def load_latest_prices(ndcs: Set[str], price_types: Set[str]) -> Dict[Tuple[str, str], Tuple[datetime, Decimal]]:
    latest: Dict[Tuple[str, str], Tuple[datetime, Decimal]] = {}
    for row in read_pipe_file(RNP3_NDC_PRICE):
        if len(row) < 4:
            continue
        ndc, price_type, eff_dt, price_str = row
        if ndc not in ndcs or price_type not in price_types:
            continue
        if not eff_dt or eff_dt == "00000000":
            continue
        try:
            eff = datetime.strptime(eff_dt, DATE_FMT)
        except ValueError:
            continue
        price = Decimal(price_str.strip() or "0")
        key = (ndc, price_type)
        current = latest.get(key)
        if not current or eff > current[0]:
            latest[key] = (eff, price)
    return latest


def quantize_currency(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def main() -> None:
    populate_med_metadata(TARGETS)

    missing = [t.med_desc for t in TARGETS if not t.medid]
    if missing:
        raise SystemExit(f"MEDID not found for: {missing}")

    ndcs = collect_target_ndcs(TARGETS)

    ndc_routes = parse_routes()
    ndc_attrs = load_ndc_attributes(ndcs)
    price_type_map = parse_price_types()
    latest_prices = load_latest_prices(ndcs, {WHN_UNIT, WHN_PKG})

    results = []
    for target in TARGETS:
        for ndc in sorted(target.ndcs):
            routes = ndc_routes.get(ndc, set())
            if not is_oral_route(routes):
                continue
            attrs = ndc_attrs.get(ndc, {})
            obsolete = attrs.get("OBSDTEC")
            if obsolete and obsolete != "00000000":
                continue
            unit_price = latest_prices.get((ndc, WHN_UNIT))
            pkg_price = latest_prices.get((ndc, WHN_PKG))

            unit_price_val = quantize_currency(unit_price[1]) if unit_price else None
            package_price_val = quantize_currency(pkg_price[1]) if pkg_price else None

            price_per_day = None
            if unit_price_val is not None:
                price_per_day = quantize_currency(unit_price_val * target.frequency.daily_units)

            if unit_price_val is None and package_price_val is None:
                continue

            results.append(
                {
                    "Name": target.display_name,
                    "NDC": ndc,
                    "Route": sorted(routes) if routes else ["PO (default assumption)"],
                    "Price_WHN": f"{unit_price_val:.2f}" if unit_price_val is not None else None,
                    "Price_WHN_effective": unit_price[0].strftime("%Y-%m-%d") if unit_price else None,
                    "Package_Price": f"{package_price_val:.2f}" if package_price_val is not None else None,
                    "Package_Price_effective": pkg_price[0].strftime("%Y-%m-%d") if pkg_price else None,
                    "Price_per_day": f"{price_per_day:.2f}" if price_per_day is not None else None,
                    "Generic_or_Brand": target.generic_or_brand,
                    "Frequency": target.frequency.label,
                    "Daily_units": str(target.frequency.daily_units),
                    "Daily_note": target.frequency.note,
                    "Brand_Generic_NDC": None,
                    "Label_Name": attrs.get("LN"),
                    "Brand_Name": attrs.get("BN"),
                    "Package_Size": attrs.get("PS"),
                    "Obsolete_Date": attrs.get("OBSDTEC") or None,
                }
            )

    def to_date(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None

    condensed: Dict[Tuple[str, str], Dict[str, object]] = {}
    for entry in results:
        labeler = entry["NDC"][:5]
        key = (entry["Name"], labeler)
        candidate_date = to_date(entry.get("Price_WHN_effective")) or to_date(entry.get("Package_Price_effective"))
        existing = condensed.get(key)
        if not existing:
            condensed[key] = {
                **entry,
                "Labeler": labeler,
                "Price_Effective": candidate_date.strftime("%Y-%m-%d") if candidate_date else None,
            }
            continue
        existing_date = to_date(existing.get("Price_WHN_effective")) or to_date(existing.get("Package_Price_effective"))
        if candidate_date and (not existing_date or candidate_date > existing_date):
            condensed[key] = {
                **entry,
                "Labeler": labeler,
                "Price_Effective": candidate_date.strftime("%Y-%m-%d"),
            }

    output = {
        "detail_rows": results,
        "condensed_rows": sorted(condensed.values(), key=lambda row: (row["Name"], row["NDC"])),
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()

