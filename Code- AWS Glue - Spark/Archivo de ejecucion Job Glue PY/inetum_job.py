import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
import spacy
import spacy.cli


from pyspark.sql.functions import col, explode, when
from pyspark.sql.functions import col, pandas_udf
from pyspark.sql import functions as F
from pyspark.sql.types import StringType
import pandas as pd
from pyspark.sql.functions import year
from pyspark.sql.functions import col, monotonically_increasing_id
from pyspark.sql.window import Window
from pyspark.sql.functions import row_number, col
from tenacity import retry, stop_after_attempt, wait_fixed
import logging


# Configurar logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

## @params: [JOB_NAME]
args = getResolvedOptions(sys.argv, ['JOB_NAME'])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

#
#args = getResolvedOptions(sys.argv, ['param1', 'param2'])
#param1_value = args['param1']
#param2_value = args['param2']

spacy.cli.download("en_core_web_sm")

#Instanciamos la clase Spacy para el proceso NLP
nlp = spacy.load("en_core_web_sm")

#Cadena de coneccion conector jdbc
jdbc_url = "jdbc:mysql://database-inetum.ctgecwsy06rn.us-west-2.rds.amazonaws.com:3306/inetum"
jdbc_properties = {
    "user": "admin",
    "password": "Juannicolas3",
    "driver": "com.mysql.cj.jdbc.Driver"
}

#Definimos el diccionario de las categorias para clasificar el texto de los articulos
categories = {
    "science": ["NASA", "astronomy", "telescope", "research", "space exploration", "planets", "galaxy", "physicists", "theory", "study", "astrophysicist", "space laboratory"],
    "missions": ["launch", "rocket", "mission", "crew", "space station", "rovers", "moon", "mars", "jupiter", "satellites", "orbiter", "lunar exploration", "space travel"],
    "technology": ["technology", "innovation", "reusable rockets", "artificial intelligence", "automation", "sensors", "navigation", "space systems", "advanced materials"],
    "politics": ["government", "regulation", "space policy", "funding", "legislation", "congress", "alliances", "international agreements", "space competition", "space industry", "corporations"],
    "commercial": ["company", "SpaceX", "Blue Origin", "private", "commercial launches", "private industry", "private rocket", "investors", "business development", "space market"],
    "security": ["defense", "military satellites", "national security", "cybersecurity", "military technology", "space warfare", "orbital surveillance", "space systems", "weapon systems"],
    "astronomy": ["star", "galaxy", "telescope", "observation", "exoplanets", "stellar clusters", "black holes", "nebula", "radio telescope", "spectroscopy", "search for life"],
    "climate and environment": ["climate change", "space weather", "weather satellites", "earth observation", "thermal waters", "global temperature", "solar cycle", "space climate", "solar energy"],
    "mars exploration": ["Mars", "rovers", "landing", "explorer", "martian surface", "water on Mars", "Martian atmosphere", "mission to Mars", "Curiosity", "Perseverance"],
    "astronautics": ["astronaut", "International Space Station", "spacelab", "crewed mission", "life support system", "space module", "microgravity experiments"],
    "space future": ["colonization", "terraforming", "space life", "lunar station", "nuclear rockets", "interplanetary exploration", "space transportation", "advanced propulsion systems"]
}

#Lectura de nuestros datos almacenados en el bcuket de S3 a travez del crawler y la BD del datacatalog
@retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
def load_df_from_s3():
    try:
        logger.info("proceso de lectura de los datos desde el bucket de S3")
        dyf = glueContext.create_dynamic_frame.from_catalog(database="dbflightnews", table_name="source_data_spacenews",transformation_ctx="dyf")
        return dyf
    except Exception as e:
        logger.error(f"Error al leer datos desde el bucket de S3 --- {e}")
        raise

# Cargar DataFrame con la opcion de reintentos mediante la implementacion de la clase retry
try:
    dyf = load_df_from_s3()
    logger.info("Datos cargados exitosamente desde el bucket de S3")
except Exception as e:
    logger.critical("Fallo en la lectura de datos desde el bucket de S3 ---{e}")
    sys.exit(1)
    
        

#Transofrmamos nuestos datos de un DynamicFrame a un pypark dataframe
df = dyf.toDF()

#Realziamos un aplanamiento del campo authors ya que es un array, esto con el fin de exraer el campo autor en una columna individual
df = df.withColumn("author", explode(col("authors")))
df = df.withColumn("author_name", col("author")["name"])

#Definicion de la funcion para poblar dimensiones y tabla de hechos, Guardado en MySQL
@retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
def save_to_mysql(df, table_name,mode):
    try:
        logger.info(f"Intentando guardar datos en MySQL wn la tabla ----{table_name}------")
        df.write \
            .format("jdbc") \
            .option("url", jdbc_url) \
            .option("dbtable", table_name) \
            .option("user", jdbc_properties["user"]) \
            .option("password", jdbc_properties["password"]) \
            .option("driver", jdbc_properties["driver"]) \
            .mode(mode) \
            .save()
        logger.info(f"Datos guardados exitosamente en la tabla {table_name}-------")
    except Exception as e:
        logger.error(f"Error guardando en MySQL en la tabla ---- {table_name}----{e}")
        sys.exit(1)

#Definimos las funciones que van a permitir extraer palabras claves,identidades y la clasificacion de los articulos

def extract_entities(text, entity_type):
    if not text:
        return ""
    doc = nlp(text)
    return ", ".join(set(ent.text for ent in doc.ents if ent.label_ == entity_type))
    
def extract_keywords(text):
    if not text:
        return ""
    doc = nlp(text)
    return ", ".join(set(token.text for token in doc if token.pos_ in ['NOUN', 'ADJ']))

def classif_text(text):
    if not text:
        return ""
    doc = nlp(text)
    category_scores = {category: 0 for category in categories}
    
    for token in doc:
        token_text = token.text.strip().lower()
        for category, keywords in categories.items():
            for keyword in keywords:
                if keyword.lower() in token_text:
                    category_scores[category] += 1
    category = max(category_scores, key=category_scores.get)
    
    return category

@pandas_udf(StringType())
def extract_org_udf(texts: pd.Series) -> pd.Series:
    return texts.apply(lambda x: extract_entities(x, "ORG"))

@pandas_udf(StringType())
def extract_person_udf(texts: pd.Series) -> pd.Series:
    return texts.apply(lambda x: extract_entities(x, "PERSON"))

@pandas_udf(StringType())
def extract_place_udf(texts: pd.Series) -> pd.Series:
    return texts.apply(lambda x: extract_entities(x, "LOC"))

@pandas_udf(StringType())
def extract_keywords_udf(texts: pd.Series) -> pd.Series:
    return texts.apply(lambda x: extract_keywords(x))

@pandas_udf(StringType())
def classify(texts: pd.Series) -> pd.Series:
    return texts.apply(lambda x: classif_text(x))
    
df = df.withColumn("entity_company", extract_org_udf(col("summary")))
df = df.withColumn("entity_people", extract_person_udf(col("summary")))
df = df.withColumn("entity_place", extract_place_udf(col("summary")))
df = df.withColumn("key_words", extract_keywords_udf(col("summary")))
df = df.withColumn("category", classify(col("summary")))

#Realizamos el filtrado y limpieza de nuestro dataframe final, seleccionando aquellas columnas con las que vamos a trabajar y son de interes para el desarrollo del proceso
df_final = df.select("id",
                     "summary",
                     "news_site",
                     "published_at",
                     "updated_at",
                     "title",
                     "type",
                     "author_name",                     
                     when(col("entity_company").isNull() | (col("entity_company") == ""), "None").otherwise(col("entity_company")).alias("entity_company"),                     
                     when(col("entity_people").isNull() | (col("entity_people") == ""), "None").otherwise(col("entity_people")).alias("entity_people"),                     
                     when(col("entity_place").isNull() | (col("entity_place") == ""), "None").otherwise(col("entity_place")).alias("entity_place"),                     
                     when(col("key_words").isNull() | (col("key_words") == ""), "None").otherwise(col("key_words")).alias("key_words"),
                     "category")
                     
df_final.show(2)
print("--------------Tendencias po teas de tiempo--"*20)

#Tendencias de Temas por Tiempo
df_time = df_final.withColumn("published_at", F.to_timestamp("published_at"))
df_tend = df_time.groupBy(F.month("published_at").alias("month"), "category").count()
df_tend = df_tend.orderBy("month", F.desc("count"))

df_tend.show(2)
print("-----------------fuentes as activas-----")
#Analisis de fuentes mas activas
df_sources = df_final.groupBy("news_site").count()
df_sources=df_sources.orderBy(F.desc("count"))
df_sources.show(2)

#Particion y almacenamiento de datos historicos
s3_path = "s3://source-data-spacenews/historical_data/"
# Agregar la columna de año para particionar
df_time = df_time.withColumn("year", year("published_at"))

# Reintento para escritura en S3
@retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
def save_bucket_s3(df,s3_path):
    try:
        logger.info(f"Proceso de escritura de datos en el bucket de S3 en la ruta {s3_path} de los datos con particion por año")
        # Escribir los datos en formato Parquet en S3 con partición por año
        df.write.mode("overwrite").partitionBy("year").parquet(s3_path)
        logger.info("Datos escritos exitosamente en el bcuket de  S3.")
    except Exception as e:
        logger.error(f"Error escribiendo en el bucket deS3: {e}")
        raise

save_bucket_s3(df_time,s3_path)       

#Cacheo de datos
df_final.cache()

#poblado de la dimension autor
print("--------------------------------Dimesion autor")
df_authors = df_final.select("author_name").distinct()
window_spec = Window.orderBy("author_name")
df_authors = df_authors.withColumn("id_autor", row_number().over(window_spec))
# Guardar el DataFrame en MySQL
#save_to_mysql(df_authors,"autor","append")

#Poblado de la dimencion category
print("--------------------------------Dimesion Category")
df_categories = df_final.select("category").distinct()
window_spec = Window.orderBy("category")
df_categories = df_categories.withColumn("id_category", row_number().over(window_spec))
# Guardar el DataFrame en MySQL
#save_to_mysql(df_categories,"category","append")


#Poblado de la dimensionsite
print("--------------------------------Dimesion Site")
df_site = df_final.select("news_site").distinct()
window_spec = Window.orderBy("news_site")
df_site = df_site.withColumn("id_site", row_number().over(window_spec))
# Guardar el DataFrame en MySQL
#save_to_mysql(df_site,"site","append")


#pobado de la tabla de hechos
df_final.createOrReplaceTempView("df_final")
df_site.createOrReplaceTempView("site")
df_categories.createOrReplaceTempView("category")
df_authors.createOrReplaceTempView("autor")

#Definicioon del Query
query="""SELECT 
            a.id_autor,
            s.id_site,
            c.id_category,
            COUNT(df.author_name) AS cantidad_noticias_autor,
            COUNT(*) OVER(PARTITION BY c.id_category) AS cantidad_noticias_categoria,
            COUNT(*) OVER(PARTITION BY s.id_site) AS cantidad_noticias_site
            FROM df_final df
            JOIN autor a ON (df.author_name = a.author_name)
            JOIN site s ON (df.news_site = s.news_site)
            JOIN category c ON (df.category = c.category)
            GROUP BY a.id_autor, s.id_site, c.id_category"""
# Ejecutar la consulta en Spark
df_hechos = spark.sql(query)
print("------------------tabla de hechos")
# Guardar el DataFrame en MySQL
try:
    save_to_mysql(df_hechos,"hechos","append")
except Exception as e:
    logger.critical(f"Fallo al guardar datos en la tabla hechos de MySQ----- {e}")
    sys.exit(1)

#Analisis sql
#Tendencias de temas por mes
print("-------------------Tendencias por mes")
query="""SELECT 
        DATE_TRUNC('month', df.published_at) AS month,
        c.category,
        COUNT(*) AS tendencia_count
        FROM df_final df
        JOIN category c ON (df.category = c.category)
        GROUP BY month, c.category
        ORDER BY month, tendencia_count DESC"""
# Ejecutar la consulta en Spark
df_tendencias = spark.sql(query)
df_tendencias.show()

#Fuentes mas influyentesp
print("-------------------Fuentes mas influyentes")
query="""SELECT 
        s.news_site,
        COUNT(*) AS count_sources
        FROM df_final df
        JOIN site s ON (df.news_site = s.news_site)
        GROUP BY s.news_site
        ORDER BY count_sources DESC;"""
# Ejecutar la consulta en Spark
df_FInfluyentes = spark.sql(query)
df_FInfluyentes.show()


job.commit()