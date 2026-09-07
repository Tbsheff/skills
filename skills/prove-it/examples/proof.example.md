<!-- prove-it:start -->
## Prove It

**2/2 claims proven.**

| Claim | Result | Evidence |
|---|---:|---|
| The status endpoint reports that the service is ready. | ✅ | Status API (`200`) |
| Checking status in the page shows the API result. | ✅ | [Screenshot](./frontend/status-ready.png), [Short demo](./frontend/status-flow.webm) |

<details>
<summary>✅ C1: The status endpoint reports that the service is ready.</summary>

**Observed:** GET returned 200 and matched all assertions.

- Status API: `GET /api/status` → `200`

</details>

### Key state

![Ready status final state](./frontend/status-ready.png)

[Watch the short interaction demo](./frontend/status-flow.webm)

<!-- prove-it:end -->
