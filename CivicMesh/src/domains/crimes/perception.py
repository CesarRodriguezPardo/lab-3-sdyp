import math
import random

def _sigma(z):
    """Función sigmoide (logística) (1 + e^-z)^-1"""
    # Acotamos z para evitar errores de Overflow en math.exp
    z = max(-700.0, min(700.0, z))
    return 1.0 / (1.0 + math.exp(-z))

def calcular_inseguridad(r_c, m_c_prev, rumores_q, config, comuna, timestamp):
    """
    Calcula el índice de sensación de inseguridad P_c(t) en [0, 1].
    
    Args:
        r_c (int): Suma de delitos simulados en el paso t (Ground Truth local).
        m_c_prev (float): Memoria EMA del paso anterior.
        rumores_q (list): Valores subjetivos recibidos por gossip.
        config (dict): Diccionario 'perception' cargado del YAML.
    """
    # 1. Cargar parámetros
    alpha = config.get('alpha', 0.8)
    beta_0 = config.get('beta_0', -1.0)
    beta_1 = config.get('beta_1', 0.4)
    beta_2 = config.get('beta_2', 0.8)
    sigma_eps = config.get('sigma_epsilon', 0.1)
    seed_base = config.get('seed', 42)
    
    # 2. Promedio de rumores (P_gossip)
    p_gossip = 0.0
    if rumores_q and len(rumores_q) > 0:
        p_gossip = sum(rumores_q) / len(rumores_q)
        
    # 3. Estímulo u_c(t) = R_c(t)
    u_c = r_c
    
    # 4. Actualizar memoria EMA
    m_c_actual = alpha * m_c_prev + (1.0 - alpha) * u_c
    
    # 5. Generar ruido estocástico \epsilon_c(t)
    estado_aleatorio = f"{seed_base}_{comuna}_perception_{timestamp}"
    random.seed(estado_aleatorio)
    epsilon_c = random.gauss(0, sigma_eps)
    
    # 6. Calcular Z_c(t)
    z_c = beta_0 + beta_1 * m_c_actual + beta_2 * p_gossip + epsilon_c
    
    # 7. Aplicar función logística P_c(t) = \sigma(Z_c(t))
    p_c = _sigma(z_c)
    
    return p_c, m_c_actual