# Use an official Python runtime as a parent image.
FROM python:3.10-slim

# Set the working directory in the container.
WORKDIR /app

# Install system dependencies, e.g. LibreOffice for DOCX-to-PDF conversion.
RUN apt-get update && apt-get install -y libreoffice && rm -rf /var/lib/apt/lists/*

# Copy requirements file and install Python dependencies.
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code.
COPY . .

# Expose the port that your FastAPI app will run on.
EXPOSE 3000

# Start the FastAPI app using Uvicorn.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3000"]
