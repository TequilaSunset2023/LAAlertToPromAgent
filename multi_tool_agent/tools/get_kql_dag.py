import subprocess
import json

def parse_kql_query(query_string):
    # Call the KustoLanguage.exe with the query as argument
    result = subprocess.run([r'packages\KustoLanguageAnalyzor\KustoLanguage.exe', query_string], 
                           capture_output=True, text=True)
    output = result.stdout
    # Parse the JSON output
    return json.loads(output)


if __name__ == "__main__":
    query = """
KubeEvents
| where Reason contains 'FailedCreatePodSandBox' and Message contains 'Failed to allocate pool: Failed to delegate: Failed to allocate address: No available addresses'
| extend cluster = split(ClusterName, '-')
| extend ['ring/silo/location'] = strcat(cluster[1], '/', cluster[2], '/', cluster[5])
| summarize AggregatedValue = count() by bin(TimeGenerated, trendBinSize), RoutingId = 'exchange-cosmic', ['ring/silo/location'], TSG = 'https://aka.ms/cosmic/tsg/failed-to-create-pod-sandbox-due-to-cni-issue', Title=['ring/silo/location'], Category=Reason, Computer=strcat(ClusterName,'/',Computer), PodName=Name, Reason, ClusterName, Message = 'Failed to allocate pool: Failed to delegate: Failed to allocate address: No available addresses'
| join (KubeNodeInventory
| extend isNodeCordonedByZH = iff(tostring(parse_json(Labels)[0]['CordonedByZH']) != '', true, false)
| where isNodeCordonedByZH == false
| summarize arg_max(TimeGenerated, *) by ClusterName, Computer=strcat(ClusterName,'/',Computer))
on ClusterName, Computer
| where Status == 'Ready'
| project-away ClusterName1, Computer1, TimeGenerated1, isNodeCordonedByZH
"""
    parsed_dag = parse_kql_query(query)
    print(parsed_dag)
