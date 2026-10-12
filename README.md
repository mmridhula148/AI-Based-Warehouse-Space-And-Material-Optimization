# SmartStock AI - Warehouse Space & Material Optimization Platform

An intelligent, full-stack warehouse management and slotting optimization web application built for the **Hack Arena Student Hackathon Challenge**.

SmartStock AI analyzes product dimensions, demand velocity, picking frequency, location accessibility, and distance to dispatch to recommend optimal storage locations. It demonstrates **measurable, mathematically validated improvements** in picking distance, labor costs, and space utilization.

---

## 🌟 Key Features

1. **Interactive SaaS Dashboard:**
   - 6 Live KPI cards (Total Products, Locations, Utilization %, Relocations Needed, Avg Picking Distance, Annual Handling Cost).
   - 5 Dynamic Chart.js charts (Space Utilization, Movement Frequency, Category Breakdown, Daily Distance Comparison, Zone Capacity).
2. **Catalog & Inventory Management:**
   - Full CRUD operations with instant dimension validation, volume calculation, and category filtering.
   - Bulk CSV Import & Export with downloadable templates.
3. **Interactive 2D Warehouse Layout:**
   - Visual grid of storage bins across 6 zones with color-coded occupancy bars (Empty, Occupied, Full, Maintenance).
   - Clickable inspector drawer displaying bin physical specifications and assigned SKUs.
4. **AI-Based Optimization Engine:**
   - Transparent, deterministic multi-factor weighted scoring algorithm.
   - Configurable weights via real-time sliders (Accessibility, Demand Priority, Storage Suitability, Capacity Fit).
   - Hard constraint filtering (dimensions, volumetric limits, Hazmat compliance, cold chain containment, ergonomic level rules).
   - Specific benchmark evaluation for product **P101** allocating to **A01**.
5. **Before-and-After Performance Evaluation:**
   - Side-by-side KPI comparison cards.
   - Documented formulas and empirical data demonstrating a **72.8% reduction in picker travel distance** and **$63,128/year labor savings**.
6. **Zero External Dependencies / Offline Ready:**
   - Runs on any standard laptop without GPU, internet connection, or paid external APIs.

---

## 🚀 Quick Start Guide

### 1. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 2. Run Test Suite
```powershell
python -m unittest tests/test_optimizer.py
python -m unittest tests/test_api.py
```

### 3. Start the Web Application
```powershell
python app.py
```

### 4. Open in Web Browser
Navigate to:
👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 📁 Project Structure

```
warehouse/
├── app.py                      # Flask REST API and web application server
├── optimizer.py                # AI slotting engine and performance evaluator
├── database.py                 # SQLite relational storage and dynamic aggregation
├── data_processor.py           # CSV parsing, validation, and Pandas integration
├── requirements.txt            # Python dependencies
├── README.md                   # Project overview and run guide
├── REPORT.md                   # Comprehensive technical report with real benchmarks
├── templates/
│   └── index.html              # Modern, responsive single-page dashboard
├── static/
│   ├── css/
│   │   └── style.css           # Industrial SaaS dark navy theme
│   └── js/
│       ├── chart.min.js        # Offline Chart.js library
│       └── app.js              # Client-side state manager and controller
├── data/
│   ├── sample_inventory.csv    # 18 realistic SKUs including P101
│   ├── sample_locations.csv    # 14 locations across 6 zones
│   └── smartstock.db           # SQLite database
└── tests/
    ├── test_optimizer.py       # Optimization algorithm unit tests
    └── test_api.py             # Flask API integration tests
```
