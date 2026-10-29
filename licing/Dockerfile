FROM python:3.11-slim

WORKDIR /app

# Copiar el archivo de dependencias primero para optimizar la caché de Docker
COPY requirements.txt /app/

# Instalar todas las dependencias del proyecto
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . /app

# Exponer el puerto de la API
EXPOSE 8000

# Comando para iniciar uvicorn
CMD ["uvicorn", "api.index:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]