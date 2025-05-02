import datetime
from azure.kusto.data.exceptions import KustoServiceError
from typing import List, Optional
import os
import json
import requests
import time

from ..utils.kusto_utils import execute_kusto_query

def get_log_analytics_table_example_value(log_analytics_table_name: str) -> dict:
    """Retrieve an example row of a specified log analytics Kusto table.
    
    Args:
        log_analytics_table_name (str): The name of the log analytics table to query.
    
    Returns:
        dict: status and a list contains all available prometheus metric name or error msg.
    """
    query = f"""
        {log_analytics_table_name}
        | where ingestion_time() > ago(30d)
        | take 1
    """
    
    try:
        # Execute the Kusto query and return the results
        return {
            "status": "success",
            "la_table_example_value": execute_kusto_query("https://ade.loganalytics.io/subscriptions/b82ee959-ba86-4925-be8d-e1e5f81dfc92/resourcegroups/cosmic-prod-monitoring-rg/providers/microsoft.operationalinsights/workspaces/cosmic-monitoring-prod-nam-workspace", "cosmic-monitoring-prod-nam-workspace", query),
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e),
        }

if __name__ == "__main__":
    def test_get_an_example_value_of_prometheus_metric():
        # 测试获取 Prometheus 指标示例值
        os.environ["KUSTOTOKEN"] = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IkNOdjBPSTNSd3FsSEZFVm5hb01Bc2hDSDJYRSIsImtpZCI6IkNOdjBPSTNSd3FsSEZFVm5hb01Bc2hDSDJYRSJ9.eyJhdWQiOiJodHRwczovL2t1c3RvLmt1c3RvLndpbmRvd3MubmV0IiwiaXNzIjoiaHR0cHM6Ly9zdHMud2luZG93cy5uZXQvY2RjNWFlZWEtMTVjNS00ZGI2LWIwNzktZmNhZGQyNTA1ZGMyLyIsImlhdCI6MTc0NTczMTcwNSwibmJmIjoxNzQ1NzMxNzA1LCJleHAiOjE3NDU3MzY1NzgsImFjciI6IjEiLCJhaW8iOiJBWFFBaS84WkFBQUFOMklwdlFOT05LeXhMdWVpUUIvNkFJaU5PVWhoNzlrWTUrZUQvL3FmMzVrS0E2Y0E2Mjh3WXpDNmRSK1lWbmU2YnFqaXFIRFhPYUtLT3d1aTR4ZXEzV1FySC93dVJ2bmYyZHBRV2kyK2c3RzdFMEJ2QVIySzdPS25kUW5QNVNvNDMzaUhFQ3AxRmh5RExMSWppQURkL0E9PSIsImFtciI6WyJyc2EiLCJtZmEiXSwiYXBwaWQiOiJmOTgxOGU1Mi01MGJkLTQ2M2UtODkzMi1hMTY1MGJkM2ZhZDIiLCJhcHBpZGFjciI6IjAiLCJpZHR5cCI6InVzZXIiLCJpcGFkZHIiOiIyNDA0OmY4MDE6YjA4MDowOjdmOTc6OjY4IiwibmFtZSI6IllpbmdjaGFvIEx2IChkZWJ1ZykiLCJvaWQiOiJkODcyZjk3My0zZmMzLTQ3N2UtYjMyZC0zOTliNmJjNmJhMGYiLCJwdWlkIjoiMTAwMzIwMDFENDUyODU4RSIsInJoIjoiMS5BVk1CNnE3RnpjVVZ0azJ3ZWZ5dDBsQmR3bmZxUmljQ1IwVkxnTW84bC1hQTZMZFRBVDVUQVEuIiwic2NwIjoidXNlcl9pbXBlcnNvbmF0aW9uIiwic2lkIjoiMDA0MTJmOTktMWM0YS1mNWE2LTIyYTUtMWQ3ZWVmZGNlMWI0Iiwic3ViIjoiWXdVSUd2YXphbXBVOHowWEJKbGJEQ3IzUF9CMmd4ZXhUQ0V3YUFMOUVYRSIsInRlbmFudF9jdHJ5IjoiVVMiLCJ0ZW5hbnRfcmVnaW9uX3Njb3BlIjoiTkEiLCJ0aWQiOiJjZGM1YWVlYS0xNWM1LTRkYjYtYjA3OS1mY2FkZDI1MDVkYzIiLCJ1bmlxdWVfbmFtZSI6InlpbmdjaGFvbHZfZGVidWdAcHJkdHJzMDEucHJvZC5vdXRsb29rLmNvbSIsInVwbiI6InlpbmdjaGFvbHZfZGVidWdAcHJkdHJzMDEucHJvZC5vdXRsb29rLmNvbSIsInV0aSI6IjRncG9HUFdWakUySnhFQjF0S05GQUEiLCJ2ZXIiOiIxLjAiLCJ4bXNfaWRyZWwiOiIyIDEifQ.J-WXVN-0TvFkuVdzhL61G9LVgctbNJiOAewgPZ0RaDcc1HD2JWwEr96ymWbzdsholGUXuqKTrOQ89FpOJw3J95txMcNS3oaGpgWDoHzQhm3pztp61en8kNz-LCAMCj2hRTQfYCuJ7Dqccbo1wJG5UpNFRPVieIQ57Wk-r2GFMXTxP-9CMoEr1E0c3BarAWH5Mstf2uYhFMJVNqPvvjAJEUlqLbpWsv52SSfl5AFD5KqrEJYsY5t3zdotzsmNEuLPK_WCX2v1XkBtyeAtue1Dr2Qbk13mi4aqUZVz-1JtrEWrCEDr7d9VgFbc6G-3S4YKkFwNe0BGqnIRpc9n37pYOw"
        metric_name = "CosmicDeployment_CL"
        result = get_log_analytics_table_example_value(metric_name)
        print(f"指标名称: {metric_name}")
        print(f"示例值: {result}")

    test_get_an_example_value_of_prometheus_metric()