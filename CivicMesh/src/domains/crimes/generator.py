import math
import random

def _generar_poisson(lam, seed_str):
    """
    Genera una muestra de una distribución de Poisson usando el algoritmo de Knuth.
    Requiere una semilla string para asegurar la reproducibilidad.
    """
    random.seed(seed_str)
    L = math.exp(-lam)
    k = 0
    p = 1.0
    
    while p > L:
        k += 1
        p *= random.random()
        
    return k - 1

def generar_delitos(comuna, config, timestamp, delta_t=1.0):
    """
    Genera los eventos de delitos para una comuna en un instante t.
    
    Returns:
        tuple: (lista_eventos, total_delitos_r_c)
    """
    lambdas = config.get('lambdas', {})
    seed_base = config.get('seed', 42)
    
    eventos = []
    total_delitos = 0
    
    for tipo, tasa in lambdas.items():
        # Cálculo de \lambda_{c,k} \Delta t
        lam_efectiva = tasa * delta_t
        
        # RNG documentado en PDF: semilla + hash(c, k, t) para que cada
        # tipo de delito en cada comuna y en cada instante sea determinista.
        seed_str = f"{seed_base}_{comuna}_{tipo}_{timestamp}"
        
        count = _generar_poisson(lam_efectiva, seed_str)
        
        if count > 0:
            eventos.append({
                "comuna": comuna,
                "tipo": tipo,
                "count": count,
                "timestamp": timestamp
            })
            total_delitos += count
            
    # Retorna los eventos individuales para el canal objetivo
    # y la suma total R_c(t) para usarla como estímulo en el canal subjetivo.
    return eventos, total_delitos