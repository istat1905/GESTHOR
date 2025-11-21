import streamlit as st
import pandas as pd
import numpy as np
import pdfplumber
import re
import io
from datetime import datetime

# --- Configuration page ---
st.set_page_config(page_title="GESTHOR – Master", page_icon="📦", layout="wide")

# --- Base de données utilisateurs (simulation) ---
USERS_DB = {
    "admin": {"password": "admin123", "role": "admin"},
    "user1": {"password": "user123", "role": "user"},
}

def check_password(username, password):
    if username in USERS_DB and USERS_DB[username]["password"] == password:
        return True, USERS_DB[username]["role"]
    return False, None

# --- Session state pour authentification ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "username" not in st.session_state:
    st.session_state.username = None
if "user_role" not in st.session_state:
    st.session_state.user_role = None

# --- Connexion ---
if not st.session_state.authenticated:
    st.markdown("### 🔐 Connexion requise")
    with st.form("login_form"):
        username = st.text_input("👤 Identifiant")
        password = st.text_input("🔒 Mot de passe", type="password")
        submit = st.form_submit_button("Se connecter")
        if submit:
            valid, role = check_password(username, password)
            if valid:
                st.session_state.authenticated = True
                st.session_state.username = username
                st.session_state.user_role = role
                st.success(f"✅ Bienvenue {username} !")
                st.experimental_rerun()
            else:
                st.error("❌ Identifiant ou mot de passe incorrect")
    st.stop()

# --- Sidebar ---
st.sidebar.header(f"👋 {st.session_state.username} ({st.session_state.user_role})")
if st.sidebar.button("🚪 Déconnexion"):
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.user_role = None
    st.experimental_rerun()

st.sidebar.header("📂 Uploads")
f_stock = st.sidebar.file_uploader("Stock Excel", type=["xlsx"])
f_pdf = st.sidebar.file_uploader("Commandes PDF", type=["pdf"])

search_input = st.sidebar.text_input("🔍 Recherche article", placeholder="Code ou libellé...")

# --- Fonctions ---
@st.cache_data
def load_stock(file):
    df = pd.read_excel(file)
    df.columns = [c.strip() for c in df.columns]
    df["N° article."] = df["N° article."].astype(str).str.strip()
    df["Inventory"] = pd.to_numeric(df["Inventory"], errors="coerce").fillna(0)
    df["Qty. per Sales Unit of Measure"] = pd.to_numeric(df["Qty. per Sales Unit of Measure"], errors="coerce").fillna(1)
    df["Stock Colis"] = df["Inventory"] / df["Qty. per Sales Unit of Measure"].replace(0,1)
    conditions = [(df["Inventory"] <= 0), (df["Inventory"] < 500)]
    choices = ["Rupture", "Faible"]
    df["Statut"] = np.select(conditions, choices, default="OK")
    return df

def extract_pdf_force(pdf_file):
    orders = []
    try:
        with pdfplumber.open(pdf_file) as pdf:
            text = "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
        # Trouver toutes les commandes
        cmd_matches = list(re.finditer(r"Commande\s*n[°º]?\s*[:\s-]*?(\d{5,10})", text))
        if not cmd_matches: return pd.DataFrame()
        cmd_positions = {m.start(): m.group(1) for m in cmd_matches}
        cmd_starts = sorted(cmd_positions.keys())

        # Pattern ligne produit
        item_pattern = re.compile(r'"\d+\n","(\d{4,7})\n",.*?"(\d+)\n"', re.DOTALL)
        for m in item_pattern.finditer(text):
            pos = m.start()
            ref = m.group(1).strip()
            qty = int(m.group(2).strip())
            current_cde = cmd_positions[cmd_starts[0]]
            for start in cmd_starts:
                if start <= pos:
                    current_cde = cmd_positions[start]
                else:
                    break
            orders.append({"Commande": current_cde, "Ref": ref, "Qte_Cde": qty})
        return pd.DataFrame(orders)
    except Exception as e:
        st.error(f"Erreur lecture PDF: {e}")
        return pd.DataFrame()

# --- Main ---
if f_stock:
    df_stock = load_stock(f_stock)
    df_display = df_stock.copy()
    if search_input:
        mask = df_display["N° article."].str.contains(search_input, case=False, na=False) | \
               df_display["Description"].str.contains(search_input, case=False, na=False)
        df_display = df_display[mask]
    
    st.subheader("📦 Aperçu du stock")
    st.dataframe(df_display[["N° article.", "Description", "Inventory", "Stock Colis", "Statut"]], use_container_width=True)

if f_stock and f_pdf:
    df_cde = extract_pdf_force(f_pdf)
    if df_cde.empty:
        st.warning("⚠️ Aucune commande exploitable trouvée dans le PDF")
    else:
        # --- Analyse commandes vs stock ---
        stock_live = df_stock.set_index("N° article.")["Inventory"].to_dict()
        desc_live = df_stock.set_index("N° article.")["Description"].to_dict()

        analyse = []
        for num_cde, group in df_cde.groupby("Commande"):
            total_commandé = group["Qte_Cde"].sum()
            total_servi = 0
            ruptures = 0
            for _, row in group.iterrows():
                ref = row["Ref"]
                qte = row["Qte_Cde"]
                dispo = stock_live.get(ref,0)
                servi = min(qte, dispo)
                total_servi += servi
                ruptures += (qte - servi)
                stock_live[ref] = max(0, dispo - servi)
            taux = (total_servi / total_commandé * 100) if total_commandé>0 else 0
            analyse.append({
                "Commande": num_cde,
                "Articles_Commandés": total_commandé,
                "Articles_Livrés": total_servi,
                "Articles_Non_Livrés": ruptures,
                "Taux_Service (%)": round(taux,1)
            })

        df_analyse = pd.DataFrame(analyse).sort_values("Taux_Service (%)")
        st.subheader("📋 Analyse par commande")
        st.dataframe(df_analyse, use_container_width=True)

        # Taux global
        total_cde = df_analyse["Articles_Commandés"].sum()
        total_livré = df_analyse["Articles_Livrés"].sum()
        taux_global = (total_livré/total_cde*100) if total_cde>0 else 0
        st.markdown(f"### 📊 Taux de service global : {taux_global:.1f}%")

        # --- Export Excel ---
        output = io.BytesIO()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df_analyse.to_excel(writer, sheet_name="Analyse_Commandes", index=False)
            df_stock.to_excel(writer, sheet_name="Stock", index=False)
        st.download_button(
            "📥 Télécharger le rapport Excel",
            data=output.getvalue(),
            file_name=f"Rapport_GESTHOR_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
