from dotenv import load_dotenv

load_dotenv()

import datetime
import os
from zoneinfo import ZoneInfo
from google.adk.tools.agent_tool import AgentTool
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.planners.built_in_planner import BuiltInPlanner
from pydantic import BaseModel, Field
from .tools.get_an_example_value_of_prom.get_an_example_value_of_prom_func import get_all_prometheus_metrics_name_list, get_lable_name_and_example_value_of_prometheus_metric
from .tools.get_log_analytics_table_example_value import get_log_analytics_table_example_value

class Corresponding_prom_metric_of_la_table_finding_agent_input(BaseModel):
    log_analytics_table_name: str = Field(
        description="The name of the log analytics table to query."
    )


corresponding_prom_metric_of_la_table_finding_agent = LlmAgent(
    name="corresponding_prom_metric_of_la_table_finding_agent",
    model=LiteLlm(model="azure/gpt-4o"),
    description=(
        "Agent to find one or multi prometheus metrics which can replace a log analytics(la) Kusto table."
    ),
    instruction=(
        """
        You are a helpful agent who find one or multi prometheus metrics which can replace a log analytics(la) Kusto table."
        Sometimes, there is corresponding prometheus metric of a log analytics Kusto table, you can return.
        If there is no exmaple value of the log analytics table, you can return "we can ignore this table since it is empty".
        """
    ),
    input_schema=Corresponding_prom_metric_of_la_table_finding_agent_input,
    tools=[get_log_analytics_table_example_value, get_all_prometheus_metrics_name_list, get_lable_name_and_example_value_of_prometheus_metric],
    disallow_transfer_to_parent=False,
)

find_corresponding_prom_metric_of_la_table = AgentTool(
    agent=corresponding_prom_metric_of_la_table_finding_agent,
    skip_summarization=True,
)

# 创建另一个专门发现LA table 到 Prom metrics mapping的agent，直接试试效果，不行的话创建下一个agent
# 再创建一个把每个Kusto的let部分挨个翻译成Prom的agent
# 创建整个翻译的agent
root_agent = LlmAgent(
    name="la_alert_translator_agent",
    model=LiteLlm(model="azure/gpt-4o"),
    description=(
        "Agent to translate Azure Monitor alert defined by kusto query to Grafana prometheus alert defined by PrometheusQL."
    ),
    instruction=(
        """
        You are a helpful agent who translate Azure Monitor alert defined by kusto to Grafana prometheus alert defined by PrometheusQL.
        The key is your PromQL must return the same value for each series as column "AggregatedValue" for each group in Kusto query.
        You don't need to translate the all columns in the kusto query result, but you need to translate the core alert logic to prometheusQL.
        If the la table is empty, you can just ignore related logic of that table.
        """
    ),
    global_instruction=(
        """
        la_alert_translator_agent will call corresponding_prom_metric_of_la_table_finding_agent to help find corresponding prom metric of a given la table
        then, corresponding_prom_metric_of_la_table_finding_agent must return and transfer to parent agent.
        """
    ),
    #sub_agents=[corresponding_prom_metric_of_la_table_finding_agent],
    tools=[find_corresponding_prom_metric_of_la_table, get_lable_name_and_example_value_of_prometheus_metric],
    disallow_transfer_to_parent=False,
)
