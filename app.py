
import streamlit as st
import requests
from PIL import Image
from google import genai

# Configurazione pagina
st.set_page_config(page_title="TrovaPrezzi AI Fulmineo", page_icon="⚡", layout="centered")

# --- GRAFICA MINIMALE E VELOCE ---
st.markdown("""
<style>
    .stApp { background-color: #F9FAFC; color: #2D3748; font-family: sans-serif; }
    h1, h2, h3 { color: #1A202C; }
    .stButton>button { background-color: #4A5568; color: white; border-radius: 8px; border: none; padding: 0.5rem 1rem; }
    .stButton>button:hover { background-color: #2D3748; }
</style>
""", unsafe_allow_html=True)

st.title("⚡ TrovaPrezzi & Usato Fulmineo")
st.markdown("<p style='color: #718096;'>Ricerca istantanea di prezzi e occasioni.</p>", unsafe_allow_html=True)

# --- CONFIGURAZIONE API ---
st.sidebar.header("🔑 Configurazione")
gemini_api_key = st.secrets.get("GEMINI_API_KEY", "") or st.sidebar.text_input("Gemini API Key", type="password")
tavily_api_key = st.secrets.get("TAVILY_API_KEY", "") or st.sidebar.text_input("Tavily API Key", type="password")

# Funzione per identificare il prodotto dalla foto (rapida)
def identifica_prodotto_da_foto(image_file, api_key):
    client = genai.Client(api_key=api_key)
    img = Image.open(image_file)
    response = client.models.generate_content(
        model='gemini-3.8-flash',
        contents=[img, "Scrivi SOLO il nome esatto del prodotto, senza altre parole."]
    )
    return response.text.strip()

# Funzione di ricerca web con TIMEOUT RIGIDO (massimo 5 secondi per evitare blocchi)
@st.cache_data(ttl=3600)
def cerca_sul_web(_api_key, query):
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": _api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": 3  # Ridotto a 3 per velocità massima
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            return response.json().get("results", [])
    except Exception:
        return []
    return []

# --- INPUT ---
st.markdown("### 1. Inserisci o fotografa il prodotto")
tab1, tab2 = st.tabs(["✍️ Scrivi Nome", "📷 Fotografa"])

prodotto_base = ""

with tab1:
    prodotto_base = st.text_input("Nome:", placeholder="Es. iPhone 15, AirPods...")

with tab2:
    foto = st.file_uploader("Carica foto", type=["jpg", "jpeg", "png"])
    if foto and gemini_api_key:
        with st.spinner("Riconoscimento..."):
            try:
                prodotto_base = identifica_prodotto_da_foto(foto, gemini_api_key)
                st.success(f"Rilevato: **{prodotto_base}**")
            except Exception:
                st.error("Errore foto.")

st.markdown("---")

# --- SCELTA MODALITÀ ---
st.markdown("### 2. Scegli dove cercare")
cat1, cat2 = st.tabs(["🛍️ Nuovo (Negozi)", "🔄 Usato (Privati)"])

tipo = None
zona = ""
modo_usato = ""

with cat1:
    if st.button("Cerca Prezzi Nuovo", type="primary"):
        tipo = "nuovo"

with cat2:
    modo_usato = st.radio("Modalità:", ["Ritiro a mano (Zona)", "Con spedizione"])
    if modo_usato == "Ritiro a mano (Zona)":
        zona = st.text_input("Città / Zona:", placeholder="Es. Milano")
    if st.button("Cerca Occasioni Usato", type="primary"):
        tipo = "usato"

# --- ESECUZIONE ---
if tipo:
    if not gemini_api_key or not tavily_api_key:
        st.error("⚠️ Inserisci le chiavi API.")
    elif not prodotto_base:
        st.warning("⚠️ Inserisci un prodotto o una foto.")
    else:
        with st.spinner("⚡ Ricerca lampo in corso..."):
            
            if tipo == "nuovo":
                query_web = f"prezzo {prodotto_base} amazon mediaworld unieuro"
                prompt_ia = "Crea una TABELLA Markdown con colonne: **Store**, **Prezzo**, **Affidabilità** (⭐⭐⭐⭐⭐), **Link** ([Vai](URL)). Ordina dal più basso."
            else:
                if modo_usato == "Ritiro a mano (Zona)":
                    if not zona:
                        st.error("Inserisci la zona.")
                        st.stop()
                    query_web = f"site:subito.it {prodotto_base} {zona}"
                    prompt_ia = f"Cerca usato per '{prodotto_base}' a {zona}. Crea una TABELLA Markdown: **Piattaforma/Zona**, **Prezzo**, **Stato**, **Link** ([Vai](URL))."
                else:
                    query_web = f"site:subito.it OR site:vinted.it OR site:wallapop.it {prodotto_base} spedizione"
                    prompt_ia = "Crea una TABELLA Markdown per l'usato con spedizione: **Piattaforma**, **Prezzo**, **Spedizione**, **Link** ([Vai](URL))."

            risultati = cerca_sul_web(tavily_api_key, query_web)

            if not risultati:
                st.warning("Nessun risultato trovato o tempo scaduto. Riprova con un termine più specifico.")
            else:
                testo_risultati = "\n\n".join([f"Titolo: {r['title']}\nURL: {r['url']}\nSnippet: {r['content']}" for r in risultati])
                
                client = genai.Client(api_key=gemini_api_key)
                try:
                    response = client.models.generate_content(
                        model='gemini-3.8-flash',
                        contents=f"{prompt_ia}\n\nProdotto: {prodotto_base}\n\nDati:\n{testo_risultati}"
                    )
                    st.success("✅ Fatto!")
                    st.markdown(response.text)
                except Exception as e:
                    st.error(f"Errore IA: {e}")
