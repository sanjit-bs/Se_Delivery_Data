import base64
from datetime import date
import re
import pandas as pd
import requests
import streamlit as st

# ======================================================
# Transport Record Section & Configuration
# ======================================================

APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzAH530mCrkFHGBGtMJBGvo2REISuHgA7UGDV3zf7Z5l77dMyAguc_qlSmxMbEFx5prJg/exec"

# COLUMNS2 includes 'Invoice Link' right after 'Remark'
COLUMNS2 = [
    "Date",
    "Vehicle No.",
    "Invoice No.",
    "Driver",
    "Owner",
    "Company & Location",
    "Invoice Received",
    "Remark",
    "Invoice Link",
    "Loading Charge",
    "Unloading Charge",
]

COMPANY_OPTIONS = [
    "Select",
    # "Kamal’s cake (SOUTH SANKRAIL)",
    "Adela Labs Pvt. Ltd (HOWRAH FOOD PARK)",
    # "Kamals Ice Cream & Industries Pvt. Ltd  (ORL E) (Dhulagori)",
    "Kamals Ice Cream (Shaoraphuli, ”Adila”)",
    # "Agarwal Food Product (Sankrail)",
    # "Pamir Ice Cream (Raiganj)",
    # "Top notch (Gaighata)",
    "SIROMONI FOOD PRODUCTS PVT. LTD (MIDNAPUR)",
    "Cold Roll (Gaighata)",
]

VEHICLE_MASTER = {
    "Select": {"driver": "", "owner": ""},
    "WB23C6784": {"driver": "Mangal", "owner": "D Biswas"},
    "WB25L6773": {"driver": "Raja", "owner": "D Biswas"},
    "WB25G3488": {"driver": "Babu", "owner": "D Biswas"},
    "WB25W1226": {"driver": "Sanjay", "owner": "D Biswas"},
    "WB25P9492": {"driver": "Badal", "owner": "D Biswas"},
    "WB25H7255": {"driver": "", "owner": "Chotu"},
    "WB25H5255": {"driver": "", "owner": "Chotu"},
    "Others": {"driver": "", "owner": ""},
}


# ======================================================
# Backend API Calls & Data Loaders
# ======================================================
@st.cache_data(ttl=5)
def load_delivery_data():
    try:
        res = requests.get(
            f"{APPS_SCRIPT_URL}?action=read_delivery", timeout=30
        )
        data = res.json().get("delivery", [])
        df = pd.DataFrame(data)
    except Exception:
        df = pd.DataFrame(columns=COLUMNS2)

    for col in COLUMNS2:
        if col not in df.columns:
            df[col] = ""

    df = df[COLUMNS2].copy()
    df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")
    text_cols = [
        "Vehicle No.",
        "Invoice No.",
        "Driver",
        "Owner",
        "Company & Location",
        "Invoice Received",
        "Remark",
        "Invoice Link",
    ]
    for col in text_cols:
        df[col] = df[col].astype(str).str.strip()

    return df


delivery_df = load_delivery_data()


# ======================================================
# Apps Script Upload Helper for Scan Copy
# ======================================================
def upload_scan_to_drive_via_appscript(
    file_bytes, file_name, mime_type, company_name
):
    """Encodes file bytes and posts to Apps Script to store in 'receive invoice/[Company Name]' subfolder."""
    encoded_file = base64.b64encode(file_bytes).decode("utf-8")

    payload = {
        "action": "upload_invoice",
        "company": company_name.strip(),
        "fileName": file_name,
        "mimeType": mime_type,
        "fileData": encoded_file,
    }

    try:
        response = requests.post(APPS_SCRIPT_URL, json=payload, timeout=30)
        if response.status_code == 200:
            res_json = response.json()
            if res_json.get("status") == "success":
                return res_json.get("link", "")
            else:
                st.error(
                    f"Apps Script Error: {res_json.get('message', 'Unknown error')}"
                )
        else:
            st.error(
                f"HTTP Error {response.status_code}: Could not reach Apps Script Endpoint."
            )
    except Exception as e:
        st.error(f"Failed to connect to Apps Script: {e}")
    return None


# ======================================================
# Auto-Increment Sequence Logic (Format: SE/039/26-27)
# ======================================================
def get_financial_year(target_date=None):
    if target_date is None:
        target_date = date.today()
    year = target_date.year
    if target_date.month >= 4:
        start_yr = year % 100
        end_yr = (year + 1) % 100
    else:
        start_yr = (year - 1) % 100
        end_yr = year % 100
    return f"{start_yr:02d}-{end_yr:02d}"


def get_next_invoice_number(df, target_date=None):
    fy = get_financial_year(target_date)
    prefix = "SE"
    default_invoice = f"{prefix}/001/{fy}"

    if df.empty or "Invoice No." not in df.columns:
        return default_invoice

    valid_invoices = df["Invoice No."].dropna().astype(str).str.strip()
    valid_invoices = [v for v in valid_invoices if v != ""]
    if not valid_invoices:
        return default_invoice

    last_invoice = valid_invoices[-1]

    # Pattern match for SE/039/26-27 style invoice numbers
    match = re.search(r"SE/(\d+)/", last_invoice, re.IGNORECASE)
    if match:
        num_part = match.group(1)
        next_num = int(num_part) + 1
        next_num_str = str(next_num).zfill(len(num_part))
        return f"{prefix}/{next_num_str}/{fy}"

    match_any = re.search(r"(\d+)", last_invoice)
    if match_any:
        num_part = match_any.group(1)
        next_num = int(num_part) + 1
        next_num_str = str(next_num).zfill(3)
        return f"{prefix}/{next_num_str}/{fy}"

    return default_invoice


suggested_next_invoice = get_next_invoice_number(delivery_df)

# ======================================================
# Runtime Session States
# ======================================================
if "form_key" not in st.session_state:
    st.session_state.form_key = 0
if "current_driver" not in st.session_state:
    st.session_state.current_driver = ""
if "current_owner" not in st.session_state:
    st.session_state.current_owner = ""
if "current_invoice" not in st.session_state:
    st.session_state.current_invoice = suggested_next_invoice
if "receive_modal_item" not in st.session_state:
    st.session_state.receive_modal_item = None


def update_vehicle_details():
    sel = st.session_state[f"v_sel_{st.session_state.form_key}"]
    st.session_state.current_driver = VEHICLE_MASTER[sel]["driver"]
    st.session_state.current_owner = VEHICLE_MASTER[sel]["owner"]
    key_suffix = st.session_state.form_key
    st.session_state[f"driver_field_{key_suffix}"] = VEHICLE_MASTER[sel][
        "driver"
    ]
    st.session_state[f"owner_field_{key_suffix}"] = VEHICLE_MASTER[sel]["owner"]


# ======================================================
# Delivery Record Form
# ======================================================
st.subheader("🚚 New Delivery Entry")
key_suffix = st.session_state.form_key

col1, col2 = st.columns(2)
with col1:
    vehicle_selection = st.selectbox(
        "Vehicle No. *",
        options=list(VEHICLE_MASTER.keys()),
        key=f"v_sel_{key_suffix}",
        on_change=update_vehicle_details,
    )
    final_vehicle_no = (
        st.text_input("Manual Vehicle No. *", key=f"v_manual_{key_suffix}")
        if vehicle_selection == "Others"
        else vehicle_selection
    )
with col2:
    invoice_no = st.text_input(
        "Invoice Number *",
        value=st.session_state.current_invoice,
        key=f"delivery_entry_invoice_field_{key_suffix}",
    )

col3, col4 = st.columns(2)
with col3:
    driver_name = st.text_input(
        "Driver",
        value=st.session_state.current_driver,
        key=f"driver_field_{key_suffix}",
    )
with col4:
    owner_name = st.text_input(
        "Owner",
        value=st.session_state.current_owner,
        key=f"owner_field_{key_suffix}",
    )

company = st.selectbox(
    "Company & Location *",
    options=COMPANY_OPTIONS,
    key=f"delivery_company_{key_suffix}",
)
remark = st.text_area("Remark", key=f"delivery_remark_{key_suffix}")
delivery_date = st.date_input(
    "Delivery Date", value=date.today(), key=f"delivery_date_{key_suffix}"
)

if st.button("Submit Delivery Log", type="primary"):
    if vehicle_selection == "Select":
        st.warning("Please select a Vehicle Number.")
    elif final_vehicle_no.strip() == "":
        st.warning("Please enter the Manual Vehicle Number.")
    elif invoice_no.strip() == "":
        st.warning("Please enter Invoice Number.")
    elif company == "Select":
        st.warning("Please choose a valid Company.")
    else:
        params = {
            "action": "add_delivery",
            "date": delivery_date.strftime("%d/%m/%Y"),
            "vehicle_no": final_vehicle_no.strip().upper(),
            "invoice_no": invoice_no.strip(),
            "driver": driver_name.strip(),
            "owner": owner_name.strip(),
            "company": company.strip(),
            "invoice_received": "No",
            "remark": remark.strip(),
            "invoice_link": "",
            "loading_charge": 0.0,
            "unloading_charge": 0.0,
        }
        try:
            res = requests.get(APPS_SCRIPT_URL, params=params, timeout=30)
            if res.json().get("status") == "success":
                st.toast("✅ Delivery Log Appended Successfully")
                st.cache_data.clear()
                fresh_df = load_delivery_data()
                st.session_state.current_driver = ""
                st.session_state.current_owner = ""
                st.session_state.current_invoice = get_next_invoice_number(
                    fresh_df, delivery_date
                )
                st.session_state.form_key += 1
                st.rerun()
            else:
                st.error(f"Backend Error: {res.json().get('message')}")
        except Exception as e:
            st.error(f"Transaction failed: {e}")

# ======================================================
# UI Section: Pending Deliveries Management
# ======================================================
st.markdown("---")
st.subheader("📋 Pending Deliveries (Not Received)")
pending_df = delivery_df[
    delivery_df["Invoice Received"].str.strip().str.lower() == "no"
]

if pending_df.empty:
    st.info("🎉 All deliveries have been successfully received!")
else:
    col_h1, col_h2, col_h3, col_h4, col_h5, col_h6 = st.columns(
        [1.2, 1.5, 1.5, 1.5, 2.5, 1]
    )
    with col_h1:
        st.markdown("**Date**")
    with col_h2:
        st.markdown("**Invoice No.**")
    with col_h3:
        st.markdown("**Vehicle No.**")
    with col_h4:
        st.markdown("**Driver**")
    with col_h5:
        st.markdown("**Company & Location**")
    with col_h6:
        st.markdown("**Action**")
    st.markdown("---")

    for idx, row in pending_df.iterrows():
        gs_row = idx + 2
        col_date, col_inv, col_veh, col_driver, col_comp, col_act = st.columns(
            [1.2, 1.5, 1.5, 1.5, 2.5, 1]
        )

        with col_date:
            if isinstance(row["Date"], pd.Timestamp) or hasattr(
                row["Date"], "strftime"
            ):
                st.write(row["Date"].strftime("%d/%m/%Y"))
            else:
                st.write(str(row["Date"]))

        with col_inv:
            st.write(row["Invoice No."])
        with col_veh:
            st.write(row["Vehicle No."])
        with col_driver:
            st.write(row["Driver"])
        with col_comp:
            st.write(row["Company & Location"])
        with col_act:
            if st.button("Receive 📩", key=f"btn_recv_{gs_row}"):
                st.session_state.receive_modal_item = {
                    "gs_row": gs_row,
                    "invoice_no": row["Invoice No."],
                    "company": row["Company & Location"],
                }
                st.rerun()

# ======================================================
# Modal Dialog for Scan Copy Capture / Upload
# ======================================================
if st.session_state.receive_modal_item is not None:
    item = st.session_state.receive_modal_item

    @st.dialog("📸 Upload Scanned Invoice Copy")
    def open_receive_modal():
        st.write(f"**Invoice No:** `{item['invoice_no']}`")
        st.write(f"**Company:** `{item['company']}`")

        input_mode = st.radio(
            "Select Scan Input Method",
            ["📷 Camera Capture", "📁 Upload File from Device"],
            horizontal=True,
        )

        file_data = None
        if input_mode == "📷 Camera Capture":
            file_data = st.camera_input("Take Invoice Photo")
        else:
            file_data = st.file_uploader(
                "Choose Invoice Image/PDF", type=["png", "jpg", "jpeg", "pdf"]
            )

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            if st.button(
                "Confirm & Upload to Drive", type="primary", use_container_width=True
            ):
                if file_data is None:
                    st.warning("Please upload or capture an image first.")
                else:
                    with st.spinner(
                        "Uploading to Google Drive & Updating Sheet..."
                    ):
                        bytes_content = file_data.getvalue()
                        filename_clean = item["invoice_no"].replace("/", "_")
                        ext = (
                            file_data.name.split(".")[-1]
                            if hasattr(file_data, "name")
                            and "." in file_data.name
                            else "png"
                        )
                        file_name = f"{filename_clean}_Scan.{ext}"
                        mime_type = (
                            getattr(file_data, "type", "image/png")
                            or "image/png"
                        )

                        # 1. Upload scan copy via Apps Script Web App
                        drive_link = upload_scan_to_drive_via_appscript(
                            bytes_content,
                            file_name,
                            mime_type,
                            item["company"],
                        )

                        if drive_link:
                            # 2. Update status and link via Apps Script
                            params = {
                                "action": "update_received",
                                "row_index": item["gs_row"],
                                "invoice_no": item["invoice_no"],
                                "status": "Yes",
                                "invoice_link": drive_link,
                            }
                            requests.get(
                                APPS_SCRIPT_URL, params=params, timeout=30
                            )

                            st.toast(
                                f"✅ Marked Invoice {item['invoice_no']} as Received & Drive Link Saved!"
                            )

                            # 3. Cache clearing and page refresh
                            st.cache_data.clear()
                            fresh_df = load_delivery_data()
                            st.session_state.current_invoice = (
                                get_next_invoice_number(fresh_df)
                            )
                            st.session_state.receive_modal_item = None
                            st.rerun()

        with col_m2:
            if st.button("Cancel", use_container_width=True):
                st.session_state.receive_modal_item = None
                st.rerun()

    open_receive_modal()

# ======================================================
# UI Section: Post-Submission Loading / Unloading Charges
# ======================================================
st.markdown("---")
st.subheader("💰 Add Loading & Unloading Charges")

if delivery_df.empty:
    st.info("No submitted invoices found to apply charges to.")
else:
    submitted_invoices = (
        delivery_df["Invoice No."].dropna().astype(str).str.strip()
    )
    valid_invoice_options = ["Select Invoice"] + [
        inv for inv in submitted_invoices.unique() if inv != ""
    ]

    col_c1, col_c2, col_c3 = st.columns(3)

    with col_c1:
        selected_charge_invoice = st.selectbox(
            "Select Submitted Invoice *",
            options=valid_invoice_options,
            key="charge_invoice_selector",
        )

    target_gs_row = None
    existing_loading = 0.0
    existing_unloading = 0.0

    if selected_charge_invoice != "Select Invoice":
        match_idx = delivery_df[
            delivery_df["Invoice No."] == selected_charge_invoice
        ].index
        if not match_idx.empty:
            target_gs_row = int(match_idx[0]) + 2
            row_data = delivery_df.loc[match_idx[0]]
            if "Loading Charge" in row_data and str(
                row_data["Loading Charge"]
            ).strip():
                existing_loading = float(
                    pd.to_numeric(
                        row_data["Loading Charge"], errors="coerce"
                    )
                    or 0.0
                )
            if "Unloading Charge" in row_data and str(
                row_data["Unloading Charge"]
            ).strip():
                existing_unloading = float(
                    pd.to_numeric(
                        row_data["Unloading Charge"], errors="coerce"
                    )
                    or 0.0
                )

    with col_c2:
        loading_input = st.number_input(
            "Loading Charge (₹)",
            min_value=0.0,
            value=existing_loading,
            step=10.0,
            format="%.2f",
            key="loading_charge_input",
        )

    with col_c3:
        unloading_input = st.number_input(
            "Unloading Charge (₹)",
            min_value=0.0,
            value=existing_unloading,
            step=10.0,
            format="%.2f",
            key="unloading_charge_input",
        )

    if st.button("Save Charges to Invoice", type="secondary"):
        if selected_charge_invoice == "Select Invoice":
            st.warning(
                "Please choose a valid submitted invoice from the dropdown menu first."
            )
        elif target_gs_row is None:
            st.error(
                "Could not trace the structural coordinates of this invoice."
            )
        else:
            params = {
                "action": "update_charges",
                "row_index": target_gs_row,
                "invoice_no": selected_charge_invoice,
                "loading_charge": round(loading_input, 2),
                "unloading_charge": round(unloading_input, 2),
            }
            requests.get(APPS_SCRIPT_URL, params=params, timeout=30)
            st.toast(
                f"💵 Charges saved successfully for Invoice {selected_charge_invoice}!"
            )
            st.cache_data.clear()
            st.rerun()

############# Ready Product Stock Management ########################

https://shivam-ready-stock-manager-app-m0ynofi753.streamlit.app/
