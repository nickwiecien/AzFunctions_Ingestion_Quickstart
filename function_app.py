import azure.functions as func
import azure.durable_functions as df
import logging
import json
import os
import hashlib
from azure.storage.blob import BlobServiceClient
from PyPDF2 import PdfReader, PdfWriter
from io import BytesIO
import tempfile

from doc_intelligence_utilities import analyze_pdf, extract_results
from aoai_utilities import generate_embeddings, get_transcription
from ai_search_utilities import create_vector_index, get_current_index, create_update_index_alias, insert_documents_vector

app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)


# An HTTP-Triggered Function with a Durable Functions Client binding
@app.route(route="orchestrators/{functionName}")
@app.durable_client_input(client_name="client")
async def http_start(req: func.HttpRequest, client):
    function_name = req.route_params.get('functionName')
    payload = json.loads(req.get_body())

    instance_id = await client.start_new(function_name, client_input=payload)
    response = client.create_check_status_response(req, instance_id)
    return response

# Orchestrators
@app.orchestration_trigger(context_name="context")
def pdf_orchestrator(context):
    
    # Get the input payload from the context
    payload = context.get_input()
    
    # Extract the container names from the payload
    source_container = payload.get("source_container")
    chunks_container = payload.get("chunks_container")
    doc_intel_results_container = payload.get("doc_intel_results_container")
    extract_container = payload.get("extract_container")

    # Initialize lists to store parent and extracted files
    parent_files = []
    extracted_files = []
    
    # Get the list of files in the source container
    files = yield context.call_activity("get_source_files", json.dumps({'source_container': source_container, 'extension': '.pdf', 'prefix': ''}))

    # For each PDF file, split it into single-page chunks and save to chunks container
    split_pdf_tasks = []
    for file in files:
        # Append the file to the parent_files list
        parent_files.append(file)
        # Create a task to split the PDF file and append it to the split_pdf_tasks list
        split_pdf_tasks.append(context.call_activity("split_pdf_files", json.dumps({'source_container': source_container, 'chunks_container': chunks_container, 'file': file})))
    # Execute all the split PDF tasks and get the results
    split_pdf_files = yield context.task_all(split_pdf_tasks)
    # Flatten the list of split PDF files
    split_pdf_files = [item for sublist in split_pdf_files for item in sublist]

    # Convert the split PDF files from JSON strings to Python dictionaries
    pdf_chunks = [json.loads(x) for x in split_pdf_files]

    # For each PDF chunk, process it with Document Intelligence and save the results to the extracts container
    extract_pdf_tasks = []
    for pdf in pdf_chunks:
        # Append the child file to the extracted_files list
        extracted_files.append(pdf['child'])
        # Create a task to process the PDF chunk and append it to the extract_pdf_tasks list
        extract_pdf_tasks.append(context.call_activity("process_pdf_with_document_intelligence", json.dumps({'child': pdf['child'], 'parent': pdf['parent'], 'chunks_container': chunks_container, 'doc_intel_results_container': doc_intel_results_container, 'extracts_container': extract_container})))
    # Execute all the extract PDF tasks and get the results
    extracted_pdf_files = yield context.task_all(extract_pdf_tasks)

    # For each extracted PDF file, generate embeddings and save the results
    generate_embeddings_tasks = []
    for file in extracted_pdf_files:
        # Create a task to generate embeddings for the extracted file and append it to the generate_embeddings_tasks list
        generate_embeddings_tasks.append(context.call_activity("generate_extract_embeddings", json.dumps({'extract_container': extract_container, 'file': file})))
    # Execute all the generate embeddings tasks and get the results
    processed_documents = yield context.task_all(generate_embeddings_tasks)
    
    # Return the list of parent files and processed documents as a JSON string
    return json.dumps({'parent_files': parent_files, 'processed_documents': processed_documents})

@app.orchestration_trigger(context_name="context")
def mp3_orchestrator(context):
    
    # Get the input payload from the context
    payload = context.get_input()
    
    # Extract the container names and prefix path from the payload
    source_container = payload.get("source_container")
    transcription_results_container = payload.get("transcription_results_container")
    extract_container = payload.get("extract_container")
    prefix_path = payload.get("prefix_path")

    # Initialize list to store parent files
    parent_files = []

    # Get the list of files in the source container
    files = yield context.call_activity("get_source_files", json.dumps({'source_container': source_container, 'extension': '.mp3', 'prefix': prefix_path}))

    # Transcribe all files with AOAI whisper model and save transcriptions to transcript/extract container
    transcribe_files_tasks = []
    for file in files:
        # Append the file to the parent_files list
        parent_files.append(file)
        # Create a task to transcribe the audio file and append it to the transcribe_files_tasks list
        transcribe_files_tasks.append(context.call_activity("transcribe_audio_files", json.dumps({'source_container': source_container, 'extract_container': extract_container, 'transcription_results_container': transcription_results_container, 'file': file})))
    # Execute all the transcribe files tasks and get the results
    transcribed_files = yield context.task_all(transcribe_files_tasks)

    # For each transcribed file, generate embeddings and save the results
    generate_embeddings_tasks = []
    for file in transcribed_files:
        # Create a task to generate embeddings for the transcribed file and append it to the generate_embeddings_tasks list
        generate_embeddings_tasks.append(context.call_activity("generate_extract_embeddings", json.dumps({'extract_container': extract_container, 'file': file})))
    # Execute all the generate embeddings tasks and get the results
    processed_documents = yield context.task_all(generate_embeddings_tasks)
    
    # Return the list of parent files and processed documents as a JSON string
    return json.dumps({'parent_files': parent_files, 'processed_documents': processed_documents})

@app.orchestration_trigger(context_name="context")
def wav_orchestrator(context):
    
    # Get the input payload from the context
    payload = context.get_input()
    
    # Extract the container names and prefix path from the payload
    source_container = payload.get("source_container")
    transcription_results_container = payload.get("transcription_results_container")
    extract_container = payload.get("extract_container")
    prefix_path = payload.get("prefix_path")

    # Initialize list to store parent files
    parent_files = []

    # Initialize list to store extracted files
    extracted_files = []
    
    # Get the list of files in the source container
    files = yield context.call_activity("get_source_files", json.dumps({'source_container': source_container, 'extension': '.wav', 'prefix': prefix_path}))

    # Transcribe all files with AOAI whisper model and save transcriptions to transcript/extract container
    transcribe_files_tasks = []
    for file in files:
        # Append the file to the parent_files list
        parent_files.append(file)
        # Create a task to transcribe the audio file and append it to the transcribe_files_tasks list
        transcribe_files_tasks.append(context.call_activity("transcribe_audio_files", json.dumps({'source_container': source_container, 'extract_container': extract_container, 'transcription_results_container': transcription_results_container, 'file': file})))
    # Execute all the transcribe files tasks and get the results
    transcribed_files = yield context.task_all(transcribe_files_tasks)

    # For each transcribed file, generate embeddings and save the results
    generate_embeddings_tasks = []
    for file in transcribed_files:
        # Create a task to generate embeddings for the transcribed file and append it to the generate_embeddings_tasks list
        generate_embeddings_tasks.append(context.call_activity("generate_extract_embeddings", json.dumps({'extract_container': extract_container, 'file': file})))
    # Execute all the generate embeddings tasks and get the results
    processed_documents = yield context.task_all(generate_embeddings_tasks)
    
    # Return the list of parent files and processed documents as a JSON string
    return json.dumps({'parent_files': parent_files, 'processed_documents': processed_documents})

@app.orchestration_trigger(context_name="context")
def index_documents_orchestrator(context):
    
    # Get the input payload from the context
    payload = context.get_input()
    
    # Extract the container name, index stem name, and prefix path from the payload
    extract_container = payload.get("extract_container")
    index_stem_name = payload.get("index_stem_name")
    prefix_path = payload.get("prefix_path")

    # Get the list of files in the source container
    files = yield context.call_activity("get_source_files", json.dumps({'source_container': extract_container, 'extension': '.json', 'prefix': prefix_path}))

    # Get the current index and its fields
    latest_index, fields = get_current_index(index_stem_name)

    # Initialize list to store tasks for inserting records
    insert_tasks = []
    for file in files:
        # Create a task to insert a record for the file and append it to the insert_tasks list
        insert_tasks.append(context.call_activity("insert_record", json.dumps({'file': file, 'index': latest_index, 'fields': fields, 'extracts-container': extract_container})))
    # Execute all the insert record tasks and get the results
    insert_results = yield context.task_all(insert_tasks)
    
    # Return the list of indexed documents and the index name as a JSON string
    return json.dumps({'indexed_documents': insert_results, 'index_name': latest_index})

# Activities
@app.activity_trigger(input_name="activitypayload")
def get_source_files(activitypayload: str):

    # Load the activity payload as a JSON string
    data = json.loads(activitypayload)
    
    # Extract the source container, file extension, and prefix from the payload
    source_container = data.get("source_container")
    extension = data.get("extension")
    prefix = data.get("prefix")
    
    # Create a BlobServiceClient object which will be used to create a container client
    blob_service_client = BlobServiceClient.from_connection_string(os.environ['STORAGE_CONN_STR'])
    
    # Get a ContainerClient object from the BlobServiceClient
    container_client = blob_service_client.get_container_client(source_container)
    
    # List all blobs in the container that start with the specified prefix
    blobs = container_client.list_blobs(name_starts_with=prefix)

    # Initialize an empty list to store the names of the files
    files = []

    # For each blob in the container
    for blob in blobs:
        # If the blob's name ends with the specified extension
        if blob.name.lower().endswith(extension):
            # Append the blob's name to the files list
            files.append(blob.name)

    # Return the list of file names
    return files

@app.activity_trigger(input_name="activitypayload")
def split_pdf_files(activitypayload: str):

    # Load the activity payload as a JSON string
    data = json.loads(activitypayload)
    
    # Extract the source container, chunks container, and file name from the payload
    source_container = data.get("source_container")
    chunks_container = data.get("chunks_container")
    file = data.get("file")

    # Create a BlobServiceClient object which will be used to create a container client
    blob_service_client = BlobServiceClient.from_connection_string(os.environ['STORAGE_CONN_STR'])
    
    # Get a ContainerClient object for the source and chunks containers
    source_container = blob_service_client.get_container_client(source_container)
    chunks_container = blob_service_client.get_container_client(chunks_container)

    # Get a BlobClient object for the PDF file
    pdf_blob_client = source_container.get_blob_client(file)

    # Initialize an empty list to store the PDF chunks
    pdf_chunks = []

    # If the PDF file exists
    if  pdf_blob_client.exists():

        # Create a PdfReader object for the PDF file
        pdf_reader = PdfReader(BytesIO(pdf_blob_client.download_blob().readall()))

        # Get the number of pages in the PDF file
        num_pages = len(pdf_reader.pages)

        # For each page in the PDF file
        for i in range(num_pages):
            # Create a new file name for the PDF chunk
            new_file_name = file.replace('.pdf', '') + '_page_' + str(i+1) + '.pdf'

            # Create a PdfWriter object
            pdf_writer = PdfWriter()
            # Add the page to the PdfWriter object
            pdf_writer.add_page(pdf_reader.pages[i])

            # Create a BytesIO object for the output stream
            output_stream = BytesIO()
            # Write the PdfWriter object to the output stream
            pdf_writer.write(output_stream)

            # Reset the position of the output stream to the beginning
            output_stream.seek(0)

            # Get a BlobClient object for the PDF chunk
            pdf_chunk_blob_client = chunks_container.get_blob_client(blob=new_file_name)

            # Upload the PDF chunk to the chunks container
            pdf_chunk_blob_client.upload_blob(output_stream, overwrite=True)
            
            # Append the parent file name and child file name to the pdf_chunks list
            pdf_chunks.append(json.dumps({'parent': file, 'child': new_file_name}))

    # Return the list of PDF chunks
    return pdf_chunks
    
@app.activity_trigger(input_name="activitypayload")
def process_pdf_with_document_intelligence(activitypayload: str):
    """
    Process a PDF file using Document Intelligence.

    Args:
        activitypayload (str): The payload containing information about the PDF file.

    Returns:
        str: The updated filename of the processed PDF file.
    """

    # Load the activity payload as a JSON string
    data = json.loads(activitypayload)

    # Extract the child file name, parent file name, and container names from the payload
    child = data.get("child")
    parent = data.get("parent")
    chunks_container = data.get("chunks_container")
    doc_intel_results_container = data.get("doc_intel_results_container")
    extracts_container = data.get("extracts_container")

    # Create a BlobServiceClient object which will be used to create a container client
    blob_service_client = BlobServiceClient.from_connection_string(os.environ['STORAGE_CONN_STR'])
    # Get a ContainerClient object for the chunks, Document Intelligence results, and extracts containers
    chunks_container_client = blob_service_client.get_container_client(container=chunks_container)
    doc_intel_results_container_client = blob_service_client.get_container_client(container=doc_intel_results_container)
    extracts_container_client = blob_service_client.get_container_client(container=extracts_container)

    # Get a BlobClient object for the PDF file
    pdf_blob_client = chunks_container_client.get_blob_client(blob=child)

    # Initialize a flag to indicate whether the PDF file has been processed
    processed = False

    # Create a new file name for the processed PDF file
    updated_filename = child.replace('.pdf', '.json')

    # Get a BlobClient object for the Document Intelligence results file
    doc_results_blob_client = doc_intel_results_container_client.get_blob_client(blob=updated_filename)
    # Check if the Document Intelligence results file exists
    if doc_results_blob_client.exists():

        # Get a BlobClient object for the extracts file
        extract_blob_client = extracts_container_client.get_blob_client(blob=updated_filename)

        # If the extracts file exists
        if extract_blob_client.exists():

            # Download the PDF file as a stream
            pdf_stream_downloader = (pdf_blob_client.download_blob())

            # Calculate the MD5 hash of the PDF file
            md5_hash = hashlib.md5()
            for byte_block in iter(lambda: pdf_stream_downloader.read(4096), b""):
                md5_hash.update(byte_block)
            checksum = md5_hash.hexdigest()

            # Load the extracts file as a JSON string
            extract_data = json.loads((extract_blob_client.download_blob().readall()).decode('utf-8'))

            # If the checksum in the extracts file matches the checksum of the PDF file
            if 'checksum' in extract_data.keys():
                if extract_data['checksum']==checksum:
                    # Set the processed flag to True
                    processed = True

    # If the PDF file has not been processed
    if not processed:
        # Extract the PDF file with AFR, save the AFR results, and save the extract results

        # Download the PDF file
        pdf_data = pdf_blob_client.download_blob().readall()
        # Analyze the PDF file with Document Intelligence
        doc_intel_result = analyze_pdf(pdf_data)

        # Get a BlobClient object for the Document Intelligence results file
        doc_intel_result_client = doc_intel_results_container_client.get_blob_client(updated_filename)

        # Upload the Document Intelligence results to the Document Intelligence results container
        doc_intel_result_client.upload_blob(json.dumps(doc_intel_result), overwrite=True)

        # Extract the results from the Document Intelligence results
        page_map = extract_results(doc_intel_result, updated_filename)

        # Extract the page number from the child file name
        page_number = child.split('_')[-1]
        page_number = page_number.replace('.pdf', '')
        # Get the content from the page map
        content = page_map[0][1]

        # Generate a unique ID for the record
        id_str = child
        hash_object = hashlib.sha256()
        hash_object.update(id_str.encode('utf-8'))
        id = hash_object.hexdigest()

        # Download the PDF file as a stream
        pdf_stream_downloader = (pdf_blob_client.download_blob())

        # Calculate the MD5 hash of the PDF file
        md5_hash = hashlib.md5()
        for byte_block in iter(lambda: pdf_stream_downloader.read(4096), b""):
            md5_hash.update(byte_block)
        checksum = md5_hash.hexdigest()

        # Create a record for the PDF file
        record = {
            'content': content,
            'sourcefile': parent,
            'sourcepage': child,
            'pagenumber': page_number,
            'category': 'manual',
            'id': str(id),
            'checksum': checksum
        }

        # Get a BlobClient object for the extracts file
        extract_blob_client = extracts_container_client.get_blob_client(blob=updated_filename)

        # Upload the record to the extracts container
        extract_blob_client.upload_blob(json.dumps(record), overwrite=True)

    # Return the updated file name
    return updated_filename

@app.activity_trigger(input_name="activitypayload")
def transcribe_audio_files(activitypayload: str):

    # Load the activity payload as a JSON string
    data = json.loads(activitypayload)

    # Extract the source container, extract container, transcription results container, and file name from the payload
    source_container_name = data.get("source_container")
    extract_container_name = data.get("extract_container")
    transcription_results_container_name = data.get("transcription_results_container")
    file = data.get("file")

    # Create new file names for the transcript and extract files
    transcript_file_name = file.replace('.mp3', '.txt').replace('.wav', '.txt').replace('.MP3', '.txt').replace('.WAV', '.txt')
    extract_file_name = file.replace('.mp3', '.json').replace('.wav', '.json').replace('.MP3', '.json').replace('.WAV', '.json')

    # Create a BlobServiceClient object which will be used to create a container client
    blob_service_client = BlobServiceClient.from_connection_string(os.environ['STORAGE_CONN_STR'])

    # Get a ContainerClient object for the source, extract, and transcription results containers
    source_container = blob_service_client.get_container_client(source_container_name)
    extract_container = blob_service_client.get_container_client(extract_container_name)
    transcription_results_container = blob_service_client.get_container_client(transcription_results_container_name)

    # Get a BlobClient object for the transcript file
    transcript_blob_client = transcription_results_container.get_blob_client(blob=transcript_file_name)

    # If the transcript file does not exist
    if not transcript_blob_client.exists():

        # Get a BlobClient object for the audio file
        audio_blob_client = source_container.get_blob_client(blob=file)

        # Download the audio file
        audio_data = audio_blob_client.download_blob().readall()

        # Get the extension of the audio file
        _, extension = os.path.splitext(audio_blob_client.blob_name)

        # Download the audio file to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temp_file:
            temp_file.write(audio_data)

        print(f'Saved {audio_blob_client.blob_name} to {temp_file.name}\n')

        # Get the path of the temporary file
        local_audio_file = temp_file.name

        try:
            # Transcribe the audio file
            transcript = get_transcription(local_audio_file)
        except Exception as e:
            pass
        finally:
            # Delete the temporary file
            os.remove(local_audio_file)

        # Upload the transcript to the transcription results container
        transcript_blob_client.upload_blob(transcript, overwrite=True)

    # Download the transcript as a string
    transcript_text = transcript_blob_client.download_blob().readall().decode('utf-8')

    # Generate a unique ID for the record
    id_str = file
    hash_object = hashlib.sha256()  
    hash_object.update(id_str.encode('utf-8'))  
    id = hash_object.hexdigest()  

    # Create a record for the transcript
    record = {
        'sourcefile': file,
        'content': transcript_text,
        'id': str(id),
        'category': 'audio'
    }

    # Get a BlobClient object for the extract file
    extract_blob_client = extract_container.get_blob_client(blob=extract_file_name)

    # Upload the record to the extract container
    extract_blob_client.upload_blob(json.dumps(record), overwrite=True)

    # Return the name of the extract file
    return extract_file_name


@app.activity_trigger(input_name="activitypayload")
def generate_extract_embeddings(activitypayload: str):

    # Load the activity payload as a JSON string
    data = json.loads(activitypayload)

    # Extract the extract container and file name from the payload
    extract_container = data.get("extract_container")
    file = data.get("file")

    # Create a BlobServiceClient object which will be used to create a container client
    blob_service_client = BlobServiceClient.from_connection_string(os.environ['STORAGE_CONN_STR'])

    # Get a ContainerClient object for the extract container
    extract_container_client = blob_service_client.get_container_client(container=extract_container)

    # Get a BlobClient object for the extract file
    extract_blob = extract_container_client.get_blob_client(blob=file)

    # Load the extract file as a JSON string
    extract_data =  json.loads((extract_blob.download_blob().readall()).decode('utf-8'))

    # If the extract data does not contain embeddings
    if 'embeddings' not in extract_data.keys():

        # Extract the content from the extract data
        content = extract_data['content']

        # Generate embeddings for the content
        embeddings = generate_embeddings(content)

        # Update the extract data with the embeddings
        updated_record = extract_data
        updated_record['embeddings'] = embeddings

        # Upload the updated extract data to the extract container
        extract_blob.upload_blob(json.dumps(updated_record), overwrite=True)

    # Return the file name
    return file

@app.activity_trigger(input_name="activitypayload")
def insert_record(activitypayload: str):

    # Load the activity payload as a JSON string
    data = json.loads(activitypayload)

    # Extract the file name, index, fields, and extracts container from the payload
    file = data.get("file")
    index = data.get("index")
    fields = data.get("fields")
    extracts_container = data.get("extracts-container")

    # Create a BlobServiceClient object which will be used to create a container client
    blob_service_client = BlobServiceClient.from_connection_string(os.environ['STORAGE_CONN_STR'])

    # Get a ContainerClient object for the extracts container
    container_client = blob_service_client.get_container_client(container=extracts_container)

    # Get a BlobClient object for the file
    blob_client = container_client.get_blob_client(blob=file)

    # Download the file as a string
    file_data = (blob_client.download_blob().readall()).decode('utf-8')

    # Load the file data as a JSON string
    file_data =  json.loads(file_data)

    # Filter the file data to only include the specified fields
    file_data = {key: value for key, value in file_data.items() if key in fields}

    # Insert the file data into the specified index
    insert_documents_vector([file_data], index)

    # Return the file name
    return file

# Standalone Functions

# This function creates a new index
@app.route(route="create_new_index", auth_level=func.AuthLevel.FUNCTION)
def create_new_index(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    # Get the JSON payload from the request
    data = req.get_json()
    # Extract the index stem name and fields from the payload
    stem_name = data.get("index_stem_name")
    fields = data.get("fields")

    # Call the function to create a vector index with the specified stem name and fields
    response = create_vector_index(stem_name, fields)

    # Return the response
    return response

# This function updates an index alias
@app.route(route="update_index_alias", auth_level=func.AuthLevel.FUNCTION)
def update_index_alias(req: func.HttpRequest) -> func.HttpResponse:
    
    # Get the JSON payload from the request
    data = req.get_json()
    # Extract the index stem name from the payload
    stem_name = data.get("index_stem_name")
    
    # Call the function to get the current index for the specified stem name
    latest_index  = get_current_index(stem_name)

    # Call the function to create or update the index alias with the specified stem name and latest index
    response = create_update_index_alias(stem_name, latest_index)

    # Return the response
    return  response