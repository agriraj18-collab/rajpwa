import streamlit as st
import sqlite3
import pandas as pd
import re
from datetime import datetime

st.set_page_config(page_title="RAJPWA - குடும்ப நிதி & எச்சரிக்கை மேலாண்மை", page_icon="💎", layout="wide")

# --- DATABASE CONNECTION ---
def get_db():
    conn = sqlite3.connect("rajpwa_finance.db", check_same_thread=False)
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # 1. செலவுகள் அட்டவணை (Expenses)
    c.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            user TEXT,
            category TEXT,
            amount REAL,
            mode TEXT,
            merchant TEXT,
            notes TEXT
        )
    """)
    
    # 2. இதர எச்சரிக்கைகள் அட்டவணை (Other Alerts & Explanations)
    c.execute("""
        CREATE TABLE IF NOT EXISTS other_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            sender TEXT,
            category TEXT,
            explanation TEXT,
            raw_text TEXT
        )
    """)
    
    # 3. மளிகை இருப்பு (Grocery Stock)
    c.execute("""
        CREATE TABLE IF NOT EXISTS grocery_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT UNIQUE,
            stock REAL,
            unit TEXT,
            min_stock REAL
        )
    """)
    
    # 4. கடன்கள் (Loans)
    c.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loan_name TEXT UNIQUE,
            total_amount REAL,
            monthly_emi REAL,
            due_day INTEGER,
            remaining_months INTEGER
        )
    """)
    
    # ஆரம்ப மளிகைப் பட்டியல்
    c.execute("SELECT COUNT(*) FROM grocery_stock")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO grocery_stock (item_name, stock, unit, min_stock) VALUES (?, ?, ?, ?)", [
            ("பொன்னி அரிசி (Rice)", 20.0, "kg", 5.0),
            ("துவரம் பருப்பு (Toor Dal)", 2.0, "kg", 1.0),
            ("நல்லெண்ணெய் (Gingelly Oil)", 2.0, "Ltr", 1.0),
            ("தேயிலைத்தூள் (Tea Powder)", 0.5, "kg", 0.25)
        ])
    
    # ஆரம்பக் கடன்கள்
    c.execute("SELECT COUNT(*) FROM loans")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO loans (loan_name, total_amount, monthly_emi, due_day, remaining_months) VALUES (?, ?, ?, ?, ?)", [
            ("L&T பினான்ஸ் லோன்", 150000.0, 2754.0, 5, 24),
            ("ஸ்கூட்டர் லோன் (Scooter EMI)", 65000.0, 2100.0, 10, 18),
            ("ஹோம் லோன் (Home Loan)", 1200000.0, 11500.0, 7, 120)
        ])
    conn.commit()
    conn.close()

init_db()

# --- TOP HEADER ---
st.title("💎 RAJPWA — குடும்ப நிதி & எச்சரிக்கை மேலாண்மை")
current_month = datetime.now().strftime("%Y-%m")

# பயனர் தேர்வு
active_user = st.radio("தற்போதைய பயனர் யார்?", ["👤 Rajkumar (கணவர்)", "👩 மனைவி (Household)"], horizontal=True)

# 6 தனித்தனி டேப்கள்
tab_dash, tab_entry, tab_alerts, tab_grocery, tab_loans, tab_report = st.tabs([
    "📊 டேஷ்போர்டு", 
    "➕ செலவு பதிவு & SMS", 
    "🔔 இதர எச்சரிக்கைகள் (Others)",
    "🛒 மளிகை ஸ்டாக்", 
    "🏦 கடன்கள்", 
    "📈 குடும்ப அறிக்கை"
])

# ==================== 1. DASHBOARD ====================
with tab_dash:
    st.subheader(f"📅 {datetime.now().strftime('%B %Y')} மாதாந்திர நிலவரம்")
    conn = get_db()
    df = pd.read_sql_query(f"SELECT * FROM expenses WHERE strftime('%Y-%m', date) = '{current_month}'", conn)
    conn.close()
    
    total_spent = df['amount'].sum() if not df.empty else 0.0
    wife_spent = df[df['user'].str.contains('மனைவி')]['amount'].sum() if not df.empty else 0.0
    wife_remaining = max(0.0, 40000.0 - wife_spent)
    
    c1, c2, c3 = st.columns(3)
    c1.metric("குடும்ப மொத்த செலவு", f"₹{total_spent:,.2f}")
    c2.metric("மனைவி வீட்டு பட்ஜெட் (₹40k-ல்)", f"₹{wife_spent:,.2f} செலவு", f"மீதம்: ₹{wife_remaining:,.2f}")
    c3.metric("மாத சேமிப்பு நிலை", f"₹{max(0.0, 65000.0 - total_spent):,.2f}")
    
    if not df.empty:
        st.write("### 📌 துறை வாரியான செலவுகள்:")
        summary = df.groupby("category")["amount"].sum().reset_index()
        st.dataframe(summary.rename(columns={"category": "பிரிவு", "amount": "தொகை (₹)"}), use_container_width=True)
        
        # சமீபத்திய செலவுகள் மற்றும் நீக்கும் வசதி
        st.write("### 📋 சமீபத்திய செலவுகள் (நீக்க/திருத்த):")
        recent_df = df.sort_values(by="id", ascending=False)
        for _, r in recent_df.iterrows():
            d_col1, d_col2 = st.columns(2)
            d_col1.write(f"• **{r['date'][:16]}** | {r['user']} | **{r['category']}** : ₹{r['amount']:,.2f} ({r['notes']})")
            if d_col2.button(f"🗑️ நீக்கு (ID: {r['id']})", key=f"del_exp_{r['id']}"):
                conn = get_db()
                conn.execute("DELETE FROM expenses WHERE id = ?", (r['id'],))
                conn.commit()
                conn.close()
                st.success("செலவு நீக்கப்பட்டது!")
                st.rerun()

        # அனைத்து டெஸ்ட் பதிவுகளையும் அழிக்கும் வசதி
        with st.expander("⚠️ அனைத்து செலவுப் பதிவுகளையும் அழிக்க (Reset All Expenses)"):
            st.warning("அனைத்து டெஸ்ட் செலவுகளையும் அழித்து கணக்கை ₹0-க்கு மாற்ற வேண்டுமா?")
            if st.button("🚨 அனைத்து செலவுகளையும் அழி (Clear All)"):
                conn = get_db()
                conn.execute("DELETE FROM expenses")
                conn.commit()
                conn.close()
                st.success("அனைத்து பதிவுகளும் அழிக்கப்பட்டு கணக்கு ₹0 என ரீசெட் செய்யப்பட்டது!")
                st.rerun()

# ====================
