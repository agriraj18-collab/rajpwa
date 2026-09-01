import streamlit as st
import sqlite3
import pandas as pd
import re
from datetime import datetime

st.set_page_config(page_title="RAJPWA - குடும்ப நிதி மேலாண்மை", page_icon="💎", layout="wide")

# --- DATABASE CONNECTION ---
def get_db():
    conn = sqlite3.connect("rajpwa_finance.db", check_same_thread=False)
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS grocery_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT UNIQUE,
            stock REAL,
            unit TEXT,
            min_stock REAL
        )
    """)
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

# --- TOP HEADER & USER SWITCHER ---
st.title("💎 RAJPWA — குடும்ப நிதி & செலவு மேலாண்மை")
current_month = datetime.now().strftime("%Y-%m")

# பயனர் தேர்வு (கணவர் / மனைவி)
col_u1, col_u2 = st.columns()
active_user = col_u2.radio("தற்போதைய பயனர்:", ["👤 Rajkumar (கணவர்)", "👩 மனைவி (Household)"], horizontal=True)

tabs = st.tabs(["📊 டேஷ்போர்டு", "➕ செலவு பதிவு & SMS", "🛒 மளிகை ஸ்டாக்", "🏦 கடன்கள்", "📈 குடும்ப அறிக்கை"])

# ==================== 1. DASHBOARD ====================
with tabs[0]:
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

# ==================== 2. SMS & MANUAL INPUT ====================
with tabs:
    st.subheader("📲 செலவுகளைப் பதிவு செய்ய")
    
    st.markdown("#### 1. SMS டிகோடர் (வங்கி SMS-ஐ பேஸ்ட் செய்யவும்)")
    sms_txt = st.text_area("SMS உரை:", placeholder="வங்கி SMS-ஐ இங்கே பேஸ்ட் செய்யவும்...")
    if st.button("🔍 SMS-ஐப் படித்து சேமி"):
        if sms_txt:
            amt_match = re.search(r"(?:rs\.?|inr|\u20b9)\s*([\d,]+\.?\d*)", sms_txt, re.IGNORECASE)
            amt = float(amt_match.group(1).replace(",", "")) if amt_match else 0.0
            
            txt_low = sms_txt.lower()
            cat = "இதர செலவுகள்"
            if any(x in txt_low for x in ["petrol", "fuel", "diesel", "iocl", "hpcl", "bpcl"]):
                cat = "வாகனம் & Fuel"
            elif any(x in txt_low for x in ["lntfin", "loan", "emi"]):
                cat = "கடன்கள் & EMI"
            elif any(x in txt_low for x in ["tangedco", "electricity"]):
                cat = "மின்சாரக் கட்டணம்"
            elif any(x in txt_low for x in ["tea", "bakery", "snack"]):
                cat = "டீ & சிற்றுண்டி"
            elif any(x in txt_low for x in ["mart", "grocery", "vegetable"]):
                cat = "மளிகை & உணவு"
                
            conn = get_db()
            conn.execute("INSERT INTO expenses (date, user, category, amount, mode, merchant, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), active_user, cat, amt, "SMS / UPI", cat, sms_txt))
            conn.commit()
            conn.close()
            st.success(f"✅ {cat} செலவு ₹{amt:,.2f} ({active_user}) கணக்கில் சேர்க்கப்பட்டது!")
            st.rerun()

    st.markdown("---")
    st.markdown("#### 2. நேரடி மேனுவல் பதிவு (ரொக்க / சில்லறை செலவு)")
    with st.form("manual_entry"):
        col_a, col_b = st.columns(2)
        man_amt = col_a.number_input("தொகை (₹):", min_value=1.0, value=50.0, step=10.0)
        man_cat = col_b.selectbox("பிரிவு:", ["மளிகை & உணவு", "டீ & சிற்றுண்டி", "வாகனம் & Fuel", "மின்சாரக் கட்டணம்", "கடன்கள் & EMI", "விவசாயச் செலவு", "இதர செலவுகள்"])
        man_mode = col_a.selectbox("செலுத்திய முறை:", ["ரொக்கம் (Cash)", "PhonePe / GPay", "வங்கி கணக்கு"])
        man_notes = col_b.text_input("குறிப்பு:", "")
        
        if st.form_submit_button("➕ செலவைச் சேமி"):
            conn = get_db()
            conn.execute("INSERT INTO expenses (date, user, category, amount, mode, merchant, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), active_user, man_cat, man_amt, man_mode, man_notes or "நேரடிப் பதிவு", man_notes))
            conn.commit()
            conn.close()
            st.success(f"✅ ₹{man_amt:,.2f} ({man_cat}) பதிவானது!")
            st.rerun()

# ==================== 3. GROCERY STOCK ====================
with tabs:
    st.subheader("🛒 மளிகை பொருட்கள் கையிருப்பு மேலாண்மை")
    conn = get_db()
    g_df = pd.read_sql_query("SELECT * FROM grocery_stock", conn)
    conn.close()
    
    col_l, col_r = st.columns(2)
    with col_l:
        st.write("### 📦 கையிருப்பு அளவு:")
        for _, row in g_df.iterrows():
            c1, c2, c3, c4 = st.columns()
            c1.write(f"**{row['item_name']}**")
            c2.write(f"இருப்பு: **{row['stock']} {row['unit']}**")
            if c3.button("➕ 1", key=f"add_{row['id']}"):
                conn = get_db()
                conn.execute("UPDATE grocery_stock SET stock = stock + 1 WHERE id = ?", (row['id'],))
                conn.commit()
                conn.close()
                st.rerun()
            if c4.button("➖ 1", key=f"sub_{row['id']}"):
                conn = get_db()
                conn.execute("UPDATE grocery_stock SET stock = MAX(0.0, stock - 1) WHERE id = ?", (row['id'],))
                conn.commit()
                conn.close()
                st.rerun()
                
    with col_r:
        st.write("### 🚨 வாங்க வேண்டிய பொருட்கள் (Reorder List):")
        low = g_df[g_df['stock'] <= g_df['min_stock']]
        if not low.empty:
            for _, r in low.iterrows():
                st.error(f"⚠️ **{r['item_name']}** (மீதம்: {r['stock']} {r['unit']})")
        else:
            st.success("✅ அனைத்துப் பொருட்களும் தேவையான அளவு கையிருப்பில் உள்ளன!")

# ==================== 4. LOANS ====================
with tabs:
    st.subheader("🏦 கடன் & EMI கண்காணிப்பு")
    conn = get_db()
    l_df = pd.read_sql_query("SELECT * FROM loans", conn)
    conn.close()
    st.dataframe(l_df.rename(columns={
        "loan_name": "கடன் பெயர்", "total_amount": "அசல் / இருப்பு (₹)",
        "monthly_emi": "மாத தவணை (₹)", "due_day": "தவணை தேதி", "remaining_months": "மீதமுள்ள மாதங்கள்"
    }), use_container_width=True)

# ==================== 5. FAMILY PEACE REPORT ====================
with tabs:
    st.subheader("📈 குடும்ப மாதாந்திர நிதி அறிக்கை")
    conn = get_db()
    rep = pd.read_sql_query(f"SELECT category, user, SUM(amount) as total FROM expenses WHERE strftime('%Y-%m', date) = '{current_month}' GROUP BY category, user", conn)
    conn.close()
    
    st.info(f"### 📋 {datetime.now().strftime('%B %Y')} மாத செலவு சுருக்கம்")
    if not rep.empty:
        st.dataframe(rep.rename(columns={"category": "பிரிவு", "user": "செலவு செய்தவர்", "total": "தொகை (₹)"}), use_container_width=True)
        st.success(f"### 💵 மொத்த குடும்ப செலவு: ₹{rep['total'].sum():,.2f}")
    else:
        st.write("இந்த மாத செலவுகள் எதுவும் இன்னும் பதிவாகவில்லை.")
