# Start with a more complete base image
FROM python:3.9-slim-bullseye

# Install system dependencies with more ODBC-related packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    unixodbc \
    unixodbc-dev \
    odbcinst \
    odbcinst1debian2 \
    libodbc1 \
    && rm -rf /var/lib/apt/lists/*

# Verify ODBC installation
RUN odbcinst -j && ls -l /usr/lib/x86_64-linux-gnu/libodbc*

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Explicitly set the port Streamlit should use (SquadBase often expects 8080)
ENV STREAMLIT_SERVER_PORT=8080

# Command to run the Streamlit app
CMD ["streamlit", "run", "your_app.py", "--server.port=8080", "--server.address=0.0.0.0"]