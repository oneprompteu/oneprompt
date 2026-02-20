# oneprompt-sdk

Lightweight cloud-only Python SDK for oneprompt.

```python
import oneprompt_sdk as op

client = op.Client(oneprompt_api_key="op_live_...")
result = client.query("Top products by revenue", dataset_id="ds_123")
print(result.summary)
```
