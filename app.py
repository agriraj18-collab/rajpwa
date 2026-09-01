import streamlit as st
import sqlite3
import pandas as pd
import re
import xml.etree.ElementTree as ET
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
    
    # 2. இதர எச்சரிக்கைகள் அட்டவணை (Other Alerts)
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

# --- HELPER FUNCTION: EXTRACT AMOUNT SAFELY ---
def extract_amount(text):
    if not text:
        return 0.0
    match = re.search(r"(?:rs\.?|inr|\u20b9)\s*([0-9]+(?:,[0-9]+)*(?:\.[0-9]+)?)", text, re.IGNORECASE)
    if match:
        raw_val = match.group(1).replace(",", "").strip()
        try:
            val = float(raw_val)
            if val > 0:
                return val
        except ValueError:
            pass
    return 0.0

# --- TOP HEADER ---
st.title("💎 RAJPWA — குடும்ப நிதி & எச்சரிக்கை மேலாண்மை")
current_month = datetime.now().strftime("%Y-%m")

# பயனர் தேர்வு
active_user = st.radio("தற்போதைய பயனர் யார்?", ["👤 Rajkumar (கணவர்)", "👩 மனைவி (Household)"], horizontal=True)

# 7 தனித்தனி டேப்கள்
tab_dash, tab_entry, tab_upload, tab_alerts, tab_grocery, tab_loans, tab_report = st.tabs([
    "📊 டேஷ்போர்டு", 
    "➕ செலவு பதிவு & SMS", 
    "📁 பழைய SMS & ஸ்டேட்மென்ட்",
    "🔔 இதர எச்சரிக்கைகள்", 
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

# ==================== 2. SMS & MANUAL INPUT ====================
with tab_entry:
    st.subheader("📲 செலவு & SMS டிகோடர்")
    
    st.markdown("#### 1. SMS டிகோடர் (வங்கி SMS-ஐ பேஸ்ட் செய்யவும்)")
    sms_txt = st.text_area("SMS உரை:", placeholder="வங்கி செலவு, OTP, மேண்டேட், விளம்பரம் அல்லது பங்குச் சந்தை மெசேஜ்கள்...")
    
    if st.button("🔍 SMS-ஐப் படித்து வகைப்படுத்தவும்"):
        if sms_txt:
            txt_low = sms_txt.lower()
            amt = extract_amount(sms_txt)
            is_debit = any(w in txt_low for w in ["debit", "debited", "spent", "paid", "recharge of", "withdrawn"])
            
            # அ. செலவு மெசேஜ்
            if is_debit and amt > 0:
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
                st.success(f"💳 **செலவுப் பதிவு:** {cat} செலவு ₹{amt:,.2f} ({active_user}) கணக்கில் சேர்க்கப்பட்டது!")
                st.rerun()
                
            # ஆ. செலவு அல்லாத இதர எச்சரிக்கைகள்
            else:
                cat = "இதர அறிவிப்பு (General Alert)"
                explanation = "தகவல் அறிவிப்பு செய்தி (செலவு எதுவும் இல்லை)."
                
                if "otp" in txt_low or "one-time password" in txt_low:
                    cat = "🔐 பாதுகாப்பு & OTP"
                    explanation = "ஆப் உள்நுழைவு அல்லது சரிபார்ப்புக்கான OTP வந்துள்ளது (செலவு இல்லை)."
                elif "mandate" in txt_low:
                    cat = "🏦 வங்கி & UPI Mandate"
                    explanation = "UPI ஆட்டோபே / மேண்டேட் பதிவு செய்ததற்கான அறிவிப்பு (பணம் எடுக்கப்படவில்லை)."
                elif any(x in txt_low for x in ["stcks", "buy now", "target", "stock", "nifty"]):
                    cat = "📈 பங்குச் சந்தை டிப்ஸ்"
                    explanation = "பங்கு வாங்குவதற்கான பரிந்துரை / வர்த்தக அறிவிப்பு."
                elif any(x in txt_low for x in ["application", "pashaz", "status"]):
                    cat = "📄 சேவை & விண்ணப்ப நிலை"
                    explanation = "விண்ணப்பம் தொடர்பான சேவை அறிவிப்பு."
                elif any(x in txt_low for x in ["special live", "worth", "sale", "offer", "discount"]):
                    cat = "📢 விளம்பரம் & சலுகைகள்"
                    explanation = "தள்ளுபடி விற்பனை / தயாரிப்பு விளம்பர அறிவிப்பு."
                    
                conn = get_db()
                conn.execute("INSERT INTO other_alerts (date, sender, category, explanation, raw_text) VALUES (?, ?, ?, ?, ?)",
                             (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "SMS", cat, explanation, sms_txt))
                conn.commit()
                conn.close()
                st.info(f"🔔 **{cat}:** {explanation} (இது 'இதர எச்சரிக்கைகள்' டேபில் சேர்க்கப்பட்டுள்ளது; செலவில் கூட்டப்படவில்லை).")
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

# ==================== 3. UPLOAD OLD SMS & STATEMENTS ====================
with tab_upload:
    st.subheader("📁 பழைய 1 வருட SMS & வங்கி அறிக்கைகள் பதிவேற்றம்")
    st.caption("கடந்த 1 வருட மெசேஜ்கள் அல்லது SBI / Credit Card அறிக்கைகளை (CSV / Excel / XML) இங்கே அப்லோட் செய்யலாம்.")
    
    st.markdown("#### 📥 1. பழைய SMS கோப்பு அப்லோட் (XML / JSON / CSV Backup)")
    sms_file = st.file_uploader("SMS Backup கோப்பைத் தேர்வு செய்யவும்:", type=["xml", "json", "csv"], key="sms_upload")
    
    if sms_file is not None:
        if st.button("🚀 பழைய SMS-களைப் படித்து டேட்டாபேஸில் ஏற்றவும்"):
            try:
                count_added = 0
                conn = get_db()
                batch_records = []
                
                # XML Backup parsing with safe exception handling
                if sms_file.name.endswith(".xml"):
                    tree = ET.parse(sms_file)
                    root = tree.getroot()
                    for sms in root.findall("sms"):
                        try:
                            body = sms.get("body", "")
                            if not body:
                                continue
                            date_ms = int(sms.get("date", "0"))
                            date_str = pd.to_datetime(date_ms, unit="ms").strftime("%Y-%m-%d %H:%M:%S")
                            address = sms.get("address", "SMS")
                            
                            txt_low = body.lower()
                            amt = extract_amount(body)
                            is_debit = any(w in txt_low for w in ["debit", "debited", "spent", "paid", "recharge of", "withdrawn"])
                            
                            if is_debit and amt > 0:
                                cat = "இதர செலவுகள்"
                                if any(x in txt_low for x in ["petrol", "fuel", "diesel", "iocl", "hpcl", "bpcl", "fastag"]):
                                    cat = "வாகனம் & Fuel"
                                elif any(x in txt_low for x in ["lntfin", "loan", "emi"]):
                                    cat = "கடன்கள் & EMI"
                                elif any(x in txt_low for x in ["tangedco", "electricity"]):
                                    cat = "மின்சாரக் கட்டணம்"
                                elif any(x in txt_low for x in ["mart", "grocery", "vegetable"]):
                                    cat = "மளிகை & உணவு"
                                    
                                batch_records.append((date_str, active_user, cat, amt, "Old SMS", address, body))
                        except Exception:
                            continue
                            
                if batch_records:
                    conn.executemany("INSERT INTO expenses (date, user, category, amount, mode, merchant, notes) VALUES (?, ?, ?, ?, ?, ?, ?)", batch_records)
                    conn.commit()
                    count_added = len(batch_records)
                    
                conn.close()
                st.success(f"🎉 வெற்றி! {count_added} பழைய செலவுப் பரிவர்த்தனைகள் வெற்றிகரமாக டேட்டாபேஸில் சேர்க்கப்பட்டன!")
                st.rerun()
            except Exception as e:
                st.error(f"பிழை: {e}")

    st.markdown("---")
    st.markdown("#### 📊 2. வங்கி / கிரெடிட் கார்டு அறிக்கை அப்லோட் (CSV / Excel)")
    bank_file = st.file_uploader("வங்கி அறிக்கை கோப்பைத் தேர்வு செய்யவும்:", type=["csv", "xlsx", "xls"], key="bank_upload")
    
    if bank_file is not None:
        if st.button("📑 வங்கி அறிக்கையைப் படித்து தணிக்கை செய்க"):
            try:
                if bank_file.name.endswith(".csv"):
                    b_df = pd.read_csv(bank_file)
                else:
                    b_df = pd.read_excel(bank_file)
                
                st.write("##### 📄 அறிக்கையின் மாதிரித் தரவுகள்:")
                st.dataframe(b_df.head(5), use_container_width=True)
                st.success(f"✅ அறிக்கை படிக்கப்பட்டது ({len(b_df)} வரிகள் கண்டறியப்பட்டன)!")
            except Exception as e:
                st.error(f"பிழை: {e}")

# ==================== 4. OTHER ALERTS ====================
with tab_alerts:
    st.subheader("🔔 இதர எச்சரிக்கைகள் & தமிழ் விளக்கம் (Non-Expense Alerts)")
    st.caption("செலவு அல்லாத OTP, வங்கி மேண்டேட், பங்குச் சந்தை மற்றும் சேவை அறிவிப்புகள் இங்கே சேமிக்கப்படும்.")
    
    conn = get_db()
    alerts_df = pd.read_sql_query("SELECT id, date, category, explanation, raw_text FROM other_alerts ORDER BY id DESC", conn)
    conn.close()
    
    if not alerts_df.empty:
        for idx, row in alerts_df.iterrows():
            with st.expander(f"{row['category']} — {row['date']}"):
                st.write(f"💡 **விளக்கம்:** {row['explanation']}")
                st.code(row['raw_text'], language="text")
                if st.button("🗑️ இந்த எச்சரிக்கையை நீக்கு", key=f"del_alert_{row['id']}"):
                    conn = get_db()
                    conn.execute("DELETE FROM other_alerts WHERE id = ?", (row['id'],))
                    conn.commit()
                    conn.close()
                    st.success("எச்சரிக்கை நீக்கப்பட்டது!")
                    st.rerun()
    else:
        st.write("இதர எச்சரிக்கைகள் எதுவும் இதுவரை வரவில்லை.")

# ==================== 5. GROCERY STOCK ====================
with tab_grocery:
    st.subheader("🛒 மளிகை பொருட்கள் கையிருப்பு மேலாண்மை")
    conn = get_db()
    g_df = pd.read_sql_query("SELECT * FROM grocery_stock", conn)
    conn.close()
    
    col_left, col_right = st.columns(2)
    with col_left:
        st.write("### 📦 கையிருப்பு அளவு:")
        for _, row in g_df.iterrows():
            st.write(f"**{row['item_name']}** — இருப்பு: **{row['stock']} {row['unit']}**")
            btn_add, btn_sub = st.columns(2)
            if btn_add.button(f"➕ 1 ({row['item_name']})", key=f"add_{row['id']}"):
                conn = get_db()
                conn.execute("UPDATE grocery_stock SET stock = stock + 1 WHERE id = ?", (row['id'],))
                conn.commit()
                conn.close()
                st.rerun()
            if btn_sub.button(f"➖ 1 ({row['item_name']})", key=f"sub_{row['id']}"):
                conn = get_db()
                conn.execute("UPDATE grocery_stock SET stock = MAX(0.0, stock - 1) WHERE id = ?", (row['id'],))
                conn.commit()
                conn.close()
                st.rerun()
            st.markdown("---")
                
    with col_right:
        st.write("### 🚨 வாங்க வேண்டிய பொருட்கள் (Reorder List):")
        low = g_df[g_df['stock'] <= g_df['min_stock']]
        if not low.empty:
            for _, r in low.iterrows():
                st.error(f"⚠️ **{r['item_name']}** (மீதம்: {r['stock']} {r['unit']})")
        else:
            st.success("✅ அனைத்துப் பொருட்களும் தேவையான அளவு கையிருப்பில் உள்ளன!")

# ==================== 6. LOANS ====================
with tab_loans:
    st.subheader("🏦 கடன் & EMI கண்காணிப்பு")
    conn = get_db()
    l_df = pd.read_sql_query("SELECT * FROM loans", conn)
    conn.close()
    st.dataframe(l_df.rename(columns={
        "loan_name": "கடன் பெயர்", "total_amount": "அசல் / இருப்பு (₹)",
        "monthly_emi": "மாத தவணை (₹)", "due_day": "தவணை தேதி", "remaining_months": "மீதமுள்ள மாதங்கள்"
    }), use_container_width=True)

# ==================== 7. FAMILY PEACE REPORT ====================
with tab_report:
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
