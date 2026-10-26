import streamlit as st
import requests
from PIL import Image
from google import genai
import urllib.parse
from bs4 import BeautifulSoup
import re

# Configurazione pagina
st.set_page_config(page_title="TrovaPrezzi Italia", page_icon="⚡", layout="centered")

# --- GRAFICA MINIMALE ---
st.markdown("""
<style>
    .stApp { background-color: #F9FAFC; color: #2D3748; font-family: sans-serif; }
    h1, h2, h3 { color: #1A202C; }
    .stButton>button { background-color: #4A5568; color: white; border-radius: 8px; border: none; padding: 0.5rem 1rem; }
    .stButton>button:hover { background-color: #2D3748; }
</style>
""", unsafe_allow_html=True)

st.title("⚡ TrovaPrezzi & Usato (Solo Italia / UE)")
st.markdown("<p style='color: #718096;'>Ricerca prodotti con prezzi espliciti e negozi con spedizione in Italia.</p>", unsafe_allow_html=True)

# --- CONFIGURAZIONE API ---
st.sidebar.header("🔑 Configurazione")
gemini_api_key = st.secrets.get("GEMINI_API_KEY", "") or st.sidebar.text_input("Gemini API Key", type="password")
tavily_api_key = st.secrets.get("TAVILY_API_KEY", "") or st.sidebar.text_input("Tavily API Key (Opzionale)", type="password")

MODELLO_IA = 'gemini-1.5-flash'

# --- FUNZIONI CORE ---

def estrai_prezzo_da_testo(testo):
    """Cerca pattern di prezzo in Euro all'interno del testo estratto"""
    match = re.search(r'(\d+[\.,]?\d*)\s*€|€\s*(\d+[\.,]?\d*)', testo)
    if match:
        p = match.group(1) or match.group(2)
        return f"{p} €"
    return "Vedi link"

def identifica_prodotto_da_foto(image_file, api_key):
    try:
        client = genai.Client(api_key=api_key)
        img = Image.open(image_file)
        response = client.models.generate_content(
            model=MODELLO_IA,
            contents=[img, "Scrivi SOLO il nome esatto del prodotto (marca e modello), senza altre parole."]
        )
        return response.text.strip()
    except Exception:
        return ""

def cerca_sul_web_sicura(tavily_key, query):
    risultati = []
    
    # 1. Tentativo Tavily con parametri geografici
    if tavily_key:
        try:
            url = "https://api.tavily.com/search"
            payload = {
                "api_key": tavily_key,
                "query": query,
                "search_depth": "basic",
                "max_results": 7,
                "include_answer": False
            }
            res = requests.post(url, json=payload, timeout=4)
            if res.status_code == 200:
                data = res.json().get("results", [])
                for r in data:
                    risultati.append({
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "content": r.get("content", "")
                    })
                if risultati:
                    return risultati, "Tavily API"
        except Exception:
            pass

    # 2. Fallback su DuckDuckGo HTML
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        query_encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={query_encoded}"
        res = requests.post(url, headers=headers, data={'q': query}, timeout=4)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for r in soup.select(".result")[:7]:
                title_elem = r.select_one(".result__title a")
                snippet_elem = r.select_one(".result__snippet")
                if title_elem:
                    risultati.append({
                        "title": title_elem.get_text(strip=True),
                        "url": title_elem.get("href"),
                        "content": snippet_elem.get_text(strip=True) if snippet_elem else ""
                    })
        if risultati:
            return risultati, "DuckDuckGo HTML"
    except Exception:
        pass

    return [], "Nessuno"

def elabora_con_gemini_o_fallback(prompt_sistema, risultati_web, api_key):
    """
    Tenta la sintesi via Gemini filtrando per disponibilità in Italia.
    Se in fallback, costruisce la tabella estraendo i prezzi via Regex.
    """
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            testo_grezzo = "\n\n".join([f"Titolo: {r['title']}\nURL: {r['url']}\nSnippet: {r['content']}" for r in risultati_web])
            response = client.models.generate_content(
                model=MODELLO_IA,
                contents=f"{prompt_sistema}\n\nDati dal web:\n{testo_grezzo}"
            )
            return response.text, "Gemini 1.5 Flash (IA)"
        except Exception:
            pass

    # --- FALLBACK DIRETTO ---
    tabella_diretta = "| Prodotto / Titolo | Prezzo (€) | Link Offerta |\n| :--- | :--- | :--- |\n"
    for r in risultati_web:
        titolo_pulito = r['title'].replace("|", "-")[:65]
        testo_completo = f"{r['title']} {r['content']}"
        prezzo = estrai_prezzo_da_testo(testo_completo)
        tabella_diretta += f"| **{titolo_pulito}** | `{prezzo}` | [Vai al sito]({r['url']}) |\n"
    
    return tabella_diretta, "Visualizzazione Diretta (Fallback anti-503)"

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
            st.warning("⚠️ Inserisci la Gemini API Key per analizzare la foto.")
        else:
            with st.spinner("Riconoscimento immagine in corso..."):
                prodotto_base = identifica_prodotto_da_foto(foto, gemini_api_key)
                if prodotto_base:
                    st.success(f"Prodotto rilevato: **{prodotto_base}**")
                else:
                    st.error("Impossibile leggere la foto automaticamente. Scrivi il nome nel box a fianco.")

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
    if not prodotto_base:
        st.warning("⚠️ Inserisci prima il nome di un prodotto o carica una foto.")
    else:
        with st.status("🚀 Ricerca offerte in Italia/UE in corso...", expanded=True) as status:
            
            st.write("🔍 Scansione store e siti italiani in tempo reale...")
            
            if tipo == "nuovo":
                query_web = f"prezzo acquista {prodotto_base} italia euro (site:.it OR amazon.it OR mediaworld.it OR unieuro.it OR euronics.it)"
                prompt_ia = f"""Sei un assistente per lo shopping in Italia per '{prodotto_base}'.
Analizza i risultati web e crea una TABELLA Markdown con colonne esatte:
1. **Store / Titolo** | 2. **Prezzo (€)** | 3. **Link** ([Vai al Sito](URL))

REGOLE RIGIDE:
- Accetta SOLO store italiani o europei con spedizione standard in Italia. ESCLUDI siti USA, in dollari ($) o con dazi doganali.
- Inserisci SEMPRE il prezzo numerico in Euro (€) nella colonna Prezzo.
- Seleziona SOLO offerte attive. Ordina dal prezzo più basso. Rispondi in italiano."""
            else:
                if modo_usato == "Ritiro a mano (Zona)":
                    if not zona:
                        status.update(label="⚠️ Errore: Inserisci la zona per il ritiro a mano.", state="error")
                        st.stop()
                    query_web = f"site:subito.it OR site:ebay.it {prodotto_base} {zona}"
                    prompt_ia = f"""Sei un assistente per l'usato in Italia. Cerca annunci per '{prodotto_base}' con ritiro a mano a {zona}.
Crea una TABELLA Markdown con colonne esatte:
1. **Piattaforma / Titolo** | 2. **Prezzo (€)** | 3. **Link** ([Vai all'Annuncio](URL))

REGOLE RIGIDE:
- Mostra solo annunci rilevanti in Italia con prezzo in Euro (€).
- Escludi annunci palesemente vecchi o scaduti. Rispondi in italiano."""
                else:
                    query_web = f"(site:subito.it OR site:vinted.it OR site:wallapop.it OR site:ebay.it) {prodotto_base} italia spedizione"
                    prompt_ia = f"""Sei un assistente per l'usato in Italia. Cerca annunci per '{prodotto_base}' con spedizione in Italia.
Crea una TABELLA Markdown con colonne esatte:
1. **Piattaforma / Titolo** | 2. **Prezzo (€)** | 3. **Link** ([Vai all'Annuncio](URL))

REGOLE RIGIDE:
- Accetta solo annunci da piattaforme operanti in Italia (Subito, Vinted, Wallapop, eBay.it).
- Estrai ed esplicita SEMPRE il prezzo in Euro (€) nell'apposita colonna. Rispondi in italiano."""

            risultati_web, motore_usato = cerca_sul_web_sicura(tavily_api_key, query_web)
            
            if not risultati_web:
                status.update(label="❌ Nessun risultato trovato in Italia.", state="error")
                st.warning("Nessun dato trovato per l'Italia. Prova con termini di ricerca più generici.")
            else:
                st.write(f"🤖 Estrazione prezzi e verifica territorialità ({motore_usato})...")
                
                risultato_finale, modalita_output = elabora_con_gemini_o_fallback(prompt_ia, risultati_web, gemini_api_key)
                
                status.update(label=f"✅ Completato ({modalita_output})!", state="complete")
                st.markdown("### 📊 Risultati della Ricerca (Italia / UE)")
                st.markdown(risultato_finale)
