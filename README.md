# Lab - Apache Airflow

## Overview

Welcome to Apache Airflow. 

## Setup

- Fork this repository into your own GitHub account and clone it to your local machine.
- Be sure you have Docker Desktop running.
- Install the `astro` CLI from Astronomer.io. Follow [these instructions](https://www.astronomer.io/docs/astro/cli/install-cli/) for your platform.

## Project Contents

This Airflow project contains the following files and folders:

- dags/: This folder contains the Python files for your Airflow DAGs. By default, this project does not yet contain a DAG:
- Dockerfile: This file contains a versioned Astro Runtime Docker image that provides a differentiated Airflow experience. If you want to execute other commands or overrides at runtime, specify them here.
- include: This folder contains any additional files that you want to include as part of your project. It is empty by default.
- packages.txt: Install OS-level packages needed for your project by adding them to this file. It is empty by default.
- requirements.txt: Install Python packages needed for your project by adding them to this file. It is empty by default, but the `requests` package has been added for this lab.
- plugins: Add custom or community plugins for your project to this file. It is empty by default.
- airflow_settings.yaml: Use this local-only file to specify Airflow Connections, Variables, and Pools instead of entering them in the Airflow UI as you develop DAGs in this project.

## Write a DAG

For this lab you will write a simple ETL pipeline example that pulls a "messy" data file from a remote source. Then let's have Airflow clean up the document by removing empty lines and unnecessary characters. Next let's extract a count of certain values present in the log, and output those values to (1) a log file; (2) a stored text file; and (3) an Airflow Dataset, where another DAG could make use of it.

0. View the original data file here and observe the messy details: https://s3.amazonaws.com/ds2002-resources/data/messy.log 
1. Create a new file in the `dags/` directory of the project. Name it `ingestion.py`.
2. Follow the chunks below and paste them into your file, in order. 

### Imports

These are the packages necessary for the DAG to run. Most of these come built-in to 
Airflow, but in our case `requests` had to be added both here and in `requirements.txt`.

    from datetime import datetime, timedelta
    from airflow import DAG
    from airflow.operators.python import PythonOperator
    from airflow.datasets import Dataset
    import requests
    import re
    import logging
    import json

### DAG Defaults

This sets up any defaults if they are not specified later when the DAG is instantiated.

    default_args = {
        'owner': 'airflow',
        'depends_on_past': False,
        'email_on_failure': False,
        'email_on_retry': False,
        'retries': 1,
        'retry_delay': timedelta(minutes=5),
    }

### Task Functions

Each of these is a separate Python function that will be called by each task.

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

### Instantiate the DAG and Add Tasks

This DAG is instantiated using a `with` command, but it could also be invoked using
a `@` decorator statement. Note the four tasks are then laid out, each using a specific type of Operator, then given a `task_id` and invoked via separate `python_callable` functions.

At the bottom of the DAG definition, notice the linear flow from one task to another using `>>`.

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

3. Save this completed file as a single file. Be sure it is placed in the `dags/` directory or it will not run.

For more on how DAGs work, see our [Getting started tutorial](https://www.astronomer.io/docs/learn/get-started-with-airflow).

## Deploy Your Project Locally

1. Start Airflow on your local machine by running 'astro dev start'.

This command will spin up 4 Docker containers on your machine, each for a different Airflow component:

- **Postgres**: Airflow's Metadata Database
- **Webserver**: The Airflow component responsible for rendering the Airflow UI
- **Scheduler**: The Airflow component responsible for monitoring and triggering tasks
- **Triggerer**: The Airflow component responsible for triggering deferred tasks

2. Verify that all 4 Docker containers were created by running 'docker ps'.

Note: Running 'astro dev start' will start your project with the Airflow Webserver exposed at port 8080 and Postgres exposed at port 5432. If you already have either of those ports allocated, you can either [stop your existing Docker containers or change the port](https://www.astronomer.io/docs/astro/cli/troubleshoot-locally#ports-are-not-available-for-my-local-airflow-webserver).

3. Access the Airflow UI for your local Airflow project. To do so, go to http://localhost:8080/ and log in with 'admin' for both your Username and Password.

You should also be able to access your Postgres Database at `localhost:5432/postgres`.

## Run your DAG

1. When you start your Airflow project with your DAG file present in the `dags/` directory, you should see it listed on the main page of the Airflow website.
2. Trigger your DAG by clicking on the "play" arrow to the right of the DAG entry.
3. Watch your DAG run by tracking the tasks scheduled, waiting, running, or completed.
4. Once completed, click on the name of your DAG to dig into the details of your latest run. 
5. Take time to browse the details of the run, noting the count of total successful runs, and note the colored matrix on the left showing success/fail for each of your tasks, for each of your runs.
6. Click into the GRAPH tab of your latest run. Select your left-most task by clicking on it once (highlighting it). You can then select further views for each task by selecting that header - "Task Duration" or "XCom", etc. In our case, click on "Logs" to view the specific log output for each specific task.
7. Repeat this browsing operation for each of your four tasks.

## Evaluate

Here are some simple steps to evaluate if your DAG ran successfully:

1. Did it complete without errors?
2. View the log output of the second task - does the data appear cleaner than the original data?
3. View the count output (in the log panel) of the third task. What values do you get?
4. Note the log panel of the final task. Notice that the cleaned log file was saved to `/tmp/cleaned_log_2025_xxxxxxxxxx.txt`. This was written to the scheduler container of your four-container Airflow deployment.
5. Use `docker ps` to find the container ID of the running scheduler container. Enter into the shell of that container using `docker exec -it` and referring to the container ID. That command will look something like this:

    ```
    docker exec -it 1a2b3c /bin/bash
    ```

6. `cd` to the `/tmp/` directory of that container and view the actual log file using `cat`. This is the cleaned file, which could be shipped to storage, a database, or a cache by modifying the final DAG task, or adding a new one.
7. Finally, notice in the `store_log_counts` function that you stored the dataset using `.xcom`. This means that if you click the "Datasets" tab at the top of the Airflow GUI, you should see it listed.

## Submit

Copy the "Logs" output from your fourth DAG task and paste it into the text field for this lab. Then submit the lab.

## Cleanup

In your terminal, from the root folder of this project, run this command to stop the Airflow project:

```
astro dev stop
```
