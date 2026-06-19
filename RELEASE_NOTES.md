# Release Notes: SecOps Inactive Accounts Connector (v4.0.0)

This release details the major structural upgrade of the stale account detection connector from the legacy synchronous UDM Search endpoint to the modern Google Security Operations (Chronicle) Asynchronous Search API.

---

## [4.0.0] - 2026-06-19

### Added
- **Asynchronous Search Integration**: Connector now leverages the `projects.locations.instances.search` API endpoint, sending queries to run as background long-running operations (LROs) and retrieving results from the generated `SearchSession` under `/searchedResults`.
- **Expanded Scaling Limit**: The query result capacity is expanded from 10,000 to up to **1,000,000 (1 million) events**.
- **Page Token Navigation**: Implemented correct cursor-based pagination loop querying `pageSize` (10K per request) and tracking `pageToken`/`nextPageToken`.
- **Health Warning Calibration**: Raised the operational blindspot detection health alert threshold from 10K to 1M events (`ASYNC_LIMIT`).

### Fixed
- **Query Dialect Configuration**: Configured the mandatory `"dialect": "YL2"` request property in the search request body. Without this dialect explicitly defined, Chronicle async queries evaluate to 0 matching events.
- **Canonical TimeRange Mapping**: Resolved an issue where time ranges were silently ignored by replacing the snake_case `start_time` and `end_time` properties inside the JSON request body with their canonical lowerCamelCase representations (`startTime` and `endTime`).
- **OAuth Token Refresh Failsafe**: Duplicated the 50-minute OAuth token check inside both the background operation polling loop and the page token result-fetching loop to prevent 401 Unauthorized timeouts on massive data pulls.
- **Connection Retry Handling**: Expanded the urllib3 Retry pooling adapter to support both `GET` (polling/list results) and `POST` (search session creation) requests.

### Performance Optimizations
- **TCP Connection Reuse**: Reuses persistent HTTP sessions across all polling and pagination requests, significantly speeding up data transfers.
- **Lexicographical Date Compares**: Eliminates expensive datetime parse functions within the main event iteration loop by comparing ISO 8601 strings directly in O(N) time.
