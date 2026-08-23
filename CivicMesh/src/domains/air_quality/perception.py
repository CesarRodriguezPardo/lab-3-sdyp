import random

def calcular_percepcion_aire(v_c, m_c_prev, rumores_q, config, comuna, timestamp):
    r"""
    Calcula el índice de percepción ciudadana para PM10/PM2.5.
    
    Args:
        v_c (float): El valor objetivo actual de la serie real (ground truth).
        m_c_prev (float): La memoria EMA del paso anterior M_c(t - \Delta t).
        rumores_q (list): Lista con los valores subjetivos recibidos por gossip (multiconjunto Q).
        config (dict): Parámetros estocásticos cargados desde config.yaml.
        comuna (str): Nombre del tópico/comuna (usado para el seed).
        timestamp (str/int): Marca de tiempo del paso (usado para el seed).
        
    Returns:
        tuple: (P_c, M_c_actual) La nueva percepción calculada y el estado actualizado de la memoria.
    """
    # 1. Cargar parámetros (usando los valores sugeridos como default)
    alpha = config.get('alpha', 0.85)
    gamma = config.get('gamma', 0.6)  # Sesgo por pico retenido
    delta = config.get('delta', 0.3)  # Arrastre por rumor
    sigma_eps = config.get('sigma_epsilon', 2.0)
    seed_base = config.get('seed', 42)
    
    # 2. Procesar los rumores de Gossip (p_gossip)
    p_gossip = 0.0
    if rumores_q and len(rumores_q) > 0:
        p_gossip = sum(rumores_q) / len(rumores_q)
        
    # 3. Estímulo con memoria de pico
    u_c = max(v_c, m_c_prev)
    
    # 4. Actualizar estado de la memoria EMA
    m_c_actual = alpha * m_c_prev + (1.0 - alpha) * u_c
    
    # 5. Generar ruido estocástico \epsilon_c(t)
    # Se genera un RNG reproducible basado en la semilla base, la comuna y el timestamp
    estado_aleatorio = f"{seed_base}_{comuna}_{timestamp}"
    random.seed(estado_aleatorio)
    epsilon_c = random.gauss(0, sigma_eps)
    
    # 6. Calcular percepción final P_c(t)
    p_c = v_c + gamma * (m_c_actual - v_c) + delta * p_gossip + epsilon_c
    
    # 7. Aplicar clip a un rango físico razonable [0; 500] sugerido en el PDF
    p_c = max(0.0, min(p_c, 500.0))
    
    return p_c, m_c_actual