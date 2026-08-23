import json
from pathlib import Path

# Importamos tu lógica matemática desde el módulo de dominio
from src.domains.air_quality.dataset import parsear_csv_sinca, aplicar_idw, COMUNAS

def main():
    # Calcula la ruta raíz del proyecto dinámicamente (sube 2 niveles desde /scripts/data/)
    base_dir = Path(__file__).resolve().parents[2]
    data_dir = base_dir / "data" / "air_quality"
    
    # 1. Definir las rutas de los 3 CSV crudos de SINCA
    # (Asegúrate de nombrar los archivos así al guardarlos en tu carpeta)
    ruta_pudahuel = data_dir / "pudahuel.csv"
    ruta_las_condes = data_dir / "las_condes.csv"
    ruta_puente_alto = data_dir / "puente_alto.csv"
    
    archivo_salida = data_dir / "sinca_cache.jsonl"
    
    print("Iniciando procesamiento y extrapolación de datos de SINCA...")
    
    # 2. Parsear los datos y arrastrar los últimos valores conocidos (manejo de huecos)
    datos_pudahuel = parsear_csv_sinca(ruta_pudahuel)
    datos_las_condes = parsear_csv_sinca(ruta_las_condes)
    datos_puente_alto = parsear_csv_sinca(ruta_puente_alto)
    
    # 3. Obtener una línea de tiempo unificada (todos los timestamps únicos)
    todos_los_timestamps = set(datos_pudahuel.keys()) | set(datos_las_condes.keys()) | set(datos_puente_alto.keys())
    
    # Ordenar cronológicamente (asumiendo formato DD-MM-YYYY HH:MM)
    # Como el formato de SINCA a veces es mañoso, un sort básico de string 
    # nos agrupará al menos de manera predecible para el replay secuencial.
    timestamps_ordenados = sorted(todos_los_timestamps)
    
    registros_procesados = 0
    
    # 4. Generar el archivo JSONL
    with open(archivo_salida, 'w', encoding='utf-8') as f_out:
        for ts in timestamps_ordenados:
            
            # Agrupar las mediciones reales en este instante 't'
            mediciones_en_t = {
                "Pudahuel": datos_pudahuel.get(ts),
                "Las Condes": datos_las_condes.get(ts),
                "Puente Alto": datos_puente_alto.get(ts)
            }
            
            # Evitar inyectar un instante de tiempo donde las 3 estaciones estaban caídas
            if all(v is None for v in mediciones_en_t.values()):
                continue
            
            valores_comunas = {}
            
            # Calcular el PM10 interpolado para cada comuna de la malla
            for nombre_comuna in COMUNAS.keys():
                pm10_calculado = aplicar_idw(nombre_comuna, mediciones_en_t)
                # Redondeamos a 2 decimales para no saturar el JSON
                valores_comunas[nombre_comuna] = round(pm10_calculado, 2)
                
            # Construir el objeto JSON de esta fila
            registro = {
                "timestamp": ts,
                "comunas": valores_comunas
            }
            
            # Escribir la línea en formato JSON Lines
            f_out.write(json.dumps(registro) + '\n')
            registros_procesados += 1
            
    print(f"¡Proceso finalizado! Se generaron {registros_procesados} registros interpolados.")
    print(f"Archivo guardado en: {archivo_salida}")

if __name__ == "__main__":
    main()