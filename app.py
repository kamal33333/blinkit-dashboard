import streamlit as st
import pandas as pd
import io
import datetime
import urllib.parse

# Page Config
st.set_page_config(page_title="Blinkit Master Analytics", page_icon="📊", layout="wide")
st.title("📊 Blinkit Sales & Inventory Master")

# ==========================================
# 1. FILE UPLOAD SECTION
# ==========================================
st.sidebar.header("📂 Upload Files")

# File Uploaders
current_file = st.sidebar.file_uploader("Current Month Sales (Excel)", type=['xlsx'])
prev_file = st.sidebar.file_uploader("Previous Month Sales (Optional)", type=['xlsx'])
inv_file = st.sidebar.file_uploader("Inventory Data (Excel)", type=['xlsx'])

if current_file and inv_file:
    st.success("✅ Files Loaded! Processing...")
    
    # ==========================================
    # 2. DATA LOADING & CLEANING
    # ==========================================
    @st.cache_data
    def load_and_clean(file):
        if file is None:
            return None
        d = pd.read_excel(file)
        d.columns = d.columns.str.strip()
        d['Order Date'] = pd.to_datetime(d['Order Date'], errors='coerce')
        d = d.dropna(subset=['Order Date'])
        for col in ['Quantity', 'Total Gross Bill Amount']:
            d[col] = pd.to_numeric(d[col], errors='coerce').fillna(0)
        return d

    df = load_and_clean(current_file)
    df_prev = load_and_clean(prev_file) if prev_file else None
    
    inv_df = pd.read_excel(inv_file, sheet_name='raw')
    inv_df.columns = inv_df.columns.str.strip()
    for col in ['Total sellable', 'Incoming scheduled inventory', 'Last 30 days']:
        inv_df[col] = pd.to_numeric(inv_df[col], errors='coerce').fillna(0)

    # ==========================================
    # 3. CORE ANALYTICS LOGIC
    # ==========================================
    # Basic Variables
    last_date = df['Order Date'].max().date()
    num_days = df['Order Date'].dt.normalize().nunique()
    month_total = df['Total Gross Bill Amount'].sum()
    
    daily_totals = df.groupby(df['Order Date'].dt.date)[['Total Gross Bill Amount', 'Quantity']].sum().reset_index()
    daily_totals.columns = ['Date', 'Total Revenue', 'Total Quantity']
    
    monthly_avg_revenue = daily_totals['Total Revenue'].mean()
    monthly_avg_qty = daily_totals['Total Quantity'].mean()
    
    last_day_rev = daily_totals.iloc[-1]['Total Revenue']
    last_day_qty = daily_totals.iloc[-1]['Total Quantity']
    last_day_name = pd.to_datetime(last_date).day_name()
    last_day_df = df[df['Order Date'].dt.date == last_date]

    # Display Metrics on Dashboard
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Last Day Rev", f"₹{last_day_rev:,.0f}", delta=f"{last_day_rev - monthly_avg_revenue:,.0f} vs Avg")
    col2.metric("Last Day Units", f"{last_day_qty:,.0f}")
    col3.metric("Total Sellable Stock", f"{inv_df['Total sellable'].sum():,.0f}")
    col4.metric("Month Total", f"₹{month_total:,.0f}")

    # ==========================================
    # 4. REPORT GENERATION (In Memory)
    # ==========================================
    def create_growth_report(group_col):
        last = last_day_df.groupby(group_col)[['Total Gross Bill Amount', 'Quantity']].sum()
        monthly = df.groupby(group_col)[['Total Gross Bill Amount', 'Quantity']].sum()
        
        report = pd.DataFrame({
            'Last Day Rev': last['Total Gross Bill Amount'],
            'Daily Avg Rev': monthly['Total Gross Bill Amount'] / num_days,
            'Total Rev': monthly['Total Gross Bill Amount'],
            'Last Day Qty': last['Quantity'],
            'Daily Avg Qty': monthly['Quantity'] / num_days,
            'Total Qty': monthly['Quantity']
        }).fillna(0)
        report['Growth %'] = (report['Last Day Rev'] - report['Daily Avg Rev']) / report['Daily Avg Rev'].replace(0, 1)
        return report

    prod_report = create_growth_report('Product Name')
    state_report = create_growth_report('Customer State')
    city_report = create_growth_report('Customer City')

    # Add Inventory to Prod Report
    inv_prod_sum = inv_df.groupby('Item Name')['Total sellable'].sum()
    prod_report = prod_report.merge(inv_prod_sum, left_index=True, right_index=True, how='left').rename(columns={'Total sellable': 'Stock'}).fillna(0)

    # ==========================================
    # 5. WHATSAPP MESSAGE GENERATOR
    # ==========================================
    st.subheader("📲 WhatsApp Summary")
    
    # Logic from your script
    top_12_revenue_getters = prod_report.sort_values('Last Day Rev', ascending=False).head(12)
    top_5_growth = top_12_revenue_getters.sort_values('Growth %', ascending=False).head(5)
    growth_lines = "\n".join([f"{i+1}. {name}: {row['Growth %']*100:.1f}%" for i, (name, row) in enumerate(top_5_growth.iterrows())])
    
    top_state_name = state_report['Last Day Rev'].idxmax()
    top_state_val = state_report['Last Day Rev'].max()
    top_state_growth = state_report.loc[top_state_name, 'Growth %']

    msg_text = (
        f"*BLINKIT EXECUTIVE SUMMARY*\n"
        f"📅 Date: {last_date}\n\n"
        f"💰 *Last Day Rev:* ₹{last_day_rev:,.0f}\n"
        f"📦 *Last Day Qty:* {last_day_qty:,.0f} units\n"
        f"⚖️ *Daily Avg Qty:* {monthly_avg_qty:.1f} units\n"
        f"📈 *Status:* {'HIGHER' if last_day_rev > monthly_avg_revenue else 'LOWER'} vs Avg\n"
        f"🌍 *Top State:* {top_state_name} (₹{top_state_val:,.0f} | {top_state_growth*100:+.1f}%)\n\n"
        f"🚀 *Top 5 Growth Leaders (Of Top 12 Sellers):*\n{growth_lines}\n\n"
        f"🏭 *Inventory:* {inv_df['Total sellable'].sum():,.0f} units"
    )

    st.text_area("Copy this text:", msg_text, height=300)
    
    # Create Clickable WhatsApp Link
    encoded_msg = urllib.parse.quote(msg_text)
    wa_link = f"https://wa.me/918580904001?text={encoded_msg}"
    st.link_button("🚀 Send via WhatsApp Now", wa_link)

    # ==========================================
    # 6. EXCEL EXPORT (To Buffer)
    # ==========================================
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    workbook = writer.book
    
    # Formats
    header_fmt = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#1F4E78', 'border': 1})
    money_fmt = workbook.add_format({'border': 1, 'num_format': '₹#,##0'})
    
    # Write Sheets (Simplified for brevity, similar to your original logic)
    prod_report.sort_values('Last Day Rev', ascending=False).to_excel(writer, sheet_name='All Products')
    daily_totals.to_excel(writer, sheet_name='Daily Sales')
    
    writer.close()
    output.seek(0)
    
    st.download_button(
        label="📥 Download Master Excel",
        data=output,
        file_name=f"Blinkit_Master_{last_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("👈 Please upload the Sales and Inventory files from the sidebar to begin.")
