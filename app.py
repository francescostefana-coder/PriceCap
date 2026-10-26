import streamlit as st
import requests
from PIL import Image
from google import genai

# Configurazione pagina
st.set_page_config(page_title="TrovaPrezzi AI", page_icon="🛒", layout="centered")

# --- GRAFICA PULITA E COLORI TENUI (CSS) ---
st.markdown("""
<style>
    .stApp {
        background-color: #F9FAFC;
        color: #2D3748;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    h1, h2, h3 { color: #1A202C; font-weight: 600; }
    .stButton>button {
        background-color: #4A5568; color: white; border-radius: 8px; border: none; padding: 0.5rem 1rem; font-weight: 500;
    }
    .stButton>button:hover { background-color: #2D3748; }
    .stTextInput>div>div>input { border-radius: 8px; border-color: #E2E8F0; background-color: #FFFFFF; }
    .stTabs [data-baseweb="tab"] { background-color: #EDF2F7; border-radius: 8px 8px 0px 0px; color: #4A5568; padding: 10px 20px; }
    .stTabs [aria-selected="true"] { background-color: #4A5568 !important; color: white !important; }
</style>
""", unsafe_allow_html=True)

# Titolo
st.title("🛒 TrovaPrezzi & Usato AI")
st.markdown("<p style='color: #718096;'>Confronta i prezzi del nuovo o cerca occasioni nell'usato (a mano o con spedizione).</p>", unsafe_allow_html=True)

# Sidebar API Keys
st.sidebar.header("🔑 Configurazione")
gemini_api_key = st.sidebar.text_input("Gemini API Key", type="password")
tavily_api_key = st.sidebar.text_input("Tavily API Key", type="password")
st.sidebar.markdown("---")
st.sidebar.info("Le chiavi non vengono salvate e restano protette.")

# Funzione per identificare il prodotto dalla foto con Gemini
def identifica_prodotto_da_foto(image_file, api_key):
    client = genai.Client(api_key=api_key)
    img = Image.open(image_file)
    response = client.models.generate_content(
        model='gemini-3.8-flash',
        contents=[img, "Identifica con precisione questo prodotto (marca, modello esatto). Rispondi SOLO ed esclusivamente con il nome completo del prodotto, senza altre parole."]
    )
    return response.text.strip()

# Funzione per cercare sul web tramite Tavily
def cerca_sul_web(query, api_key):
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "include_answer": False,
        "max_results": 8
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return response.json().get("results", [])
    return []

# --- INPUT COMUNE (Testo o Foto) ---
st.markdown("### 1. Inserisci o fotografa il prodotto")
input_tab1, input_tab2 = st.tabs(["✍️ Scrivi Nome", "📷 Scatta / Carica Foto"])

prodotto_base = ""

with input_tab1:
    testo_input = st.text_input("Nome del prodotto:", placeholder="Es. iPhone 15, Dyson V15, LEGO...")
    if testo_input:
        prodotto_base = testo_input

with input_tab2:
    foto_caricata = st.file_uploader("Carica una foto dell'oggetto", type=["jpg", "jpeg", "png"])
    if foto_caricata and gemini_api_key:
        with st.spinner("Analisi foto in corso con Gemini..."):
            try:
                prodotto_base = identifica_prodotto_da_foto(foto_caricata, gemini_api_key)
                st.success(f"Prodotto rilevato: **{prodotto_base}**")
            except Exception as e:
                st.error(f"Errore nella lettura dell'immagine: {e}")

st.markdown("---")

# --- SEZIONE SCELTA MODALITÀ (Nuovo vs Usato) ---
st.markdown("### 2. Scegli dove cercare")
categoria_tab1, categoria_tab2 = st.tabs(["🛍️ Prodotti Nuovi (Negozi)", "🔄 Prodotti Usati (Privati & Marketplace)"])

tipo_ricerca = None
zona_utente = ""
modalita_usato = ""

with categoria_tab1:
    st.write("Cerca nei principali negozi di elettronica e grandi e-commerce.")
    if st.button("Cerca Prezzi sul Nuovo", type="primary"):
        tipo_ricerca = "nuovo"

with categoria_tab2:
    st.write("Cerca annunci di seconda mano su piattaforme verificate (Subito, Vinted, Wallapop, eBay).")
    modalita_usato = st.radio("Seleziona modalità:", ["Ritiro a mano (Zona)", "Con spedizione"])
    
    if modalita_usato == "Ritiro a mano (Zona)":
        zona_utente = st.text_input("Inserisci la tua zona / città (es. Brescia, Milano, ecc.):", placeholder="Città o Provincia")
    
    if st.button("Cerca Occasioni Usato", type="primary"):
        tipo_ricerca = "usato"

# --- ESECUZIONE DELLA RICERCA E RISULTATI ---
if tipo_ricerca:
    if not gemini_api_key or not tavily_api_key:
        st.error("⚠️ Inserisci sia la Gemini API Key che la Tavily API Key nella barra laterale a sinistra.")
    elif not prodotto_base:
        st.warning("⚠️ Inserisci prima il nome del prodotto o carica una foto.")
    else:
        with st.spinner("Ricerca sul web in corso..."):
            
            if tipo_ricerca == "nuovo":
                query_web = f"acquista prezzo {prodotto_base} amazon mediaworld unieuro euronics"
                prompt_ia = (
                    "Sei un assistente per lo shopping online. Analizza i dati web ricevuti. "
                    "Considera SOLO negozi blasonati e affidabili (Amazon, MediaWorld, Unieuro, ecc.). "
                    "Crea una TABELLA Markdown ordinata dal prezzo più basso con colonne:\n"
                    "1. **Store** | 2. **Prezzo** | 3. **Affidabilità** (es. ⭐⭐⭐⭐⭐) | 4. **Link** ([Vai al Sito](URL))."
                )
            else:
                if modalita_usato == "Ritiro a mano (Zona)":
                    if not zona_utente:
                        st.error("⚠️ Inserisci una zona valida per il ritiro a mano.")
                        st.stop()
                    query_web = f"site:subito.it OR site:ebay.it {prodotto_base} {zona_utente}"
                    prompt_ia = (
                        f"Sei un assistente per l'usato. Cerca annunci di seconda mano per '{prodotto_base}' con ritiro a mano in zona '{zona_utente}'. "
                        "Crea una TABELLA Markdown con colonne:\n"
                        "1. **Piattaforma / Annuncio** | 2. **Prezzo** | 3. **Stato / Affidabilità Venditore** | 4. **Link Annuncio** ([Vai al Link](URL))."
                    )
                else:
                    query_web = f"site:subito.it OR site:vinted.it OR site:wallapop.it OR site:ebay.it {prodotto_base} spedizione"
                    prompt_ia = (
                        f"Sei un assistente per l'usato. Cerca annunci di seconda mano per '{prodotto_base}' con opzione di spedizione. "
                        "Crea una TABELLA Markdown con colonne:\n"
                        "1. **Piattaforma** (Subito/Vinted/Wallapop) | 2. **Prezzo** | 3. **Protezione / Spedizione** | 4. **Link Annuncio** ([Vai al Link](URL))."
                    )

            risultati = cerca_sul_web(query_web, tavily_api_key)

            if not risultati:
                st.error("Nessun risultato trovato.")
            else:
                testo_risultati = "\n\n".join([f"Titolo: {r['title']}\nURL: {r['url']}\nSnippet: {r['content']}" for r in risultati])
                
                client = genai.Client(api_key=gemini_api_key)
                prompt_completo = f"{prompt_ia}\n\nProdotto: {prodotto_base}\n\nDati Web:\n{testo_risultati}"
                
                try:
                    response = client.models.generate_content(
                        model='gemini-3.8-flash',
                        contents=prompt_completo
                    )
                    
                    st.success("✅ Risultati pronti!")
                    st.markdown("### 📊 Risultati della Ricerca")
                    st.markdown(response.text)
                except Exception as e:
                    st.error(f"Errore durante la generazione AI con Gemini: {e}")
