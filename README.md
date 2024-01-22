# Azure Functions Ingestion - Generative AI Quickstart

## Project Overview

The 'Azure Functions Ingestion - Generative AI Quickstart' is an Azure Durable Functions project aimed at streamlining the process of ingesting, chunking, and vectorizing various data types such as PDFs, MP3s, WAV files, and more. These processes are critical for indexing and utilizing data in Retrieval Augmented Generation (RAG) patterns within Generative AI applications.

By leveraging Azure Durable Functions, the project orchestrates the complex workflows involved in data processing, ensuring efficiency and scalability. It includes capabilities for creating and managing Azure AI Search indexes, updating index aliases for deployment strategies, and indexing large volumes of pre-processed documents in bulk.

## Features
- **Ingestion and Chunking**: Automated breakdown of documents and audio files into chunks for easier processing.
- **Vectorization**: Transformation of textual and auditory information into vector embeddings suitable for AI models.
- **Index Management**: Tools for creating and updating Azure AI Search indexes to optimize data retrieval.
- **Workflow Orchestration**: Utilization of Durable Functions to coordinate and manage data processing tasks.

## Getting Started

### Prerequisites
- An active Azure subscription.
- A configured Azure Storage Account.
- Access to Azure Cognitive Services, including Document Intelligence and Azure OpenAI.
- An Azure AI Search Service instance.

### Installation
1. Clone the repository to your desired environment.
2. Install Azure Functions Core Tools if not already available.
3. In the project directory, install dependencies with `pip install -r requirements.txt`.

### Configuration
Configure the environment variables in your Azure Function App settings as follows:

| Variable Name                | Description                                               |\n|------------------------------|-----------------------------------------------------------|\n| `STORAGE_CONN_STR`           | Azure Storage account connection string                   |\n| `DOC_INTEL_ENDPOINT`         | Endpoint for Azure Document Intelligence service          |\n| `DOC_INTEL_KEY`              | Key for Azure Document Intelligence service               |\n| `AOAI_KEY`                   | Key for Azure OpenAI service                              |\n| `AOAI_ENDPOINT`              | Endpoint for Azure OpenAI service                         |\n| `AOAI_EMBEDDINGS_MODEL`      | Model for generating embeddings with Azure OpenAI         |\n| `AOAI_WHISPER_KEY`           | Key for Azure OpenAI Whisper model                        |\n| `AOAI_WHISPER_ENDPOINT`      | Endpoint for Azure OpenAI Whisper model                   |\n| `AOAI_WHISPER_MODEL`         | Model for transcribing audio with Azure OpenAI            |\n| `SEARCH_ENDPOINT`            | Endpoint for Azure AI Search service                      |\n| `SEARCH_KEY`                 | Key for Azure AI Search service                           |\n| `SEARCH_SERVICE_NAME`        | Name of the Azure AI Search service instance              |



### Orchestrators\nThe project contains orchestrators tailored for specific data types:
- `pdf_orchestrator`: Orchestrates the processing of PDF files, including splitting, analyzing, and generating embeddings.
- `mp3_orchestrator`: Orchestrates the transcription and vectorization of MP3 audio files.
- `wav_orchestrator`: Orchestrates the transcription and vectorization of WAV audio files.
- `index_documents_orchestrator`: Orchestrates the indexing of processed documents into Azure AI Search.

### Activities\nThe orchestrators utilize the following activities to perform discrete tasks:
- `get_source_files`: Retrieves a list of files from a specified Azure Storage container.
- `split_pdf_files`: Splits PDF files into individual pages and stores them as separate files.
- `process_pdf_with_document_intelligence`: Processes PDF chunks using Azure Document Intelligence and extracts relevant data.
- `transcribe_audio_files`: Transcribes audio files using Azure OpenAI's Whisper model and stores the results.
- `generate_extract_embeddings`: Generates vector embeddings for the processed text data
- `insert_record`: Inserts processed data records into the Azure AI Search index.

### Standalone Functions\nIn addition to orchestrators and activities, the project includes standalone functions for index management:
- `create_new_index`: Creates a new Azure AI Search index with the specified fields.
- `update_index_alias`: Updates an index alias to point to the latest version of an index, facilitating blue-green deployments and other staged rollout strategies.

## Contributing
We welcome contributions to this project. To contribute, please follow the standard fork-branch-pull request workflow.

---

Remember to replace placeholders with actual values that are relevant to your project setup.