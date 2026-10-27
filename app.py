import streamlit as st
import requests
from PIL import Image
from google import genai
import urllib.parse
from bs4 import BeautifulSoup
import re

# Configurazione pagina Streamlit
st.set_page_config(
    page_title="TrovaPrezzi & Recensioni Italia", 
    page_icon="⚡", 
    layout="centered"
)

# --- INTESTAZIONE ---
st.title("⚡ TrovaPrezzi, Usato & Recensioni")
st.caption("Confronta prezzi in tempo reale e sintetizza le recensioni reali degli utenti (Pro e Contro).")

# --- CONFIGURAZIONE API SIDEBAR ---
st.sidebar.header("🔑 Configurazione API")
gemini_api_key = st.secrets.get("GEMINI_API_KEY", "") or st.sidebar.text_input("Gemini API Key", type="password")
tavily_api_key = st.secrets.get("TAVILY_API_KEY", "") or st.sidebar.text_input("Tavily API Key (Opzionale)", type="password")

MODELLI_IA = ['gemini-1.5-flash', 'gemini-1.5-pro']
BLACKLIST_TERMINI = ["come scaricare", "come fare", "guida tutorial", "scarica gratis"]

# --- UTILITIES & PARSING ---

def pulisci_testo_markdown(testo):
    """Rimuove caratteri che potrebbero rompere la tabella Markdown."""
    if not testo:
        return ""
    return testo.replace("|", "-").replace("[", "(").replace("]", ")").replace("\n", " ").strip()

def estrai_prezzo_da_testo(testo):
    """Regex ottimizzato per rilevare prezzi in Euro in formati italiani ed europei."""
    match = re.search(r'(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)\s*€|€\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)', testo)
    if match:
        p = match.group(1) or match.group(2)
        return f"{p} €"
    return "Vedi link"

def e_risultato_pertinente(titolo, snippet, prodotto_cercato):
    """Filtro euristico per scartare spam e guide non inerenti."""
    testo_totale = f"{titolo} {snippet}".lower()
    
    for bad_word in BLACKLIST_TERMINI:
        if bad_word in testo_totale:
            return False
            
    parole_prodotto = [p.lower() for p in prodotto_cercato.split() if len(p) > 2]
    if not parole_prodotto:
        return True
        
    matches = sum(1 for p in parole_prodotto if p in testo_totale)
    return (matches / len(parole_prodotto)) >= 0.4

# --- AI & VISION SERVICE ---

def identifica_prodotto_da_foto(image_file, api_key):
    """Analisi visiva dell'immagine con gestione robusta delle eccezioni."""
    if not api_key:
        return ""
    try:
        client = genai.Client(api_key=api_key)
        img = Image.open(image_file)
        prompt = "Identifica il prodotto in foto. Scrivi SOLO marca e modello esatto (es. 'Dyson V15 Detect'), senza punti o spiegazioni."
        
        for modello in MODELLI_IA:
            try:
                response = client.models.generate_content(
                    model=modello,
                    contents=[img, prompt]
                )
                if response and response.text:
                    return response.text.strip()
            except Exception:
                continue
    except Exception as e:
        st.sidebar.error(f"Errore Vision: {e}")
    return ""

# --- SEARCH ENGINE SERVICE ---

def cerca_sul_web_sicura(tavily_key, query):
    """Ricerca a 2 livelli: Tavily API -> DuckDuckGo HTML Fallback."""
    risultati = []
    
    # 1. Tavily API
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
                        "title": pulisci_testo_markdown(r.get("title", "")),
                        "url": r.get("url", ""),
                        "content": pulisci_testo_markdown(r.get("content", ""))
                    })
                if risultati:
                    return risultati, "Tavily API"
        except Exception:
            pass

    # 2. DuckDuckGo HTML Scraping (Fallback resiliente)
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        query_encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={query_encoded}"
        res = requests.post(url, headers=headers, data={'q': query}, timeout=4)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            blocchi = soup.select(".result") or soup.select(".web-result")
            
            for r in blocchi[:10]:
                title_elem = r.select_one(".result__title a") or r.select_one(".result__a")
                snippet_elem = r.select_one(".result__snippet")
                if title_elem:
                    risultati.append({
                        "title": pulisci_testo_markdown(title_elem.get_text(strip=True)),
                        "url": title_elem.get("href", ""),
                        "content": pulisci_testo_markdown(snippet_elem.get_text(strip=True)) if snippet_elem else ""
                    })
        if risultati:
            return risultati, "DuckDuckGo HTML"
    except Exception:
        pass

    return [], "Nessuno"

# --- LLM PROCESSING & FALLBACK ENGINE ---

def elabora_con_gemini_o_fallback(prompt_sistema, risultati_web, prodotto_cercato, api_key):
    """Generazione tabella tramite LLM con Fallback Regex/Parsing automatico anti-503."""
    testo_grezzo = "\n\n".join([f"Titolo: {r['title']}\nURL: {r['url']}\nSnippet: {r['content']}" for r in risultati_web])
    
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt_completo = f"{prompt_sistema}\n\nDati dal web:\n{testo_grezzo}"
            
            for modello in MODELLI_IA:
                try:
                    response = client.models.generate_content(
                        model=modello,
                        contents=prompt_completo
                    )
                    if response and response.text:
                        return response.text, f"IA ({modello})"
                except Exception:
                    continue
        except Exception:
            pass

    # Fallback Deterministico (Parsing Diretto senza IA)
    head = "| Store / Titolo | Prezzo (€) | Recensioni / Note | Link |\n| :--- | :--- | :--- | :--- |\n"
    tabella_diretta = head
    conteggio_validi = 0
    
    for r in risultati_web:
        if e_risultato_pertinente(r['title'], r['content'], prodotto_cercato):
            titolo_pulito = r['title'][:55]
            prezzo = estrai_prezzo_da_testo(f"{r['title']} {r['content']}")
            snippet_breve = r['content'][:90] + "..." if r['content'] else "N/D"
            tabella_diretta += f"| **{titolo_pulito}** | `{prezzo}` | {snippet_breve} | [Vai al sito]({r['url']}) |\n"
            conteggio_validi += 1

    if conteggio_validi == 0:
        return "⚠️ Nessuna offerta o recensione pertinente trovata per questa ricerca.", "Parsing Diretto"

    return tabella_diretta, "Parsing Diretto (Fallback Anti-503 Active)"

# --- INTERFACCIA UTENTE (UX AMICHEVOLE & RESPONSIVE) ---

st.subheader("1. Inserisci o fotografa il prodotto")
metodo_inserimento = st.radio("Seleziona modalità:", ["✍️ Nome Prodotto", "📷 Carica Foto Prodotto"], horizontal=True)

prodotto_base = ""

if metodo_inserimento == "✍️ Nome Prodotto":
    prodotto_base = st.text_input("Inserisci marca e modello:", placeholder="Es. iPhone 15 Pro, Dyson V15, PlayStation 5...")
else:
    foto = st.file_uploader("Carica un'immagine del prodotto", type=["jpg", "jpeg", "png"])
    if foto:
        st.image(foto, caption="Immagine caricata", width=220)
        if not gemini_api_key:
            st.error("⚠️ Per la ricerca tramite foto è necessaria la Gemini API Key nella barra laterale.")
        else:
            with st.spinner("🔍 Riconoscimento intelligente del prodotto..."):
                prodotto_rilevato = identifica_prodotto_da_foto(foto, gemini_api_key)
                if prodotto_rilevato:
                    prodotto_base = prodotto_rilevato
                    st.success(f"Prodotto identificato: **{prodotto_base}**")
                else:
                    st.warning("Impossibile identificare chiaramente il prodotto. Prova a inserire il nome manualmente.")

st.markdown("---")

st.subheader("2. Scegli dove cercare")
modalita_acquisto = st.radio("Ambito di ricerca:", ["🛍️ Nuovo (Store & E-commerce)", "🔄 Usato (Mercatini & Privati)"], horizontal=True)

tipo = None
zona = ""
modo_usato = ""

if modalita_acquisto == "🛍️ Nuovo (Store & E-commerce)":
    if st.button("🔎 Cerca Prezzi & Recensioni Nuovo", type="primary", use_container_width=True):
        tipo = "nuovo"
else:
    modo_usato = st.radio("Tipo di consegna usato:", ["Con spedizione", "Ritiro a mano in zona"], horizontal=True)
    if modo_usato == "Ritiro a mano in zona":
        zona = st.text_input("Città o Provincia:", placeholder="Es. Milano, Roma, Brescia...")
    if st.button("🔎 Cerca Occasioni & Recensioni Usato", type="primary", use_container_width=True):
        tipo = "usato"

# --- LOGICA DI ESECUZIONE ---

if tipo:
    if not prodotto_base.strip():
        st.warning("⚠️ Per favore, inserisci un nome di prodotto valido o carica una foto prima di avviare la ricerca.")
    else:
        with st.status("🚀 Ricerca e analisi offerte in corso...", expanded=True) as status:
            st.write(f"🔎 Scansione web per: **{prodotto_base}**...")
            
            if tipo == "nuovo":
                query_web = f'"{prodotto_base}" prezzo recensioni opinioni pro e contro (site:amazon.it OR site:mediaworld.it OR site:unieuro.it OR site:trovaprezzi.it)'
                prompt_ia = (
                    f"Sei un assistente per lo shopping in Italia per '{prodotto_base}'. "
                    "Analizza i dati web forniti e genera una TABELLA Markdown con colonne esatte:\n"
                    "| Store / Titolo | Prezzo (€) | Recensioni Utenti (Pro e Contro) | Link |\n\n"
                    "REGOLE:\n"
                    "1. Estrai il prezzo esatto in Euro.\n"
                    "2. Nella colonna recensioni, sintetizza in poche parole i punti di forza e i difetti principali segnalati dagli utenti (es. 'Pro: schermo top - Contro: autonomia').\n"
                    "3. Usa la sintassi Markdown `[Vai al Sito](URL)` per la colonna Link.\n"
                    "4. Ordina i risultati dal prezzo più basso. Rispondi in italiano."
                )
            else:
                if modo_usato == "Ritiro a mano in zona":
                    if not zona.strip():
                        status.update(label="⚠️ Inserisci la città/zona per il ritiro a mano.", state="error")
                        st.stop()
                    query_web = f'"{prodotto_base}" {zona} (site:subito.it OR site:ebay.it)'
                    prompt_ia = (
                        f"Cerca annunci usati per '{prodotto_base}' con ritiro a mano a {zona}. "
                        "Genera una TABELLA Markdown con colonne esatte:\n"
                        "| Piattaforma / Titolo | Prezzo (€) | Condizioni / Note | Link |\n\n"
                        "REGOLE:\n"
                        "1. Estrai solo annunci reali ed evidenzia lo stato del prodotto o la reputazione del venditore.\n"
                        "2. Usa la sintassi `[Vai all'Annuncio](URL)` per la colonna Link. Rispondi in italiano."
                    )
                else:
                    query_web = f'"{prodotto_base}" (site:subito.it OR site:vinted.it OR site:wallapop.it OR site:ebay.it)'
                    prompt_ia = (
                        f"Cerca annunci usati per '{prodotto_base}'. "
                        "Genera una TABELLA Markdown con colonne esatte:\n"
                        "| Piattaforma / Titolo | Prezzo (€) | Condizioni / Note | Link |\n\n"
                        "REGOLE:\n"
                        "1. Estrai solo annunci di vendita reali.\n"
                        "2. Usa la sintassi `[Vai all'Annuncio](URL)` per la colonna Link. Rispondi in italiano."
                    )

            risultati_web, motore_usato = cerca_sul_web_sicura(tavily_api_key, query_web)
            
            if not risultati_web:
                status.update(label="❌ Nessun risultato trovato.", state="error")
                st.warning("Nessun dato trovato per questa ricerca. Prova a rendere il nome del prodotto più generico.")
            else:
                st.write(f"🤖 Elaborazione tabella e sintesi recensioni ({motore_usato})...")
                
                risultato_finale, modalita_output = elabora_con_gemini_o_fallback(
                    prompt_ia, risultati_web, prodotto_base, gemini_api_key
                )
                
                status.update(label=f"✅ Analisi completata ({modalita_output})!", state="complete")
                st.markdown("### 📊 Risultati Ricerca & Recensioni")
                st.markdown(risultato_finale)
