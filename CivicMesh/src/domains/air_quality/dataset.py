import csv
import math

# Coordenadas geográficas aproximadas
ESTACIONES = {
    "Pudahuel": (-33.445, -70.755),
    "Las Condes": (-33.411, -70.522),
    "Puente Alto": (-33.611, -70.575)
}

COMUNAS = {
    "Santiago": (-33.440, -70.653),
    "Providencia": (-33.431, -70.606),
    "Ñuñoa": (-33.454, -70.601),
    "Maipú": (-33.510, -70.756),
    "Las Condes": (-33.411, -70.522),
    "La Florida": (-33.521, -70.598)
}

def calcular_distancia(lat1, lon1, lat2, lon2):
    """Calcula la distancia real en km usando la fórmula de Haversine."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def aplicar_idw(comuna, mediciones_en_t):
    """
    Interpola el valor de PM10 para una comuna usando Inverse Distance Weighting.
    mediciones_en_t = {"Pudahuel": 69, "Las Condes": 45, "Puente Alto": 50}
    """
    lat_c, lon_c = COMUNAS[comuna]
    numerador = 0.0
    denominador = 0.0
    
    for estacion, valor in mediciones_en_t.items():
        if valor is None:
            continue
            
        lat_s, lon_s = ESTACIONES[estacion]
        distancia = calcular_distancia(lat_c, lon_c, lat_s, lon_s)
        
        # Caso base: la comuna coincide con la estación
        if distancia < 0.1: 
            return valor
            
        # Potencia p=2
        peso = 1.0 / (distancia**2) 
        numerador += peso * valor
        denominador += peso
        
    return numerador / denominador if denominador > 0 else 0.0

def parsear_csv_sinca(ruta_archivo):
    """
    Lee el CSV, salta las primeras filas y arrastra el último valor conocido 
    si hay celdas vacías.
    """
    historico = {}
    ultimo_valor_conocido = None
    
    with open(ruta_archivo, mode='r', encoding='utf-8') as f:
        # En Chile, es común que Excel exporte CSV separados por punto y coma
        lector = csv.reader(f, delimiter=';') 
        
        for fila in lector:
            # Buscamos la fila de cabeceras para empezar a leer
            if fila and "Fecha y hora" in fila[0]:
                break
                
        for fila in lector:
            if len(fila) < 2:
                continue
                
            fecha_str = fila[0].strip()
            mp10_str = fila[1].strip()
            
            if mp10_str:
                # Actualiza la memoria si hay un dato nuevo
                ultimo_valor_conocido = float(mp10_str.replace(',', '.'))
            
            historico[fecha_str] = ultimo_valor_conocido
            
    return historico