import datetime
from azure.kusto.data.exceptions import KustoServiceError
from typing import List, Optional
import os
import json
from concurrent.futures import ThreadPoolExecutor
import requests
import time
from google.adk.tools import ToolContext, FunctionTool
from google.adk.agents.callback_context import CallbackContext
from google.genai.types import Content, Part, FunctionCall

from ...utils.kusto_utils import execute_kusto_query

def get_all_prometheus_metrics_name_list(callback_context:CallbackContext) -> Content:
    """Retrieve all available prometheus metric names."""
    query = """
        let cosmicMDMSubscriptions = GetCOSMICMdmStamps
        | distinct SubscriptionId;
        MDMCostDistributed
        | where BillDate > ago(17d)
        | where SubscriptionId in (cosmicMDMSubscriptions)
        | where MdmAccount startswith "cosmic"
        | where MetricNamespace == "customdefault"
        | where MetricName !startswith "envoy_"
        | distinct MetricName
    """

    try:
        # Execute the Kusto query and return the results
        callback_context.state["all_available_prometheus_metrics_name_list"] = execute_kusto_query("https://resourcemanagement.westus2.kusto.windows.net", "prod", query, False)
        return Content(
                parts=[Part(text=f"Agent {callback_context.agent_name} executed successfully.")],
                role="model" # Assign model role to the overriding response
            )
    except Exception as e:
        return Content(
                parts=[Part(text=f"Agent {callback_context.agent_name} executed failed.")],
                role="model" # Assign model role to the overriding response
            )

get_all_prometheus_metrics_name_list_tool = FunctionTool(func=get_all_prometheus_metrics_name_list)

def get_cluster_name() -> str:
    """
    Retrieve a Cosmic AKS cluster name from environment variable or Kusto database.
    
    First checks if COSMICCLUSTERNAME environment variable exists.
    If not, queries from Kusto database and sets the environment variable.
    
    Returns:
        str: a Cosmic AKS cluster name
    """
    # 首先检查环境变量是否已存在
    cluster_name = os.environ.get("COSMICCLUSTERNAME")
    if cluster_name:
        return cluster_name
        
    # 如果环境变量不存在，执行原有逻辑获取集群名
    current_time = datetime.datetime.now() - datetime.timedelta(days=8)
    formatted_month = f"{current_time.month:02d}"
    formatted_day = f"{current_time.day:02d}"
    query = f"""
    AllEandDCosts_{current_time.year}_{formatted_month}_{formatted_day}
    | where ServiceTreeService == "COSMIC Platform"
    | where ResourceId contains "/providers/microsoft.containerservice/managedclusters/cosmic-prod-" and ResourceId contains "-nam-"
    | top 1 by Cost
    | parse ResourceId with * "/providers/microsoft.containerservice/managedclusters/" ClusterName
    | distinct ClusterName
    """
    
    try:
        # Execute the Kusto query and return the results
        results = execute_kusto_query("https://resourcemanagement.westus2.kusto.windows.net", "prod", query, False)
        
        cluster_name = results[0] if results else ""
        
        # 如果查询成功，将结果设置为环境变量
        if cluster_name:
            os.environ["COSMICCLUSTERNAME"] = cluster_name
            
        return cluster_name
    except KustoServiceError as e:
        raise KustoServiceError(f"Error executing Kusto query: {str(e)}")
    except Exception as e:
        raise ValueError(f"Failed to connect to Kusto or execute query: {str(e)}")

def get_prometheus_metric_lable_name_and_example_value(callback_context:CallbackContext) -> Content:
    """Retrieve an example value of some specified prometheus metrics and save them to the tool context.
    
    Args:
    
    Returns:
        dict: status, metric_name, example lable value or error msg.
    """
    try:
        # Pass the cluster name to the JavaScript context
        cluster_name = get_cluster_name()
        cookie = os.getenv("GRAFANACOOKIE")
        metric_name_list = callback_context.state["current_prometheus_metrics_need_get_value"]["prom_metrics_needs_to_be_investigated_name_list"]
        la_table_name = callback_context.state["name_of_current_target_la_table_needs_investigate_alternatives"]

        full_state_name = "prometheus_metrics_lable_name_and_example_value"
        current_value_state_name = "prom_metrics_value_for_current_target_la_kusto_table"
        name_only_state_name = "investigated_prom_metrics_for_current_target_la_kusto_table"
        if (full_state_name not in callback_context.state):
            callback_context.state[full_state_name] = {}
        if (current_value_state_name not in callback_context.state):
            callback_context.state[current_value_state_name] = {}
        if (name_only_state_name not in callback_context.state):
            callback_context.state[name_only_state_name] = []


        def fetch(metric_name):
            return metric_name, fetch_example_for_metric_py(cookie, metric_name, cluster_name)

        with ThreadPoolExecutor() as executor:
            results = list(executor.map(fetch, metric_name_list))

        for metric_name, result in results:
            callback_context.state[full_state_name][metric_name] = result
            callback_context.state[current_value_state_name][metric_name] = result
            callback_context.state[name_only_state_name].append(metric_name)
        
        return Content(
                parts=[Part(text=f"Agent {callback_context.agent_name} executed, for {la_table_name} la table replacement, fetched example label and value for prom metrics: {metric_name_list}.")],
                role="model" # Assign model role to the overriding response
            )
    except Exception as e:
        return Content(
            parts=[Part(text=f"Agent {callback_context.agent_name} executed failed, error: {str(e)}.")],
            role="model" # Assign model role to the overriding response
        )

def validate_prometheus_query(callback_context:CallbackContext) -> Content:
    """
    validate a prometheus query by executing query in grafana.
    If the query is valid, store the result in the callback context state.
    """
    try:
        # Get the Prometheus query from the callback context
        state = callback_context.state
        promql_query = state.get("current_prometheusQL_for_validation", "")
        
        # Get the cookie from environment variable
        cookie = os.getenv("GRAFANACOOKIE")
        
        if not promql_query or promql_query == "''" or promql_query == '""':
            # Store the validation result in the callback context state
            callback_context._event_actions.escalate = True
            state["validation_passed"] = True
            if "PromQL_of_kusto_dag_node" in callback_context.state:
                state["PromQL_of_kusto_dag_node"].append(state["PromQL_of_current_kusto_dag_node"])
            else:
                state["PromQL_of_kusto_dag_node"] = [state["PromQL_of_current_kusto_dag_node"]]
            return Content(
                parts=[Part(text=f"Agent {callback_context.agent_name} execution successfully. PromQL query block is not expected to be executed.")],
                role="model"
            )
            
        if not cookie:
            state["validation_passed"] = False
            return Content(
                parts=[Part(text=f"Agent {callback_context.agent_name} execution failed: GRAFANACOOKIE environment variable not found.")],
                role="model" 
            )
        
        # Execute the Prometheus query and get results
        result = execute_prometheus_query(promql_query, cookie)
        
        if result['status'] == "success":
            # Store the validation result in the callback context state
            callback_context._event_actions.escalate = True
            # Do not append the result to state["PromQL_of_kusto_dag_node"] because it still needs human verification
            
            state["validation_passed"] = True
            return Content(
                parts=[Part(text=f"Agent {callback_context.agent_name} execution successfully. PromQL query has been validated and result stored in context..")],
                role="model"
            )
        else:
            state["validation_passed"] = False
            return Content(
                parts=[Part(text=f"Agent {callback_context.agent_name} executed. PromQL query validation failed. Start to refine")],
                role="model"
            )

    except Exception as e:
        return Content(
            parts=[Part(text=f"Agent {callback_context.agent_name} execution failed: {str(e)}")],
            role="model"
        )

def validate_human_prometheus_query(callback_context:CallbackContext) -> Content:
    """
    validate a prometheus query by executing query in grafana.
    If the query is valid, store the result in the callback context state.
    """
    try:
        # Get the Prometheus query from the callback context
        state = callback_context.state
        promql_query = state.get("current_prometheusQL_for_validation", "")
        
        # Get the cookie from environment variable
        cookie = os.getenv("GRAFANACOOKIE")
        
        if not promql_query or promql_query == "''" or promql_query == '""':
            # Store the validation result in the callback context state
            callback_context._event_actions.escalate = True
            state["validation_passed"] = True
            if "PromQL_of_kusto_dag_node" in callback_context.state:
                state["PromQL_of_kusto_dag_node"].append(state["PromQL_of_current_kusto_dag_node"])
            else:
                state["PromQL_of_kusto_dag_node"] = [state["PromQL_of_current_kusto_dag_node"]]
            return Content(
                parts=[Part(text=f"Agent {callback_context.agent_name} execution successfully. PromQL query block is not expected to be executed.")],
                role="model"
            )
            
        if not cookie:
            state["validation_passed"] = False
            return Content(
                parts=[Part(text=f"Agent {callback_context.agent_name} execution failed: GRAFANACOOKIE environment variable not found.")],
                role="model" 
            )
        
        # Execute the Prometheus query and get results
        result = execute_prometheus_query(promql_query, cookie)
        
        if result['status'] == "success":
            # Store the validation result in the callback context state
            callback_context._event_actions.escalate = True
            if "PromQL_of_kusto_dag_node" in callback_context.state:
                state["PromQL_of_kusto_dag_node"].append(state["PromQL_of_current_kusto_dag_node"])
            else:
                state["PromQL_of_kusto_dag_node"] = [state["PromQL_of_current_kusto_dag_node"]]
            
            state["validation_passed"] = True
            return Content(
                parts=[Part(text=f"Agent {callback_context.agent_name} execution successfully. PromQL query has been validated and result stored in context..")],
                role="model"
            )
        else:
            state["validation_passed"] = False
            return Content(
                parts=[Part(text=f"Agent {callback_context.agent_name} executed. PromQL query validation failed. Start to refine")],
                role="model"
            )

    except Exception as e:
        return Content(
            parts=[Part(text=f"Agent {callback_context.agent_name} execution failed: {str(e)}")],
            role="model"
        )

def get_prometheus_metric_lable_name_and_example_value_batch(metric_name: List[str], tool_context: ToolContext) -> dict:
    """Retrieve an example value of a specified prometheus metric in parallel.
    
    Args:
        metric_name (str): The name of the prometheus metric to retrieve an example lable value for.
    
    Returns:
        dict: status, metric_name, example lable value or error msg.
    """
    try:
        # Pass the cluster name to the JavaScript context
        cluster_name = get_cluster_name()
        cookie = os.getenv("GRAFANACOOKIE")
        
        # Define a custom function to get example value for the specific metric
        result = fetch_example_for_metric_py(cookie, metric_name, cluster_name)
        state_name = "prometheus_metrics_lable_name_and_example_value"
        json_result = json.dumps(result)
        if (state_name not in tool_context.state):
            tool_context.state[state_name] = {}
        tool_context.state[state_name][metric_name] = result
        
        return {
            "status": result.get("status", "error"),
            "metric_name": metric_name,
            "example_value": result
        }
    except Exception as e:
        return {
            "status": "error",
            "metric_name": metric_name,
            "error_message": str(e)
        }

def execute_prometheus_query(query: str, cookie: str) -> dict:
    datasources = {
        '2LZ5icZVk': 'CosmicMdmProdNam',
        'ddns8c8j1iz9cb': 'CosmicMdmProdNam-WinProcess',
    }

    requests_list = []
    timestamp_on_query = int(time.time() * 1000) - 86400000  # 24 hours ago in milliseconds

    # Build request objects for all datasources with the specified metric
    for uid in datasources:
        requests_list.append({
            "url": "https://cosmicmonitoring-b6a0cza8a4ghfnda.scus.grafana.azure.com/api/ds/query?ds_type=prometheus&requestId=explore_jq2",
            "uid": uid,
            "dataSource": datasources[uid],
            "body": {
                "queries": [{
                    "refId": "A",
                    "expr": query,
                    "range": False,
                    "instant": True,
                    "datasource": {
                        "type": "prometheus",
                        "uid": uid
                    },
                    "editorMode": "code",
                    "legendFormat": "__auto",
                    "key": "Q-660a4e71-2dc1-4937-8de8-299e0c2b8472-0",
                    "format": "table",
                    "exemplar": False,
                    "requestId": "25562A",
                    "utcOffsetSec": 28800,
                    "interval": "",
                    "datasourceId": 151,
                    "intervalMs": 60000,
                    "maxDataPoints": 717
                }],
                "from": f"{timestamp_on_query}",
                "to": f"{timestamp_on_query}"
            }
        })

    headers = {
        'Cookie': cookie,
        'Content-Type': 'application/json'
    }

    # Try each request until we get a successful response
    for request_obj in requests_list:
        try:
            response = requests.post(
                url=request_obj["url"],
                headers=headers,
                json=request_obj["body"],
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                        'status': "success",
                        'data': data,
                    }
        except Exception as error:
            print(f"Error processing request: {request_obj['url']} - {str(error)}")
            continue

    return {
        'status': "error",
        'error_message': "No data found for the specified metric",
    }


def fetch_example_for_metric_py(cookie: str, metric_name: str, cluster_name: str) -> dict:
    """Python version of the fetchExampleForMetric JavaScript function.
    
    Args:
        cookie (str): Grafana cookie for authentication
        metric_name (str): Name of the Prometheus metric to query
        cluster_name (str): Name of the cluster to query data from
        
    Returns:
        dict: Dictionary containing status and labels or error message
    """

    result = execute_prometheus_query(f"topk(1, {metric_name}{{cluster=\"{cluster_name}\"}})", cookie)
    if result['status'] != "success":
        return result
    data = result['data']
    if (data and 'results' in data and 'A' in data['results'] and
    'frames' in data['results']['A'] and len(data['results']['A']['frames']) > 0 and
    'schema' in data['results']['A']['frames'][0] and 
    'fields' in data['results']['A']['frames'][0]['schema'] and
    len(data['results']['A']['frames'][0]['schema']['fields']) > 1):
        return {
            'status': "success",
            'labels': data['results']['A']['frames'][0]['schema']['fields'][1]['labels'],
        }
    else:
        return {
            'status': "error",
            'error_message': "No data found for the specified metric",
        }

if __name__ == "__main__":

    def base_test():
        # 测试函数
        try:
            test_cluster = "https://resourcemanagement.westus2.kusto.windows.net"
            test_database = "staging"
            test_query = """
                let cosmicMDMSubscriptions = GetCOSMICMdmStamps
                | distinct SubscriptionId;
                MDMCostDistributed
                | where BillDate > ago(17d)
                | where SubscriptionId in (cosmicMDMSubscriptions)
                | where MdmAccount startswith "cosmic"
                | where MetricNamespace == "customdefault"
                | distinct MetricName
                """
            
            print(f"执行测试查询: {test_query}")
            results = execute_kusto_query(test_cluster, test_database, test_query)
            
            print("查询结果:")
            for idx, result in enumerate(results):
                print(f"{idx + 1}. {result}")
        except Exception as e:
            print(f"测试执行失败: {str(e)}")

    def test_get_an_example_value_of_prometheus_metric():
        # 测试获取 Prometheus 指标示例值
        metric_name = "kube_pod_container_status_waiting"
        result = get_prometheus_metric_lable_name_and_example_value(metric_name)
        print(f"指标名称: {metric_name}")
        print(f"示例值: {result}")

    test_get_an_example_value_of_prometheus_metric()