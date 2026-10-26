import streamlit as st
import requests
from bs4 import BeautifulSoup
import urllib.parse

# Configurazione pagina
st.set_page_config(page_title="TrovaPrezzi Direct", page_icon="⚡", layout="centered")

# --- GRAFICA MINIMALE ---
st.markdown("""
<style>
    .stApp { background-color: #F9FAFC; color: #2D3748; font-family: sans-serif; }
    h1, h2, h3 { color: #1A202C; }
    .stButton>button { background-color: #4A5568; color: white; border-radius: 8px; border: none; padding: 0.5rem 1rem; }
    .stButton>button:hover { background-color: #2D3748; }
</style>
""", unsafe_allow_html=True)

st.title("⚡ TrovaPrezzi Direct (Zero AI)")
st.markdown("<p style='color: #718096;'>Ricerca istantanea tramite web scraping nativo. Nessun blocco, nessun server IA.</p>", unsafe_allow_html=True)

# User-Agent per simulare un browser reale ed evitare filtri anti-bot basilari
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7"
}

def cerca_su_ebay(query):
    """Estrae i prodotti direttamente dai risultati di ricerca di eBay Italia"""
    query_encoded = urllib.parse.quote(query)
    url = f"https://www.ebay.it/sch/i.html?_nkw={query_encoded}&_sop=12" # Ordinati per prezzo più basso
    
    risultati = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=4)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.select(".s-item__info")
            
            for item in items[:6]: # Prende i primi 6 risultati rilevanti
                title_elem = item.select_one(".s-item__title")
                price_elem = item.select_one(".s-item__price")
                link_elem = item.select_one(".s-item__link")
                
                if title_elem and price_elem and link_elem:
                    titolo = title_elem.get_text(strip=True)
                    prezzo = price_elem.get_text(strip=True)
                    link = link_elem["href"]
                    
                    if "Shop on eBay" not in titolo and titolo:
                        risultati.append({
                            "titolo": titolo,
                            "prezzo": prezzo,
                            "link": link
                        })
    except Exception:
        pass
        
    return risultati

# --- INPUT UTENTE ---
st.markdown("### 1. Inserisci il prodotto da cercare")
prodotto = st.text_input("Prodotto:", placeholder="Es. AirPods Pro, iPhone 14, Dyson V15...")

st.markdown("---")

if st.button("Cerca Prezzi Subito", type="primary"):
    if not prodotto:
        st.warning("⚠️ Inserisci il nome di un prodotto.")
    else:
        with st.spinner("Ricerca in corso sui canali di vendita..."):
            
            # Esecuzione della ricerca diretta
            offerte = cerca_su_ebay(prodotto)
            
            if offerte:
                st.success(f"Trovate {len(offerte)} offerte in tempo reale!")
                st.markdown("### 📊 Risultati")
                
                # Visualizzazione pulita a schede/righe interattive
                for off in offerte:
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.write(f"**{off['titolo']}**")
                    with col2:
                        st.markdown(f"### `{off['prezzo']}`")
                    with col3:
                        st.markdown(f"[Vai al sito]({off['link']})")
                    st.markdown("---")
            else:
                st.error("Nessun risultato trovato o blocco temporaneo della risposta. Riprova con un termine più specifico.")
