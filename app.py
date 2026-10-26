import streamlit as st
import requests
import time
from PIL import Image
from google import genai
from groq import Groq

# Configurazione pagina
st.set_page_config(page_title="TrovaPrezzi AI Senior", page_icon="⚡", layout="centered")

# --- GRAFICA MINIMALE ---
st.markdown("""
<style>
    .stApp { background-color: #F9FAFC; color: #2D3748; font-family: sans-serif; }
    h1, h2, h3 { color: #1A202C; }
    .stButton>button { background-color: #4A5568; color: white; border-radius: 8px; border: none; padding: 0.5rem 1rem; }
    .stButton>button:hover { background-color: #2D3748; }
</style>
""", unsafe_allow_html=True)

st.title("⚡ TrovaPrezzi & Usato Fulmineo")
st.markdown("<p style='color: #718096;'>Architettura resiliente con retries automatici anti-503.</p>", unsafe_allow_html=True)

# --- CONFIGURAZIONE API ---
st.sidebar.header("🔑 Configurazione")
groq_api_key = st.secrets.get("GROQ_API_KEY", "") or st.sidebar.text_input("Groq API Key", type="password")
tavily_api_key = st.secrets.get("TAVILY_API_KEY", "") or st.sidebar.text_input("Tavily API Key", type="password")
gemini_api_key = st.secrets.get("GEMINI_API_KEY", "") or st.sidebar.text_input("Gemini API Key", type="password")

MODELLO_GEMINI = 'gemini-3.8-flash'

# --- CORE FUNCTIONS ---

def identifica_prodotto_da_foto(image_file, api_key):
    client = genai.Client(api_key=api_key)
    img = Image.open(image_file)
    response = client.models.generate_content(
        model=MODELLO_GEMINI,
        contents=[img, "Scrivi SOLO il nome esatto del prodotto (marca e modello), senza parole aggiuntive."]
    )
    return response.text.strip()

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
        response = requests.post(url, json=payload, timeout=4)
        if response.status_code == 200:
            return response.json().get("results", [])
    except Exception:
        return []
    return []

def genera_con_groq_dinamico(prompt_sistema, dati_web, api_key, max_retries=3):
    client = Groq(api_key=api_key)
    modelli_disponibili = client.models.list()
    priorita = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-70b-8192", "llama3-8b-8192"]
    ids_attivi = [m.id for m in modelli_disponibili.data]
    
    modello_scelto = None
    for p in priorita:
        if p in ids_attivi:
            modello_scelto = p
            break
            
    if not modello_scelto and ids_attivi:
        modello_scelto = ids_attivi[0]
        
    if not modello_scelto:
        raise Exception("Nessun modello attivo restituito dall'API Groq.")

    # Retry loop con backoff per gestire sovraccarichi temporanei (503/429)
    for attempt in range(max_retries):
        try:
            completion = client.chat.completions.create(
                model=modello_scelto,
                messages=[
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": f"Dati ricerca web:\n{dati_web}"}
                ],
                temperature=0.2,
                max_tokens=1024,
            )
            return completion.choices[0].message.content, modello_scelto
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1.5 * (attempt + 1))
            else:
                raise e

def genera_con_gemini_fallback(prompt_sistema, dati_web, api_key, max_retries=3):
    client = genai.Client(api_key=api_key)
    
    # Retry loop con backoff per Gemini
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODELLO_GEMINI,
                contents=f"{prompt_sistema}\n\nDati ricerca web:\n{dati_web}"
            )
            return response.text
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1.5 * (attempt + 1))
            else:
                raise e

# --- INPUT UI ---
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
            with st.spinner("Analisi visiva in corso..."):
                try:
                    prodotto_base = identifica_prodotto_da_foto(foto, gemini_api_key)
                    st.success(f"Rilevato: **{prodotto_base}**")
                except Exception as e:
                    st.error(f"Errore lettura foto: {e}")

st.markdown("---")

# --- SELEZIONE MODALITÀ ---
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

# --- PIPELINE DI ESECUZIONE ---
if tipo:
    if not tavily_api_key:
        st.error("⚠️ Manca la Tavily API Key nei Secrets o nella barra laterale.")
    elif not prodotto_base:
        st.warning("⚠️ Inserisci il nome di un prodotto o carica una foto.")
    else:
        with st.status("🚀 Esecuzione pipeline di ricerca...", expanded=True) as status:
            
            st.write("🔍 [1/2] Ricerca offerte con Tavily...")
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
                status.update(label="❌ Nessun dato restituito dal motore di ricerca.", state="error")
                st.warning("Nessun risultato trovato. Prova con termini più generici.")
            else:
                st.write("🤖 [2/2] Elaborazione dati ed estrazione tabella...")
                testo_risultati = "\n\n".join([f"Titolo: {r['title']}\nURL: {r['url']}\nSnippet: {r['content']}" for r in risultati])
                
                risposta_finale = None
                engine_usato = ""

                # Provider 1: Groq (con retries automatici)
                if groq_api_key:
                    try:
                        risposta_finale, modello = genera_con_groq_dinamico(prompt_ia, testo_risultati, groq_api_key)
                        engine_usato = f"Groq ({modello})"
                    except Exception as e:
                        st.write(f"⚠️ Groq temporaneamente occupato. Tentativo con fallback Gemini...")

                # Provider 2: Gemini (con retries automatici)
                if not risposta_finale and gemini_api_key:
                    try:
                        risposta_finale = genera_con_gemini_fallback(prompt_ia, testo_risultati, gemini_api_key)
                        engine_usato = "Gemini 3.8 Flash (Fallback)"
                    except Exception as e:
                        status.update(label="❌ Errore generale sui provider IA.", state="error")
                        st.error(f"I server di generazione sono momentaneamente saturi. Riprova tra qualche secondo: {e}")

                # Render Risultati
                if risposta_finale:
                    status.update(label=f"✅ Completato con successo via {engine_usato}!", state="complete")
                    st.markdown("### 📊 Risultati della Ricerca")
                    st.markdown(risposta_finale)
