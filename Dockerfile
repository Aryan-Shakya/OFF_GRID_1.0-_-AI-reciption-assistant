FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# Set environment variables to non-interactive to avoid prompts during apt installs
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Ensure data and public directories exist and have proper permissions
RUN mkdir -p data public && chmod -R 777 data public

# Expose the correct port
EXPOSE 8000

# Run the FastAPI server using Uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
