import streamlit as st
import requests
from PIL import Image
from google import genai
from groq import Groq

# Configurazione pagina
st.set_page_config(page_title="TrovaPrezzi AI SuperFast", page_icon="⚡", layout="centered")

# --- GRAFICA MINIMALE ---
st.markdown("""
<style>
    .stApp { background-color: #F9FAFC; color: #2D3748; font-family: sans-serif; }
    h1, h2, h3 { color: #1A202C; }
    .stButton>button { background-color: #4A5568; color: white; border-radius: 8px; border: none; padding: 0.5rem 1rem; }
    .stButton>button:hover { background-color: #2D3748; }
</style>
""", unsafe_allow_html=True)

st.title("⚡ TrovaPrezzi & Usato (Istantaneo)")
st.markdown("<p style='color: #718096;'>Ricerca alimentata da Groq Llama 3.3 per la massima velocità.</p>", unsafe_allow_html=True)

# --- CONFIGURAZIONE API ---
st.sidebar.header("🔑 Configurazione")
groq_api_key = st.secrets.get("GROQ_API_KEY", "") or st.sidebar.text_input("Groq API Key", type="password")
tavily_api_key = st.secrets.get("TAVILY_API_KEY", "") or st.sidebar.text_input("Tavily API Key", type="password")
gemini_api_key = st.secrets.get("GEMINI_API_KEY", "") or st.sidebar.text_input("Gemini API Key (per le foto)", type="password")

# Funzione per identificare il prodotto dalla foto con Gemini (Vision)
def identifica_prodotto_da_foto(image_file, api_key):
    client = genai.Client(api_key=api_key)
    img = Image.open(image_file)
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[img, "Scrivi SOLO il nome esatto del prodotto (marca e modello), senza altre parole."]
    )
    return response.text.strip()

# Funzione di ricerca web veloce (Tavily)
@st.cache_data(ttl=3600)
def cerca_sul_web(_api_key, query):
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": _api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": 4
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            return response.json().get("results", [])
    except Exception:
        return []
    return []

# Funzione per generare la risposta con Groq (Ultra-veloce)
def elabora_con_groq(prompt_sistema, dati_web, api_key):
    client = Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": f"Dati ricerca web:\n{dati_web}"}
        ],
        temperature=0.2,
        max_tokens=1024,
    )
    return completion.choices[0].message.content

# --- INPUT ---
st.markdown("### 1. Inserisci o fotografa il prodotto")
tab1, tab2 = st.tabs(["✍️ Scrivi Nome", "📷 Fotografa"])

prodotto_base = ""

with tab1:
    prodotto_base = st.text_input("Nome:", placeholder="Es. iPhone 15 Pro, Dyson V15...")

with tab2:
    foto = st.file_uploader("Carica foto", type=["jpg", "jpeg", "png"])
    if foto:
        if not gemini_api_key:
            st.error("⚠️ Serve la Gemini API Key nei Secrets per l'analisi visiva delle foto.")
        else:
            with st.spinner("Riconoscimento immagine con IA..."):
                try:
                    prodotto_base = identifica_prodotto_da_foto(foto, gemini_api_key)
                    st.success(f"Rilevato: **{prodotto_base}**")
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
    if not groq_api_key or not tavily_api_key:
        st.error("⚠️ Mancano le chiavi API (Groq o Tavily). Configurale nei Secrets o nella barra laterale.")
    elif not prodotto_base:
        st.warning("⚠️ Inserisci prima il nome di un prodotto o carica una foto.")
    else:
        with st.status("🚀 Elaborazione lampo in corso...", expanded=True) as status:
            
            st.write("🔍 Ricerca delle migliori offerte sul web...")
            if tipo == "nuovo":
                query_web = f"prezzo acquista {prodotto_base} amazon mediaworld unieuro euronics"
                prompt_ia = (
                    f"Sei un assistente per lo shopping online per il prodotto '{prodotto_base}'. "
                    "Analizza i dati web forniti e crea una TABELLA Markdown con colonne:\n"
                    "1. **Store** | 2. **Prezzo** | 3. **Affidabilità** (es. ⭐⭐⭐⭐⭐) | 4. **Link** ([Vai al Sito](URL)).\n"
                    "Ordina la tabella partendo dal prezzo più basso. Rispondi in italiano."
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

            risultati = cerca_sul_web(tavily_api_key, query_web)
            
            if not risultati:
                status.update(label="❌ Nessun risultato trovato dal motore di ricerca.", state="error")
                st.warning("Nessun dato trovato. Riprova con termini più semplici.")
            else:
                st.write("⚡ Trovati i dati! Generazione tabella con Groq Llama 3.3...")
                testo_risultati = "\n\n".join([f"Titolo: {r['title']}\nURL: {r['url']}\nSnippet: {r['content']}" for r in risultati])
                
                try:
                    risposta = elabora_con_groq(prompt_ia, testo_risultati, groq_api_key)
                    status.update(label="✅ Completato in un istante!", state="complete")
                    st.markdown("### 📊 Risultati della Ricerca")
                    st.markdown(risposta)
                except Exception as e:
                    status.update(label="❌ Errore durante la generazione.", state="error")
                    st.error(f"Dettaglio errore Groq: {e}")
