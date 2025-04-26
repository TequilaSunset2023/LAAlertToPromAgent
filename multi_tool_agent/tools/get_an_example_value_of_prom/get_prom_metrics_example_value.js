// Add the new function to be called from Python
function fetchExampleForMetric(cookie, metricName, cluster_name) {
    const datasources = {
        '2LZ5icZVk': 'CosmicMdmProdNam',
        'ddns8c8j1iz9cb': 'CosmicMdmProdNam-WinProcess',
    };

    let requests = [];
    const timestampOnQuery = Date.now() - 86400000; // 24 hours ago

    // Build request objects for all datasources with the specified metric
    for (const uid of Object.keys(datasources)) {
        requests.push({
            url: `https://cosmicmonitoring-b6a0cza8a4ghfnda.scus.grafana.azure.com/api/ds/query?ds_type=prometheus&requestId=explore_jq2`,
            uid,
            metric,
            dataSource: datasources[uid],
            body: {
                "queries": [{
                    "refId": "A",
                    "expr": `topk(1, ${metricName}{cluster=\"${cluster_name}\"})`,
                    "range": false,
                    "instant": true,
                    "datasource": {
                        "type": "prometheus",
                        "uid": uid
                    },
                    "editorMode": "code",
                    "legendFormat": "__auto",
                    "key": "Q-660a4e71-2dc1-4937-8de8-299e0c2b8472-0",
                    "format": "table",
                    "exemplar": false,
                    "requestId": "25562A",
                    "utcOffsetSec": 28800,
                    "interval": "",
                    "datasourceId": 151,
                    "intervalMs": 60000,
                    "maxDataPoints": 717
                }],
                "from": `${timestampOnQuery}`,
                "to": `${timestampOnQuery}`
            }
        });
    };

    const headers = {  
        'Cookie': cookie,
        'Content-Type': 'application/json'
    };

    // This is a synchronous version to work with execjs
    function fetchSynchronously(request) {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', request.url, false);  // false makes the request synchronous
        
        for (const [key, value] of Object.entries(headers)) {
            xhr.setRequestHeader(key, value);
        }
        
        try {
            xhr.send(JSON.stringify(request.body));
            if (xhr.status === 200) {
                return JSON.parse(xhr.responseText);
            }
        } catch (error) {
            console.error(`Error fetching ${request.url}: ${error}`);
        }
        return null;
    }

    // Try each request until we get a successful response
    for (const requestObj of requests) {
        try {
            const response = fetchSynchronously(requestObj);
            if (response && response.results && response.results.A 
                    && response.results.A.frames && response.results.A.frames.length > 0
                    && response.results.A.frames[0].schema && response.results.A.frames[0].schema.fields
                    && response.results.A.frames[0].schema.fields.length > 1) {
                return {
                    'status': "success",
                    'labels': response.results.A.frames[0].schema.fields[1].labels,
                }
            }
        } catch (error) {
            console.error(`Error processing request: \n${requestObj} \n ${error}`);
            continue;
        }
    }

    return {
        'status': "error",
        'error_message': "No data found for the specified metric",
    }
}

