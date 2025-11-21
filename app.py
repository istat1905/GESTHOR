import streamlit as st
import pandas as pd
import numpy as np
import pdfplumber
import re

# --- Configuration de la page ---
st.set_page_config(page_title="GESTHOR – Gestion Stock & Commandes", page_icon="📦", layout="wide")

# --- CSS Pro & Clean ---
st.markdown("""
    <style>
    .block-container { padding-top: 2rem; }
    /* KPIs styles */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    /* Taux de service coloré */
    .rate-high { color: #2ecc71; font-weight: bold; }
    .rate-med { color: #f1c40f; font-weight: bold; }
    .rate-low { color: #e74c3c; font-weight: bold; }
    
    /* Footer */
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
st.markdown("<h4 style='text-align: center; color: grey; font-weight: normal;'>Analyse de stock et Taux de service</h4>", unsafe_allow_html=True)

# --- FONCTIONS LOGIQUES ---

@st.cache_data
def load_inventory(file):
    try:
        df = pd.read_excel(file)
        # Nettoyage des colonnes clés
        if "N° article." in df.columns:
            df["N° article."] = df["N° article."].astype(str).str.strip()
        df["Inventory"] = pd.to_numeric(df["Inventory"], errors='coerce').fillna(0)
        df["Qty. per Sales Unit of Measure"] = pd.to_numeric(df["Qty. per Sales Unit of Measure"], errors='coerce').fillna(1)
        
        # Calculs de base
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
    """Extraction intelligente des commandes depuis le PDF"""
    orders = []
    current_order = None
    
    try:
        with pdfplumber.open(pdf_file) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                full_text += text + "\n"
                
                # 1. Recherche du numéro de commande sur la page
                # On cherche "Commande n°XXXXXX"
                order_match = re.search(r"Commande n°\s*(\d+)", text)
                if order_match:
                    current_order_id = order_match.group(1)
                    # Si c'est un nouveau numéro, on update. 
                    # Note: Un PDF peut avoir plusieurs pages pour la MEME commande ou PLUSIEURS commandes.
                    # Ici on simplifie : on associe les lignes trouvées au dernier ID vu.
                    current_order = current_order_id

                # 2. Extraction des lignes produits (basé sur la structure du fichier fourni)
                # On cherche des lignes qui commencent par un index "1", "2", etc suivi d'une ref
                # Regex pour capturer: Ligne | Ref | EAN | NbCarton | Libellé (skip) | Qty | ...
                # Cette regex est adaptée au format spécifique "CSV-like" ou tabulaire du PDF fourni
                
                # On cherche pattern: Ref (ex: 402000) ... Code EAN (13 chiffres) ... Quantité
                # Pattern souple : Ref + EAN + Qty
                lines = text.split('\n')
                for line in lines:
                    # On cherche une ligne contenant une Ref (ex: 6 chiffres) et une Qty
                    # Ex: "1 402000 4040328040575 ... 228"
                    # On va utiliser une regex qui cherche une ref (souvent 4 à 7 chiffres) et une grosse quantité plus loin
                    
                    # Regex pour capturer la REF (colonne 2) et la QTE (avant dernière colonne souvent)
                    # C'est tricky car le texte PDF est parfois décalé. 
                    # On se base sur le fichier fourni : "402000 ... 228 ... EUR"
                    
                    match = re.search(r"\b(\d{4,7})\b.*?\b(\d+)\b.*?\bEUR\b", line)
                    if match and current_order:
                        ref_article = match.group(1)
                        qty_ordered = int(match.group(2))
                        
                        # On filtre les faux positifs (ex: code postal)
                        if qty_ordered < 10000: 
                            orders.append({
                                "Commande": current_order,
                                "Ref": ref_article,
                                "Qte_Cde": qty_ordered
                            })
                            
        return pd.DataFrame(orders)
    except Exception as e:
        st.error(f"Erreur lecture PDF: {e}")
        return pd.DataFrame()

# --- INTERFACE UTILISATEUR ---

# Sidebar
with st.sidebar:
    st.header("📂 Importation")
    file_stock = st.file_uploader("1. Stock (Excel)", type=["xlsx"])
    file_pdf = st.file_uploader("2. Commandes (PDF)", type=["pdf"])
    
    st.divider()
    st.info("💡 Chargez d'abord le stock, puis le PDF des commandes pour lancer le comparatif.")

# Logique
if file_stock:
    df_stock = load_inventory(file_stock)
    
    # --- ONGLET 1 : GESTION DE STOCK (Classique) ---
    if not file_pdf:
        st.subheader("📦 État du Stock Actuel")
        
        # Filtres rapides
        col_search, col_filter = st.columns([3, 1])
        search = col_search.text_input("Recherche article", placeholder="Code ou Désignation...")
        
        # Filtrage
        df_view = df_stock.copy()
        if search:
            df_view = df_view[df_view["N° article."].str.contains(search, case=False) | df_view["Description"].str.contains(search, case=False)]
            
        # Tableau simple sans barre de progression inutile
        st.dataframe(
            df_view[["N° article.", "Description", "Inventory", "Stock Colis", "Statut"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Inventory": st.column_config.NumberColumn("Unités", format="%d"),
                "Stock Colis": st.column_config.NumberColumn("Colis (Est.)", format="%.1f"), # Plus de barre
            }
        )

    # --- ONGLET 2 : ANALYSE COMMANDES (Si PDF chargé) ---
    else:
        df_orders = extract_orders_from_pdf(file_pdf)
        
        if not df_orders.empty:
            # --- MOTEUR DE CALCUL (Le cœur du réacteur) ---
            
            # 1. On joint les commandes avec le stock (Via "Ref" = "N° article.")
            # On prépare le stock virtuel (dictionnaire pour décrémenter en temps réel)
            virtual_stock = df_stock.set_index("N° article.")["Inventory"].to_dict()
            article_desc = df_stock.set_index("N° article.")["Description"].to_dict()
            
            results = []
            
            # On traite commande par commande pour respecter la chronologie (ou l'ordre du PDF)
            for order_id, group in df_orders.groupby("Commande"):
                
                total_ordered_order = 0
                total_shipped_order = 0
                missing_items = []
                
                for _, row in group.iterrows():
                    ref = row["Ref"]
                    qty = row["Qte_Cde"]
                    
                    stock_dispo = virtual_stock.get(ref, 0) # 0 si ref inconnue
                    desc = article_desc.get(ref, "Article Inconnu")
                    
                    total_ordered_order += qty
                    
                    if stock_dispo >= qty:
                        # On livre tout
                        shipped = qty
                        virtual_stock[ref] -= qty # On déduit du stock
                    else:
                        # On livre ce qu'il reste
                        shipped = stock_dispo
                        virtual_stock[ref] = 0 # Stock épuisé
                        
                        # On note le manquant
                        missing_qty = qty - stock_dispo
                        missing_items.append({
                            "Ref": ref,
                            "Desc": desc,
                            "Manquant": missing_qty,
                            "Commandé": qty
                        })
                    
                    total_shipped_order += shipped
                
                # Calcul taux par commande
                rate = (total_shipped_order / total_ordered_order * 100) if total_ordered_order > 0 else 0
                
                results.append({
                    "Commande": order_id,
                    "Taux Service": rate,
                    "Commandé": total_ordered_order,
                    "Livré": total_shipped_order,
                    "Ruptures": missing_items
                })
            
            # Conversion en DF pour affichage global
            df_res = pd.DataFrame(results)
            global_rate = df_res["Livré"].sum() / df_res["Commandé"].sum() * 100

            # --- AFFICHAGE DASHBOARD ---
            
            # 1. KPIs GLOBAUX
            st.subheader("🚀 Analyse des Commandes (DESADV)")
            k1, k2, k3 = st.columns(3)
            k1.metric("Commandes analysées", len(df_res))
            k2.metric("Lignes Totales", len(df_orders))
            k3.metric("Taux de Service GLOBAL", f"{global_rate:.2f}%", 
                      delta="Excellent" if global_rate > 98 else "Attention" if global_rate < 90 else "Moyen")
            
            st.divider()

            # 2. DÉTAIL PAR COMMANDE (Liste déroulante)
            st.markdown("### 🔎 Détail par Commande")
            
            for index, row in df_res.iterrows():
                # Couleur du badge selon le taux
                color = "green" if row["Taux Service"] == 100 else "orange" if row["Taux Service"] > 80 else "red"
                icon = "✅" if row["Taux Service"] == 100 else "⚠️" if row["Taux Service"] > 80 else "❌"
                
                with st.expander(f"{icon} Commande {row['Commande']} — Taux: **{row['Taux Service']:.1f}%** ({int(row['Livré'])}/{int(row['Commandé'])})"):
                    
                    c1, c2 = st.columns([1, 3])
                    with c1:
                        st.progress(row["Taux Service"] / 100)
                    
                    if row["Taux Service"] == 100:
                        st.success("Toute la commande est livrable en intégralité.")
                    else:
                        st.error(f"⚠️ {len(row['Ruptures'])} articles ne peuvent pas être livrés totalement :")
                        # Tableau des manquants pour cette commande
                        df_missing = pd.DataFrame(row["Ruptures"])
                        st.table(df_missing)

        else:
            st.warning("Impossible de lire les commandes du PDF. Vérifiez que le format est standard.")

else:
    st.info("👈 En attente du fichier de Stock (Excel)...")

# --- PIED DE PAGE ---
st.markdown("""<div class="footer">Powered by IC - 2025 ★★★★★</div>""", unsafe_allow_html=True)
