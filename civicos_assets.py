"""CivicOS Government Assets Management Engine

Provides data models, category metadata, condition rating metrics,
preventive maintenance calculators, QR badge generators, and seed datasets
across all 17 municipal asset categories.
"""

from datetime import datetime, timedelta
import json
import math
from typing import Any, Dict, List, Optional, Tuple

ASSET_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "roads": {
        "id": "roads",
        "name": "Roads & Road Segments",
        "name_mr": "रस्ते आणि रस्त्यांचे तुकडे",
        "icon": "🛣️",
        "department": "road",
        "unit": "km",
        "default_maintenance_days": 180,
        "spec_schema": [
            {"key": "surface_type", "label": "Surface Type", "type": "select", "options": ["Asphalt / Bitumen", "Concrete (CC)", "Paver Blocks", "WBM / Gravel", "Earthen"]},
            {"key": "length_km", "label": "Length (km)", "type": "number", "step": "0.1"},
            {"key": "width_m", "label": "Width (m)", "type": "number", "step": "0.5"},
            {"key": "lane_count", "label": "Lanes", "type": "select", "options": ["1 Lane", "2 Lanes", "4 Lanes", "6 Lanes"]},
            {"key": "traffic_density", "label": "Traffic Density", "type": "select", "options": ["Low", "Moderate", "Heavy", "Very Heavy"]},
            {"key": "contractor", "label": "Construction Agency / Contractor", "type": "text"},
            {"key": "warranty_years", "label": "Defect Liability Period (Years)", "type": "number"},
        ],
    },
    "streetlights": {
        "id": "streetlights",
        "name": "Streetlights & High-Masts",
        "name_mr": "रस्त्यावरील दिवे आणि हाय-मास्ट",
        "icon": "💡",
        "department": "electricity",
        "unit": "poles",
        "default_maintenance_days": 90,
        "spec_schema": [
            {"key": "luminaire_type", "label": "Luminaire Type", "type": "select", "options": ["LED Energy-Efficient", "High-Pressure Sodium (HPS)", "Solar-Powered LED", "Halogen High-Mast"]},
            {"key": "wattage", "label": "Wattage (W)", "type": "select", "options": ["45W", "70W", "90W", "120W", "250W", "400W High Mast"]},
            {"key": "pole_material", "label": "Pole Material", "type": "select", "options": ["Octagonal Galvanized Steel", "Tubular Steel", "Concrete (PCC)", "Cast Iron"]},
            {"key": "height_m", "label": "Pole Height (m)", "type": "number", "step": "0.5"},
            {"key": "feeder_pillar", "label": "Connected Feeder Pillar ID", "type": "text"},
            {"key": "auto_timer", "label": "Smart Light Sensor / Timer", "type": "select", "options": ["Smart Astronomical Timer", "LDR Daylight Sensor", "Manual Control Switch"]},
        ],
    },
    "water_pipelines": {
        "id": "water_pipelines",
        "name": "Water Supply Pipelines",
        "name_mr": "पाणी पुरवठा पाईपलाईन",
        "icon": "🚰",
        "department": "water",
        "unit": "meters",
        "default_maintenance_days": 120,
        "spec_schema": [
            {"key": "pipe_material", "label": "Pipe Material", "type": "select", "options": ["Ductile Iron (DI)", "Cast Iron (CI)", "HDPE High-Density", "PVC / uPVC", "Mild Steel (MS)"]},
            {"key": "diameter_mm", "label": "Diameter (mm)", "type": "select", "options": ["80mm", "100mm", "150mm", "200mm", "300mm", "450mm Main Trunk", "600mm Primary Feeder"]},
            {"key": "pressure_rating_bar", "label": "Rated Pressure (Bar)", "type": "number", "step": "0.5"},
            {"key": "length_m", "label": "Segment Length (m)", "type": "number"},
            {"key": "source_reservoir", "label": "Fed by Reservoir / Tank", "type": "text"},
            {"key": "burial_depth_m", "label": "Burial Depth (m)", "type": "number", "step": "0.1"},
        ],
    },
    "valves_pumps": {
        "id": "valves_pumps",
        "name": "Valves & Pumping Stations",
        "name_mr": "व्हॉल्व्ह आणि पंपिंग स्टेशन्स",
        "icon": "⚙️",
        "department": "water",
        "unit": "units",
        "default_maintenance_days": 60,
        "spec_schema": [
            {"key": "equipment_type", "label": "Equipment Type", "type": "select", "options": ["Booster Pump", "Centrifugal Submersible Pump", "Sluice Valve", "Air Release Valve", "Non-Return (Check) Valve", "Pressure Reducing Valve (PRV)"]},
            {"key": "power_hp", "label": "Motor Power (HP / kW)", "type": "text"},
            {"key": "discharge_lpm", "label": "Flow Rate (LPM / m3/hr)", "type": "number"},
            {"key": "valve_size_mm", "label": "Valve / Port Size (mm)", "type": "text"},
            {"key": "automation_mode", "label": "Control Mode", "type": "select", "options": ["SCADA / IoT Automated", "Semi-Automatic Panel", "Manual Wheel Operation"]},
        ],
    },
    "drainage": {
        "id": "drainage",
        "name": "Drainage Lines & Culverts",
        "name_mr": "सांडपाणी वाहिन्या आणि नाले",
        "icon": "🌊",
        "department": "road",
        "unit": "meters",
        "default_maintenance_days": 90,
        "spec_schema": [
            {"key": "drain_type", "label": "Drain Type", "type": "select", "options": ["Underground RCC Box Drain", "Covered Stormwater Drain", "Open Masonry Nallah", "Perforated Roadside Kerb Drain", "Cross Culvert"]},
            {"key": "width_m", "label": "Width (m)", "type": "number", "step": "0.1"},
            {"key": "depth_m", "label": "Depth (m)", "type": "number", "step": "0.1"},
            {"key": "desilting_status", "label": "Desiltation Status", "type": "select", "options": ["Clean / De-silted", "Partial Silt Accumulation", "Severely Choked / Blocked"]},
            {"key": "discharge_destination", "label": "Discharges Into", "type": "text"},
        ],
    },
    "public_toilets": {
        "id": "public_toilets",
        "name": "Public Toilets & Sanitation Blocks",
        "name_mr": "सार्वजनिक स्वच्छतागृहे",
        "icon": "🚻",
        "department": "health",
        "unit": "blocks",
        "default_maintenance_days": 30,
        "spec_schema": [
            {"key": "male_seats", "label": "Male Seats / Urinals", "type": "number"},
            {"key": "female_seats", "label": "Female Seats", "type": "number"},
            {"key": "pwd_friendly", "label": "Divyangjan (Accessible) Seat", "type": "select", "options": ["Yes - Fully Accessible", "No"]},
            {"key": "running_water", "label": "24x7 Running Water Connection", "type": "select", "options": ["Yes - Overhead Tank + Municipal Supply", "Yes - Borewell", "Intermittent / Tanker Supply", "No - Water Shortage"]},
            {"key": "electricity_status", "label": "Lighting / Power Supply", "type": "select", "options": ["Grid Connected + Solar Backup", "Grid Connected", "No Power"]},
            {"key": "cleanliness_audit_score", "label": "Latest Cleanliness Score (1-5)", "type": "select", "options": ["5 - Spotless", "4 - Clean & Hygenic", "3 - Acceptable", "2 - Sub-standard", "1 - Critical / Unhygienic"]},
            {"key": "cleaning_contractor", "label": "Caretaker / Sanitation Agency", "type": "text"},
        ],
    },
    "garbage_bins": {
        "id": "garbage_bins",
        "name": "Garbage Bins & Secondary Dumper Placers",
        "name_mr": "कचरा कुंड्या आणि डंपर",
        "icon": "🗑️",
        "department": "health",
        "unit": "bins",
        "default_maintenance_days": 15,
        "spec_schema": [
            {"key": "bin_type", "label": "Bin Category", "type": "select", "options": ["Twin Segregated Bin (Wet & Dry)", "Community Dumper Placer (4.5 m3)", "Galvanized Wheelie Bin (240L)", "Underground Smart Compactor Bin"]},
            {"key": "capacity_liters", "label": "Capacity (Liters / m3)", "type": "text"},
            {"key": "iot_fill_sensor", "label": "Ultrasonic Fill Level Sensor", "type": "select", "options": ["Yes - IoT Connected", "No Sensor"]},
            {"key": "collection_frequency", "label": "Scheduled Clearance Frequency", "type": "select", "options": ["Twice Daily", "Daily", "Alternate Days", "On-Demand"]},
            {"key": "current_fill_percentage", "label": "Current Estimated Fill %", "type": "number", "min": "0", "max": "100"},
        ],
    },
    "gov_buildings": {
        "id": "gov_buildings",
        "name": "Government & Panchayat Buildings",
        "name_mr": "शासकीय आणि पंचायत इमारती",
        "icon": "🏛️",
        "department": "road",
        "unit": "buildings",
        "default_maintenance_days": 180,
        "spec_schema": [
            {"key": "facility_type", "label": "Office Type", "type": "select", "options": ["Gram Panchayat Karyalaya", "Ward Administrative Office", "Citizen Facilitation Centre (CFC / Maha E-Seva)", "Municipal Corporation Sub-Office", "Community Hall (Samaj Mandir)", "Disaster Relief Shelter"]},
            {"key": "built_up_area_sqft", "label": "Built-up Area (sq.ft)", "type": "number"},
            {"key": "floors", "label": "Floors", "type": "number"},
            {"key": "fire_safety_noc", "label": "Fire Safety NOC Status", "type": "select", "options": ["Valid & Certified", "Renewal In Progress", "Expired / Pending Inspection"]},
            {"key": "structural_stability", "label": "Structural Audit Status", "type": "select", "options": ["Structurally Sound (Audit Passed)", "Minor Repairs Required", "Major Retrofitting Needed"]},
            {"key": "solar_rooftop_kw", "label": "Solar Rooftop Capacity (kW)", "type": "text"},
        ],
    },
    "schools": {
        "id": "schools",
        "name": "Government & Municipal Schools",
        "name_mr": "शासकीय आणि नगरपालिका शाळा",
        "icon": "🏫",
        "department": "health",
        "unit": "schools",
        "default_maintenance_days": 90,
        "spec_schema": [
            {"key": "school_level", "label": "School Level", "type": "select", "options": ["Primary School (Grade 1-5)", "Upper Primary (Grade 6-8)", "Secondary / High School (Grade 9-10)", "Higher Secondary / Junior College"]},
            {"key": "student_enrollment", "label": "Enrolled Students", "type": "number"},
            {"key": "classroom_count", "label": "Classrooms", "type": "number"},
            {"key": "drinking_water_facility", "label": "Safe Drinking Water (RO/Purifier)", "type": "select", "options": ["Functional RO Plant with UV", "Direct Filtered Tap Water", "Borewell (Needs Testing)", "No Dedicated Purifier"]},
            {"key": "separate_girls_toilet", "label": "Dedicated Functional Girls Toilet", "type": "select", "options": ["Yes - Fully Functional", "Yes - Minor Repair Needed", "No"]},
            {"key": "playground_available", "label": "Playground Facility", "type": "select", "options": ["Yes - Maintained", "Yes - Needs Leveling", "No"]},
        ],
    },
    "hospitals_phcs": {
        "id": "hospitals_phcs",
        "name": "Hospitals, PHCs & Wellness Centres",
        "name_mr": "रुग्णालये, प्राथमिक आरोग्य केंद्रे (PHC)",
        "icon": "🏥",
        "department": "health",
        "unit": "centers",
        "default_maintenance_days": 45,
        "spec_schema": [
            {"key": "facility_grade", "label": "Facility Grade", "type": "select", "options": ["Primary Health Centre (PHC)", "Community Health Centre (CHC)", "Sub-District Hospital (SDH)", "Arogya Vardhini Kendra / Sub-Centre", "Maternity & Child Hospital"]},
            {"key": "bed_capacity", "label": "Sanctioned Beds", "type": "number"},
            {"key": "doctor_in_charge", "label": "Medical Officer In-Charge", "type": "text"},
            {"key": "emergency_generator", "label": "24x7 Generator / Power Backup", "type": "select", "options": ["Yes - Auto DG Genset + UPS", "Yes - Manual Generator", "No Dedicated Backup"]},
            {"key": "cold_chain_vaccine", "label": "Vaccine Cold Chain Refrigerator (ILR)", "type": "select", "options": ["Operational & Temp Logged", "Faulty / Backup Used", "Not Applicable"]},
            {"key": "ambulance_attached", "label": "Dedicated 108/Ambulance Stationed", "type": "select", "options": ["Yes - Active on Site", "Shared / On Call", "No"]},
        ],
    },
    "parks": {
        "id": "parks",
        "name": "Parks, Gardens & Public Grounds",
        "name_mr": "उद्याने, बागा आणि सार्वजनिक मैदाने",
        "icon": "🌳",
        "department": "road",
        "unit": "parks",
        "default_maintenance_days": 30,
        "spec_schema": [
            {"key": "park_area_acres", "label": "Area (Acres / Sq.m)", "type": "number", "step": "0.1"},
            {"key": "walking_track_condition", "label": "Jogging / Walking Track", "type": "select", "options": ["Paved / Excellent", "Gravel / Fair", "Needs Resurfacing", "None"]},
            {"key": "open_gym_equipment", "label": "Open Gym & Kids Play Set", "type": "select", "options": ["Fully Functional & Certified", "Partial Wear / Maintenance Needed", "Damaged / Unsafe", "No Equipment"]},
            {"key": "irrigation_source", "label": "Watering / Irrigation Source", "type": "select", "options": ["Treated STP Recycled Water", "Borewell with Sprinklers", "Municipal Supply", "Manual Hose"]},
            {"key": "illumination_lighting", "label": "Night Lighting Coverage", "type": "select", "options": ["Complete LED Illumination", "Partial Lighting", "Poor / Non-functional Lights"]},
        ],
    },
    "cctv_cameras": {
        "id": "cctv_cameras",
        "name": "CCTV Surveillance Cameras",
        "name_mr": "सीसीटीव्ही सुरक्षा कॅमेरे",
        "icon": "📹",
        "department": "police",
        "unit": "cameras",
        "default_maintenance_days": 60,
        "spec_schema": [
            {"key": "camera_type", "label": "Camera Type", "type": "select", "options": ["PTZ 360-Degree Optical Zoom", "Bullet Night-Vision IR", "Dome High-Resolution (4K)", "ANPR Automatic Number Plate Recognition"]},
            {"key": "feed_status", "label": "Live Video Feed Status", "type": "select", "options": ["Online - Transmitting to Police Control Room", "Online - Local SD/NVR Recording", "Offline - Network Loss", "Offline - Power Loss", "Hardware Fault"]},
            {"key": "storage_retention_days", "label": "Storage Retention (Days)", "type": "select", "options": ["30 Days", "60 Days", "90 Days"]},
            {"key": "network_link", "label": "Backhaul Connectivity", "type": "select", "options": ["Dedicated OFC Fiber", "4G/5G Wireless SIM", "Wi-Fi Bridge"]},
            {"key": "junction_box_id", "label": "Connected Junction Box", "type": "text"},
        ],
    },
    "bus_stops": {
        "id": "bus_stops",
        "name": "Bus Stops & Transit Shelters",
        "name_mr": "बस थांबे आणि शेड",
        "icon": "🚏",
        "department": "road",
        "unit": "shelters",
        "default_maintenance_days": 90,
        "spec_schema": [
            {"key": "shelter_type", "label": "Shelter Type", "type": "select", "options": ["Stainless Steel Modern Shelter", "RCC Permanent Structure", "Cantilever MS Canopy", "Pole-only Flag Stop"]},
            {"key": "seating_capacity", "label": "Seating Capacity (Seats)", "type": "number"},
            {"key": "solar_lighting", "label": "Solar Roof Lighting", "type": "select", "options": ["Functional Solar Light", "Grid Connected", "No Lighting"]},
            {"key": "bus_routes_served", "label": "Key Bus Route Numbers", "type": "text"},
            {"key": "digital_display", "label": "Passenger Information Display (PIS)", "type": "select", "options": ["LED Real-Time ETA Display", "Printed Timetable Board", "No Display"]},
        ],
    },
    "borewells": {
        "id": "borewells",
        "name": "Public Borewells & Handpumps",
        "name_mr": "सार्वजनिक कूपनलिका आणि हातपंप",
        "icon": "🛢️",
        "department": "water",
        "unit": "borewells",
        "default_maintenance_days": 60,
        "spec_schema": [
            {"key": "mechanism", "label": "Pumping Mechanism", "type": "select", "options": ["Electric Submersible Motor", "Solar-Powered Pump", "India Mark II Handpump", "Dual Handpump + Motor"]},
            {"key": "depth_ft", "label": "Bore Depth (Feet)", "type": "number"},
            {"key": "motor_hp", "label": "Motor Capacity (HP)", "type": "text"},
            {"key": "discharge_yield_gph", "label": "Water Yield (Gallons/Liters per hr)", "type": "text"},
            {"key": "water_potability", "label": "Water Quality / Potability Test", "type": "select", "options": ["Potable - Passed Lab Test", "TDS High - Non-Potable / Utility Only", "Fluoride/Iron Detected - Filter Needed", "Test Expired / Due"]},
            {"key": "recharge_structure", "label": "Rainwater Recharge Pit Attached", "type": "select", "options": ["Yes - Functional Recharge Pit", "No"]},
        ],
    },
    "water_tanks": {
        "id": "water_tanks",
        "name": "Overhead Water Tanks (ESR / GSR)",
        "name_mr": "उंच पाण्याच्या टाक्या (ESR / GSR)",
        "icon": "💧",
        "department": "water",
        "unit": "reservoirs",
        "default_maintenance_days": 90,
        "spec_schema": [
            {"key": "tank_type", "label": "Structure Type", "type": "select", "options": ["Overhead Elevated Storage Reservoir (ESR)", "Ground Level Service Reservoir (GSR)", "Master Balancing Reservoir (MBR)", "High-Density Polyethylene Cluster"]},
            {"key": "capacity_liters", "label": "Storage Capacity (Liters / Lakh Liters)", "type": "text"},
            {"key": "staging_height_m", "label": "Staging Height (m)", "type": "number"},
            {"key": "chlorination_system", "label": "Chlorination / Disinfection System", "type": "select", "options": ["Automated Gas/Liquid Chlorinator", "Bleaching Dosing Pump", "Manual Tablet Dosing"]},
            {"key": "last_scoured_cleaned", "label": "Last Scour / Cleaning Date", "type": "date"},
            {"key": "structural_leakage_status", "label": "Tank Seepage / Structural Health", "type": "select", "options": ["Completely Dry / Sound", "Minor Sweating on Wall", "Active Seepage / Crack Detected", "Valve Leakage Only"]},
        ],
    },
    "transformers": {
        "id": "transformers",
        "name": "Transformers & Distribution Sub-Stations",
        "name_mr": "ट्रान्सफॉर्मर आणि वीज उपकेंद्रे",
        "icon": "⚡",
        "department": "electricity",
        "unit": "units",
        "default_maintenance_days": 60,
        "spec_schema": [
            {"key": "rating_kva", "label": "Capacity Rating (kVA)", "type": "select", "options": ["25 kVA", "63 kVA", "100 kVA", "200 kVA", "315 kVA", "500 kVA", "1000 kVA Sub-Station"]},
            {"key": "voltage_ratio", "label": "Voltage Ratio", "type": "select", "options": ["11 kV / 433 V (Distribution)", "22 kV / 433 V", "33 kV / 11 kV (Substation)"]},
            {"key": "mounting_type", "label": "Mounting Configuration", "type": "select", "options": ["Plinth-Mounted with Fencing", "H-Pole Mounted DP Structure", "Single Pole Mounted", "Indoor Substation Room"]},
            {"key": "oil_level_status", "label": "Transformer Oil Level & BDV Test", "type": "select", "options": ["Normal / BDV Test Passed", "Low Oil Level - Top Up Needed", "Oil Leakage Visible", "BDV Test Due"]},
            {"key": "earthing_resistance_ohms", "label": "Earthing Resistance (Ohms)", "type": "text"},
            {"key": "lightning_arrester", "label": "Lightning Arrester & Horn Gap", "type": "select", "options": ["Installed & Intact", "Damaged / Missing", "Not Installed"]},
        ],
    },
    "vehicles_machinery": {
        "id": "vehicles_machinery",
        "name": "Municipal Vehicles & Heavy Machinery",
        "name_mr": "पालिका वाहने आणि अवजड यंत्रसामग्री",
        "icon": "🚜",
        "department": "road",
        "unit": "vehicles",
        "default_maintenance_days": 45,
        "spec_schema": [
            {"key": "machinery_type", "label": "Vehicle / Equipment Category", "type": "select", "options": ["Hydraulic Garbage Compactor Truck", "TATA Ace Door-to-Door Waste Tipper", "Water Tanker (5000L - 10000L)", "JCB Backhoe Loader Excavator", "Suction & Jetting Sewer Machine", "Road Roller & Asphalt Patcher", "Emergency Ambulance Van", "Thermal Fogging Mosquito Machine", "Aerial Bucket Lift (Streetlight Repair)"]},
            {"key": "registration_number", "label": "Vehicle Registration (RTO Number)", "type": "text"},
            {"key": "chassis_engine_no", "label": "Engine / Serial Number", "type": "text"},
            {"key": "fuel_type", "label": "Fuel / Powertrain", "type": "select", "options": ["Diesel", "CNG Eco-Friendly", "Electric (EV Battery)", "Petrol"]},
            {"key": "fitness_certificate_expiry", "label": "RTO Fitness & Insurance Expiry", "type": "date"},
            {"key": "gps_tracking_enabled", "label": "AIS-140 GPS Vehicle Tracker", "type": "select", "options": ["Active & Streaming", "Installed - Offline", "Not Installed"]},
            {"key": "odometer_hours", "label": "Odometer / Engine Run Hours", "type": "text"},
            {"key": "assigned_driver", "label": "Assigned Operator / Driver", "type": "text"},
        ],
    },
}

ASSET_STATUS_OPTIONS = [
    "Operational",
    "Needs Maintenance",
    "Under Repair",
    "Critical / Defective",
    "Decommissioned",
]

def calculate_condition_index(condition_score: int) -> Dict[str, Any]:
    score = max(0, min(100, int(condition_score or 100)))
    if score >= 80:
        return {
            "score": score,
            "label": "Good / Healthy",
            "label_mr": "उत्कृष्ट / उत्तम",
            "tier": "good",
            "badge_class": "badge-success",
            "color": "#10b981",
        }
    elif score >= 50:
        return {
            "score": score,
            "label": "Fair / Functional",
            "label_mr": "समाधानकारक",
            "tier": "fair",
            "badge_class": "badge-warning",
            "color": "#f59e0b",
        }
    elif score >= 25:
        return {
            "score": score,
            "label": "Degraded / Service Required",
            "label_mr": "दुरुस्ती आवश्यक",
            "tier": "degraded",
            "badge_class": "badge-orange",
            "color": "#ea580c",
        }
    else:
        return {
            "score": score,
            "label": "Critical / Hazardous",
            "label_mr": "अतिधोकादायक / नादुरुस्त",
            "tier": "critical",
            "badge_class": "badge-danger",
            "color": "#ef4444",
        }

def evaluate_maintenance_due(next_due_str: Optional[str]) -> Dict[str, Any]:
    if not next_due_str:
        return {"status": "On Track", "status_mr": "नियमित", "is_overdue": False, "days_remaining": 999, "class": "text-success", "badge": "badge-success"}
    try:
        due = datetime.fromisoformat(next_due_str)
        now = datetime.now()
        diff = (due.date() - now.date()).days
        if diff < 0:
            return {
                "status": f"Overdue by {abs(diff)} day(s)",
                "status_mr": f"{abs(diff)} दिवस उशीर",
                "is_overdue": True,
                "days_remaining": diff,
                "class": "text-danger",
                "badge": "badge-danger",
            }
        elif diff <= 7:
            return {
                "status": f"Due in {diff} day(s)",
                "status_mr": f"{diff} दिवसात नियोजित",
                "is_overdue": False,
                "days_remaining": diff,
                "class": "text-warning",
                "badge": "badge-warning",
            }
        else:
            return {
                "status": f"Scheduled in {diff} days",
                "status_mr": f"{diff} दिवसांनी",
                "is_overdue": False,
                "days_remaining": diff,
                "class": "text-success",
                "badge": "badge-success",
            }
    except (ValueError, TypeError):
        return {"status": "Scheduled", "status_mr": "नियोजित", "is_overdue": False, "days_remaining": 999, "class": "text-success", "badge": "badge-success"}

def generate_svg_qr(uid: str, name: str = "", width: int = 140, height: int = 140) -> str:
    import hashlib
    h = hashlib.md5(uid.encode("utf-8")).hexdigest()
    grid_size = 21
    cell_size = width / grid_size
    rects = []
    
    def add_finder(ox: int, oy: int):
        for r in range(7):
            for c in range(7):
                if (r in (0, 6) or c in (0, 6)) or (2 <= r <= 4 and 2 <= c <= 4):
                    x = (ox + c) * cell_size
                    y = (oy + r) * cell_size
                    rects.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_size:.1f}" height="{cell_size:.1f}" fill="#0f172a" />')

    add_finder(0, 0)
    add_finder(14, 0)
    add_finder(0, 14)

    for i in range(8, 13):
        if i % 2 == 0:
            rects.append(f'<rect x="{i * cell_size:.1f}" y="{6 * cell_size:.1f}" width="{cell_size:.1f}" height="{cell_size:.1f}" fill="#0f172a" />')
            rects.append(f'<rect x="{6 * cell_size:.1f}" y="{i * cell_size:.1f}" width="{cell_size:.1f}" height="{cell_size:.1f}" fill="#0f172a" />')

    hash_int = int(h, 16)
    bit_index = 0
    for r in range(grid_size):
        for c in range(grid_size):
            if (r < 8 and c < 8) or (r < 8 and c >= 13) or (r >= 13 and c < 8):
                continue
            if r == 6 or c == 6:
                continue
            bit = (hash_int >> (bit_index % 128)) & 1
            bit_index += 1
            if bit:
                x = c * cell_size
                y = r * cell_size
                rects.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_size:.1f}" height="{cell_size:.1f}" fill="#1e293b" rx="0.5"/>')

    matrix_svg = "".join(rects)
    center_x = width / 2
    center_y = height / 2
    r_val = cell_size * 2.2
    text_y = center_y + 2.5
    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" class="civic-qr-svg" role="img" aria-label="QR Code for {uid}">
        <rect width="100%" height="100%" fill="#ffffff" rx="8"/>
        <g id="qr-matrix">
            {matrix_svg}
        </g>
        <circle cx="{center_x}" cy="{center_y}" r="{r_val}" fill="#ffffff" stroke="#2563eb" stroke-width="1.5"/>
        <text x="{center_x}" y="{text_y}" text-anchor="middle" font-size="7" font-weight="900" fill="#2563eb" font-family="system-ui, sans-serif">CIVIC</text>
    </svg>"""
    return svg_content

def summarize_asset_portfolio(assets: List[Any], complaints: List[Any] = None) -> Dict[str, Any]:
    total = len(assets)
    if total == 0:
        return {
            "total": 0,
            "operational": 0,
            "needs_repair": 0,
            "critical": 0,
            "total_valuation": 0,
            "avg_health_score": 100,
            "by_category": {},
            "by_ward": {},
            "by_department": {},
            "maintenance_overdue": 0,
            "active_fleet_count": 0,
        }

    operational = 0
    needs_repair = 0
    critical = 0
    total_val = 0.0
    scores = []
    maintenance_overdue = 0
    active_fleet = 0
    by_category: Dict[str, Dict[str, Any]] = {k: {"count": 0, "valuation": 0, "critical": 0, "name": v["name"], "name_mr": v.get("name_mr", v["name"]), "icon": v["icon"]} for k, v in ASSET_CATEGORIES.items()}
    by_ward: Dict[str, Dict[str, Any]] = {}
    by_department: Dict[str, int] = {}

    now = datetime.now()

    for a in assets:
        status = a["status"]
        score = int(a["condition_score"] or 100)
        val = float(a["estimated_value"] or 0)
        cat = a["category"]
        ward = a["ward"] or "Central Ward"
        dept = a["department"] or "road"
        next_maint = a["next_maintenance_due"]

        total_val += val
        scores.append(score)

        if status == "Operational":
            operational += 1
        elif status in {"Needs Maintenance", "Under Repair"}:
            needs_repair += 1
        elif status == "Critical / Defective":
            critical += 1

        if cat == "vehicles_machinery" and status in {"Operational", "Under Repair"}:
            active_fleet += 1

        if next_maint:
            try:
                due_dt = datetime.fromisoformat(next_maint)
                if due_dt.date() < now.date():
                    maintenance_overdue += 1
            except (ValueError, TypeError):
                pass

        if cat in by_category:
            by_category[cat]["count"] += 1
            by_category[cat]["valuation"] += val
            if score < 50 or status == "Critical / Defective":
                by_category[cat]["critical"] += 1

        if ward not in by_ward:
            by_ward[ward] = {"count": 0, "valuation": 0, "critical": 0}
        by_ward[ward]["count"] += 1
        by_ward[ward]["valuation"] += val
        if score < 50:
            by_ward[ward]["critical"] += 1

        by_department[dept] = by_department.get(dept, 0) + 1

    avg_health = round(sum(scores) / len(scores), 1) if scores else 100

    return {
        "total": total,
        "operational": operational,
        "needs_repair": needs_repair,
        "critical": critical,
        "total_valuation": total_val,
        "avg_health_score": avg_health,
        "by_category": by_category,
        "by_ward": by_ward,
        "by_department": by_department,
        "maintenance_overdue": maintenance_overdue,
        "active_fleet_count": active_fleet,
    }

def get_demo_assets_seed() -> List[Dict[str, Any]]:
    today = datetime.now()
    d_iso = lambda days_ago: (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    next_iso = lambda days_future: (today + timedelta(days=days_future)).strftime("%Y-%m-%d")

    return [
        {
            "asset_uid": "AST-ROD-001",
            "name": "Main Market Road (Shivaji Chowk to Station)",
            "category": "roads",
            "department": "road",
            "ward": "Ward 1 · Central",
            "village": "Talegaon Central",
            "location": "Station Road Junction, Shivaji Chowk",
            "latitude": 18.7324,
            "longitude": 73.6841,
            "status": "Operational",
            "condition_score": 88,
            "install_date": d_iso(720),
            "last_inspection_date": d_iso(20),
            "next_maintenance_due": next_iso(160),
            "estimated_value": 4500000,
            "replacement_cost": 5200000,
            "specifications": json.dumps({
                "surface_type": "Asphalt / Bitumen",
                "length_km": 2.4,
                "width_m": 12.0,
                "lane_count": "4 Lanes",
                "traffic_density": "Heavy",
                "contractor": "Apex Infra Works Pvt Ltd",
                "warranty_years": 3,
            }),
            "assigned_worker": "RD-01",
            "notes": "Main arterial commercial corridor. Heavy morning and evening transit load.",
        },
        {
            "asset_uid": "AST-ROD-002",
            "name": "Gram Panchayat Link Road (Zilla Parishad stretch)",
            "category": "roads",
            "department": "road",
            "ward": "Ward 3 · North",
            "village": "Khadki Gaon",
            "location": "Near ZP High School, Khadki",
            "latitude": 18.7412,
            "longitude": 73.6915,
            "status": "Needs Maintenance",
            "condition_score": 48,
            "install_date": d_iso(1100),
            "last_inspection_date": d_iso(45),
            "next_maintenance_due": next_iso(-10),
            "estimated_value": 1800000,
            "replacement_cost": 2300000,
            "specifications": json.dumps({
                "surface_type": "WBM / Gravel",
                "length_km": 1.1,
                "width_m": 6.5,
                "lane_count": "2 Lanes",
                "traffic_density": "Moderate",
                "contractor": "Sai Construction",
                "warranty_years": 1,
            }),
            "assigned_worker": "RD-01",
            "notes": "Edge raveling and pothole clusters reported during monsoon runoff.",
        },
        {
            "asset_uid": "AST-STL-042",
            "name": "High-Mast Commercial LED Light (Pole #42)",
            "category": "streetlights",
            "department": "electricity",
            "ward": "Ward 1 · Central",
            "village": "Talegaon Central",
            "location": "Bazaar Peth Circle, Market Ward",
            "latitude": 18.7335,
            "longitude": 73.6852,
            "status": "Operational",
            "condition_score": 95,
            "install_date": d_iso(300),
            "last_inspection_date": d_iso(15),
            "next_maintenance_due": next_iso(75),
            "estimated_value": 120000,
            "replacement_cost": 140000,
            "specifications": json.dumps({
                "luminaire_type": "Halogen High-Mast",
                "wattage": "400W High Mast",
                "pole_material": "Octagonal Galvanized Steel",
                "height_m": 16.0,
                "feeder_pillar": "FP-MKT-01",
                "auto_timer": "Smart Astronomical Timer",
            }),
            "assigned_worker": "ELE-01",
            "notes": "16-meter motorized high mast illuminating central intersection.",
        },
        {
            "asset_uid": "AST-STL-089",
            "name": "Solar Streetlight Cluster (Poles 89-94)",
            "category": "streetlights",
            "department": "electricity",
            "ward": "Ward 2 · East",
            "village": "Shanti Nagar",
            "location": "Shanti Nagar bypass curve",
            "latitude": 18.7288,
            "longitude": 73.6931,
            "status": "Needs Maintenance",
            "condition_score": 62,
            "install_date": d_iso(600),
            "last_inspection_date": d_iso(50),
            "next_maintenance_due": next_iso(10),
            "estimated_value": 75000,
            "replacement_cost": 90000,
            "specifications": json.dumps({
                "luminaire_type": "Solar-Powered LED",
                "wattage": "70W",
                "pole_material": "Tubular Steel",
                "height_m": 7.0,
                "feeder_pillar": "Standalone Solar Battery",
                "auto_timer": "LDR Daylight Sensor",
            }),
            "assigned_worker": "ELE-01",
            "notes": "Solar panel cleaning required to restore 100% battery backup capacity.",
        },
        {
            "asset_uid": "AST-WTR-108",
            "name": "Primary 300mm Ductile-Iron Feeder Line",
            "category": "water_pipelines",
            "department": "water",
            "ward": "Ward 1 · Central",
            "village": "Talegaon Central",
            "location": "Water Works Road to Central Reservoir",
            "latitude": 18.7302,
            "longitude": 73.6811,
            "status": "Operational",
            "condition_score": 91,
            "install_date": d_iso(450),
            "last_inspection_date": d_iso(30),
            "next_maintenance_due": next_iso(90),
            "estimated_value": 3800000,
            "replacement_cost": 4400000,
            "specifications": json.dumps({
                "pipe_material": "Ductile Iron (DI)",
                "diameter_mm": "300mm",
                "pressure_rating_bar": 10.0,
                "length_m": 1800,
                "source_reservoir": "Talegaon Dam Treatment Plant",
                "burial_depth_m": 1.5,
            }),
            "assigned_worker": "WTR-01",
            "notes": "Core water supply line feeding over 6,500 households.",
        },
        {
            "asset_uid": "AST-WTR-204",
            "name": "Secondary 150mm Distribution Loop (North Ward)",
            "category": "water_pipelines",
            "department": "water",
            "ward": "Ward 3 · North",
            "village": "Khadki Gaon",
            "location": "Gaothan Internal Lane 4",
            "latitude": 18.7435,
            "longitude": 73.6898,
            "status": "Needs Maintenance",
            "condition_score": 54,
            "install_date": d_iso(1400),
            "last_inspection_date": d_iso(75),
            "next_maintenance_due": next_iso(-5),
            "estimated_value": 950000,
            "replacement_cost": 1200000,
            "specifications": json.dumps({
                "pipe_material": "Cast Iron (CI)",
                "diameter_mm": "150mm",
                "pressure_rating_bar": 6.0,
                "length_m": 850,
                "source_reservoir": "ESR North Ward Tank #2",
                "burial_depth_m": 1.2,
            }),
            "assigned_worker": "WTR-01",
            "notes": "Older cast-iron joint showing minor pressure drop during peak morning hours.",
        },
        {
            "asset_uid": "AST-VLV-012",
            "name": "Main Sluice Control Valve #12 (Sector 1)",
            "category": "valves_pumps",
            "department": "water",
            "ward": "Ward 1 · Central",
            "village": "Talegaon Central",
            "location": "Opposite Civil Hospital Junction",
            "latitude": 18.7315,
            "longitude": 73.6835,
            "status": "Operational",
            "condition_score": 85,
            "install_date": d_iso(360),
            "last_inspection_date": d_iso(25),
            "next_maintenance_due": next_iso(35),
            "estimated_value": 180000,
            "replacement_cost": 210000,
            "specifications": json.dumps({
                "equipment_type": "Sluice Valve",
                "power_hp": "N/A - Mechanical Gear",
                "discharge_lpm": 1200,
                "valve_size_mm": "250mm",
                "automation_mode": "Semi-Automatic Panel",
            }),
            "assigned_worker": "WTR-02",
            "notes": "Controls morning 6 AM - 9 AM pressure cycle for Central & Hospital wards.",
        },
        {
            "asset_uid": "AST-PMP-003",
            "name": "Submersible Booster Pump Station (30 HP)",
            "category": "valves_pumps",
            "department": "water",
            "ward": "Ward 2 · East",
            "village": "Shanti Nagar",
            "location": "Pumping Chamber 3, Shanti Nagar",
            "latitude": 18.7275,
            "longitude": 73.6962,
            "status": "Operational",
            "condition_score": 79,
            "install_date": d_iso(520),
            "last_inspection_date": d_iso(18),
            "next_maintenance_due": next_iso(42),
            "estimated_value": 350000,
            "replacement_cost": 420000,
            "specifications": json.dumps({
                "equipment_type": "Booster Pump",
                "power_hp": "30 HP / 22 kW",
                "discharge_lpm": 2400,
                "valve_size_mm": "150mm Suction",
                "automation_mode": "SCADA / IoT Automated",
            }),
            "assigned_worker": "WTR-02",
            "notes": "Connected to IoT pressure telemetry; operational efficiency at 92%.",
        },
        {
            "asset_uid": "AST-DRN-005",
            "name": "RCC Underground Stormwater Box Drain",
            "category": "drainage",
            "department": "road",
            "ward": "Ward 1 · Central",
            "village": "Talegaon Central",
            "location": "Market Yard to Outfall Canal",
            "latitude": 18.7341,
            "longitude": 73.6872,
            "status": "Operational",
            "condition_score": 82,
            "install_date": d_iso(400),
            "last_inspection_date": d_iso(28),
            "next_maintenance_due": next_iso(62),
            "estimated_value": 2800000,
            "replacement_cost": 3300000,
            "specifications": json.dumps({
                "drain_type": "Underground RCC Box Drain",
                "width_m": 1.8,
                "depth_m": 1.5,
                "desilting_status": "Clean / De-silted",
                "discharge_destination": "Indrayani River Outfall Canal",
            }),
            "assigned_worker": "RD-01",
            "notes": "De-silted prior to monsoon season; flow rate free-flowing.",
        },
        {
            "asset_uid": "AST-DRN-014",
            "name": "Open Masonry Nallah (Gandhi Nagar border)",
            "category": "drainage",
            "department": "road",
            "ward": "Ward 3 · North",
            "village": "Khadki Gaon",
            "location": "Khadki Nallah Bridge",
            "latitude": 18.7449,
            "longitude": 73.6925,
            "status": "Needs Maintenance",
            "condition_score": 45,
            "install_date": d_iso(900),
            "last_inspection_date": d_iso(60),
            "next_maintenance_due": next_iso(5),
            "estimated_value": 650000,
            "replacement_cost": 850000,
            "specifications": json.dumps({
                "drain_type": "Open Masonry Nallah",
                "width_m": 2.2,
                "depth_m": 1.8,
                "desilting_status": "Partial Silt Accumulation",
                "discharge_destination": "North Creek Drainage",
            }),
            "assigned_worker": "RD-01",
            "notes": "Garbage debris trapped near culvert mouth requires suction/excavator clearance.",
        },
        {
            "asset_uid": "AST-TLT-003",
            "name": "Community Sanitation Complex (Pink & Green Toilet)",
            "category": "public_toilets",
            "department": "health",
            "ward": "Ward 1 · Central",
            "village": "Talegaon Central",
            "location": "Bus Stand Complex, Market Area",
            "latitude": 18.7330,
            "longitude": 73.6848,
            "status": "Operational",
            "condition_score": 90,
            "install_date": d_iso(240),
            "last_inspection_date": d_iso(5),
            "next_maintenance_due": next_iso(25),
            "estimated_value": 750000,
            "replacement_cost": 900000,
            "specifications": json.dumps({
                "male_seats": 6,
                "female_seats": 6,
                "pwd_friendly": "Yes - Fully Accessible",
                "running_water": "Yes - Overhead Tank + Municipal Supply",
                "electricity_status": "Grid Connected + Solar Backup",
                "cleanliness_audit_score": "5 - Spotless",
                "cleaning_contractor": "Sulabh Swachhata Mission",
            }),
            "assigned_worker": "HLT-01",
            "notes": "Includes dedicated sanitary napkin dispenser and incinerator unit.",
        },
        {
            "asset_uid": "AST-TLT-008",
            "name": "Gramin Public Toilet Block (Shanti Nagar)",
            "category": "public_toilets",
            "department": "health",
            "ward": "Ward 2 · East",
            "village": "Shanti Nagar",
            "location": "Near Community Ground, Shanti Nagar",
            "latitude": 18.7262,
            "longitude": 73.6948,
            "status": "Needs Maintenance",
            "condition_score": 58,
            "install_date": d_iso(550),
            "last_inspection_date": d_iso(14),
            "next_maintenance_due": next_iso(16),
            "estimated_value": 420000,
            "replacement_cost": 500000,
            "specifications": json.dumps({
                "male_seats": 4,
                "female_seats": 4,
                "pwd_friendly": "No",
                "running_water": "Intermittent / Tanker Supply",
                "electricity_status": "Grid Connected",
                "cleanliness_audit_score": "3 - Acceptable",
                "cleaning_contractor": "Local Ward Sanitation Staff",
            }),
            "assigned_worker": "HLT-01",
            "notes": "Water tap replacement requested for female cubicle #2.",
        },
        {
            "asset_uid": "AST-BIN-088",
            "name": "Smart Segregated Dumper Placer (4.5 m3)",
            "category": "garbage_bins",
            "department": "health",
            "ward": "Ward 1 · Central",
            "village": "Talegaon Central",
            "location": "Vegetable Market Corner, Bazaar Peth",
            "latitude": 18.7348,
            "longitude": 73.6859,
            "status": "Operational",
            "condition_score": 86,
            "install_date": d_iso(180),
            "last_inspection_date": d_iso(2),
            "next_maintenance_due": next_iso(13),
            "estimated_value": 85000,
            "replacement_cost": 95000,
            "specifications": json.dumps({
                "bin_type": "Community Dumper Placer (4.5 m3)",
                "capacity_liters": "4500 Liters",
                "iot_fill_sensor": "Yes - IoT Connected",
                "collection_frequency": "Twice Daily",
                "current_fill_percentage": 42,
            }),
            "assigned_worker": "HLT-01",
            "notes": "Ultrasonic sensor transmitting hourly fill level to Solid Waste Control Room.",
        },
        {
            "asset_uid": "AST-BIN-112",
            "name": "Twin Wet & Dry Wheeled Bins (240L Cluster)",
            "category": "garbage_bins",
            "department": "health",
            "ward": "Ward 3 · North",
            "village": "Khadki Gaon",
            "location": "Khadki School Chowk",
            "latitude": 18.7420,
            "longitude": 73.6908,
            "status": "Operational",
            "condition_score": 75,
            "install_date": d_iso(120),
            "last_inspection_date": d_iso(4),
            "next_maintenance_due": next_iso(11),
            "estimated_value": 18000,
            "replacement_cost": 22000,
            "specifications": json.dumps({
                "bin_type": "Twin Segregated Bin (Wet & Dry)",
                "capacity_liters": "480 Liters (2x240L)",
                "iot_fill_sensor": "No Sensor",
                "collection_frequency": "Daily",
                "current_fill_percentage": 68,
            }),
            "assigned_worker": "HLT-01",
            "notes": "Door-to-door tipper empties this station daily at 8:30 AM.",
        },
        {
            "asset_uid": "AST-BLD-001",
            "name": "Gram Panchayat Administrative Bhawan",
            "category": "gov_buildings",
            "department": "road",
            "ward": "Ward 1 · Central",
            "village": "Talegaon Central",
            "location": "Main Chowk, Talegaon",
            "latitude": 18.7310,
            "longitude": 73.6845,
            "status": "Operational",
            "condition_score": 92,
            "install_date": d_iso(1200),
            "last_inspection_date": d_iso(30),
            "next_maintenance_due": next_iso(150),
            "estimated_value": 12500000,
            "replacement_cost": 14000000,
            "specifications": json.dumps({
                "facility_type": "Gram Panchayat Karyalaya",
                "built_up_area_sqft": 4500,
                "floors": 2,
                "fire_safety_noc": "Valid & Certified",
                "structural_stability": "Structurally Sound (Audit Passed)",
                "solar_rooftop_kw": "10 kW Net Metered",
            }),
            "assigned_worker": "RD-01",
            "notes": "Headquarters of local civic administration, meeting hall, and Citizen CSC Centre.",
        },
        {
            "asset_uid": "AST-BLD-004",
            "name": "Ward Sub-Office & Disaster Relief Shelter",
            "category": "gov_buildings",
            "department": "road",
            "ward": "Ward 2 · East",
            "village": "Shanti Nagar",
            "location": "East Zone Civic Office, Shanti Nagar",
            "latitude": 18.7295,
            "longitude": 73.6950,
            "status": "Operational",
            "condition_score": 84,
            "install_date": d_iso(800),
            "last_inspection_date": d_iso(45),
            "next_maintenance_due": next_iso(135),
            "estimated_value": 6800000,
            "replacement_cost": 7500000,
            "specifications": json.dumps({
                "facility_type": "Disaster Relief Shelter",
                "built_up_area_sqft": 3200,
                "floors": 1,
                "fire_safety_noc": "Valid & Certified",
                "structural_stability": "Structurally Sound (Audit Passed)",
                "solar_rooftop_kw": "5 kW Off-Grid",
            }),
            "assigned_worker": "RD-01",
            "notes": "Designated emergency muster point during floods or extreme weather events.",
        },
        {
            "asset_uid": "AST-SCH-014",
            "name": "Zilla Parishad Model Primary & Secondary School",
            "category": "schools",
            "department": "health",
            "ward": "Ward 3 · North",
            "village": "Khadki Gaon",
            "location": "Khadki School Campus",
            "latitude": 18.7428,
            "longitude": 73.6920,
            "status": "Operational",
            "condition_score": 87,
            "install_date": d_iso(1500),
            "last_inspection_date": d_iso(20),
            "next_maintenance_due": next_iso(70),
            "estimated_value": 8500000,
            "replacement_cost": 9800000,
            "specifications": json.dumps({
                "school_level": "Upper Primary (Grade 6-8)",
                "student_enrollment": 380,
                "classroom_count": 12,
                "drinking_water_facility": "Functional RO Plant with UV",
                "separate_girls_toilet": "Yes - Fully Functional",
                "playground_available": "Yes - Maintained",
            }),
            "assigned_worker": "HLT-01",
            "notes": "PM-SHRI verified school campus with smart classroom audio-visual lab.",
        },
        {
            "asset_uid": "AST-HSP-002",
            "name": "Talegaon Primary Health Centre (PHC & 24x7 Maternity)",
            "category": "hospitals_phcs",
            "department": "health",
            "ward": "Ward 1 · Central",
            "village": "Talegaon Central",
            "location": "Hospital Road, Near Civil Court",
            "latitude": 18.7305,
            "longitude": 73.6828,
            "status": "Operational",
            "condition_score": 94,
            "install_date": d_iso(1100),
            "last_inspection_date": d_iso(10),
            "next_maintenance_due": next_iso(35),
            "estimated_value": 16000000,
            "replacement_cost": 18500000,
            "specifications": json.dumps({
                "facility_grade": "Primary Health Centre (PHC)",
                "bed_capacity": 30,
                "doctor_in_charge": "Dr. Rameshwar Kadam (MBBS, DGO)",
                "emergency_generator": "Yes - Auto DG Genset + UPS",
                "cold_chain_vaccine": "Operational & Temp Logged",
                "ambulance_attached": "Yes - Active on Site",
            }),
            "assigned_worker": "HLT-01",
            "notes": "Serves 45,000 rural and semi-urban population; 24x7 emergency delivery room.",
        },
        {
            "asset_uid": "AST-PRK-009",
            "name": "Chhatrapati Shivaji Maharaj Public Garden & Open Gym",
            "category": "parks",
            "department": "road",
            "ward": "Ward 1 · Central",
            "village": "Talegaon Central",
            "location": "Shivaji Nagar Garden Road",
            "latitude": 18.7355,
            "longitude": 73.6820,
            "status": "Operational",
            "condition_score": 89,
            "install_date": d_iso(400),
            "last_inspection_date": d_iso(7),
            "next_maintenance_due": next_iso(23),
            "estimated_value": 3200000,
            "replacement_cost": 3800000,
            "specifications": json.dumps({
                "park_area_acres": 2.5,
                "walking_track_condition": "Paved / Excellent",
                "open_gym_equipment": "Fully Functional & Certified",
                "irrigation_source": "Borewell with Sprinklers",
                "illumination_lighting": "Complete LED Illumination",
            }),
            "assigned_worker": "RD-01",
            "notes": "Includes 600m paved walking track, senior citizen gazebo, and 12 outdoor gym units.",
        },
        {
            "asset_uid": "AST-CAM-033",
            "name": "Smart PTZ 360° Surveillance Camera (Junction 3)",
            "category": "cctv_cameras",
            "department": "police",
            "ward": "Ward 1 · Central",
            "village": "Talegaon Central",
            "location": "Station Chowk Traffic Island",
            "latitude": 18.7328,
            "longitude": 73.6838,
            "status": "Operational",
            "condition_score": 96,
            "install_date": d_iso(200),
            "last_inspection_date": d_iso(12),
            "next_maintenance_due": next_iso(48),
            "estimated_value": 110000,
            "replacement_cost": 130000,
            "specifications": json.dumps({
                "camera_type": "PTZ 360-Degree Optical Zoom",
                "feed_status": "Online - Transmitting to Police Control Room",
                "storage_retention_days": "60 Days",
                "network_link": "Dedicated OFC Fiber",
                "junction_box_id": "JB-STN-03",
            }),
            "assigned_worker": "SAF-01",
            "notes": "High definition feed integrated with Women Safety & Traffic Monitoring Dashboard.",
        },
        {
            "asset_uid": "AST-BUS-021",
            "name": "Modern Stainless Steel Transit Shelter (Market Stop)",
            "category": "bus_stops",
            "department": "road",
            "ward": "Ward 1 · Central",
            "village": "Talegaon Central",
            "location": "Market Main Gate, Bazaar Peth",
            "latitude": 18.7338,
            "longitude": 73.6860,
            "status": "Operational",
            "condition_score": 83,
            "install_date": d_iso(350),
            "last_inspection_date": d_iso(22),
            "next_maintenance_due": next_iso(68),
            "estimated_value": 240000,
            "replacement_cost": 280000,
            "specifications": json.dumps({
                "shelter_type": "Stainless Steel Modern Shelter",
                "seating_capacity": 10,
                "solar_lighting": "Functional Solar Light",
                "bus_routes_served": "Route 12, 18, 45 (Pune-Lonavala PMT)",
                "digital_display": "Printed Timetable Board",
            }),
            "assigned_worker": "RD-01",
            "notes": "High footfall transit hub with braille tactile paving for visually impaired commuters.",
        },
        {
            "asset_uid": "AST-BOR-019",
            "name": "Community Solar Dual Pump Borewell #19",
            "category": "borewells",
            "department": "water",
            "ward": "Ward 2 · East",
            "village": "Shanti Nagar",
            "location": "Shanti Nagar Hanuman Mandir Compound",
            "latitude": 18.7280,
            "longitude": 73.6940,
            "status": "Operational",
            "condition_score": 81,
            "install_date": d_iso(380),
            "last_inspection_date": d_iso(15),
            "next_maintenance_due": next_iso(45),
            "estimated_value": 210000,
            "replacement_cost": 250000,
            "specifications": json.dumps({
                "mechanism": "Dual Handpump + Motor",
                "depth_ft": 280,
                "motor_hp": "3 HP Solar DC Pump",
                "discharge_yield_gph": "2800 LPH",
                "water_potability": "Potable - Passed Lab Test",
                "recharge_structure": "Yes - Functional Recharge Pit",
            }),
            "assigned_worker": "WTR-02",
            "notes": "Supplies backup non-potable and potable water to 180 families during grid power cuts.",
        },
        {
            "asset_uid": "AST-TNK-008",
            "name": "Elevated Storage Reservoir (ESR 5.0 Lakh Litres)",
            "category": "water_tanks",
            "department": "water",
            "ward": "Ward 1 · Central",
            "village": "Talegaon Central",
            "location": "Hilltop Water Works Compound",
            "latitude": 18.7298,
            "longitude": 73.6805,
            "status": "Operational",
            "condition_score": 93,
            "install_date": d_iso(900),
            "last_inspection_date": d_iso(35),
            "next_maintenance_due": next_iso(55),
            "estimated_value": 6500000,
            "replacement_cost": 7800000,
            "specifications": json.dumps({
                "tank_type": "Overhead Elevated Storage Reservoir (ESR)",
                "capacity_liters": "500,000 Liters (5.0 Lakh L)",
                "staging_height_m": 18.0,
                "chlorination_system": "Automated Gas/Liquid Chlorinator",
                "last_scoured_cleaned": d_iso(45),
                "structural_leakage_status": "Completely Dry / Sound",
            }),
            "assigned_worker": "WTR-01",
            "notes": "Gravity distribution reservoir supplying Wards 1 and 2 uninterrupted water supply.",
        },
        {
            "asset_uid": "AST-TRF-015",
            "name": "Distribution Transformer (200 kVA Plinth Mounted)",
            "category": "transformers",
            "department": "electricity",
            "ward": "Ward 1 · Central",
            "village": "Talegaon Central",
            "location": "Market Sub-Station Enclosure, Ward 1",
            "latitude": 18.7318,
            "longitude": 73.6855,
            "status": "Operational",
            "condition_score": 87,
            "install_date": d_iso(650),
            "last_inspection_date": d_iso(18),
            "next_maintenance_due": next_iso(42),
            "estimated_value": 480000,
            "replacement_cost": 550000,
            "specifications": json.dumps({
                "rating_kva": "200 kVA",
                "voltage_ratio": "11 kV / 433 V (Distribution)",
                "mounting_type": "Plinth-Mounted with Fencing",
                "oil_level_status": "Normal / BDV Test Passed",
                "earthing_resistance_ohms": "1.8 Ohms (Safe < 2.0)",
                "lightning_arrester": "Installed & Intact",
            }),
            "assigned_worker": "ELE-01",
            "notes": "Supplies 3-phase commercial and domestic load for central marketplace.",
        },
        {
            "asset_uid": "AST-VEH-004",
            "name": "Hydraulic Solid Waste Compactor (MH-14-GH-4821)",
            "category": "vehicles_machinery",
            "department": "road",
            "ward": "Ward 1 · Central",
            "village": "Talegaon Central",
            "location": "Municipal Transport Yard, Depot 1",
            "latitude": 18.7290,
            "longitude": 73.6870,
            "status": "Operational",
            "condition_score": 90,
            "install_date": d_iso(320),
            "last_inspection_date": d_iso(8),
            "next_maintenance_due": next_iso(37),
            "estimated_value": 3200000,
            "replacement_cost": 3600000,
            "specifications": json.dumps({
                "machinery_type": "Hydraulic Garbage Compactor Truck",
                "registration_number": "MH-14-GH-4821",
                "chassis_engine_no": "TATA-LPT-1618-9941",
                "fuel_type": "CNG Eco-Friendly",
                "fitness_certificate_expiry": next_iso(400),
                "gps_tracking_enabled": "Active & Streaming",
                "odometer_hours": "18,450 km",
                "assigned_driver": "Suresh Waghmare (Driver #12)",
            }),
            "assigned_worker": "RD-01",
            "notes": "14-cubic-meter compactor truck serving morning commercial collection routes.",
        },
        {
            "asset_uid": "AST-VEH-009",
            "name": "JCB 3DX Heavy Excavator & Backhoe Loader (MH-14-EB-3011)",
            "category": "vehicles_machinery",
            "department": "road",
            "ward": "Ward 2 · East",
            "village": "Shanti Nagar",
            "location": "Public Works Depot 2, Shanti Nagar",
            "latitude": 18.7282,
            "longitude": 73.6970,
            "status": "Operational",
            "condition_score": 84,
            "install_date": d_iso(480),
            "last_inspection_date": d_iso(14),
            "next_maintenance_due": next_iso(31),
            "estimated_value": 2900000,
            "replacement_cost": 3300000,
            "specifications": json.dumps({
                "machinery_type": "JCB Backhoe Loader Excavator",
                "registration_number": "MH-14-EB-3011",
                "chassis_engine_no": "JCB-4WD-7720-E",
                "fuel_type": "Diesel",
                "fitness_certificate_expiry": next_iso(280),
                "gps_tracking_enabled": "Active & Streaming",
                "odometer_hours": "1,820 Engine Hours",
                "assigned_driver": "Santosh Gaikwad (Operator #04)",
            }),
            "assigned_worker": "RD-01",
            "notes": "Dispatched for drain desiltation, road trenching, and disaster clearance operations.",
        },
    ]
