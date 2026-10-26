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

st.title("⚡ TrovaPrezzi & Usato (Foto & Filtri)")
st.markdown("<p style='color: #718096;'>Carica una foto del prodotto o scrivi il nome per cercare in Italia.</p>", unsafe_allow_html=True)

# --- CONFIGURAZIONE API ---
st.sidebar.header("🔑 Configurazione")
gemini_api_key = st.secrets.get("GEMINI_API_KEY", "") or st.sidebar.text_input("Gemini API Key", type="password")
tavily_api_key = st.secrets.get("TAVILY_API_KEY", "") or st.sidebar.text_input("Tavily API Key (Opzionale)", type="password")

MODELLO_IA = 'gemini-1.5-flash'

# --- PAROLE CHIAVE DA ESCLUDERE SEMPRE ---
BLACKLIST_TERMINI = [
    "recensione", "come scaricare", "come fare", "guida", "tutorial", 
    "trovaprezzi.it/offerte", "forum", "vs", "confronto", "scheda tecnica"
]

# --- FUNZIONI CORE ---

def estrai_prezzo_da_testo(testo):
    """Cerca pattern di prezzo in Euro all'interno del testo estratto"""
    match = re.search(r'(\d+[\.,]?\d*)\s*€|€\s*(\d+[\.,]?\d*)', testo)
    if match:
        p = match.group(1) or match.group(2)
        return f"{p} €"
    return "Vedi link"

def e_risultato_pertinente(titolo, snippet, prodotto_cercato):
    """Verifica che il risultato parli davvero del prodotto inserito e non sia un blog/guida"""
    testo_totale = f"{titolo} {snippet}".lower()
    
    for bad_word in BLACKLIST_TERMINI:
        if bad_word in testo_totale:
            return False
            
    parole_prodotto = [p.lower() for p in prodotto_cercato.split() if len(p) > 2]
    matches = sum(1 for p in parole_prodotto if p in testo_totale)
    
    if parole_prodotto and (matches / len(parole_prodotto)) < 0.5:
        return False
        
    return True

def identifica_prodotto_da_foto(image_file, api_key):
    """Analisi visiva dell'immagine con Gemini e gestione errori dettagliata"""
    try:
        client = genai.Client(api_key=api_key)
        img = Image.open(image_file)
        response = client.models.generate_content(
            model=MODELLO_IA,
            contents=[img, "Scrivi SOLO il nome esatto del prodotto (marca e modello), senza altre parole."]
        )
        if response and response.text:
            return response.text.strip()
        return ""
    except Exception as e:
        st.error(f"Errore tecnico durante la lettura della foto: {e}")
        return ""

def cerca_sul_web_sicura(tavily_key, query):
    risultati = []
    
    if tavily_key:
        try:
            url = "https://api.tavily.com/search"
            payload = {
                "api_key": tavily_key,
                "query": query,
                "search_depth": "basic",
                "max_results": 10,
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

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        query_encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={query_encoded}"
        res = requests.post(url, headers=headers, data={'q': query}, timeout=4)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for r in soup.select(".result")[:10]:
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

def elabora_con_gemini_o_fallback(prompt_sistema, risultati_web, prodotto_cercato, api_key):
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

    # Fallback diretto con filtri
    tabella_diretta = "| Prodotto / Titolo | Prezzo (€) | Link Offerta |\n| :--- | :--- | :--- |\n"
    conteggio_validi = 0
    
    for r in risultati_web:
        if e_risultato_pertinente(r['title'], r['content'], prodotto_cercato):
            titolo_pulito = r['title'].replace("|", "-")[:65]
            testo_completo = f"{r['title']} {r['content']}"
            prezzo = estrai_prezzo_da_testo(testo_completo)
            tabella_diretta += f"| **{titolo_pulito}** | `{prezzo}` | [Vai al sito]({r['url']}) |\n"
            conteggio_validi += 1

    if conteggio_validi == 0:
        return "⚠️ Nessun annuncio o offerta direttamente pertinente trovato. Prova a raffinare il nome del prodotto.", "Visualizzazione Diretta"

    return tabella_diretta, "Visualizzazione Diretta Filtrata"

# --- INTERFACCIA UTENTE ---
st.markdown("### 1. Inserisci o fotografa il prodotto")
tab1, tab2 = st.tabs(["✍️ Scrivi Nome", "📷 Fotografa"])

prodotto_base = ""

with tab1:
    prodotto_base = st.text_input("Nome:", placeholder="Es. iPhone 15 Pro, Dyson V15...")

with tab2:
    foto = st.file_uploader("Carica foto", type=["jpg", "jpeg", "png"])
    if foto:
        st.image(foto, caption="Foto caricata", width=250)
        if not gemini_api_key:
            st.error("⚠️ Inserisci la Gemini API Key nella barra laterale per analizzare la foto.")
        else:
            with st.spinner("Riconoscimento immagine in corso con Gemini..."):
                prodotto_rilevato = identifica_prodotto_da_foto(foto, gemini_api_key)
                if prodotto_rilevato:
                    prodotto_base = prodotto_rilevato
                    st.success(f"Prodotto rilevato con successo: **{prodotto_base}**")
                else:
                    st.warning("Non è stato possibile identificare il prodotto dalla foto. Puoi comunque scriverlo nel box a fianco.")

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
        st.warning("⚠️ Inserisci prima il nome di un prodotto o carica una foto valida.")
    else:
        with st.status("🚀 Ricerca offerte in corso...", expanded=True) as status:
            
            st.write(f"🔍 Scansione per: **{prodotto_base}**...")
            
            if tipo == "nuovo":
                query_web = f'"{prodotto_base}" prezzo acquista (site:amazon.it OR site:mediaworld.it OR site:unieuro.it OR site:euronics.it OR site:trovaprezzi.it)'
                prompt_ia = (
                    "Sei un assistente per lo shopping in Italia per '" + prodotto_base + "'.\n"
                    "Analizza i risultati web e crea una TABELLA Markdown con colonne esatte:\n"
                    "1. Store / Titolo | 2. Prezzo (€) | 3. Link ([Vai al Sito](URL))\n\n"
                    "REGOLE RIGIDE:\n"
                    "- Filtra ed ESCLUDI del tutto articoli non pertinenti, recensioni, o guide.\n"
                    "- Mostra SOLO inserzioni di vendita reali per '" + prodotto_
