"""
SmartStock AI - Flask Web Application & API Server
Full-stack warehouse space and material optimization platform.
"""

import os
from flask import Flask, render_template, request, jsonify, Response, send_file
import database
from optimizer import WarehouseOptimizer
from data_processor import DataProcessor

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload

# Initialize database on startup
database.seed_sample_data(force=False)


@app.route('/')
def index():
    return render_template('index.html')


# ==========================================
# DASHBOARD & PERFORMANCE APIS
# ==========================================

@app.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    try:
        products = database.get_all_products()
        locations = database.get_all_locations()
        recs = database.get_latest_recommendations()

        total_products = len(products)
        total_locations = len(locations)
        
        total_usable_volume = sum([l['max_volume_cm3'] for l in locations])
        occupied_volume = sum([l['current_volume_cm3'] for l in locations])
        available_volume = max(0.0, total_usable_volume - occupied_volume)
        utilization_pct = round((occupied_volume / max(total_usable_volume, 1.0)) * 100.0, 1)

        # Performance calculations
        perf = WarehouseOptimizer.evaluate_performance(products, locations, recs)
        
        # Products requiring relocation count
        relocations_needed = sum(1 for r in recs if r.get('status') == 'Recommended')
        opt_status = "Optimized" if relocations_needed == 0 and len(recs) > 0 else ("Pending Review" if len(recs) > 0 else "Unoptimized")

        # Category distribution
        category_counts = {}
        for p in products:
            cat = p['category']
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Picking frequency distribution
        freq_counts = {'High': 0, 'Medium': 0, 'Low': 0}
        for p in products:
            f = p.get('picking_frequency', 'Medium')
            if f in freq_counts:
                freq_counts[f] += 1
            else:
                freq_counts['Medium'] += 1

        # Zone capacity vs occupancy
        zone_stats = {}
        for l in locations:
            z = l['zone']
            if z not in zone_stats:
                zone_stats[z] = {'capacity': 0.0, 'occupied': 0.0, 'locations_count': 0}
            zone_stats[z]['capacity'] += l['max_volume_cm3']
            zone_stats[z]['occupied'] += l['current_volume_cm3']
            zone_stats[z]['locations_count'] += 1

        # Average picking distance
        distances = []
        loc_map = {l['location_id']: l for l in locations}
        for p in products:
            lid = p.get('current_location_id')
            if lid in loc_map:
                distances.append(loc_map[lid]['distance_meters'])
            else:
                distances.append(45.0)
        avg_pick_dist = round(sum(distances) / max(len(distances), 1), 1)

        return jsonify({
            'success': True,
            'kpis': {
                'total_products': total_products,
                'total_locations': total_locations,
                'total_usable_volume_cm3': round(total_usable_volume, 0),
                'occupied_volume_cm3': round(occupied_volume, 0),
                'available_volume_cm3': round(available_volume, 0),
                'space_utilization_pct': utilization_pct,
                'products_requiring_relocation': relocations_needed,
                'optimization_status': opt_status,
                'avg_picking_distance_m': avg_pick_dist,
                'baseline_daily_distance_m': perf['baseline']['daily_picking_distance_m'],
                'optimized_daily_distance_m': perf['optimized']['daily_picking_distance_m'],
                'daily_labor_cost': perf['baseline']['daily_labor_cost'],
                'annual_labor_cost': perf['baseline']['annual_labor_cost'],
                'estimated_annual_savings': perf['comparison']['annual_cost_savings'],
                'distance_reduction_pct': perf['comparison']['distance_reduction_pct']
            },
            'charts': {
                'category_distribution': category_counts,
                'picking_frequency': freq_counts,
                'zone_stats': zone_stats,
                'space_utilization': {
                    'occupied_pct': utilization_pct,
                    'available_pct': round(100.0 - utilization_pct, 1)
                },
                'distance_comparison': {
                    'baseline_m': perf['baseline']['daily_picking_distance_m'],
                    'optimized_m': perf['optimized']['daily_picking_distance_m']
                },
                'cost_comparison': {
                    'baseline_daily_cost': perf['baseline']['daily_labor_cost'],
                    'optimized_daily_cost': perf['optimized']['daily_labor_cost']
                }
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/performance/comparison', methods=['GET'])
def get_performance_comparison():
    try:
        products = database.get_all_products()
        locations = database.get_all_locations()
        recs = database.get_latest_recommendations()
        perf = WarehouseOptimizer.evaluate_performance(products, locations, recs)
        return jsonify({'success': True, 'data': perf})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# INVENTORY CRUD APIS
# ==========================================

@app.route('/api/products', methods=['GET'])
def get_products():
    try:
        filters = {
            'category': request.args.get('category'),
            'picking_frequency': request.args.get('picking_frequency'),
            'location': request.args.get('location'),
            'search': request.args.get('search')
        }
        products = database.get_all_products(filters)
        return jsonify({'success': True, 'count': len(products), 'products': products})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/products/<product_id>', methods=['GET'])
def get_product(product_id):
    try:
        prod = database.get_product(product_id)
        if not prod:
            return jsonify({'success': False, 'error': f"Product '{product_id}' not found"}), 404
        return jsonify({'success': True, 'product': prod})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/products', methods=['POST'])
def create_product():
    try:
        payload = request.get_json(force=True)
        if not payload:
            return jsonify({'success': False, 'error': 'Invalid JSON body'}), 400

        # Check for duplicate
        pid = str(payload.get('product_id', '')).strip().upper()
        if database.get_product(pid):
            return jsonify({'success': False, 'error': f"Product with ID '{pid}' already exists"}), 400

        valid, err, cleaned = DataProcessor.validate_inventory_record(payload)
        if not valid or not cleaned:
            return jsonify({'success': False, 'error': err}), 400

        # Check location validity if specified
        curr_loc = cleaned['current_location_id']
        if curr_loc != 'Unassigned':
            loc_obj = database.get_location(curr_loc)
            if not loc_obj:
                return jsonify({'success': False, 'error': f"Assigned location '{curr_loc}' does not exist"}), 400

        database.save_product(cleaned)
        return jsonify({'success': True, 'message': f"Product '{pid}' created successfully", 'product': cleaned}), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/products/<product_id>', methods=['PUT'])
def update_product(product_id):
    try:
        existing = database.get_product(product_id)
        if not existing:
            return jsonify({'success': False, 'error': f"Product '{product_id}' not found"}), 404

        payload = request.get_json(force=True)
        payload['product_id'] = product_id

        valid, err, cleaned = DataProcessor.validate_inventory_record(payload)
        if not valid or not cleaned:
            return jsonify({'success': False, 'error': err}), 400

        curr_loc = cleaned['current_location_id']
        if curr_loc != 'Unassigned':
            loc_obj = database.get_location(curr_loc)
            if not loc_obj:
                return jsonify({'success': False, 'error': f"Assigned location '{curr_loc}' does not exist"}), 400

        database.save_product(cleaned)
        return jsonify({'success': True, 'message': f"Product '{product_id}' updated successfully", 'product': cleaned})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/products/<product_id>', methods=['DELETE'])
def delete_product(product_id):
    try:
        deleted = database.delete_product(product_id)
        if not deleted:
            return jsonify({'success': False, 'error': f"Product '{product_id}' not found"}), 404
        return jsonify({'success': True, 'message': f"Product '{product_id}' deleted successfully"})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# STORAGE LOCATIONS CRUD APIS
# ==========================================

@app.route('/api/locations', methods=['GET'])
def get_locations():
    try:
        locations = database.get_all_locations()
        return jsonify({'success': True, 'count': len(locations), 'locations': locations})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/locations/<location_id>', methods=['GET'])
def get_location(location_id):
    try:
        loc = database.get_location(location_id)
        if not loc:
            return jsonify({'success': False, 'error': f"Location '{location_id}' not found"}), 404
        return jsonify({'success': True, 'location': loc})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/locations', methods=['POST'])
def create_location():
    try:
        payload = request.get_json(force=True)
        if not payload:
            return jsonify({'success': False, 'error': 'Invalid JSON body'}), 400

        lid = str(payload.get('location_id', '')).strip().upper()
        if database.get_location(lid):
            return jsonify({'success': False, 'error': f"Location with ID '{lid}' already exists"}), 400

        valid, err, cleaned = DataProcessor.validate_location_record(payload)
        if not valid or not cleaned:
            return jsonify({'success': False, 'error': err}), 400

        database.save_location(cleaned)
        return jsonify({'success': True, 'message': f"Location '{lid}' created successfully", 'location': cleaned}), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/locations/<location_id>', methods=['PUT'])
def update_location(location_id):
    try:
        existing = database.get_location(location_id)
        if not existing:
            return jsonify({'success': False, 'error': f"Location '{location_id}' not found"}), 404

        payload = request.get_json(force=True)
        payload['location_id'] = location_id

        valid, err, cleaned = DataProcessor.validate_location_record(payload)
        if not valid or not cleaned:
            return jsonify({'success': False, 'error': err}), 400

        database.save_location(cleaned)
        return jsonify({'success': True, 'message': f"Location '{location_id}' updated successfully", 'location': cleaned})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/locations/<location_id>', methods=['DELETE'])
def delete_location(location_id):
    try:
        deleted = database.delete_location(location_id)
        if not deleted:
            return jsonify({'success': False, 'error': f"Location '{location_id}' not found"}), 404
        return jsonify({'success': True, 'message': f"Location '{location_id}' deleted successfully"})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# OPTIMIZATION ENGINE APIS
# ==========================================

@app.route('/api/optimization/run', methods=['POST'])
def run_optimization():
    try:
        weights_data = request.get_json(silent=True) or {}
        optimizer = WarehouseOptimizer(weights=weights_data)

        products = database.get_all_products()
        locations = database.get_all_locations()

        if not products:
            return jsonify({'success': False, 'error': 'Cannot run optimization on empty inventory'}), 400
        if not locations:
            return jsonify({'success': False, 'error': 'No storage locations available in warehouse'}), 400

        results = optimizer.run_optimization(products, locations)
        
        # Save recommendations to database
        database.save_recommendations(results['recommendations'])

        # Compute performance summary
        perf = WarehouseOptimizer.evaluate_performance(products, locations, results['recommendations'])

        return jsonify({
            'success': True,
            'summary': results['summary'],
            'weights': results['weights'],
            'recommendations': database.get_latest_recommendations(),
            'performance': perf
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/optimization/recommendations', methods=['GET'])
def get_recommendations():
    try:
        recs = database.get_latest_recommendations()
        return jsonify({'success': True, 'count': len(recs), 'recommendations': recs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/optimization/apply', methods=['POST'])
def apply_optimization():
    try:
        payload = request.get_json(silent=True) or {}
        product_ids = payload.get('product_ids')
        applied_count = database.apply_recommendations(product_ids)
        return jsonify({
            'success': True,
            'message': f"Successfully applied {applied_count} storage assignments",
            'applied_count': applied_count
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/optimization/reset', methods=['POST'])
def reset_allocation():
    try:
        count = database.restore_baseline_locations()
        # Re-run optimization with defaults to refresh state
        products = database.get_all_products()
        locations = database.get_all_locations()
        optimizer = WarehouseOptimizer()
        res = optimizer.run_optimization(products, locations)
        database.save_recommendations(res['recommendations'])
        return jsonify({'success': True, 'message': f"Restored {count} products to baseline allocations"})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/demo/reset', methods=['POST'])
def reset_demo_data():
    try:
        database.seed_sample_data(force=True)
        # Run optimization
        products = database.get_all_products()
        locations = database.get_all_locations()
        optimizer = WarehouseOptimizer()
        res = optimizer.run_optimization(products, locations)
        database.save_recommendations(res['recommendations'])
        return jsonify({'success': True, 'message': 'Demo warehouse dataset restored successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# CSV IMPORT & EXPORT APIS
# ==========================================

@app.route('/api/template/inventory', methods=['GET'])
def template_inventory():
    headers = "product_id,name,category,length_cm,width_cm,height_cm,weight_kg,daily_demand,picking_frequency,compatibility_req,current_location_id\n"
    sample = "P999,Sample Electronic Component,Electronics,30.0,20.0,15.0,2.5,45,High,Standard,B01\n"
    return Response(
        headers + sample,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=inventory_template.csv"}
    )


@app.route('/api/template/locations', methods=['GET'])
def template_locations():
    headers = "location_id,zone,aisle,rack,level,length_cm,width_cm,height_cm,max_volume_cm3,max_weight_kg,accessibility_score,distance_meters,allowed_categories,status\n"
    sample = "Z99,Z,1,1,1,100.0,80.0,60.0,480000.0,300.0,85.0,12.5,All,Available\n"
    return Response(
        headers + sample,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=locations_template.csv"}
    )


@app.route('/api/upload/inventory', methods=['POST'])
def upload_inventory():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file part provided in request'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        content = file.stream.read().decode('utf-8-sig')
        rows = DataProcessor.read_csv_data(content)
        if not rows:
            return jsonify({'success': False, 'error': 'Uploaded CSV is empty'}), 400

        valid_count = 0
        errors = []
        for idx, row in enumerate(rows, start=1):
            valid, err, cleaned = DataProcessor.validate_inventory_record(row)
            if valid and cleaned:
                database.save_product(cleaned)
                valid_count += 1
            else:
                errors.append(f"Row {idx}: {err}")

        # Update baseline backup
        database.backup_baseline_locations()

        return jsonify({
            'success': True,
            'imported_count': valid_count,
            'errors_count': len(errors),
            'errors': errors[:10]  # Cap top 10 error messages
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f"Failed to process CSV: {str(e)}"}), 500


@app.route('/api/upload/locations', methods=['POST'])
def upload_locations():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file part provided'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        content = file.stream.read().decode('utf-8-sig')
        rows = DataProcessor.read_csv_data(content)
        if not rows:
            return jsonify({'success': False, 'error': 'Uploaded CSV is empty'}), 400

        valid_count = 0
        errors = []
        for idx, row in enumerate(rows, start=1):
            valid, err, cleaned = DataProcessor.validate_location_record(row)
            if valid and cleaned:
                database.save_location(cleaned)
                valid_count += 1
            else:
                errors.append(f"Row {idx}: {err}")

        return jsonify({
            'success': True,
            'imported_count': valid_count,
            'errors_count': len(errors),
            'errors': errors[:10]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f"Failed to process CSV: {str(e)}"}), 500


@app.route('/api/export/inventory', methods=['GET'])
def export_inventory():
    products = database.get_all_products()
    csv_str = DataProcessor.export_to_csv_string(products)
    return Response(
        csv_str,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=inventory_export.csv"}
    )


@app.route('/api/export/locations', methods=['GET'])
def export_locations():
    locations = database.get_all_locations()
    # Strip nested assigned_products for clean CSV export
    cleaned_locs = []
    for l in locations:
        copy_l = dict(l)
        copy_l.pop('assigned_products', None)
        cleaned_locs.append(copy_l)
    csv_str = DataProcessor.export_to_csv_string(cleaned_locs)
    return Response(
        csv_str,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=locations_export.csv"}
    )


@app.route('/api/export/recommendations', methods=['GET'])
def export_recommendations():
    recs = database.get_latest_recommendations()
    csv_str = DataProcessor.export_to_csv_string(recs)
    return Response(
        csv_str,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=optimization_recommendations.csv"}
    )


@app.route('/api/export/performance', methods=['GET'])
def export_performance():
    products = database.get_all_products()
    locations = database.get_all_locations()
    recs = database.get_latest_recommendations()
    perf = WarehouseOptimizer.evaluate_performance(products, locations, recs)
    
    records = [
        {"Metric": "Space Utilization (%)", "Baseline": perf['baseline']['space_utilization_pct'], "Optimized": perf['optimized']['space_utilization_pct'], "Delta": round(perf['optimized']['space_utilization_pct'] - perf['baseline']['space_utilization_pct'], 2)},
        {"Metric": "Daily Picking Travel (meters)", "Baseline": perf['baseline']['daily_picking_distance_m'], "Optimized": perf['optimized']['daily_picking_distance_m'], "Delta": f"-{perf['comparison']['distance_saved_m_daily']} m ({perf['comparison']['distance_reduction_pct']}%)"},
        {"Metric": "Daily Labor Time (hours)", "Baseline": perf['baseline']['daily_picking_time_hrs'], "Optimized": perf['optimized']['daily_picking_time_hrs'], "Delta": f"-{perf['comparison']['time_saved_hrs_daily']} hrs"},
        {"Metric": "Daily Labor Cost ($)", "Baseline": perf['baseline']['daily_labor_cost'], "Optimized": perf['optimized']['daily_labor_cost'], "Delta": f"-${perf['comparison']['daily_cost_savings']}"},
        {"Metric": "Annual Labor Cost ($)", "Baseline": perf['baseline']['annual_labor_cost'], "Optimized": perf['optimized']['annual_labor_cost'], "Delta": f"-${perf['comparison']['annual_cost_savings']}"},
        {"Metric": "Products Relocated", "Baseline": 0, "Optimized": perf['optimized']['products_relocated'], "Delta": perf['optimized']['products_relocated']},
        {"Metric": "Constraint Satisfaction (%)", "Baseline": f"{round(100 - (perf['baseline']['constraint_violations']/max(len(products),1)*100),1)}%", "Optimized": f"{perf['optimized']['constraint_satisfaction_pct']}%", "Delta": "Improved"}
    ]
    csv_str = DataProcessor.export_to_csv_string(records)
    return Response(
        csv_str,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=performance_evaluation.csv"}
    )


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"SmartStock AI server running at http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)
