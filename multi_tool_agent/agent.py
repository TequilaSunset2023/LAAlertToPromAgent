from typing import Optional
from dotenv import load_dotenv

from multi_tool_agent.tools.get_kql_dag import parse_kql_query
from multi_tool_agent.utils.human_in_the_loop_agent import MyHILAgent
from multi_tool_agent.utils.my_loop_agent import MyLoopAgent

load_dotenv()

import datetime
import os
import subprocess
import json
from zoneinfo import ZoneInfo
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools import ToolContext, FunctionTool
from google.adk.agents import LlmAgent, SequentialAgent, LoopAgent, BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.lite_llm import LiteLlm, LlmResponse
from google.genai.types import Content, Part, FunctionCall, GenerateContentConfig
from google.adk.planners.built_in_planner import BuiltInPlanner
from pydantic import BaseModel, Field
from .tools.get_an_example_value_of_prom.get_an_example_value_of_prom_func import get_all_prometheus_metrics_name_list, get_prometheus_metric_lable_name_and_example_value, validate_prometheus_query, get_cluster_name, validate_human_prometheus_query
from .tools.get_log_analytics_table_example_value import get_log_analytics_table_example_value
from .utils.kusto_utils import execute_kusto_query

class Corresponding_prom_metric_of_la_table_finding_agent_input(BaseModel):
    log_analytics_table_name: str = Field(
        description="The name of the log analytics table to query."
    )

"""
usage: after_agent_callback=transfer_to_parent_callback
"""
def transfer_to_parent_callback(callback_context:CallbackContext):
    #callback_context._event_actions.transfer_to_agent = "la_alert_translator_agent"
    #callback_context._event_actions.escalate = True
    return Content(
        parts=[
            Part(
                function_call=FunctionCall(
                    args = {"agent_name": "la_alert_translator_agent"},
                    name="transfer_to_agent"
                )
            )
        ],
        role="model"
    )

def get_target_la_table_name_and_example_value_callback(callback_context:CallbackContext) -> Content|None:
    """Get target la kusto table name and example value."""
    callback_context.state["prometheus_metrics_lable_name_and_example_value"] = {}
    callback_context.state["investigated_prom_metrics_for_current_target_la_kusto_table"] = []
    if len(callback_context.state["name_of_all_la_kusto_table_needed_replacement"]) > 0 \
        and len(callback_context.state["name_of_all_la_kusto_table_needed_replacement"].get("log_analytics_table_name_list", [])) > 0 \
        and len(callback_context.state["name_of_all_la_kusto_table_needed_replacement"].get("log_analytics_table_usage_list", [])) > 0:
        
        log_analytics_table_name = callback_context.state["name_of_all_la_kusto_table_needed_replacement"]["log_analytics_table_name_list"][0]
        log_analytics_table_usage = callback_context.state["name_of_all_la_kusto_table_needed_replacement"]["log_analytics_table_usage_list"][0]
        callback_context.state[f"name_of_current_target_la_table_needs_investigate_alternatives"] = log_analytics_table_name
        callback_context.state[f"usage_of_current_target_la_table_needs_investigate_alternatives"] = log_analytics_table_usage

        query = f"""
            {log_analytics_table_name}
            | where ingestion_time() > ago(30d)
            | take 1
        """
        
        try:
            example_value = execute_kusto_query("https://ade.loganalytics.io/subscriptions/b82ee959-ba86-4925-be8d-e1e5f81dfc92/resourcegroups/cosmic-prod-monitoring-rg/providers/microsoft.operationalinsights/workspaces/cosmic-monitoring-prod-nam-workspace", "cosmic-monitoring-prod-nam-workspace", query)
            callback_context.state[f"example_value_of_current_target_la_table_needs_investigate_alternatives"] = example_value
            # Execute the Kusto query and return the results
            return None
        except Exception as e:
            return Content(
                    parts=[Part(text=f"Agent {callback_context.agent_name} executed failed, cann't get example value of la table {log_analytics_table_name}, error: {str(e)}.")],
                    role="model" # Assign model role to the overriding response
                )

        return None
    else:
        return Content(
                parts=[Part(text=f"Agent {callback_context.agent_name} executed failed, there is no more la table to be processed.")],
                role="model" # Assign model role to the overriding response
            )

def update_pending_task_and_result_states(la_table_name:str, prometheus_metric_candidates: list[str], tool_context: ToolContext):
    """You MUST call this function to save the result into state when you found corresponding prometheus_metric."""
    
    if len(tool_context.state["name_of_all_la_kusto_table_needed_replacement"]) > 0 \
        and len(tool_context.state["name_of_all_la_kusto_table_needed_replacement"].get("log_analytics_table_name_list", [])) > 0 \
        and len(tool_context.state["name_of_all_la_kusto_table_needed_replacement"].get("log_analytics_table_usage_list", [])) > 0:
        
        la_table_name = tool_context.state["name_of_all_la_kusto_table_needed_replacement"]["log_analytics_table_name_list"].pop(0)
        la_table_usage = tool_context.state["name_of_all_la_kusto_table_needed_replacement"]["log_analytics_table_usage_list"].pop(0)
        result_state_name = "prometheus_metrics_candidate_of_a_la_table"
        if result_state_name not in tool_context.state:
            tool_context.state[result_state_name] = {}
        tool_context.state[result_state_name][la_table_name] = prometheus_metric_candidates
        return {
                "status": "success",
            }
    else:
        return {
            "status": "error",
            "error_message": "No need to update since there is no la kusto table needs to be processed."
        }

update_pending_task_and_result_states_tool = FunctionTool(func=update_pending_task_and_result_states)

llm_config = GenerateContentConfig(
    temperature=0.2,
    #top_p=0.2
)

corresponding_prom_metric_of_la_table_finding_agent_old = LlmAgent(
    name="corresponding_prom_metric_of_la_table_finding_agent",
    model=LiteLlm(model="azure/gpt-4o-mini"),
    description=(
        "Agent to find one or multi prometheus metrics which can replace a given log analytics(la) Kusto table."
    ),
    instruction=(
        f"""
        You are a professional agent who find one or multi prometheus metrics which can partially or fully replace this log analytics(la) Kusto table: {{name_of_current_target_la_table_needs_investigate_alternatives}}
        DO NOT CARE ANY OTHER log analytics(la) Kusto tables.
        If there is an error in the tool response, you can take that prometheus metrics as unqualified.
        Find all prometheus metric(s) from given available metric name list below.

        Your response must be in List<str> format.
        response format example:
        ["kube_pod_info", "kube_pod_container_info", "kube_pod_container_status_waiting", "kube_pod_container_status_terminated_reason"]
        
        **Target la kusto table name: **
        {{name_of_current_target_la_table_needs_investigate_alternatives}}

        **Target la kusto table usage:**
        {{usage_of_current_target_la_table_needs_investigate_alternatives}}

        **Target la kusto table example value:**
        {{example_value_of_current_target_la_table_needs_investigate_alternatives}}

        **Available prometheus metrics list:**
        {{all_available_prometheus_metrics_name_list}}
        """
    ),
    # input_schema=Corresponding_prom_metric_of_la_table_finding_agent_input,
    # 可能需要把get_target_la_table_name_tool 变成before agent callback
    # 把update_pending_task_and_result_states_tool，变成 after agent callback, 然后参数传递完全用state
    # get_log_analytics_table_example_value 要获取带schema的
    tools=[
        get_prometheus_metric_lable_name_and_example_value,
        update_pending_task_and_result_states_tool
    ],
    before_agent_callback=get_target_la_table_name_and_example_value_callback,
    generate_content_config=llm_config
)

def check_if_need_exit_loop(callback_context:CallbackContext) -> Content:
    """Call this function ONLY when the critique indicates no further changes are needed, signaling the iterative process should end."""
    agent_name = callback_context.agent_name

    if len(callback_context.state["name_of_all_la_kusto_table_needed_replacement"]) == 0 or len(callback_context.state["name_of_all_la_kusto_table_needed_replacement"]["log_analytics_table_name_list"]) == 0:
        callback_context._event_actions.escalate = True
        return Content(
                parts=[Part(text=f"Agent {agent_name} exit the loop.")],
                role="model" # Assign model role to the overriding response
            )
    else:
        # return None to continue
        return Content(
                parts=[Part(text=f"Agent {agent_name} continue the loop.")],
                role="model" # Assign model role to the overriding response
            )

# add a before_agent_callback to check
corresponding_prom_metric_finding_task_checker_agent = BaseAgent(
    name="corresponding_prom_metric_finding_task_checker_agent",
    description=(
        "Agent to check if the task of finding corresponding prometheus metric is done."
    ),
    before_agent_callback=check_if_need_exit_loop
)

def save_tool_output_into_state(callback_context:CallbackContext):
    """Call this function ONLY when the critique indicates no further changes are needed, signaling the iterative process should end."""
    agent_name = callback_context.agent_name
    
    if len(callback_context.state["name_of_all_la_kusto_table_needed_replacement"]) == 0:
        callback_context._event_actions.escalate = True
        return Content(
                parts=[Part(text=f"Agent {agent_name} skipped by before_agent_callback due to state.")],
                role="model" # Assign model role to the overriding response
            )
    else:
        # return None to continue
        return None

load_all_available_prometheus_metrics_name_agent = BaseAgent(
    name="load_all_available_prometheus_metrics_name_agent",
    description=(
        "Agent to load all available prometheus metrics name list."
    ),
    before_agent_callback=get_all_prometheus_metrics_name_list
)

class get_all_referenced_la_table_agent_output(BaseModel):
    log_analytics_table_name_list: list[str] = Field(
        description="The name list of all referenced log analytics tables."
    ),
    log_analytics_table_usage_list: list[str] = Field(
        description="The usage description list for each referenced log analytics tables."
    )

get_all_referenced_la_tables_agent = LlmAgent(
    name="get_all_referenced_la_table_agent",
    model=LiteLlm(model="azure/gpt-4o-mini"),
    description=(
        "Agent to analyze all log analytics kusto tables referenced by a KQL."
    ),
    instruction=(
        """
        You are a helpful agent who analyze all log analytics kusto tables referenced by a KQL given by user.
        Your response MUST be a raw json which can be deserialized directly, Do not use markdown marks like ```json, 

        response format example:
        {
            "log_analytics_table_name_list": ["Table1", "Table2", "Table3"],
            "log_analytics_table_usage_list": ["Only take running pod from Table1", "Get avg CPU usage of all pods from xxx image", "Get container id and image id mapping"]
        }

        """
    ),
    output_key="name_of_all_la_kusto_table_needed_replacement",
    output_schema=get_all_referenced_la_table_agent_output
)

class Prom_metrics_need_to_be_investigated(BaseModel):
    prom_metrics_needs_to_be_investigated_name_list: list[str] = Field(
        description="The name list of prometheus metrics whch needs to be investigated."
    )

find_more_potential_related_prom_metric_agent = LlmAgent(
    name="find_more_potential_related_prom_metric_agent",
    model=LiteLlm(model="azure/gpt-4o-mini"),
    description=(
        "Agent to find potential related prometheus metrics which can replace a given log analytics(la) Kusto table with specific usage."
    ),
    instruction=(
        f"""
        You are a professional agent who find one or multi prometheus metrics which can partially or fully replace a given log analytics(la) Kusto table and has not been investigated yet.
        Your response must be in raw Json format which can be deserialized directly, DO NOT use markdown marks like ```json.
        response format example:
        {{
            "prom_metrics_needs_to_be_investigated_name_list": ["kube_pod_info", "kube_pod_container_info", "kube_pod_container_status_waiting", "kube_pod_container_status_terminated_reason"]
        }}

        **Target la kusto table name: **
        {{name_of_current_target_la_table_needs_investigate_alternatives}}

        **Target la kusto table usage:**
        {{usage_of_current_target_la_table_needs_investigate_alternatives}}

        **Target la kusto table example value:**
        {{example_value_of_current_target_la_table_needs_investigate_alternatives}}

        **Actual user Azure log analytics kusto query:**
        {{kusto_query}}

        **Prometheus metrics already investigated**
        {{investigated_prom_metrics_for_current_target_la_kusto_table}}

        **Available prometheus metrics list:**
        {{all_available_prometheus_metrics_name_list}}
        """
    ),
    include_contents='none',
    output_key="current_prometheus_metrics_need_get_value",
    output_schema=Prom_metrics_need_to_be_investigated,
)

fetch_prometheus_metrics_value_agent = BaseAgent(
    name="fetch_prometheus_metrics_value_agent",
    description=(
        "Agent to fetch prometheus metrics value."
    ),
    before_agent_callback=get_prometheus_metric_lable_name_and_example_value
)

fetch_prometheus_metrics_value_agent_old = LlmAgent(
    name="fetch_prometheus_metrics_value_agent",
    model=LiteLlm(model="azure/gpt-4o-mini"),
    description=(
        "Agent to fetch prometheus metrics value."
    ),
    instruction=(
        """
        You are a professional agent who fetch prometheus metrics value for given prometheus metrics by calling "get_prometheus_metric_lable_name_and_example_value" tool.
        The tool will return nothing to you but it will update the states directly, 
        once you call it with specific parameter, it will save the prometheus metrics values silcencly.

        **Prometheus metrics names you need fetch labels and values: **
        {current_prometheus_metrics_need_get_value}
        """
    ),
    include_contents='none',
    # this tool get and save prometheus metrics value into 
    #   state["prometheus_metrics_lable_name_and_example_value"][metric_name] = result
    # also save the prometheus metrics value into
    #   state["prom_metrics_value_for_current_target_la_kusto_table"][metric_name] = result
    # and also save the prometheus metrics name into 
    #   state["investigated_prom_metrics_for_current_target_la_kusto_table"].append(metric_name)
    tools=[get_prometheus_metric_lable_name_and_example_value]
)

def add_new_prom_metrics_candidate_and_exit_if_enough_candidates(callback_context:CallbackContext) -> Content:
    """Add new qualified prometheus candidates to candidates list and terminate the loop if we already have enough."""
    state = callback_context.state
    target_la_table_name = state["name_of_current_target_la_table_needs_investigate_alternatives"]
    result_state_name = "prometheus_metrics_candidate_of_a_la_table"
    good_prom_candidates = state["good_prom_candidates_and_if_enough_candidates"]["new_qualified_prom_candidates"]
    if_enough_candidates = state["good_prom_candidates_and_if_enough_candidates"]["if_enough_candidates"]
    if result_state_name not in state:
        state[result_state_name] = {}
    if target_la_table_name not in state[result_state_name]:
        state[result_state_name][target_la_table_name] = []
    state[result_state_name][target_la_table_name].extend(good_prom_candidates)
    
    if if_enough_candidates:
        callback_context._event_actions.escalate = True
        #callback_context._event_actions.transfer_to_agent = "corresponding_prom_metric_finding_task_checker_agent"
        if len(state["name_of_all_la_kusto_table_needed_replacement"]) > 0 \
            and len(state["name_of_all_la_kusto_table_needed_replacement"].get("log_analytics_table_name_list", [])) > 0 \
            and len(state["name_of_all_la_kusto_table_needed_replacement"].get("log_analytics_table_usage_list", [])) > 0:
            
            la_table_name = state["name_of_all_la_kusto_table_needed_replacement"]["log_analytics_table_name_list"].pop(0)
            la_table_usage = state["name_of_all_la_kusto_table_needed_replacement"]["log_analytics_table_usage_list"].pop(0)
            return Content(
                parts=[
                    Part(
                        text=f"Agent {callback_context.agent_name} exit the loop and added {good_prom_candidates} into candidates of {target_la_table_name}."
                    ),
                ],
                role="model" # Assign model role to the overriding response
            )
    return Content(
            parts=[Part(text=f"Agent {callback_context.agent_name} continue the loop.")],
            role="model" # Assign model role to the overriding response
        )

class Result_of_prom_metrics_evaluation_agent(BaseModel):
    new_qualified_prom_candidates:list[str] = Field(
        description="The name list of prometheus metrics which can partially replace a given log analytics(la) table and given usage of the table."
    ),
    if_enough_candidates:bool = Field(
        description="If we have enough prometheus metrics candidates to replace a given log analytics(la) table."
    )

evaluate_qualified_prom_metrics_of_a_la_table_agent = LlmAgent(
    name="evaluate_qualified_prom_metrics_of_a_la_table_agent",
    model=LiteLlm(model="azure/gpt-4o-mini"),
    description=(
        """
        Agent to determin if a potential prometheus metric is a good candidate to partially replace a give log analytics(la) table.
        Update the potential prom metrics list of a Azure log analytics(la) kusto table.
        And determin if we need to continue the loop to investiget more prometheus mertics.
        Your response MUST be a raw json which can be deserialized directly, DO NOT use markdown marks like ```json, 

        response format example:
        {
            "new_qualified_prom_candidates": ["kube_pod_info", "kube_pod_container_info", "kube_pod_container_status_waiting", "kube_pod_container_status_terminated_reason"],
            "if_enough_candidates": true
        }
        """
    ),
    instruction=(
        """
        You are a professional agent who determin which prometheus metric is a good candidate can partially replace a given log analytics(la) table 
        and if there are enough prometheus metrics candidates after adding new candidates to provide almost same information as the la kusto table be used in a KQL.
        Then you MUST call "add_new_prom_metrics_candidate_and_ternimate_if_enough_candidates" tool ONLY ONCE to add all new prom metrics candidates and ternimate if enough candidates.
        
        **Target la kusto table name: **
        {{name_of_current_target_la_table_needs_investigate_alternatives}}

        **Target la kusto table usage:**
        {{usage_of_current_target_la_table_needs_investigate_alternatives}}

        **Target la kusto table example value:**
        {{example_value_of_current_target_la_table_needs_investigate_alternatives}}

        **Prom metrics need to be evaluated:**
        {{current_prometheus_metrics_need_get_value}}

        **All known prometheus metrics values**
        {{prom_metrics_value_for_current_target_la_kusto_table}}

        **Available prometheus metrics list:**
        {{all_available_prometheus_metrics_name_list}}
        """
    ),
    include_contents='none',
    output_key="good_prom_candidates_and_if_enough_candidates",
    output_schema=Result_of_prom_metrics_evaluation_agent,
    after_agent_callback=add_new_prom_metrics_candidate_and_exit_if_enough_candidates
)

# 把 corresponding_prom_metric_of_la_table_finding_loop_agent 里的 corresponding_prom_metric_of_la_table_finding_agent
# 拆成一个loop agent，里面3个agent，分别是，
# 1. 分析还有需要哪些prom metric 可能有帮助，一个llm agent，输出一个prom metric name list：list[str]
# 2. 找到对应的prom metric 值，是一个llm agent, 获得那些value
# 3. 看有没有帮助，更新状态，并且决定是否继续，也是一个llm agent
corresponding_prom_metric_of_given_la_table_finding_loop_agent = MyLoopAgent(
    name="corresponding_prom_metric_of_given_la_table_finding_loop_agent",
    description=(
        "Agent to find one or multi prometheus metrics which can replace a given log analytics(la) Kusto table."
    ),
    sub_agents=[
        find_more_potential_related_prom_metric_agent,
        fetch_prometheus_metrics_value_agent,
        evaluate_qualified_prom_metrics_of_a_la_table_agent
    ],
    before_agent_callback=get_target_la_table_name_and_example_value_callback,
    max_iterations=5,
)

# 把 corresponding_prom_metric_of_la_table_finding_loop_agent 里的 corresponding_prom_metric_of_la_table_finding_agent
# 拆成一个loop agent，里面3个agent，分别是，
# 1. 分析还有需要哪些prom metric 可能有帮助，一个llm agent，输出一个prom metric name list：list[str]
# 2. 找到对应的prom metric 值，是一个llm agent, 获得那些value
# 3. 看有没有帮助，更新状态，并且决定是否继续，也是一个llm agent
corresponding_prom_metric_of_la_table_finding_loop_agent = MyLoopAgent(
    name="corresponding_prom_metric_of_la_table_finding_loop_agent",
    description=(
        "Loop agent to find corresponding prometheus metric for each la kusto table in state['name_of_all_la_kusto_table_needed_replacement']."
    ),
    sub_agents=[
        corresponding_prom_metric_of_given_la_table_finding_loop_agent,
        corresponding_prom_metric_finding_task_checker_agent
    ],
    # this means support to find no more than 10 la tables
    max_iterations=10
)

def get_kql_execution_topological_dag(callback_context:CallbackContext) -> Content:
    """Get kql execution blocks with topological sorted DAG."""
    try:
        # Execute the Kusto query and return the results
        kusto_query = callback_context.state["kusto_query"]["kusto_query_extracted"]
        execution_dag = parse_kql_query(kusto_query)
        callback_context.state["kql_execution_dag"] = execution_dag
 
        return Content(
                parts=[Part(text=f"Agent {callback_context.agent_name} executed successfully.")],
                role="model" # Assign model role to the overriding response
            )
    except Exception as e:
        return Content(
                parts=[Part(text=f"Agent {callback_context.agent_name} executed failed.")],
                role="model" # Assign model role to the overriding response
            )

kql_analyzer_agent = BaseAgent(
    name="kql_dag_analyzer_agent",
    description=(
        "Agent to analyze the KQL execution DAG."
    ),
    before_agent_callback=get_kql_execution_topological_dag
)


"""
find_corresponding_prom_metric_of_la_table = AgentTool(
    agent=corresponding_prom_metric_of_la_table_finding_agent,
    skip_summarization=True,
)
"""
# 创建另一个专门发现LA table 到 Prom metrics mapping的agent，直接试试效果，不行的话创建下一个agent
# 再创建一个把每个Kusto的let部分挨个翻译成Prom的agent
# 创建整个翻译的agent
la_alert_translator_agent = LlmAgent(
    name="la_alert_translator_agent",
    model=LiteLlm(model="azure/gpt-4.1"),
    description=(
        "Agent to translate Azure Monitor alert defined by kusto query to Grafana prometheus alert defined by PrometheusQL."
    ),
    instruction=(
        f"""
        You are a helpful agent who translate Azure Monitor alert defined by kusto to Grafana prometheus alert defined by PrometheusQL.
        The key is your PromQL must return the same value for each series as column "AggregatedValue" for each group in Kusto query.
        You don't need to translate the all columns in the kusto query result, but you need to translate the core alert logic to prometheusQL.
        If the la table is empty, you can just ignore related logic of that table.

        You must follow a mapping which contains prometheus metrics candidate of a given Azure log analytics(la) table to translate user's KQL to prometheusQL.
        {{prometheus_metrics_candidate_of_a_la_table}}
        """
    ),
    global_instruction=(
        """
        la_alert_translator_agent will call corresponding_prom_metric_of_la_table_finding_agent to help find corresponding prom metric of a given la table
        then, corresponding_prom_metric_of_la_table_finding_agent must return and transfer to parent agent.
        """
    ),
)

def kusto_execution_dag_data_preparation_callback(callback_context:CallbackContext) -> Optional[Content]:
    """Prepare data for kusto_execution_dag_prometheusQL_translation_agent."""
    state = callback_context.state
    kql_execution_dag = state["kql_execution_dag"]
    if len(kql_execution_dag) > 0:
        # Update state["content_of_target_kusto_dag_node"]
        if "content_of_target_kusto_dag_node" not in state:
            state["content_of_target_kusto_dag_node"] = kql_execution_dag[0]
        else:
            if "DAGIndex" not in state["content_of_target_kusto_dag_node"]:
                raise ValueError(f"DAGIndex not found in state['content_of_target_kusto_dag_node']: {state['content_of_target_kusto_dag_node']}")
            state["content_of_target_kusto_dag_node"] = kql_execution_dag[state["content_of_target_kusto_dag_node"]["DAGIndex"] + 1]

        # Update state["content_of_referenced_kusto_dag_node"]
        if "content_of_referenced_kusto_dag_node" not in state:
            state["content_of_referenced_kusto_dag_node"] = []
        if len(state["content_of_target_kusto_dag_node"]["ReferencedKqlBlockDAGNodeIndexes"]) > 0:
            state["content_of_referenced_kusto_dag_node"] = [kql_execution_dag[dag_index] for dag_index in state["content_of_target_kusto_dag_node"]["ReferencedKqlBlockDAGNodeIndexes"]]
        else:
            state["content_of_referenced_kusto_dag_node"] = []

        # Update state["PromQL_of_referenced_kusto_dag_node"]
        if "PromQL_of_kusto_dag_node" in state:
            referencedKqlBlockDAGNodeIndexes = state["content_of_target_kusto_dag_node"]["ReferencedKqlBlockDAGNodeIndexes"]
            state["PromQL_of_referenced_kusto_dag_node"] = [ { 'referenced_kql_block_dag_node_index': dag_index, 'referenced_kql_block_dag_node_translated_text': state["PromQL_of_kusto_dag_node"][dag_index]} for dag_index in referencedKqlBlockDAGNodeIndexes]
        else:
            state["PromQL_of_kusto_dag_node"] = []
            state["PromQL_of_referenced_kusto_dag_node"] = []

        return None
    
    else:
        return Content(
                parts=[Part(text=f"Agent {callback_context.agent_name} executed failed, there is no kql_execution_dag to be processed.")],
                role="model" # Assign model role to the overriding response
            )

def show_convertion_result_callback(callback_context:CallbackContext) -> Content:
    """Show the conversion result."""
    state = callback_context.state
    if "PromQL_of_current_kusto_dag_node" in state and "content_of_target_kusto_dag_node" in state:
        return Content(
                parts=[Part(text=f"""
*KQL:*
{state["content_of_target_kusto_dag_node"]["Text"]}

*PromQL:*
{state["PromQL_of_current_kusto_dag_node"]}
                    """)],
                role="model" # Assign model role to the overriding response
            )
    else:
        return Content(
                parts=[Part(text=f"Agent {callback_context.agent_name} executed failed.")],
                role="model" # Assign model role to the overriding response
            )

kusto_execution_dag_prometheusQL_translation_agent = LlmAgent(
    name="kusto_execution_dag_prometheusQL_translation_agent",
    model=LiteLlm(model="azure/gpt-4.1"),
    description=(
        "LLM agent to translate kusto execution dag node to PromQL."
    ),
    include_contents='none',
    instruction=(
        f"""
        You are a professional agent who translate a kusto execution dag node into PromQL text.
        A kusto execution dag node typically contains a kusto query text and referenced kusto execution dag node.
        I will give you target kusto execution dag node, all referenced kusto execution dag node and corresponding PromQL text of each referenced kusto execution dag node.

        The ONLY response you need to give is the translated PromQL text of target kusto execution dag node, do not show the analysis in response and NEVER return your response with markdown marks like ```.
        To achieve this, you need to find what does target kusto execution dag node do to all referenced kusto execution dag node,
        and then generate PromQL text of target kusto execution dag node based on PromQL text of referenced nodes.
        
        For Kusto table names referenced in the query text of target kusto execution dag node, 
        we already have corresponding alternative Prometheus metrics, you can use a suitable one.
        
        **Target kusto execution dag node: **
        {{content_of_target_kusto_dag_node}}

        **All referenced kusto execution dag node: **
        {{content_of_referenced_kusto_dag_node}}

        **Corresponding PromQL of referenced kusto execution dag node: **
        {{PromQL_of_referenced_kusto_dag_node}}

        **Mapping between Kusto table and its potential alternative Prometheus metrics: **
        {{prometheus_metrics_candidate_of_a_la_table}}

        **Lable name and example value of prometheus metrics candidates: **
        {{prometheus_metrics_lable_name_and_example_value}}
        """
    ),
    before_agent_callback=kusto_execution_dag_data_preparation_callback,
    #after_model_callback=save_model_output_into_state,
    output_key="PromQL_of_current_kusto_dag_node",
    generate_content_config=llm_config
)

prometheusQL_validation_prepare_agent = LlmAgent(
    name="prometheusQL_validation_prepare_agent",
    model=LiteLlm(model="azure/gpt-4o-mini"),
    description=(
        "Agent to prepare the PromQL for validation."
    ),
    instruction=(
        f"""
        You are a professional agent who refine the PromQL to adapt hard enviroment for validation.
        You have a prometheus query text to be validated, however, the query text can not be executed directly in Grafana since the prometheus data source contains too much time series and cann't execute query if we do not specific a value on a common lable "cluster".
        So your job is to update a given prometheus query text to add a filter on the common lable "cluster" of all prometheus metrics shown in the query and return the updated prometheus query text.
        Your response MUST be a prometheus query text which can be executed directly in Grafana or a empty string. Never return your response with markdown marks like ```.
        
        For example, if the original prometheus query text is:
        "sum(rate(container_cpu_usage_seconds_total{{container_name=~"abc"}}[5m])) by (cluster, container_name)"
        You need to update the query into something like this:
        "sum(rate(container_cpu_usage_seconds_total{{cluster=~"cluster1", container_name=~"abc"}}[5m])) by (cluster, container_name)"

        For exmaple, if the original prometheus query text is:
        "120m"
        This is only a part of query, it is not expected to be executed, so you need to return nothing.

        **Prometheus query text to be validated:**
        {{PromQL_of_current_kusto_dag_node}}

        **Cluster filter value:**
        {{prometheusQL_cluster_filter}}
        
        **All prometheus names:**
        {{prometheus_metrics_candidate_of_a_la_table}}
        """
    ),
    include_contents='none',
    output_key="current_prometheusQL_for_validation",
)

prometheus_query_validation_agent = BaseAgent(
    name="prometheus_query_validation_agent",
    description=(
        "Agent to validate a prometheus query by executing query in grafana."
    ),
    before_agent_callback=validate_prometheus_query
)

prometheusQL_translation_refine_agent = LlmAgent(
    name="prometheusQL_translation_refine_agent",
    model=LiteLlm(model="azure/gpt-4o"),
    description=(
        "LLM agent to refine the prometheus query translated from a kusto execution dag node."
    ),
    include_contents='none',
    instruction=(
        f"""
        You are a professional agent who refine the prometheus query translated from a kusto execution dag node.
        A kusto execution dag node typically contains a kusto query text and referenced kusto execution dag node.
        I will give you target kusto execution dag node, all referenced kusto execution dag node and corresponding PromQL text of each referenced kusto execution dag node.

        The ONLY response you need to give is the translated PromQL text of target kusto execution dag node, do not show the analysis in response.
        To achieve this, you need to find what does target kusto execution dag node do to all referenced kusto execution dag node.
        Think about why last prometheus query parsed failed and how to fix it,
        then generate PromQL text of target kusto execution dag node based on PromQL text of referenced nodes.
        
        For Kusto table names referenced in the query text of target kusto execution dag node, 
        we already have corresponding alternative Prometheus metrics, you can use a suitable one.
        
        **Last failed prometheus query needs to refine:**
        {{PromQL_of_current_kusto_dag_node}}

        **Target kusto execution dag node: **
        {{content_of_target_kusto_dag_node}}

        **All referenced kusto execution dag node: **
        {{content_of_referenced_kusto_dag_node}}

        **Corresponding PromQL of referenced kusto execution dag node: **
        {{PromQL_of_referenced_kusto_dag_node}}

        **Mapping between Kusto table and its potential alternative Prometheus metrics: **
        {{prometheus_metrics_candidate_of_a_la_table}}

        **Lable name and example value of prometheus metrics candidates: **
        {{prometheus_metrics_lable_name_and_example_value}}
        """
    ),
    #before_agent_callback=kusto_execution_dag_data_preparation_callback,
    #after_model_callback=save_model_output_into_state,
    output_key="PromQL_of_current_kusto_dag_node",
    generate_content_config=llm_config
)

prom_query_validation_and_refine_loop_agent = MyLoopAgent(
    name="prom_query_validation_and_refine_loop_agent",
    description=(
        "Loop agent to validate and refine the prometheus query translated from a kusto execution dag node."
    ),
    sub_agents=[
        prometheusQL_validation_prepare_agent,
        prometheus_query_validation_agent,
        prometheusQL_translation_refine_agent,
    ],
    max_iterations=5
)

def print_refine_context(callback_context:CallbackContext) -> Content:
    """Print the context of refine."""
    state = callback_context.state

    return Content(
            parts=[
                Part(
                    text=f"""
AI generated Prometheus query execution {"successed" if state.get("validation_passed", False) else "failed"}. Please help confirm or input correct PromQL:


- If the PromQL is correct, please type in "#HITL Confirmed".

- If the PromQL is not correct, please type in "#HITL <Your converted PromQL text which can be executed directly in Grafana>". 


**Target kusto execution dag node:**
```json
{json.dumps(state["content_of_target_kusto_dag_node"], indent=4)}
```


**All referenced kusto execution dag node:**
```json
{json.dumps(state["content_of_referenced_kusto_dag_node"], indent=4)}
```


**Corresponding PromQL of referenced kusto execution dag node:**
```json
{json.dumps(state["PromQL_of_referenced_kusto_dag_node"], indent=4)}
```


**Last tried prometheus query:**
```json
{state["PromQL_of_current_kusto_dag_node"]}
```


**Mapping between Kusto table and its potential alternative Prometheus metrics:**
```json
{json.dumps(state["prometheus_metrics_candidate_of_a_la_table"], indent=4)}
```
"""
                )
            ],
            role="model" # Assign model role to the overriding response
        )

refine_context_print_agent = BaseAgent(
    name="refine_context_print_agent",
    description=(
        "Agent to print the context to help human convert kql to PromQL."
    ),
    before_agent_callback=print_refine_context
)

def save_human_refine_result_into_state(callback_context:CallbackContext) -> Content:
    """Save the human refine result into state."""
    state = callback_context.state
    ctx = callback_context._invocation_context
    user_state_key = "hitl"
    human_refine_result = ctx.session_service.user_state[ctx.session.app_name][ctx.session.user_id][user_state_key]
    # This means if human does not think the PromQL is correct, 
    # we need to update the state["PromQL_of_current_kusto_dag_node"] with the human's response.
    # If the human response is "#HITL Confirmed", we do not need to update the state.
    if human_refine_result != "Confirmed":
        state["PromQL_of_current_kusto_dag_node"] = human_refine_result

    return Content(
            parts=[Part(text=f"Got human refine result: {human_refine_result}.")],
            role="model" # Assign model role to the overriding response
        )

human_refine_agent = MyHILAgent(
    name="human_refine_agent",
    description=(
        "Agent to get PromQL from human's response and store into state."
    ),
    after_agent_callback=save_human_refine_result_into_state,
)

def check_if_need_human_refine(callback_context:CallbackContext) -> Content:
    state = callback_context.state
    # if the validation passed, it don't need human help, we need to return directly
    if len(state.get("current_prometheusQL_for_validation", "")) == 0:
        return Content(
                parts=[Part(text=f"PromQL of current kql node doesn't need validation and no need to get help from human.")],
                role="model" # Assign model role to the overriding response
            )
    else:
        return None

human_prometheusQL_validation_prepare_agent = LlmAgent(
    name="human_prometheusQL_validation_prepare_agent",
    model=LiteLlm(model="azure/gpt-4o-mini"),
    description=(
        "Agent to prepare the PromQL for validation."
    ),
    instruction=(
        f"""
        You are a professional agent who refine the PromQL to adapt hard enviroment for validation.
        You have a prometheus query text to be validated, however, the query text can not be executed directly in Grafana since the prometheus data source contains too much time series and cann't execute query if we do not specific a value on a common lable "cluster".
        So your job is to update a given prometheus query text to add a filter on the common lable "cluster" of all prometheus metrics shown in the query and return the updated prometheus query text.
        Your response MUST be a prometheus query text which can be executed directly in Grafana or a empty string. Never return your response with markdown marks like ```.
        
        For example, if the original prometheus query text is:
        "sum(rate(container_cpu_usage_seconds_total{{container_name=~"abc"}}[5m])) by (cluster, container_name)"
        You need to update the query into something like this:
        "sum(rate(container_cpu_usage_seconds_total{{cluster=~"cluster1", container_name=~"abc"}}[5m])) by (cluster, container_name)"

        For exmaple, if the original prometheus query text is:
        "120m"
        This is only a part of query, it is not expected to be executed, so you need to return nothing.

        **Prometheus query text to be validated:**
        {{PromQL_of_current_kusto_dag_node}}

        **Cluster filter value:**
        {{prometheusQL_cluster_filter}}
        
        **All prometheus names:**
        {{prometheus_metrics_candidate_of_a_la_table}}
        """
    ),
    include_contents='none',
    output_key="current_prometheusQL_for_validation",
)

human_prometheus_query_validation_agent = BaseAgent(
    name="human_prometheus_query_validation_agent",
    description=(
        "Agent to validate a prometheus query by executing query in grafana."
    ),
    before_agent_callback=validate_human_prometheus_query
)

human_refine_loop_agent = MyLoopAgent(
    name="human_refine_loop_agent",
    description=(
        "Agent to ask human to refine the prometheus query translated from a kusto execution dag node."
    ),
    sub_agents=[
        refine_context_print_agent,
        human_refine_agent,
        human_prometheusQL_validation_prepare_agent,
        human_prometheus_query_validation_agent,
    ],
    before_agent_callback=check_if_need_human_refine,
)

def check_if_need_exit_loop_promql_trans(callback_context:CallbackContext)-> Content:
    """Call this function ONLY when the critique indicates no further changes are needed, signaling the iterative process should end."""
    agent_name = callback_context.agent_name
    state = callback_context.state
    current_dag_index = state["content_of_target_kusto_dag_node"]["DAGIndex"]
    
    if (current_dag_index + 1) == len(state["kql_execution_dag"]):
        callback_context._event_actions.escalate = True
        return Content(
                parts=[Part(text=f"Agent {agent_name} exit the loop. Completed iteration: {current_dag_index + 1}")],
                role="model" # Assign model role to the overriding response
            )
    else:
        # return None to continue
        return Content(
                parts=[Part(text=f"Agent {agent_name} continue the loop. Completed iteration: {current_dag_index + 1}")],
                role="model" # Assign model role to the overriding response
            )

promql_translation_loop_checker_agent = BaseAgent(
    name="prometheusQL_translation_loop_checker_agent",
    description=(
        "Agent to check if the task of PromQL translation is done and update states."
    ),
    before_agent_callback=check_if_need_exit_loop_promql_trans
)

def set_promql_cluster_filter(callback_context:CallbackContext) -> Content:
    """Set the cluster filter for the PromQL to state."""
    state = callback_context.state
    state_name = "prometheusQL_cluster_filter"
    if state_name not in state:
        cluster_name = get_cluster_name()
        state[state_name] = cluster_name
        return None
    else:
        return Content(
                parts=[Part(text=f"Agent {callback_context.agent_name} executed failed, can not get prom cluster name filter.")],
                role="model" # Assign model role to the overriding response
            )

kusto_execution_dag_promql_translation_loop_agent = LoopAgent(
    name="kusto_execution_dag_prometheusQL_translation_loop_agent",
    description=(
        "Loop agent to translate kusto execution dag to PromQL."
    ),
    sub_agents=[
        kusto_execution_dag_prometheusQL_translation_agent,
        prom_query_validation_and_refine_loop_agent,
        human_refine_loop_agent,
        promql_translation_loop_checker_agent
    ],
    max_iterations=200,
    before_agent_callback=set_promql_cluster_filter
)

class KustoQueryExtracted(BaseModel):
    kusto_query_extracted: str = Field(
        description="kusto query extracted from user message."
    )

kusto_query_extract_agent = LlmAgent(
    name="kusto_query_extract_agent",
    model=LiteLlm(model="azure/gpt-4.1"),
    description=(
        "Agent to extract kusto query user inputs."
    ),
    instruction=(
        """
        You are a helpful agent who extract pure kusto query text from user message.
        Your response must be pure kusto query text wrapped with json format, 
        it means a valid kusto query which can be executed directly in Azure Monitor.
        Your response MUST be a raw json which can be deserialized directly, Do not use markdown marks like ```json, 

        response format example:
        {
            "kusto_query_extracted": "let mitigationStep = ```Mitigation steps not added.```;InsightsMetrics| where Namespace =~ 'prometheus' and Name == 'DRU_health_check_gauge'| extend tags=parse_json(Tags)| extend ClusterName = tostring(tags.['ClusterName'])"
        }
        """
    ),
    output_key="kusto_query",
    output_schema=KustoQueryExtracted,
)

root_agent = SequentialAgent(
    name="root_agent",
    description=(
        "Agent to check all available prometheus metrics name list first and then translate."
    ),
    sub_agents=[
        kusto_query_extract_agent,
        load_all_available_prometheus_metrics_name_agent,
        get_all_referenced_la_tables_agent,
        corresponding_prom_metric_of_la_table_finding_loop_agent,
        kql_analyzer_agent,
        kusto_execution_dag_promql_translation_loop_agent
    ],
)

# 把 corresponding_prom_metric_of_la_table_finding_loop_agent 里的 corresponding_prom_metric_of_la_table_finding_agent
# 拆成一个loop agent，里面3个agent，分别是，
# 1. 分析还有需要哪些prom metric 可能有帮助，
# 2. 找到对应的prom metric 值
# 3. 看有没有帮助，更新状态，并且决定是否继续