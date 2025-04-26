from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from azure.kusto.data.exceptions import KustoServiceError
from typing import List, Optional

def execute_kusto_query(
    cluster_url: str,
    database_name: str,
    query: str,
) -> List[str]:
    """
    Execute a Kusto query in a specified database and return the results as a list of strings.
    
    Args:
        cluster_url (str): The URL of the Kusto cluster (e.g., "https://myinstance.kusto.windows.net")
        database_name (str): The name of the database to query
        query (str): The Kusto query to execute
    
    Returns:
        List[str]: A list of result strings from the Kusto query
    
    Raises:
        KustoServiceError: If there's an error executing the query
        ValueError: If invalid connection parameters are provided
    """
    try:
        # Set up the connection to Kusto using default user authentication
        kcsb = KustoConnectionStringBuilder.with_az_cli_authentication(cluster_url)
        
        # Create the client
        client = KustoClient(kcsb)
        
        # Execute the query
        response = client.execute(database_name, query)
        
        # Process the results
        result_list = []
        primary_results = response.primary_results[0]
        
        # Extract data rows as strings
        for row in primary_results:
            if len(row) == 1:
                result_list.append(str(row[0]))
            else:
                result_list.append(str(row))
        
        return result_list
    
    except KustoServiceError as e:
        raise KustoServiceError(f"Error executing Kusto query: {str(e)}")
    except Exception as e:
        raise ValueError(f"Failed to connect to Kusto or execute query: {str(e)}")