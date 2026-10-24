import streamlit as st
import requests
import json
import os
import time
from datetime import datetime, timezone

st.set_page_config(page_title="BESCOM Dynamic EV Charger", page_icon="⚡", layout="wide")

STATE_FILE = "live_sync_state.json"

# --- HELPER: SAFE TWO-WAY SYNC BETWEEN USER LAPTOP & BACKEND LAPTOP ---
def load_state() -> dict:
    default_state = {
        # Controlled by Laptop 1 (User)
        "ride_type": "No — Normal Ride",
        "departure_hours": 1.5,
        # Controlled by Laptop 2 (Backend)
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
        return res["current_weather"]["temperature"], "Open-Meteo Live Cloud API (Bengaluru)"
    except Exception:
        return 26.5, "Fallback Cloud Sensor (Offline)"

# --- CORE BACKEND ENGINE ---
def run_backend_controller(state: dict) -> tuple:
    ambient_temp, cloud_temp_source = get_live_bengaluru_weather()

    # 1. Battery Temperature (From Backend Slider or Live Cloud Weather)
    if state["temp_mode"] == "Auto (Fetch from Bengaluru Cloud Weather)":
        battery_temp = round(ambient_temp + 5.0, 1)
        temp_source = cloud_temp_source
    else:
        battery_temp = float(state["manual_temp_c"])
        temp_source = "Backend BMS Temperature Sensor"

    # 2. Grid Condition (Auto Cloud vs Low vs High)
    hour = datetime.now().hour
    grid_choice = state["grid_mode"]

    if grid_choice == "High (Peak Grid Stress)":
        grid_load = "HIGH (Peak Grid Stress)"
        carbon_intensity = 645
    elif grid_choice == "Low (Off-Peak Clean Grid)":
        grid_load = "LOW (Off-Peak Clean Grid)"
        carbon_intensity = 410
    else:
        # Auto Cloud Fetch based on BESCOM Time-of-Day
        if 6 <= hour < 10 or 18 <= hour < 22:
            grid_load = "HIGH (Peak Grid Stress)"
            carbon_intensity = 635
        elif 22 <= hour or hour < 6:
            grid_load = "LOW (Off-Peak Clean Grid)"
            carbon_intensity = 415
        else:
            grid_load = "NORMAL (Balanced Grid)"
            carbon_intensity = 520

    # 3. Charging Modes & BESCOM Tariff Definitions
    rapid_kw = 22.0 if battery_temp > 40.0 else 50.0
    all_modes = {
        "Rapid Charging (DC Fast)": {"kw": rapid_kw, "rate": 13.50, "window": "< 2 Hours (Low/Normal Grid) or Emergency"},
        "Normal AC Charging": {"kw": 7.4, "rate": 7.50, "window": "2 to 6 Hours (or High Grid / Temp Fallback)"},
        "Overnight Smart Charging": {"kw": 3.3, "rate": 6.00, "window": "> 6 Hours (Off-Peak Smart Shift)"}
    }

    dep_hrs = float(state["departure_hours"])
    is_emergency = (state["ride_type"] == "Yes — Emergency (Throttle Fast Charge)")
    is_high_grid = (grid_load == "HIGH (Peak Grid Stress)")
    alert_banner = None

    # 4. Mode Assignment Logic
    if is_emergency:
        selected_mode = "Rapid Charging (DC Fast)"
        color = "red"
        if battery_temp > 40.0:
            reason = f"🚨 Emergency Ride requested, but battery temp is hot ({battery_temp}°C). Power safely throttled from 50 kW to 22 kW."
        else:
            reason = f"🚨 Emergency Ride Active: Overriding grid conditions to deliver full 50 kW Rapid Charging."

    elif dep_hrs < 2.0:
        if is_high_grid:
            selected_mode = "Normal AC Charging"
            color = "orange"
            alert_banner = (
                "⚠️ PEAK GRID PROTECTION: Departure is under 2 hours, but BESCOM Grid Stress is HIGH. "
                "Switched from Rapid Charging to Normal AC Charging (7.4 kW) to prevent grid overload!"
            )
            reason = f"Switched to Normal AC Charging due to HIGH Peak Grid Stress ({carbon_intensity} gCO2/kWh). Switch to 'Emergency' if immediate rapid charge is required."
        elif battery_temp > 40.0:
            selected_mode = "Normal AC Charging"
            color = "orange"
            alert_banner = (
                f"🔥 THERMAL PROTECTION ACTIVE: Battery temperature is high ({battery_temp}°C). "
                "Switched from Rapid Charging to Normal AC Charging (7.4 kW) to protect battery health!"
            )
            reason = f"Switched to Normal AC Charging because battery temperature ({battery_temp}°C) exceeds the 40°C safe limit for Rapid Charging."
        else:
            selected_mode = "Rapid Charging (DC Fast)"
            color = "red"
            reason = f"Departure is under 2 hours ({dep_hrs} hrs), grid stress is safe ({grid_load}), and battery temp ({battery_temp}°C) is normal."

    elif 2.0 <= dep_hrs <= 6.0:
        selected_mode = "Normal AC Charging"
        color = "orange"
        reason = f"Departure is between 2 and 6 hours ({dep_hrs} hrs). Assigned steady 7.4 kW Normal AC Charging at BESCOM rate ₹7.50/kWh."

    else:
        selected_mode = "Overnight Smart Charging"
        color = "green"
        reason = f"Departure is above 6 hours ({dep_hrs} hrs). Assigned 3.3 kW Overnight Smart Charging at BESCOM off-peak rate ₹6.00/kWh."

    # 5. Calculate Battery % Charged & BESCOM Cost
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
        "user_inputs_from_laptop_1": {
            "emergency_status": state["ride_type"],
            "hours_until_departure": dep_hrs
        },
        "ev_telemetry_from_backend": {
            "current_soc_percent": soc,
            "battery_temp_c": battery_temp,
            "temp_source": temp_source,
            "battery_capacity_kwh": cap,
            "charging_status": "PLUGGED_IN"
        },
        "grid_telemetry_from_cloud": {
            "zone": "IN-SO (Bengaluru / BESCOM)",
            "grid_condition": grid_load,
            "carbon_intensity_g_per_kwh": carbon_intensity
        },
        "controller_decision": {
            "selected_mode": selected_mode,
            "allocated_power_kw": charger_kw,
            "final_soc_at_departure_percent": final_battery_percent,
            "total_bescom_cost_inr": total_cost_inr
        }
    }

    results = {
        "selected_mode": selected_mode,
        "color": color,
        "reason": reason,
        "alert_banner": alert_banner,
        "charger_kw": charger_kw,
        "bescom_rate": bescom_rate,
        "actual_kwh_added": actual_kwh_added,
        "percent_added": percent_added,
        "final_battery_percent": final_battery_percent,
        "total_cost_inr": total_cost_inr,
        "all_modes": all_modes
    }

    return unified_json, results

# --- SIDEBAR: SELECT WHICH LAPTOP THIS IS ---
st.sidebar.header("💻 Select Laptop Screen")
laptop_role = st.sidebar.radio(
    "Choose role for this laptop:",
    options=[
        "🚗 Laptop 1: EV User Screen (Driver View)",
        "⚙️ Laptop 2: Backend Cloud & BMS Simulator"
    ]
)

state = load_state()

# ==============================================================================
# LAPTOP 1: WHAT THE EV CAR / BIKE USER SEES
# ==============================================================================
if laptop_role == "🚗 Laptop 1: EV User Screen (Driver View)":
    st.title("⚡ BESCOM Smart EV Charger — User Screen")
    st.caption(f"🟢 Live Connected to Vehicle BMS & BESCOM Cloud | Last Sync: {state['last_updated']}")

    # 1. ONLY TWO USER INPUTS
    st.subheader("1️⃣ Enter Your Trip Details")
    u_col1, u_col2 = st.columns(2)

    with u_col1:
        dep_input = st.number_input(
            "⏰ Hours Until Departure:",
            min_value=0.5, max_value=24.0,
            value=float(state["departure_hours"]),
            step=0.5
        )

    with u_col2:
        ride_options = ["No — Normal Ride", "Yes — Emergency (Throttle Fast Charge)"]
        ride_input = st.radio(
            "🚨 Is there an Emergency Ride?",
            options=ride_options,
            index=ride_options.index(state["ride_type"]) if state["ride_type"] in ride_options else 0
        )

    # Save immediately if user changed either input
    if dep_input != state["departure_hours"] or ride_input != state["ride_type"]:
        state = update_state({"departure_hours": dep_input, "ride_type": ride_input})

    # Run controller using backend values from Laptop 2
    unified_json, res = run_backend_controller(state)
    ev = unified_json["ev_telemetry_from_backend"]
    grid = unified_json["grid_telemetry_from_cloud"]

    st.divider()

    # Show Alert Banner if Peak Grid or High Temp switched Rapid -> Normal
    if res["alert_banner"]:
        st.warning(res["alert_banner"])

    # 2. LIVE TELEMETRY & OUTPUT DISPLAY FOR THE USER
    st.subheader("2️⃣ Live Vehicle, Grid & Charging Status")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("🔋 Current Battery %", f"{ev['current_soc_percent']}%", "From Vehicle BMS")
    m2.metric("🌡️ Battery Temp", f"{ev['battery_temp_c']} °C", "Live Sensor")
    m3.metric("🌐 Grid Condition", grid["grid_condition"].split(" ")[0], grid["grid_condition"])
    m4.metric("⚡ Charged Before Leaving", f"{res['final_battery_percent']}%", f"+{res['percent_added']}% added")
    m5.metric("₹ Total BESCOM Cost", f"₹{res['total_cost_inr']}", f"₹{res['bescom_rate']}/kWh")

    st.markdown(f"### 🎯 Selected Mode: :{res['color']}[**{res['selected_mode']}**] (`{res['charger_kw']} kW`)")
    st.info(f"**Why this mode was selected:** {res['reason']}")

    st.write(f"**Battery Level Projection in {state['departure_hours']} Hours:** `{ev['current_soc_percent']}%` ➡️ **`{res['final_battery_percent']}%`**")
    st.progress(int(res["final_battery_percent"]))

    st.divider()

    # 3. SELECTED vs UNSELECTED MODES COMPARISON
    st.subheader("3️⃣ Charging Modes & BESCOM Cost Comparison")
    mode_cols = st.columns(3)
    for idx, (m_name, m_info) in enumerate(res["all_modes"].items()):
        is_sel = (m_name == res["selected_mode"])
        cap = float(state["battery_capacity_kwh"])
        kwh_need = ((100.0 - ev["current_soc_percent"]) / 100.0) * cap
        kwh_add = round(min(kwh_need, m_info["kw"] * state["departure_hours"]), 2)
        final_pct = round(min(100.0, ev["current_soc_percent"] + (kwh_add / cap) * 100.0), 1)
        est_cost = round(kwh_add * m_info["rate"], 2)

        with mode_cols[idx]:
            if is_sel:
                st.success(f"✅ **SELECTED: {m_name}**")
            else:
                st.warning(f"⚪ **UNSELECTED: {m_name}**")
            st.write(f"• **Speed:** `{m_info['kw']} kW`")
            st.write(f"• **BESCOM Rate:** `₹{m_info['rate']} / kWh`")
            st.write(f"• **Battery by Departure:** `{final_pct}%`")
            st.write(f"• **Estimated Cost:** `₹{est_cost}`")

    # Auto-refresh every 2 seconds so changes made on Laptop 2 (Backend) appear immediately on Laptop 1
    time.sleep(2)
    st.rerun()

# ==============================================================================
# LAPTOP 2: BACKEND CLOUD, GRID & BMS SIMULATOR
# ==============================================================================
else:
    st.title("⚙️ Backend Server — Cloud Grid & BMS Telemetry Simulator (Laptop 2)")
    st.caption(f"🟢 Sending Live Telemetry to User Screen (Laptop 1) | Last Sync: {state['last_updated']}")
    st.divider()

    col_b1, col_b2 = st.columns(2)

    with col_b1:
        st.subheader("🔋 1. Vehicle BMS Telemetry Controls")
        soc_slider = st.slider(
            "Current Battery Percentage (%):",
            min_value=5, max_value=95,
            value=int(state["current_soc"]),
            step=5
        )

        temp_mode_options = ["Manual Backend Slider", "Auto (Fetch from Bengaluru Cloud Weather)"]
        temp_mode_input = st.radio(
            "🌡️ Battery Temperature Source:",
            options=temp_mode_options,
            index=temp_mode_options.index(state["temp_mode"]) if state["temp_mode"] in temp_mode_options else 0
        )

        temp_slider = st.slider(
            "🌡️ Battery Temperature Slider (°C):",
            min_value=15.0, max_value=50.0,
            value=float(state["manual_temp_c"]),
            step=0.5,
            disabled=(temp_mode_input != "Manual Backend Slider"),
            help="Slide above 40°C to trigger Thermal Protection on the User Screen!"
        )

    with col_b2:
        st.subheader("🌐 2. BESCOM Cloud Grid Controls")
        grid_options = [
            "Auto (Live Cloud API)",
            "Low (Off-Peak Clean Grid)",
            "High (Peak Grid Stress)"
        ]
        grid_input = st.selectbox(
            "Select Grid Condition:",
            options=grid_options,
            index=grid_options.index(state["grid_mode"]) if state["grid_mode"] in grid_options else 0
        )

        vehicle_options = [40.0, 4.0]
        cap_input = st.selectbox(
            "🚗 Vehicle Battery Type:",
            options=vehicle_options,
            format_func=lambda x: "EV Car (40 kWh Battery)" if x == 40.0 else "EV Bike / Scooter (4 kWh Battery)",
            index=vehicle_options.index(float(state["battery_capacity_kwh"])) if float(state["battery_capacity_kwh"]) in vehicle_options else 0
        )

    # Save Backend Changes Immediately
    if (
        soc_slider != state["current_soc"]
        or temp_mode_input != state["temp_mode"]
        or temp_slider != state["manual_temp_c"]
        or grid_input != state["grid_mode"]
        or cap_input != state["battery_capacity_kwh"]
    ):
        state = update_state({
            "current_soc": soc_slider,
            "temp_mode": temp_mode_input,
            "manual_temp_c": temp_slider,
            "grid_mode": grid_input,
            "battery_capacity_kwh": cap_input
        })

    unified_json, res = run_backend_controller(state)

    st.success(f"📡 Broadcasting to User Screen -> Active Mode: **{res['selected_mode']}** | Final Charge: **{res['final_battery_percent']}%** | Cost: **₹{res['total_cost_inr']}**")

    st.subheader("📦 Live Unified JSON Schema (Backend Payload)")
    st.json(unified_json)

    # Auto-refresh every 2 seconds so user inputs from Laptop 1 update the JSON schema live
    time.sleep(2)
    st.rerun()