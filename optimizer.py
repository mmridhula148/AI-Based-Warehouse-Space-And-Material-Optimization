"""
SmartStock AI - Warehouse Space and Material Optimization Engine
Implements deterministic, explainable multi-factor weighted scoring and heuristic slotting.
"""

from typing import List, Dict, Any, Tuple, Optional
import copy


class WarehouseOptimizer:
    DEFAULT_WEIGHTS = {
        'accessibility': 40.0,
        'demand_priority': 30.0,
        'storage_suitability': 20.0,
        'capacity_fit': 10.0
    }

    # Physical and operational assumptions
    WALKING_SPEED_MPS = 1.2      # 1.2 meters per second walking speed
    PICK_TIME_SEC = 25.0         # 25 seconds handling/scanning per pick
    LABOR_RATE_PER_HR = 22.50    # $22.50 per hour warehouse operator wage
    ANNUAL_WORK_DAYS = 300       # 300 working days per year
    STABILITY_THRESHOLD = 8.0    # Retain current slot if delta score < 8 to avoid churn

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = self._normalize_weights(weights or self.DEFAULT_WEIGHTS)

    def _normalize_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        access = float(weights.get('accessibility', 40.0))
        demand = float(weights.get('demand_priority', 30.0))
        suit = float(weights.get('storage_suitability', 20.0))
        cap = float(weights.get('capacity_fit', 10.0))
        total = access + demand + suit + cap
        if total <= 0:
            total = 100.0
            access, demand, suit, cap = 40.0, 30.0, 20.0, 10.0
        return {
            'accessibility': round((access / total) * 100.0, 2),
            'demand_priority': round((demand / total) * 100.0, 2),
            'storage_suitability': round((suit / total) * 100.0, 2),
            'capacity_fit': round((cap / total) * 100.0, 2)
        }

    @staticmethod
    def fits_dimensions(p_len: float, p_wid: float, p_hgt: float, 
                        loc_len: float, loc_wid: float, loc_hgt: float) -> bool:
        """Checks if product fits inside bin allowing 3D rotation."""
        p_dims = sorted([p_len, p_wid, p_hgt])
        loc_dims = sorted([loc_len, loc_wid, loc_hgt])
        return p_dims[0] <= loc_dims[0] and p_dims[1] <= loc_dims[1] and p_dims[2] <= loc_dims[2]

    @staticmethod
    def is_compatible(prod: Dict[str, Any], loc: Dict[str, Any]) -> Tuple[bool, str]:
        """Check compatibility restrictions between product requirements and location."""
        compat_req = prod.get('compatibility_req', 'Standard')
        category = prod.get('category', 'General')
        allowed = loc.get('allowed_categories', 'All')

        if loc.get('status') == 'Maintenance' or loc.get('status') == 'Unavailable':
            return False, f"Location {loc['location_id']} is under maintenance"

        # Hazardous materials check: must go to designated Hazmat/Chemicals location
        if compat_req in ['Hazmat', 'Chemicals', 'Flammable'] or category.lower() in ['chemicals', 'hazmat']:
            if 'Hazmat' not in allowed and 'Chemicals' not in allowed and loc.get('zone') != 'D':
                return False, f"Product requires Hazmat-certified storage; {loc['location_id']} is a general non-hazmat bin"

        # Temperature-controlled check: must go to designated cold-chain location
        if compat_req in ['Temperature-Controlled', 'Perishables', 'Cold Storage'] or category.lower() in ['perishables', 'cold storage']:
            if 'Temperature-Controlled' not in allowed and 'Perishables' not in allowed and loc.get('zone') != 'E':
                return False, f"Product requires cold/temperature-controlled storage; {loc['location_id']} is ambient"

        # Heavy-Duty check: heavy items should be on ground rack (level 1)
        if compat_req == 'Heavy-Duty' or prod.get('weight_kg', 0) > 30:
            if loc.get('level', 1) > 1 and 'Heavy-Duty' not in allowed:
                return False, f"Heavy item ({prod.get('weight_kg')} kg) prohibited on upper rack level {loc.get('level')}"

        # Category constraint if location is restricted and not 'All'
        if allowed != 'All':
            allowed_list = [c.strip().lower() for c in allowed.split(',')]
            if category.lower() not in allowed_list and compat_req.lower() not in allowed_list:
                return False, f"Category '{category}' not permitted in location {loc['location_id']} (allowed: {allowed})"

        return True, "Compatible"

    def calculate_candidate_score(self, prod: Dict[str, Any], loc: Dict[str, Any], 
                                  max_dist: float, current_occupied_vol: float) -> Tuple[float, Dict[str, float]]:
        """
        Calculates normalized weighted score [0 - 100] for placing product into location.
        Returns: (final_score, breakdown_dict)
        """
        # 1. Accessibility Score (0 - 100)
        base_access = float(loc.get('accessibility_score', 50.0))
        freq = prod.get('picking_frequency', 'Medium')
        freq_factor = 1.0 if freq == 'High' else (0.85 if freq == 'Medium' else 0.70)
        s_access = min(100.0, max(0.0, base_access * freq_factor + (15.0 if freq == 'High' and base_access >= 85 else 0.0)))

        # 2. Demand & Distance Priority Score (0 - 100)
        # Closer distance = higher score, especially for high demand
        dist = float(loc.get('distance_meters', 20.0))
        norm_dist_factor = max(0.0, min(100.0, 100.0 * (1.0 - (dist / max(max_dist, 50.0)))))
        demand = prod.get('daily_demand', 20)
        demand_weight = 1.0 if demand >= 60 else (0.75 if demand >= 25 else 0.50)
        s_demand_dist = min(100.0, norm_dist_factor * 0.7 + (base_access * 0.3 * demand_weight))

        # 3. Storage Suitability (0 - 100)
        # Volumetric ratio and ergonomic level match
        p_vol = float(prod.get('unit_volume_cm3', 1000.0))
        loc_max_vol = float(loc.get('max_volume_cm3', 100000.0))
        vol_ratio = p_vol / max(loc_max_vol, 1.0)
        # Ideal single product slice in bin: 5% - 40%
        if 0.03 <= vol_ratio <= 0.45:
            vol_score = 95.0
        elif vol_ratio < 0.03:
            vol_score = 70.0  # slight waste of large bin
        else:
            vol_score = 60.0  # tight fit

        # Ergonomic level fit:
        level = loc.get('level', 1)
        weight = prod.get('weight_kg', 1.0)
        if weight > 25.0:
            ergo_score = 100.0 if level == 1 else (50.0 if level == 2 else 20.0)
        elif freq == 'High':
            # Golden zone: waist/chest level (levels 1 or 2)
            ergo_score = 100.0 if level in [1, 2] else 60.0
        else:
            ergo_score = 85.0
        s_suitability = 0.6 * vol_score + 0.4 * ergo_score

        # 4. Capacity Fit (0 - 100)
        # Target utilization 65% - 85%
        projected_vol = current_occupied_vol + p_vol
        projected_util_pct = (projected_vol / max(loc_max_vol, 1.0)) * 100.0
        if 50.0 <= projected_util_pct <= 85.0:
            s_capacity = 95.0
        elif projected_util_pct < 50.0:
            s_capacity = 80.0
        elif projected_util_pct <= 98.0:
            s_capacity = 65.0
        else:
            s_capacity = 40.0

        w = self.weights
        total_score = (
            w['accessibility'] * s_access +
            w['demand_priority'] * s_demand_dist +
            w['storage_suitability'] * s_suitability +
            w['capacity_fit'] * s_capacity
        ) / 100.0

        breakdown = {
            'accessibility_component': round(s_access, 1),
            'demand_dist_component': round(s_demand_dist, 1),
            'suitability_component': round(s_suitability, 1),
            'capacity_component': round(s_capacity, 1)
        }
        return round(total_score, 2), breakdown

    def run_optimization(self, products: List[Dict[str, Any]], locations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Executes multi-factor heuristic slotting algorithm.
        Returns:
            {
                'recommendations': [...],
                'summary': {...},
                'weights': self.weights
            }
        """
        loc_map = {loc['location_id']: copy.deepcopy(loc) for loc in locations}
        # Track dynamic allocation volume and weight
        loc_occupancy = {loc['location_id']: 0.0 for loc in locations}
        loc_weight = {loc['location_id']: 0.0 for loc in locations}

        max_dist = max([float(loc.get('distance_meters', 20.0)) for loc in locations] or [50.0])

        # Priority calculation for ordering allocation:
        # High frequency and high demand allocate first to prime spots
        def get_priority_key(p: Dict[str, Any]) -> float:
            freq = p.get('picking_frequency', 'Medium')
            freq_val = 300.0 if freq == 'High' else (200.0 if freq == 'Medium' else 100.0)
            demand = float(p.get('daily_demand', 0))
            return freq_val + demand

        sorted_products = sorted(products, key=get_priority_key, reverse=True)

        recommendations = []
        relocations_count = 0
        retained_count = 0
        unfeasible_count = 0

        for prod in sorted_products:
            pid = prod['product_id']
            curr_loc_id = prod.get('current_location_id', 'Unassigned')
            curr_loc = loc_map.get(curr_loc_id)
            baseline_dist = float(curr_loc.get('distance_meters', 45.0)) if curr_loc else 45.0

            p_len = float(prod.get('length_cm', 0))
            p_wid = float(prod.get('width_cm', 0))
            p_hgt = float(prod.get('height_cm', 0))
            p_vol = float(prod.get('unit_volume_cm3', p_len * p_wid * p_hgt))
            p_wt = float(prod.get('weight_kg', 1.0))

            # Evaluate all candidate locations
            feasible_candidates = []
            failure_reasons = []

            for loc_id, loc in loc_map.items():
                # 1. Dimension feasibility
                if not self.fits_dimensions(p_len, p_wid, p_hgt, loc['length_cm'], loc['width_cm'], loc['height_cm']):
                    failure_reasons.append(f"{loc_id}: dimensions exceed bin")
                    continue

                # 2. Capacity volume feasibility
                rem_vol = loc['max_volume_cm3'] - loc_occupancy[loc_id]
                if rem_vol < p_vol:
                    failure_reasons.append(f"{loc_id}: remaining capacity ({round(rem_vol)} cm³) < needed ({round(p_vol)} cm³)")
                    continue

                # 3. Max weight feasibility
                rem_wt = loc.get('max_weight_kg', 300.0) - loc_weight[loc_id]
                if rem_wt < p_wt:
                    failure_reasons.append(f"{loc_id}: remaining weight capacity ({round(rem_wt,1)} kg) < item weight ({p_wt} kg)")
                    continue

                # 4. Compatibility feasibility
                is_comp, comp_msg = self.is_compatible(prod, loc)
                if not is_comp:
                    failure_reasons.append(f"{loc_id}: {comp_msg}")
                    continue

                # Feasible! Calculate score
                score, breakdown = self.calculate_candidate_score(prod, loc, max_dist, loc_occupancy[loc_id])
                feasible_candidates.append({
                    'location_id': loc_id,
                    'location': loc,
                    'score': score,
                    'breakdown': breakdown,
                    'distance': loc['distance_meters']
                })

            if not feasible_candidates:
                # No feasible location exists
                unfeasible_count += 1
                unique_reasons = list(dict.fromkeys(failure_reasons))[:2]
                reason_str = "; ".join(unique_reasons) if unique_reasons else "Exceeds warehouse dimension and capacity limits"
                recommendations.append({
                    'product_id': pid,
                    'current_location_id': curr_loc_id,
                    'recommended_location_id': 'No Suitable Location',
                    'score': 0.0,
                    'baseline_distance': baseline_dist,
                    'optimized_distance': baseline_dist,
                    'distance_delta': 0.0,
                    'reason': f"No feasible location: {reason_str}",
                    'benefit': "Requires dedicated staging area, oversized rack, or re-allocation",
                    'status': 'Unfeasible'
                })
                continue

            # Sort feasible candidates by score descending
            feasible_candidates.sort(key=lambda c: c['score'], reverse=True)
            best_candidate = feasible_candidates[0]

            # Check if current location is among feasible candidates
            curr_candidate = next((c for c in feasible_candidates if c['location_id'] == curr_loc_id), None)
            
            selected_loc_id = best_candidate['location_id']
            selected_score = best_candidate['score']
            selected_dist = best_candidate['distance']

            # Stability heuristic: If current location is valid and within stability threshold, keep it!
            if curr_candidate is not None:
                curr_score = curr_candidate['score']
                score_improvement = best_candidate['score'] - curr_score
                # If improvement is marginal, avoid unnecessary physical relocation
                if score_improvement < self.STABILITY_THRESHOLD and curr_loc_id != 'Unassigned':
                    selected_loc_id = curr_loc_id
                    selected_score = curr_score
                    selected_dist = curr_candidate['distance']

            # Update occupied volume and weight
            loc_occupancy[selected_loc_id] += p_vol
            loc_weight[selected_loc_id] += p_wt

            dist_delta = baseline_dist - selected_dist
            pct_dist_improved = (dist_delta / baseline_dist * 100.0) if baseline_dist > 0 else 0.0

            # Formulate transparent explainable reason and operational benefit
            rec_loc_obj = loc_map[selected_loc_id]
            is_relocated = (selected_loc_id != curr_loc_id)

            if is_relocated:
                relocations_count += 1
                rec_status = 'Recommended'
                if dist_delta > 0:
                    reason = (
                        f"Relocate from {curr_loc_id} ({baseline_dist}m) to {selected_loc_id} ({selected_dist}m, "
                        f"Zone {rec_loc_obj['zone']}, Level {rec_loc_obj['level']}). High demand ({prod['daily_demand']}/day) "
                        f"benefits from {round(pct_dist_improved, 1)}% travel distance reduction and high accessibility ({rec_loc_obj['accessibility_score']}/100)."
                    )
                    benefit = f"Saves ~{round(dist_delta * prod['daily_demand'] * 2, 0):,.0f} m/day picking travel distance."
                else:
                    reason = (
                        f"Move from {curr_loc_id} to {selected_loc_id} for superior capacity fit and category compliance "
                        f"(Score: {selected_score}/100)."
                    )
                    benefit = "Prevents aisle congestion and satisfies storage compatibility requirements."
            else:
                retained_count += 1
                rec_status = 'Optimal (Keep)'
                reason = (
                    f"Current location {curr_loc_id} is already well-matched (Score: {selected_score}/100, "
                    f"Accessibility: {rec_loc_obj['accessibility_score']}). No relocation needed."
                )
                benefit = "Zero relocation labor required; optimal slot stability maintained."

            recommendations.append({
                'product_id': pid,
                'current_location_id': curr_loc_id,
                'recommended_location_id': selected_loc_id,
                'score': selected_score,
                'baseline_distance': baseline_dist,
                'optimized_distance': selected_dist,
                'distance_delta': round(dist_delta, 2),
                'reason': reason,
                'benefit': benefit,
                'status': rec_status
            })

        summary = {
            'total_products': len(products),
            'recommended_relocations': relocations_count,
            'retained_in_place': retained_count,
            'unfeasible_products': unfeasible_count,
            'feasibility_rate_pct': round(((len(products) - unfeasible_count) / max(len(products), 1)) * 100.0, 1)
        }

        return {
            'recommendations': recommendations,
            'summary': summary,
            'weights': self.weights
        }

    @classmethod
    def evaluate_performance(cls, products: List[Dict[str, Any]], locations: List[Dict[str, Any]], 
                             recommendations: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Calculates baseline vs optimized performance metrics based on strict formulas.
        """
        loc_map = {loc['location_id']: loc for loc in locations}
        rec_map = {r['product_id']: r for r in (recommendations or [])}

        total_usable_volume = sum([float(loc.get('max_volume_cm3', 0)) for loc in locations])
        
        # 1. Baseline metrics calculation
        baseline_assigned_volume = 0.0
        baseline_daily_distance = 0.0
        baseline_picks_count = 0
        baseline_violations = 0

        for p in products:
            vol = float(p.get('unit_volume_cm3', 0))
            demand = int(p.get('daily_demand', 0))
            curr_loc_id = p.get('current_location_id', 'Unassigned')
            baseline_picks_count += demand

            if curr_loc_id in loc_map:
                baseline_assigned_volume += vol
                loc = loc_map[curr_loc_id]
                dist = float(loc.get('distance_meters', 35.0))
                # Round-trip picking travel per demand unit
                baseline_daily_distance += (demand * dist * 2.0)
                # Check baseline compatibility
                is_comp, _ = cls.is_compatible(p, loc)
                if not is_comp:
                    baseline_violations += 1
            else:
                # Unassigned penalty distance assumption: 50m
                baseline_daily_distance += (demand * 50.0 * 2.0)
                baseline_violations += 1

        baseline_utilization_pct = (baseline_assigned_volume / max(total_usable_volume, 1.0)) * 100.0
        baseline_travel_time_sec = baseline_daily_distance / cls.WALKING_SPEED_MPS
        baseline_handling_time_sec = baseline_picks_count * cls.PICK_TIME_SEC
        baseline_total_time_hrs = (baseline_travel_time_sec + baseline_handling_time_sec) / 3600.0
        baseline_daily_cost = baseline_total_time_hrs * cls.LABOR_RATE_PER_HR
        baseline_annual_cost = baseline_daily_cost * cls.ANNUAL_WORK_DAYS

        # 2. Optimized metrics calculation
        optimized_assigned_volume = 0.0
        optimized_daily_distance = 0.0
        optimized_violations = 0
        relocations_count = 0

        for p in products:
            pid = p['product_id']
            vol = float(p.get('unit_volume_cm3', 0))
            demand = int(p.get('daily_demand', 0))
            curr_loc_id = p.get('current_location_id', 'Unassigned')

            rec = rec_map.get(pid)
            if rec and rec.get('recommended_location_id') not in ['No Suitable Location', 'Unassigned']:
                target_loc_id = rec['recommended_location_id']
            else:
                target_loc_id = curr_loc_id

            if target_loc_id != curr_loc_id:
                relocations_count += 1

            if target_loc_id in loc_map:
                optimized_assigned_volume += vol
                loc = loc_map[target_loc_id]
                dist = float(loc.get('distance_meters', 35.0))
                optimized_daily_distance += (demand * dist * 2.0)
            else:
                optimized_daily_distance += (demand * 50.0 * 2.0)
                optimized_violations += 1

        optimized_utilization_pct = (optimized_assigned_volume / max(total_usable_volume, 1.0)) * 100.0
        optimized_travel_time_sec = optimized_daily_distance / cls.WALKING_SPEED_MPS
        optimized_handling_time_sec = baseline_picks_count * cls.PICK_TIME_SEC
        optimized_total_time_hrs = (optimized_travel_time_sec + optimized_handling_time_sec) / 3600.0
        optimized_daily_cost = optimized_total_time_hrs * cls.LABOR_RATE_PER_HR
        optimized_annual_cost = optimized_daily_cost * cls.ANNUAL_WORK_DAYS

        # Deltas and improvement percentages
        dist_savings_meters = max(0.0, baseline_daily_distance - optimized_daily_distance)
        dist_reduction_pct = (dist_savings_meters / max(baseline_daily_distance, 1.0)) * 100.0
        
        daily_cost_savings = max(0.0, baseline_daily_cost - optimized_daily_cost)
        annual_cost_savings = daily_cost_savings * cls.ANNUAL_WORK_DAYS

        time_saved_hrs_daily = max(0.0, baseline_total_time_hrs - optimized_total_time_hrs)

        total_prods = len(products)
        constraint_satisfaction_pct = round(((total_prods - optimized_violations) / max(total_prods, 1)) * 100.0, 1)

        return {
            'assumptions': {
                'walking_speed_mps': cls.WALKING_SPEED_MPS,
                'pick_time_sec': cls.PICK_TIME_SEC,
                'labor_rate_per_hr': cls.LABOR_RATE_PER_HR,
                'annual_work_days': cls.ANNUAL_WORK_DAYS,
                'formula_space_utilization': "Occupied storage volume / Total usable storage volume * 100",
                'formula_distance_reduction': "(Baseline distance - Optimized distance) / Baseline distance * 100",
                'formula_cost_savings': "Baseline estimated handling cost - Optimized estimated handling cost"
            },
            'baseline': {
                'space_utilization_pct': round(baseline_utilization_pct, 2),
                'occupied_volume_cm3': round(baseline_assigned_volume, 2),
                'total_usable_volume_cm3': round(total_usable_volume, 2),
                'daily_picking_distance_m': round(baseline_daily_distance, 1),
                'daily_picking_time_hrs': round(baseline_total_time_hrs, 2),
                'daily_labor_cost': round(baseline_daily_cost, 2),
                'annual_labor_cost': round(baseline_annual_cost, 2),
                'constraint_violations': baseline_violations
            },
            'optimized': {
                'space_utilization_pct': round(optimized_utilization_pct, 2),
                'occupied_volume_cm3': round(optimized_assigned_volume, 2),
                'total_usable_volume_cm3': round(total_usable_volume, 2),
                'daily_picking_distance_m': round(optimized_daily_distance, 1),
                'daily_picking_time_hrs': round(optimized_total_time_hrs, 2),
                'daily_labor_cost': round(optimized_daily_cost, 2),
                'annual_labor_cost': round(optimized_annual_cost, 2),
                'constraint_satisfaction_pct': constraint_satisfaction_pct,
                'products_relocated': relocations_count
            },
            'comparison': {
                'distance_saved_m_daily': round(dist_savings_meters, 1),
                'distance_reduction_pct': round(dist_reduction_pct, 1),
                'time_saved_hrs_daily': round(time_saved_hrs_daily, 2),
                'daily_cost_savings': round(daily_cost_savings, 2),
                'annual_cost_savings': round(annual_cost_savings, 2),
                'products_relocated_count': relocations_count,
                'unnecessary_movements_eliminated': max(0, baseline_violations - optimized_violations + relocations_count)
            }
        }
