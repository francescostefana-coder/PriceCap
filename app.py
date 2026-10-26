import streamlit as st
import requests
from PIL import Image
from google import genai

# Configurazione pagina
st.set_page_config(page_title="TrovaPrezzi AI", page_icon="⚡", layout="centered")

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
st.markdown("<p style='color: #718096;'>Ricerca istantanea protetta da blocchi.</p>", unsafe_allow_html=True)

# --- CONFIGURAZIONE API ---
st.sidebar.header("🔑 Configurazione")
gemini_api_key = st.secrets.get("GEMINI_API_KEY", "") or st.sidebar.text_input("Gemini API Key", type="password")
tavily_api_key = st.secrets.get("TAVILY_API_KEY", "") or st.sidebar.text_input("Tavily API Key", type="password")

# Nomi esatti e ufficiali dei modelli supportati dalla nuova libreria google-genai
MODELLI_VALIDI = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']

# Funzione per identificare il prodotto dalla foto
def identifica_prodotto_da_foto(image_file, api_key):
    client = genai.Client(api_key=api_key)
    img = Image.open(image_file)
    for model_name in MODELLI_VALIDI:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[img, "Scrivi SOLO il nome esatto del prodotto, senza altre parole."]
            )
            return response.text.strip()
        except Exception:
            continue
    raise Exception("Impossibile analizzare l'immagine.")

# Funzione di ricerca web con timeout rigoroso (massimo 4 secondi)
@st.cache_data(ttl=3600)
def cerca_sul_web(_api_key, query):
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": _api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": 3
    }
    try:
        response = requests.post(url, json=payload, timeout=4)
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
        with st.spinner("Riconoscimento in corso..."):
            try:
                prodotto_base = identifica_prodotto_da_foto(foto, gemini_api_key)
                st.success(f"Rilevato: **{prodotto_base}**")
            except Exception as e:
                st.error(f"Errore foto: {e}")

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

# --- ESECUZIONE CON FALLBACK SUI MODELLI ---
if tipo:
    if not gemini_api_key or not tavily_api_key:
        st.error("⚠️ Inserisci le chiavi API nei Secrets o nella barra laterale.")
    elif not prodotto_base:
        st.warning("⚠️ Inserisci un prodotto o carica una foto.")
    else:
        with st.status("🚀 Elaborazione in corso...", expanded=True) as status:
            
            st.write("🔍 Connessione a Tavily per la ricerca web...")
            if tipo == "nuovo":
                query_web = f"prezzo {prodotto_base} amazon mediaworld unieuro"
                prompt_ia = "Crea una TABELLA Markdown con colonne: **Store**, **Prezzo**, **Affidabilità** (⭐⭐⭐⭐⭐), **Link** ([Vai](URL)). Ordina dal più basso."
            else:
                if modo_usato == "Ritiro a mano (Zona)":
                    if not zona:
                        status.update(label="⚠️ Errore: Inserisci la zona per il ritiro a mano.", state="error")
                        st.stop()
                    query_web = f"site:subito.it {prodotto_base} {zona}"
                    prompt_ia = f"Cerca usato per '{prodotto_base}' a {zona}. Crea una TABELLA Markdown: **Piattaforma/Zona**, **Prezzo**, **Stato**, **Link** ([Vai](URL))."
                else:
                    query_web = f"site:subito.it OR site:vinted.it OR site:wallapop.it {prodotto_base} spedizione"
                    prompt_ia = "Crea una TABELLA Markdown per l'usato con spedizione: **Piattaforma**, **Prezzo**, **Spedizione**, **Link** ([Vai](URL))."

            risultati = cerca_sul_web(tavily_api_key, query_web)
            
            if not risultati:
                status.update(label="❌ Nessun risultato trovato dal motore di ricerca.", state="error")
                st.warning("Il motore di ricerca non ha trovato nulla o ha impiegato troppo tempo.")
            else:
                st.write("✨ Trovati risultati web! Interrogazione dell'IA...")
                testo_risultati = "\n\n".join([f"Titolo: {r['title']}\nURL: {r['url']}\nSnippet: {r['content']}" for r in risultati])
                
                client = genai.Client(api_key=gemini_api_key)
                risposta_testo = None
                ultimo_errore = None

                # Prova i modelli in sequenza finché uno non risponde
                for model_name in MODELLI_VALIDI:
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=f"{prompt_ia}\n\nProdotto: {prodotto_base}\n\nDati:\n{testo_risultati}"
                        )
                        if response and response.text:
                            risposta_testo = response.text
                            break
                    except Exception as e:
                        ultimo_errore = e
                        continue

                if risposta_testo:
                    status.update(label="✅ Ricerca completata con successo!", state="complete")
                    st.markdown("### 📊 Risultati della Ricerca")
                    st.markdown(risposta_testo)
                else:
                    status.update(label="❌ Errore durante l'interrogazione dell'IA.", state="error")
                    st.error(f"Errore generazione: {ultimo_errore}")
