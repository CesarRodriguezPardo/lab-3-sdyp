FROM python:3.11-slim

# Evitar que Python bufferice la salida y no escriba archivos .pyc
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/CivicMesh

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación y configuración
COPY . .

# Puerto por defecto
EXPOSE 8000

# Comando por defecto para arrancar un peer
ENTRYPOINT ["python", "-m", "CivicMesh.src.main"]
CMD ["--host", "0.0.0.0", "--port", "8000", "--hostfile", "/app/runs/hostfile.txt"]
