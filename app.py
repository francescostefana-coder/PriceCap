import streamlit as st
import requests
from PIL import Image
from google import genai
from duckduckgo_search import DDGS

# Configurazione pagina
st.set_page_config(page_title="TrovaPrezzi Multi-AI & Free", page_icon="⚡", layout="centered")

# --- GRAFICA MINIMALE ---
st.markdown("""
<style>
    .stApp { background-color: #F9FAFC; color: #2D3748; font-family: sans-serif; }
    h1, h2, h3 { color: #1A202C; }
    .stButton>button { background-color: #4A5568; color: white; border-radius: 8px; border: none; padding: 0.5rem 1rem; }
    .stButton>button:hover { background-color: #2D3748; }
</style>
""", unsafe_allow_html=True)

st.title("⚡ TrovaPrezzi & Usato (Multi-Engine)")
st.markdown("<p style='color: #718096;'>Ricerca intelligente con fallback automatico su motori gratuiti.</p>", unsafe_allow_html=True)

# --- CONFIGURAZIONE API ---
st.sidebar.header("🔑 Configurazione")
gemini_api_key = st.secrets.get("GEMINI_API_KEY", "") or st.sidebar.text_input("Gemini API Key", type="password")
tavily_api_key = st.secrets.get("TAVILY_API_KEY", "") or st.sidebar.text_input("Tavily API Key (Opzionale)", type="password")

MODELLO_IA = 'gemini-3.8-flash'

# --- FUNZIONI CORE ---

def identifica_prodotto_da_foto(image_file, api_key):
    """Analisi visiva dell'immagine con Gemini"""
    client = genai.Client(api_key=api_key)
    img = Image.open(image_file)
    response = client.models.generate_content(
        model=MODELLO_IA,
        contents=[img, "Scrivi SOLO il nome esatto del prodotto (marca e modello), senza altre parole."]
    )
    return response.text.strip()

def cerca_sul_web_ibrida(tavily_key, query):
    """
    Motore di ricerca ibrido:
    1. Prova Tavily (se configurato)
    2. Fallback automatico su DuckDuckGo (Gratuito, senza chiavi)
    """
    risultati = []
    
    # Tentativo 1: Tavily API
    if tavily_key:
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": tavily_key,
            "query": query,
            "search_depth": "basic",
            "max_results": 5
        }
        try:
            res = requests.post(url, json=payload, timeout=5)
            if res.status_code == 200:
                data = res.json().get("results", [])
                for r in data:
                    risultati.append({
                        "title": r.get("title"),
                        "url": r.get("url"),
                        "content": r.get("content")
                    })
                if risultati:
                    return risultati, "Tavily API"
        except Exception:
            pass

    # Tentativo 2: DuckDuckGo (Gratuito e nativo)
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=6))
            for r in results:
                risultati.append({
                    "title": r.get("title"),
                    "url": r.get("href"),
                    "content": r.get("body")
                })
        if risultati:
            return risultati, "DuckDuckGo (Free Engine)"
    except Exception as e:
        st.warning(f"Errore ricerca DuckDuckGo: {e}")

    return [], "Nessuno"

def elabora_risultati(prompt_sistema, dati_web, api_key):
    """Generazione della tabella e analisi delle offerte con Gemini"""
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODELLO_IA,
        contents=f"{prompt_sistema}\n\nDati raccolti dal web:\n{dati_web}"
    )
    return response.text

# --- INTERFACCIA UTENTE ---
st.markdown("### 1. Inserisci o fotografa il prodotto")
tab1, tab2 = st.tabs(["✍️ Scrivi Nome", "📷 Fotografa"])

prodotto_base = ""

with tab1:
    prodotto_base = st.text_input("Nome:", placeholder="Es. iPhone 15 Pro, Dyson V15...")

with tab2:
    foto = st.file_uploader("Carica foto", type=["jpg", "jpeg", "png"])
    if foto:
        if not gemini_api_key:
            st.error("⚠️ Inserisci la Gemini API Key per analizzare la foto.")
        else:
            with st.spinner("Riconoscimento immagine in corso..."):
                try:
                    prodotto_base = identifica_prodotto_da_foto(foto, gemini_api_key)
                    st.success(f"Prodotto rilevato: **{prodotto_base}**")
                except Exception as e:
                    st.error(f"Errore lettura foto: {e}")

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
        zona = st.text_input("Città / Zona:", placeholder="Es. Milano, Brescia...")
    if st.button("Cerca Occasioni Usato", type="primary"):
        tipo = "usato"

# --- ESECUZIONE ---
if tipo:
    if not gemini_api_key:
        st.error("⚠️ Configura la Gemini API Key nei Secrets o nella barra laterale.")
    elif not prodotto_base:
        st.warning("⚠️ Inserisci prima il nome di un prodotto o carica una foto.")
    else:
        with st.status("🚀 Ricerca ed elaborazione in corso...", expanded=True) as status:
            
            st.write("🔍 Scansione del web multi-motore...")
            
            if tipo == "nuovo":
                query_web = f"prezzo acquista {prodotto_base} amazon mediaworld unieuro euronics"
                prompt_ia = (
                    f"Sei un assistente per lo shopping online per il prodotto '{prodotto_base}'. "
                    "Analizza i dati web forniti e crea una TABELLA Markdown ordinata dal prezzo più basso con colonne:\n"
                    "1. **Store** | 2. **Prezzo** | 3. **Affidabilità** (es. ⭐⭐⭐⭐⭐) | 4. **Link** ([Vai al Sito](URL)).\n"
                    "Rispondi in italiano."
                )
            else:
                if modo_usato == "Ritiro a mano (Zona)":
                    if not zona:
                        status.update(label="⚠️ Errore: Inserisci la tua zona per il ritiro a mano.", state="error")
                        st.stop()
                    query_web = f"site:subito.it OR site:ebay.it {prodotto_base} {zona}"
                    prompt_ia = (
                        f"Sei un assistente per l'usato. Cerca annunci per '{prodotto_base}' con ritiro a mano in zona '{zona}'. "
                        "Crea una TABELLA Markdown con colonne:\n"
                        "1. **Piattaforma/Zona** | 2. **Prezzo** | 3. **Stato / Dettagli** | 4. **Link** ([Vai all'Annuncio](URL)).\n"
                        "Rispondi in italiano."
                    )
                else:
                    query_web = f"site:subito.it OR site:vinted.it OR site:wallapop.it OR site:ebay.it {prodotto_base} spedizione"
                    prompt_ia = (
                        f"Sei un assistente per l'usato. Cerca annunci per '{prodotto_base}' con spedizione. "
                        "Crea una TABELLA Markdown con colonne:\n"
                        "1. **Piattaforma** | 2. **Prezzo** | 3. **Info Spedizione/Stato** | 4. **Link** ([Vai all'Annuncio](URL)).\n"
                        "Rispondi in italiano."
                    )

            risultati_web, motore_usato = cerca_sul_web_ibrida(tavily_api_key, query_web)
            
            if not risultati_web:
                status.update(label="❌ Nessun risultato trovato sul web.", state="error")
                st.warning("Nessun dato trovato. Prova con termini più semplici.")
            else:
                st.write(f"🤖 Sintesi dati tramite {motore_usato} e Gemini...")
                testo_grezzo = "\n\n".join([f"Titolo: {r['title']}\nURL: {r['url']}\nSnippet: {r['content']}" for r in risultati_web])
                
                try:
                    risposta_ia = elabora_risultati(prompt_ia, testo_grezzo, gemini_api_key)
                    status.update(label=f"✅ Completato con successo ({motore_usato})!", state="complete")
                    st.markdown("### 📊 Risultati della Ricerca")
                    st.markdown(risposta_ia)
                except Exception as e:
                    status.update(label="❌ Errore durante l'elaborazione dell'IA.", state="error")
                    st.error(f"Dettaglio: {e}")
