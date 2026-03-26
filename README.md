# Google SecOps: Automated Stale Account Suspension v2 

This repository contains a custom Google SecOps (Chronicle) SOAR integration and playbook designed to automatically detect, warn, and suspend inactive user accounts via Azure Active Directory.

By natively querying Google Chronicle for raw login events, processing the data locally, and executing a tiered response playbook, this pipeline minimizes your attack surface with zero manual intervention required.

## 📖 Use Case Overview

This workflow is a fully automated, end-to-end solution:

1. **The Detection Engine (Daily Log Pull):** A custom Python connector securely queries the Google SecOps `udmSearch` API. It searches for `USER_LOGIN` events and pulls up to 90 days of history, cleanly handling API pagination for enterprise-scale environments.
2. **Local Processing & Case Creation:** The connector groups the logs by user, finds the exact timestamp of their most recent login, and calculates how many days have passed since they last authenticated. If a user breaches the inactivity threshold, a case is generated in the SOAR queue. If multiple alerts, events will be batched upto 80 alerts in one case (adjust in global constants if required 'CHUNK_SIZE') 
3. **The Automation Playbook:** The playbook immediately queries **Azure Active Directory** to enrich the user's profile data, including their display name, job title, and their direct manager's contact info.
4. **The Tiered Response Logic:** Based on the days inactive, the playbook routes the user through a tiered protocol:
    * **Under 30 Days:** Immediate case closure (False Positive/Warning). 
    * **30 - 59 Days:** Direct email warning sent to the user.
    * **60 - 89 Days:** Escalation email sent to the user's direct manager.
    * **90+ Days:** Automated account suspension in Azure AD and case closure.
  
## Version 2 Enhancements 🚀

## 🚀 Enterprise Enhancements & Features

This connector has been heavily optimized for high-throughput, large-scale Google SecOps environments. It moves beyond standard API polling to include state management, network resilience, and UI protection.

### 📦 Smart Event Batching (Anti-Case Explosion)
To prevent SOAR UI degradation and alert fatigue, the connector aggregates breached users and chunks them into grouped cases. 
* **Dynamic Chunking:** Limits cases to **80 events per case**, safely staying under the platform's 90-event ingestion ceiling.
* **Seamless Playbook Integration:** Passes the grouped events directly to the SOAR Ontology engine, allowing playbooks to seamlessly loop through all users in the batch simultaneously.

### 🏥 Proactive Health Monitoring
Chronicle's `udmSearch` API has a hard cap of 10,000 returned events per query. 
* **Blindspot Detection:** If the log volume hits this 10K ceiling, the script automatically spawns a dedicated **Health Alert** case (`SecOps Connector Health`). 
* **Operational Awareness:** This acts as a "Check Engine" light, actively warning the engineering team that the API query is too broad and logs are potentially being dropped, preventing silent failures and false negatives.

### ⚡ Performance & Compute Optimizations
* **Lexicographical Sorting:** Removes computationally heavy `datetime` parsing from the main data ingestion loop. The script sorts and compares raw ISO 8601 strings in $O(n)$ time and only executes the math calculation once per unique user at the very end of the run.
* **Connection Pooling:** Utilizes `requests.Session()` to reuse a single, persistent TCP connection, drastically reducing TLS handshake latency across hundreds of paginated API calls.

### 🛡️ Network Resilience & Reliability
* **Automatic Retries:** Implements a `urllib3` Retry adapter. If the Google Cloud API throws a `429 Too Many Requests` or `503 Service Unavailable` due to load, the connector automatically backs off and retries.
* **OAuth Token Failsafe:** Includes a timer check inside the pagination loop. If log extraction runs longer than 50 minutes, the script automatically requests a fresh Google Cloud bearer token, preventing catastrophic `401 Unauthorized` timeouts during massive data pulls.

### 🧹 Data Normalization & Filtering
* **Case-Insensitive Deduplication:** Email addresses are immediately converted to lowercase upon extraction. This naturally merges upper and lowercase variants (e.g., `User@` vs `user@`), preventing duplicate playbook executions for the same identity without requiring complex evaluation logic.
* **Targeted Exclusions:** Includes a strict bypass filter to drop specific customer domains (e.g., `@gmail.com`), satisfying requirements to shield specific administrative or service accounts from automated suspension logic. See line 139 to adjust this filtering

### 📖 Code Readability & Maintainability
* **Global Constants:** "Magic numbers" (lookback periods, chunk sizes, page limits, and token refresh timers) have been moved to global constants at the top of the script. This makes the codebase self-documenting and allows future engineers to tune the integration parameters without digging through the pagination logic.

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
6. **🛑 IMPORTANT:** Modify the `raw_query` variable on line 48 of the script to match your specific log sources and vendor telemetry. 
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


if __name__ == "__main__":
    main()
