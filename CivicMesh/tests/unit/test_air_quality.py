import pytest
from src.domains.air_quality.dataset import aplicar_idw, COMUNAS

def test_aplicar_idw_coordenada_exacta():
    """Si la comuna es la misma que la estación, debe retornar el valor exacto."""
    # Las Condes está en la lista de estaciones y comunas
    mediciones = {"Pudahuel": 69, "Las Condes": 45, "Puente Alto": 50}
    
    # Debería heredar instantáneamente el 45
    resultado = aplicar_idw("Las Condes", mediciones)
    assert resultado == 45.0

def test_aplicar_idw_interpolacion():
    """Para una comuna sin estación, debe retornar un promedio ponderado válido."""
    mediciones = {"Pudahuel": 100, "Las Condes": 50, "Puente Alto": 50}
    
    # Santiago está entre medio, debería dar un valor interpolado mayor a 0
    resultado = aplicar_idw("Santiago", mediciones)
    assert resultado > 0.0
    assert resultado < 100.0  # Lógica básica: no puede superar el máximo