
import streamlit as st
import requests
import pandas as pd
from PIL import Image
from google.cloud import vision
from google.oauth2 import service_account
import json
import os
import re

# === CONFIGURATION ===
API_TOKEN = "65789ea069112a92c574c5a475910792005a08de"
BASE_URL = "https://api.pipedrive.com/v1"
APP_PASSWORD = "cprteam2025"

# === GOOGLE VISION CLIENT ===
def get_vision_client():
    json_str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if not json_str:
        raise Exception("GOOGLE_APPLICATION_CREDENTIALS_JSON environment variable not set.")
    credentials_info = json.loads(json_str)
    creds = service_account.Credentials.from_service_account_info(credentials_info)
    return vision.ImageAnnotatorClient(credentials=creds)

# === OCR FIELD PARSING ===
def extract_fields(text):
    email = re.search(r"[\w\.-]+@[\w\.-]+", text)
    phones = re.findall(r"(?:\+1\s?)?(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})", text)
    websites = re.findall(r"(https?://)?(www\.)?([\w-]+\.[a-z]{2,})(/\S*)?", text)
    addresses = re.findall(r"\d{1,5}\s\w+(\s\w+)*,?\s\w+,?\s[A-Z]{2}\s\d{5}", text)

    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    website_full = f"http://{websites[0][2]}" if websites else ""

    return {
        "name": lines[0] if lines else "",
        "email": email.group() if email else "",
        "phone": ", ".join(phones),
        "org_name": lines[1] if len(lines) > 1 else "",
        "org_address": addresses[0] if addresses else "",
        "org_website": website_full,
        "raw_text": text
    }

# === AUTHENTICATION ===
def login():
    st.title("🔐 Login Required")
    pwd = st.text_input("Enter password to access the uploader:", type="password")
    if pwd == APP_PASSWORD:
        st.success("Access granted. Welcome!")
        return True
    elif pwd:
        st.error("Incorrect password. Please try again.")
    return False

if login():

    # === PIPEDRIVE HELPERS ===
    def get_user_id():
        url = f"{BASE_URL}/users/me?api_token={API_TOKEN}"
        res = requests.get(url)
        res.raise_for_status()
        return res.json()["data"]["id"]

    def create_organization(org, owner_id):
        payload = {
            "name": org["name"],
            "owner_id": owner_id,
            "visible_to": 3
        }
        if "address" in org:
            payload["address"] = org["address"]
        if "website" in org:
            payload["website"] = org["website"]

        url = f"{BASE_URL}/organizations?api_token={API_TOKEN}"
        res = requests.post(url, json=payload)
        res.raise_for_status()
        return res.json()["data"]["id"]

    def create_person(person, org_id, owner_id):
        payload = {
            "name": person["name"],
            "email": person["email"],
            "phone": person["phone"],
            "org_id": org_id,
            "owner_id": owner_id,
            "visible_to": 3,
            "label": person.get("label", "Business Card Import")
        }
        url = f"{BASE_URL}/persons?api_token={API_TOKEN}"
        res = requests.post(url, json=payload)
        res.raise_for_status()
        return res.json()["data"]["id"]

    def extract_text_from_image_gcv(image_data):
        client = get_vision_client()
        image = vision.Image(content=image_data)
        response = client.text_detection(image=image)
        if response.error.message:
            raise Exception(f"Google Vision API error: {response.error.message}")
        return response.full_text_annotation.text

    # === INTERFACE ===
    st.title("📇 Pipedrive Contact Uploader with Google OCR")
    st.markdown("Upload contact CSVs or business card images to auto-populate Pipedrive using Google Cloud Vision.")

    st.header("Upload CSV of Contacts")
    csv_file = st.file_uploader("Upload CSV", type=["csv"])

    if csv_file:
        df = pd.read_csv(csv_file)
        st.write("CSV Preview:", df.head())

        if st.button("Upload CSV to Pipedrive"):
            user_id = get_user_id()
            for _, row in df.iterrows():
                org = {"name": row["org_name"], "address": row.get("org_address", ""), "website": row.get("org_website", "")}
                person = {"name": row["name"], "email": row["email"], "phone": row["phone"]}
                org_id = create_organization(org, user_id)
                create_person(person, org_id, user_id)
            st.success("CSV contacts uploaded to Pipedrive.")

    st.header("Upload Scanned Business Cards")
    images = st.file_uploader("Upload images", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

    if images:
        extracted = []
        for img in images:
            image_data = img.read()
            text = extract_text_from_image_gcv(image_data)
            parsed = extract_fields(text)
            st.subheader(f"{img.name}")
            st.text(text)
            extracted.append(parsed)

        df_edit = pd.DataFrame(extracted)
        st.subheader("📝 Review & Edit Extracted Contact Info")
        edited_df = st.data_editor(df_edit, num_rows="dynamic")

        if st.button("✅ Confirm and Upload to Pipedrive"):
            user_id = get_user_id()
            for _, row in edited_df.iterrows():
                org = {"name": row["org_name"], "address": row.get("org_address", ""), "website": row.get("org_website", "")}
                person = {"name": row["name"], "email": row["email"], "phone": row["phone"]}
                org_id = create_organization(org, user_id)
                create_person(person, org_id, user_id)
            st.success("Business card data uploaded to Pipedrive.")
