import pytest
from src.domains.air_quality.perception import calcular_percepcion_aire
from src.domains.crimes.generator import generar_delitos

def test_percepcion_aire_reproducibilidad():
    """Dos llamadas con el mismo estado inicial deben generar el mismo ruido exacto."""
    config = {'alpha': 0.85, 'gamma': 0.6, 'delta': 0.3, 'sigma_epsilon': 2.0, 'seed': 42}
    
    # Primera corrida
    p_c_1, m_c_1 = calcular_percepcion_aire(100.0, 50.0, [110.0, 105.0], config, "Maipú", "2026-08-22T17:00")
    
    # Segunda corrida exacta
    p_c_2, m_c_2 = calcular_percepcion_aire(100.0, 50.0, [110.0, 105.0], config, "Maipú", "2026-08-22T17:00")
    
    assert p_c_1 == p_c_2
    assert m_c_1 == m_c_2

def test_generador_delitos_reproducibilidad():
    """El generador de Poisson debe dar la misma secuencia con la misma semilla."""
    config = {'lambdas': {'robo': 2.0}, 'seed': 99}
    
    eventos_1, total_1 = generar_delitos("Santiago", config, "t1", delta_t=1.0)
    eventos_2, total_2 = generar_delitos("Santiago", config, "t1", delta_t=1.0)
    
    assert total_1 == total_2
    assert eventos_1 == eventos_2