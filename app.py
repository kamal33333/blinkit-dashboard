import streamlit as st
import pandas as pd
import io
import datetime
import urllib.parse

# Page Config
st.set_page_config(page_title="Blinkit Master Analytics", page_icon="📊", layout="wide")
st.title("📊 Blinkit Sales & Inventory Master")

# ==========================================
# 1. SMART LOADERS (Fixes your 'raw' sheet error)
# ==========================================
@st.cache_data
def load_smart_sales(file):
    """
    Reads sales file, looking for standard columns even if headers are slightly shifted.
    """
    if file is None:
        return None
    try:
        # Read normally first
        df = pd.read_excel(file)
        
        # If 'Order Date' isn't in columns, scan first 10 rows
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
                st.error("❌ Could not find 'Order Date' column in Sales file.")
                return None

        # Clean Columns
        df.columns = df.columns.str.strip()
        
        # Data Type Conversion
        df['Order Date'] = pd.to_datetime(df['Order Date'], errors='coerce')
        df = df.dropna(subset=['Order Date'])
        
        # Numeric Cleanups
        for col in ['Quantity', 'Total Gross Bill Amount']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            else:
                df[col] = 0
                
        return df
    except Exception as e:
        st.error(f"Error loading Sales file: {e}")
        return None

@st.cache_data
def load_smart_inventory(file):
    """
    Scans all sheets to find Inventory data.
    """
    if file is None:
        return None
    try:
        xl = pd.ExcelFile(file)
        target_sheet = None
        header_row_idx = 0
        
        # Loop through ALL sheets to find the one with data
        for sheet in xl.sheet_names:
            df_preview = pd.read_excel(file, sheet_name=sheet, header=None, nrows=10)
            for idx, row in df_preview.iterrows():
                row_vals = row.astype(str).str.strip().tolist()
                # We identify the correct sheet by looking for these specific columns
                if 'Item Name' in row_vals and 'Total sellable' in row_vals:
                    target_sheet = sheet
                    header_row_idx = idx
                    break
            if target_sheet:
                break
        
        if target_sheet is None:
            st.error("❌ Could not find Inventory data (looking for 'Item Name' & 'Total sellable').")
            return None

        # Load the identified sheet
        df = pd.read_excel(file, sheet_name=target_sheet, header=header_row_idx)
        df.columns = df.columns.str.strip()
        
        cols_to_clean = ['Total sellable', 'Incoming scheduled inventory', 'Last 30 days']
        for col in cols_to_clean:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            else:
                df[col] = 0
        
        return df
    except Exception as e:
        st.error(f"Error loading Inventory file: {e}")
        return None

# ==========================================
# 2. FILE UPLOAD SECTION
# ==========================================
st.sidebar.header("📂 Upload Raw Files")
current_file = st.sidebar.file_uploader("Current Month Sales (Raw)", type=['xlsx'])
prev_file = st.sidebar.file_uploader("Previous Month Sales (Raw)", type=['xlsx'])
inv_file = st.sidebar.file_uploader("Inventory (Raw)", type=['xlsx'])

if current_file and inv_file:
    with st.spinner('Processing Files...'):
        df = load_smart_sales(current_file)
        df_prev = load_smart_sales(prev_file) if prev_file else None
        inv_df = load_smart_inventory(inv_file)

    if df is not None and inv_df is not None:
        st.success("✅ Data Loaded Successfully!")
        
        # ==========================================
        # 3. CORE ANALYTICS (Current Month)
        # ==========================================
        last_date = df['Order Date'].max().date()
        num_days = df['Order Date'].dt.normalize().nunique()
        month_total = df['Total Gross Bill Amount'].sum()
        
        daily_totals = df.groupby(df['Order Date'].dt.date)[['Total Gross Bill Amount', 'Quantity']].sum().reset_index()
        daily_totals.columns = ['Date', 'Total Revenue', 'Total Quantity']
        
        monthly_avg_revenue = daily_totals['Total Revenue'].mean()
        monthly_avg_qty = daily_totals['Total Quantity'].mean()
        
        last_day_rev = daily_totals.iloc[-1]['Total Revenue']
        last_day_qty = daily_totals.iloc[-1]['Total Quantity']
        last_day_df = df[df['Order Date'].dt.date == last_date]

        # Metrics
        st.markdown("### 📊 Key Performance Metrics")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Last Day Revenue", f"₹{last_day_rev:,.0f}", delta=f"{last_day_rev - monthly_avg_revenue:,.0f} vs Avg")
        c2.metric("Last Day Units", f"{last_day_qty:,.0f}")
        c3.metric("Total Sellable Stock", f"{inv_df['Total sellable'].sum():,.0f}")
        c4.metric("Month Total", f"₹{month_total:,.0f}")

        # ==========================================
        # 4. PREVIOUS MONTH COMPARISON LOGIC
        # ==========================================
        comparison_sheets = {}
        if df_prev is not None:
            num_days_prev = df_prev['Order Date'].dt.normalize().nunique()
            st.info(f"📊 Comparing: Current ({num_days} days) vs Previous ({num_days_prev} days)")

            def generate_comparison(group_col):
                if group_col not in df.columns or group_col not in df_prev.columns:
                    return pd.DataFrame()

                prev_sum = df_prev.groupby(group_col)[['Total Gross Bill Amount', 'Quantity']].sum()
                prev_avg = prev_sum / num_days_prev
                prev_avg.columns = ['Prev Daily Avg Rev', 'Prev Daily Avg Qty']

                curr_sum = df.groupby(group_col)[['Total Gross Bill Amount', 'Quantity']].sum()
                curr_avg = curr_sum / num_days
                curr_avg.columns = ['Curr Daily Avg Rev', 'Curr Daily Avg Qty']

                merged = pd.merge(prev_avg, curr_avg, left_index=True, right_index=True, how='outer').fillna(0)
                
                # Growth Calculation
                merged['Rev Growth %'] = (merged['Curr Daily Avg Rev'] - merged['Prev Daily Avg Rev']) / merged['Prev Daily Avg Rev'].replace(0, 1)
                merged['Qty Growth %'] = (merged['Curr Daily Avg Qty'] - merged['Prev Daily Avg Qty']) / merged['Prev Daily Avg Qty'].replace(0, 1)
                
                cols = ['Prev Daily Avg Rev', 'Curr Daily Avg Rev', 'Rev Growth %', 
                        'Prev Daily Avg Qty', 'Curr Daily Avg Qty', 'Qty Growth %']
                return merged[cols].sort_values('Curr Daily Avg Rev', ascending=False)

            comparison_sheets['Vs Prev Month - Products'] = generate_comparison('Product Name')
            comparison_sheets['Vs Prev Month - States'] = generate_comparison('Customer State')
            comparison_sheets['Vs Prev Month - Cities'] = generate_comparison('Customer City')

        # ==========================================
        # 5. GROWTH REPORT (Last Day vs Current Avg)
        # ==========================================
        def create_growth_report(group_col):
            if group_col not in df.columns: return pd.DataFrame()
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
        
        # Merge Inventory info
        if 'Item Name' in inv_df.columns:
            inv_prod_sum = inv_df.groupby('Item Name')['Total sellable'].sum()
            prod_report = prod_report.merge(inv_prod_sum, left_index=True, right_index=True, how='left').rename(columns={'Total sellable': 'Stock'}).fillna(0)
        else:
            prod_report['Stock'] = 0

        # ==========================================
        # 6. WHATSAPP LOGIC
        # ==========================================
        st.divider()
        st.subheader("📲 WhatsApp Summary")
        
        # Calculate Top 5 Growth
        top_12_revenue = prod_report.sort_values('Last Day Rev', ascending=False).head(12)
        top_5_growth = top_12_revenue.sort_values('Growth %', ascending=False).head(5)
        growth_lines = "\n".join([f"{i+1}. {name}: {row['Growth %']*100:.1f}%" for i, (name, row) in enumerate(top_5_growth.iterrows())])
        
        # State Data
        if not state_report.empty:
            top_state_name = state_report['Last Day Rev'].idxmax()
            top_state_val = state_report['Last Day Rev'].max()
            top_state_growth = state_report.loc[top_state_name, 'Growth %']
            state_str = f"🌍 *Top State:* {top_state_name} (₹{top_state_val:,.0f} | {top_state_growth*100:+.1f}%)"
        else:
            state_str = ""

        msg_text = (
            f"*BLINKIT EXECUTIVE SUMMARY*\n"
            f"📅 Date: {last_date}\n\n"
            f"💰 *Last Day Rev:* ₹{last_day_rev:,.0f}\n"
            f"📦 *Last Day Qty:* {last_day_qty:,.0f} units\n"
            f"⚖️ *Daily Avg Qty:* {monthly_avg_qty:.1f} units\n"
            f"📈 *Status:* {'HIGHER' if last_day_rev > monthly_avg_revenue else 'LOWER'} vs Avg\n"
            f"{state_str}\n\n"
            f"🚀 *Top 5 Growth Leaders (Of Top 12 Sellers):*\n{growth_lines}\n\n"
            f"🏭 *Inventory:* {inv_df['Total sellable'].sum():,.0f} units"
        )
        
        col_wa1, col_wa2 = st.columns([3, 1])
        with col_wa1:
            st.text_area("Message Preview:", msg_text, height=300)
        with col_wa2:
            st.info("Send instantly:")
            encoded_msg = urllib.parse.quote(msg_text)
            st.link_button("🚀 WhatsApp Web", f"https://wa.me/918580904001?text={encoded_msg}")

        # ==========================================
        # 7. EXCEL EXPORT
        # ==========================================
        st.divider()
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        workbook = writer.book
        
        # Formats
        money_fmt = workbook.add_format({'num_format': '₹#,##0'})
        pct_fmt = workbook.add_format({'num_format': '0.0%'})
        
        # Write Sheets
        prod_report.sort_values('Last Day Rev', ascending=False).to_excel(writer, sheet_name='All Products')
        
        # Write Comparison Sheets
        if df_prev is not None:
            for sheet_name, data in comparison_sheets.items():
                data.to_excel(writer, sheet_name=sheet_name)
                # Apply formats
                ws = writer.sheets[sheet_name]
                ws.set_column('A:A', 40)
                ws.set_column('C:C', 10, pct_fmt) # Growth column
        
        daily_totals.to_excel(writer, sheet_name='Daily Sales', index=False)
        inv_df.to_excel(writer, sheet_name='Raw Inventory', index=False)
        
        writer.close()
        output.seek(0)
        
        st.download_button(
            label="📥 Download Master Excel",
            data=output,
            file_name=f"Blinkit_Master_{last_date}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

else:
    st.info("👈 Please upload the 'Raw' Excel files from the sidebar.")
