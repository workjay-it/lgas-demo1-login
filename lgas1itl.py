import streamlit as st
import pandas as pd
from datetime import datetime
from st_supabase_connection import SupabaseConnection

#------------------------------------------------------------------------------------------------------------------------------------------------------------

# --- 1. SETTINGS & CONNECTION ---
st.set_page_config(page_title="KWS LGAS Management", layout="wide")

# Connect using the credentials in your .streamlit/secrets.toml
conn = st.connection("supabase", type=SupabaseConnection)

# Initialize Session State
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "user_role" not in st.session_state:
    st.session_state["user_role"] = None
if "bulk_ids_val" not in st.session_state:
    st.session_state.bulk_ids_val = ""
if "batch_search_val" not in st.session_state:
    st.session_state.batch_search_val = ""

#------------------------------------------------------------------------------------------------------------------------------------------------------------

# --- 2. LOGIN PAGE ---
def login_page():
    st.title("🔐 KWS Cylinder Portal")
    with st.container(border=True):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Login", use_container_width=True, type="primary"):
            try:
                # Auth with Supabase
                auth_res = conn.auth.sign_in_with_password({"email": email, "password": password})
                user_id = auth_res.user.id
                
                # Fetch profile details (Role & Client Link)
                prof_res = conn.table("profiles").select("*").eq("id", user_id).single().execute()
                
                st.session_state["authenticated"] = True
                st.session_state["user_role"] = prof_res.data["role"]
                st.session_state["client_link"] = prof_res.data["client_link"]
                st.session_state["full_name"] = prof_res.data.get("full_name", "User")
                st.rerun()
            except Exception:
                st.error("Invalid credentials. Please contact the administrator.")

# Logout Function
def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# Gatekeeper: Stop execution if not logged in
if not st.session_state["authenticated"]:
    login_page()
    st.stop()

#------------------------------------------------------------------------------------------------------------------------------------------------------------

# --- 3. SIDEBAR NAVIGATION ---
role = st.session_state["user_role"]
st.sidebar.title(f"👋 {st.session_state['full_name']}")
st.sidebar.write(f"**Role:** {role.upper()}")

# Menu visibility based on Role
if role == "admin":
    menu = ["Dashboard", "Cylinder Finder", "Bulk Operations", "Inventory Management"]
elif role == "bulk_user":
    menu = ["Dashboard", "Cylinder Finder", "Bulk Operations"]
else: # private_user
    menu = ["Dashboard", "Cylinder Finder"]

page = st.sidebar.selectbox("Navigate", menu)
st.sidebar.divider()
if st.sidebar.button("Logout", use_container_width=True):
    logout()

#------------------------------------------------------------------------------------------------------------------------------------------------------------

# --- 4. DATA LOADING (Role-Filtered) ---
@st.cache_data(ttl=60)
def load_cylinders():
    query = conn.table("cylinders").select("*")
    # If not admin, only show data belonging to their client_link
    if role != "admin":
        query = query.eq("Customer_Name", st.session_state["client_link"])
    
    res = query.execute()
    return pd.DataFrame(res.data)

df_main = load_cylinders()

# --- 5. PAGE LOGIC: DASHBOARD ---
if page == "Dashboard":
    st.title("📊 Fleet Overview")
    if not df_main.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Cylinders", len(df_main))
        col2.metric("In Testing (Empty)", len(df_main[df_main["Status"] == "Empty"]))
        
        # Check if 'Overdue' column exists before metric
        if "Overdue" in df_main.columns:
            col3.metric("Overdue Units", len(df_main[df_main["Overdue"] == True]))
        
        st.subheader("Inventory Preview")
        st.dataframe(df_main, use_container_width=True, hide_index=True)
    else:
        st.info("No cylinders found for your account.")

#------------------------------------------------------------------------------------------------------------------------------------------------------------

# --- 6. PAGE LOGIC: BULK OPERATIONS ---
elif page == "Bulk Operations":
    st.title("🚛 Bulk Management & Reconciliation")
    TARGET_TABLE = "TEST_cylinders" 
    
    # 1. BATCH LOOKUP SECTION
    with st.container(border=True):
        c_id, c_btn = st.columns([3, 1])
        batch_lookup = c_id.text_input("Search Batch ID", value=st.session_state.batch_search_val, key="batch_search_input")
        
        batch_data = pd.DataFrame()
        if batch_lookup:
            query = conn.table(TARGET_TABLE).select("*").eq("Batch_ID", batch_lookup)
            # Security: bulk_users can only see their own batches
            if role != "admin":
                query = query.eq("Customer_Name", st.session_state["client_link"])
            
            res = query.execute()
            batch_data = pd.DataFrame(res.data)
            
            if not batch_data.empty:
                if c_btn.button("🔍 Pull Pending IDs"):
                    # Only pull IDs that are NOT 'Full'
                    remaining = batch_data[batch_data["Status"] != "Full"]
                    ids = remaining["Cylinder_ID"].astype(str).tolist() if not remaining.empty else batch_data["Cylinder_ID"].astype(str).tolist()
                    st.session_state.bulk_ids_val = "\n".join(ids)
                    st.session_state.batch_search_val = batch_lookup
                    st.session_state["confirm_batch"] = batch_lookup
                    st.rerun()
            else:
                st.info("No data found for this Batch ID.")

    st.divider()

     
    # 2. UPDATE FORM
    with st.expander("📝 Process Updates", expanded=True):
        f1, f2 = st.columns(2)
        with f1:
            t_batch = st.text_input("Confirm Batch ID", key="confirm_batch")
            new_loc = st.selectbox("New Location", ["Testing Center", "Gas Company"])
        with f2:
            new_stat = st.selectbox("Update Status", ["No Change", "Empty", "Full", "Damaged"])
            # Auto-fill owner for clients, allow entry for admins
            default_owner = st.session_state["client_link"] if role != "admin" else ""
            new_owner = st.text_input("Owner Name", value=default_owner)

        bulk_ids = st.text_area("Cylinder IDs (One per line)", value=st.session_state.bulk_ids_val, height=150)

        if st.button("🚀 Execute Bulk Update", type="primary", use_container_width=True):
            if bulk_ids:
                id_list = [i.strip().upper() for i in bulk_ids.replace(',', '\n').split('\n') if i.strip()]
                
                # Prepare payload
                payload = {"Current_Location": new_loc}
                if t_batch: payload["Batch_ID"] = t_batch
                if new_stat != "No Change": payload["Status"] = new_stat
                if new_owner: payload["Customer_Name"] = new_owner

                try:
                    # Update based on Cylinder_ID primary key
                    conn.table(TARGET_TABLE).update(payload).in_("Cylinder_ID", id_list).execute()
                    st.success(f"Successfully updated {len(id_list)} cylinders.")
                    st.cache_data.clear() # Clear cache to refresh data
                    st.rerun()
                except Exception as e:
                    st.error(f"Error during update: {e}")
            else:
                st.error("Please enter at least one Cylinder ID.")

    #------------------------------------------------------------------------------------------------------------------------------------------------------------
    
    # 3. RECONCILIATION SECTION
    if not batch_data.empty:
        st.divider()
        st.subheader(f"🚩 Reconciliation: {batch_lookup}")
        total = len(batch_data)
        full = len(batch_data[batch_data["Status"] == "Full"])
        prog = full/total
        st.write(f"**Batch Progress:** {full} of {total} units completed.")
        st.progress(prog)
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Sent Back (Full)", full)
        m2.metric("In Testing (Empty)", len(batch_data[batch_data["Status"] == "Empty"]))
        m3.metric("Damaged/Rejected", len(batch_data[batch_data["Status"] == "Damaged"]))

# --- 7. PAGE LOGIC: CYLINDER FINDER ---
elif page == "Cylinder Finder":
    st.title("🔍 Individual Cylinder Lookup")
    search_id = st.text_input("Enter Cylinder ID").strip().upper()
    if search_id:
        result = df_main[df_main["Cylinder_ID"] == search_id]
        if not result.empty:
            st.dataframe(result, use_container_width=True, hide_index=True)
        else:
            st.warning("Cylinder not found or access denied.")
            
#------------------------------------------------------------------------------------------------------------------------------------------------------------

# --- 8. PAGE LOGIC: INVENTORY MANAGEMENT (Admin Only) ---
elif page == "Inventory Management":
    st.title("⚙️ System Inventory Management")
    if role != "admin":
        st.error("Access Denied.")
    else:
        st.write("Use this page to add new cylinders to the master database.")
        with st.form("add_cylinder_form"):
            new_id = st.text_input("Cylinder ID (Unique)")
            new_cust = st.text_input("Assign to Customer")
            new_cap = st.number_input("Capacity (kg)", min_value=0.0)
            
            if st.form_submit_button("Add to System"):
                if new_id:
                    try:
                        conn.table("cylinders").insert({
                            "Cylinder_ID": new_id.upper(),
                            "Customer_Name": new_cust,
                            "Capacity_kg": new_cap,
                            "Status": "Empty",
                            "Current_Location": "Testing Center"
                        }).execute()
                        st.success(f"Cylinder {new_id} added successfully!")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.warning("Please enter a Cylinder ID.")
































































