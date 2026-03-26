from SiemplifyConnectors import SiemplifyConnectorExecution
from SiemplifyConnectorsDataModel import AlertInfo
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import json
import uuid
import time
from datetime import datetime
from google.oauth2 import service_account
import google.auth.transport.requests

# --- Global Constants ---
LOOKBACK_DAYS = 90
SECONDS_IN_DAY = 86400
PAGE_LIMIT = 10000
CHUNK_SIZE = 80
TOKEN_REFRESH_SECONDS = 3000  # 50 minutes

def get_auth_token(siemplify, sa_json_string):
    """Generates the OAuth2 Bearer token using the proven dual-scope method."""
    try:
        sa_info = json.loads(sa_json_string)
        scopes = [
            'https://www.googleapis.com/auth/chronicle',
            'https://www.googleapis.com/auth/cloud-platform'
        ]
        credentials = service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=scopes
        )
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        return credentials.token
    except Exception as e:
        siemplify.LOGGER.error(f"Failed to generate auth token: {e}")
        raise

def main():
    siemplify = SiemplifyConnectorExecution()
    siemplify.script_name = "SecOps Raw Log Parser Connector (Enterprise)"
    siemplify.LOGGER.info("Starting Enterprise SecOps Raw Log Parser Connector...")
    
    # --- Extract Parameters from the UI ---
    customer_id = siemplify.extract_connector_param(param_name="Customer ID", is_mandatory=True)
    region = siemplify.extract_connector_param(param_name="Region", is_mandatory=True)
    project_id = siemplify.extract_connector_param(param_name="Project ID", is_mandatory=True)
    sa_json_string = siemplify.extract_connector_param(param_name="Service Account JSON", is_mandatory=True)
    days_threshold = siemplify.extract_connector_param(param_name="Days Inactive Threshold", is_mandatory=True, default_value=30, input_type=int)
    
    api_base_url = f"https://{region.lower()}-chronicle.googleapis.com/v1alpha"
    search_endpoint = f"{api_base_url}/projects/{project_id}/locations/{region.lower()}/instances/{customer_id}:udmSearch"
    # =========================================================
    # UDM Query - Insert Filtering to limit results
    # =========================================================
    raw_query = '''metadata.event_type = "USER_LOGIN"'''

    alerts = []
    
    try:
        token = get_auth_token(siemplify, sa_json_string)
        
        # --- Connection Pooling & Retry Strategy ---
        session = requests.Session()
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        })
        
        start_time = datetime.fromtimestamp(datetime.utcnow().timestamp() - (LOOKBACK_DAYS * SECONDS_IN_DAY)).strftime('%Y-%m-%dT%H:%M:%SZ')
        end_time = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        
        siemplify.LOGGER.info(f"Executing paginated UDM Search (Looking back {LOOKBACK_DAYS} days)...")
        
        user_last_logins = {}
        page_token = None
        total_events_processed = 0
        page_count = 0
        start_exec_time = time.time()
        
        # --- The Pagination Loop ---
        while True:
            # Token Refresh Failsafe
            if time.time() - start_exec_time > TOKEN_REFRESH_SECONDS:
                siemplify.LOGGER.info("Execution nearing 50 mins. Refreshing auth token to prevent 401 timeout...")
                token = get_auth_token(siemplify, sa_json_string)
                session.headers.update({"Authorization": f"Bearer {token}"})
                start_exec_time = time.time()

            params = {
                "query": raw_query, 
                "timeRange.startTime": start_time,
                "timeRange.endTime": end_time,
                "limit": PAGE_LIMIT 
            }
            if page_token:
                params["pageToken"] = page_token
                
            response = session.get(search_endpoint, params=params)
            
            if response.status_code != 200:
                siemplify.LOGGER.error(f"Google API Error Details on Page {page_count + 1}: {response.text}")
                response.raise_for_status()
                
            data = response.json()
            events = data.get("events", [])
            
            page_count += 1
            events_in_page = len(events)
            total_events_processed += events_in_page
            
            siemplify.LOGGER.info(f"Processed Page {page_count} - Found {events_in_page} events (Total so far: {total_events_processed})")
            
            for event_container in events:
                udm = event_container.get("udm", {})
                target = udm.get("target", {})
                user = target.get("user", {})
                emails = user.get("emailAddresses", user.get("email_addresses", []))
                metadata = udm.get("metadata", {})
                timestamp_str = metadata.get("eventTimestamp", metadata.get("event_timestamp"))
                
                if not emails or not timestamp_str:
                    continue
         # =======================================================================================================
         # Enhancement - Filtering based on specific domain(s) see README
         # =======================================================================================================        
                    
                # Performance Enhancement: Lexicographical sort on raw strings
                for email in emails:
                    if email not in user_last_logins or timestamp_str > user_last_logins[email]:
                        user_last_logins[email] = timestamp_str
            
            page_token = data.get("nextPageToken")
            if not page_token:
                break
                
        siemplify.LOGGER.info(f"Pagination complete. Evaluated {total_events_processed} total login events.")
        
        # =========================================================
        # ENHANCEMENT 1: HEALTH MONITORING ALERT
        # =========================================================
        current_time = datetime.utcnow().timestamp()

        if total_events_processed >= PAGE_LIMIT:
            siemplify.LOGGER.info(f"Event volume reached or exceeded {PAGE_LIMIT}. Generating health alert.")
            health_alert = AlertInfo()
            health_alert.display_id = str(uuid.uuid4())
            health_alert.ticket_id = f"health_warning_{int(current_time)}"
            health_alert.name = f"Connector Warning: High Log Volume ({total_events_processed} events)"
            health_alert.rule_generator = "SecOps Connector Health"
            health_alert.start_time = int(current_time * 1000)
            health_alert.end_time = int(current_time * 1000)
            health_alert.device_vendor = "Google SecOps"
            health_alert.device_product = "SecOps UDM"
            
            health_alert.events = [{
                "EventName": "Connector High Volume Warning",
                "Message": f"The UDM Search connector hit the {PAGE_LIMIT} threshold. Limits may have caused dropped logs. Consider tuning the query.",
                "TotalEvents": total_events_processed
            }]
            alerts.append(health_alert)

        # =========================================================
        # ENHANCEMENT 2: MATH & BATCHING
        # =========================================================
        breached_users = []
        
        for email, latest_ts_str in user_last_logins.items():
            # Convert to float math only once per unique user
            try:
                clean_ts = latest_ts_str.replace('Z', '+00:00')
                last_login_ts = datetime.fromisoformat(clean_ts).timestamp()
            except Exception:
                continue

            days_inactive = (current_time - last_login_ts) / SECONDS_IN_DAY
            if days_inactive > days_threshold:
                breached_users.append((email, round(days_inactive, 1)))
                
        siemplify.LOGGER.info(f"Found {len(breached_users)} total users exceeding the {days_threshold} day threshold.")
        
        for i in range(0, len(breached_users), CHUNK_SIZE):
            chunk = breached_users[i:i + CHUNK_SIZE]
            
            alert = AlertInfo()
            alert.display_id = str(uuid.uuid4())
            alert.ticket_id = f"stale_batch_{int(current_time)}_{i}"
            
            alert.name = f"Inactive Users Batch Detected ({len(chunk)} Accounts)"
            alert.rule_generator = "Stale Account UDM Search" 
            alert.start_time = int(current_time * 1000)
            alert.end_time = int(current_time * 1000)
            alert.device_vendor = "Google SecOps"
            alert.device_product = "SecOps UDM"
            
            events_list = []
            for user_email, days_inactive in chunk:
                events_list.append({
                    "EventName": "Inactive Account Flagged",
                    "DestinationUserName": user_email,
                    "DaysInactive": days_inactive,
                    "device_product": "SecOps UDM"
                })
                
            alert.events = events_list
            alerts.append(alert)
            siemplify.LOGGER.info(f"Created batch case containing {len(chunk)} users.")

    except Exception as e:
        siemplify.LOGGER.error(f"Execution failed: {e}")
        siemplify.LOGGER.exception(e)
        raise # Ensures the SOAR platform correctly logs a failed execution state
        
    siemplify.return_package(alerts)

if __name__ == "__main__":
    main()
