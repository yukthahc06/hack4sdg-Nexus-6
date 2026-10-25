import streamlit as st
import requests
import json
import base64
import os
import time
from datetime import datetime, timezone

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Dynamo Charzz Dashboard", 
    page_icon="⚡", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# --- PREMIUM TESLA-STYLE MINIMALIST CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@200;400;600&display=swap');
    
    /* Deep Black Luxury Background */
    .stApp {
        background-color: #000000;
        color: #f4f4f5;
        font-family: 'Montserrat', sans-serif;
    }
    
    /* Hide top colored decoration bar */
    div[data-testid="stDecoration"] {
        display: none;
    }
    
    /* Make header bar transparent so it doesn't leave an ugly bar */
    header[data-testid="stHeader"] {
        background-color: transparent !important;
    }
    
    /* Hide Deploy button and hamburger menu toolbar */
    div[data-testid="stToolbar"] {
        visibility: hidden;
        height: 0%;
        position: fixed;
    }
    #MainMenu {
        visibility: hidden;
    }
    footer {
        visibility: hidden;
    }

    /* Remove close/collapse arrow mark so sidebar stays permanently open */
    [data-testid="stSidebarCollapseButton"],
    [data-testid="collapsedControl"],
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="stSidebarHeader"] button,
    button[kind="header"] {
        display: none !important;
        visibility: hidden !important;
    }

    /* Keep sidebar permanently docked as it is */
    [data-testid="stSidebar"] {
        visibility: visible !important;
        transform: none !important;
        background-color: #09090b;
        border-right: 1px solid #27272a;
    }

    /* Brand Header with Logo and Title */
    .brand-container {
        display: flex;
        align-items: center;
        gap: 22px;
        margin-bottom: 6px;
    }
    .brand-logo {
        height: 5.4rem;
        width: auto;
        object-fit: contain;
        filter: drop-shadow(0 0 16px rgba(34, 197, 94, 0.4));
    }
    .premium-title {
        font-family: 'Montserrat', sans-serif;
        font-size: 5.6rem;
        font-weight: 200;
        letter-spacing: 0.15em;
        text-transform: uppercase;
        color: #ffffff;
        line-height: 1;
        margin: 0;
    }
    .premium-subtitle {
        color: #71717a;
        font-size: 1.15rem;
        font-weight: 400;
        letter-spacing: 0.12em;
        margin-top: 10px;
        margin-bottom: 38px;
        text-transform: uppercase;
    }

    /* Minimalist Metrics Styling */
    [data-testid="stMetricValue"] {
        color: #ffffff !important; 
        font-size: 2.2rem !important;
        font-weight: 200 !important;
        font-family: 'Montserrat', sans-serif;
    }
    [data-testid="stMetricLabel"] {
        color: #a1a1aa !important;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        font-size: 0.8rem !important;
    }
    
    /* Luxury Glass Cards */
    .glass-card {
        background: rgba(24, 24, 27, 0.6);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 8px;
        padding: 24px;
        transition: transform 0.2s ease;
    }
    .glass-card:hover {
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    
    /* Clean Divider */
    hr {
        border-color: #27272a !important;
    }
    </style>
""", unsafe_allow_html=True)


# --- HELPER: LOGO LOADER ---
@st.cache_data
def get_logo_data_uri() -> str:
    candidates = [
        os.path.join(os.path.dirname(__file__) if "__file__" in globals() else ".", "dynamo_logo.png"),
        "dynamo_logo.png",
        r"C:\Users\VYSHAK\Documents\2 hack\dynamo_logo.png",
        r"C:\Users\VYSHAK\.gemini\antigravity\brain\9d0d06c7-3d96-4b37-878e-1b89b735d11e\dynamo_logo_transparent.png",
        "dynamo_logo_original.jpg"
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    ext = "png" if path.lower().endswith(".png") else "jpeg"
                    return f"data:image/{ext};base64,{base64.b64encode(f.read()).decode()}"
            except Exception:
                pass
    return ""

STATE_FILE = "live_sync_state.json"
CRITICAL_TEMP_LIMIT = 45.0  # Safe threshold limit

# --- HELPER: SAFE TWO-WAY SYNC ---
def load_state() -> dict:
    default_state = {
        "ride_type": "No — Normal Ride",
        "departure_hours": 1.5,
        "current_soc": 25,
        "temp_mode": "Manual Backend Slider",
        "manual_temp_c": 32.0,
        "grid_mode": "Auto (Live Cloud API)",
        "battery_capacity_kwh": 40.0,
        "last_updated": datetime.now().strftime("%H:%M:%S")
    }
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                default_state.update(data)
                return default_state
        except Exception:
            return default_state
    return default_state

def update_state(updates: dict):
    state = load_state()
    state.update(updates)
    state["last_updated"] = datetime.now().strftime("%H:%M:%S")
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
    return state

# --- CLOUD API: LIVE BENGALURU WEATHER ---
@st.cache_data(ttl=60)
def get_live_bengaluru_weather() -> tuple:
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=12.9716&longitude=77.5946&current_weather=true"
        res = requests.get(url, timeout=4).json()
        return res["current_weather"]["temperature"], "Open-Meteo API (BLR)"
    except Exception:
        return 26.5, "Fallback Sensor (Offline)"

# --- CORE BACKEND ENGINE ---
def run_backend_controller(state: dict) -> tuple:
    ambient_temp, cloud_temp_source = get_live_bengaluru_weather()

    if state["temp_mode"] == "Auto (Fetch from Bengaluru Cloud Weather)":
        battery_temp = round(ambient_temp + 5.0, 1)
        temp_source = cloud_temp_source
    else:
        battery_temp = float(state["manual_temp_c"])
        temp_source = "Backend BMS Sensor"

    hour = datetime.now().hour
    grid_choice = state["grid_mode"]

    if grid_choice == "High (Peak Grid Stress)":
        grid_load, carbon_intensity = "HIGH (Peak Grid Stress)", 645
    elif grid_choice == "Low (Off-Peak Clean Grid)":
        grid_load, carbon_intensity = "LOW (Off-Peak Clean Grid)", 410
    else:
        if 6 <= hour < 10 or 18 <= hour < 22:
            grid_load, carbon_intensity = "HIGH (Peak Grid Stress)", 635
        elif 22 <= hour or hour < 6:
            grid_load, carbon_intensity = "LOW (Off-Peak Clean Grid)", 415
        else:
            grid_load, carbon_intensity = "NORMAL (Balanced Grid)", 520

    rapid_kw = 22.0 if battery_temp > 40.0 else 50.0
    all_modes = {
        "Rapid Charging (DC Fast)": {"kw": rapid_kw, "rate": 13.50, "window": "< 2 Hours"},
        "Normal AC Charging": {"kw": 7.4, "rate": 7.50, "window": "2 to 6 Hours"},
        "Overnight Smart Charging": {"kw": 3.3, "rate": 6.00, "window": "> 6 Hours"}
    }

    dep_hrs = float(state["departure_hours"])
    is_emergency = (state["ride_type"] == "Yes — Emergency (Throttle Fast Charge)")
    is_high_grid = (grid_load == "HIGH (Peak Grid Stress)")
    
    alert_banner = None
    is_suspended = False

    # --- 1. CRITICAL SAFETY OVERRIDE ---
    if battery_temp >= CRITICAL_TEMP_LIMIT:
        selected_mode = "CHARGING SUSPENDED"
        color = "red"
        alert_banner = f"🛑 CRITICAL SAFETY ALERT: Battery temperature reached {battery_temp}°C. Power disconnected to prevent thermal runaway."
        reason = "Safety limit exceeded (>45°C). Cooling protocol active."
        charger_kw = 0.0
        bescom_rate = 0.0
        is_suspended = True

    # --- 2. NORMAL LOGIC ---
    elif is_emergency:
        selected_mode = "Rapid Charging (DC Fast)"
        color = "white"
        if battery_temp > 40.0:
            reason = f"🚨 Emergency Ride: Power throttled to 22 kW due to elevated temp ({battery_temp}°C)."
        else:
            reason = "🚨 Emergency Override: 50 kW Rapid Charging activated."

    elif dep_hrs < 2.0:
        if is_high_grid:
            selected_mode = "Normal AC Charging"
            color = "orange"
            alert_banner = "⚠️ GRID PROTECTION: Switched to 7.4 kW AC to prevent grid overload."
            reason = f"Peak Grid Stress detected ({carbon_intensity} gCO2/kWh). Fast charging disabled."
        elif battery_temp > 40.0:
            selected_mode = "Normal AC Charging"
            color = "orange"
            alert_banner = f"🔥 THERMAL PROTECTION: Battery at {battery_temp}°C. Switched to 7.4 kW AC."
            reason = f"Thermal Protection Active. High-speed DC disabled."
        else:
            selected_mode = "Rapid Charging (DC Fast)"
            color = "white"
            reason = f"Optimal conditions met. Fast charging safely engaged."

    elif 2.0 <= dep_hrs <= 6.0:
        selected_mode = "Normal AC Charging"
        color = "white"
        reason = f"Mid-range departure ({dep_hrs} hrs). Assigned steady 7.4 kW AC Charging."

    else:
        selected_mode = "Overnight Smart Charging"
        color = "white"
        reason = f"Extended dwell time ({dep_hrs} hrs). Assigned 3.3 kW off-peak Smart Charging."

    if not is_suspended:
        charger_kw = all_modes[selected_mode]["kw"]
        bescom_rate = all_modes[selected_mode]["rate"]

    cap = float(state["battery_capacity_kwh"])
    soc = int(state["current_soc"])

    kwh_needed = ((100.0 - soc) / 100.0) * cap
    kwh_possible = charger_kw * dep_hrs
    actual_kwh_added = round(min(kwh_needed, kwh_possible), 2)

    percent_added = round((actual_kwh_added / cap) * 100.0, 1)
    final_battery_percent = round(min(100.0, soc + percent_added), 1)
    total_cost_inr = round(actual_kwh_added * bescom_rate, 2)

    unified_json = {
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ev_telemetry": {
            "soc": soc,
            "temp_c": battery_temp,
            "status": "SUSPENDED" if is_suspended else "CHARGING"
        },
        "controller_decision": {
            "mode": selected_mode,
            "power_kw": charger_kw,
            "target_soc": final_battery_percent
        }
    }

    results = {
        "selected_mode": selected_mode,
        "color": color,
        "reason": reason,
        "alert_banner": alert_banner,
        "charger_kw": charger_kw,
        "bescom_rate": bescom_rate,
        "percent_added": percent_added,
        "final_battery_percent": final_battery_percent,
        "total_cost_inr": total_cost_inr,
        "all_modes": all_modes,
        "is_suspended": is_suspended
    }

    return unified_json, results

# --- SIDEBAR UI ---
with st.sidebar:
    st.markdown("### SYSTEM CONTROL")
    laptop_role = st.radio(
        "Active Terminal:",
        options=[
            "Vehicle Interface",
            "Backend Simulator"
        ],
        key="active_terminal",
        label_visibility="collapsed"
    )
    st.divider()
    state = load_state()
    st.caption(f"SYNC: {state['last_updated']}")

# ==============================================================================
# TERMINAL 1: VEHICLE INTERFACE (LUXURY VIEW)
# ==============================================================================
if laptop_role == "Vehicle Interface":
    logo_uri = get_logo_data_uri()
    logo_tag = f'<img src="{logo_uri}" class="brand-logo" alt="Dynamo Logo" />' if logo_uri else ''
    st.markdown(f'''
    <div class="brand-container">
        {logo_tag}
        <span class="premium-title">DYNAMO CHARZZ</span>
    </div>
    <p class="premium-subtitle">Intelligent Charging Architecture</p>
    ''', unsafe_allow_html=True)
    
    with st.container(border=False):
        st.markdown("#### TRIP PARAMETERS")
        u_col1, u_col2 = st.columns(2)
        with u_col1:
            dep_input = st.number_input("Departure Time (Hours)", min_value=0.5, max_value=24.0, value=float(state["departure_hours"]), step=0.5)
        with u_col2:
            ride_options = ["No — Normal Ride", "Yes — Emergency (Throttle Fast Charge)"]
            ride_input = st.radio("Override Settings", options=ride_options, index=ride_options.index(state["ride_type"]) if state["ride_type"] in ride_options else 0)

    if dep_input != state["departure_hours"] or ride_input != state["ride_type"]:
        state = update_state({"departure_hours": dep_input, "ride_type": ride_input})

    unified_json, res = run_backend_controller(state)
    ev = unified_json["ev_telemetry"]

    st.divider()

    if res["alert_banner"]:
        if res["is_suspended"]:
            st.error(res["alert_banner"], icon="🚨")
        else:
            st.warning(res["alert_banner"], icon="⚠️")

    # Live Telemetry - Clean row
    m_cols = st.columns(5)
    with m_cols[0]: st.metric("Battery Level", f"{ev['soc']}%")
    with m_cols[1]: st.metric("Cell Temp", f"{ev['temp_c']} °C")
    with m_cols[2]: st.metric("Output", f"{res['charger_kw']} kW")
    with m_cols[3]: st.metric("Target Level", f"{res['final_battery_percent']}%")
    with m_cols[4]: st.metric("Est. Cost", f"₹{res['total_cost_inr']}")

    st.markdown("<br>", unsafe_allow_html=True)

    # Active State display
    if res["is_suspended"]:
        st.markdown(f"""
        <div style="border: 1px solid #ef4444; background: rgba(239, 68, 68, 0.1); padding: 25px; border-radius: 8px;">
            <h3 style="color: #ef4444; margin-top:0; font-weight: 600; letter-spacing: 0.1em;">{res['selected_mode']}</h3>
            <p style="color: #fca5a5; font-size: 1.1rem;">{res['reason']}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="border: 1px solid #ffffff; background: rgba(255, 255, 255, 0.05); padding: 25px; border-radius: 8px;">
            <h3 style="color: #ffffff; margin-top:0; font-weight: 600; letter-spacing: 0.1em;">ACTIVE: {res['selected_mode']}</h3>
            <p style="color: #a1a1aa; font-size: 1.1rem;">{res['reason']}</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br><br>", unsafe_allow_html=True)

    # Modes Comparison View (Sleek cards)
    if not res["is_suspended"]:
        st.markdown("#### CHARGING TIERS")
        mode_cols = st.columns(3)
        for idx, (m_name, m_info) in enumerate(res["all_modes"].items()):
            is_sel = (m_name == res["selected_mode"])
            border_color = "#ffffff" if is_sel else "#27272a"
            text_color = "#ffffff" if is_sel else "#a1a1aa"
            
            cap = float(state["battery_capacity_kwh"])
            kwh_need = ((100.0 - ev["soc"]) / 100.0) * cap
            kwh_add = round(min(kwh_need, m_info["kw"] * state["departure_hours"]), 2)
            final_pct = round(min(100.0, ev["soc"] + (kwh_add / cap) * 100.0), 1)
            est_cost = round(kwh_add * m_info["rate"], 2)

            with mode_cols[idx]:
                st.markdown(f"""
                <div class="glass-card" style="border-color: {border_color};">
                    <h4 style="margin-top:0; color: {text_color}; font-weight: 400; letter-spacing: 0.05em;">{m_name}</h4>
                    <hr>
                    <p style="color: {text_color};"><b>Power:</b> {m_info['kw']} kW</p>
                    <p style="color: {text_color};"><b>Target SOC:</b> {final_pct}%</p>
                    <p style="color: {text_color};"><b>Est. Cost:</b> ₹{est_cost}</p>
                </div>
                """, unsafe_allow_html=True)

    time.sleep(2)
    st.rerun()

# ==============================================================================
# TERMINAL 2: BACKEND SIMULATOR
# ==============================================================================
else:
    st.markdown('<p class="premium-title" style="font-size: 3rem;">SYSTEM ARCHITECTURE</p>', unsafe_allow_html=True)
    st.markdown('<p class="premium-subtitle">Diagnostic & Emulation Terminal</p>', unsafe_allow_html=True)
    
    col_b1, col_b2 = st.columns(2)

    with col_b1:
        with st.container(border=True):
            st.markdown("#### VEHICLE TELEMETRY")
            soc_slider = st.slider("Current Battery (%)", 5, 95, int(state["current_soc"]), 5)
            
            temp_mode_options = ["Manual Backend Slider", "Auto (Fetch from Bengaluru Cloud Weather)"]
            temp_mode_input = st.radio("Temp Source", options=temp_mode_options, index=temp_mode_options.index(state["temp_mode"]) if state["temp_mode"] in temp_mode_options else 0)
            
            st.caption(f"🚨 Push temp to {CRITICAL_TEMP_LIMIT}°C+ to trigger Safety Kill-Switch.")
            temp_slider = st.slider("Manual Temp (°C)", 15.0, 55.0, float(state["manual_temp_c"]), 0.5, disabled=(temp_mode_input != "Manual Backend Slider"))

    with col_b2:
        with st.container(border=True):
            st.markdown("#### GRID LOAD")
            grid_options = ["Auto (Live Cloud API)", "Low (Off-Peak Clean Grid)", "High (Peak Grid Stress)"]
            grid_input = st.selectbox("Grid Condition", options=grid_options, index=grid_options.index(state["grid_mode"]) if state["grid_mode"] in grid_options else 0)
            
            vehicle_options = [40.0, 4.0]
            cap_input = st.selectbox(
                "Vehicle Platform",
                options=vehicle_options,
                format_func=lambda x: "40 kWh (Car Platform)" if x == 40.0 else "4 kWh (Scooter Platform)",
                index=vehicle_options.index(float(state["battery_capacity_kwh"])) if float(state["battery_capacity_kwh"]) in vehicle_options else 0
            )

    if (soc_slider != state["current_soc"] or temp_mode_input != state["temp_mode"] or temp_slider != state["manual_temp_c"] or grid_input != state["grid_mode"] or cap_input != state["battery_capacity_kwh"]):
        state = update_state({
            "current_soc": soc_slider,
            "temp_mode": temp_mode_input,
            "manual_temp_c": temp_slider,
            "grid_mode": grid_input,
            "battery_capacity_kwh": cap_input
        })

    unified_json, res = run_backend_controller(state)

    if res["is_suspended"]:
        st.error(f"⚠️ SIGNAL: Thermal Runaway Prevented -> **{res['selected_mode']}**")
    else:
        st.success(f"📡 SIGNAL BROADCASTED -> **{res['selected_mode']}**")
    
    with st.expander("📦 Raw JSON Payload (BMS Link)", expanded=True):
        st.json(unified_json)

    time.sleep(2)
    st.rerun()