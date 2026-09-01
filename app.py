import streamlit as st
import sqlite3
import pandas as pd
import re
import xml.etree.ElementTree as ET
import plotly.express as px
from datetime import datetime

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="RAJPWA — குடும்ப நிதி & செலவு மேலாண்மை",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- MODERN CUSTOM CSS STYLING ---
st.markdown("""
<style>
    .main {
        background-color: #f8fafc;
        font-family: 'Segoe UI', Roboto, sans-serif;
    }
    .app-header {
        background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 50%, #06b6d4 100%);
        padding: 24px;
        border-radius: 16px;
        color: white;
        text-align: center;
        margin-bottom: 20px;
        box-shadow: 0 10px 25px -5px rgba(59, 130, 246, 0.3);
    }
    .app-header h1 {
        color: white !important;
        font-weight: 800;
        font-size: 28px;
        margin: 0;
        letter-spacing: 0.5px;
    }
    .app-header p {
        color: #e0f2fe !important;
        font-size: 14px;
        margin-top: 6px;
        margin-bottom: 0;
    }
    .metric-card {
        background: white;
        padding: 20px;
        border-radius: 14px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        text-align: center;
        transition: transform 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 15px -3px rgba(0, 0, 0, 0.08);
    }
    .metric-title {
        font-size: 13px;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-value {
        font-size: 24px;
        font-weight: 700;
        color: #0f172a;
        margin-top: 6px;
    }
    .metric-badge {
        display: inline-block;
        font-size: 12px;
        padding: 3px 10px;
        border-radius: 20px;
        margin-top: 6px;
        font-weight: 600;
    }
    .badge-green { background: #dcfce7; color: #166534; }
    .badge-blue { background: #e0f2fe; color: #0369a1; }
    .badge-orange { background: #ffedd5; color: #9a3412; }
</style>
""", unsafe_allow_html=True)

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
        CREATE TABLE IF NOT EXISTS other_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            sender TEXT,
            category TEXT,
            explanation TEXT,
            raw_text TEXT
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

# --- APP HEADER BANNER ---
st.markdown("""
<div class="app-header">
    <h1>💎 RAJPWA</h1>
    <p>குடும்ப நிதி, மளிகை இருப்பு & நிகழ்நேரச் செலவு மேலாண்மை செயலி</p>
</div>
""", unsafe_allow_html=True)

# பயனர் தேர்வு
col_user, col_space = st.columns(2)
active_user = col_user.radio("👤 தற்போதைய பயனர் யார்?", ["👤 Rajkumar (கணவர்)", "👩 மனைவி (Household)"], horizontal=True)

# 7 தனித்தனி டேப்கள்
tab_dash, tab_history, tab_entry, tab_upload, tab_alerts, tab_grocery, tab_loans = st.tabs([
    "📊 டேஷ்போர்டு", 
    "📜 வரலாற்று வரைபடம்",
    "➕ புதிய செலவு & SMS", 
    "📁 பழைய SMS & ஸ்டேட்மென்ட்",
    "🔔 இதர எச்சரிக்கைகள்", 
    "🛒 மளிகை ஸ்டாக்", 
    "🏦 கடன்கள்"
])

# ==================== 1. DASHBOARD ====================
with tab_dash:
    conn = get_db()
    all_df = pd.read_sql_query("SELECT * FROM expenses", conn)
    conn.close()
    
    available_months = ["இந்த மாதம் (நடப்பு மாதம்)"]
    if not all_df.empty:
        all_df['month_year'] = pd.to_datetime(all_df['date'], errors='coerce').dt.strftime('%Y-%m')
        unique_months = sorted([m for m in all_df['month_year'].dropna().unique() if m.startswith('202')], reverse=True)
        available_months += unique_months
        
    col_m1, col_m2 = st.columns(2)
    selected_view = col_m1.selectbox("📅 எந்த மாதத்திற்கான கணக்கு பார்க்க வேண்டும்?", available_months)
    
    current_m = datetime.now().strftime("%Y-%m")
    target_month = current_m if selected_view == "இந்த மாதம் (நடப்பு மாதம்)" else selected_view
        
    df = all_df[all_df['month_year'] == target_month] if not all_df.empty and 'month_year' in all_df else pd.DataFrame()
    
    total_spent = df['amount'].sum() if not df.empty else 0.0
    wife_spent = df[df['user'].str.contains('மனைவி')]['amount'].sum() if not df.empty else 0.0
    wife_remaining = max(0.0, 40000.0 - wife_spent)
    savings_est = max(0.0, 65000.0 - total_spent)
    
    # Modern Metric Cards
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">💳 {target_month} மொத்த செலவு</div>
        <div class="metric-value" style="color:#ef4444;">₹{total_spent:,.2f}</div>
        <span class="metric-badge badge-orange">{len(df)} பரிவர்த்தனைகள்</span>
    </div>
    """, unsafe_allow_html=True)
    
    c2.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">👩 மனைவி வீட்டு பட்ஜெட் (₹40k)</div>
        <div class="metric-value" style="color:#0284c7;">₹{wife_spent:,.2f}</div>
        <span class="metric-badge badge-blue">மீதம்: ₹{wife_remaining:,.2f}</span>
    </div>
    """, unsafe_allow_html=True)
    
    c3.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">💰 மாத சேமிப்பு நிலை</div>
        <div class="metric-value" style="color:#10b981;">₹{savings_est:,.2f}</div>
        <span class="metric-badge badge-green">நிகர சேமிப்பு</span>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    if not df.empty:
        col_chart, col_table = st.columns(2)
        summary = df.groupby("category")["amount"].sum().reset_index()
        
        with col_chart:
            st.write("### 🍩 துறை வாரியான செலவுப் பகிர்வு:")
            fig = px.pie(summary, values="amount", names="category", hole=0.45,
                         color_discrete_sequence=px.colors.qualitative.Prism)
            fig.update_traces(textposition='inside', textinfo='percent+label')
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=300)
            st.plotly_chart(fig, use_container_width=True)
            
        with col_table:
            st.write("### 📊 செலவு அட்டவணை:")
            st.dataframe(summary.rename(columns={"category": "பிரிவு", "amount": "தொகை (₹)"}), use_container_width=True, height=280)
            
        # சமீபத்திய செலவுகள் பட்டியல்
        st.write("### 📋 அந்த மாத பரிவர்த்தனைகள் (நீக்க/திருத்த):")
        recent_df = df.sort_values(by="id", ascending=False)
        for _, r in recent_df.head(25).iterrows():
            d_col1, d_col2 = st.columns(2)
            d_col1.write(f"• **{r['date'][:16]}** | **{r['category']}** : ₹{r['amount']:,.2f} | *{r['notes'][:45]}*")
            if d_col2.button(f"🗑️ நீக்கு (ID: {r['id']})", key=f"del_exp_{r['id']}"):
                conn = get_db()
                conn.execute("DELETE FROM expenses WHERE id = ?", (r['id'],))
                conn.commit()
                conn.close()
                st.success("செலவு நீக்கப்பட்டது!")
                st.rerun()

# ==================== 2. HISTORY & TRENDS ====================
with tab_history:
    st.subheader("📜 கடந்த கால வரலாற்று வரைபடங்கள் & அறிக்கைகள்")
    conn = get_db()
    h_df = pd.read_sql_query("SELECT * FROM expenses ORDER BY date DESC", conn)
    conn.close()
    
    if not h_df.empty:
        h_df['month_year'] = pd.to_datetime(h_df['date'], errors='coerce').dt.strftime('%Y-%m')
        valid_history = h_df[h_df['month_year'].str.startswith('202', na=False)]
        
        # Interactive Monthly Bar Chart with Plotly
        monthly_trend = valid_history.groupby("month_year")["amount"].sum().reset_index()
        monthly_trend = monthly_trend.sort_values(by="month_year")
        
        st.write("### 📊 மாதம் தோறும் செலவு வளர்ச்சி வரைபடம்:")
        bar_fig = px.bar(monthly_trend, x="month_year", y="amount",
                         labels={"month_year": "மாதம் / வருடம்", "amount": "மொத்த செலவு (₹)"},
                         color="amount", color_continuous_scale="Blues", text_auto=".2s")
        bar_fig.update_layout(height=350, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(bar_fig, use_container_width=True)
        
        st.write("### 📑 அனைத்து பரிவர்த்தனைகளின் பட்டியல்:")
        st.dataframe(valid_history[['date', 'user', 'category', 'amount', 'merchant', 'notes']].rename(columns={
            'date': 'தேதி & நேரம்', 'user': 'பயனர்', 'category': 'பிரிவு', 'amount': 'தொகை (₹)', 'merchant': 'சேவை/கடை', 'notes': 'முழு உரை'
        }), use_container_width=True, height=400)
    else:
        st.info("டேட்டாபேஸில் இன்னும் பழைய பரிவர்த்தனைகள் எதுவும் இல்லை.")

# ==================== 3. SMS & MANUAL INPUT ====================
with tab_entry:
    st.subheader("📲 புதிய செலவு & SMS டிகோடர்")
    
    col_input1, col_input2 = st.columns(2)
    
    with col_input1:
        st.markdown("#### 1. 🔍 SMS டிகோடர் (பேஸ்ட் செய்யவும்)")
        sms_txt = st.text_area("SMS உரை:", placeholder="வங்கி செலவு, OTP, மேண்டேட், விளம்பரம் அல்லது பங்குச் சந்தை மெசேஜ்கள்...")
        if st.button("🚀 SMS-ஐப் படித்து வகைப்படுத்துக"):
            if sms_txt:
                txt_low = sms_txt.lower()
                amt = extract_amount(sms_txt)
                is_debit = any(w in txt_low for w in ["debit", "debited", "spent", "paid", "recharge of", "withdrawn"])
                
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
                else:
                    cat = "இதர அறிவிப்பு (General Alert)"
                    explanation = "தகவல் அறிவிப்பு செய்தி (செலவு எதுவும் இல்லை)."
                    if "otp" in txt_low or "one-time password" in txt_low:
                        cat = "🔐 பாதுகாப்பு & OTP"
                        explanation = "ஆப் உள்நுழைவு அல்லது சரிபார்ப்புக்கான OTP வந்துள்ளது."
                    elif "mandate" in txt_low:
                        cat = "🏦 வங்கி & UPI Mandate"
                        explanation = "UPI ஆட்டோபே / மேண்டேட் பதிவு செய்ததற்கான அறிவிப்பு."
                    elif any(x in txt_low for x in ["stcks", "buy now", "target", "stock", "nifty"]):
                        cat = "📈 பங்குச் சந்தை டிப்ஸ்"
                        explanation = "பங்கு வாங்குவதற்கான பரிந்துரை அறிவிப்பு."
                        
                    conn = get_db()
                    conn.execute("INSERT INTO other_alerts (date, sender, category, explanation, raw_text) VALUES (?, ?, ?, ?, ?)",
                                 (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "SMS", cat, explanation, sms_txt))
                    conn.commit()
                    conn.close()
                    st.info(f"🔔 **{cat}:** {explanation}")
                    st.rerun()

    with col_input2:
        st.markdown("#### 2. ✍️ நேரடி மேனுவல் பதிவு (ரொக்கச் செலவு)")
        with st.form("manual_entry_form"):
            man_amt = st.number_input("தொகை (₹):", min_value=1.0, value=50.0, step=10.0)
            man_cat = st.selectbox("பிரிவு:", ["மளிகை & உணவு", "டீ & சிற்றுண்டி", "வாகனம் & Fuel", "மின்சாரக் கட்டணம்", "கடன்கள் & EMI", "விவசாயச் செலவு", "இதர செலவுகள்"])
            man_mode = st.selectbox("செலுத்திய முறை:", ["ரொக்கம் (Cash)", "PhonePe / GPay", "வங்கி கணக்கு"])
            man_notes = st.text_input("குறிப்பு:", "")
            
            if st.form_submit_button("➕ செலவைச் சேமிக்கவும்"):
                conn = get_db()
                conn.execute("INSERT INTO expenses (date, user, category, amount, mode, merchant, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), active_user, man_cat, man_amt, man_mode, man_notes or "நேரடிப் பதிவு", man_notes))
                conn.commit()
                conn.close()
                st.success(f"✅ ₹{man_amt:,.2f} ({man_cat}) பதிவானது!")
                st.rerun()

# ==================== 4. UPLOAD OLD SMS & STATEMENTS ====================
with tab_upload:
    st.subheader("📁 பழைய SMS & வங்கி அறிக்கைகள் பதிவேற்றம்")
    st.caption("கடந்த 1 வருட மெசேஜ்கள் அல்லது SBI / Credit Card அறிக்கைகளை (CSV / Excel / XML) இங்கே அப்லோட் செய்யலாம்.")
    
    sms_file = st.file_uploader("📥 SMS Backup கோப்பைத் தேர்வு செய்யவும் (XML / JSON):", type=["xml", "json", "csv"], key="sms_upload")
    if sms_file is not None:
        if st.button("🚀 பழைய SMS-களைப் படித்து ஏற்றவும்"):
            try:
                conn = get_db()
                batch_records = []
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
                                elif any(x in txt_low for x in ["mart", "grocery"]):
                                    cat = "மளிகை & உணவு"
                                batch_records.append((date_str, active_user, cat, amt, "Old SMS", address, body))
                        except Exception:
                            continue
                if batch_records:
                    conn.executemany("INSERT INTO expenses (date, user, category, amount, mode, merchant, notes) VALUES (?, ?, ?, ?, ?, ?, ?)", batch_records)
                    conn.commit()
                    st.success(f"🎉 {len(batch_records)} பழைய செலவுகள் வெற்றிகரமாக சேர்க்கப்பட்டன!")
                conn.close()
                st.rerun()
            except Exception as e:
                st.error(f"பிழை: {e}")

# ==================== 5. OTHER ALERTS ====================
with tab_alerts:
    st.subheader("🔔 இதர எச்சரிக்கைகள் & தமிழ் விளக்கம்")
    conn = get_db()
    alerts_df = pd.read_sql_query("SELECT id, date, category, explanation, raw_text FROM other_alerts ORDER BY id DESC", conn)
    conn.close()
    if not alerts_df.empty:
        for idx, row in alerts_df.iterrows():
            with st.expander(f"{row['category']} — {row['date']}"):
                st.write(f"💡 **விளக்கம்:** {row['explanation']}")
                st.code(row['raw_text'], language="text")
                if st.button("🗑️ நீக்கு", key=f"del_alert_{row['id']}"):
                    conn = get_db()
                    conn.execute("DELETE FROM other_alerts WHERE id = ?", (row['id'],))
                    conn.commit()
                    conn.close()
                    st.rerun()
    else:
        st.info("இதர எச்சரிக்கைகள் எதுவும் இல்லை.")

# ==================== 6. GROCERY STOCK ====================
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
        st.write("### 🚨 வாங்க வேண்டிய பொருட்கள்:")
        low = g_df[g_df['stock'] <= g_df['min_stock']]
        if not low.empty:
            for _, r in low.iterrows():
                st.error(f"⚠️ **{r['item_name']}** (மீதம்: {r['stock']} {r['unit']})")
        else:
            st.success("✅ அனைத்துப் பொருட்களும் போதிய அளவில் உள்ளன!")

# ==================== 7. LOANS ====================
with tab_loans:
    st.subheader("🏦 கடன் & EMI கண்காணிப்பு")
    conn = get_db()
    l_df = pd.read_sql_query("SELECT * FROM loans", conn)
    conn.close()
    st.dataframe(l_df.rename(columns={
        "loan_name": "கடன் பெயர்", "total_amount": "அசல் / இருப்பு (₹)",
        "monthly_emi": "மாத தவணை (₹)", "due_day": "தவணை தேதி", "remaining_months": "மீதமுள்ள மாதங்கள்"
    }), use_container_width=True)
