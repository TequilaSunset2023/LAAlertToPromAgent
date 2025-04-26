from dotenv import load_dotenv

load_dotenv()

import datetime
import os
from zoneinfo import ZoneInfo
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from .tools.get_an_example_value_of_prom.get_an_example_value_of_prom_func import get_all_prometheus_metrics_name_list, get_lable_name_and_example_value_of_prometheus_metric


def get_weather(city: str) -> dict:
    """Retrieves the current weather report for a specified city.

    Args:
        city (str): The name of the city for which to retrieve the weather report.

    Returns:
        dict: status and result or error msg.
    """
    if city.lower() == "new york":
        return {
            "status": "success",
            "report": (
                "The weather in New York is sunny with a temperature of 25 degrees"
                " Celsius (77 degrees Fahrenheit)."
            ),
        }
    else:
        return {
            "status": "error",
            "error_message": f"Weather information for '{city}' is not available.",
        }


def get_current_time(city: str) -> dict:
    """Returns the current time in a specified city.

    Args:
        city (str): The name of the city for which to retrieve the current time.

    Returns:
        dict: status and result or error msg.
    """

    if city.lower() == "new york":
        tz_identifier = "America/New_York"
    else:
        return {
            "status": "error",
            "error_message": (
                f"Sorry, I don't have timezone information for {city}."
            ),
        }

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    report = (
        f'The current time in {city} is {now.strftime("%Y-%m-%d %H:%M:%S %Z%z")}'
    )
    return {"status": "success", "report": report}

# 创建另一个专门发现LA table 到 Prom metrics mapping的agent，直接试试效果，不行的话创建下一个agent
# 再创建一个把每个Kusto的let部分挨个翻译成Prom的agent
# 创建整个翻译的agent
root_agent = LlmAgent(
    name="la_alert_translator_agent",
    model=LiteLlm(model="azure/gpt-4o"),
    description=(
        "Agent to translate Azure Monitor alert defined by kusto to Grafana prometheus alert defined by PrometheusQL."
    ),
    instruction=(
        """
        You are a helpful agent who translate Azure Monitor alert defined by kusto to Grafana prometheus alert defined by PrometheusQL."
        You don't need to translate the all columns in the kusto query result, but you need to translate the core alert logic to prometheusQL.
        """
    ),
    tools=[get_all_prometheus_metrics_name_list, get_lable_name_and_example_value_of_prometheus_metric],
)