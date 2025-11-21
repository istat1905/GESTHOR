import streamlit as st
import pandas as pd
import numpy as np
import pdfplumber
import re

# --- Configuration de la page ---
st.set_page_config(page_title="GESTHOR – Master", page_icon="📦", layout="wide")

# --- CSS Style "Desathor" ---
st.markdown("""
    <style>
    .block-container { padding-top: 2rem; }
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        text-align: center;
    }
    .footer { text-align: center; margin-top: 4rem; color: #888; font-size: 0.8rem; border-top: 1px solid #eee; padding-top: 1rem;}
    </style>
    """, unsafe_allow_html=True)

# --- EN-TÊTE ---
col_l1, col_l2, col_l3 = st.columns([1, 1, 1])
with col_l2:
    try:
        st.image("Gesthor.png", use_container_width=True) 
    except:
        st.markdown("<h1 style='text-align: center; color: #0072B5;'>GESTHOR</h1>", unsafe_allow_html=True)
st.markdown("<h4 style='text-align: center; color: grey; font-weight: normal;'>Gestion de Stock & Analyse de Commandes</h4>", unsafe_allow_html=True)

# --- FONCTIONS ---

@st.cache_data
def load_inventory(file):
    try:
        df = pd.read_excel(file)
        # Conversion texte obligatoire pour la recherche
        if "N° article." in df.columns:
            df["N° article."] = df["N° article."].astype(str).str.strip()
        if "Description" in df.columns:
            df["Description"] = df["Description"].astype(str).str.strip()
            
        # Nettoyage numérique
        df["Inventory"] = pd.to_numeric(df["Inventory"], errors='coerce').fillna(0)
        df["Qty. per Sales Unit of Measure"] = pd.to_numeric(df["Qty. per Sales Unit of Measure"], errors='coerce').fillna(1)
        
        # Calculs
        df["Stock Colis"] = df["Inventory"] / df["Qty. per Sales Unit of Measure"].replace(0, 1)
        
        # Statuts
        conditions = [(df["Inventory"] <= 0), (df["Inventory"] < 500)]
        choices = ["Rupture", "Faible"]
        df["Statut"] = np.select(conditions, choices, default="OK")
        
        return df
    except Exception as e:
        st.error(f"Erreur Excel: {e}")
        return None

def extract_orders_from_pdf(pdf_file):
    """ Extraction adaptée au format spécifique CSV-in-PDF """
    orders = []
    current_order = None
    
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text: continue
                
                # 1. Trouver le numéro de commande
                # Cherche "Commande n°XXXXXX"
                order_matches = re.findall(r"Commande n°\s*(\d+)", text)
                if order_matches:
                    current_order = order_matches[-1] # Prend le dernier vu sur la page

                # 2. Lire les lignes produits
                # Le format fourni est : "1","402000","4040328...","19","...","228","12","EUR"
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    # On cherche une ligne qui ressemble à du CSV avec des guillemets
                    if line.startswith('"') and '","' in line:
                        # On enlève les guillemets du début et fin
                        clean_content = line[1:-1] 
                        # On split par separator ","
                        parts = clean_content.split('","')
                        
                        # Vérification de structure (au moins Ref et Qté)
                        # Index théoriques: 0=Ligne, 1=Ref, 2=EAN, 3=Colis, 4=Desc, 5=Qté, 6=PCB, 7=Devise
                        if len(parts) >= 6:
                            ref_article = parts[1].strip()
                            qte_str = parts[5].strip()
                            
                            # Vérifier que la référence et la quantité sont bien des chiffres
                            if ref_article.isdigit() and qte_str.isdigit():
                                if current_order:
                                    orders.append({
                                        "Commande": current_order,
                                        "Ref": ref_article,
                                        "Qte_Cde": int(qte_str)
                                    })
        
        return pd.DataFrame(orders)
    except Exception as e:
        st.error(f"Erreur lecture PDF: {e}")
        return pd.DataFrame()

# --- SIDEBAR ---
with st.sidebar:
    st.header("📂 Données")
    file_stock = st.file_uploader("1. Stock (Excel)", type=["xlsx"])
    file_pdf = st.file_uploader("2. Commandes (PDF)", type=["pdf"])
    st.divider()
    st.header("🔍 Recherche Stock")
    search_input = st.text_input("Code ou Libellé...")

# --- MAIN LOGIC ---
if file_stock:
    df = load_inventory(file_stock)
    
    # Filtre Recherche Global
    if search_input:
        mask = (df["N° article."].str.contains(search_input, case=False, na=False) | 
                df["Description"].str.contains(search_input, case=False, na=False))
        df = df[mask]

    # --- CRÉATION DES ONGLETS ---
    # Si un PDF est chargé, on affiche l'onglet Analyse en premier, sinon les stocks
    tabs_list = ["📊 Analyse Commandes (PDF)"] if file_pdf else []
    tabs_list += ["❌ Ruptures", "⚠️ Stock Faible", "✅ Stock OK", "📁 Tout le stock"]
    
    tabs = st.tabs(tabs_list)

    # --- LOGIQUE ONGLET ANALYSE PDF ---
    if file_pdf:
        with tabs[0]:
            df_orders = extract_orders_from_pdf(file_pdf)
            if df_orders.empty:
                st.warning("⚠️ Aucune commande trouvée. Vérifiez que le PDF correspond au format DESADV standard.")
            else:
                # Calcul du Taux de Service
                virtual_stock = df.set_index("N° article.")["Inventory"].to_dict()
                desc_map = df.set_index("N° article.")["Description"].to_dict()
                
                results = []
                
                for order_id, group in df_orders.groupby("Commande"):
                    ordered_total = 0
                    shipped_total = 0
                    missing_items = []
                    
                    for _, row in group.iterrows():
                        ref = row["Ref"]
                        qty = row["Qte_Cde"]
                        desc = desc_map.get(ref, "Inconnu")
                        stock = virtual_stock.get(ref, 0)
                        
                        ordered_total += qty
                        to_ship = min(qty, stock)
                        shipped_total += to_ship
                        virtual_stock[ref] = max(0, stock - qty) # Décrémente stock
                        
                        if to_ship < qty:
                            missing_items.append({"Ref": ref, "Produit": desc, "Manquant": qty - to_ship, "Sur": qty})
                    
                    rate = (shipped_total / ordered_total * 100) if ordered_total > 0 else 0
                    results.append({
                        "Commande": order_id, "Taux": rate, 
                        "Livrable": shipped_total, "Total": ordered_total, 
                        "Détails": missing_items
                    })
                
                df_res = pd.DataFrame(results)
                
                # KPIs Analyse
                glob_rate = df_res["Livrable"].sum() / df_res["Total"].sum() * 100
                c1, c2, c3 = st.columns(3)
                c1.metric("Commandes", len(df_res))
                c2.metric("Taux Service Global", f"{glob_rate:.1f}%", delta="Moyenne")
                c3.metric("Pièces Manquantes", int(df_res["Total"].sum() - df_res["Livrable"].sum()), delta_color="inverse")
                
                st.divider()
                
                # Liste des commandes
                for idx, row in df_res.iterrows():
                    color = "green" if row["Taux"] == 100 else "red"
                    icon = "✅" if row["Taux"] == 100 else "⚠️"
                    with st.expander(f"{icon} Commande {row['Commande']} : {row['Taux']:.1f}% de service"):
                        if row["Taux"] < 100:
                            st.error(f"Produits manquants ({len(row['Détails'])}) :")
                            st.table(pd.DataFrame(row['Détails']))
                        else:
                            st.success("Commande complète. Stock suffisant.")

    # --- LOGIQUE ONGLETS STOCKS (Le retour !) ---
    
    # Décalage d'index selon si le PDF est là ou pas
    idx_start = 1 if file_pdf else 0
    
    def show_stock_tab(status_filter, tab_index):
        with tabs[tab_index]:
            # Filtrage
            if status_filter:
                d_view = df[df["Statut"] == status_filter]
            else:
                d_view = df
            
            if d_view.empty:
                st.info("Aucun article ici.")
                return

            # Slider pour limiter l'affichage
            nb_items = st.slider(f"Nombre de lignes à afficher ({status_filter or 'Tout'})", 5, 200, 20, key=f"sl_{tab_index}")
            
            # Tableau Clean
            st.dataframe(
                d_view.head(nb_items)[["N° article.", "Description", "Inventory", "Stock Colis", "Statut"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Inventory": st.column_config.NumberColumn("Stock (UVC)", format="%d"),
                    "Stock Colis": st.column_config.ProgressColumn("Colis", format="%.1f", max_value=float(df["Stock Colis"].max())),
                }
            )

    # Appel des onglets
    show_stock_tab("Rupture", idx_start)
    show_stock_tab("Faible", idx_start + 1)
    show_stock_tab("OK", idx_start + 2)
    show_stock_tab(None, idx_start + 3)

else:
    st.info("👈 En attente du fichier Stock Excel...")

# --- FOOTER ---
st.markdown("""<div class="footer">Powered by IC - 2025 ★★★★★</div>""", unsafe_allow_html=True)
