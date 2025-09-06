# This Dockerfile should be inside your new standalone project folder.

FROM python:3.10-alpine
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies directly from PyPI
RUN pip install --no-cache-dir -r requirements.txt

# Copy your application and test code
COPY ./app /app
COPY ./tests /tests

# Expose the application port
EXPOSE 8000

# Command to run the application
# We use --app-dir to solve any import issues
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]