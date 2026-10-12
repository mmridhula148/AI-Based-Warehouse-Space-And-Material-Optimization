"""
SmartStock AI - Data Processor Module
Handles CSV parsing, data validation, transformations, and tabular computations.
Designed with Pandas integration and a robust native fallback engine.
"""

import csv
import io
from typing import List, Dict, Any, Tuple, Optional

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except Exception:
    pd = None
    PANDAS_AVAILABLE = False


class DataProcessor:
    @staticmethod
    def is_pandas_available() -> bool:
        return PANDAS_AVAILABLE

    @staticmethod
    def read_csv_data(file_content_or_path: str) -> List[Dict[str, Any]]:
        """Read CSV from file path or raw string content and return list of dicts."""
        if PANDAS_AVAILABLE:
            try:
                if "\n" in file_content_or_path or "\r" in file_content_or_path:
                    df = pd.read_csv(io.StringIO(file_content_or_path))
                else:
                    df = pd.read_csv(file_content_or_path)
                return df.fillna("").to_dict(orient="records")
            except Exception:
                pass

        # Native CSV reading fallback
        if "\n" in file_content_or_path or "\r" in file_content_or_path:
            f = io.StringIO(file_content_or_path)
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]
        else:
            with open(file_content_or_path, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                return [dict(row) for row in reader]

    @staticmethod
    def export_to_csv_string(records: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> str:
        """Export list of records to CSV string."""
        if not records:
            return ""
        if PANDAS_AVAILABLE:
            try:
                df = pd.DataFrame(records)
                if fieldnames:
                    cols = [c for c in fieldnames if c in df.columns]
                    df = df[cols]
                return df.to_csv(index=False)
            except Exception:
                pass

        output = io.StringIO()
        if not fieldnames:
            fieldnames = list(records[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for row in records:
            writer.writerow(row)
        return output.getvalue()

    @staticmethod
    def validate_inventory_record(row: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Validate single inventory product record.
        Returns: (is_valid, error_message, cleaned_dict)
        """
        required_fields = ['product_id', 'name', 'category', 'length_cm', 'width_cm', 'height_cm', 'daily_demand', 'picking_frequency']
        for field in required_fields:
            val = str(row.get(field, '')).strip()
            if not val:
                return False, f"Missing required field: '{field}'", None

        product_id = str(row['product_id']).strip().upper()
        name = str(row['name']).strip()
        category = str(row['category']).strip()

        try:
            length_cm = float(row['length_cm'])
            width_cm = float(row['width_cm'])
            height_cm = float(row['height_cm'])
            if length_cm <= 0 or width_cm <= 0 or height_cm <= 0:
                return False, f"Dimensions must be greater than zero for product '{product_id}'", None
        except ValueError:
            return False, f"Invalid dimension value for product '{product_id}'. Must be numeric.", None

        unit_volume = length_cm * width_cm * height_cm

        try:
            weight_kg = float(row.get('weight_kg', 1.0))
            if weight_kg < 0:
                return False, f"Weight cannot be negative for product '{product_id}'", None
        except ValueError:
            weight_kg = 1.0

        try:
            daily_demand = int(float(row['daily_demand']))
            if daily_demand < 0:
                return False, f"Daily demand cannot be negative for product '{product_id}'", None
        except ValueError:
            return False, f"Invalid daily demand for product '{product_id}'. Must be integer.", None

        picking_freq = str(row.get('picking_frequency', 'Medium')).strip().capitalize()
        if picking_freq not in ['High', 'Medium', 'Low']:
            if daily_demand >= 60:
                picking_freq = 'High'
            elif daily_demand >= 25:
                picking_freq = 'Medium'
            else:
                picking_freq = 'Low'

        compat_req = str(row.get('compatibility_req', 'Standard')).strip()
        if not compat_req:
            compat_req = 'Standard'

        curr_loc = str(row.get('current_location_id', 'Unassigned')).strip()
        if not curr_loc or curr_loc.lower() in ['none', 'null', 'nan', '']:
            curr_loc = 'Unassigned'

        cleaned = {
            'product_id': product_id,
            'name': name,
            'category': category,
            'length_cm': length_cm,
            'width_cm': width_cm,
            'height_cm': height_cm,
            'unit_volume_cm3': round(unit_volume, 2),
            'weight_kg': round(weight_kg, 2),
            'daily_demand': daily_demand,
            'picking_frequency': picking_freq,
            'compatibility_req': compat_req,
            'current_location_id': curr_loc
        }
        return True, None, cleaned

    @staticmethod
    def validate_location_record(row: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Validate single warehouse storage location record.
        Returns: (is_valid, error_message, cleaned_dict)
        """
        required_fields = ['location_id', 'zone', 'length_cm', 'width_cm', 'height_cm', 'accessibility_score', 'distance_meters']
        for field in required_fields:
            val = str(row.get(field, '')).strip()
            if not val:
                return False, f"Missing required location field: '{field}'", None

        location_id = str(row['location_id']).strip().upper()
        zone = str(row['zone']).strip().upper()

        try:
            aisle = int(row.get('aisle', 1))
            rack = int(row.get('rack', 1))
            level = int(row.get('level', 1))
        except ValueError:
            aisle, rack, level = 1, 1, 1

        try:
            length_cm = float(row['length_cm'])
            width_cm = float(row['width_cm'])
            height_cm = float(row['height_cm'])
            if length_cm <= 0 or width_cm <= 0 or height_cm <= 0:
                return False, f"Dimensions must be positive for location '{location_id}'", None
        except ValueError:
            return False, f"Invalid dimension value for location '{location_id}'", None

        calc_volume = length_cm * width_cm * height_cm
        try:
            max_volume_cm3 = float(row.get('max_volume_cm3', calc_volume))
            if max_volume_cm3 <= 0:
                max_volume_cm3 = calc_volume
        except ValueError:
            max_volume_cm3 = calc_volume

        try:
            max_weight_kg = float(row.get('max_weight_kg', 300.0))
            if max_weight_kg <= 0:
                max_weight_kg = 300.0
        except ValueError:
            max_weight_kg = 300.0

        try:
            accessibility = float(row['accessibility_score'])
            if not (0 <= accessibility <= 100):
                return False, f"Accessibility score must be between 0 and 100 for location '{location_id}'", None
        except ValueError:
            return False, f"Invalid accessibility score for location '{location_id}'", None

        try:
            distance = float(row['distance_meters'])
            if distance < 0:
                return False, f"Distance cannot be negative for location '{location_id}'", None
        except ValueError:
            return False, f"Invalid distance value for location '{location_id}'", None

        allowed = str(row.get('allowed_categories', 'All')).strip()
        if not allowed:
            allowed = 'All'

        status = str(row.get('status', 'Available')).strip().capitalize()
        if status not in ['Available', 'Occupied', 'Maintenance', 'Unavailable']:
            status = 'Available'

        cleaned = {
            'location_id': location_id,
            'zone': zone,
            'aisle': aisle,
            'rack': rack,
            'level': level,
            'length_cm': length_cm,
            'width_cm': width_cm,
            'height_cm': height_cm,
            'max_volume_cm3': round(max_volume_cm3, 2),
            'max_weight_kg': round(max_weight_kg, 2),
            'accessibility_score': round(accessibility, 2),
            'distance_meters': round(distance, 2),
            'allowed_categories': allowed,
            'status': status
        }
        return True, None, cleaned
