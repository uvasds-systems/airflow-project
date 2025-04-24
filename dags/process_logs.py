from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.datasets import Dataset
import requests
import re
import logging
import json

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Define the dataset
log_counts_dataset = Dataset("log_counts")

def fetch_log_file():
    url = "https://s3.amazonaws.com/ds2002-resources/data/messy.log"
    response = requests.get(url)
    response.raise_for_status()
    return response.text

def clean_log_file(**context):
    log_content = context['ti'].xcom_pull(task_ids='fetch_log_file')
    
    # Remove blank lines and lines with only integers
    lines = [line for line in log_content.split('\n') 
             if line.strip() and not re.match(r'^\s*\d+\s*$', line)]
    
    # Remove meaningless ":......" patterns
    cleaned_lines = []
    for line in lines:
        cleaned_line = re.sub(r':\.+', '', line)
        cleaned_lines.append(cleaned_line)
    
    return '\n'.join(cleaned_lines)

def count_log_types(**context):
    cleaned_content = context['ti'].xcom_pull(task_ids='clean_log_file')
    lines = cleaned_content.split('\n')
    
    info_count = sum(1 for line in lines if 'INFO' in line)
    trace_count = sum(1 for line in lines if 'TRACE' in line)
    event_count = sum(1 for line in lines if 'EVENT' in line)
    proterr_count = sum(1 for line in lines if 'PROTERR' in line)
    
    logging.info(f"INFO lines: {info_count}")
    logging.info(f"TRACE lines: {trace_count}")
    logging.info(f"EVENT lines: {event_count}")
    logging.info(f"PROTERR lines: {proterr_count}")
    
    return {
        'info_count': info_count,
        'trace_count': trace_count,
        'event_count': event_count,
        'proterr_count': proterr_count
    }

def store_log_counts(**context):
    counts = context['ti'].xcom_pull(task_ids='count_log_types')
    cleaned_content = context['ti'].xcom_pull(task_ids='clean_log_file')
    timestamp = datetime.now().isoformat()
    
    # Create the dataset content
    dataset_content = {
        'timestamp': timestamp,
        'counts': counts
    }
    
    # Store the dataset
    context['ti'].xcom_push(key='log_counts', value=json.dumps(dataset_content))
    
    # Save cleaned data to file
    filename = f"/tmp/cleaned_log_{timestamp.replace(':', '-')}.txt"
    with open(filename, 'w') as f:
        f.write(cleaned_content)
    
    # Log the stored data and file location
    logging.info(f"Stored log counts dataset: {dataset_content}")
    logging.info(f"Saved cleaned log to: {filename}")
    
    return dataset_content

with DAG(
    'process_logs',
    default_args=default_args,
    description='A DAG to process and analyze log files',
    schedule_interval=timedelta(days=1),
    start_date=datetime(2024, 1, 1),
    catchup=False,
) as dag:

    fetch_task = PythonOperator(
        task_id='fetch_log_file',
        python_callable=fetch_log_file,
    )

    clean_task = PythonOperator(
        task_id='clean_log_file',
        python_callable=clean_log_file,
    )

    count_task = PythonOperator(
        task_id='count_log_types',
        python_callable=count_log_types,
    )
    
    store_task = PythonOperator(
        task_id='store_log_counts',
        python_callable=store_log_counts,
        outlets=[log_counts_dataset],
    )

    fetch_task >> clean_task >> count_task >> store_task 