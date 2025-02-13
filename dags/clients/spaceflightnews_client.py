import requests
import time
import logging
from tenacity import retry, stop_after_attempt, wait_exponential
#definicion de la clase ExtractAPI que se encarga de extraer los datos de la API de Spaceflightnews
#ademas se definen los metodos para extraer los articulos, blogs y reportes segun los parametros de limit y offset

class ExtractAPI:
    
    url = "https://api.spaceflightnewsapi.net/v4"
    
    def __init__(self):
        self.session=requests.Session()
    
    #implementamos la libreria de tenacity para reintentar la peticion en caso de error
    @retry(stop=stop_after_attempt(3),wait=wait_exponential(multiplier=2))
    def get_api_data(self,endpoint,params=None):
        url = f"{self.url}/{endpoint}"
        
        response = self.session.get(url,params=params)
        
        if response.status_code == 429:
            print("Rate limit exceeded")
            time.sleep(60)
            response = self.get_api_data(endpoint,params)
        response.raise_for_status()
        return response.json()
    
    def extract_all_articles(self):
        params = {"limit":2553}
        return self.get_api_data("articles",params)
    
    def extract_all_blogs(self):
        return self.get_api_data("blogs")
    
    def extract_all_reports(self):
        return self.get_api_data("reports")
        
    def extract_articles(self,limit=10,offset=1):
        params = {
            "limit":limit,
            "offset":offset
        }
        return self.get_api_data("articles",params)
    
    def extract_blogs(self,limit=10,offset=1):
        params = {
            "limit":limit,
            "offset":offset
        }
        return self.get_api_data("blogs",params)
    
    def extract_reports(self,limit=10,offset=1):
        params = {
            "limit":limit,
            "offset":offset
        }
        return self.get_api_data("reports",params)
    
    def extract_info(self):
        return self.get_api_data("info")