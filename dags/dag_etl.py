from airflow import DAG
from airflow.operators.dummy_operator import DummyOperator
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.providers.amazon.aws.operators.glue_crawler import GlueCrawlerOperator
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.operators.python import PythonOperator

from clients.spaceflightnews_client import ExtractAPI

import os
import pandas as pd
import logging
from tenacity import retry, stop_after_attempt, wait_fixed
# Configuración
BUCKET_NAME = "source-data-spacenews"
S3_KEY = "raw/archivo.json"

# Definir la ruta del archivo temporal
TEMP_FILE = "/tmp/archivo.json"

# Configurar los logs de Airflow
logging.basicConfig(
                    level=logging.INFO,  # Definicion del nivel de logs
                    format='%(asctime)s - %(levelname)s - %(message)s',  # Formato de logs
                    handlers=[
                        logging.FileHandler("extraction_log.log"),  # Guardar los logs
                        logging.StreamHandler()  #mostrar los logs en consola
                            ]
                    )

default_args = {
    "owner":"Andres Urrea",
    "depends_on_past" : False,
    "email_on_failture" :False,
    "email_on_retry" :False,
    "retries" : 1
}


#La presente funcion extrae los datos de la API de Spaceflightnews y los guarda en un archivo temporal
def extract_data(ti):
    try:        
        client_spaceflight = ExtractAPI()
        articles = client_spaceflight.extract_all_articles()    
        ti.xcom_push(key="articles", value=articles)
        logging.info(f"Proceso de extraccion de data realizado con exito")
    except Exception as e:
        logging.error(f"Error en la extraccion de datos: {e}")
        raise e
    
#La presente funcion realiza la limpieza de los datos extraidos de la API de Spaceflightnews
def preprocess_data(ti):
    try:
        
        articles = ti.xcom_pull(task_ids='extract_data', key='articles')    
        if not articles:
            logging.error("No se encontraron datos para procesar")
            return
    
        df_articles  = pd.DataFrame(articles["results"])
        df_articles['type'] = 'article'
    
        df_articles = df_articles.drop_duplicates(subset=['id'], keep='first')
    
        df_articles.to_json(TEMP_FILE, orient="records", lines=True)
        logging.info(f"Proceso de preprocess_data realizado con exito, se extrajeron {len(df_articles)} registros unicos")
        logging.info(f"El archivo temporal se guardo en la ruta {TEMP_FILE}")
    except Exception as e:
        logging.error(f"Error en la funcion preprocess_data: {e}")
        raise e

#La presente funcion guarda el archivo temporal en el buckset de S3 y hace 3 intentos y espera entre intento 5 segundos
@retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
def upload_to_s3():
    #Lee el archivo JSON almacenado y lo sube a un bucket S3.
    
    try:
        if not os.path.exists(TEMP_FILE):
            raise FileNotFoundError(f"El archivo {TEMP_FILE} no existe.")

        s3_hook = S3Hook(aws_conn_id="aws_default")
        s3_hook.load_file(
            filename=TEMP_FILE,
            key=S3_KEY,
            bucket_name=BUCKET_NAME,
            replace=True
            )
        
        logging.info(f"Proceso de almacenamiento en la nube se realizado con exito, Archivo {TEMP_FILE} subido a S3 en s3://{BUCKET_NAME}/{S3_KEY}")
    except Exception as e:
        logging.error(f"Error en la funcion save_to_df: {e}")
        raise e
#La presente funcion elimina el archivo temporal creado en el proceso de extraccion y transformacion
def clear_temp():    
    
    if os.path.exists(TEMP_FILE):
        os.remove(TEMP_FILE)        
        logging.info(f"El archivo temporal {TEMP_FILE} eliminado correctamente.")
    else:        
        logging.info(f"El archivo temporal {TEMP_FILE} no fue encontrado, probablemente ya fue eliminado.")



# Definir el DAG principal con el nombre "csv_dag"
with DAG(
    "DAG_INETUM_ETL",
    default_args=default_args,
    description = "Creacion Dag ETL para INETUM",
    tags=["ETL","Inetum","Glue","S3","AWS","ETL"]
) as dag:
    
    # Definir los operadores del DAG usando los operadores DummyOperator, PythonOperator y DatabricksRunNowOperator
    start = DummyOperator(task_id="start")
    
    extract_data = PythonOperator(
        task_id="extract_data",
        python_callable=extract_data
        )
    
    preprocess_data_task = PythonOperator(
        task_id="preprocess_data",
        python_callable=preprocess_data
        )
    
    load_data_task = PythonOperator(
        task_id="load_data_task",
        python_callable=upload_to_s3
        )
    
    clear_data_task = PythonOperator(
        task_id="clear_data_task",
        python_callable=clear_temp
        )
    
    submit_glue_crwal = GlueCrawlerOperator(
        task_id='run_glue_crawler',
        config={'Name': "crawler_source_flightnews"},
        aws_conn_id='aws_default',
        wait_for_completion = True,
        region_name = 'us-west-2',
        poll_interval = 10
        )
    
    submit_glue_job = GlueJobOperator(
        task_id="submit_glue_job",
        job_name="inetum_job",
        script_location=f"s3://aws-glue-assets-248189914606-us-west-2/scripts/inetum_job.py",
        s3_bucket="aws-glue-assets-248189914606-us-west-2",
        iam_role_name="AWSGlueServiceRole-s3-fullacces-glue-au",
        create_job_kwargs={"GlueVersion": "4.0", "NumberOfWorkers": 2, "WorkerType": "G.1X", "Timeout": 60},
        retry_limit=0,
        script_args={
        "--param1": "valor1",
        "--param2": "valor2"
        },
    )
    
    
    
    end = DummyOperator(task_id="end")
    
    
    # Definir el orden de ejecución de los operadores
    
    start>>extract_data>>preprocess_data_task>>load_data_task>> clear_data_task>> submit_glue_crwal >> submit_glue_job >> end
    