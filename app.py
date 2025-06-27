import streamlit as st
import pandas as pd
import datetime as dt
import os
from sqlalchemy import create_engine, text, URL
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import folium_static

# SET PARAMETERS
server = os.environ.get("SQL_SERVER")
database = os.environ.get("SQL_DATABASE")
username = os.environ.get("SQL_USERNAME")
password = os.environ.get("SQL_PASSWORD")

st.set_page_config(page_title="IVMS Events Map", layout="wide")

st.title("IVMS Events Map")

###########################################################################
# SECRET DATABASE CONNECTION
###########################################################################

connection_string = (
    f"Driver={{ODBC Driver 17 for SQL Server}};"
    f"Server={server};"
    f"Database={database};"
    f"Uid={username};"
    f"Pwd={password};"
    "Encrypt=yes;"
    "TrustServerCertificate=no;"
    "Connection Timeout=30;"
)

connection_url = URL.create("mssql+pyodbc", query={"odbc_connect": connection_string})
engine = create_engine(connection_url)

###########################################################################
# SITE LOCATION DICTIONARY
###########################################################################

site_locations = {
    "Duketon South Operation": {"fleetId": "Maca_Mining", "lat": -27.89620553, "lon": 122.3646589},
    "Karlawinda": {"fleetId": "MACA_Mining-Karlawinda", "lat": -23.7669495, "lon": 120.1058764},
    "Sanjiv Ridge": {"fleetId": "Maca_Mining-Sanjiv-Ridge", "lat": -21.39442598, "lon": 119.6887332},
    "Cape Preston": {"fleetId": "Maca_Cape_Preston", "lat": -21.08549464, "lon": 116.1568276},
    "Mt Holland": {"fleetId": "Thiess-MtHolland", "lat": -32.10294581, "lon": 119.7708762},
    "McPhee Creek": {"fleetId": "Maca_McPhee_Creek", "lat": -21.62052587, "lon": 120.0787808},
    "Miralga Creek": {"fleetId": "Maca_Miralga_Creek", "lat": -20.99199543, "lon": 119.3067888},
    "Prominent Hill": {"fleetId": "THIESS_PROMINENT_HILL_MINING", "lat": -29.729704, "lon": 135.564669},
    "Iron Bridge": {"fleetId": "Thiess_Iron_Bridge", "lat": -29.729704, "lon": 135.564669}
}

###########################################################################
# DATA LOADING FUNCTION
###########################################################################

def load_data(utc_start, utc_end):
    with engine.connect() as conn:
        df_os = pd.read_sql_query(
            text("""
                SELECT id, EventInfoId, isActioned, lastActioned
                FROM [APP].[Outsystem_IVMSEventActionStatus]
                WHERE isActioned = 1 
            """),
            conn,
            #params={"start_date": utc_start, "end_date": utc_end}
        )

        df_lm = pd.read_sql_query(
            text("""
                SELECT id, eventType, mediaFile, asset, fleetId, kafka_id, timestampUTC
                FROM [SRC].[LightMetrics_IVMSEventInfo]
                WHERE timestampUTC BETWEEN :start_date AND :end_date
            """),
            conn,
            params={"start_date": utc_start, "end_date": utc_end}
        )
        df_lm.rename(columns={"timestampUTC": "lm_timestampUTC"}, inplace=True)

        df_kafka = pd.read_sql_query(
            text("""
                SELECT id, topic, assetId, latitude, longitude, speed, altitude, timestampUTC, api_processed, tripEventIndex
                FROM [SRC].[Kafka_IVMSEvents]
                WHERE api_processed = 1 AND timestampUTC BETWEEN :start_date AND :end_date
            """),
            conn,
            params={"start_date": utc_start, "end_date": utc_end}
        )
        df_kafka.rename(columns={"id": "kafka_id"}, inplace=True)

        df_class = pd.read_sql_query(
            text("""
                SELECT id, Title
                FROM [APP].[Outsystem_IVMSEventResponse]
            """),
            conn
        )
        df_class["Title"] = df_class["Title"].str.strip()
        df_class.rename(columns={"Title": "classification"}, inplace=True)

        df_classification = pd.read_sql_query(
            text("""
                SELECT ResponseId, EventInfoId
                FROM [APP].[Outsystem_IVMSEventActions]
            """),
            conn
        )

    #### NEW JOIN TEST ####
    final = pd.merge(df_lm, df_kafka, how="left", on="kafka_id")
    df_os = pd.merge(df_os, df_classification, how="left", on="EventInfoId")
    df_os = pd.merge(df_os, df_class, how="left", left_on="ResponseId", right_on="id")
    df_os.rename(columns={"id_x": "id"}, inplace=True)
    df_os.drop(columns=['id_y'], inplace=True)
    final = pd.merge(final, df_os, how="left", left_on="id", right_on='EventInfoId')
    final.rename(columns={"id_x": "id"}, inplace=True)
    final["timestampUTC"] = pd.to_datetime(final["timestampUTC"], errors="coerce")
    return final


###########################################################################
# SIDEBAR FILTER PANEL
###########################################################################

st.sidebar.header("Date & Time Filters")

today = dt.date.today()
first_day = today.replace(day=1)
last_day = (first_day + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)

date_range = st.sidebar.date_input("Date Range (Local Time)", (first_day, last_day))
time_from = st.sidebar.time_input("Time From (24h)", dt.time(0, 0))
time_to = st.sidebar.time_input("Time To (24h)", dt.time(23, 59))
utc_offset = st.sidebar.slider("Project UTC Offset (Hours)", -12, 14, 0)

get_data = st.sidebar.button("Get Data")
clear_cache = st.sidebar.button("Clear Cache")

###########################################################################
# HANDLE BUTTON ACTIONS
###########################################################################

if clear_cache:
    if "df" in st.session_state:
        del st.session_state.df
    st.success("Cache cleared.")

if get_data:
    start_date, end_date = date_range
    utc_start = dt.datetime.combine(start_date, dt.time.min) - dt.timedelta(hours=utc_offset, days=1)
    utc_end = dt.datetime.combine(end_date, dt.time.max) - dt.timedelta(hours=utc_offset, days=1)

    with st.spinner("Loading data..."):
        df = load_data(utc_start, utc_end)

    df["local_timestamp"] = df["timestampUTC"] + pd.to_timedelta(utc_offset, unit="h")
    df["local_date_only"] = df["local_timestamp"].dt.date.astype("object")
    df["local_time"] = df["local_timestamp"].dt.time
    df["time_min"] = df["local_timestamp"].dt.hour * 60 + df["local_timestamp"].dt.minute

    st.session_state.df = df
    st.success("Data loaded successfully.")

###########################################################################
# IF DATA IS CACHED, SHOW MAIN FILTERS & MAP
###########################################################################

if "df" in st.session_state:
    df = st.session_state.df

    st.subheader("Event Filters")

    col1, col2, col3 = st.columns(3)
    with col1:
        selected_site = st.selectbox("Select Site", list(site_locations.keys()))
    with col2:
        unique_classes = sorted(df["classification"].dropna().unique())
        unique_classes = [c for c in unique_classes if c.lower() != "discard"]
        selected_classes = st.multiselect("Human Event Classifications", unique_classes)
    with col3:
        unique_events = sorted(df["eventType"].dropna().unique())
        selected_events = st.multiselect("**OR SELECT**: System Event Classifications", unique_events)


    fleet_id = site_locations[selected_site]["fleetId"]
    start_date, end_date = date_range
    time_from_min = time_from.hour * 60 + time_from.minute
    time_to_min = time_to.hour * 60 + time_to.minute

    mask = (df["local_date_only"] >= start_date) & (df["local_date_only"] <= end_date)
    if time_from_min <= time_to_min:
        mask &= (df["time_min"] >= time_from_min) & (df["time_min"] <= time_to_min)
    else:
        mask &= (df["time_min"] >= time_from_min) | (df["time_min"] <= time_to_min)

    mask &= (df["fleetId"] == fleet_id)
    if selected_classes:
        mask &= df["classification"].isin(selected_classes)

    # ADDED FOR COL 3 (KAFKA EVENTS)
    if selected_events:
        mask &= df["eventType"].isin(selected_events)

    filtered_df = df[mask]

    coords = site_locations[selected_site]
    m = folium.Map(
        location=[coords["lat"], coords["lon"]],
        zoom_start=10,
        width="100%",
        height="100%",
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="World Imagery",
        max_zoom=17

    )

    marker_cluster = MarkerCluster().add_to(m)

    for _, row in filtered_df.iterrows():
        popup_html = f"""
        <b>Asset:</b> {row['assetId']}<br>
        <b>Lat / Long:</b> {row['latitude']}, {row['longitude']}<br>
        <b>Timestamp:</b> {row['local_timestamp']}<br>
        <b>Event Type:</b> {row['classification']}<br>
        <b><a href="{row['mediaFile']}" target="_blank">Media Link</a></b>
        """
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(color='red', icon='info-sign')
        ).add_to(marker_cluster)

    folium_static(m, width=1800, height=1100)
    st.success(f"Total events shown: {len(filtered_df):,}")

else:
    st.info("Click 'Get Data' to load events.")
