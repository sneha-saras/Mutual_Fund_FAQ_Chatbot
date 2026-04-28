import requests
import time

# Wait a few seconds for Streamlit to start
time.sleep(10)

try:
    # Try to access the Streamlit app
    response = requests.get("http://localhost:8501", timeout=5)
    if response.status_code == 200:
        print("Streamlit app is running successfully!")
        print("You can access it at: http://localhost:8501")
    else:
        print(f"Streamlit app returned status code: {response.status_code}")
except requests.exceptions.ConnectionError:
    print("Could not connect to Streamlit app. It may not be running.")
except requests.exceptions.Timeout:
    print("Request to Streamlit app timed out.")
except Exception as e:
    print(f"An error occurred: {e}")