from SiemplifyConnectors import SiemplifyConnectorExecution
from SiemplifyConnectorsDataModel import AlertInfo
import requests
import json
import uuid
from datetime import datetime
from google.oauth2 import service_account
import google.auth.transport.requests

def get_auth_token(siemplify, sa_json_string):
    """
    Generates the OAuth2 Bearer token using the proven dual-scope method.
    """
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
    siemplify.script_name = "SecOps Raw Log Parser Connector (Paginated)"
    siemplify.LOGGER.info("Starting SecOps Raw Log Parser Connector...")
    
    # --- Extract Parameters from the UI ---
    customer_id = siemplify.extract_connector_param(param_name="Customer ID", is_mandatory=True)
    region = siemplify.extract_connector_param(param_name="Region", is_mandatory=True)
    project_id = siemplify.extract_connector_param(param_name="Project ID", is_mandatory=True)
    sa_json_string = siemplify.extract_connector_param(param_name="Service Account JSON", is_mandatory=True)
    days_threshold = siemplify.extract_connector_param(param_name="Days Inactive Threshold", is_mandatory=True, input_type=int)
    
    # --- Construct Endpoints & Query ---
    api_base_url = f"https://{region.lower()}-chronicle.googleapis.com/v1alpha"
    search_endpoint = f"{api_base_url}/projects/{project_id}/locations/{region.lower()}/instances/{customer_id}:udmSearch"

    # --- ACTION REQUIRED: Modify this UDM query for your environment including Entra variables paste as one long string in the raw_query variable, ---
    raw_query = 'metadata.event_type = "USER_LOGIN"'
    # -------------------------------------------------------------------

    alerts = []
    
    try:
        token = get_auth_token(siemplify, sa_json_string)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Lookback set to 90 days
        lookback_days = 90
        start_time = datetime.fromtimestamp(datetime.utcnow().timestamp() - (lookback_days * 86400)).strftime('%Y-%m-%dT%H:%M:%SZ')
        end_time = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        
        siemplify.LOGGER.info(f"Executing paginated UDM Search (Looking back {lookback_days} days)...")
        
        user_last_logins = {}
        page_token = None
        total_events_processed = 0
        page_count = 0
        
        # --- The Pagination Loop ---
        while True:
            params = {
                "query": raw_query, 
                "timeRange.startTime": start_time,
                "timeRange.endTime": end_time,
                "limit": 10000 
            }
            
            if page_token:
                params["pageToken"] = page_token
                
            response = requests.get(search_endpoint, headers=headers, params=params)
            
            if response.status_code != 200:
                siemplify.LOGGER.error(f"Google API Error Details on Page {page_count + 1}: {response.text}")
                response.raise_for_status()
                
            data = response.json()
            events = data.get("events", [])
            
            page_count += 1
            events_in_page = len(events)
            total_events_processed += events_in_page
            
            siemplify.LOGGER.info(f"Processed Page {page_count} - Found {events_in_page} events (Total so far: {total_events_processed})")
            
            # Parse the events from this specific page immediately
            for event_container in events:
                udm = event_container.get("udm", {})
                
                target = udm.get("target", {})
                user = target.get("user", {})
                emails = user.get("emailAddresses", user.get("email_addresses", []))
                
                metadata = udm.get("metadata", {})
                timestamp_str = metadata.get("eventTimestamp", metadata.get("event_timestamp"))
                
                if not emails or not timestamp_str:
                    continue
                    
                try:
                    clean_ts = timestamp_str.replace('Z', '+00:00')
                    event_time = datetime.fromisoformat(clean_ts).timestamp()
                except Exception:
                    continue
                    
                for email in emails:
                    if email not in user_last_logins or event_time > user_last_logins[email]:
                        user_last_logins[email] = event_time
            
            # Check if Google gave us a token for the next page
            page_token = data.get("nextPageToken")
            
            # If no token is returned, we have reached the end of the logs
            if not page_token:
                break
                
        siemplify.LOGGER.info(f"Pagination complete. Evaluated {total_events_processed} total login events.")
        
        # --- Calculate Threshold Breaches ---
        current_time = datetime.utcnow().timestamp()
        
        for email, last_login_ts in user_last_logins.items():
            days_inactive = (current_time - last_login_ts) / 86400
            
            if days_inactive > days_threshold:
                alert = AlertInfo()
                alert.display_id = str(uuid.uuid4())
                alert.ticket_id = f"stale_user_{email}"
                alert.name = f"Inactive User Detected: {email}"
                alert.rule_generator = "Stale Account UDM Search"
                alert.start_time = int(datetime.utcnow().timestamp() * 1000)
                alert.end_time = int(datetime.utcnow().timestamp() * 1000)
                alert.device_vendor = "Google SecOps"
                alert.device_product = "SecOps UDM"
                
                alert.events = [{
                    "EventName": "Inactive Account Flagged",
                    "DestinationUserName": email,
                    "DaysInactive": round(days_inactive, 1),
                    "device_product": "SecOps UDM"
                }]
                
                alerts.append(alert)
                siemplify.LOGGER.info(f"Created alert for user: {email} (Inactive for {round(days_inactive, 1)} days)")

    except Exception as e:
        siemplify.LOGGER.error(f"Execution failed: {e}")
        siemplify.LOGGER.exception(e)
        
    siemplify.return_package(alerts)

if __name__ == "__main__":
    main()
