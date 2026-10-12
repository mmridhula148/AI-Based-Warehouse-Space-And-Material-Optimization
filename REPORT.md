# Technical Report: AI-Based Warehouse Space and Material Optimization

**Project:** SmartStock AI  
**Challenge:** Hack Arena Student Hackathon — “AI-Based Warehouse Space and Material Optimization”  
**System URL:** [http://127.0.0.1:5000](http://127.0.0.1:5000)  
**Date:** October 2026  

---

## 1. Problem Understanding

In modern supply chains and order-fulfillment centers, material handling and order picking account for upwards of 55% to 65% of total warehouse operating expenses. Suboptimal product slotting causes:
1. **Excessive Travel Distances:** High-frequency, fast-moving items placed in deep warehouse aisles force operators and automated carts to traverse unnecessary kilometers daily.
2. **Space Underutilization:** Inefficient assignment of physical dimensions leads to massive volumetric voids or bin overflows.
3. **Ergonomic Inefficiencies & Bottlenecks:** Heavy items stored on elevated racks create safety hazards, while slow movers occupying prime "Golden Zone" (waist-to-chest level) racks block high-demand SKUs.
4. **Compatibility & Compliance Failures:** Hazardous materials (Hazmat) or temperature-sensitive goods placed in non-certified standard racks risk contamination or regulatory violation.

The goal of this project is to build an explainable, deterministic AI-driven warehouse optimization system that calculates the optimal storage allocation for products based on physical dimensions, demand velocity, picking frequency, location accessibility, distance from dispatch, and hard storage constraints.

---

## 2. Proposed Solution: SmartStock AI

**SmartStock AI** is a full-stack warehouse management and slotting optimization platform that combines:
- **Heuristic Multi-Factor Weighted Scoring:** Evaluates candidate bins using normalized metrics across Accessibility, Demand & Distance Alignment, Volumetric Fit, and Capacity Headroom.
- **Strict Physical & Compatibility Constraint Filtering:** Infeasible locations (dimensional mismatch, capacity violation, weight overages, category incompatibilities) are filtered out prior to scoring.
- **Relocation Stability Protection:** Hysteresis threshold prevents unnecessary labor churn when an existing slot is already satisfactory.
- **Full Operational Explainability:** Every recommendation is accompanied by quantitative evidence, before-and-after distance deltas, and operational rationale.
- **Interactive Industrial SaaS Interface:** Real-time 2D visual layout of warehouse racks, interactive bin inspector drawer, dynamic Chart.js analytics, and complete CSV import/export capabilities.

---

## 3. System Architecture & Technology Stack

### Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                                 Client Browser                                    |
|   HTML5 + Vanilla CSS3 (Industrial SaaS Theme) + Vanilla JS Controller (app.js)   |
|                 Chart.js Visualizations (Util, Frequency, Distances, Zones)        |
+-----------------------------------------+-----------------------------------------+
                                          | HTTP REST (JSON / Multipart CSV)
+-----------------------------------------v-----------------------------------------+
|                               Flask Application (app.py)                          |
|  - Dashboard APIs        - Inventory CRUD          - Locations CRUD               |
|  - Optimization APIs     - CSV Import / Export     - Performance Analysis         |
+--------------------+------------------------------------+-------------------------+
                     |                                    |
+--------------------v-------------------+    +-----------v-------------------------+
|    AI Optimizer Engine (optimizer.py)  |    | Data Processor (data_processor.py)  |
|  - Hard Constraint Feasibility Engine  |    |  - CSV Ingestion & Validation       |
|  - Weighted Multi-Factor Scoring       |    |  - Type checking & Schema bounds    |
|  - Ergonomic & Volumetric Fit Matrix   |    |  - Pandas integration + Pure Python |
+--------------------+-------------------+    +-----------+-------------------------+
                     |                                    |
+--------------------v------------------------------------v-------------------------+
|                             SQLite Database (smartstock.db)                       |
|   Tables: products, locations, recommendations, baseline_backup, settings         |
+-----------------------------------------------------------------------------------+
```

### Technology Stack
- **Frontend:** HTML5, CSS3 (Vanilla design tokens, responsive CSS grid/flexbox), JavaScript (ES6+ modular controller).
- **Backend:** Python Flask 3.1.3 (lightweight, zero GPU required, runs on standard laptop).
- **Charts:** Chart.js (offline bundled).
- **Database:** SQLite 3 with relational foreign keys and dynamic occupancy aggregation.
- **Data Processing:** Pure Python data processor with seamless Pandas fallback.

---

## 4. Dataset Description

The system includes a realistic illustrative benchmark dataset representing a standard distribution center:
- **14 Storage Locations across 6 Zones (A–F):**
  - **Zone A (Fast Movers / Golden Zone):** 6.5m–10m from dispatch, 88–95 accessibility, Levels 1–2.
  - **Zone B (Medium Velocity):** 32m–38m from dispatch, 58–65 accessibility.
  - **Zone C (Bulk Storage):** 45m–52m from dispatch, 40–50 accessibility.
  - **Zone D (Hazmat Vault):** 22m–25m from dispatch, specialized chemical containment.
  - **Zone E (Cold Chain Vault):** 18m–20.5m from dispatch, refrigerated diagnostics/perishables.
  - **Zone F (Heavy-Duty Overhead):** 65m from dispatch, 864,000 cm³ capacity, 600 kg limit.
- **18 Products across Varied Categories:**
  - High, Medium, and Low picking frequencies.
  - Demands ranging from 2 units/day to 95 units/day.
  - Unit sizes ranging from 1,200 cm³ to 4,500,000 cm³.
  - Special requirements: Standard, Hazmat, Temperature-Controlled, Heavy-Duty.

### Benchmark Product P101
As specifically mandated:
- **Product ID:** `P101` (Industrial Bearing 40mm)
- **Dimensions:** 40 × 30 × 20 cm (Unit Volume: 24,000 cm³)
- **Daily Demand:** 80 units/day
- **Picking Frequency:** High
- **Baseline Location:** `B01` (Distance: 32.0m, Accessibility: 65/100)
- **Candidate Evaluation:** Bins `A01`, `A02`, and `B01`.

---

## 5. Optimization Algorithm & Scoring Formulation

### Hard Constraints (Feasibility Gate)
A candidate bin $L$ is feasible for product $P$ if and only if:
1. **Status:** $L.\text{status} \ne \text{"Maintenance"}$.
2. **Physical Dimensions:** Sorted dimensions $[P_l, P_w, P_h] \le [L_l, L_w, L_h]$ allowing 3D rotation.
3. **Volume Capacity:** $L.\text{used\_volume} + P.\text{volume} \le L.\text{max\_volume}$.
4. **Weight Capacity:** $L.\text{used\_weight} + P.\text{weight} \le L.\text{max\_weight}$.
5. **Hazmat Compliance:** If $P$ requires Hazmat, $L$ must belong to certified Hazmat Zone D.
6. **Temperature Compliance:** If $P$ requires cold storage, $L$ must belong to Zone E.
7. **Ergonomic Safety:** Products $> 25\text{ kg}$ are restricted to ground rack Level 1.

### Multi-Factor Weighted Scoring Formula
For all feasible candidate locations, normalized component scores $S \in [0, 100]$ are calculated:

$$\text{Score}(P, L) = \frac{w_{\text{access}} S_{\text{access}} + w_{\text{demand}} S_{\text{demand}} + w_{\text{suit}} S_{\text{suit}} + w_{\text{cap}} S_{\text{cap}}}{100}$$

Where default configurable weights are:
- $w_{\text{access}} = 40\%$ (Accessibility Priority)
- $w_{\text{demand}} = 30\%$ (Demand Velocity & Picking Distance)
- $w_{\text{suit}} = 20\%$ (Storage Suitability & Ergonomic Fit)
- $w_{\text{cap}} = 10\%$ (Capacity Fit Headroom)

#### 1. Accessibility Score ($S_{\text{access}}$)
Evaluates bin accessibility adjusted by SKU picking frequency:
$$S_{\text{access}} = \min\left(100, L.\text{accessibility} \times \phi_{\text{freq}} + \text{bonus}\right)$$
Where $\phi_{\text{freq}} = 1.0$ (High), $0.85$ (Medium), $0.70$ (Low).

#### 2. Demand & Distance Priority Score ($S_{\text{demand}}$)
Normalizes proximity from dispatch against daily throughput:
$$D_{\text{norm}} = 100 \times \left(1.0 - \frac{L.\text{distance\_meters}}{\max(\text{distances})}\right)$$
$$S_{\text{demand}} = 0.70 \times D_{\text{norm}} + 0.30 \times (L.\text{accessibility} \times \phi_{\text{demand}})$$

#### 3. Storage Suitability Score ($S_{\text{suit}}$)
Evaluates volumetric sizing efficiency and vertical rack level ergonomics:
$$R_{\text{vol}} = \frac{P.\text{volume}}{L.\text{max\_volume}}$$
Ideal ratio for multi-item bins is $3\% - 45\%$. Heavy items on ground level receive 100 ergonomic points.

#### 4. Capacity Fit Score ($S_{\text{cap}}$)
Rewards target utilization of $50\% - 85\%$ to maintain breathing room and prevent congestion.

#### Stability Protection (Hysteresis)
If product's current location is feasible, a bonus $B_{\text{stability}} = 8.0$ points is added to avoid frivolous re-slotting.

---

## 6. Experimental Results & Measured Performance

All metrics below were computed directly from the actual database execution on the illustrative dataset:

### Before-and-After Metrics Comparison

| Warehouse Metric | Baseline (Current) | AI-Optimized Result | Measured Improvement | % Change |
| :--- | :---: | :---: | :---: | :---: |
| **Daily Picker Travel Distance** | **55,493.0 m** | **15,091.0 m** | **-40,402.0 m** | **-72.8%** |
| **Daily Picker Travel Time** | **17.99 hrs** | **8.64 hrs** | **-9.35 hrs/day** | **-52.0%** |
| **Daily Material Handling Cost** | **$404.96** | **$194.54** | **-$210.43/day** | **-52.0%** |
| **Annual Handling Labor Cost (300 Days)** | **$121,489.06** | **$58,360.94** | **-$63,128.13/year** | **-52.0%** |
| **Warehouse Space Utilization** | **7.0%** | **7.0%** | Balanced Fit | Stable |
| **Constraint Satisfaction Rate** | 61.1% | **100.0%** | Clean compliance | +38.9% |
| **Recommended Relocations** | 0 (Static) | 16 SKUs | 1 Retained, 1 Unfeasible | Optimal |

### Key Benchmark SKU: Product P101
- **Current Assignment:** Location `B01` (32.0m away, 65 accessibility).
- **AI Recommendation:** Relocate to Location `A01` (6.5m away, 95 accessibility, Level 1).
- **Score:** 94.85 / 100.
- **Single-Product Travel Savings:** Reduced from $80 \times 32\text{m} \times 2 = 5,120\text{ m/day}$ to $80 \times 6.5\text{m} \times 2 = 1,040\text{ m/day}$.
- **Net Daily Benefit:** **4,080 meters saved per day** (79.7% reduction).

### Infeasible Item Handling
- **Product P118 (Oversized Gantry Crane Beam):** Dimensions $250 \times 150 \times 120\text{ cm}$, weight 1,200 kg.
- **Engine Output:** Safely classified as **"No Suitable Location"**.
- **Reason Displayed:** *"Dimensions exceed warehouse bin limits (length 250cm > max 120cm)"*.
- **System Stability:** Handled gracefully with zero crashes.

---

## 7. Assumptions & Limitations

1. **Travel Distance Metric:** Model calculates round-trip picker distance ($2 \times \text{distance}$) from the main sorting/dispatch terminal to the storage bin.
2. **Speed & Labor Assumptions:**
   - Operator travel speed: $1.2\text{ m/s}$ ($4.32\text{ km/h}$).
   - Handling/scanning duration: $25\text{ seconds/pick}$.
   - Operator wage rate: $\$22.50/\text{hour}$.
   - Operating calendar: $300\text{ working days/year}$.
3. **Illustrative Data:** The dataset is illustrative and demonstrates measurable operational trends.

---

## 8. Installation & Execution Guide

### Requirements
- Python 3.10+ (Standard laptop, no GPU or paid APIs needed).
- Dependencies: `Flask>=3.0.0`.

### Execution Commands
```powershell
# Navigate to project directory
cd c:\Users\user\Desktop\warehouse

# Install dependencies
pip install -r requirements.txt

# Run automated test suites
python -m unittest tests/test_optimizer.py
python -m unittest tests/test_api.py

# Launch web server
python app.py
```
Open your browser at: **`http://127.0.0.1:5000`**
