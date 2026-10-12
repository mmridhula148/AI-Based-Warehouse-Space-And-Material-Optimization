"""
SmartStock AI - Database Management Layer
Manages SQLite storage for Products, Storage Locations, Recommendations, and History.
Ensures relational consistency and dynamic capacity tracking.
"""

import sqlite3
import os
import json
from typing import List, Dict, Any, Optional
from data_processor import DataProcessor

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "smartstock.db")
SAMPLE_INVENTORY_PATH = os.path.join(os.path.dirname(__file__), "data", "sample_inventory.csv")
SAMPLE_LOCATIONS_PATH = os.path.join(os.path.dirname(__file__), "data", "sample_locations.csv")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(reset: bool = False):
    """Initialize database tables. If reset is True, drops and recreates schema."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if reset:
            cursor.execute("DROP TABLE IF EXISTS recommendations")
            cursor.execute("DROP TABLE IF EXISTS baseline_backup")
            cursor.execute("DROP TABLE IF EXISTS products")
            cursor.execute("DROP TABLE IF EXISTS locations")
            cursor.execute("DROP TABLE IF EXISTS settings")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS locations (
                location_id TEXT PRIMARY KEY,
                zone TEXT NOT NULL,
                aisle INTEGER DEFAULT 1,
                rack INTEGER DEFAULT 1,
                level INTEGER DEFAULT 1,
                length_cm REAL NOT NULL,
                width_cm REAL NOT NULL,
                height_cm REAL NOT NULL,
                max_volume_cm3 REAL NOT NULL,
                max_weight_kg REAL NOT NULL DEFAULT 300.0,
                accessibility_score REAL NOT NULL,
                distance_meters REAL NOT NULL,
                allowed_categories TEXT DEFAULT 'All',
                status TEXT DEFAULT 'Available'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                length_cm REAL NOT NULL,
                width_cm REAL NOT NULL,
                height_cm REAL NOT NULL,
                unit_volume_cm3 REAL NOT NULL,
                weight_kg REAL NOT NULL DEFAULT 1.0,
                daily_demand INTEGER NOT NULL,
                picking_frequency TEXT NOT NULL,
                compatibility_req TEXT DEFAULT 'Standard',
                current_location_id TEXT DEFAULT 'Unassigned'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                current_location_id TEXT,
                recommended_location_id TEXT,
                score REAL,
                baseline_distance REAL,
                optimized_distance REAL,
                distance_delta REAL,
                reason TEXT,
                benefit TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products (product_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS baseline_backup (
                product_id TEXT PRIMARY KEY,
                current_location_id TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()


def seed_sample_data(force: bool = False):
    """Seed sample data from CSV files if database is empty or force is True."""
    init_db(reset=force)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM locations")
        loc_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM products")
        prod_count = cursor.fetchone()[0]

    if not force and loc_count > 0 and prod_count > 0:
        return

    # Load locations
    if os.path.exists(SAMPLE_LOCATIONS_PATH):
        raw_locs = DataProcessor.read_csv_data(SAMPLE_LOCATIONS_PATH)
        for row in raw_locs:
            valid, err, cleaned = DataProcessor.validate_location_record(row)
            if valid and cleaned:
                save_location(cleaned)

    # Load products
    if os.path.exists(SAMPLE_INVENTORY_PATH):
        raw_prods = DataProcessor.read_csv_data(SAMPLE_INVENTORY_PATH)
        for row in raw_prods:
            valid, err, cleaned = DataProcessor.validate_inventory_record(row)
            if valid and cleaned:
                save_product(cleaned)

    # Backup baseline state
    backup_baseline_locations()


def backup_baseline_locations():
    """Stores initial baseline assignments for rollback capability."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM baseline_backup")
        cursor.execute("INSERT INTO baseline_backup (product_id, current_location_id) SELECT product_id, current_location_id FROM products")
        conn.commit()


def restore_baseline_locations() -> int:
    """Restores baseline location assignments."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM baseline_backup")
        count = cursor.fetchone()[0]
        if count == 0:
            return 0
        cursor.execute("""
            UPDATE products 
            SET current_location_id = (
                SELECT b.current_location_id 
                FROM baseline_backup b 
                WHERE b.product_id = products.product_id
            )
            WHERE product_id IN (SELECT product_id FROM baseline_backup)
        """)
        conn.commit()
        return count


# --- Products CRUD ---

def get_all_products(filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if filters:
        if filters.get("category"):
            query += " AND category = ?"
            params.append(filters["category"])
        if filters.get("picking_frequency"):
            query += " AND picking_frequency = ?"
            params.append(filters["picking_frequency"])
        if filters.get("location"):
            query += " AND current_location_id = ?"
            params.append(filters["location"])
        if filters.get("search"):
            search_term = f"%{filters['search'].strip()}%"
            query += " AND (product_id LIKE ? OR name LIKE ? OR category LIKE ?)"
            params.extend([search_term, search_term, search_term])

    query += " ORDER BY product_id ASC"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_product(product_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE product_id = ?", (product_id.upper(),))
        row = cursor.fetchone()
        return dict(row) if row else None


def save_product(data: Dict[str, Any]) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO products (
                product_id, name, category, length_cm, width_cm, height_cm,
                unit_volume_cm3, weight_kg, daily_demand, picking_frequency,
                compatibility_req, current_location_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                name=excluded.name,
                category=excluded.category,
                length_cm=excluded.length_cm,
                width_cm=excluded.width_cm,
                height_cm=excluded.height_cm,
                unit_volume_cm3=excluded.unit_volume_cm3,
                weight_kg=excluded.weight_kg,
                daily_demand=excluded.daily_demand,
                picking_frequency=excluded.picking_frequency,
                compatibility_req=excluded.compatibility_req,
                current_location_id=excluded.current_location_id
        """, (
            data['product_id'].upper(),
            data['name'],
            data['category'],
            data['length_cm'],
            data['width_cm'],
            data['height_cm'],
            data['unit_volume_cm3'],
            data['weight_kg'],
            data['daily_demand'],
            data['picking_frequency'],
            data['compatibility_req'],
            data.get('current_location_id', 'Unassigned')
        ))
        conn.commit()
        return True


def delete_product(product_id: str) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE product_id = ?", (product_id.upper(),))
        conn.commit()
        return cursor.rowcount > 0


# --- Locations CRUD ---

def get_all_locations() -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM locations ORDER BY zone ASC, aisle ASC, rack ASC, level ASC, location_id ASC")
        locations = [dict(row) for row in cursor.fetchall()]

        # Compute dynamic occupancy and assigned products
        cursor.execute("SELECT product_id, name, unit_volume_cm3, weight_kg, current_location_id FROM products WHERE current_location_id != 'Unassigned'")
        assigned = cursor.fetchall()

        loc_map = {loc['location_id']: loc for loc in locations}
        for loc in locations:
            loc['assigned_products'] = []
            loc['current_volume_cm3'] = 0.0
            loc['current_weight_kg'] = 0.0

        for p in assigned:
            lid = p['current_location_id']
            if lid in loc_map:
                loc_map[lid]['assigned_products'].append(dict(p))
                loc_map[lid]['current_volume_cm3'] += p['unit_volume_cm3']
                loc_map[lid]['current_weight_kg'] += p['weight_kg']

        for loc in locations:
            loc['current_volume_cm3'] = round(loc['current_volume_cm3'], 2)
            loc['current_weight_kg'] = round(loc['current_weight_kg'], 2)
            cap = loc['max_volume_cm3']
            loc['utilization_pct'] = round((loc['current_volume_cm3'] / cap * 100), 2) if cap > 0 else 0.0
            # Dynamic status badge
            if loc['status'] != 'Maintenance':
                if loc['utilization_pct'] >= 99.0:
                    loc['display_status'] = 'Full'
                elif loc['utilization_pct'] > 0.0:
                    loc['display_status'] = 'Occupied'
                else:
                    loc['display_status'] = 'Empty'
            else:
                loc['display_status'] = 'Maintenance'

        return locations


def get_location(location_id: str) -> Optional[Dict[str, Any]]:
    locs = get_all_locations()
    for loc in locs:
        if loc['location_id'].upper() == location_id.upper():
            return loc
    return None


def save_location(data: Dict[str, Any]) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO locations (
                location_id, zone, aisle, rack, level, length_cm, width_cm, height_cm,
                max_volume_cm3, max_weight_kg, accessibility_score, distance_meters,
                allowed_categories, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(location_id) DO UPDATE SET
                zone=excluded.zone,
                aisle=excluded.aisle,
                rack=excluded.rack,
                level=excluded.level,
                length_cm=excluded.length_cm,
                width_cm=excluded.width_cm,
                height_cm=excluded.height_cm,
                max_volume_cm3=excluded.max_volume_cm3,
                max_weight_kg=excluded.max_weight_kg,
                accessibility_score=excluded.accessibility_score,
                distance_meters=excluded.distance_meters,
                allowed_categories=excluded.allowed_categories,
                status=excluded.status
        """, (
            data['location_id'].upper(),
            data['zone'].upper(),
            data.get('aisle', 1),
            data.get('rack', 1),
            data.get('level', 1),
            data['length_cm'],
            data['width_cm'],
            data['height_cm'],
            data['max_volume_cm3'],
            data.get('max_weight_kg', 300.0),
            data['accessibility_score'],
            data['distance_meters'],
            data.get('allowed_categories', 'All'),
            data.get('status', 'Available')
        ))
        conn.commit()
        return True


def delete_location(location_id: str) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Unassign products currently located here
        cursor.execute("UPDATE products SET current_location_id = 'Unassigned' WHERE current_location_id = ?", (location_id.upper(),))
        cursor.execute("DELETE FROM locations WHERE location_id = ?", (location_id.upper(),))
        conn.commit()
        return cursor.rowcount > 0


# --- Recommendations & Optimization Storage ---

def save_recommendations(recs: List[Dict[str, Any]]):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM recommendations")
        for r in recs:
            cursor.execute("""
                INSERT INTO recommendations (
                    product_id, current_location_id, recommended_location_id,
                    score, baseline_distance, optimized_distance, distance_delta,
                    reason, benefit, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r['product_id'],
                r['current_location_id'],
                r['recommended_location_id'],
                r['score'],
                r['baseline_distance'],
                r['optimized_distance'],
                r['distance_delta'],
                r['reason'],
                r['benefit'],
                r['status']
            ))
        conn.commit()


def get_latest_recommendations() -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.*, p.name, p.category, p.daily_demand, p.picking_frequency, p.unit_volume_cm3, p.compatibility_req
            FROM recommendations r
            JOIN products p ON r.product_id = p.product_id
            ORDER BY r.distance_delta DESC, r.score DESC
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def apply_recommendations(product_ids: Optional[List[str]] = None) -> int:
    """Apply recommended storage locations to products."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if product_ids:
            placeholders = ",".join("?" for _ in product_ids)
            cursor.execute(f"""
                UPDATE products
                SET current_location_id = (
                    SELECT recommended_location_id 
                    FROM recommendations 
                    WHERE recommendations.product_id = products.product_id
                    AND recommended_location_id NOT IN ('No Suitable Location', 'Unassigned')
                )
                WHERE product_id IN ({placeholders})
                AND product_id IN (
                    SELECT product_id FROM recommendations 
                    WHERE recommended_location_id NOT IN ('No Suitable Location', 'Unassigned')
                )
            """, [p.upper() for p in product_ids])
        else:
            cursor.execute("""
                UPDATE products
                SET current_location_id = (
                    SELECT recommended_location_id 
                    FROM recommendations 
                    WHERE recommendations.product_id = products.product_id
                    AND recommended_location_id NOT IN ('No Suitable Location', 'Unassigned')
                )
                WHERE product_id IN (
                    SELECT product_id FROM recommendations 
                    WHERE recommended_location_id NOT IN ('No Suitable Location', 'Unassigned')
                )
            """)
        conn.commit()
        return cursor.rowcount
