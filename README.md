
![Inetum-AWS](https://github.com/user-attachments/assets/600df596-9fc3-4d8d-bcf7-69c6e9d1e26b)

# inetum
Proyecto de Ingesta y Clasificación de Artículos de SpaceflightNews

Este proyecto permite la extracción, procesamiento, almacenamiento, clasificación de artículos, extracción de entidades (compañías, personas, lugares), extracción de palabras claves del API SpaceflightNews todo esto mediante la implementación de un procesamiento de lenguaje natural orquestado en un flujo de datos en AWS Glue el cual esta orquestado por Apache Airflow mediante un DAG el cual desencadenara un Job para el procesamiento en AWS Glue.

Este proyecto permite una solución automatizada y escalable para manejar grandes volúmenes de datos provenientes del api de SpaceflightNews esto mediante la implementación de tecnologías como:

  •	Python
  
  •	NLP (Procesamiento de Lenguaje Natural)
  
  •	Apache Airflow
  
  •	Apache Spark (AWS Glue)
  
  •	RDS
  
  •	Bucket S3
  
  
Este proyecto facilitará el manejo de volúmenes de información del API   de SpaceflightNews mediante una arquitectura distribuida garantizando seguridad en el proceso y un correcto modelamiento del DaataWareHouse en RDS y un almacenamiento seguro de los datos en un bucket de S3.

La solución del presente proyecto esta orquestada por la tecnología de apache Airflow el cual es el encargado de orquestar las diferentes tareas en el DAG, con el fin de realizar un procesamiento eficiente y monitoreado.

