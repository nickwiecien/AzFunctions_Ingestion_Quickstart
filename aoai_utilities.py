import datetime
from pathlib import Path
import time
import json
import openai
import os


def generate_embeddings(text):
    """
    Generates embeddings for the given text using the specified embeddings model provided by OpenAI.

    Args:
        text (str): The text to generate embeddings for.
        embeddings_model (str): The name of the embeddings model to use.
        aoai_endpoint (str): The endpoint of the OpenAI Azure service.
        aoai_key (str): The key of the OpenAI Azure service.

    Returns:
        embeddings (list): The embeddings generated for the given text.
    """

    # Configure OpenAI with Azure settings
    openai.api_type = "azure"
    openai.api_base = os.environ['AOAI_ENDPOINT']
    openai.api_version = "2023-03-15-preview"
    openai.api_key = os.environ['AOAI_KEY']

    # Initialize variable to track if the embeddings have been processed
    processed = False
    # Attempt to generate embeddings, retrying on failure
    while not processed:
        try:
            # Make API call to OpenAI to generate embeddings
            response = openai.Embedding.create(input=text, engine=os.environ['AOAI_EMBEDDINGS_MODEL'])
            processed = True
        except Exception as e:  # Catch any exceptions and retry after a delay
            print(e)
            time.sleep(5)

    # Extract embeddings from the response6
    embeddings = response['data'][0]['embedding']
    return embeddings
