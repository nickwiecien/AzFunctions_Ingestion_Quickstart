from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents import SearchClient
from azure.search.documents.indexes.models import (
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchField,
    SearchField,  
    VectorSearch,  
    HnswAlgorithmConfiguration, 
    VectorSearchProfile
)
import os
from datetime import datetime
import requests
import json
# from azure.search.documents.indexes.models import HnswAlgorithmConfiguration

def get_current_index(index_stem_name):
    """
    Manages indexes by updating an alias to point to the newest index, and deleting the oldest index if necessary.

    Args:
    search_service_name (str): The name of the Azure Cognitive Search service.
    search_endpoint (str): The endpoint of the Azure Cognitive Search service.
    search_key (str): The admin key of the Azure Cognitive Search service.
    index_stem_name (str): The stem of the index name to filter out relevant indexes.
    """
    search_key = os.environ['SEARCH_KEY']
    search_endpoint = os.environ['SEARCH_ENDPOINT']
    search_service_name = os.environ['SEARCH_SERVICE_NAME']
    
    # Connect to Azure Cognitive Search resource using the provided key and endpoint
    credential = AzureKeyCredential(search_key)
    client = SearchIndexClient(endpoint=search_endpoint, credential=credential)
    
    # List all indexes in the search service
    indexes = client.list_index_names()
    
    # Find all indexes starting with the given stem name
    matching_indexes = [i for i in indexes if i.startswith(index_stem_name)]
    print(matching_indexes)

    # Parse the timestamp from each index name and store in a dictionary
    timestamp_to_index_dict = {}
    for index_name in matching_indexes:
        parts = index_name.split('-')
        timestamp = parts[-1]
        parsed_timestamp = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
        timestamp_to_index_dict[parsed_timestamp] = index_name

    # Sort timestamps from oldest to newest
    timestamps = sorted(timestamp_to_index_dict.keys())
    
    # Get the oldest and newest index based on timestamps
    # oldest_index = timestamp_to_index_dict[timestamps[0]]
    newest_index = timestamp_to_index_dict[timestamps[-1]]
    return newest_index
   

def insert_documents_vector(documents, index_name):
    """
    Inserts a document vector into the specified search index on Azure Cognitive Search.

    Args:
    endpoint (str): The endpoint of the search service.
    key (str): The API key for the search service.
    index_name (str): The name of the search index.
    document (dict): The document vector to insert.

    Returns:
    result (dict): The result of the document upload operation.
    """
    search_key = os.environ['SEARCH_KEY']
    search_endpoint = os.environ['SEARCH_ENDPOINT']
    search_service_name = os.environ['SEARCH_SERVICE_NAME']

    # Create a SearchClient object
    credential = AzureKeyCredential(search_key)
    client = SearchClient(endpoint=search_endpoint, index_name=index_name, credential=credential)

    # Upload the document to the search index
    result = client.upload_documents(documents=documents)

    return result

def create_vector_index(stem_name, user_fields):
    search_key = os.environ['SEARCH_KEY']
    search_endpoint = os.environ['SEARCH_ENDPOINT']
    search_service_name = os.environ['SEARCH_SERVICE_NAME']

    now =  datetime.now()
    timestamp  = datetime.strftime(now, "%Y%m%d%H%M%S")

    index_name  = f'{stem_name}-{timestamp}'

    # Create a SearchIndexClient object
    credential = AzureKeyCredential(search_key)
    client = SearchIndexClient(endpoint=search_endpoint, credential=credential)

    # Define the fields for the index
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True)]
    
    for field in user_fields:
        fields.append(SearchableField(name=field, type=SearchFieldDataType.String, searchable=True,  filterable=True))

    fields = fields + [ SearchField(name="embeddings", type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True, vector_search_dimensions=1536, vector_search_profile_name="vector-config")]
    

    # Define vector search configurations
    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="algorithm-config",
            )
        ],
        profiles=[VectorSearchProfile(name="vector-config", algorithm_configuration_name="algorithm-config")],
    )

    # Create the search index with the specified fields and vector search configuration
    index = SearchIndex(name=index_name, fields=fields, vector_search=vector_search)
    result = client.create_or_update_index(index)

    return result.name


def create_update_index_alias(alias_name, target_index):
    """
    Creates or updates an alias for a given Azure Cognitive Search index.

    Args:
    search_service_name (str): The name of the Azure Cognitive Search service.
    search_key (str): The admin key of the Azure Cognitive Search service.
    alias_name (str): The name of the alias to create or update.
    target_index (str): The name of the index that the alias should point to.
    """

    search_key = os.environ['SEARCH_KEY']
    search_endpoint = os.environ['SEARCH_ENDPOINT']
    search_service_name = os.environ['SEARCH_SERVICE_NAME']


    # Construct the URI for alias creation
    uri = f'https://{search_service_name}.search.windows.net/aliases?api-version=2023-07-01-Preview'
    headers = {'Content-Type': 'application/json', 'api-key': search_key}
    payload = {
        "name": alias_name,
        "indexes": [target_index]
    }
    print(target_index)
    
    try:
        # Attempt to create the alias
        response = requests.post(uri, headers=headers, data=json.dumps(payload))
        # If alias creation fails with a 400 error, update the existing alias
        if response.status_code == 400:
            uri = f'https://{search_service_name}.search.windows.net/aliases/{alias_name}?api-version=2023-07-01-Preview'
            response = requests.put(uri, headers=headers, data=json.dumps(payload))
    except Exception as e:
        print(e)
