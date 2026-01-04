import streamlit as st
import pandas as pd
import io
import datetime
import urllib.parse
import plotly.express as px # New library for charts (Built-in to Streamlit)

# Page Config
st.set_page_config(page_title="Blinkit Master Analytics", page_icon="📊", layout="wide")

# ==========================================
# 🔐 UPGRADE 1: PASSWORD PROTECTION
# ==========================================
# Change "kressa123" to whatever password you want
PASSWORD = "blinkithelp" 

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def check_password():
    if st.session_state.authenticated:
        return True
    
    st.title("🔒 Login Required")
    password = st.text_input("Enter Password", type="password")
    if st.button("Login"):
        if password == PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("❌ Incorrect Password")
    return False

if not check_password():
    st.stop()

# ==========================================
# 🚀 MAIN APP STARTS HERE
# ==========================================
st.title("📊 Blinkit Sales & Inventory Master")

# --- SMART LOADERS (Keep existing logic) ---
@st.cache_data
def load_smart_sales(file):
    if file is None: return None
    try:
        df = pd.read_excel(file)
        if 'Order Date' not in df.columns:
            df_preview = pd.read_excel(file, header=None, nrows=10)
            header_row = None
            for idx, row in df_preview.iterrows():
                row_str = row.astype(str).str.strip().tolist()
                if 'Order Date' in row_str and 'Quantity' in row_str:
                    header_row = idx
                    break
            if header_row is not None:
                df = pd.read_excel(file, header=header_row)
            else:
                return None
        df.columns = df.columns.str.strip()
        df['Order Date'] = pd.to_datetime(df['Order Date'], errors='coerce')
        df = df.dropna(subset=['Order Date'])
        for col in ['Quantity', 'Total Gross Bill Amount']:
            if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            else: df[col] = 0
        return df
    except Exception: return None

@st.cache_data
def load_smart_inventory(file):
    if file is None: return None
    try:
        xl = pd.ExcelFile(file)
        target_sheet, header_row_idx = None, 0
        for sheet in xl.sheet_names:
            df_preview = pd.read_excel(file, sheet_name=sheet, header=None, nrows=10)
            for idx, row in df_preview.iterrows():
                row_vals = row.astype(str).str.strip().tolist()
                if 'Item Name' in row_vals and 'Total sellable' in row_vals:
                    target_sheet = sheet; header_row_idx = idx; break
            if target_sheet: break
        if not target_sheet: return None
        df = pd.read_excel(file, sheet_name=target_sheet, header=header_row_idx)
        df.columns = df.columns.str.strip()
        for col in ['Total sellable', 'Incoming scheduled inventory', 'Last 30 days']:
            if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            else: df[col] = 0
        return df
    except Exception: return None

# --- SIDEBAR ---
st.sidebar.header("📂 Upload Raw Files")
current_file = st.sidebar.file_uploader("Current Month Sales", type=['xlsx'])
prev_file = st.sidebar.file_uploader("Previous Month Sales", type=['xlsx'])
inv_file = st.sidebar.file_uploader("Inventory File", type=['xlsx'])

if st.sidebar.button("🔴 Logout"):
    st.session_state.authenticated = False
    st.rerun()

if current_file and inv_file:
    with st.spinner('Processing...'):
        df = load_smart_sales(current_file)
        df_prev = load_smart_sales(prev_file) if prev_file else None
        inv_df = load_smart_inventory(inv_file)

    if df is not None and inv_df is not None:
        # --- CORE METRICS ---
        last_date = df['Order Date'].max().date()
        num_days = df['Order Date'].dt.normalize().nunique()
        month_total = df['Total Gross Bill Amount'].sum()
        
        daily_totals = df.groupby(df['Order Date'].dt.date)[['Total Gross Bill Amount', 'Quantity']].sum().reset_index()
        daily_totals.columns = ['Date', 'Total Revenue', 'Total Quantity']
        
        last_day_rev = daily_totals.iloc[-1]['Total Revenue']
        last_day_qty = daily_totals.iloc[-1]['Total Quantity']
        monthly_avg = daily_totals['Total Revenue'].mean()

        st.markdown("### 📊 Key Performance Metrics")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Last Day Rev", f"₹{last_day_rev:,.0f}", delta=f"{last_day_rev - monthly_avg:,.0f} vs Avg")
        c2.metric("Last Day Units", f"{last_day_qty:,.0f}")
        c3.metric("Total Sellable Stock", f"{inv_df['Total sellable'].sum():,.0f}")
        c4.metric("Month Revenue", f"₹{month_total:,.0f}")

        # ==========================================
        # 📈 UPGRADE 2: TREND CHARTS
        # ==========================================
        st.divider()
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.subheader("📅 Daily Revenue Trend")
            fig_trend = px.line(daily_totals, x='Date', y='Total Revenue', markers=True, 
                                title=f"Sales Trend (Last Date: {last_date})")
            fig_trend.update_layout(xaxis_title="", yaxis_title="Revenue (₹)")
            st.plotly_chart(fig_trend, use_container_width=True)

        with col_chart2:
            st.subheader("🏆 Top 10 Products (Revenue)")
            top_products = df.groupby('Product Name')['Total Gross Bill Amount'].sum().nlargest(10).reset_index()
            fig_bar = px.bar(top_products, x='Total Gross Bill Amount', y='Product Name', orientation='h',
                             text_auto='.2s', title="Top Performers This Month")
            fig_bar.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title="Total Revenue")
            st.plotly_chart(fig_bar, use_container_width=True)

        # --- PREVIOUS MONTH COMPARISON LOGIC (Hidden Calculation) ---
        comparison_sheets = {}
        if df_prev is not None:
            num_days_prev = df_prev['Order Date'].dt.normalize().nunique()
            def generate_comparison(group_col):
                if group_col not in df.columns or group_col not in df_prev.columns: return pd.DataFrame()
                prev_sum = df_prev.groupby(group_col)[['Total Gross Bill Amount', 'Quantity']].sum()
                prev_avg = prev_sum / num_days_prev
                prev_avg.columns = ['Prev Daily Avg Rev', 'Prev Daily Avg Qty']
                curr_sum = df.groupby(group_col)[['Total Gross Bill Amount', 'Quantity']].sum()
                curr_avg = curr_sum / num_days
                curr_avg.columns = ['Curr Daily Avg Rev', 'Curr Daily Avg Qty']
                merged = pd.merge(prev_avg, curr_avg, left_index=True, right_index=True, how='outer').fillna(0)
                merged['Rev Growth %'] = (merged['Curr Daily Avg Rev'] - merged['Prev Daily Avg Rev']) / merged['Prev Daily Avg Rev'].replace(0, 1)
                merged['Qty Growth %'] = (merged['Curr Daily Avg Qty'] - merged['Prev Daily Avg Qty']) / merged['Prev Daily Avg Qty'].replace(0, 1)
                return merged[['Prev Daily Avg Rev', 'Curr Daily Avg Rev', 'Rev Growth %', 'Prev Daily Avg Qty', 'Curr Daily Avg Qty', 'Qty Growth %']]

            comparison_sheets['Vs Prev Month - Products'] = generate_comparison('Product Name')
            comparison_sheets['Vs Prev Month - States'] = generate_comparison('Customer State')

        # --- REPORT GENERATION ---
        last_day_df = df[df['Order Date'].dt.date == last_date]
        
        prod_report = pd.DataFrame()
        if 'Product Name' in df.columns:
            last = last_day_df.groupby('Product Name')[['Total Gross Bill Amount', 'Quantity']].sum()
            monthly = df.groupby('Product Name')[['Total Gross Bill Amount', 'Quantity']].sum()
            prod_report = pd.DataFrame({
                'Last Day Rev': last['Total Gross Bill Amount'],
                'Daily Avg Rev': monthly['Total Gross Bill Amount'] / num_days,
                'Growth %': (last['Total Gross Bill Amount'] - (monthly['Total Gross Bill Amount']/num_days)) / (monthly['Total Gross Bill Amount']/num_days).replace(0, 1)
            }).fillna(0)
            if 'Item Name' in inv_df.columns:
                inv_sum = inv_df.groupby('Item Name')['Total sellable'].sum()
                prod_report = prod_report.merge(inv_sum, left_index=True, right_index=True, how='left').fillna(0)

        # --- WHATSAPP ---
        st.divider()
        st.subheader("📲 WhatsApp Summary")
        
        top_5_growth = prod_report.sort_values('Growth %', ascending=False).head(5) if not prod_report.empty else pd.DataFrame()
        growth_lines = "\n".join([f"{i+1}. {n}: {r['Growth %']*100:.1f}%" for i, (n, r) in enumerate(top_5_growth.iterrows())])
        
        msg = f"*BLINKIT SUMMARY {last_date}*\n💰 Rev: ₹{last_day_rev:,.0f}\n📦 Units: {last_day_qty:,.0f}\n🚀 *Growth Leaders:*\n{growth_lines}"
        
        c1, c2 = st.columns([3, 1])
        c1.text_area("Msg", msg, height=150)
        c2.link_button("🚀 Send WhatsApp", f"https://wa.me/918580904001?text={urllib.parse.quote(msg)}")

        # --- DOWNLOAD ---
        st.divider()
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        if not prod_report.empty: prod_report.to_excel(writer, sheet_name='Products')
        daily_totals.to_excel(writer, sheet_name='Daily Sales', index=False)
        if df_prev is not None:
            for name, data in comparison_sheets.items(): data.to_excel(writer, sheet_name=name)
        writer.close()
        output.seek(0)
        st.download_button("📥 Download Master Excel", output, f"Blinkit_{last_date}.xlsx")

else:
    st.info("👈 Please upload files to begin.")
