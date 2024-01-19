import azure.functions as func
import azure.durable_functions as df
import logging
import json
import os
import hashlib
from azure.storage.blob import BlobServiceClient
from PyPDF2 import PdfReader, PdfWriter
from io import BytesIO

from doc_intelligence_utilities import analyze_pdf, extract_results
from aoai_utilities import generate_embeddings

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

# Orchestrator
@app.orchestration_trigger(context_name="context")
def pdf_orchestrator(context):
    
    payload = context.get_input()
    source_container = payload.get("source_container")
    chunks_container = payload.get("chunks_container")
    doc_intel_results_container = payload.get("doc_intel_results_container")
    extract_container = payload.get("extract_container")

    parent_files = []

    extracted_files = []
    
    # Get the list of files in the source container
    files = yield context.call_activity("get_source_files", json.dumps({'source_container': source_container, 'extension': '.pdf', 'prefix': ''}))

    # For each PDF file, split it into single-page chunks and save to chunks container
    split_pdf_tasks = []
    for file in files:
        parent_files.append(file)
        split_pdf_tasks.append(context.call_activity("split_pdf_files", json.dumps({'source_container': source_container, 'chunks_container': chunks_container, 'file': file})))
    split_pdf_files = yield context.task_all(split_pdf_tasks)
    split_pdf_files = [item for sublist in split_pdf_files for item in sublist]

    pdf_chunks = [json.loads(x) for x in split_pdf_files]

    extract_pdf_tasks = []
    for pdf in pdf_chunks:
        extracted_files.append(pdf['child'])
        extract_pdf_tasks.append(context.call_activity("process_pdf_with_document_intelligence", json.dumps({'child': pdf['child'], 'parent': pdf['parent'], 'chunks_container': chunks_container, 'doc_intel_results_container': doc_intel_results_container, 'extracts_container': extract_container})))
    extracted_pdf_files = yield context.task_all(extract_pdf_tasks)

    generate_embeddings_tasks = []
    for file in extracted_pdf_files:
        generate_embeddings_tasks.append(context.call_activity("generate_extract_embeddings", json.dumps({'extract_container': extract_container, 'file': file})))
    processed_documents = yield context.task_all(generate_embeddings_tasks)
    t = ''
    
    return json.dumps({'parent_files': parent_files, 'processed_documents': processed_documents})

# Activity
@app.activity_trigger(input_name="activitypayload")
def get_source_files(activitypayload: str):

    data = json.loads(activitypayload)
    source_container = data.get("source_container")
    extension = data.get("extension")
    prefix = data.get("prefix")
    

    blob_service_client = BlobServiceClient.from_connection_string(os.environ['STORAGE_CONN_STR'])
    container_client = blob_service_client.get_container_client(source_container)
    blobs = container_client.list_blobs(name_starts_with=prefix)

    files = []

    for blob in blobs:
        if blob.name.endswith(extension):
            files.append(blob.name)

    return files

@app.activity_trigger(input_name="activitypayload")
def split_pdf_files(activitypayload: str):

    data = json.loads(activitypayload)
    source_container = data.get("source_container")
    chunks_container = data.get("chunks_container")
    file = data.get("file")

    blob_service_client = BlobServiceClient.from_connection_string(os.environ['STORAGE_CONN_STR'])
    source_container = blob_service_client.get_container_client(source_container)
    chunks_container = blob_service_client.get_container_client(chunks_container)

    pdf_blob_client = source_container.get_blob_client(file)

    pdf_chunks = []

    if  pdf_blob_client.exists():

        pdf_reader = PdfReader(BytesIO(pdf_blob_client.download_blob().readall()))

        num_pages = len(pdf_reader.pages)

        for i in range(num_pages):
            new_file_name = file.replace('.pdf', '') + '_page_' + str(i+1) + '.pdf'

            pdf_writer = PdfWriter()
            pdf_writer.add_page(pdf_reader.pages[i])

            output_stream = BytesIO()
            pdf_writer.write(output_stream)

            output_stream.seek(0)

            pdf_chunk_blob_client = chunks_container.get_blob_client(blob=new_file_name)

            pdf_chunk_blob_client.upload_blob(output_stream, overwrite=True)
            
            pdf_chunks.append(json.dumps({'parent': file, 'child': new_file_name}))

    return pdf_chunks
    
@app.activity_trigger(input_name="activitypayload")
def process_pdf_with_document_intelligence(activitypayload: str):

    data = json.loads(activitypayload)

    child = data.get("child")
    parent = data.get("parent")
    chunks_container = data.get("chunks_container")
    doc_intel_results_container = data.get("doc_intel_results_container")
    extracts_container = data.get("extracts_container")
    

    blob_service_client = BlobServiceClient.from_connection_string(os.environ['STORAGE_CONN_STR'])
    chunks_container_client = blob_service_client.get_container_client(container=chunks_container)
    doc_intel_results_container_client = blob_service_client.get_container_client(container=doc_intel_results_container)
    extracts_container_client = blob_service_client.get_container_client(container=extracts_container)

    pdf_blob_client = chunks_container_client.get_blob_client(blob=child)
    
    processed = False

    updated_filename = child.replace('.pdf', '.json')

    doc_results_blob_client = doc_intel_results_container_client.get_blob_client(blob=updated_filename)
    # Check if Doc Intel result file exists
    if doc_results_blob_client.exists():

        extract_blob_client = extracts_container_client.get_blob_client(blob=updated_filename)

        if extract_blob_client.exists():

            pdf_stream_downloader = (pdf_blob_client.download_blob())
            
            md5_hash = hashlib.md5()
            for byte_block in iter(lambda: pdf_stream_downloader.read(4096), b""):
                md5_hash.update(byte_block)
            checksum = md5_hash.hexdigest()

            extract_data = json.loads((extract_blob_client.download_blob().readall()).decode('utf-8'))

            if 'checksum' in extract_data.keys():
                if extract_data['checksum']==checksum:
                    processed = True

    if not processed:
        ## Extract with AFR, save AFR results, save extract results
        pdf_data = pdf_blob_client.download_blob().readall()
        doc_intel_result = analyze_pdf(pdf_data)

        doc_intel_result_client = doc_intel_results_container_client.get_blob_client(updated_filename)

        doc_intel_result_client.upload_blob(json.dumps(doc_intel_result), overwrite=True)

        page_map = extract_results(doc_intel_result, updated_filename)

        page_number = child.split('_')[-1]  
        page_number = page_number.replace('.pdf', '')  
        content = page_map[0][1]

        id_str = child
        hash_object = hashlib.sha256()  
        hash_object.update(id_str.encode('utf-8'))  
        id = hash_object.hexdigest()  

        pdf_stream_downloader = (pdf_blob_client.download_blob())
            
        md5_hash = hashlib.md5()
        for byte_block in iter(lambda: pdf_stream_downloader.read(4096), b""):
            md5_hash.update(byte_block)
        checksum = md5_hash.hexdigest()

        record = {  
            'content': content,  
            'sourcefile': parent,  
            'sourcepage': child,  
            'pagenumber': page_number,  
            'category': 'manual',  
            'id': str(id),  
            'checksum': checksum  
        }  
  

        extract_blob_client.upload_blob(json.dumps(record), overwrite=True)
        
    return updated_filename

@app.activity_trigger(input_name="activitypayload")
def generate_extract_embeddings(activitypayload: str):

    data = json.loads(activitypayload)
    extract_container = data.get("extract_container")
    file = data.get("file")

    blob_service_client = BlobServiceClient.from_connection_string(os.environ['STORAGE_CONN_STR'])
    extract_container_client = blob_service_client.get_container_client(container=extract_container)
    extract_blob = extract_container_client.get_blob_client(blob=file)

    extract_data =  json.loads((extract_blob.download_blob().readall()).decode('utf-8'))

    if 'embeddings' not in extract_data.keys():

        content = extract_data['content']

        embeddings = generate_embeddings(content)

        updated_record = extract_data
        updated_record['embeddings'] = embeddings

        extract_blob.upload_blob(json.dumps(updated_record), overwrite=True)

    return file