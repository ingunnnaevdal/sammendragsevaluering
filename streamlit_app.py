import streamlit as st
import pandas as pd
import random
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv
import ast
import os

st.set_page_config(layout="wide")

load_dotenv()
password = os.getenv("MONGODB_PASSWORD")
uri = f"mongodb+srv://ingunn:{password}@samiaeval.2obnm.mongodb.net/?retryWrites=true&w=majority&tlsAllowInvalidCertificates=true"

client = MongoClient(uri, server_api=ServerApi('1'))
evaluering_kolleksjon = client['SamiaEvalDB']['personalisering_VOL2']



############################
#    HJELPEFUNKSJONER
############################

def les_datasett(filsti: str):
    """Leser CSV og returnerer en pandas DataFrame."""
    try:
        return pd.read_csv(filsti)
    except FileNotFoundError:
        st.error(f"Filen {filsti} ble ikke funnet.")
        st.stop()
    except pd.errors.ParserError:
        st.error(f"Kunne ikke lese filen {filsti}. Sjekk formatet.")
        st.stop()

def lagre_evaluering_mongodb(kolleksjon, evaluering: dict):
    """Lagrer et evaluering-dokument i MongoDB."""
    try:
        kolleksjon.insert_one(evaluering)
        st.success("Evaluering lagret!")
    except Exception as e:
        st.error(f"Feil under lagring i MongoDB: {e}")

def hent_siste_evaluering(bruker_id: str, koll) -> tuple:
    """
    Returnerer (artikkel_indeks, modell_indeks) basert på siste evaluering i databasen.
    Hvis brukeren aldri har evaluert før, returnerer (0, 0).
    Hvis siste evaluering var runde 3 (BEST), betyr det at artikkelen er fullført,
    og vi hopper til neste artikkel, runde 0.
    """
    siste = koll.find_one({'bruker_id': bruker_id, 'type': {'$ne': 'undersokelse'}}, sort=[('_id', -1)])
    # Vi ekskluderer 'type': 'undersokelse' for å kun se på evalueringsrunder

    if siste is None:
        # Aldri evaluert før
        return (0, 0)

    # Har evaluert tidligere – hent artikkel_indeks og modell_indeks
    sist_artikkel = siste.get('artikkel_indeks', 0)
    sist_modell = siste.get('modell_indeks', 0)

    # Hvis siste runde var 3 (BEST), har brukeren fullført en artikkel,
    # så vi går videre til neste artikkel, start på runde 0.
    if sist_modell == 3:
        return (sist_artikkel + 1, 0)
    else:
        # Vi fortsetter på samme artikkel, men neste runde
        return (sist_artikkel, sist_modell + 1)

def vis_tekst_sammendrag(tekst):
    """Viser sammendragstekst, enten den er en liste eller en streng."""
    try:
        # Hvis tekst er en streng med liste-notasjon, forsøk å parse til Python-liste
        tekst = ast.literal_eval(tekst)
    except (SyntaxError, ValueError):
        pass

    if isinstance(tekst, list):
        tekst = [punkt.replace("•", "").strip() for punkt in tekst]
        tekst = [f"- {punkt}" if not punkt.startswith("-") else punkt for punkt in tekst]
        st.markdown("\n".join(tekst), unsafe_allow_html=True)
    else:
        st.write(tekst)

#######################################
#  HOVEDAPP: SPØR OM BRUKER, UNDERSØKELSE
#######################################

st.title("Evaluering")

bruker_id = st.text_input("Skriv inn ditt navn eller ID:", key="bruker_id")
if not bruker_id:
    st.stop()

# Først sjekk om brukeren har svart på undersøkelsen
undersokelse_svart = evaluering_kolleksjon.find_one({'bruker_id': bruker_id, 'type': 'undersokelse'})

if not undersokelse_svart:
    st.header("Før vi starter, vennligst svar på noen spørsmål:")
    svar_lengde = st.radio(
        "Hvor lange mener du at nyhetssammendrag burde være?",
        options=[
            "1-2 setninger",
            "Et kort avsnitt",
            "En mer detaljert oppsummering (flere avsnitt)",
            "Varierer avhengig av sakens kompleksitet"
        ]
    )

    svar_presentasjon = st.radio(
        "Hvordan foretrekker du at nyhetssammendrag presenteres?",
        options=[
            "Nøytralt og objektivt, uten vurderinger",
            "Kort og konsist, med kun de viktigste fakta",
            "Med en kort vurdering av saken",
            "Med forklaringer av komplekse begreper eller sammenhenger"
        ]
    )

    svar_bakgrunn = st.radio(
        "Hvor viktig er det at nyhetssammendrag gir bakgrunnsinformasjon og kontekst?",
        options=["Svært viktig", "Litt viktig", "Ikke viktig"]
    )

    svar_viktigst = st.radio(
        "Hva er viktigst for deg?",
        options=[
            "At nyhetssammendraget gir meg all relevant informasjon raskt",
            "At nyhetssammendraget forklarer hvorfor saken er viktig",
            "At nyhetssammendraget er enkelt å forstå",
            "At nyhetssammendraget har god språklig kvalitet"
        ]
    )

    svar_irriterende = st.radio(
        "Hva ville irritert deg mest med et nyhetssammendrag?",
        options=[
            "Upresis eller unøyaktig informasjon",
            "For mye tekst eller unødvendige detaljer",
            "Mangel på kontekst eller bakgrunn",
            "Et subjektivt eller vinklet språk"
        ]
    )

    if st.button("Start evaluering"):
        undersokelse = {
            'bruker_id': bruker_id,
            'type': 'undersokelse',  # marker at dette er en undersøkelse
            'svar_lengde': svar_lengde,
            'svar_presentasjon': svar_presentasjon,
            'svar_bakgrunn': svar_bakgrunn,
            'svar_viktigst': svar_viktigst,
            'svar_irriterende': svar_irriterende
        }
        evaluering_kolleksjon.insert_one(undersokelse)
        st.success("Takk for at du svarte! Du kan nå starte evalueringen.")
        st.experimental_rerun()

############################
#  LES DATASETT + EVALUERING
############################

filsti = '../Punktvis/prompt4_merget_kun_sammendrag.csv'
data = les_datasett(filsti)

# Definer 4 "runder" pr artikkel: 0=gemini, 1=claude, 2=gpt, 3=BEST
modellene = ['gemini', 'claude', 'gpt', 'BEST']

# Sett session state: artikkel_indeks og modell_indeks
if f'artikkel_indeks_{bruker_id}' not in st.session_state:
    # Finn siste evaluering i DB og gjenoppta
    art_idx, mod_idx = hent_siste_evaluering(bruker_id, evaluering_kolleksjon)
    st.session_state[f'artikkel_indeks_{bruker_id}'] = art_idx
    # Viktig: Modellindeks lagres spesifikt for [bruker_id, artikkel_indeks].
    st.session_state[f'modell_indeks_{bruker_id}_{art_idx}'] = mod_idx

start_indeks = st.session_state[f'artikkel_indeks_{bruker_id}']

# Hvis av en eller annen grunn ikke eksisterer (ny artikkel?), initier
if f'modell_indeks_{bruker_id}_{start_indeks}' not in st.session_state:
    st.session_state[f'modell_indeks_{bruker_id}_{start_indeks}'] = 0

modell_indeks = st.session_state[f'modell_indeks_{bruker_id}_{start_indeks}']

# Hvis vi har gått forbi siste artikkel ...
if start_indeks >= len(data):
    st.success("Alle artikler er evaluert!")
    st.stop()

# Hent rad for aktuell artikkel
row = data.iloc[start_indeks]

# Sjekk om modell_indeks er gyldig
if modell_indeks < len(modellene):
    valgt_modell = modellene[modell_indeks]
    st.header(f"Artikkel {start_indeks + 1}/{len(data)} – Evaluering {modell_indeks + 1}/4")
else:
    # Ugyldig – da hopper vi til neste artikkel
    st.session_state[f'artikkel_indeks_{bruker_id}'] += 1
    st.session_state.pop(f'modell_indeks_{bruker_id}_{start_indeks}', None)
    st.rerun()

# Vis artikkeltekst
st.markdown(f"""
<div class='main-container'>
    <h1 class='article-title'>{row['title']}</h1>
    <div class='lead-text'>{row['byline']}</div>
    <div class='lead-text'>Publisert: {row['creation_date']}</div>
    <div class='lead-text'>{row['lead_text']}</div>
    <div class='article-body'>{row['artikkeltekst']}</div>
</div>
""", unsafe_allow_html=True)

#################################
#   EVALUERING AV SAMMENDRAG
#################################

if valgt_modell != "BEST":
    # Hent / generer 4 sammendrag: 2 faste, 2 tilfeldige
    session_key_sammendrag = f"valgte_sammendrag_{bruker_id}_{start_indeks}_{valgt_modell}"
    if session_key_sammendrag not in st.session_state:
        # 2 faste sammendrag
        faste_sammendrag = [
            (f"{valgt_modell}_prompt4", row[f"{valgt_modell}_prompt4"]),
            (f"{valgt_modell}_prompt4_age", row[f"{valgt_modell}_prompt4_age"])
        ]
        # Andre sammendrag (fra samme modell)
        andre_sammendrag = [
            (col, row[col]) for col in row.index
            if (valgt_modell in col and col not in [f"{valgt_modell}_prompt4", f"{valgt_modell}_prompt4_age"])
        ]
        random.shuffle(andre_sammendrag)
        valgte_tilfeldige = andre_sammendrag[:2]

        valgte_sammendrag = faste_sammendrag + valgte_tilfeldige
        random.shuffle(valgte_sammendrag)

        st.session_state[session_key_sammendrag] = valgte_sammendrag

    valgte_sammendrag = st.session_state[session_key_sammendrag]

    st.subheader("Sammendrag:")
    rankings = {}
    ikke_publiserbar = {}
    ranking_options = ["Best", "Nest best", "Nest dårligst", "Dårligst"]

    for i, (kilde, tekst) in enumerate(valgte_sammendrag):
        with st.expander(f"Sammendrag {i + 1}"):
            vis_tekst_sammendrag(tekst)

            # Husk unik key for hver widget
            rankings[kilde] = st.selectbox(
                f"Ranger sammendrag {i + 1}",
                ranking_options,
                key=f"ranking_{bruker_id}_{start_indeks}_{valgt_modell}_{i}"
            )

            ikke_publiserbar[kilde] = st.checkbox(
                "Kan ikke publiseres",
                key=f"ikke_publiserbar_{bruker_id}_{start_indeks}_{valgt_modell}_{i}"
            )

    kommentar = st.text_area("Kommentar:", key=f"kommentar_{bruker_id}_{start_indeks}_{valgt_modell}")

    if st.button("Lagre evaluering", key=f"lagre_{bruker_id}_{start_indeks}_{valgt_modell}"):
        evaluering = {
            'bruker_id': bruker_id,
            'type': 'evaluering',  # for å skille fra 'undersokelse'
            'artikkel_indeks': start_indeks,
            'modell_indeks': modell_indeks,   # <— LAGRES
            'modell': valgt_modell,
            'uuid': row['uuid'],
            'rangeringer': rankings,
            'ikke_publiserbar': ikke_publiserbar,
            'sammendrag_kilder': [kilde for (kilde, _) in valgte_sammendrag],
            'kommentar': kommentar
        }
        lagre_evaluering_mongodb(evaluering_kolleksjon, evaluering)

        # Oppdater session state
        st.session_state[f'modell_indeks_{bruker_id}_{start_indeks}'] += 1

        # Hvis vi har passert siste runde (>=4), gå til neste artikkel
        if st.session_state[f'modell_indeks_{bruker_id}_{start_indeks}'] >= 4:
            st.session_state[f'artikkel_indeks_{bruker_id}'] += 1
            st.session_state.pop(f'modell_indeks_{bruker_id}_{start_indeks}', None)
        st.rerun()

elif valgt_modell == "BEST":
    st.subheader("Sammendrag:")

    # Finn ALLE evalueringer for gemini/claude/gpt der rang = "Best"
    tidligere_evalueringer = evaluering_kolleksjon.find({
        'bruker_id': bruker_id,
        'type': 'evaluering',
        'artikkel_indeks': start_indeks,
        'modell': {'$in': ['gemini', 'claude', 'gpt']}
    })

    best_summaries_raw = []
    for doc in tidligere_evalueringer:
        for kilde, rang in doc.get('rangeringer', {}).items():
            if rang == "Best":
                tekst = row.get(kilde, "")
                modellnavn = doc.get('modell', 'ukjent')
                best_summaries_raw.append((kilde, tekst, modellnavn))

    # Nøkkel i session_state (for denne artikkelen og brukeren)
    best_key = f"best_summaries_{bruker_id}_{start_indeks}"

    # Hvis vi IKKE allerede har en blandet rekkefølge liggende i session_state, lag én
    if best_key not in st.session_state:
        # Kopier listen inn i session_state
        st.session_state[best_key] = best_summaries_raw[:]
        random.shuffle(st.session_state[best_key])  # bland rekkefølgen

    # Trekk ut listen fra session_state (nå i blandet rekkefølge)
    best_summaries = st.session_state[best_key]

    # Dynamisk liste med "1. plass", "2. plass", ...
    ranking_options = [f"{i+1}. plass" for i in range(len(best_summaries))]

    rankings_best = {}
    ikke_publiserbar_best = {}

    for i, (kilde, tekst, modellnavn) in enumerate(best_summaries):
        with st.expander(f"Sammendrag {i + 1}"):
            vis_tekst_sammendrag(tekst)
            rankings_best[kilde] = st.selectbox(
                f"Ranger sammendrag {i + 1}",
                ranking_options,
                key=f"ranking_best_{bruker_id}_{start_indeks}_{kilde}"
            )
            # ikke_publiserbar_best[kilde] = st.checkbox(
            #     "Kan ikke publiseres",
            #     key=f"ikke_publiserbar_best_{bruker_id}_{start_indeks}_{kilde}"
            # )

    kommentar_best = st.text_area("Kommentar:", key=f"kommentar_best_{bruker_id}_{start_indeks}")
    
    if st.button("Lagre evaluering", key=f"lagre_best_{bruker_id}_{start_indeks}"):
        evaluering_best = {
            'bruker_id': bruker_id,
            'type': 'evaluering',
            'artikkel_indeks': start_indeks,
            'modell_indeks': modell_indeks,
            'modell': "BEST",
            'uuid': row['uuid'],
            'rangeringer': rankings_best,
            #'ikke_publiserbar': ikke_publiserbar_best,
            'sammendrag_kilder': [k for (k, t, m) in best_summaries],
            'kommentar': kommentar_best
        }
        lagre_evaluering_mongodb(evaluering_kolleksjon, evaluering_best)

        # Rens opp hvis du vil, f.eks. slette best_key fra session_state
        if best_key in st.session_state:
            del st.session_state[best_key]

        st.session_state[f'modell_indeks_{bruker_id}_{start_indeks}'] += 1
        if st.session_state[f'modell_indeks_{bruker_id}_{start_indeks}'] >= 4:
            st.session_state[f'artikkel_indeks_{bruker_id}'] += 1
            st.session_state.pop(f'modell_indeks_{bruker_id}_{start_indeks}', None)

        st.rerun()





st.markdown("""
    <style>
        :root {
            --primary-text-color: #333;
            --secondary-text-color: #555;
            --background-color: #f9f9f9;
        }

        @media (prefers-color-scheme: dark) {
            :root {
                --primary-text-color: #f0f0f0;
                --secondary-text-color: #bbb;
                --background-color: #222;
            }
        }
        .main-container {
            max-width: 800px;
            margin: auto;
            padding: 20px;
            background-color: var(--background-color);
            border-radius: 8px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
            max-height: 800px;
            overflow-y: auto;
        }
        .article-title {
            font-size: 28px;
            font-weight: bold;
            color: var(--primary-text-color);
            margin-bottom: 10px;
        }
        .lead-text {
            font-size: 18px;
            color: var(--secondary-text-color);
            margin-bottom: 20px;
        }
        .article-body {
            font-size: 16px;
            line-height: 1.6;
            color: var(--primary-text-color);
            margin-bottom: 30px;
        }
        .summary-box {
            background: white;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        }
        .summary-header {
            font-weight: bold;
            margin-bottom: 10px;
        }
        .evaluation-section {
            background-color: #fff;
            padding: 20px;
            border: 1px solid #ddd;
            border-radius: 8px;
        }
        .evaluation-button {
            background-color: #2051b3;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
        }
        .evaluation-button:hover {
            background-color: #183c85;
        }
    </style>
""", unsafe_allow_html=True)