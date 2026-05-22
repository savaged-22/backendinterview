# Usa una imagen base ligera de Python
FROM python:3.9-slim

# Establece el directorio de trabajo en el contenedor
WORKDIR /app

# Copia los archivos de requisitos y luego instálalos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el código de la aplicación al directorio de trabajo
COPY . .

# Expone el puerto en el que la aplicación Flask se ejecutará
EXPOSE 5001

# Comando para ejecutar la aplicación Flask
# Asegúrate de que tu aplicación Flask esté configurada para escuchar en 0.0.0.0
CMD ["python", "servicio_productos.py"]