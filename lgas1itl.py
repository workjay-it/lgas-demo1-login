import streamlit as st
import pandas as pd
import pytz
import time
from datetime import datetime
from st_supabase_connection import SupabaseConnection

#-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# --- 1. INITIALIZE & DB CONNECTION ---
if "last_refresh" not in st.session_state:
    st.session_state["last_refresh"] = "Initializing..."

conn = st.connection("supabase", type=SupabaseConnection)

@st.cache_data(ttl=60)
def load_supabase_data():
    try:
        # Fetching from the LIVE table for the main dashboard
        response = conn.table("cylinders").select("*").execute()
        df_raw = pd.DataFrame(response.data)
        
        # --- TIMEZONE & DATE CLEANING ---
        ist = pytz.timezone('Asia/Kolkata')
        st.session_state["last_refresh"] = datetime.now(ist).strftime("%I:%M:%S %p")
        
        if not df_raw.empty:
            if "Location_PIN" in df_raw.columns:
                df_raw["Location_PIN"] = df_raw["Location_PIN"].astype(str).str.strip()
            
            date_cols = ["Last_Fill_Date", "Last_Test_Date", "Next_Test_Due"]
            for col in date_cols:
                if col in df_raw.columns:
                    df_raw[col] = pd.to_datetime(df_raw[col], errors='coerce')
        
        return df_raw
    except Exception as e:
        st.session_state["last_refresh"] = "Refresh Error"
        st.error(f"Database Connection Error: {e}")
        return pd.DataFrame()

# Load the base data
df_main = load_supabase_data()

#-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# --- 2. SIDEBAR GLOBAL FILTERS ---
st.sidebar.header("📊 Global Filters")

# Display the last refresh time (useful for debugging connectivity)
st.sidebar.caption(f"Last Sync: {st.session_state['last_refresh']}")

# TEMPORARY: We define 'df' as the full dataset to bypass the Batch_ID KeyError
# This ensures Dashboard, Finder, and Inventory pages still have data to show.
df = df_main.copy()

# Add a simple status message so you know the filter is off
st.sidebar.info(f"Total Fleet: {len(df)} units")
st.sidebar.warning("Category Filter: Temporarily Disabled")


#-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# --- 3. SIDEBAR NAVIGATION (CRITICAL FIX) ---
# This defines the 'page' variable so you don't get a NameError
page = st.sidebar.selectbox(
    "Menu", 
    [
        "Dashboard", 
        "Cylinder Finder", 
        "Bulk Operations", 
        "Return & Penalty Log", 
        "Add New Cylinder"
    ]
)

#-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# 3. DASHBOARD PAGE
if page == "Dashboard":
    st.title("Live Fleet Dashboard")
    
    if not df.empty:
        # 1. Setup Dates
        ist = pytz.timezone('Asia/Kolkata')
        today = datetime.now(ist).date()

        # 2. Metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Units", len(df))
        overdue_count = len(df[df["Next_Test_Due"].dt.date <= today])
        col2.metric("Overdue (Test)", overdue_count)
        col3.metric("Empty Stock", len(df[df["Status"] == "Empty"]))

        # 3. Style Function (Dark Grey / Near Black)
        def highlight_overdue(row):
            # Hex #1E1E1E is a soft "Onyx" grey close to black
            if row["Next_Test_Due"].date() <= today:
                return ['background-color: #303030; color: white; font-weight: italic'] * len(row)
            return [''] * len(row)

        styled_df = df.style.apply(highlight_overdue, axis=1)

        st.subheader("Inventory Overview")
        
        # 4. Display with Hidden Index
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
        
        # 5. Footer Note
        st.caption("**Grey Rows indicate cylinders that have exceeded their safety test date.")
    else:
        st.warning("No data found.")
        
#-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------


# 4. CYLINDER FINDER (Hardware Scanner Friendly)
elif page == "Cylinder Finder":
    st.title("Advanced Cylinder Search")

    # 1. DEFINE THE CALLBACK
    def clear_callback():
        st.session_state["s_id_key"] = ""
        st.session_state["s_name_key"] = ""

    # 2. Initialize keys safely
    if "s_id_key" not in st.session_state:
        st.session_state["s_id_key"] = ""
    if "s_name_key" not in st.session_state:
        st.session_state["s_name_key"] = ""

    # 3. Search Inputs with Vertical Alignment
    colA, colB, colC, colD = st.columns([3, 3, 2, 1], vertical_alignment="bottom")
    
    with colA:
        s_id = st.text_input("Search ID (Scan Now)", key="s_id_key").strip().upper()
    with colB:
        s_name = st.text_input("Search Customer", key="s_name_key").strip()
    with colC:
        s_status = st.selectbox("Filter Status", ["All", "Full", "Empty", "Damaged"])
    with colD:
        # The button will now sit perfectly level with the input fields
        st.button("Reset", on_click=clear_callback, use_container_width=True)

    # 4. Date Setup
    ist = pytz.timezone('Asia/Kolkata')
    today = datetime.now(ist).date()

    # 5. Filtering Logic
    f_df = df.copy()
    if s_id:
        f_df = f_df[f_df["Cylinder_ID"].str.upper().str.contains(s_id, na=False)]
    if s_name:
        f_df = f_df[f_df["Customer_Name"].str.contains(s_name, case=False, na=False)]
    if s_status != "All":
        f_df = f_df[f_df["Status"] == s_status]

    # 6. Alert Logic (Only for ID or Name search)
    if s_id or s_name:
        if not f_df.empty:
            overdue_list = f_df[f_df["Next_Test_Due"].dt.date <= today]
            num_overdue = len(overdue_list)
            if num_overdue > 0:
                if s_id and num_overdue == 1:
                    due_date = overdue_list.iloc[0]["Next_Test_Due"].date()
                    st.error(f"⚠️ SAFETY ALERT: Cylinder {s_id} is OVERDUE! (Due: {due_date})")
                else:
                    st.error(f"⚠️ ATTENTION: Found {num_overdue} overdue cylinder(s) for your search.")
            else:
                st.success(f"✅ No overdue cylinders found for this search.")
        else:
            st.warning("No matching cylinders found.")

    # 7. Apply Dark-Grey Styling
    def highlight_overdue(row):
        if row["Next_Test_Due"].date() <= today:
            return ['background-color: #1E1E1E; color: #E0E0E0; font-weight: bold'] * len(row)
        return [''] * len(row)

    styled_f_df = f_df.style.apply(highlight_overdue, axis=1)

    st.subheader(f"Results Found: {len(f_df)}")
    st.dataframe(styled_f_df, use_container_width=True, hide_index=True)

#-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# --- 5. BULK OPERATIONS  ---
elif page == "Bulk Operations":
    st.title("🚛 Bulk Management & Progress")
    
    # 🧪 CONFIGURATION
    TARGET_TABLE = "TEST_cylinders" 
    st.warning(f"CURRENTLY TESTING ON: `{TARGET_TABLE}`")

    # Initialize session state for automation
    if "bulk_ids_val" not in st.session_state:
        st.session_state.bulk_ids_val = ""
    if "batch_search_val" not in st.session_state:
        st.session_state.batch_search_val = ""

    # 1. BATCH LOOKUP SECTION
    with st.container(border=True):
        col_id, col_btn = st.columns([3, 1])
        with col_id:
            batch_lookup = st.text_input(
                "Track Batch Number", 
                value=st.session_state.batch_search_val,
                placeholder="e.g., BATCH001",
                key="batch_lookup_input"
            )
        
        batch_data = pd.DataFrame()
        if batch_lookup:
            res = conn.table(TARGET_TABLE).select("*").eq("Batch_ID", batch_lookup).execute()
            batch_data = pd.DataFrame(res.data)
            
            if not batch_data.empty:
                with col_btn:
                    st.write("") 
                    if st.button("Retrieve info", use_container_width=True):
                        # Filter to only pull IDs that aren't 'Full' yet (The remaining units)
                        remaining = batch_data[batch_data["Status"] != "Full"]
                        ids_to_pull = remaining["Cylinder_ID"].astype(str).tolist() if not remaining.empty else batch_data["Cylinder_ID"].astype(str).tolist()
                        
                        # --- THE AUTOMATION FIX: Explicitly set session state keys ---
                        st.session_state.bulk_ids_val = "\n".join(ids_to_pull)
                        st.session_state.batch_search_val = batch_lookup
                        st.session_state["confirm_batch"] = batch_lookup # Auto-fills Confirm Batch ID box
                        
                        st.rerun()
            else:
                st.info("No data found for this Batch ID.")

    st.divider()

    # 2. THE BULK UPDATE FORM
    with st.expander("📝 Bulk Update Form", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            # We use the 'key' to allow "Pull IDs" to fill this box automatically
            target_batch = st.text_input("Confirm Batch ID", key="confirm_batch")
            dest = st.selectbox("New Location", ["Testing Center", "Gas Company"], key="dest_select")
        with c2:
            new_status = st.selectbox("New Status", ["No Change", "Empty", "Full", "Damaged"], key="status_select")
            new_owner = st.text_input("Update Customer/Owner", key="owner_input")

        bulk_input = st.text_area("Cylinder IDs to Update", value=st.session_state.bulk_ids_val, height=200)

        # --- Button Actions ---
        st.write("---")
        col_process, col_clear = st.columns([3, 1])
        
        with col_process:
            if st.button("🚀 Process Bulk Update", use_container_width=True, type="primary"):
                if bulk_input and target_batch:
                    id_list = [i.strip().upper() for i in bulk_input.replace(',', '\n').split('\n') if i.strip()]
                    payload = {"Batch_ID": target_batch, "Current_Location": dest}
                    if new_status != "No Change":
                        payload["Status"] = new_status
                    if new_owner:
                        payload["Customer_Name"] = new_owner

                    try:
                        conn.table(TARGET_TABLE).update(payload).in_("Cylinder_ID", id_list).execute()
                        st.success(f"✅ Successfully updated {len(id_list)} cylinders!")
                        st.balloons()
                        st.cache_data.clear() # Refresh progress bar data
                    except Exception as e:
                        st.error(f"Update failed: {e}")
                else:
                    st.error("Please provide both a Batch ID and Cylinder IDs.")

        with col_clear:
            with st.popover("🧹 Reset Form", use_container_width=True):
                st.error("This will clear ALL fields. Are you sure?")
                if st.button("Confirm Master Reset", type="primary", use_container_width=True):
                    # Clear session states
                    st.session_state.bulk_ids_val = ""
                    st.session_state.batch_search_val = ""
                    # Delete widget keys to reset to defaults
                    for key in ["batch_lookup_input", "confirm_batch", "dest_select", "status_select", "owner_input"]:
                        if key in st.session_state: del st.session_state[key]
                    st.rerun()

    # 3. BATCH RECONCILIATION SECTION (At the bottom)
    if not batch_data.empty:
        st.divider()
        st.subheader("🚩 Batch Reconciliation Status")
        
        total = len(batch_data)
        completed = len(batch_data[batch_data["Status"] == "Full"])
        prog = completed / total
        
        st.write(f"**Overall Progress:** {completed} of {total} units ({(prog*100):.1f}%)")
        st.progress(prog)

        # Breakdown Metrics
        remaining_df = batch_data[batch_data["Status"] != "Full"]
        m1, m2, m3 = st.columns(3)
        m1.metric("Processed (Full)", completed)
        m2.metric("In Testing (Empty)", len(remaining_df[remaining_df["Status"] == "Empty"]))
        m3.metric("Damaged/Rejected", len(remaining_df[remaining_df["Status"] == "Damaged"]))
        
        if not remaining_df.empty:
            with st.expander(f"View IDs of the {len(remaining_df)} Pending Units"):
                st.dataframe(remaining_df[["Cylinder_ID", "Status", "Current_Location"]], 
                             use_container_width=True, hide_index=True)
        else:
            st.success("✅ Batch Reconciliation Complete: All cylinders accounted for.")
            
#-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# 5. RETURN & PENALTY LOG
elif page == "Return & Penalty Log":
    st.title("Cylinder Return Audit")
    if not df.empty:
        # You can also scan into a selectbox if the ID matches exactly
        target_id = st.selectbox("Select ID for Return", options=df["Cylinder_ID"].unique())
        with st.form("audit_form"):
            condition = st.selectbox("Condition", ["Good", "Dented", "Leaking", "Valve Damage"])
            if st.form_submit_button("Submit Return"):
                new_status = "Empty" if condition == "Good" else "Damaged"
                try:
                    conn.table("cylinders").update({"Status": new_status, "Fill_Percent": 0}).eq("Cylinder_ID", target_id).execute()
                    st.success(f"Cylinder {target_id} processed!")
                    time.sleep(2)
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Update failed: {e}")

#-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# 6. ADD NEW CYLINDER (Hardware Scanner Friendly)
elif page == "Add New Cylinder":
    st.title("Register New Cylinder")
    
    # clear_on_submit=True is critical for scanners so you don't have to delete the old ID manually
    with st.form("new_entry_form", clear_on_submit=True):
        st.write("Scan the cylinder barcode to auto-fill ID.")
        c_id = st.text_input("New Cylinder ID").strip().upper()
        
        cust = st.text_input("Customer Name", value="Internal Stock")
        pin = st.text_input("Location PIN", value="500001", max_chars=6)
        
        cap_val = st.selectbox("Capacity (kg)", options=[5.0, 10.0, 14.2, 19.0, 47.5], index=2)
        
        if st.form_submit_button("Add Cylinder"):
            if not c_id:
                st.error("Missing Cylinder ID!")
            else:
                today = datetime.now().date()
                payload = {
                    "Cylinder_ID": str(c_id),
                    "Customer_Name": str(cust),
                    "Location_PIN": int(pin) if pin.isdigit() else 0,
                    "Capacity_kg": float(cap_val),
                    "Fill_Percent": 100,
                    "Status": "Full",
                    "Last_Fill_Date": str(today),
                    "Last_Test_Date": str(today),
                    "Next_Test_Due": str(today + pd.Timedelta(days=1825)),
                    "Overdue": False
                }
                try:
                    conn.table("cylinders").insert(payload).execute()
                    st.success(f"Cylinder {c_id} added successfully!")
                    time.sleep(2)
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Database Error: {e}")
                    
#-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# 7. FOOTER #JCNaga
st.markdown("---")
last_time = st.session_state["last_refresh"]
footer_text = f"""
<div style="text-align: center; color: grey; font-size: 0.85em; font-family: sans-serif;">
    <p><b> Developed for </b> KWS Pvt Ltd </p>
    <p style="color: #007bff;"><b>Last Refresh:</b> {last_time} IST</p>
    <p> Cylinder Management System v1.2</p>
</div>
"""
st.markdown(footer_text, unsafe_allow_html=True)































































