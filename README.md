# Google SecOps: Automated Stale Account Suspension

This repository contains a custom Google SecOps (Chronicle) SOAR integration and playbook designed to automatically detect, warn, and suspend inactive user accounts via Azure Active Directory.

By natively querying Google Chronicle for raw login events, processing the data locally, and executing a tiered response playbook, this pipeline minimizes your attack surface with zero manual intervention required.

## 📖 Use Case Overview

This workflow is a fully automated, end-to-end solution:

1. **The Detection Engine (Daily Log Pull):** A custom Python connector securely queries the Google SecOps `udmSearch` API. It searches for `USER_LOGIN` events and pulls up to 90 days of history, cleanly handling API pagination for enterprise-scale environments.
2. **Local Processing & Case Creation:** The connector groups the logs by user, finds the exact timestamp of their most recent login, and calculates how many days have passed since they last authenticated. If a user breaches the inactivity threshold, a case is generated in the SOAR queue.
3. **The Automation Playbook:** The playbook immediately queries **Azure Active Directory** to enrich the user's profile data, including their display name, job title, and their direct manager's contact info.
4. **The Tiered Response Logic:** Based on the days inactive, the playbook routes the user through a tiered protocol:
    * **Under 30 Days:** Immediate case closure (False Positive/Warning).
    * **30 - 59 Days:** Direct email warning sent to the user.
    * **60 - 89 Days:** Escalation email sent to the user's direct manager.
    * **90+ Days:** Automated account suspension in Azure AD and case closure.

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
