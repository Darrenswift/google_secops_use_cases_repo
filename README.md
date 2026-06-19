# Google SecOps: Automated Stale Account Suspension v4

This repository contains a custom Google SecOps (Chronicle) SOAR integration and playbook designed to automatically detect, warn, and suspend inactive user accounts via Azure Active Directory.

By natively querying Google Chronicle for raw login events, processing the data locally, and executing a tiered response playbook, this pipeline minimizes your attack surface with zero manual intervention required.

## 📖 Use Case Overview

This workflow is a fully automated, end-to-end solution:

1. **The Detection Engine (Daily Log Pull):** A custom Python connector securely queries the Google SecOps **Asynchronous Search API**. It searches for `USER_LOGIN` events and pulls up to 90 days of history, cleanly handling API pagination for enterprise-scale environments.
2. **Local Processing & Case Creation:** The connector groups the logs by user, finds the exact timestamp of their most recent login, and calculates how many days have passed since they last authenticated. If a user breaches the inactivity threshold, a case is generated in the SOAR queue. If multiple alerts, events will be batched upto 80 alerts in one case (adjust in global constants if required 'CHUNK_SIZE') 
3. **The Automation Playbook:** The playbook immediately queries **Azure Active Directory** to enrich the user's profile data, including their display name, job title, and their direct manager's contact info.
4. **The Tiered Response Logic:** Based on the days inactive, the playbook routes the user through a tiered protocol:
    * **Under 30 Days:** Immediate case closure (False Positive/Warning). 
    * **30 - 59 Days:** Direct email warning sent to the user.
    * **60 - 89 Days:** Escalation email sent to the user's direct manager.
    * **90+ Days:** Automated account suspension in Azure AD and case closure.
  
Release Notes: SecOps Inactive Accounts Connector (v4)
🚀 Enterprise Enhancements & Features

This connector has been heavily optimized for high-throughput, large-scale Google SecOps environments. It uses Google Security Operations' modern Asynchronous Search API to support high-volume data retrieval, state management, network resilience, and UI protection.

📦 Smart Event Batching (Anti-Case Explosion)
To prevent SOAR UI degradation and alert fatigue, the connector aggregates breached users and chunks them into grouped cases:

Dynamic Chunking: Limits cases to 80 events per case, safely staying under the platform's ingestion ceiling.
Seamless Playbook Integration: Passes the grouped events directly to the SOAR Ontology engine, allowing playbooks to seamlessly loop through all users in the batch simultaneously.
🏥 Proactive Health Monitoring (Upgraded to 1M Scale)
Asynchronous API Capacity: Migrated from the synchronous udmSearch API to the asynchronous Search Session API, allowing the connector to retrieve up to 1,000,000 events (compared to the previous 10,000 limit).
Blindspot Detection: The Health Alert ("Check Engine" light) threshold is now set to the 1,000,000 limit (ASYNC_LIMIT). If the query volume reaches or exceeds this capacity, the connector automatically spawns a dedicated Health Alert case (SecOps Connector Health) to warn the engineering team that the query window is too broad and logs may be dropped.
⚡ Performance & Compute Optimizations
Asynchronous Query Execution: Moves away from blocking synchronous calls. The connector issues a POST request to spawn a background search session, polls for completion, and then streams the results, avoiding timeouts.
Lexicographical Sorting: Removes computationally heavy datetime parsing from the main data ingestion loop. The script sorts and compares raw ISO 8601 strings in $O(n)$ time and only executes the math calculation once per unique user at the end of the run.
Connection Pooling: Utilizes requests.Session() to reuse persistent TCP connections, reducing TLS handshake latency across paginated API calls.
🛡️ Network Resilience & Reliability
Automatic Retries: Implements a urllib3 Retry adapter configured to catch and automatically retry on 429 (Rate Limited) or 5xx server errors. The adapter handles both the initial POST requests and subsequent paginated GET requests.
OAuth Token Failsafe: Features timer checks in both the polling and pagination loops. If polling or data extraction runs longer than 50 minutes, the script automatically refreshes the bearer token to prevent 401 Unauthorized timeouts during massive data pulls.
🧹 Data Normalization & Filtering
Case-Insensitive Deduplication: Email addresses are immediately converted to lowercase upon extraction. This merges variants (e.g., User@ vs user@), preventing duplicate playbook executions for the same identity.
Targeted Exclusions: Includes standard exclusions to shield specific administrative or service accounts (e.g., service accounts or specific customer domains) from automated suspension logic.
📖 Code Readability & Maintainability
Global Constants: All configuration variables (lookback periods, chunk sizes, page limits, token refresh intervals, and async limits) are defined at the top of the script. This makes the codebase self-documenting and allows future tuning without modifying the pagination logic.
---

## ⚙️ Prerequisites

Before configuring the connector in SOAR, ensure you have a Google Cloud Service Account JSON key.
* The Service Account must be tied to the GCP project associated with your SecOps tenant.
* Ensure the Service Account is granted the appropriate IAM role in Google Cloud. The **Chronicle API Editor** (or Chronicle API Viewer) role is sufficient to allow the connector to query the log endpoints.

---

## 🚀 Deployment Guide

### Phase 1: Create the Custom Connector
1. In Google SecOps SOAR, navigate to the **IDE** (`</>` icon).
2. Create a new Custom Integration named **SecOps Custom Parsers**.
3. Create a new Connector under this integration named **Raw Log Parser**.
4. In the **Parameters** tab, add the following exact parameters:
   * **Customer ID** *(Type: String, Mandatory: Yes)* - Your SecOps Tenant UUID
   * **Region** *(Type: String, Mandatory: Yes)* - e.g., `US`, `EU`, `GLOBAL`
   * **Project ID** *(Type: String, Mandatory: Yes)* - Your GCP Project ID
   * **Days Inactive Threshold** *(Type: String, Mandatory: Yes)*
   * **Service Account JSON** *(Type: Password, Mandatory: Yes)*
5. Switch to the **Code** tab and paste the Python script located in `connector.py` 
6. **🛑 IMPORTANT:** Modify the `raw_query` variable on line 55 of the script to match your specific log sources and vendor telemetry. 
7. Click **Save** and **Publish**.

### Phase 2: Enable the Connector
1. Navigate to **Settings > Ingestion > Connectors**.
2. Click **+ Add Connector** and select **Raw Log Parser** from your new integration.
3. Fill in your environment details (Customer ID, Region, Project ID, Threshold, and paste the raw JSON key into the password field).
4. Set the **Polling Frequency** to run **Once a day** (e.g., Every 24 hours or a specific cron schedule).
5. Click **Save**.

### Phase 3: Generate Initial Test Case
1. On the Connectors screen, click the gear icon next to your connector and select **Run Once**.
2. Navigate to your main **Cases** screen.
3. Verify that cases titled `"Inactive User Detected: [Email]"` have been generated.

### Phase 4: Configure Entity Extraction (Ontology)
To ensure the Playbook can automatically target the correct users in Azure AD, we must map the email address to the SOAR entity engine.
1. Open one of the newly generated test cases.
2. Under the case title block, click the **Events** tab.
3. On the far right side of the raw event row, click the **gear/settings icon** to open the Event Configuration window.
4. Click the **Mapping** tab at the top of the window.
5. Locate the **`DestinationUserName`** target field.
6. Set the **Extracted Field** dropdown to `DestinationUserName` and the **Entity Type** to `User`.
7. Click **Save**.
8. Go back to the **Overview** tab of the case and click **Re-extract Entities**. Verify the user's email populates in the **Entities Highlights** widget.

### Phase 5: Deploy the Playbook
1. Navigate to the **Playbooks** tab.
2. Build or import your Stale Account Management playbook 'stale_account_soar_playbook.zip'
3. Ensure the Playbook trigger is set to:
   * **Type:** Alert
   * **Property:** Rule Generator
   * **Operator:** Equals
   * **Value:** `Stale Account UDM Search`
4. Review the **Azure Active Directory** blocks to ensure they point to your active integration instance.
5. Enable the Playbook.
