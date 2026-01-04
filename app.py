import streamlit as st
import pandas as pd
import io
import datetime
import urllib.parse
import plotly.express as px

# ==========================================
# 1. CONFIG & AUTHENTICATION
# ==========================================
st.set_page_config(page_title="Blinkit Master Analytics", page_icon="📊", layout="wide")

# PASSWORD SYSTEM
PASSWORD = "kressa_admin"  # <--- Change this if you want
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def check_password():
    if st.session_state.authenticated:
        return True
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("🔒 Blinkit Dashboard Login")
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
# 2. SMART LOADERS (Robust Version)
# ==========================================
@st.cache_data
def load_smart_sales(file):
    if file is None: return None
    try:
        df = pd.read_excel(file)
        # Auto-detect header row
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
            if col in df.columns: 
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            else: 
                df[col] = 0
        return df
    except Exception: return None

@st.cache_data
def load_smart_inventory(file):
    if file is None: return None
    try:
        xl = pd.ExcelFile(file)
        target_sheet, header_row_idx = None, 0
        # Smart Sheet Detection
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
            if col in df.columns: 
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            else: 
                df[col] = 0
        return df
    except Exception: return None

# ==========================================
# 3. UI & FILE UPLOAD
# ==========================================
st.title("📊 Blinkit Sales & Inventory Master")
st.sidebar.header("📂 Upload Files")

current_file = st.sidebar.file_uploader("Current Month Sales", type=['xlsx'])
prev_file = st.sidebar.file_uploader("Previous Month Sales (Optional)", type=['xlsx'])
inv_file = st.sidebar.file_uploader("Inventory File", type=['xlsx'])

if st.sidebar.button("🔴 Logout"):
    st.session_state.authenticated = False
    st.rerun()

if current_file and inv_file:
    with st.spinner('🚀 Processing Data & Restoring Logic...'):
        df = load_smart_sales(current_file)
        df_prev = load_smart_sales(prev_file) if prev_file else None
        inv_df = load_smart_inventory(inv_file)

    if df is not None and inv_df is not None:
        # ==========================================
        # 4. CORE VARIABLES & CALCULATIONS
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
        last_day_name = pd.to_datetime(last_date).day_name()
        last_day_df = df[df['Order Date'].dt.date == last_date]

        # --- Display Metrics ---
        st.markdown(f"### 📅 Report Date: {last_date}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Last Day Rev", f"₹{last_day_rev:,.0f}", delta=f"{last_day_rev - monthly_avg_revenue:,.0f} vs Avg")
        c2.metric("Last Day Units", f"{last_day_qty:,.0f}")
        c3.metric("Total Stock", f"{inv_df['Total sellable'].sum():,.0f}")
        c4.metric("Month Total", f"₹{month_total:,.0f}")

        # ==========================================
        # 5. CHARTS (Web Exclusive)
        # ==========================================
        st.divider()
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.subheader("📅 Daily Revenue Trend")
            fig = px.line(daily_totals, x='Date', y='Total Revenue', markers=True, template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)
        with col_chart2:
            st.subheader("🏆 Top 10 Products (Revenue)")
            top_10 = df.groupby('Product Name')['Total Gross Bill Amount'].sum().nlargest(10).reset_index()
            fig2 = px.bar(top_10, x='Total Gross Bill Amount', y='Product Name', orientation='h', template="plotly_white")
            fig2.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig2, use_container_width=True)

        # ==========================================
        # 6. REPORT LOGIC (Exact Match to Original)
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
            report = report.replace([float('inf'), -float('inf')], 0)
            return report

        prod_report = create_growth_report('Product Name')
        
        # Merge Inventory Logic
        if 'Item Name' in inv_df.columns:
            inv_sum = inv_df.groupby('Item Name')['Total sellable'].sum()
            prod_report = prod_report.merge(inv_sum, left_index=True, right_index=True, how='left').rename(columns={'Total sellable': 'Stock'}).fillna(0)
        else:
            prod_report['Stock'] = 0

        state_report = create_growth_report('Customer State')
        city_report = create_growth_report('Customer City')

        # --- Comparison Logic ---
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
                cols = ['Prev Daily Avg Rev', 'Curr Daily Avg Rev', 'Rev Growth %', 'Prev Daily Avg Qty', 'Curr Daily Avg Qty', 'Qty Growth %']
                return merged[cols].sort_values('Curr Daily Avg Rev', ascending=False)
            
            comparison_sheets['Vs Prev Month - Products'] = generate_comparison('Product Name')
            comparison_sheets['Vs Prev Month - States'] = generate_comparison('Customer State')
            comparison_sheets['Vs Prev Month - Cities'] = generate_comparison('Customer City')

        # ==========================================
        # 7. WHATSAPP LOGIC (Exact Match)
        # ==========================================
        st.divider()
        st.subheader("📲 WhatsApp Summary")

        # Step A: Top 12 by Revenue
        top_12 = prod_report.sort_values('Last Day Rev', ascending=False).head(12)
        # Step B: From those 12, Top 5 by Growth
        top_5_growth = top_12.sort_values('Growth %', ascending=False).head(5)
        
        growth_lines = "\n".join([f"{i+1}. {name}: {row['Growth %']*100:.1f}%" for i, (name, row) in enumerate(top_5_growth.iterrows())])
        
        # State Data
        if not state_report.empty:
            top_state_name = state_report['Last Day Rev'].idxmax()
            top_state_val = state_report['Last Day Rev'].max()
            top_state_growth = state_report.loc[top_state_name, 'Growth %']
            state_str = f"🌍 *Top State:* {top_state_name} (₹{top_state_val:,.0f} | {top_state_growth*100:+.1f}%)"
        else:
            state_str = ""

        msg = (
            f"📊 *BLINKIT EXECUTIVE SUMMARY*\n"
            f"📅 Date: {last_date}\n\n"
            f"💰 *Last Day Rev:* ₹{last_day_rev:,.0f}\n"
            f"📦 *Last Day Qty:* {last_day_qty:,.0f} units\n"
            f"⚖️ *Daily Avg Qty:* {monthly_avg_qty:.1f} units\n"
            f"📈 *Status:* {'HIGHER' if last_day_rev > monthly_avg_revenue else 'LOWER'} vs Avg\n"
            f"{state_str}\n\n"
            f"🚀 *Top 5 Growth Leaders (Of Top 12 Sellers):*\n{growth_lines}\n\n"
            f"🏭 *Inventory:* {inv_df['Total sellable'].sum():,.0f} units"
        )
        
        c1, c2 = st.columns([3,1])
        c1.text_area("Message Preview", msg, height=300)
        c2.link_button("🚀 Send via WhatsApp", f"https://wa.me/918580904001?text={urllib.parse.quote(msg)}")

        # ==========================================
        # 8. EXCEL EXPORT (The Heavy Lifter)
        # ==========================================
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        workbook = writer.book

        # Formats
        header_fmt = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#1F4E78', 'border': 1})
        data_fmt = workbook.add_format({'border': 1})
        money_fmt = workbook.add_format({'border': 1, 'num_format': '₹#,##0'})
        qty_fmt = workbook.add_format({'border': 1, 'num_format': '0.0'}) 
        pct_fmt = workbook.add_format({'border': 1, 'num_format': '0.0%'})

        # 1. SUMMARY SHEET
        summary_ws = workbook.add_worksheet('Summary')
        summary_rows = [
            ('Report Date', str(last_date), data_fmt),
            ('Monthly Total Revenue', month_total, money_fmt),
            ('Daily Average Revenue', monthly_avg_revenue, money_fmt),
            ('Last Day Revenue', last_day_rev, money_fmt),
            ('Revenue Status', "HIGHER" if last_day_rev > monthly_avg_revenue else "LOWER", data_fmt),
            ('Daily Average Units', monthly_avg_qty, qty_fmt),
            ('Last Day Units', last_day_qty, qty_fmt),
            ('Total Sellable Stock', inv_df['Total sellable'].sum(), data_fmt)
        ]
        summary_ws.write(0, 0, 'Metric', header_fmt); summary_ws.write(0, 1, 'Value', header_fmt)
        for i, (m, v, fmt) in enumerate(summary_rows, 1):
            summary_ws.write(i, 0, m, data_fmt); summary_ws.write(i, 1, v, fmt)
        summary_ws.set_column('A:B', 30)

        # Helper Function for formatted sheets
        def write_sheet_formatted(df_input, sheet_name):
            df_input.to_excel(writer, sheet_name=sheet_name)
            ws = writer.sheets[sheet_name]
            ws.set_column('A:A', 40)
            ws.set_column('B:D', 15, money_fmt)
            ws.set_column('E:E', 12, pct_fmt)
            ws.set_column('F:H', 12, qty_fmt)

        cols_order = ['Last Day Rev', 'Daily Avg Rev', 'Total Rev', 'Growth %', 'Stock', 'Last Day Qty', 'Daily Avg Qty']

        # 2. All Products
        write_sheet_formatted(prod_report.sort_values('Last Day Rev', ascending=False)[cols_order], 'All Products')

        # 3. Top Products (Top 20)
        write_sheet_formatted(prod_report.sort_values('Last Day Rev', ascending=False)[cols_order].head(20), 'Top Products')

        # 4. Top States
        if not state_report.empty:
            state_report.sort_values('Last Day Rev', ascending=False).to_excel(writer, sheet_name='Top States')
            writer.sheets['Top States'].set_column('B:D', 15, money_fmt)

        # 5. Top Cities
        if not city_report.empty:
            city_report.sort_values('Last Day Rev', ascending=False).to_excel(writer, sheet_name='Top Cities')
            writer.sheets['Top Cities'].set_column('B:D', 15, money_fmt)

        # 6. Last Day Performers (Specific Logic)
        performers = prod_report[(prod_report['Last Day Rev'] > prod_report['Daily Avg Rev']) & (prod_report['Last Day Rev'] >= 1000)]
        performers_sorted = performers.sort_values('Growth %', ascending=False)
        write_sheet_formatted(performers_sorted[cols_order], 'Last Day Performers')

        # 7. Daily Sales
        daily_totals.to_excel(writer, sheet_name='Daily Sales', index=False)

        # 8. Weekly Patterns
        weekly_stats = daily_totals.groupby(daily_totals['Date'].apply(lambda x: x.strftime('%A')))[['Total Revenue', 'Total Quantity']].mean()
        # Sort Mon-Sun
        days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekly_stats = weekly_stats.reindex(days_order)
        weekly_stats['Last Day Rev'] = 0.0
        if last_day_name in weekly_stats.index:
            weekly_stats.at[last_day_name, 'Last Day Rev'] = last_day_rev
        weekly_stats.to_excel(writer, sheet_name='Weekly Patterns')

        # 9. Inventory Insights (Projected Inventory)
        wh_inv = inv_df.copy()
        if 'Incoming scheduled inventory' in wh_inv.columns and 'Last 30 days' in wh_inv.columns:
            wh_inv['Projected Inventory'] = wh_inv['Total sellable'] + wh_inv['Incoming scheduled inventory'] - wh_inv['Last 30 days']
            wh_inv.sort_values('Projected Inventory').to_excel(writer, sheet_name='Inventory Insights', index=False)

        # 10. Comparison Sheets
        if df_prev is not None:
            for name, data in comparison_sheets.items():
                data.to_excel(writer, sheet_name=name)
                writer.sheets[name].set_column('A:A', 40)
                writer.sheets[name].set_column('C:C', 12, pct_fmt)

        writer.close()
        output.seek(0)
        
        st.divider()
        st.subheader("📥 Download Complete Report")
        st.download_button(
            label="📥 Download Master Excel (All Sheets)",
            data=output,
            file_name=f"Blinkit_Master_{last_date}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

else:
    st.info("👈 Please upload your files to generate the dashboard.")
